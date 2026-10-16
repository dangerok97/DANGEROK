"""Adapter for verified work, not a classifier for emails or life situations.

The original DeliveryService decides timing/channels and uses its original
provider, consent, rate limits, recheck and WhatsApp admission. This adapter
binds those decisions to an immutable completed result and serializes its send.
No model assertion alone can manufacture a delivered result.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import os
import re
import uuid

from pymongo.errors import DuplicateKeyError
from agent.memory_fence import MemorySourcesUnavailable
from delivery.models import DeliveryPlan, DeliverySubject, PushCopy

SOURCE_KIND = 'source_result'
_OPAQUE = re.compile(r'^[A-Za-z0-9_-]{4,80}$')
_STOP_SEND = ('started', 'unknown', 'accepted')
_CLOSED = ('delivered', 'cancelled', 'expired')


def now():
    return datetime.now(timezone.utc)


def enabled_owners():
    from connected.core_work import enabled_for
    values = {s.strip() for s in os.environ.get('ORA_SOURCE_RESULT_DELIVERY_OWNERS', '').split(',') if s.strip()}
    if '*' in values:
        return set()
    return {s for s in values if enabled_for(s)}


async def owner_enabled(db, owner_id):
    # Existing infrastructure-enrolled owners retain their exact old rules.
    if owner_id in enabled_owners():
        return True
    from connected.core_work import pilot_enrollment, ready_for_owner
    return bool(await pilot_enrollment(db, owner_id) and
                await ready_for_owner(db, owner_id))


async def enabled_owners_in(db):
    owners = set(enabled_owners())
    # The self-enrollment pilot is deliberately one server-managed email
    # digest, not a "*" wildcard and not a permission the model can grant.
    digest = os.environ.get('ORA_SOURCE_SINGLE_PILOT_EMAIL_SHA256', '').strip().lower()
    if len(digest) == 64:
        rows = await db.source_pilot_enrollments.find(
            {'active': True, 'created_by': 'authenticated_user',
             'email_digest': digest}, {'_id': 0, 'owner_id': 1}).to_list(5)
        for row in rows:
            owner = str(row.get('owner_id') or '')
            if owner and await owner_enabled(db, owner):
                owners.add(owner)
    return owners


def plan_id(owner_id, activity_id):
    raw = (owner_id + '\0' + activity_id).encode()
    return 'dlv_sres_' + hashlib.sha256(raw).hexdigest()[:32]


def moment(raw):
    value = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('source_result_missing_timezone')
    return value


async def current_subject(db, owner_id, activity_id):
    """Canonical re-read at decision, scheduled delivery and transport boundary.

    A caller's summary, fake success, stale receipt or another account's id is
    never a delivery source. Database unavailability is not evidence of absence.
    """
    if not isinstance(activity_id, str) or not _OPAQUE.fullmatch(activity_id):
        return None
    if not await owner_enabled(db, owner_id):
        return None
    try:
        return await _load(db, owner_id, activity_id)
    except (ValueError, KeyError, TypeError):
        return None  # Malformed or provably stale receipt, no usable source.
    except Exception as exc:
        raise MemorySourcesUnavailable('source_result_check_unavailable') from exc


async def _load(db, owner_id, activity_id):
    from connected.core_work import _event_version, _home_summary
    from connected.source_read import resolve_source
    from home.manual_event import get_manual_event
    row = await db.connected_signals.find_one({
        'owner_id': owner_id, 'status': 'interpreted',
        'outcome': 'source_core_effect_verified', '_supersession_pending': {'$ne': True},
        '_core_work.phase': 'completed', '_core_work.home_activity_id': activity_id,
    }, {'_id': 0})
    if row is None:
        return None
    signal, _ = await resolve_source(db, owner_id, 'signal:' + row['id'])
    if signal.origin == 'self_originated' or signal.fingerprint != row['fingerprint']:
        return None
    # A later version can exist while an earlier, completed signal keeps its
    # historical state. Historical completion is not permission to notify late.
    newer = await db.connected_signals.find_one({
        'owner_id': owner_id, 'source_id': row['source_id'], 'source_type': row['source_type'],
        'source_object_ref': row['source_object_ref'], 'observed_at': {'$gt': row['observed_at']},
    }, {'_id': 1})
    if newer:
        return None
    effect = row['_core_work']['effect']
    obs = effect['observation']
    payload = obs['payload']
    ref = payload.get('calendar_ref')
    if (effect.get('state') != 'verified' or payload.get('verified') is not True
            or not isinstance(ref, str) or not ref.startswith('calendar:')
            or ref not in obs.get('provenance', []) or payload.get('provider') != 'ora'):
        return None
    event = await get_manual_event(db, owner_id, ref.removeprefix('calendar:'))
    if not event or event.get('status') != 'active' or _event_version(event) != effect['event_version']:
        return None
    activity = await db.ambient_activity.find_one({
        'owner_id': owner_id, 'id': activity_id, 'visibility': 'ambient',
    }, {'_id': 0})
    if not activity or activity.get('summary') != _home_summary(event, payload.get('operation'))[:200]:
        return None
    provenance = activity.get('cognitive_provenance') or {}
    if (provenance.get('source_core') is not True or provenance.get('verified') is not True
            or provenance.get('event_version') != effect['event_version']
            or provenance.get('source_fingerprint') != row['fingerprint']
            or not {'signal:' + row['id'], ref} <= set(activity.get('source_refs') or [])):
        return None
    deadline = min(moment(activity['occurred_at']) + timedelta(hours=24),
                   moment(event['attributes']['starts_at']))
    if deadline <= now():
        return None
    summary = str(activity['summary'])[:200]
    return DeliverySubject(source_type=SOURCE_KIND, id=activity_id, owner_id=owner_id,
        semantic_summary=summary, work_already_done=[summary],
        why_it_matters='Un impegno personale è stato registrato o aggiornato e verificato nel calendario ORA.',
        why_now='Il risultato è già disponibile nella Home; la persona non deve autorizzare nuovamente la stessa azione.',
        created_at=activity['occurred_at'], valid_until=deadline.isoformat(),
        requires_response=False, requires_clarification=False, sensitivity_hint='personal',
        source_refs=['signal:' + row['id'], ref])


async def existing_plan(db, owner_id, subject_id):
    row = await db.delivery_plans.find_one({
        'id': plan_id(owner_id, subject_id), 'owner_id': owner_id,
        'source_type': SOURCE_KIND, 'source_id': subject_id,
    }, {'_id': 0})
    return row


def settled_or_inflight(row):
    return bool(row and (row.get('status') in _CLOSED
        or (row.get('_source_dispatch') or {}).get('state') in _STOP_SEND))


async def save_decision(service, subject, decision, *, held_reason=''):
    """One immutable result has one plan, including across writer races.

    A new model judgement cannot overwrite a provider acceptance or the marker
    of a send whose outcome is unknown. No random plan id can bypass that fence.
    """
    existing = await existing_plan(service.db, subject.owner_id, subject.id)
    if settled_or_inflight(existing):
        return DeliveryPlan.model_validate(existing)
    pid = plan_id(subject.owner_id, subject.id)
    sensitivity = 'private' if decision.sensitivity == 'private' else 'personal'
    plan = DeliveryPlan(id=pid, owner_id=subject.owner_id, source_type=SOURCE_KIND,
        source_id=subject.id, mode='push', status='held' if held_reason else 'pending',
        not_before=decision.not_before,
        not_after=min(moment(value) for value in (decision.not_after, subject.valid_until) if value).isoformat(),
        words=PushCopy(title='Calendario ORA aggiornato', body=subject.semantic_summary[:200],
            public_title='Calendario ORA aggiornato',
            public_body='Un aggiornamento verificato è disponibile nel tuo calendario ORA.'),
        reason_to_interrupt=decision.reason_to_interrupt, reason_to_open=subject.semantic_summary,
        what_decided_the_mode=decision.what_decided_the_mode, sensitivity=sensitivity,
        deep_link='/', decision_provenance='code_safety' if held_reason else 'model',
        rationale=held_reason or decision.reason_to_interrupt[:300])
    if existing:
        plan.created_at = existing['created_at']
        plan.transport_retry_attempts = existing.get('transport_retry_attempts', 0)
        plan.transport_retry_due = existing.get('transport_retry_due')
        plan.transport_retry_alarm_queued = existing.get('transport_retry_alarm_queued', False)
        if plan.transport_retry_due and moment(plan.transport_retry_due) > now():
            plan.not_before = max(moment(plan.not_before or now().isoformat()), moment(plan.transport_retry_due)).isoformat()
            plan.status = 'held'
    query = {'_id': pid, 'owner_id': subject.owner_id,
             'status': {'$nin': list(_CLOSED)},
             '_source_dispatch.state': {'$nin': list(_STOP_SEND)}}
    try:
        await service.db.delivery_plans.update_one(query, {'$set': plan.model_dump()}, upsert=True)
    except DuplicateKeyError:
        # A concurrent send/settlement wins. Never replace it with a fresh plan.
        pass
    saved = await existing_plan(service.db, subject.owner_id, subject.id)
    if saved is None:
        raise RuntimeError('source_result_plan_not_persisted')
    return DeliveryPlan.model_validate(saved)


async def send_guarded(service, owner_id, plan):
    """Serialize the original sender for a single verified result.

    Unknown acceptance is durable and never automatically resent. An explicit
    zero-acceptance response may use the EXISTING bounded transport retry path.
    This does not promise exactly-once delivery beyond the provider boundary.
    """
    if (plan.owner_id != owner_id or plan.id != plan_id(owner_id, plan.source_id)
            or not service._due(plan) or service._expired(plan)):
        return
    subject = await current_subject(service.db, owner_id, plan.source_id)
    if subject is None:
        await service._cancel(plan, 'il risultato non è più attuale', 'code_cancel')
        return
    token = uuid.uuid4().hex
    claimed = await service.db.delivery_plans.find_one_and_update({
        'id': plan.id, 'owner_id': owner_id, 'source_type': SOURCE_KIND,
        'source_id': plan.source_id, 'status': {'$in': ['pending', 'held']},
        '_source_dispatch.state': {'$nin': list(_STOP_SEND)},
    }, {'$set': {'_source_dispatch': {
        'state': 'started', 'token': token, 'started_at': now().isoformat(),
    }}}, return_document=True)
    if claimed is None:
        return
    live = DeliveryPlan.model_validate(claimed)
    fence = {'id': live.id, 'owner_id': owner_id, '_source_dispatch.token': token}
    state, error_kind, provider = 'unknown', '', ''
    try:
        # Check notification consent and fatigue at the last boundary, not
        # solely before an AI decision which may have taken time.
        from delivery import context
        permission = await context._permission(service.db, owner_id, now())
        recent = await context._recent_interruptions(service.db, owner_id, now())
        muted = await service._muted(owner_id, live.source_id)
        allowed, reason = await service._may_push(owner_id, {
            'can_be_notified': permission, 'recent_interruptions': recent,
            'they_muted_this_concern': muted})
        if not allowed:
            live.status = 'held'
            live.rationale = reason
            live.decision_provenance = 'code_safety'
            await service.repo.save_plan(live)
            state = 'not_sent'
        else:
            # The original sender revalidates the source again, admits WhatsApp
            # through its own opt-in/template checks, and uses the usual provider.
            outcome = await service._send_current(owner_id, live)
            provider = str((outcome or {}).get('provider') or '')[:32]
            if live.status == 'delivered':
                state = 'accepted'
            elif live.status in ('cancelled', 'expired'):
                state = 'not_sent'
            elif (outcome or {}).get('safe_to_retry') is True or (outcome or {}).get('reason') == 'no_endpoint':
                state = 'rejected'
    except Exception as exc:
        error_kind = type(exc).__name__
        # Includes a lost write acknowledgment after provider acceptance.
        # Preserve uncertainty; another worker must not repeat the send.
        saved = await service.repo.get_plan(owner_id, live.id)
        if saved and saved.status == 'delivered':
            state = 'accepted'
        else:
            await service.db.delivery_plans.update_one(fence, {'$set': {
                'status': 'held', 'rationale': 'Esito del recapito non verificabile; nessun reinvio automatico.'}})
    finally:
        await service.db.delivery_plans.update_one(fence, {'$set': {
            '_source_dispatch.state': state, '_source_dispatch.finished_at': now().isoformat(),
            '_source_dispatch.error_kind': error_kind, '_source_dispatch.provider': provider,
            '_source_dispatch.device_delivery_verified': False,
        }})
        current = await service.repo.get_plan(owner_id, live.id)
        if current:
            plan.status, plan.outcome = current.status, current.outcome
            plan.delivered_at = current.delivered_at
