"""Keep a sourced answer distinct from an executable follow-up promise.

Cognition selects relevance. This gate checks owner-scoped work and current-turn
source evidence. A failed schedule must not erase a successful personal read.
"""
from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class FollowupDisposition(BaseModel):
    disposition: Literal['continue', 'unrelated', 'declined', 'blocked', 'status_only']
    situation_id: Optional[str] = Field(default=None, max_length=80)
    reason: str = Field(min_length=1, max_length=300)
    user_words: Optional[str] = Field(default=None, max_length=300)
    evidence_refs: list[str] = Field(default_factory=list, max_length=8)


FOLLOWUP_CONTRACT = """
## Current-turn follow-up responsibility (execution contract)
If current_facts.situation_followup_contract is present, it lists owner-verified
active Situations with an existing attention purpose but no confirmed next check.
These are candidates, NOT orders to act on every Situation. Decide semantically
whether THIS user message continues a delegated task or asks for facts about it.

ANSWERING WHAT IS KNOWN AND ACCEPTING FUTURE WORK ARE DIFFERENT RESULTS.
A factual status question must first receive its evidence-backed answer. Do not
replace a known date or source statement with a report about scheduler internals.
A status-only answer neither cancels nor repairs existing delegated work. Do not
create/update a Situation just to answer a factual question or trigger a guard.
Preserve the identity and outstanding work of any existing Situation.

For relevant delegated work: read the necessary context/live evidence and schedule
a justified NEXT CHECK using schedule_situation_check. You choose process, source
and checkpoint; the person need not choose an arbitrary clock time. Distinguish
an approximate outcome from the next check. A past provider summary is not current
evidence. Never promise future work without a persisted executable job.

For a final reply while a check remains unconfirmed, include:
"situation_followup": {"disposition": "continue|unrelated|declined|blocked|status_only",
"situation_id": "exact candidate id, or null for unrelated/status_only",
"reason": "short reason", "user_words": "exact restriction, only for declined",
"evidence_refs": ["exact current-turn source references, required for status_only"]}.
- continue: this request delegates or repairs a follow-up. Perform the next tool,
  context or research step. Do not offer a process menu instead of doing the work.
- status_only: this request asks what a source says NOW, not to start or repair a
  monitor. Cite the exact factual_readback.ref returned by a successful read this
  turn. Answer the question, attribute the source, preserve uncertainty, and make
  NO promise of future checking or alerts. Missing monitoring must not erase facts.
  This disposition does not satisfy a request to monitor, remind or repair work.
- unrelated: this message is about a different matter, or the attention purpose is
  not real delegated work. Answer normally; no new work.
- declined: the person EXPLICITLY restricts action/repair. Quote the restriction
  exactly in user_words. A question about your prior intention is NOT a refusal.
- blocked: name a real blocker: essential personal information with structured
  uncertainty marked required/blocking/ask, a provider/permission error observed
  this turn, or disabled/unverifiable runtime state. An arbitrary reminder time
  or routine process choice is not missing personal information.

Only the selected source establishes its claims. A user-authored note or test
message is NOT confirmation from a merchant, courier or other third party.
Tools still enforce consent, ownership and authority. This contract authorizes
no external write. Reuse scheduled work without moving its deadline.
"""


def verified_readbacks(observations) -> list[dict[str, str]]:
    """Only adapter-provided excerpts tied to a successful current-turn read.

    Model prose and source instructions cannot register evidence themselves.
    The adapter provides the envelope; the excerpt remains quoted source DATA.
    """
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for obs in reversed(list(observations or [])):
        if not isinstance(obs, dict) or obs.get('kind') != 'tool' or obs.get('status') != 'ok':
            continue
        payload = obs.get('payload') or {}
        if not isinstance(payload, dict):
            continue
        item = payload.get('factual_readback')
        if not isinstance(item, dict):
            continue
        ref = str(item.get('ref') or '').strip()
        text = str(item.get('text') or '').strip()
        if not ref or ref not in (obs.get('provenance') or []) or not text or ref in seen:
            continue
        seen.add(ref)
        out.append({'ref': ref, 'text': text[:1200],
                    'label': str(item.get('label') or 'Fonte consultata')[:260]})
        if len(out) == 3:
            break
    return out


class FollowupTurnGate:
    """One bounded recovery opportunity; no separate reasoning or scheduler."""

    def __init__(self, db, owner: str):
        self.db, self.owner = db, owner
        self.pending: list[dict[str, Any]] = []
        self.nudged = False
        self._readbacks: list[dict[str, str]] = []

    async def refresh(self, facts, focus=None, current=None) -> None:
        from situations.repository import SituationRepository
        from situations.followup import read_followup

        self.pending = []
        if self.db is None or not self.owner:
            return
        ids = []
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
                continue

    def instruction(self) -> str:
        return FOLLOWUP_CONTRACT if self.pending else ''

    def accepts_final(self, decision, user_message: str, observations) -> bool:
        # The caller supplies only this turn's observations. Never retain a
        # previous answer when this turn has no evidence of a successful read.
        self._readbacks = verified_readbacks(observations)
        if not self.pending:
            return True
        handling = getattr(decision, 'situation_followup', None)
        if handling is None:
            return False
        if handling.disposition == 'unrelated':
            return True
        if handling.disposition == 'status_only':
            refs = set(handling.evidence_refs or [])
            available = {item['ref'] for item in self._readbacks}
            return bool(
                getattr(decision, 'response_mode', '') in ('answer', 'finish')
                and refs and refs <= available
            )
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
                'available_answer_refs': [item['ref'] for item in self._readbacks],
                'reason': (
                    'First answer the actual question using current-turn source evidence. '
                    'A factual status query can use status_only with exact factual_readback refs, '
                    'without claiming that future work is active. Do not erase a successful read '
                    'because scheduling failed. For delegated follow-up work, read needed evidence '
                    'and execute the next useful step. For unrelated work, an explicit restriction '
                    'or a real blocker, return the corresponding structured disposition. '
                    'Never schedule other candidates merely because they exist.'
                ),
            },
        }

    def failure_text(self) -> str:
        if self._readbacks:
            item = self._readbacks[0]
            return (
                f"{item['label']}:\n«{item['text']}»\n\n"
                'Questo è quanto riporta la fonte consultata. '
                'Non risulta ancora attivo un controllo automatico per la situazione.'
            )
        return (
            'Non risulta confermato un controllo automatico per la situazione. '
            'Non sono riuscita a completarne la valutazione operativa in questo turno: '
            'non ti dirò che è sotto controllo senza un lavoro effettivamente registrato.'
        )
