from pathlib import Path


def replace(path, old, new):
    p = Path(path)
    source = p.read_text()
    assert source.count(old) == 1, (path, old[:80], source.count(old))
    p.write_text(source.replace(old, new))


replace('backend/conversation_engine/ai_core/models.py',
    'from situations.models import SituationUpdate\n',
    'from situations.models import SituationUpdate\nfrom situations.turn_followup import FollowupDisposition\n')
replace('backend/conversation_engine/ai_core/models.py',
    '    situation_update: Optional[SituationUpdate] = None\n',
    '    situation_update: Optional[SituationUpdate] = None\n    situation_followup: Optional[FollowupDisposition] = None\n')
path = 'backend/conversation_engine/ai_core/loop.py'
replace(path, '    situation_followup_nudge_used = False\n', '')
replace(path,
    '    clock_context = await user_clock_context(db, sess.user_id)\n\n    for step in range(max(1, max_steps)):',
    '''    clock_context = await user_clock_context(db, sess.user_id)

    from situations.turn_followup import FollowupTurnGate
    followup_gate = FollowupTurnGate(db, sess.user_id)
    if (sess.meta or {}).get("entry_point") != "phone":
        await followup_gate.refresh(context_facts, st.get("active_situation_ref"))

    for step in range(max(1, max_steps)):''')
replace(path, '                **(st.get("current_facts") or {}),\n',
    '''                **(st.get("current_facts") or {}),
                **({"situation_followup_contract": followup_gate.pending}
                   if followup_gate.pending else {}),
''')
replace(path, '            system=COGNITIVE_SYSTEM_PROMPT,\n',
    '            system=COGNITIVE_SYSTEM_PROMPT + followup_gate.instruction(),\n')
replace(path,
    '                system=COGNITIVE_SYSTEM_PROMPT\n                + "\\nPrevious output was invalid. Return valid JSON only.",',
    '                system=COGNITIVE_SYSTEM_PROMPT + followup_gate.instruction()\n                + "\\nPrevious output was invalid. Return valid JSON only.",')
old = '''                if (mode in ("answer", "finish") and persisted.get("attention_intent")
                    and followup["status"] in ("not_scheduled", "recovery_pending")
                    and not situation_followup_nudge_used and step + 1 < max_steps):
                    situation_followup_nudge_used = True
                    observations.append(Observation(kind="system", name="situation_followup_required", status="nudge", payload={
                        "situation_id": persisted["id"], "expected_revision": persisted.get("revision"),
                        "follow_up": followup,
                        "reason": "The Situation was saved but no executable checkpoint is confirmed. You chose an attention_intent. Read needed live evidence and call schedule_situation_check with your own justified checkpoint and notification condition before promising monitoring. Do not ask the user to pick a time or authorize required read-only checks. If required information/provider access is missing, explain that concrete blocker. A time window in prose is not a scheduler entry."
                    }).model_dump())
                    add_step(trace, event="SITUATION_FOLLOWUP_NUDGE")
                    continue
'''
new = '''            if mode in ("answer", "ask", "finish") and not phone_owns_turn:
                await followup_gate.refresh(context_facts, st.get("active_situation_ref"), persisted)
                if not followup_gate.accepts_final(decision, user_message, observations[turn_start:]):
                    if not followup_gate.nudged and step + 1 < max_steps:
                        observations.append(followup_gate.observation())
                        add_step(trace, event="SITUATION_FOLLOWUP_NUDGE")
                        continue
                    # A second process menu is a failed turn, not autonomy.
                    # Keep the failure visible without inventing a job or
                    # sending a canned question back to the person.
                    decision = CognitiveDecision(response_mode="answer", message_to_user=followup_gate.failure_text())
                    mode = "answer"
                    add_step(trace, event="SITUATION_FOLLOWUP_UNRESOLVED")
'''
replace(path, old, new)
replace('backend/conversation_engine/ai_core/governance.py',
    '            situation_update=situation_update,\n',
    '            situation_update=situation_update,\n            situation_followup=data.get("situation_followup"),\n')
replace('backend/conversation_engine/ai_core/prompt.py', '  "situation_update": {\n',
    '''  "situation_followup": {
    "disposition": "continue|unrelated|declined|blocked",
    "situation_id": "exact current follow-up candidate id, or null for unrelated",
    "reason": "short operational reason",
    "user_words": "exact user restriction for declined only, otherwise null"
  } or null,
  "situation_update": {
''')
