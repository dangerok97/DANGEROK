"""Opt-in live-model diagnostic, no DB/production users and no action execution.

Run explicitly: python -m scripts.autonomy_model_smoke
Uses only synthetic facts and installed LLM settings. This is a judgment/plan
gate, not proof of an end-to-end background run or market research quality.
No imports from deps/server, no Mongo, no scheduler, no capability execution.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone


def report(stage, **result):
    print("AUTONOMY_MODEL_SMOKE " + json.dumps({"stage": stage, **result}, ensure_ascii=False), flush=True)


async def run_case(*, incomplete=False):
    from opportunities.reasoning import scan
    from agent.reasoning import decide_goal, make_plan

    # An isolated fictional persona. These facts are never written to an account.
    snapshot = {
        "now": datetime.now(timezone.utc).isoformat(), "unavailable_sources": [],
        "documents": [{"ref": "document:synthetic-price-options",
            "title": "Condizioni del mio archivio digitale",
            "unverified_excerpt": "Piano attivo: 15 euro al mese, totale annuo 180 euro. "
                "Alternativa dello stesso servizio: 120 euro per dodici mesi, anticipati. "
                "Entrambi hanno 100 GB e identico supporto, imposte incluse, nessun costo iniziale. "
                "Il mensile si cancella ogni mese; l'annuale non rimborsa i mesi non usati. "
                "Il titolare ha già confermato di voler mantenere il servizio per dodici mesi. "
                "Nessuna autorizzazione a cambiare piano o spendere denaro.",
            "freshness": "unknown", "excerpt_truncated": False, "text_available": True}],
    }
    case = "requires_further_reading" if incomplete else "complete_price_facts"
    if incomplete:
        snapshot["documents"][0]["unverified_excerpt"] = (
            "Il piano attivo dell'archivio passa da 10 a 25 euro mensili dal prossimo rinnovo. "
            "È disponibile un'alternativa annuale pubblicizzata a 120 euro. "
            "Le spese di attivazione, i limiti del piano e il prezzo dal secondo anno "
            "sono specificati nelle pagine successive dello stesso documento. "
            "Il titolare mantiene il servizio per almeno dodici mesi. Nessun cambio autorizzato."
        )
        snapshot["documents"][0]["excerpt_truncated"] = True
    found = await scan(snapshot, already_raised=[])
    candidates = (found or {}).get("opportunities") or []
    grounded = [c for c in candidates if "document:synthetic-price-options" in (c.get("evidence_refs") or [])]
    report("discovery", case=case, available=found is not None, grounded_opportunities=len(grounded),
           reason=str((found or {}).get("reason_for_silence") or "")[:500])
    if not grounded:
        report("gate", case=case, passed=False, reason="no_grounded_opportunity")
        return
    opportunity = grounded[0]
    report("opportunity", case=case, what=opportunity.get("what"),
           proposed_work=opportunity.get("what_i_can_do"), initiative=opportunity.get("initiative"))
    admission = await decide_goal({"what": opportunity.get("what"),
        "why_it_matters": opportunity.get("why_it_matters"),
        "what_ora_offered_to_do": opportunity.get("what_i_can_do"),
        "how_far_ora_meant_to_go": opportunity.get("initiative"), "who_asked": "agent_initiated",
        "source_context": snapshot["documents"], "source_context_unavailable": False})
    report("admission", case=case, outcome=(admission or {}).get("outcome"), reason=str((admission or {}).get("reasoning") or "")[:500])
    if not admission or admission.get("outcome") != "create_goal":
        report("gate", case=case, passed=False, reason="no_autonomous_goal")
        return
    capabilities = [{"capability": name, "status": "available_real", "can_be_used_now": True,
                     "changes_something_in_the_world": False}
                    for name in ("document.read", "information.read", "comparison.run")]
    plan = await make_plan({**admission, "source_refs": ["document:synthetic-price-options"]},
        capabilities=capabilities, context={"now": snapshot["now"]})
    steps = (plan or {}).get("steps") or []
    reads = any(s.get("capability_needed") == "document.read" and
                s.get("input_refs") == ["document:synthetic-price-options"] for s in steps)
    asks_first = bool(steps and steps[0].get("step_type") == "ask_user")
    writes = any(s.get("step_type") == "execute" for s in steps)
    report("planning", case=case, steps=len(steps), reads_source=reads, asks_first=asks_first,
           proposes_external_execution=writes)
    report("gate", case=case, passed=bool(steps and reads and not asks_first),
           scope="live_discovery_admission_plan_only_no_execution")


async def run():
    await run_case()
    await run_case(incomplete=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    try:
        asyncio.run(asyncio.wait_for(run(), timeout=150))
    except Exception as exc:
        # Diagnostic failure must not interrupt an otherwise healthy deployment.
        # The explicit failed gate is the outcome; never print env/error contents.
        report("gate", passed=False, error_type=type(exc).__name__)
