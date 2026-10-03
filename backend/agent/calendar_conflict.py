"""A source-backed preparation for two overlapping ORA commitments.

An LLM review cannot certify its own speculative rescheduling options. This
small case can be prepared from the current calendar rows and exact interval
arithmetic, with every proposed new appointment explicitly unconfirmed.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from home.manual_event import get_manual_event, manual_event_public


def is_home_calendar_pair(goal):
    refs = list(dict.fromkeys(goal.source_refs))
    return (goal.source_kind == "opportunity" and bool(goal.opportunity_id)
            and len(refs) == 2 and all(r.startswith("calendar:node_home_") for r in refs))


async def active_home_pair(db, owner_id, refs):
    refs = list(dict.fromkeys(refs))
    if len(refs) != 2 or not all(r.startswith("calendar:node_home_") for r in refs):
        return None
    events = []
    for ref in refs:
        node = await get_manual_event(db, owner_id, ref.removeprefix("calendar:"))
        if not node or node.get("status") != "active":
            return None
        row = manual_event_public(node)
        try:
            start = datetime.fromisoformat(row["starts_at"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(row["ends_at"].replace("Z", "+00:00"))
            zone = ZoneInfo(row["timezone"])
        except (KeyError, TypeError, ValueError):
            return None
        if start.tzinfo is None or end.tzinfo is None or end <= start or end <= datetime.now(timezone.utc):
            return None
        events.append((start, end, zone, row, ref))
    events.sort(key=lambda item: item[0])
    first, second = events
    overlap_start = max(first[0], second[0])
    overlap_end = min(first[1], second[1])
    if overlap_end <= overlap_start:
        return None
    minutes = round((overlap_end - overlap_start).total_seconds() / 60)
    if not minutes:
        return None
    return events, overlap_start, overlap_end, minutes


async def overlap_draft(db, owner_id, goal, evidence):
    refs = list(dict.fromkeys(goal.source_refs))
    if not is_home_calendar_pair(goal):
        return None
    pair = await active_home_pair(db, owner_id, refs)
    if pair is None:
        return None
    events, overlap_start, overlap_end, minutes = pair
    first, second = events
    # The goal must actually have read these sources. A goal merely citing two
    # event IDs is insufficient to mark a prepared deliverable as supported.
    ids = []
    for ref in refs:
        found = next((e.id for e in evidence if e.supports == ref or ref in e.provenance.source_refs), None)
        if not found:
            return None
        ids.append(found)
    date = first[0].astimezone(first[2]).strftime("%d/%m/%Y")
    def period(item):
        start, end, zone, *_ = item
        return f"{start.astimezone(zone):%H:%M}–{end.astimezone(zone):%H:%M}"
    content = (
        f"Il {date} risultano due impegni ORA sovrapposti per {minutes} minuti "
        f"({overlap_start.astimezone(first[2]):%H:%M}–{overlap_end.astimezone(first[2]):%H:%M}):\n"
        f"• {first[3]['title']}: {period(first)}.\n"
        f"• {second[3]['title']}: {period(second)}.\n\n"
        "Prima scelta da verificare: chiedere di spostare il secondo impegno. "
        "Non risulta confermata alcuna disponibilità alternativa; vanno considerati "
        "anche i tempi di spostamento e i requisiti annotati nei due eventi.\n\n"
        "Bozza da inviare al referente del secondo impegno, dopo aver scelto il destinatario:\n"
        f"Oggetto: Richiesta di spostamento dell'appuntamento del {date}\n\n"
        f"Buongiorno, ho un appuntamento fissato per il {date} alle {second[0].astimezone(second[2]):%H:%M}. "
        "Ho un altro impegno sovrapposto e vorrei sapere se possiamo concordare un orario diverso. "
        "Mi può indicare le disponibilità? Le confermerò dopo aver verificato i tempi "
        "necessari e quanto devo portare. Grazie.\n\n"
        "Nessun impegno è stato modificato e nessun messaggio è stato inviato."
    )
    return content, list(dict.fromkeys(ids))

async def resolution_step_from_answer(db, owner_id, goal, reply, *, language="it"):
    """Build the next safe step from a person's choice about an overlap.

    Returns (step, reason). The step is either another knowledge question or
    one exact local-calendar modification. It never executes anything.
    """
    pair = await active_home_pair(db, owner_id, goal.source_refs)
    if pair is None:
        return None, "calendar_changed"
    events, _overlap_start, _overlap_end, _minutes = pair
    from agent.reasoning import interpret_calendar_conflict_choice
    from agent.models import ActionStep

    presented = [
        {
            "ref": item[4],
            "title": item[3]["title"],
            "starts_at": item[3]["starts_at"],
            "ends_at": item[3]["ends_at"],
            "timezone": item[3]["timezone"],
        }
        for item in events
    ]
    choice = await interpret_calendar_conflict_choice(
        reply, events=presented, language=language
    )
    if choice is None:
        return None, "choice_unavailable"

    target_ref = str(choice.get("target_ref") or "")
    target = next((item for item in events if item[4] == target_ref), None)
    if target is None:
        return ActionStep(
            intent="Capire quale dei due impegni va spostato",
            step_type="ask_user",
            asks=(
                "Non ho capito quale dei due vuoi spostare. Dimmi il titolo "
                "oppure «il primo» / «il secondo»."
            ),
            ask_kind="knowledge",
        ), ""

    requested_time = str(choice.get("requested_time") or "")
    title = target[3]["title"]
    if not requested_time:
        return ActionStep(
            intent=f"Conoscere il nuovo orario per {title}",
            step_type="ask_user",
            asks=f"A che ora vuoi spostare «{title}»?",
            ask_kind="knowledge",
        ), ""

    requested_date = str(choice.get("requested_date") or "")
    local_day = target[0].astimezone(target[2]).date().isoformat()
    day = requested_date or local_day
    duration = max(5, round((target[1] - target[0]).total_seconds() / 60))
    try:
        from home.manual_event import home_event_times, get_manual_event
        new_start_raw, new_end_raw = home_event_times(
            day, requested_time, target[2].key, duration_minutes=duration
        )
        new_start = datetime.fromisoformat(new_start_raw)
        new_end = datetime.fromisoformat(new_end_raw)
    except (ValueError, TypeError):
        return ActionStep(
            intent=f"Chiarire il nuovo orario per {title}",
            step_type="ask_user",
            asks=(
                f"L'orario indicato per «{title}» non è utilizzabile. "
                "Scrivimi un orario come 12:00."
            ),
            ask_kind="knowledge",
        ), ""

    if new_start.astimezone(timezone.utc) <= datetime.now(timezone.utc):
        return ActionStep(
            intent=f"Chiarire un orario futuro per {title}",
            step_type="ask_user",
            asks=f"L'orario indicato per «{title}» è già passato. A che ora futura vuoi spostarlo?",
            ask_kind="knowledge",
        ), ""

    other = next(item for item in events if item[4] != target_ref)
    if min(new_end, other[1]) > max(new_start, other[0]):
        return ActionStep(
            intent=f"Evitare una nuova sovrapposizione per {title}",
            step_type="ask_user",
            asks=(
                f"Alle {requested_time} «{title}» si sovrapporrebbe ancora "
                f"a «{other[3]['title']}». Indicami un altro orario."
            ),
            ask_kind="knowledge",
        ), ""

    node = await get_manual_event(
        db, owner_id, target_ref.removeprefix("calendar:")
    )
    if not node or node.get("status") != "active":
        return None, "calendar_changed"

    proposal = {
        "target_ref": target_ref,
        "title": title,
        "day": day,
        "requested_time": requested_time,
        "start_datetime": new_start_raw,
        "end_datetime": new_end_raw,
        "timezone": target[2].key,
        "expected_revision": str(node.get("updated_at") or ""),
    }
    return ActionStep(
        intent=f"Verificare se «{title}» può essere spostato direttamente",
        step_type="ask_user",
        asks=(
            f"«{title}» è un impegno solo tuo, che posso spostare nel tuo "
            "calendario, oppure il nuovo orario deve essere confermato da "
            "un'altra persona o struttura?"
        ),
        ask_kind="knowledge",
        parameters={**proposal, "conflict_followup": "coordination"},
    ), ""



async def resolution_step_from_coordination_answer(
    db, owner_id, goal, prior_step, reply, *, language="it"
):
    """Continue a prepared conflict only after real-world ownership is clear."""
    from agent.models import ActionStep
    from agent.reasoning import interpret_calendar_coordination

    params = dict(prior_step.parameters or {})
    target_ref = str(params.get("target_ref") or "")
    if params.get("conflict_followup") != "coordination" or not target_ref:
        return None, "not_coordination"

    pair = await active_home_pair(db, owner_id, goal.source_refs)
    if pair is None:
        return None, "calendar_changed"
    node = await get_manual_event(db, owner_id, target_ref.removeprefix("calendar:"))
    if not node or node.get("status") != "active":
        return None, "calendar_changed"
    if str(node.get("updated_at") or "") != str(params.get("expected_revision") or ""):
        return None, "calendar_changed"

    answer = await interpret_calendar_coordination(reply, language=language)
    if answer is None:
        return None, "choice_unavailable"
    mode = answer.get("mode")

    if mode == "unclear":
        return ActionStep(
            intent="Chiarire chi deve confermare lo spostamento",
            step_type="ask_user",
            asks=(
                "Per evitare di dirti che un appuntamento è spostato quando "
                "ho cambiato solo il calendario: questo nuovo orario dipende "
                "solo da te oppure deve accettarlo qualcun altro?"
            ),
            ask_kind="knowledge",
            parameters={**params, "conflict_followup": "coordination"},
        ), ""

    if mode == "needs_confirmation":
        return ActionStep(
            intent="Ottenere la conferma reale del nuovo orario",
            step_type="ask_user",
            asks=(
                f"Non sposto ancora «{params.get('title') or 'l’impegno'}»: "
                "serve una conferma esterna. Dimmi chi deve confermare e, se "
                "vuoi che me ne occupi io, il canale o recapito verificabile "
                "da usare."
            ),
            ask_kind="knowledge",
            parameters={
                **params,
                "conflict_followup": "external_confirmation",
                "requires_external_confirmation": True,
            },
        ), ""

    return ActionStep(
        intent=(
            f"Spostare «{params.get('title') or 'l’impegno'}» al "
            f"{params.get('day')} alle {params.get('requested_time')}"
        ),
        step_type="execute",
        capability_needed="calendar.local.write",
        input_refs=[target_ref],
        expected_result=(
            f"«{params.get('title') or 'L’impegno'}» risulta nel calendario ORA "
            f"al {params.get('day')} alle {params.get('requested_time')} e la "
            "modifica è stata riletta."
        ),
        external_effect=True,
        effect_type="modify",
        effect_target="il tuo calendario ORA",
        reaches_somebody_else=False,
        parameters={
            "start_datetime": params.get("start_datetime"),
            "end_datetime": params.get("end_datetime"),
            "timezone": params.get("timezone"),
            "expected_revision": params.get("expected_revision"),
        },
        reversibility="easily",
    ), ""
