"""One-use integration for the isolated CAL164 branch; never run on an app service."""
from pathlib import Path
import ast
import hashlib

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    'backend/home/manual_event.py': 'ec947ef57f40f19246803f095b170e4d955ba211',
    'backend/conversation_engine/ai_core/tools/calendar_caps.py': '9f1296c6bb6fb4c2a2a52ee2f5d7d75fd937be4a',
    'backend/conversation_engine/ai_core/loop.py': '5359eff4de07ef9d5a0c5b6b590d3e0f36eafe6f',
}


def once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Unsafe or moved source anchor: ' + old[:90])
    return text.replace(old, new, 1)


def apply():
    sources = {}
    for path, sha in EXPECTED.items():
        raw = (ROOT / path).read_bytes()
        found = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if found != sha:
            raise RuntimeError('Source changed: ' + path)
        sources[path] = raw.decode()

    path = 'backend/home/manual_event.py'
    source = sources[path]
    start = source.index('async def update_manual_event(')
    end = source.index('\n\nasync def archive_manual_event', start)
    fn = source[start:end]
    a = fn.index('    attrs = dict(node["attributes"])\n')
    b = fn.index('    if expected_updated_at and', a)
    preparation = fn[a:b]
    helper = ('def _manual_update_target(node, fields):\n' + preparation
              + '    return title, description, attrs\n\n\n'
              + 'def manual_update_is_noop(node, fields):\n'
              + '    """Compare the requested canonical state with a fresh owned record."""\n'
              + '    if not node or node.get("status") != "active":\n'
              + '        return False\n'
              + '    title, description, attrs = _manual_update_target(node, fields)\n'
              + '    return (title == node["label"] and description == (node.get("description") or "")\n'
              + '            and attrs == node["attributes"])\n\n\n')
    old_check = '''    if expected_updated_at and expected_updated_at != node.get("updated_at"):
        if title == node["label"] and description == (node.get("description") or "") and attrs == node["attributes"]:
            return manual_event_public(node)  # Retry after a lost success response.
        raise ValueError("event_changed")
'''
    new_check = '''    # A retry is not a new change. Do not rewrite the revision or wake the
    # autonomous worker when all material fields are already as requested.
    # This also preserves recovery after a lost success response.
    if title == node["label"] and description == (node.get("description") or "") and attrs == node["attributes"]:
        return {**manual_event_public(node), "changed_now": False}
    if expected_updated_at and expected_updated_at != node.get("updated_at"):
        raise ValueError("event_changed")
'''
    fn = once(fn, preparation, '    title, description, attrs = _manual_update_target(node, fields)\n')
    fn = once(fn, old_check, new_check)
    fn = once(fn, '    return manual_event_public(observed)', '    return {**manual_event_public(observed), "changed_now": True}')
    sources[path] = source[:start] + helper + fn + source[end:]

    path = 'backend/conversation_engine/ai_core/tools/calendar_caps.py'
    source = sources[path]
    start = source.index('async def update_calendar_event(')
    end = source.index('\nasync def continue_calendar_action(', start)
    fn = source[start:end]
    anchor = '''    if not act.may_execute:
        return _authority_required("update_calendar_event", act)

    taken = await commanded.begin(db, act)
'''
    addition = '''    if not act.may_execute:
        return _authority_required("update_calendar_event", act)

    if local_node:
        # Ownership and the ordinary authority gate have already been checked.
        # Read again after those awaits; only the observed exact target state
        # can justify saying no further write is necessary.
        from home.manual_event import manual_update_is_noop, manual_event_public
        fresh = await get_manual_event(db, uid, draft_id)
        try:
            no_change = manual_update_is_noop(fresh, fields)
        except (ValueError, KeyError) as exc:
            return _fail("update_calendar_event", str(exc).upper())
        if no_change:
            seen = manual_event_public(fresh)
            return Observation(
                kind="tool", name="update_calendar_event", status="ok",
                payload={"status": "ok", "operation": "already_updated", "verified": True,
                         "changed_now": False, "calendar_ref": _ref(draft_id),
                         "source": "ora_local", "updated_on_google": False,
                         "title": seen["title"], "start_datetime": seen["starts_at"],
                         "end_datetime": seen["ends_at"], "timezone": seen["timezone"],
                         "location": seen["location"], "description": seen["description"],
                         "reason": "L'evento è già nello stato richiesto: non ho eseguito una nuova modifica."},
                provenance=[_ref(draft_id)],
            )

    taken = await commanded.begin(db, act)
'''
    fn = once(fn, anchor, addition)
    fn = once(fn, 'payload={"status": "ok", "operation": "updated", "verified": True,',
              'payload={"status": "ok", "operation": "updated" if updated.get("changed_now", True) else "already_updated", "verified": True,\n                     "changed_now": updated.get("changed_now", True),')
    sources[path] = source[:start] + fn + source[end:]

    path = 'backend/conversation_engine/ai_core/loop.py'
    source = sources[path]
    source = once(source, '            if effective_calendar_cap:\n',
                  '            if effective_calendar_cap and (obs.payload or {}).get("changed_now") is not False:\n')
    anchor = '            state_mod.append_turn(st, role="ora", text=ora, kind=mode)\n'
    addition = '''            if mode in ("answer", "finish"):
                from conversation_engine.ai_core.grounding.calendar_weekday import guard_calendar_weekdays
                ora, calendar_date_fixes = guard_calendar_weekdays(
                    ora, observations[turn_start:], calendar_ahead,
                )
                if calendar_date_fixes:
                    add_step(trace, event="CALENDAR_WEEKDAY_CORRECTED", count=calendar_date_fixes)
            state_mod.append_turn(st, role="ora", text=ora, kind=mode)
'''
    sources[path] = once(source, anchor, addition)
    for path, source in sources.items():
        ast.parse(source, filename=path)
    for path, source in sources.items():
        (ROOT / path).write_text(source)
    print('CAL164 applied three SHA-verified source changes; no provider/account configuration touched.')


if __name__ == '__main__':
    apply()
