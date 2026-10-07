"""A reply cannot silently abandon an existing follow-up responsibility.

The model selects relevance and the next capability. This module only checks
owner-scoped state and whether a final reply has accounted for unfinished work.
It does not classify user prose, choose a domain, query providers, or schedule.
"""
from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class FollowupDisposition(BaseModel):
    disposition: Literal['continue', 'unrelated', 'declined', 'blocked']
    situation_id: Optional[str] = Field(default=None, max_length=80)
    reason: str = Field(min_length=1, max_length=300)
    user_words: Optional[str] = Field(default=None, max_length=300)


FOLLOWUP_CONTRACT = """
## Current-turn follow-up responsibility (execution contract)
If current_facts.situation_followup_contract is present, it lists owner-verified
active Situations with an existing attention purpose but no confirmed next check.
These are candidates, NOT orders to act on every Situation. Decide semantically
whether THIS user message continues one of them. A status query about a delegated
follow-up continues that responsibility; situation_update.operation=none does
not mean the delegated work is finished. Do not create/update a Situation merely
to trigger a guard or schedule. Preserve its identity.

If relevant: first be honest about the old missing schedule; then use the existing
context/live read capabilities needed to assess what matters now and schedule the
justified NEXT CHECK using schedule_situation_check. You choose process, source
and checkpoint; the person need not choose an arbitrary clock time. Distinguish
an approximate outcome from the next check. A past weather or provider summary
is not current evidence. Do not return a menu asking whether to read conditions
or choose a reminder time. That is still unfinished work, even in response_mode
answer. Do not promise work outside this turn without a persisted executable job.

For a final reply while one of these checks remains unconfirmed, include:
"situation_followup": {"disposition": "continue|unrelated|declined|blocked",
"situation_id": "exact candidate id or null only for unrelated",
"reason": "short operational reason", "user_words": "exact restriction, only for declined"}.
- continue: the current request is about this responsibility. Do the next necessary
  tool/context/research step; a final answer is not completion of that work.
- unrelated: the message is about a different matter, or the candidate's recorded
  attention purpose is not a real delegated follow-up. Answer normally; no new work.
- declined: the person EXPLICITLY restricts action/repair in this turn. Quote their
  restriction exactly in user_words. A question about your prior intention is NOT
  a restriction or refusal. Do not invent one, schedule, or postpone a check.
- blocked: name an actual blocker: an essential personal fact with structured
  uncertainty.missing_information marked required/blocking/ask, a provider or
  permission error observed this turn, or disabled/unverifiable runtime state.
  Missing routine read permission or an arbitrary preferred reminder time is NOT
  a missing personal fact. Respect actual denied consent; never grant it yourself.

Tools still enforce consent, identity and authority. This contract authorizes no
external write. Existing scheduled work is reused without moving its deadline.
"""


class FollowupTurnGate:
    """One bounded recovery opportunity per turn; no independent reasoning loop."""

    def __init__(self, db, owner: str):
        self.db, self.owner = db, owner
        self.pending: list[dict[str, Any]] = []
        self.nudged = False

    async def refresh(self, facts, focus=None, current=None) -> None:
        from situations.repository import SituationRepository
        from situations.followup import read_followup

        self.pending = []
        if self.db is None or not self.owner:
            return
        ids = []
        # Current mutation and prior thread focus take precedence over Stage A.
        for value in (current, focus):
            if isinstance(value, dict) and value.get('id'):
                ids.append(str(value['id']))
        for fact in facts or []:
            ref = getattr(fact, 'ref', '') or (fact.get('ref', '') if isinstance(fact, dict) else '')
            source = getattr(fact, 'source', '') or (fact.get('source', '') if isinstance(fact, dict) else '')
            if source == 'situation' and ref.startswith('situation:'):
                ids.append(ref.split(':', 1)[1])
        for sid in list(dict.fromkeys(ids))[:4]:
            try:
                item = await SituationRepository(self.db).get(self.owner, sid)
                if item is None or item.status not in ('active', 'changed'):
                    continue
                # An explicit structured attention purpose is an unfinished
                # responsibility, not evidence of an already scheduled job.
                purpose = item.attention_intent or item.next_check_summary
                if not purpose:
                    continue
                state = await read_followup(self.db, self.owner, sid)
                if state['status'] in ('scheduled', 'due', 'running', 'stopped'):
                    continue
                self.pending.append({
                    'situation_id': sid, 'expected_revision': item.revision,
                    'summary': item.summary[:300], 'attention_intent': str(purpose)[:300],
                    'follow_up': state,
                })
            except Exception:
                # Do not infer an actionable responsibility from an unreadable
                # or unowned record. Other runtime guards report tool failures.
                continue

    def instruction(self) -> str:
        return FOLLOWUP_CONTRACT if self.pending else ''

    def accepts_final(self, decision, user_message: str, observations) -> bool:
        if not self.pending:
            return True
        handling = getattr(decision, 'situation_followup', None)
        if handling is None:
            return False
        if handling.disposition == 'unrelated':
            return True  # semantic judgement stays with cognition
        candidate = next((x for x in self.pending if x['situation_id'] == handling.situation_id), None)
        if candidate is None:
            return False
        if handling.disposition == 'declined':
            quote = (handling.user_words or '').strip()
            return bool(quote and quote in user_message)
        if handling.disposition != 'blocked':
            return False
        state = candidate['follow_up']
        if state.get('runtime_enabled') is False or state['status'] in ('unavailable', 'waiting_for_user', 'runtime_disabled'):
            return True
        uncertainty = getattr(decision, 'uncertainty', None)
        if uncertainty and any(
            x.necessity == 'required' and x.blocking and x.strategy == 'ask'
            for x in uncertainty.missing_information
        ):
            return True
        # Only actual observations from THIS turn can support a provider block.
        return any(
            x.get('kind') in ('tool', 'error') and
            x.get('status') in ('error', 'failed', 'unavailable', 'denied', 'blocked')
            for x in observations if isinstance(x, dict)
        )

    def observation(self) -> dict:
        self.nudged = True
        first = self.pending[0]
        return {
            'kind': 'system', 'name': 'situation_followup_required', 'status': 'nudge',
            'payload': {
                'situation_id': first['situation_id'],
                'expected_revision': first['expected_revision'],
                'candidates': self.pending,
                'reason': (
                    'Your draft leaves an existing follow-up unaccounted for. '
                    'Choose relevance semantically. For the responsibility continued by this '
                    'message, read needed evidence and execute the next useful step; do not '
                    'ask the person to choose whether you should check or what clock time to use. '
                    'For unrelated work, an explicit restriction, or a genuine blocker, return '
                    'the structured situation_followup disposition. No other candidate may be '
                    'scheduled just because it exists. A schedule claim needs persisted read-back.'
                ),
            },
        }

    @staticmethod
    def failure_text() -> str:
        return (
            'Non risulta confermato un controllo automatico per la situazione. '
            'Non sono riuscita a completarne la valutazione operativa in questo turno: '
            'non ti dirò che è sotto controllo senza un lavoro effettivamente registrato.'
        )
