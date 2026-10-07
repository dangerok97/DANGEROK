"""Read-only Situation cards: a registered check is not a user update.

Reuse the existing visibility decision and its owned execution/evidence refs.
Do not schedule work, infer physical outcomes, call a model or alter user data.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from agent.models import AgentEvidence
from agent.evidence import REAL_SOURCES

VISIBLE = ('quiet_update', 'inform_user', 'requires_attention', 'ask_user')
PROBLEMS = {
    'unavailable': 'Non riesco a verificare lo stato del controllo.',
    'not_scheduled': 'Non risulta un controllo programmato.',
    'recovery_pending': 'Il controllo programmato deve essere recuperato.',
    'runtime_disabled': 'I controlli automatici sono disattivati.',
}


async def _published_update(db, owner: str, goal_id: str) -> dict | None:
    """No headline is promoted merely because the goal was AI-initiated."""
    now = datetime.now(timezone.utc)
    rows = await db.agent_updates.find(
        {'owner_id': owner, 'goal_id': goal_id, 'outcome': {'$in': list(VISIBLE)},
         'at': {'$gte': (now - timedelta(hours=24)).isoformat(), '$lte': now.isoformat()}},
        {'_id': 0},
    ).sort('at', -1).to_list(6)
    for row in rows:
        if not str(row.get('headline') or '').strip():
            continue
        refs = [x for x in row.get('refs', []) if isinstance(x, str)][:8]
        if not refs:
            continue
        evidence = await db.agent_evidence.find(
            {'owner_id': owner, 'goal_id': goal_id, 'id': {'$in': refs},
             'superseded': {'$ne': True}},
            {'_id': 0, 'expires_at': 0},
        ).to_list(8)
        for item in evidence:
            try:
                if AgentEvidence.model_validate(item).provenance.source_class in REAL_SOURCES:
                    return row
            except (ValueError, TypeError):
                continue
        stamps = [ref[len('journal:'):] for ref in refs if ref.startswith('journal:')]
        done = await db.agent_journal.find_one(
            {'owner_id': owner, 'goal_id': goal_id, 'at': {'$in': stamps},
             'kind': 'step_done', 'detail.really_happened': True,
             'detail.status': 'succeeded', 'detail.came_from': {'$in': list(REAL_SOURCES)}}, {'_id': 0, 'at': 1},
        ) if stamps else None
        if done:
            return row
    return None


async def project_situation_card(db, owner: str, goal, card: dict[str, Any]) -> dict[str, Any]:
    """Same projection for Home and direct detail; only Home filters visibility."""
    if goal.source_kind != 'situation_followup':
        return card
    out = {**card, 'source_kind': 'situation_followup', 'show_in_updates': False,
           'what': 'Situazione temporanea', 'source': 'Situazione originale non disponibile',
           'detected': '', 'why_now': '', 'already_done': '', 'unknown': '',
           'next_step': '', 'progress_kind': 'pending'}
    refs = [ref for ref in goal.source_refs if str(ref).startswith('situation:')]
    if len(refs) != 1:
        return {**out, 'state': 'Non riesco a identificare la situazione originale.'}
    sid = refs[0].split(':', 1)[1]
    try:
        from situations.repository import SituationRepository
        from situations.followup import read_followup
        situation = await SituationRepository(db).get(owner, sid)
        if situation is None:
            return {**out, 'state': 'La situazione originale non è disponibile.'}
        out['what'] = (situation.semantic_kind or situation.summary)[:120]
        out['icon_key'] = situation.icon_key or 'other'
        user_source = 'user_conversation' in situation.source_refs or any(
            event.source == 'user_conversation' for event in situation.history
        )
        out['source'] = 'Una tua conversazione' if user_source else 'La situazione che ORA sta seguendo'
        if situation.status == 'cancelled' or goal.status == 'cancelled':
            return {**out, 'state': 'Controllo annullato.', 'progress_kind': 'stopped'}
        followup = await read_followup(db, owner, sid)
        status = followup.get('status', 'unavailable')
        if goal.is_open:
            out['state'] = {
                'scheduled': 'Controllo programmato.',
                'due': 'Il controllo è in attesa di esecuzione.',
                'running': 'Controllo in corso.',
                'waiting_for_user': card.get('needs_you') or 'Mi serve una tua risposta per continuare.',
                'stopped': 'Controllo terminato.',
                **PROBLEMS,
            }.get(status, PROBLEMS['unavailable'])
            out['progress_kind'] = 'running' if status == 'running' else 'scheduled' if status == 'scheduled' else 'pending'
            # Only a read-back wake, not goal.next_run_at alone, permits this sentence.
            label = followup.get('next_check_label')
            if label and status in ('scheduled', 'due'):
                out['next_step'] = f'Prossimo controllo: {label}.'
            if card.get('needs_you') or status == 'waiting_for_user':
                return {**out, 'show_in_updates': True, 'progress_kind': 'needs_input',
                        'next_step': card.get('needs_you') or out['state']}
            if status in PROBLEMS:
                return {**out, 'show_in_updates': True, 'progress_kind': 'problem'}
            # A missed deadline is not silently hidden along with future checks.
            if status == 'due' and followup.get('next_check_at'):
                due = datetime.fromisoformat(str(followup['next_check_at']).replace('Z', '+00:00'))
                if due.tzinfo and datetime.now(timezone.utc) - due > timedelta(minutes=5):
                    return {**out, 'show_in_updates': True, 'progress_kind': 'problem',
                            'state': 'Il controllo previsto è in ritardo; non risulta ancora eseguito.'}
        else:
            out['state'] = 'Monitoraggio terminato.'
            out['progress_kind'] = 'stopped'
        published = await _published_update(db, owner, goal.id)
        if published:
            return {**out, 'show_in_updates': True, 'progress_kind': 'update',
                    'state': str(published['headline'])[:200],
                    'outcome': str(published['headline'])[:200], 'update_at': published.get('at')}
        return out
    except Exception:
        # A failed status read must remain visible, never masquerade as silence.
        return {**out, 'show_in_updates': True, 'progress_kind': 'problem',
                'state': PROBLEMS['unavailable']}
