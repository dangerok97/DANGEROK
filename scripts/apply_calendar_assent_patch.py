"""One-time SHA-fenced integration on the dedicated repair branch only."""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[1]
BASES = {
    'backend/agent/commanded.py': '6c13016ed3993fea5a9fdbfa08ff43260d8b7325',
    'backend/home/calendar_event.py': '47bbfb340f556bdf0777fafa833c3af8074edd1c',
    'backend/conversation_engine/ai_core/tools/calendar_caps.py': 'd80224cf55e6f91118154ebb1830d69b96e20bbb',
    'backend/conversation_engine/ai_core/loop.py': '2b500a02546a537513f0750b794b2423ce038351',
}
texts = {}
for name, expected in BASES.items():
    b = (ROOT / name).read_bytes()
    assert hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest() == expected, name
    texts[name] = b.decode()


def change(name, before, after):
    assert texts[name].count(before) == 1, (name, 'anchor_not_unique', before[:100])
    texts[name] = texts[name].replace(before, after)


name = 'backend/agent/commanded.py'
change(name, '    expected: str = "", answered_proposal: bool = False,\n',
             '    expected: str = "", answered_proposal: bool = False, confirmation=None,\n')
change(name, '''    if answered_proposal and reads_as_an_approval(command.spoken):
        await authority.consent(
            owner_id, intent, decision="approved",
            shown=(command.asked_for or summary)[:300],
        )
''', '''    from agent.calendar_assent import CalendarCancellationConfirmation
    bound_reply = (
        type(confirmation) is CalendarCancellationConfirmation
        and confirmation.permits(owner_id, intent, command.spoken)
    )
    if answered_proposal and (reads_as_an_approval(command.spoken) or bound_reply):
        consent = await authority.consent(
            owner_id, intent, decision="approved",
            shown=(command.asked_for or summary)[:300],
        )
        if bound_reply:
            # Keep the real utterance, never replace it with a synthetic yes.
            await db.autonomy_consents.update_one(
                {"id": consent.id, "owner_id": owner_id},
                {"$set": {"confirmation_evidence": confirmation.audit()}},
            )
''')
name = 'backend/home/calendar_event.py'
change(name, '    command=None, answered_proposal: bool = True,\n',
             '    command=None, answered_proposal: bool = True, confirmation=None,\n')
change(name, '''    # --- chi lo ha chiesto, e per cosa esattamente -----------------------
    effect = commanded.calendar_effect({"title": title, "delete": True})
''', '''    if confirmation is not None:
        from agent.calendar_assent import CalendarCancellationConfirmation
        latest = await event_detail(db, user_id, item_id)
        if (type(confirmation) is not CalendarCancellationConfirmation or not latest
                or not row.get("ora_manual")
                or not confirmation.matches_readback(user_id, "calendar:" + str(row["id"]), latest)):
            return {"ok": False, "reason": "event_changed", "title": title}

    # --- chi lo ha chiesto, e per cosa esattamente -----------------------
    effect = commanded.calendar_effect({"title": title, "delete": True})
''')
change(name, '        answered_proposal=answered_proposal,\n',
             '        answered_proposal=answered_proposal, confirmation=confirmation,\n')
name = 'backend/conversation_engine/ai_core/tools/calendar_caps.py'
change(name, '''    if not reads_as_an_approval(str(runtime.get("user_message") or "")):
''', '''    from agent.calendar_assent import cancellation_confirmation
    if (not reads_as_an_approval(str(runtime.get("user_message") or ""))
            and cancellation_confirmation(runtime) is None):
''')
change(name, '''    out = await delete_event(
        db, uid, handle, confirmed_title=detail["title"],
        command=_user_command(arguments, runtime), answered_proposal=_answered_a_proposal(runtime),
    )
''', '''    from agent.calendar_assent import cancellation_confirmation
    confirmation = cancellation_confirmation(runtime)
    if confirmation is not None and not confirmation.matches_readback(uid, _ref(ref), snapshot):
        return _fail("cancel_calendar_event", "event_changed", "La proposta non corrisponde più all'evento.")
    out = await delete_event(
        db, uid, handle, confirmed_title=detail["title"],
        command=_user_command(arguments, runtime), answered_proposal=_answered_a_proposal(runtime),
        confirmation=confirmation,
    )
''')
change(name, '''                         "confirmation_request": {"question": question, "arguments": {
''', '''                         "confirmation_request": {"owner_id": uid, "question": question, "arguments": {
''')
name = 'backend/conversation_engine/ai_core/loop.py'
change(name, '''        gov = validate_decision(
            raw,
''', '''        # A capability has already asked for this specific authority. More
        # same-turn tool attempts cannot supply a new user reply. Narrow to
        # its factual question and use the ordinary durable pending-act exit.
        calendar_wait = pending_request(observations[turn_start:])
        if calendar_wait:
            raw = {
                "response_mode": "ask", "reasoning_status": "needs_user_input",
                "question": calendar_wait["question"],
                "situation_update": {"operation": "none"},
            }
            add_step(trace, event="CALENDAR_AUTHORITY_HANDOFF")

        gov = validate_decision(
            raw,
''')
for name, text in texts.items():
    compile(text, name, 'exec')
for name, text in texts.items():
    (ROOT / name).write_text(text, encoding='utf-8')
print('Integrated four SHA-verified runtime files; no other source changed.')
