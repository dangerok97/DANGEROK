"""Durable orchestration around the SAME conversational Core.

No source classification, new AI planner, implicit grant, external send or new
scheduler. The existing ConnectedLifeService may opt an owner into this lane.
A local write with an uncertain outcome is quarantined, NEVER replayed blindly.
The initial pilot permits one governed local mutation per observed source;
this is an effect budget, not a rule deciding what a message means.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import uuid
from zoneinfo import ZoneInfo

from connected.source_read import resolve_source
from conversation_engine.ai_core.models import Observation
from conversation_engine.ai_core.source_activation import SourceActivation

LEASE_SECONDS = 240
TURN_SECONDS = 180
MAX_ATTEMPTS = 5
COLLECTION = 'connected_signals'


def _now():
    return datetime.now(timezone.utc)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                   separators=(',', ':')).encode()).hexdigest()


def enabled_for(owner_id):
    # Infrastructure enrolment is not consent. The original authority handlers
    # still decide whether every specific effect is within an existing grant.
    owners = {x.strip() for x in os.environ.get('ORA_SOURCE_CORE_PILOT_OWNERS', '').split(',') if x.strip()}
    return bool(owner_id and owner_id in owners and '*' not in owners)


def _event_version(node):
    return _digest({key: node.get(key) for key in
                    ('id', 'user_id', 'type', 'status', 'label', 'description', 'attributes', 'updated_at')})


class LeaseLost(RuntimeError):
    pass


class SourceWork:
    def __init__(self, db, row, token):
        self.db, self.row, self.token = db, row, token
        self.owner = row['owner_id']
        self.signal_id = row['id']
        self.ref = 'signal:' + self.signal_id

    def fence(self):
        return {'owner_id': self.owner, 'id': self.signal_id,
                'fingerprint': self.row['fingerprint'], 'observed_at': self.row['observed_at'],
                'status': 'pending', '_supersession_pending': {'$ne': True},
                '_core_work.token': self.token,
                '_core_work.lease_until': {'$gt': _now().isoformat()}}

    async def current(self):
        row = await self.db[COLLECTION].find_one(self.fence(), {'_id': 0})
        if row is None:
            raise LeaseLost('source_claim_no_longer_owned')
        return row

    async def change(self, values, *, extra=None):
        result = await self.db[COLLECTION].update_one(
            {**self.fence(), **(extra or {})}, {'$set': values})
        if not result.matched_count:
            raise LeaseLost('source_claim_changed')

    async def before_effect(self, name, arguments):
        row = await self.current()
        previous = (row.get('_core_work') or {}).get('effect')
        key = _digest([name, arguments])
        if previous:
            if previous.get('state') == 'verified' and previous['key'] == key:
                return Observation.model_validate(previous['observation'])
            raise RuntimeError('source_effect_budget_or_reconciliation_required')
        await self.change({'_core_work.effect': {
            'key': key, 'capability': name, 'state': 'started',
            'started_at': _now().isoformat(),
        }}, extra={'_core_work.effect': {'$exists': False}})
        return None

    async def after_effect(self, name, arguments, result):
        # Persist only a compact receipt and a hash of actual state, not tool
        # arguments, raw source content or an unverified model assertion.
        if result.status != 'ok' or result.payload.get('verified') is not True:
            await self.change({'_core_work.effect.state': 'unverified'})
            return
        ref = result.payload.get('calendar_ref')
        if not isinstance(ref, str) or not ref.startswith('calendar:') or ref not in result.provenance:
            raise RuntimeError('verified_effect_missing_owned_reference')
        from home.manual_event import get_manual_event
        node = await get_manual_event(self.db, self.owner, ref.removeprefix('calendar:'))
        if not node or node.get('status') != 'active':
            raise RuntimeError('effect_readback_unavailable')
        receipt = Observation(kind='tool', name=name, status='ok', payload={
            'status': 'ok', 'operation': result.payload.get('operation'),
            'verified': True, 'calendar_ref': ref, 'provider': 'ora',
        }, provenance=[ref])
        await self.change({'_core_work.effect': {
            'key': _digest([name, arguments]), 'capability': name, 'state': 'verified',
            'observation': receipt.model_dump(), 'event_version': _event_version(node),
            'verified_at': _now().isoformat(),
        }})

    async def finish_from_receipt(self):
        row = await self.current()
        effect = (row.get('_core_work') or {}).get('effect') or {}
        if effect.get('state') != 'verified':
            await self.change({'_core_work.phase': 'reconciliation_required',
                               '_core_work.lease_until': _now().isoformat()})
            return {'state': 'reconciliation_required', 'home_visible': False, 'notifications_sent': False}
        # Result and pending handoff share the original durable source document.
        # A crash after this write never requires repeating the model or effect.
        await self.change({'_core_work.phase': 'result_ready', '_core_work.home_pending': True})
        return await self.show_home()

    async def show_home(self):
        row = await self.current()
        effect = row['_core_work']['effect']
        ref = effect['observation']['payload']['calendar_ref']
        activity_id = 'ambsrc_' + _digest([self.owner, self.signal_id, self.row['fingerprint']])[:32]
        from home.manual_event import get_manual_event
        from delivery.service import DeliveryService

        async def still_current():
            await self.current()
            signal, _ = await resolve_source(self.db, self.owner, self.ref)
            if signal.fingerprint != self.row['fingerprint'] or signal.observed_at != self.row['observed_at']:
                raise LeaseLost('source_revision_changed')
            node = await get_manual_event(self.db, self.owner, ref.removeprefix('calendar:'))
            if not node or node.get('status') != 'active' or _event_version(node) != effect['event_version']:
                raise ValueError('effect_has_changed')
            return node

        try:
            node = await still_current()
            attrs = node['attributes']
            moment = datetime.fromisoformat(attrs['starts_at'].replace('Z', '+00:00'))
            moment = moment.astimezone(ZoneInfo(attrs.get('timezone') or 'Europe/Rome'))
            operation = effect['observation']['payload'].get('operation')
            verbs = {'created': 'Ho aggiunto', 'already_created': 'È già presente',
                     'updated': 'Ho aggiornato', 'already_updated': 'È già aggiornato'}
            verb = verbs.get(operation)
            if verb is None:
                raise ValueError('unsupported_verified_operation')
            summary = (f'{verb} nel calendario ORA «{node["label"][:95]}»: '
                       f'{moment:%d/%m/%Y} alle {moment:%H:%M}.')
            await DeliveryService(self.db).note_activity(
                self.owner, kind='change_processed', summary=summary,
                source_refs=[self.ref, ref], visible=True, activity_id=activity_id,
                provenance={'source_core': True, 'source_fingerprint': self.row['fingerprint'],
                            'event_version': effect['event_version'], 'verified': True})
            saved = await self.db.ambient_activity.find_one(
                {'id': activity_id, 'owner_id': self.owner, 'visibility': 'ambient'}, {'_id': 0})
            if not saved or saved.get('summary') != summary[:200]:
                raise RuntimeError('home_write_not_verified')
            await still_current()
            await self.change({'status': 'interpreted', 'outcome': 'source_core_effect_verified',
                'interpreted_at': _now().isoformat(), '_core_work.phase': 'completed',
                '_core_work.home_pending': False, '_core_work.home_activity_id': activity_id,
                '_core_work.lease_until': _now().isoformat()})
            return {'state': 'completed', 'home_visible': True, 'activity_id': activity_id,
                    'notifications_sent': False}
        except (ValueError, LeaseLost):
            # Never leave a newly materialised stale result visible when its
            # original source/event changed during the handoff.
            await self.db.ambient_activity.update_one(
                {'id': activity_id, 'owner_id': self.owner}, {'$set': {'visibility': 'internal'}})
            try:
                await self.change({'_core_work.phase': 'stale_result', '_core_work.home_pending': False,
                                   '_core_work.lease_until': _now().isoformat()})
            except LeaseLost:
                pass
            return {'state': 'stale_result', 'home_visible': False, 'notifications_sent': False}


class _LeasedActivation(SourceActivation):
    async def validate(self, db, owner_id):
        await self.work.current()
        await super().validate(db, owner_id)

    def restrict_registry(self, registry):
        registry = super().restrict_registry(registry)
        for name, spec in list(registry._tools.items()):
            if spec.side_effect == 'READ_ONLY':
                continue
            handler = spec.handler
            async def once(arguments, runtime, *, handler=handler, name=name):
                await self.validate(runtime['db'], runtime['user_id'])
                # A source read is a real dependency, not merely an instruction
                # the model may disregard. Original effect authority remains in
                # the wrapped handler and is not replaced by this budget.
                if self.context['content_access']['state'] != 'read':
                    return Observation(kind='tool', name=name, status='partial',
                        payload={'status': 'source_read_required'})
                cached = await self.work.before_effect(name, arguments)
                if cached is not None:
                    return cached
                result = await handler(arguments, runtime)
                await self.work.after_effect(name, arguments, result)
                return result
            registry._tools[name] = replace(spec, handler=once)
        return registry


class SourceCoreWorker:
    def __init__(self, db):
        self.db = db

    async def claim(self, owner_id, signal_id):
        stamp = _now().isoformat()
        token = uuid.uuid4().hex
        row = await self.db[COLLECTION].find_one_and_update({
            'owner_id': owner_id, 'id': signal_id, 'status': 'pending',
            'origin': {'$ne': 'self_originated'}, '_supersession_pending': {'$ne': True},
            '$and': [
                {'$or': [{'_core_work.phase': {'$exists': False}},
                         {'_core_work.phase': {'$in': ['running', 'retry', 'result_ready']}}]},
                {'$or': [{'_core_work.lease_until': {'$exists': False}},
                         {'_core_work.lease_until': {'$lte': stamp}}]},
                {'$or': [{'_core_work.next_run_at': {'$exists': False}},
                         {'_core_work.next_run_at': {'$lte': stamp}}]},
                {'$or': [{'_core_work.attempts': {'$exists': False}},
                         {'_core_work.attempts': {'$lt': MAX_ATTEMPTS}}]},
            ],
        }, {'$set': {'_core_work.phase': 'running', '_core_work.token': token,
                    '_core_work.lease_until': (_now() + timedelta(seconds=LEASE_SECONDS)).isoformat()},
            '$inc': {'_core_work.attempts': 1}}, return_document=True, projection={'_id': 0})
        return SourceWork(self.db, row, token) if row else None

    async def process_one(self, owner_id, signal_id, *, decision_fn=None):
        work = await self.claim(owner_id, signal_id)
        if work is None:
            return {'state': 'not_claimed', 'home_visible': False, 'notifications_sent': False}
        try:
            if (work.row.get('_core_work') or {}).get('effect'):
                return await work.finish_from_receipt()
            from conversation_engine.models import ConversationSession
            from conversation_engine.ai_core.loop import run_cognitive_loop
            from llm.model_contract import scoped_model_contract
            contract = os.environ.get('ORA_SOURCE_MODEL_CONTRACT')
            if decision_fn is None and not contract:
                raise RuntimeError('source_model_contract_required')
            activation = await _LeasedActivation.load(self.db, owner_id, signal_id)
            activation.work = work
            activation.context['effect_budget'] = {'maximum_writes': 1, 'remaining_writes': 1}
            sess = ConversationSession(user_id=owner_id, meta={'entry_point': 'durable_source_change'})
            with scoped_model_contract(contract):
                result = await asyncio.wait_for(run_cognitive_loop(
                    sess=sess, user_message='', db=self.db, max_steps=8,
                    decision_fn=decision_fn, source_activation=activation), TURN_SECONDS)
            current = await work.current()
            if (current.get('_core_work') or {}).get('effect'):
                return await work.finish_from_receipt()
            if not result.ok or activation.context['content_access']['state'] != 'read':
                raise RuntimeError('source_turn_not_verified')
            # This is not proof that the model's no-effect decision was useful.
            # No success notification or event is invented for a text answer.
            phase = 'needs_input' if result.mode == 'clarify' else 'reviewed_no_effect'
            await work.change({'status': 'interpreted', 'outcome': 'source_core_' + phase,
                'interpreted_at': _now().isoformat(), '_core_work.phase': phase,
                '_core_work.lease_until': _now().isoformat()})
            return {'state': phase, 'home_visible': False, 'notifications_sent': False}
        except LeaseLost:
            return {'state': 'lease_lost', 'home_visible': False, 'notifications_sent': False}
        except Exception as exc:
            # Preserve unknown writes and successful receipts. Never turn an
            # outage after an effect into permission to execute it once more.
            row = await work.current()
            effect = (row.get('_core_work') or {}).get('effect') or {}
            phase = ('result_ready' if effect.get('state') == 'verified' else
                     'reconciliation_required' if effect else
                     'failed' if row['_core_work']['attempts'] >= MAX_ATTEMPTS else 'retry')
            await work.change({'_core_work.phase': phase,
                '_core_work.last_error_kind': type(exc).__name__,
                '_core_work.lease_until': _now().isoformat(),
                '_core_work.next_run_at': (_now() + timedelta(seconds=30)).isoformat()})
            return {'state': phase, 'home_visible': False, 'notifications_sent': False}

    async def process_pending(self, owner_id, *, limit=2):
        rows = await self.db[COLLECTION].find({
            'owner_id': owner_id, 'status': 'pending', '_supersession_pending': {'$ne': True},
            '$or': [{'_core_work.phase': {'$exists': False}},
                    {'_core_work.phase': {'$in': ['running', 'retry', 'result_ready']}}],
        }, {'_id': 0, 'id': 1, 'origin': 1}).sort('observed_at', 1).to_list(min(max(limit, 1), 6))
        results = []
        for row in rows:
            if row.get('origin') == 'self_originated':
                from connected.signals import SignalService
                await SignalService(self.db).settle(owner_id, row['id'], outcome='own_work_confirmed')
                continue
            results.append(await self.process_one(owner_id, row['id']))
        return {'ok': True, 'looked_at': len(results), 'noise': 0,
                'passed_on': sum(r['state'] == 'completed' for r in results),
                'source_core_results': results}
