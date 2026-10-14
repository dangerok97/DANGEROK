"""Bounded durable admission of verified source results to original Delivery.

No second scheduler, no source interpretation, no automatic grant creation.
The completed work owns the pending-review marker, so a crash after Home cannot
lose it or force another calendar action. Channel choice stays with Delivery.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
import uuid

from delivery.source_results import current_subject, enabled_owners, now, plan_id

ATTEMPTS = 3
LEASE_SECONDS = 120
REVIEW_SECONDS = 60


async def drain(db, *, limit=2):
    owners = sorted(enabled_owners())
    if not owners:
        return 0
    handled, seen = 0, set()
    for _ in range(min(max(limit, 1), 6)):
        stamp = now()
        path = '_core_work.delivery_review'
        query = {
            'owner_id': {'$in': owners}, 'status': 'interpreted',
            'outcome': 'source_core_effect_verified', '_core_work.phase': 'completed',
            path + '.phase': {'$in': ['pending', 'retry']},
            path + '.due_at': {'$lte': stamp.isoformat()},
            '$and': [
                {'$or': [{path + '.lease_until': {'$exists': False}},
                         {path + '.lease_until': {'$lte': stamp.isoformat()}}]},
                {'$or': [{path + '.attempts': {'$exists': False}},
                         {path + '.attempts': {'$lt': ATTEMPTS}}]},
            ],
        }
        token = uuid.uuid4().hex
        change = {'$set': {path + '.token': token,
            path + '.lease_until': (stamp + timedelta(seconds=LEASE_SECONDS)).isoformat()},
            '$inc': {path + '.attempts': 1}}
        # One owner with many results should not consume every slot.
        fair = {**query, 'owner_id': {'$in': [owner for owner in owners if owner not in seen]}}
        row = await db.connected_signals.find_one_and_update(
            fair, change, sort=[(path + '.due_at', 1), ('id', 1)], return_document=True)
        if row is None and seen:
            row = await db.connected_signals.find_one_and_update(
                query, change, sort=[(path + '.due_at', 1), ('id', 1)], return_document=True)
        if row is None:
            break
        owner, activity_id = row['owner_id'], row['_core_work']['home_activity_id']
        seen.add(owner)
        state, outcome, error_kind = 'settled', '', ''
        try:
            from delivery.service import DeliveryService
            service = DeliveryService(db)
            subject = await current_subject(db, owner, activity_id)
            if subject is None:
                await service.cancel_for_source(owner, activity_id, source_type='source_result',
                                                reason='il risultato non è più attuale')
                outcome = 'source_changed'
            else:
                result = await asyncio.wait_for(service.evaluate_subject(
                    owner, subject, app_state='unknown'), REVIEW_SECONDS)
                if result.unavailable:
                    raise RuntimeError(result.blocked_by or 'delivery_judgement_unavailable')
                saved = await service.repo.get_plan(owner, plan_id(owner, activity_id))
                # These names describe records, NOT a claim that a phone was reached.
                outcome = ('provider_accepted' if saved and saved.status == 'delivered' else
                           'plan_' + saved.status if saved else result.mode)
        except Exception as exc:
            error_kind = type(exc).__name__
            state = 'retry' if row['_core_work']['delivery_review']['attempts'] < ATTEMPTS else 'paused'
            outcome = 'unavailable'
        next_due = (now() + timedelta(minutes=2)).isoformat() if state == 'retry' else None
        fence = {'id': row['id'], 'owner_id': owner, 'fingerprint': row['fingerprint'],
                 '_core_work.home_activity_id': activity_id, path + '.token': token}
        await db.connected_signals.update_one(fence, {'$set': {
            path + '.phase': state, path + '.due_at': next_due,
            path + '.outcome': outcome, path + '.error_kind': error_kind,
            path + '.finished_at': now().isoformat(),
        }, '$unset': {path + '.lease_until': '', path + '.token': ''}})
        handled += 1
    return handled
