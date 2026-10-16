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
import hmac
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
PILOT_ENROLLMENTS = 'source_pilot_enrollments'


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


def pilot_email_allowed(email):
    """Server-managed single-account canary gate; never a global wildcard."""
    raw = os.environ.get('ORA_SOURCE_SINGLE_PILOT_EMAIL_SHA256', '').strip().lower()
    if len(raw) != 64 or not all(ch in '0123456789abcdef' for ch in raw):
        return False
    digest = hashlib.sha256(str(email or '').strip().casefold().encode()).hexdigest()
    return hmac.compare_digest(digest, raw)


async def pilot_enrollment(db, owner_id):
    """Read only this owner's opt-in; rotating the server digest disables it."""
    if not owner_id:
        return None
    raw = os.environ.get('ORA_SOURCE_SINGLE_PILOT_EMAIL_SHA256', '').strip().lower()
    if len(raw) != 64:
        return None
    row = await db[PILOT_ENROLLMENTS].find_one(
        {'_id': 'pilot:' + owner_id, 'owner_id': owner_id,
         'email_digest': raw, 'active': True}, {'_id': 0})
    if not row or row.get('created_by') != 'authenticated_user':
        return None
    if not isinstance(row.get('since'), str) or not row['since']:
        return None
    return row


async def enroll_owner(db, owner_id, email):
    """Idempotent single-user enrollment, never used to create a grant."""
    if not pilot_email_allowed(email):
        return {'ok': False, 'reason': 'account_not_in_pilot'}
    if not await ready_for_owner(db, owner_id, require_enrollment=False):
        return {'ok': False, 'reason': 'mode_or_create_permission_required'}
    previous = await pilot_enrollment(db, owner_id)
    if previous:
        return {'ok': True, 'already_active': True}
    digest = hashlib.sha256(str(email).strip().casefold().encode()).hexdigest()
    # A new enrollment establishes the boundary for fresh messages. Ignore
    # historical signals instead of unexpectedly replaying months of mail.
    await db[PILOT_ENROLLMENTS].update_one(
        {'_id': 'pilot:' + owner_id, 'owner_id': owner_id},
        {'$set': {'owner_id': owner_id, 'email_digest': digest, 'active': True,
                  'created_by': 'authenticated_user', 'since': _now().isoformat()}},
        upsert=True)
    return {'ok': True, 'already_active': False}


async def ready_for_owner(db, owner_id, *, require_enrollment=True):
    """Whether this enrolled owner explicitly opted into the first source pilot.

    Infrastructure enrollment is deliberately insufficient. Until the person
    has chosen act-within-grants AND granted create-only local-calendar
    authority, Connected Life must keep using its legacy interpretation path.
    That preserves pending source observations instead of letting a background
    worker consume them into an invisible needs_input state before opt-in.
    """
    if require_enrollment and not enabled_for(owner_id) and not await pilot_enrollment(db, owner_id):
        return False
    from agent.authority import AuthorityService, GRANTS
    from agent.models import AutonomyGrant

    authority = AuthorityService(db)
    policy = await authority.policy(owner_id)
    if policy.mode != 'act_within_grants' or not policy.chosen_by_user:
        return False
    # The public grants() API deliberately omits expires_at/revoked_at. It is
    # suitable for UI labels, NOT for deciding whether to consume a pending
    # source into the durable pilot. Match the authority service's live grant
    # semantics before switching away from the legacy interpreter.
    rows = await db[GRANTS].find(
        {'owner_id': owner_id, 'capability': 'calendar.local.write', 'active': True},
        {'_id': 0},
    ).to_list(20)
    current = _now()
    for row in rows:
        try:
            grant = AutonomyGrant.model_validate(row)
        except Exception:
            continue
        if not grant.active or grant.granted_by != 'user' or grant.revoked_at:
            continue
        # MongoDB stores UTC dates and its default Python decoder returns
        # naive UTC datetimes. Use precisely the authority matcher's convention:
        # a missing expiry is not enough to enter this finite-permission pilot.
        expires = grant.expires_at
        if not expires:
            continue
        expiry_utc = expires if expires.tzinfo else expires.replace(tzinfo=timezone.utc)
        if expiry_utc <= current:
            continue
        if 'create' in grant.effect_scope:
            return True
    return False


