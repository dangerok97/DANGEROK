from pathlib import Path
root = Path.cwd()
def replace(path, old, new):
    p=root/path; s=p.read_text(); assert s.count(old)==1, (path, s.count(old), old[:100]); p.write_text(s.replace(old,new))

(root/'backend/situations/clock.py').write_text('''"""Presentation-only projection of persisted instants. Never reschedule a job."""
from datetime import datetime
from zoneinfo import ZoneInfo

_MONTHS = ("gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic")


def local_check_fields(value, timezone_name):
    """Return a local display of an aware timestamp; invalid inputs remain unknown."""
    try:
        instant = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if instant.tzinfo is None:
            return {}
        local = instant.astimezone(ZoneInfo(timezone_name))
    except (ValueError, TypeError, KeyError):
        return {}
    return {
        "next_check_at_local": local.isoformat(),
        "next_check_time_local": local.strftime("%H:%M"),
        "next_check_label": f"{local.day} {_MONTHS[local.month - 1]} {local.year}, {local:%H:%M}",
    }
''')
replace('backend/situations/followup.py',
 'from situations.repository import SituationRepository\n',
 'from situations.repository import SituationRepository\nfrom situations.clock import local_check_fields\nfrom timezone_service import user_clock_context\n')
replace('backend/situations/followup.py',
 '    out = {"status": "unavailable", "next_check_at": None, "last_checked_at": None,',
 '    out = {"status": "unavailable", "situation_id": situation_id, "next_check_at": None, "last_checked_at": None,\n           "next_check_at_local": None, "next_check_time_local": None, "next_check_label": None,\n           "timezone": None, "timezone_authority": None,')
replace('backend/situations/followup.py',
 '        if situation is None:\n            return out\n        if situation.status not in ("active", "changed"):',
 '        if situation is None:\n            return out\n        clock = await user_clock_context(db, owner)\n        out.update(timezone=clock["timezone"], timezone_authority=clock["authority"])\n        if situation.status not in ("active", "changed"):')
replace('backend/situations/followup.py',
 '                "next_check_at": at.isoformat()}',
 '                "next_check_at": at.isoformat(),\n                **local_check_fields(at, clock["timezone"])}')
replace('backend/situations/followup.py',
 'Read the returned status before promising a check.',
 'Read the returned status before promising a check. For dialogue use next_check_label and timezone from the result, not the raw UTC hour or the proposed check_at. This operation does not measure any physical state.')

replace('backend/conversation_engine/ai_core/loop.py', 'import json\n', 'import json\nimport html\nimport unicodedata\n')
replace('backend/conversation_engine/ai_core/loop.py',
 '''    r"verific(?:a|are|her[oò]|heremo)?|checkpoint)\\b.{0,100}?"
    r"(?:alle?|per\\s+le|verso\\s+le)\\s*([01]?\\d|2[0-3])(?::([0-5]\\d))?\\b"''',
 '''    r"verific(?:a|are|her[oò]|heremo)?|checkpoint)\\b[^!?;]{0,160}?"
    r"(?:alle?|per\\s+le|verso\\s+le)\\s*(?:ore\\s*)?([01]?\\d|2[0-3])(?:\\s*[:.]\\s*([0-5]\\d))?\\b"''')
replace('backend/conversation_engine/ai_core/loop.py',
 '''def _latest_situation_schedule(observations) -> Optional[Dict[str, Any]]:
    for obs in reversed(list(observations or [])):
        if not isinstance(obs, dict):
            continue
        if obs.get("name") != "schedule_situation_check" or obs.get("status") != "ok":
            continue
        payload = obs.get("payload") or {}
        if isinstance(payload, dict) and payload.get("next_check_at"):
            return payload
    return None
''',
 '''def _latest_situation_schedule(observations) -> Optional[Dict[str, Any]]:
    # A successful read is as authoritative as an arrange operation. Do not use
    # an older successful schedule after a newer stopped/failed read, nor mix
    # two different Situations into one unconditional prose replacement.
    relevant = [obs for obs in (observations or []) if isinstance(obs, dict)
                and obs.get("name") in ("schedule_situation_check", "get_situation_followup")]
    identities = {str((obs.get("payload") or {}).get("situation_id")) for obs in relevant
                  if isinstance(obs.get("payload"), dict) and (obs.get("payload") or {}).get("situation_id")}
    if not relevant or len(identities) > 1:
        return None
    obs = relevant[-1]
    payload = obs.get("payload") or {}
    if (obs.get("status") == "ok" and isinstance(payload, dict)
            and payload.get("ok") is not False
            and payload.get("status") in ("scheduled", "due", "running")
            and payload.get("next_check_at")):
        return payload
    return None
''')
replace('backend/conversation_engine/ai_core/loop.py',
 '''def _claims_wrong_situation_check_time(text: str, actual_hhmm: Optional[str]) -> bool:
    if not actual_hhmm:
        return False
    for match in _SITUATION_CHECK_TIME_RE.finditer(str(text or "")):
        claimed = f"{int(match.group(1)):02d}:{int(match.group(2) or 0):02d}"
        if claimed != actual_hhmm:
            return True
    return False
''',
 '''def _claims_wrong_situation_check_time(text: str, actual_hhmm: Optional[str]) -> bool:
    if not actual_hhmm:
        return False
    # Compare rendered clock text, not its formatting. The v106 guard silently
    # missed "per le **15:00 di oggi**" and newline-separated clauses.
    rendered = unicodedata.normalize("NFKC", html.unescape(str(text or "")))
    rendered = re.sub(r"<[^>]*>", "", rendered)
    rendered = re.sub(r"[*_`]", "", rendered)
    rendered = " ".join(rendered.split())
    for match in _SITUATION_CHECK_TIME_RE.finditer(rendered):
        clause = match.group(0).lower()
        prefix = re.split(r"[.!?;]", rendered[:match.start()])[-1].lower()
        # Past executions and explicit denials are not promises of a future check.
        if re.search(r"\\b(?:precedente|ultimo|eseguito|effettuato)\\b", clause + " " + prefix):
            continue
        if re.search(r"\\bnon\\b", prefix):
            continue
        claimed = f"{int(match.group(1)):02d}:{int(match.group(2) or 0):02d}"
        if claimed != actual_hhmm:
            return True
    return False
''')
replace('backend/conversation_engine/ai_core/loop.py',
 '''    if include_check_time and actual_hhmm:
        parts.append(f"Il prossimo controllo è programmato alle {actual_hhmm}.")
    if completion:
        parts.append(f"Ti avviso quando {completion.lower()}.")
    if early:
        parts.append(f"Se prima {early.lower()}, ti avviso prima.")''',
 '''    if include_check_time and actual_hhmm:
        parts.append(f"Il prossimo controllo è programmato alle {actual_hhmm}.")
        if payload.get("next_check_label") and payload.get("timezone"):
            parts.append(f"Data e fuso: {payload['next_check_label']} ({payload['timezone']}).")
    if completion:
        parts.append(f"Ti avviso quando: {completion}.")
    if early:
        parts.append(f"Ti avviso prima se: {early}.")''')
