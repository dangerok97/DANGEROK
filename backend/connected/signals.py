"""Owner-scoped source observations, deduplicated without disguising lost writes.

Source content is not interpreted here. Storage acknowledges an observation only
when it is durable; a read/write outage is not a duplicate or a verdict of noise.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from pymongo.errors import DuplicateKeyError
from connected.models import ConnectedSignal, now_iso

logger = logging.getLogger('ora.connected.signals')
SIGNALS = 'connected_signals'
RETENTION_DAYS = 30
MAX_PENDING = 12


def _source_scope(signal: ConnectedSignal) -> Dict[str, str]:
    return {'owner_id': signal.owner_id, 'source_id': signal.source_id,
            'source_type': signal.source_type}


def _storage_identity(signal: ConnectedSignal) -> Tuple[str, str]:
    """Version the storage key while retaining the original delta fingerprint.

    The original fingerprint omitted the connection id. Preserve it solely for
    finding old rows in the SAME source, never for merging different mailboxes.
    Opaque connection identifiers are exact: do not case-fold or trim them.
    """
    legacy = signal.compute_fingerprint()
    encoded = json.dumps(['source-v2', signal.owner_id, signal.source_type,
                          signal.source_id, legacy], separators=(',', ':'))
    return hashlib.sha256(encoded.encode()).hexdigest()[:32], legacy


class SignalService:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        try:
            # Retain the legacy index; new fingerprints include their source.
            await self.db[SIGNALS].create_index(
                [('owner_id', 1), ('fingerprint', 1)], unique=True)
            await self.db[SIGNALS].create_index([('owner_id', 1), ('status', 1)])
            await self.db[SIGNALS].create_index([
                ('owner_id', 1), ('source_id', 1), ('source_type', 1),
                ('source_object_ref', 1), ('status', 1)])
            await self.db[SIGNALS].create_index('expires_at', expireAfterSeconds=0)
        except Exception:
            logger.exception('indici connected signals non creati (non fatale)')

    async def _repair_supersession(self, doc: Dict[str, Any]) -> None:
        """Finish only a recorded predecessor transition; safe to retry.

        Incomplete new rows are withheld from pending/get until this succeeds.
        A late worker cannot overwrite a revoked or already-settled predecessor.
        No original email/document body is stored as part of this checkpoint.
        """
        if not doc.get('_supersession_pending'):
            return
        predecessor = doc.get('supersedes')
        if predecessor and predecessor != doc['id']:
            await self.db[SIGNALS].update_one(
                {'owner_id': doc['owner_id'], 'source_id': doc.get('source_id', ''),
                 'source_type': doc['source_type'], 'source_object_ref': doc['source_object_ref'],
                 'id': predecessor, 'status': 'pending'},
                {'$set': {'status': 'superseded'}})
        await self.db[SIGNALS].update_one(
            {'_id': doc['_id'], 'owner_id': doc['owner_id'], 'fingerprint': doc['fingerprint']},
            {'$unset': {'_supersession_pending': ''}})

    async def record(self, signal: ConnectedSignal) -> Tuple[Optional[ConnectedSignal], str]:
        """Keep an observation or report a VERIFIED duplicate; other errors raise.

        Never invalidate pending work before its replacement has been inserted.
        The deterministic Mongo _id closes identical-insert races even while an
        optional secondary index is unavailable. Legacy rows keep their ids and
        status, so adopting this key does not replay all already-reviewed mail.
        """
        if not signal.owner_id:
            return None, 'no_owner'
        fingerprint, legacy = _storage_identity(signal)
        signal.fingerprint = fingerprint
        identity = {**_source_scope(signal), 'fingerprint': {'$in': [fingerprint, legacy]}}
        existing = await self.db[SIGNALS].find_one(identity)
        if existing is not None:
            await self._repair_supersession(existing)
            return None, 'duplicate'

        predecessor = None
        # supersedes is storage-owned, not a caller-supplied mutation target.
        signal.supersedes = ''
        if signal.source_object_ref:
            predecessor = await self.db[SIGNALS].find_one(
                {**_source_scope(signal), 'source_object_ref': signal.source_object_ref,
                 'status': 'pending', '_supersession_pending': {'$ne': True}},
                {'_id': 0, 'id': 1}, sort=[('observed_at', -1)])
            if predecessor:
                signal.supersedes = str(predecessor['id'])

        doc = signal.model_dump()
        key = json.dumps([signal.owner_id, fingerprint], separators=(',', ':'))
        doc['_id'] = 'connected_signal:' + hashlib.sha256(key.encode()).hexdigest()
        doc['fingerprint_version'] = 2
        doc['expires_at'] = datetime.now(timezone.utc) + timedelta(days=RETENTION_DAYS)
        if predecessor:
            doc['_supersession_pending'] = True
        try:
            await self.db[SIGNALS].insert_one(doc)
        except DuplicateKeyError:
            # A colliding key alone does not prove this observation exists.
            # Verify the full source identity before calling the error harmless.
            saved = await self.db[SIGNALS].find_one(identity)
            if saved is None:
                raise
            await self._repair_supersession(saved)
            return None, 'duplicate'
        # A lost acknowledgement or other storage failure propagates. On retry,
        # lookup above can finish a persisted but incomplete replacement safely.
        await self._repair_supersession(doc)
        return signal, 'superseded_previous' if predecessor else 'recorded'

    async def pending(self, owner_id: str, *, limit: int = MAX_PENDING) -> List[ConnectedSignal]:
        docs = await self.db[SIGNALS].find(
            {'owner_id': owner_id, 'status': 'pending', '_supersession_pending': {'$ne': True}},
            {'_id': 0}).sort('observed_at', 1).to_list(limit)
        return [ConnectedSignal.model_validate(d) for d in docs]

    async def get(self, owner_id: str, signal_id: str) -> Optional[ConnectedSignal]:
        doc = await self.db[SIGNALS].find_one(
            {'owner_id': owner_id, 'id': signal_id, '_supersession_pending': {'$ne': True}}, {'_id': 0})
        return ConnectedSignal.model_validate(doc) if doc else None

    async def history(self, owner_id: str, source_object_ref: str, *, limit: int = 6) -> List[ConnectedSignal]:
        docs = await self.db[SIGNALS].find(
            {'owner_id': owner_id, 'source_object_ref': source_object_ref,
             '_supersession_pending': {'$ne': True}}, {'_id': 0}).sort('observed_at', -1).to_list(limit)
        return [ConnectedSignal.model_validate(d) for d in docs]

    async def settle(self, owner_id: str, signal_id: str, *, outcome: str) -> None:
        """One pending observation can settle once; a late result cannot revive it."""
        await self.db[SIGNALS].update_one(
            {'owner_id': owner_id, 'id': signal_id, 'status': 'pending',
             '_supersession_pending': {'$ne': True}},
            {'$set': {'status': 'interpreted', 'interpreted_at': now_iso(), 'outcome': str(outcome)[:60]}})

    async def skip(self, owner_id: str, signal_id: str, *, why: str) -> None:
        await self.db[SIGNALS].update_one(
            {'owner_id': owner_id, 'id': signal_id, 'status': 'pending',
             '_supersession_pending': {'$ne': True}},
            {'$set': {'status': 'skipped', 'interpreted_at': now_iso(), 'outcome': str(why)[:60]}})

    async def forget_all(self, owner_id: str) -> int:
        result = await self.db[SIGNALS].delete_many({'owner_id': owner_id})
        return result.deleted_count