def _event_version(node):
    return _digest({key: node.get(key) for key in
                    ('id', 'user_id', 'type', 'status', 'label', 'description', 'attributes', 'updated_at')})


_NO_EFFECT_UNSTABLE_GUARDS = frozenset({
    # A source-driven no-op is only terminal when the model reached it cleanly.
    # These guards prove the same turn first tried to narrate an unsupported
    # write/action. Retrying later is safer than silently treating that unstable
    # reasoning as a reviewed source. This is effect-agnostic infrastructure:
    # no subject, merchant or life category is inspected here.
    'CALENDAR_PERSIST_NUDGE',
    'CALENDAR_CLAIM_BLOCKED_TERMINAL',
    'READY_ACT_NO_EFFECT_NUDGE',
    'READY_ACT_NO_EFFECT_BLOCKED',
})


def _no_effect_result_is_stable(result) -> bool:
    trace = getattr(result, 'trace', None) or {}
    events = {str(step.get('event') or '') for step in trace.get('steps', [])}
    return not bool(events & _NO_EFFECT_UNSTABLE_GUARDS)


def _home_summary(node, operation):
    """One factual formatter shared by Home and subsequent receipt delivery."""
    attrs = node['attributes']
    moment = datetime.fromisoformat(attrs['starts_at'].replace('Z', '+00:00'))
    if moment.tzinfo is None:
        raise ValueError('result_event_timezone_missing')
    moment = moment.astimezone(ZoneInfo(attrs.get('timezone') or 'Europe/Rome'))
    verbs = {'created': 'Ho aggiunto', 'already_created': 'È già presente',
             'updated': 'Ho aggiornato', 'already_updated': 'È già aggiornato'}
    verb = verbs.get(operation)
    if verb is None:
        raise ValueError('unsupported_verified_operation')
    return (f'{verb} nel calendario ORA «{node["label"][:95]}»: '
            f'{moment:%d/%m/%Y} alle {moment:%H:%M}.')