replace('backend/conversation_engine/ai_core/loop.py',
 '''                    str((clock_context or {}).get("timezone") or "Europe/Rome"),''',
 '''                    str((scheduled_followup or {}).get("timezone")
                        or (clock_context or {}).get("timezone") or "Europe/Rome"),''')
replace('backend/conversation_engine/ai_core/loop.py',
 '''                            "local_check_time": persisted_check_hhmm,
                            "reason": (''',
 '''                            "local_check_time": persisted_check_hhmm,
                            "next_check_label": scheduled_followup.get("next_check_label"),
                            "timezone": scheduled_followup.get("timezone") or clock_context.get("timezone"),
                            "reason": (''')
replace('backend/conversation_engine/ai_core/loop.py',
 '''                                "and answer only with the user outcome and any earlier warning."''',
 '''                                "and answer only with the user outcome and any earlier warning. "
                                "Do not offer to perform the ordinary read-only work that ORA already "
                                "accepted. Do not imply direct observation of an unmeasured physical state."''')

replace('frontend/src/components/ora/presence/knowledge.ts',
 '    next_check_at?: string | null;\n',
 '    next_check_at?: string | null;\n    next_check_at_local?: string | null;\n    next_check_label?: string | null;\n    timezone?: string | null;\n    timezone_authority?: string | null;\n')
replace('frontend/src/components/ora/OraCockpitContext.tsx',
 'title="Prossimo controllo" body={timeLabel(followup.next_check_at)}',
 'title="Prossimo controllo" body={followup.next_check_label || timeLabel(followup.next_check_at)}')
replace('backend/conversation_engine/ai_core/prompt.py',
 '''checkpoint time. Never repeat the originally proposed check_at if the runtime persisted a different
time. Unless the person explicitly asks when ORA will check again, keep checkpoint timing internal.''',
 '''checkpoint time. Its next_check_at is an INSTANT (often serialized in UTC); next_check_label and
timezone are the local display for the person. Copy that local display instead of taking the hour
substring from the UTC timestamp. Never repeat the originally proposed check_at if the runtime
persisted a different time. Unless the person explicitly asks when ORA will check again, keep
checkpoint timing internal. Do not invent an exact occurrence time from the time of your reply:
Situation creation is a registration time, not proof of when the physical activity began.''')
replace('backend/conversation_engine/ai_core/prompt.py',
 '''reasonable to consider the outcome reached. On failure say what is missing.''',
 '''reasonable to consider the outcome reached. A provider forecast or elapsed time is not a sensor
measurement of the user's specific object. Never promise to detect physical irregularities without
an actual observation channel. Answer about the useful readiness/action moment, not unrelated
process anomalies. Do not offer the already-delegated read-only checks as an optional next task.
On failure say what is missing.''')
replace('frontend/e2e/mobile-conversation-v93.spec.ts',
    "next_check_at: '2026-10-08T14:30:00+02:00', last_checked_at: '2026-10-08T13:00:00+02:00',",
    "next_check_at: '2026-10-07T15:00:00Z', next_check_label: '7 ott 2026, 17:00', timezone: 'Europe/Rome', last_checked_at: '2026-10-08T13:00:00+02:00',")
replace('frontend/e2e/mobile-conversation-v93.spec.ts',
    "  await expect(card).toContainText('Ultimo controllo eseguito');",
    "  await expect(card).toContainText('Ultimo controllo eseguito');\n  // Backend local projection wins even when the browser's timezone differs.\n  await expect(card).toContainText('7 ott 2026, 17:00');\n  await expect(card).not.toContainText('7 ott 2026, 15:00');")
p = root/'frontend/src/components/ora/ora14.test.ts'
p.write_text(p.read_text() + "\n// v107: show the same server-projected local schedule as conversation readback.\n{\n  const rail = readCode('src/components/ora/OraCockpitContext.tsx');\n  assert.ok(rail.includes('followup.next_check_label || timeLabel(followup.next_check_at)'));\n}\n")
print('Applied reviewed v107 application changes')