def _due_query(owner_id):
    stamp = _now().isoformat()
    return {'owner_id': owner_id, 'status': 'pending',
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
            ]}


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
            payload = result.payload or {}
            # Keep only bounded operational evidence needed for reconciliation.
            # Never persist source text, tool arguments or model prose here.
            await self.change({
                '_core_work.effect.state': 'unverified',
                '_core_work.effect.last_status': str(result.status or '')[:40],
                '_core_work.effect.failure_kind': str(
                    payload.get('failure_kind') or payload.get('status') or ''
                )[:80],
                '_core_work.effect.operation': str(payload.get('operation') or '')[:40],
            })
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
            # Content validity and ownership are distinct. A late worker losing
            # its lease must NOT hide a valid Home row already delivered by the
            # new owner of that lease.
            signal, _ = await resolve_source(self.db, self.owner, self.ref)
            if (signal.fingerprint != self.row['fingerprint']
                    or signal.observed_at != self.row['observed_at']
                    or signal.origin == 'self_originated'):
                raise ValueError('source_revision_changed')
            node = await get_manual_event(self.db, self.owner, ref.removeprefix('calendar:'))
            if not node or node.get('status') != 'active' or _event_version(node) != effect['event_version']:
                raise ValueError('effect_has_changed')
            await self.current()
            return node

        try:
            node = await still_current()
            summary = _home_summary(node, effect['observation']['payload'].get('operation'))
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
                '_core_work.delivery_review': {'phase': 'pending', 'due_at': _now().isoformat(), 'attempts': 0},
                '_core_work.lease_until': _now().isoformat()})
            return {'state': 'completed', 'home_visible': True, 'activity_id': activity_id,
                    'notifications_sent': False}
        except LeaseLost:
            return {'state': 'lease_lost', 'home_visible': False, 'notifications_sent': False}
        except ValueError:
            # Do not leave an actually stale source/event result visible.
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
                # Original effect authority remains in the wrapped handler.
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
        token = uuid.uuid4().hex
        # Keep Mongo's _id in this internal snapshot. It never leaves the work
        # object, and find-and-modify implementations need it to locate the
        # updated row independently of the now-changed eligibility predicate.
        row = await self.db[COLLECTION].find_one_and_update(
            {**_due_query(owner_id), 'id': signal_id},
            {'$set': {'_core_work.phase': 'running', '_core_work.token': token,
                      '_core_work.lease_until': (_now() + timedelta(seconds=LEASE_SECONDS)).isoformat()},
             '$inc': {'_core_work.attempts': 1}}, return_document=True)
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
            if not _no_effect_result_is_stable(result):
                # The source was read and no durable effect occurred, but the
                # reasoning path was internally inconsistent about performing
                # one. Do not settle the source or surface that draft. Existing
                # durable retry/backoff will give the SAME Core another bounded
                # attempt; verified effects above never come through this path.
                raise RuntimeError('source_no_effect_not_stable')
            phase = 'needs_input' if result.mode == 'clarify' else 'reviewed_no_effect'
            await work.change({'status': 'interpreted', 'outcome': 'source_core_' + phase,
                'interpreted_at': _now().isoformat(), '_core_work.phase': phase,
                '_core_work.lease_until': _now().isoformat()})
            return {'state': phase, 'home_visible': False, 'notifications_sent': False}
        except LeaseLost:
            return {'state': 'lease_lost', 'home_visible': False, 'notifications_sent': False}
        except Exception as exc:
            try:
                row = await work.current()
                effect = (row.get('_core_work') or {}).get('effect') or {}
                exhausted = row['_core_work']['attempts'] >= MAX_ATTEMPTS
                phase = ('handoff_failed' if exhausted and effect.get('state') == 'verified' else
                         'result_ready' if effect.get('state') == 'verified' else
                         'reconciliation_required' if effect else 'failed' if exhausted else 'retry')
                await work.change({'_core_work.phase': phase,
                    '_core_work.last_error_kind': type(exc).__name__,
                    '_core_work.lease_until': _now().isoformat(),
                    '_core_work.next_run_at': (_now() + timedelta(seconds=30)).isoformat()})
                return {'state': phase, 'home_visible': False, 'notifications_sent': False}
            except LeaseLost:
                return {'state': 'lease_lost', 'home_visible': False, 'notifications_sent': False}

    async def process_pending(self, owner_id, *, limit=2):
        bound = min(max(limit, 1), 6)
        # Deterministic acknowledgement of the app's own echoes, not a model
        # decision about an external source's relevance.
        own = await self.db[COLLECTION].find({
            'owner_id': owner_id, 'status': 'pending', 'origin': 'self_originated',
            '_supersession_pending': {'$ne': True}}, {'_id': 0, 'id': 1}).to_list(bound)
        from connected.signals import SignalService
        for row in own:
            await SignalService(self.db).settle(owner_id, row['id'], outcome='own_work_confirmed')
        query = _due_query(owner_id)
        # A self-enrolled canary must never replay earlier mail as a new
        # autonomous task. Existing infrastructure-managed pilots retain
        # their original scope and regression behavior.
        if not enabled_for(owner_id):
            enrollment = await pilot_enrollment(self.db, owner_id)
            if not enrollment:
                return {'ok': True, 'looked_at': 0, 'noise': 0, 'passed_on': 0,
                        'source_core_results': []}
            query['observed_at'] = {'$gte': enrollment['since']}
        rows = await self.db[COLLECTION].find(query, {'_id': 0, 'id': 1}).sort(
            'observed_at', 1).to_list(bound)
        results = [await self.process_one(owner_id, row['id']) for row in rows]
        return {'ok': True, 'looked_at': len(results), 'noise': 0,
                'passed_on': sum(r['state'] == 'completed' for r in results),
                'source_core_results': results}
