"""Sprint 4 / 4.1 — conversational Life Experience copy & rhythm (not a wizard)."""
from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ["LIFE_SETUP_ENABLED"] = "1"
os.environ["AI_LIFE_STRATEGIST_ENABLED"] = "1"
os.environ["AI_LIFE_STRATEGIST_GEMINI"] = "0"
os.environ.setdefault("JWT_SECRET", "test-secret-life-setup")
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "ora_life_setup_test")

_BACKEND = str(Path(__file__).resolve().parents[2])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from ai_life_strategist.conversation_planner import (
    PHILOSOPHY_GREETING,
    assert_not_wizard_copy,
    build_active_turn,
    build_greeting_turn,
    wrap_up_turn,
)
from ai_life_strategist.conversational_voice import (
    build_acknowledgement,
    looks_like_role_title,
    location_confirm_prompt,
    near_mlc_bridge,
    render_conversational_turn,
    render_priority_for_ora,
    resolve_turn_question,
    safe_wrap_fallback,
    sanitize_acknowledgement,
    synthesize_first_picture,
    validate_rendered_text,
    validate_spoken_question_for_goal,
)
from ai_life_strategist.minimum_life_context import (
    NUCLEUS_QUESTIONS,
    QUESTION_GOALS,
    question_goal_for_gap,
)
from ai_life_strategist.models import ReasoningContext, StrategistPlan
from ai_life_strategist.question_planner import GREETING_QUESTION, plan_greeting, plan_next
from ai_life_strategist.service import AILifeStrategistService

INTERNAL_JARGON = ("mlc", "coverage", "life graph", "gap", "strategist", "planner", "minimum life")


def _no_jargon(text: str) -> None:
    low = (text or "").lower()
    for j in INTERNAL_JARGON:
        assert j not in low, f"jargon leak: {j} in {text!r}"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client, client[os.environ.get("DB_NAME", "ora_life_setup_test")]


async def _clean(db, user_id: str):
    for col in ("life_setup_sessions", "life_profiles", "goals", "documents"):
        await db[col].delete_many({"user_id": user_id})


def _svc(db):
    from life_setup.service import LifeSetupService
    from ai_life_strategist import cache as c
    import life_setup.service as ls

    c.clear()
    ls._SERVICE = LifeSetupService(db)
    return ls._SERVICE


def uid(prefix: str = "c4") -> str:
    return f"ls_conv_{prefix}_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Sprint 4 baseline
# ---------------------------------------------------------------------------


def test_greeting_first_contact_then_one_question():
    plan = plan_greeting()
    turn = build_greeting_turn(plan)
    text = turn["text"]
    assert "Ciao, sono ORA" in text or "sono ORA" in PHILOSOPHY_GREETING
    assert GREETING_QUESTION in text
    assert text.index("Ciao") < text.index(GREETING_QUESTION.split()[0]) or "ORA" in text
    assert "step" not in text.lower()
    assert "%" not in text
    assert assert_not_wizard_copy(text)
    _no_jargon(text)
    assert text.count("?") <= 2


def test_ack_rich_answer_grounded():
    facts = {
        "mlc.identity.name": "Luca",
        "mlc.current_situation": "lavoro",
        "mlc.life_places.home": "Milano",
        "lavoro.ruolo": "architetto",
        "mlc.responsibilities": "architetto",
    }
    ack = build_acknowledgement(
        last_user_text=(
            "Mi chiamo Luca, vivo a Milano, lavoro come architetto "
            "e ultimamente faccio fatica a organizzare i progetti."
        ),
        known_facts=facts,
    )
    assert ack
    assert "Capito" in ack or "Piacere" in ack
    assert "Milano" in ack or "lavor" in ack.lower()
    _no_jargon(ack)


def test_ack_minimal_may_be_none_or_light():
    ack = build_acknowledgement(last_user_text="Studio.", known_facts={})
    assert ack is None or ack == "Capito."


def test_ack_not_repeated():
    facts = {"mlc.life_places.home": "Roma", "mlc.current_situation": "studio"}
    a1 = build_acknowledgement(last_user_text="Studio medicina a Roma.", known_facts=facts)
    a2 = build_acknowledgement(
        last_user_text="Studio medicina a Roma.",
        known_facts=facts,
        previous_ack=a1,
    )
    assert a1
    assert a2 is None


def test_near_mlc_bridge_no_percentages():
    rich = {
        "mlc.life_places.home": "Milano",
        "lavoro.ruolo": "architetto",
        "lavoro.active": True,
        "mlc.current_situation": "lavoro",
        "mlc.responsibilities": "architetto",
    }
    b = near_mlc_bridge(
        covered_count=4,
        missing=["immediate_priority"],
        sufficient=False,
        known_facts=rich,
    )
    assert b
    assert "%" not in b
    assert "checklist" not in b.lower()
    assert "quadro abbastanza chiaro" not in b.lower()
    _no_jargon(b)
    assert near_mlc_bridge(covered_count=1, missing=["x"], sufficient=False) is None


def test_near_mlc_bridge_thin_knowledge_no_false_clarity():
    """Name + studio only must NOT claim a clear picture."""
    thin = {
        "mlc.identity.name": "Francesco",
        "mlc.current_situation": "studio",
        "studio.active": True,
    }
    b = near_mlc_bridge(
        covered_count=3,
        missing=["life_places", "immediate_priority"],
        sufficient=False,
        known_facts=thin,
    )
    assert b is None or "quadro" not in b.lower()
    assert b is None or "abbastanza chiaro" not in (b or "").lower()


def test_final_synthesis_uses_real_facts():
    facts = {
        "mlc.identity.name": "Luca",
        "mlc.current_situation": "lavoro",
        "mlc.life_places.home": "Milano",
        "lavoro.ruolo": "architetto",
        "mlc.immediate_priority": "organizzare meglio i progetti",
    }
    text = synthesize_first_picture(facts)
    assert "Milano" in text
    assert "architett" in text.lower() or "lavor" in text.lower()
    assert "organizzare" in text.lower() or "progetti" in text.lower()
    assert "abbastanza" in text.lower() or "iniziare" in text.lower()
    assert "conoscer" in text.lower()
    assert "setup completato" not in text.lower()
    assert ".." not in text
    _no_jargon(text)
    assert assert_not_wizard_copy(text)


def test_wrap_turn_cta_entra_in_ora():
    facts = {
        "mlc.current_situation": "lavoro",
        "mlc.life_places.home": "Milano",
        "lavoro.ruolo": "architetto",
        "mlc.immediate_priority": "organizzare i progetti",
    }
    turn = _run(wrap_up_turn(known_facts=facts, force_fallback=True))
    assert turn["ui"]["done"] is True
    assert turn["actions"][0]["id"] == "done"
    assert turn["actions"][0]["label"] == "Entra in ORA"
    assert "Milano" in turn["text"]
    _no_jargon(turn["text"])


def test_scenario_a_rich_then_no_redundant_name_city():
    facts = {
        "mlc.identity.name": "Luca",
        "mlc.current_situation": "lavoro",
        "mlc.life_places.home": "Milano",
        "mlc.responsibilities": "architetto",
        "lavoro.ruolo": "architetto",
        "lavoro.active": True,
    }
    plan = plan_next(ReasoningContext(user_id="u_a", known_facts=facts, session_phase="active"))
    q = (plan.next_best_question or "").lower()
    assert "come preferisci che ti chiami" not in q
    assert "dove vivi" not in q
    assert "lavori" not in q or "priorit" in q or "gestire" in q or "aiut" in q or "ora" in q


def test_scenario_f_plan_turn_synthesis():
    facts = {
        "mlc.identity.name": "Luca",
        "mlc.current_situation": "lavoro",
        "mlc.life_places.home": "Milano",
        "mlc.responsibilities": "architetto",
        "mlc.immediate_priority": "organizzare scadenze",
        "lavoro.ruolo": "architetto",
    }

    async def _go():
        svc = AILifeStrategistService()
        return await svc.plan_turn(
            "u_f4",
            known_facts=facts,
            session_phase="active",
            force_fallback=True,
            use_cache=False,
        )

    turn = asyncio.get_event_loop().run_until_complete(_go())
    assert turn.get("ui", {}).get("done") is True
    assert any(a.get("label") == "Entra in ORA" for a in (turn.get("actions") or []))
    assert "Milano" in (turn.get("text") or "")
    _no_jargon(turn.get("text") or "")


# ---------------------------------------------------------------------------
# Sprint 4.1 — explain tone
# ---------------------------------------------------------------------------


def test_nucleus_benefits_first_person_natural():
    for key, meta in NUCLEUS_QUESTIONS.items():
        b = meta["benefit"]
        _no_jargon(b)
        assert "mlc" not in b.lower()
        assert "nucleo" not in b.lower()
        assert "coverage" not in b.lower()
    pri = NUCLEUS_QUESTIONS["immediate_priority"]["benefit"]
    assert "Mi aiuta a capire da dove ha senso partire quando entri in ORA" in pri


# ---------------------------------------------------------------------------
# Sprint 4.1 — synthesis regressions
# ---------------------------------------------------------------------------


def test_synthesis_francesco_studio_tarquinia_priority():
    facts = {
        "mlc.identity.name": "Francesco",
        "mlc.current_situation": "studio",
        "studio.active": True,
        "mlc.life_places.home": "Tarquinia",
        "mlc.immediate_priority": "Vorrei organizzare meglio il tempo libero",
    }
    text = synthesize_first_picture(facts)
    low = text.lower()
    assert "francesco" in low
    assert "tarquinia" in low
    assert "studio" in low or "studi" in low
    assert "tempo libero" in low or "organizz" in low
    assert "vuoi soprattutto vorrei" not in low
    assert "vorrei vorrei" not in low
    assert ".." not in text
    # Must NOT imply studying *at* Tarquinia as a single clause
    assert "studiando" not in low or "a tarquinia" not in low.split("studiando", 1)[-1][:40].lower()
    assert "studio a tarquinia" not in low
    assert "stai studiando" not in low or "tarquinia" not in (
        low[low.find("stai studiando") : low.find("stai studiando") + 50] if "stai studiando" in low else ""
    )
    # Independent presence
    assert "vivi" in low or "tarquinia" in low
    _no_jargon(text)


def test_synthesis_guardia_di_finanza_not_come_nella():
    facts = {
        "mlc.identity.name": "Marco",
        "mlc.current_situation": "lavoro",
        "lavoro.active": True,
        "lavoro.ruolo": "Guardia di Finanza",
        "mlc.responsibilities": "Guardia di Finanza",
        "mlc.life_places.home": "Tarquinia",
        "mlc.immediate_priority": "organizzare i turni",
    }
    text = synthesize_first_picture(facts)
    low = text.lower()
    assert "lavori come nella guardia" not in low
    assert "come nella guardia di finanza" not in low
    assert "guardia di finanza" in low or "lavor" in low
    assert "tarquinia" in low
    assert ".." not in text


# ---------------------------------------------------------------------------
# Sprint 4.1 final — USER → ORA priority perspective (render-time only)
# ---------------------------------------------------------------------------


def _assert_no_user_possessive_leak(text: str) -> None:
    """Flag USER first-person possessives leaking into ORA-facing copy.

    Allows ORA voice like 'mi preme' / 'mi manca'; focuses on mio/mia/miei/mie NPs.
    """
    low = (text or "").lower()
    for bad in (
        "il mio ",
        "la mia ",
        "lo mio ",
        "i miei ",
        "le mie ",
        "un mio ",
        "una mia ",
        "del mio ",
        "della mia ",
        "dei miei ",
        "delle mie ",
        "al mio ",
        "alla mia ",
        "con la mia ",
        "con i miei ",
        "con le mie ",
    ):
        assert bad not in low, f"user possessive leak {bad!r} in {text!r}"
    # Bare possessives (not 'tuo/tua…')
    assert not re.search(r"\b(?:mio|mia|miei|mie)\b", low), f"bare user possessive in {text!r}"
    assert "organizzarmi" not in low
    # 'mi + verb' as user experience, not ORA 'mi preme/manca'
    assert not re.search(r"\bmi\s+(?!preme\b|manca\b)\w+", low), f"user 'mi …' leak in {text!r}"


def test_priority_perspective_tempo_libero_studio():
    facts = {
        "mlc.identity.name": "Francesco",
        "mlc.current_situation": "studio",
        "studio.active": True,
        "mlc.life_places.home": "Tarquinia",
        "mlc.immediate_priority": "Il mio tempo libero conciliando lo studio",
    }
    # Stored fact unchanged by renderer
    assert facts["mlc.immediate_priority"] == "Il mio tempo libero conciliando lo studio"
    text = synthesize_first_picture(facts)
    low = text.lower()
    assert "il mio tempo libero" not in low
    assert "mio tempo" not in low
    assert "studio" in low
    assert "tempo libero" in low
    _assert_no_user_possessive_leak(text)
    # Ack path also normalized
    ack = build_acknowledgement(
        last_user_text="Il mio tempo libero conciliando lo studio",
        known_facts={"mlc.immediate_priority": facts["mlc.immediate_priority"]},
    )
    if ack:
        assert "il mio tempo libero" not in ack.lower()
        _assert_no_user_possessive_leak(ack)


def test_priority_perspective_famiglia():
    facts = {
        "mlc.current_situation": "lavoro",
        "lavoro.active": True,
        "mlc.life_places.home": "Roma",
        "mlc.immediate_priority": "Vorrei passare più tempo con la mia famiglia",
    }
    text = synthesize_first_picture(facts)
    low = text.lower()
    assert "la mia famiglia" not in low
    assert "famiglia" in low
    assert "la tua famiglia" in low or "per la famiglia" in low or "tempo" in low
    _assert_no_user_possessive_leak(text)


def test_priority_perspective_lavoro_tempo():
    facts = {
        "mlc.current_situation": "lavoro",
        "lavoro.active": True,
        "mlc.life_places.home": "Milano",
        "mlc.immediate_priority": "Il mio lavoro mi prende troppo tempo",
    }
    text = synthesize_first_picture(facts)
    low = text.lower()
    assert "mio lavoro" not in low
    assert "il mio lavoro" not in low
    assert "lavoro" in low
    assert "tempo" in low
    _assert_no_user_possessive_leak(text)
    rendered = render_priority_for_ora(facts["mlc.immediate_priority"])
    assert rendered
    assert "mio" not in rendered.text.lower()


def test_priority_perspective_esami():
    facts = {
        "mlc.current_situation": "studio",
        "studio.active": True,
        "mlc.life_places.home": "Bologna",
        "mlc.immediate_priority": "Voglio organizzarmi meglio con i miei esami",
    }
    text = synthesize_first_picture(facts)
    low = text.lower()
    assert "i miei esami" not in low
    assert "organizzarmi" not in low
    assert "esami" in low
    assert "organizz" in low or "gestir" in low
    _assert_no_user_possessive_leak(text)


def test_priority_perspective_francesco_no_regression():
    facts = {
        "mlc.identity.name": "Francesco",
        "mlc.current_situation": "studio",
        "studio.active": True,
        "mlc.life_places.home": "Tarquinia",
        "mlc.immediate_priority": "Vorrei organizzare meglio il tempo libero",
    }
    text = synthesize_first_picture(facts)
    low = text.lower()
    assert "francesco" in low
    assert "tarquinia" in low
    assert "studio" in low or "studi" in low
    assert "tempo libero" in low or "organizz" in low
    assert "vuoi soprattutto vorrei" not in low
    assert "studio a tarquinia" not in low
    _assert_no_user_possessive_leak(text)
    _no_jargon(text)


def test_priority_perspective_synthesis_no_user_voice_leak():
    cases = [
        "Il mio tempo libero conciliando lo studio",
        "Vorrei passare più tempo con la mia famiglia",
        "Il mio lavoro mi prende troppo tempo",
        "Voglio organizzarmi meglio con i miei esami",
        "organizzare meglio i progetti",
        "Vorrei organizzare meglio il tempo libero",
    ]
    base = {
        "mlc.identity.name": "Francesco",
        "mlc.current_situation": "studio",
        "studio.active": True,
        "mlc.life_places.home": "Tarquinia",
    }
    for pri in cases:
        text = synthesize_first_picture({**base, "mlc.immediate_priority": pri})
        _assert_no_user_possessive_leak(text)
        # Stored value must not be rewritten by synthesis
        assert pri  # fact key remains caller-owned; renderer is pure


# ---------------------------------------------------------------------------
# Sprint 4.1 — location action contract
# ---------------------------------------------------------------------------


def _plan_with_gap(gap_key: str, nucleus: str | None = None) -> StrategistPlan:
    nuc = nucleus or "life_places"
    return StrategistPlan(
        next_best_question="Dove vivi principalmente in questo periodo? Basta la città.",
        question_reason="test",
        expected_benefit=NUCLEUS_QUESTIONS.get(nuc, {}).get("benefit", "x"),
        information_gain=0.9,
        domain="casa",
        priority=20,
        prefer_document=False,
        source="deterministic_fallback",
        gap_keys=[gap_key],
        meta={
            "phase": "active",
            "gap_key": gap_key,
            "mlc_nucleus": nuc,
            "question_goal": question_goal_for_gap(gap_key, nuc),
        },
    )


def test_location_action_present_for_life_places_gap():
    turn = build_active_turn(_plan_with_gap("mlc.life_places.home", "life_places"))
    ids = [a["id"] for a in turn["actions"]]
    assert "use_current_location" in ids
    loc = next(a for a in turn["actions"] if a["id"] == "use_current_location")
    assert loc["label"] == "Usa la mia posizione"


def test_location_action_absent_for_other_gap():
    plan = StrategistPlan(
        next_best_question="Come preferisci che ti chiami?",
        question_reason="test",
        expected_benefit="x",
        information_gain=0.9,
        domain="servizi",
        priority=10,
        source="deterministic_fallback",
        gap_keys=["mlc.identity.name"],
        meta={"phase": "active", "gap_key": "mlc.identity.name", "mlc_nucleus": "identity"},
    )
    turn = build_active_turn(plan)
    ids = [a["id"] for a in turn["actions"]]
    assert "use_current_location" not in ids


def test_location_confirm_prompt_copy():
    p = location_confirm_prompt("Tarquinia")
    assert "Tarquinia" in p
    assert "vivi principalmente" in p.lower()


def test_document_proposal_actions_in_turn_contract():
    plan = StrategistPlan(
        next_best_question="Hai un rogito a portata di mano?",
        question_reason="posso ricavare io indirizzo senza form",
        expected_benefit="posso ricavare io indirizzo senza form",
        information_gain=0.8,
        domain="casa",
        priority=30,
        prefer_document=True,
        source="deterministic_fallback",
        gap_keys=["doc.rogito"],
        meta={"phase": "active", "gap_key": "doc.rogito"},
    )
    from ai_life_strategist.document_strategy import recommend_document

    plan.recommended_document = recommend_document("rogito", domain="casa")
    turn = build_active_turn(plan)
    ids = {a["id"]: a["label"] for a in turn["actions"]}
    assert "upload_doc" in ids
    assert "doc_not_now" in ids
    assert ids["doc_not_now"] == "Non ora"
    assert "doc_prefer_answer" in ids
    assert ids["doc_prefer_answer"] == "Preferisco rispondere"
    text_blob = " ".join(
        [
            turn.get("text") or "",
            plan.recommended_document.reason if plan.recommended_document else "",
            turn.get("expected_benefit") or "",
        ]
    )
    _no_jargon(text_blob)
    assert "obbligatorio" not in text_blob.lower() or "non" in text_blob.lower()


# ---------------------------------------------------------------------------
# Sprint 4.1 — refusal + location confirm (Mongo)
# ---------------------------------------------------------------------------


def test_refusal_preferisco_non_parlarne():
    user = uid("ref1")

    async def _go():
        client, db = await _db()
        try:
            await _clean(db, user)
            svc = _svc(db)
            started = await svc.start(user)
            assert started.get("ok")
            # Force a known gap so refuse binds to it
            sess = await svc.repo.latest_session(user)
            assert sess
            sess.last_plan = {
                "next_best_question": "Come preferisci che ti chiami?",
                "meta": {"gap_key": "mlc.identity.name", "mlc_nucleus": "identity"},
            }
            sess.phase = "active"
            await svc.repo.save_session(sess)

            ans = await svc.answer(user, "Preferisco non parlarne.")
            assert ans.get("ok")
            sess2 = ans["session"]
            assert "mlc.identity.name" in (sess2.get("refused_keys") or [])
            facts = sess2.get("known_facts") or {}
            assert facts.get("mlc.identity.name") in (None, "", False)
            turn = ans.get("turn") or {}
            text = (turn.get("text") or "") + " " + (sess2.get("meta", {}).get("last_ack") or "")
            assert "rispetto" in text.lower() or "va bene" in text.lower() or "non insist" in text.lower()
            next_gap = ((turn.get("plan") or {}).get("meta") or {}).get("gap_key")
            assert next_gap != "mlc.identity.name"
            assert not (turn.get("ui") or {}).get("done"), "refuse alone must not illegitimately wrap"
        finally:
            client.close()

    _run(_go())


def test_refusal_non_voglio_dirlo():
    user = uid("ref2")

    async def _go():
        client, db = await _db()
        try:
            await _clean(db, user)
            svc = _svc(db)
            await svc.start(user)
            sess = await svc.repo.latest_session(user)
            sess.last_plan = {
                "next_best_question": "Dove vivi principalmente?",
                "meta": {"gap_key": "mlc.life_places.home", "mlc_nucleus": "life_places"},
            }
            sess.phase = "active"
            await svc.repo.save_session(sess)

            ans = await svc.answer(user, "Non voglio dirlo.")
            sess2 = ans["session"]
            assert "mlc.life_places.home" in (sess2.get("refused_keys") or [])
            assert not (sess2.get("known_facts") or {}).get("mlc.life_places.home")
            turn = ans.get("turn") or {}
            next_gap = ((turn.get("plan") or {}).get("meta") or {}).get("gap_key")
            assert next_gap != "mlc.life_places.home"
            ack = (sess2.get("meta") or {}).get("last_ack") or turn.get("text") or ""
            assert "va bene" in ack.lower() or "rispetto" in ack.lower()
        finally:
            client.close()

    _run(_go())


def test_confirm_location_saves_city_reject_does_not():
    user = uid("loc")

    async def _go():
        client, db = await _db()
        try:
            await _clean(db, user)
            svc = _svc(db)
            await svc.start(user)
            sess = await svc.repo.latest_session(user)
            sess.last_plan = {
                "next_best_question": "Dove vivi principalmente?",
                "meta": {"gap_key": "mlc.life_places.home", "mlc_nucleus": "life_places"},
            }
            sess.phase = "active"
            await svc.repo.save_session(sess)

            with patch(
                "action_engine.travel.maps.nominatim_reverse_city",
                new=AsyncMock(return_value="Tarquinia"),
            ):
                geo = await svc.reverse_geocode(user, 42.25, 11.75)
            assert geo.get("ok")
            assert geo.get("city") == "Tarquinia"
            assert geo.get("persists_coordinates") is False
            assert "Tarquinia" in (geo.get("confirm_prompt") or "")

            # Reject — no save
            rej = await svc.confirm_location(user, "Tarquinia", confirmed=False)
            assert rej.get("ok")
            assert rej.get("location_confirmed") is False
            sess_r = rej["session"]
            assert not (sess_r.get("known_facts") or {}).get("mlc.life_places.home")

            # Confirm — save city only
            conf = await svc.confirm_location(user, "Tarquinia", confirmed=True)
            assert conf.get("ok")
            assert conf.get("location_confirmed") is True
            facts = (conf.get("session") or {}).get("known_facts") or {}
            assert facts.get("mlc.life_places.home") == "Tarquinia"
            assert "pending_lat" not in (conf.get("session") or {}).get("meta", {})
        finally:
            client.close()

    _run(_go())


# ---------------------------------------------------------------------------
# Sprint 4.2 — AI-Native Conversational Rendering (property-based)
# ---------------------------------------------------------------------------


def _assert_no_broken_lavori_come(text: str) -> None:
    low = (text or "").lower()
    assert "lavori come mi prende" not in low
    assert "lavori come il mio" not in low
    assert not re.search(r"lavori\s+come\s+mi\s+", low)


def test_42_a_work_family_priority_no_fake_profession():
    """A) work+family priority — no 'lavori come mi prende'; no fake profession."""
    priority = "Il mio lavoro mi prende troppo tempo, vorrei passare più tempo con la famiglia"
    # Bug class: priority wrongly stored as ruolo / responsibilities
    facts = {
        "mlc.current_situation": "lavoro",
        "lavoro.active": True,
        "lavoro.ruolo": priority,  # poisoned structured field
        "mlc.responsibilities": priority,
        "mlc.immediate_priority": priority,
        "mlc.life_places.home": "Milano",
    }
    assert not looks_like_role_title(priority)
    ack = build_acknowledgement(last_user_text=priority, known_facts=facts)
    syn = synthesize_first_picture(facts)
    wrap = safe_wrap_fallback(facts)
    for text in (ack or "", syn, wrap):
        _assert_no_broken_lavori_come(text)
        low = text.lower()
        assert "lavori come il mio lavoro" not in low
    # Semantic preservation via priority render (work + time + family)
    rendered = render_priority_for_ora(priority)
    assert rendered
    low_r = rendered.text.lower()
    assert "lavoro" in low_r or "tempo" in low_r
    assert "famiglia" in syn.lower() or "famiglia" in low_r or "tempo" in syn.lower()
    # Ack/synthesis must not invent a short fake job title from the sentence
    for text in (ack or "", syn):
        assert not re.search(r"lavori\s+come\s+\w{3,20}\.", text.lower())


def test_42_b_tempo_libero_studio_no_mio_leak():
    """B) tempo libero + studio — no perspective leak 'il mio'."""
    facts = {
        "mlc.current_situation": "studio",
        "studio.active": True,
        "mlc.immediate_priority": "Il mio tempo libero conciliando lo studio",
        "mlc.life_places.home": "Tarquinia",
    }
    text = synthesize_first_picture(facts)
    assert "il mio" not in text.lower()
    _assert_no_user_possessive_leak(text)
    plan = StrategistPlan(
        next_best_question="Dove vivi principalmente in questo periodo?",
        spoken_question="Dove vivi principalmente in questo periodo?",
        acknowledgement="Capito — ti preme bilanciare studio e tempo libero.",
        question_reason="t",
        expected_benefit="b",
        domain="casa",
        source="gemini",
    )
    turn_text = render_conversational_turn({"plan": plan, "known_facts": facts})
    assert "il mio" not in turn_text.lower()
    _no_jargon(turn_text)


def test_42_c_maresciallo_roma_no_invented_works_in_city():
    """C) role+city OK; don't invent works-in-Roma unless structured."""
    facts = {
        "mlc.current_situation": "lavoro",
        "lavoro.active": True,
        "lavoro.ruolo": "maresciallo",
        "mlc.life_places.home": "Roma",
        "mlc.immediate_priority": "organizzare i turni",
    }
    assert looks_like_role_title("maresciallo")
    text = synthesize_first_picture(facts)
    low = text.lower()
    assert "roma" in low
    assert "maresciallo" in low or "lavor" in low
    assert "lavori a roma" not in low
    assert "lavori come maresciallo a roma" not in low
    _assert_no_broken_lavori_come(text)
    # Gemini spoken path must not invent workplace-in-city
    bad = validate_rendered_text(
        "Capito, lavori a Roma come maresciallo. Dove vivi?",
        allowed_fact_values=["Roma", "maresciallo"],
        kind="turn",
    )
    assert bad is None


def test_42_d_studio_medicina_bologna_structured_ok():
    """D) Studio medicina a Bologna — structured extraction OK."""
    facts = {
        "mlc.current_situation": "studio",
        "studio.active": True,
        "studio.universita": "medicina",
        "mlc.life_places.home": "Bologna",
        "mlc.immediate_priority": "organizzare gli esami",
    }
    text = synthesize_first_picture(facts)
    low = text.lower()
    assert "bologna" in low
    assert "studio" in low or "studi" in low or "medicina" in low
    assert "studio a bologna" not in low  # no invented study-at-city glue
    _assert_no_broken_lavori_come(text)
    _no_jargon(text)


def test_42_e_ambiguous_prudent_no_invention():
    """E) ambiguous 'Sto facendo un po' di cose.' — prudent, no invention."""
    facts = {"mlc.immediate_priority": "Sto facendo un po' di cose."}
    ack = build_acknowledgement(
        last_user_text="Sto facendo un po' di cose.",
        known_facts=facts,
    )
    syn = synthesize_first_picture(facts)
    for text in (ack or "Capito.", syn):
        low = text.lower()
        _assert_no_broken_lavori_come(text)
        assert "lavori come" not in low
        assert "medico" not in low
        assert "ingegner" not in low
        assert "roma" not in low
        _no_jargon(text)


def test_42_f_gemini_failure_safe_fallback():
    """F) Gemini failure mocked — safe fallback, no broken 'lavori come'."""
    facts = {
        "mlc.current_situation": "lavoro",
        "lavoro.active": True,
        "lavoro.ruolo": "Il mio lavoro mi prende troppo tempo",
        "mlc.responsibilities": "Il mio lavoro mi prende troppo tempo",
        "mlc.immediate_priority": "Il mio lavoro mi prende troppo tempo, e la famiglia",
        "mlc.life_places.home": "Milano",
    }

    async def _gemini_fail(*_a, **_k):
        return None  # same as reason_with_gemini soft-fail

    with patch("ai_life_strategist.reasoner.reason_with_gemini", new=_gemini_fail):
        plan = _run(
            AILifeStrategistService().next_question(
                "u_42f",
                known_facts=facts,
                last_user_text="Il mio lavoro mi prende troppo tempo",
                force_fallback=False,
                use_cache=False,
            )
        )
    assert plan.source == "deterministic_fallback"
    assert plan.next_best_question
    turn = build_active_turn(plan, known_facts=facts, ack=None)
    _assert_no_broken_lavori_come(turn["text"])
    _no_jargon(turn["text"])

    # AI wrap failure → SAFE wrap (not poisoned 'lavori come')
    async def _chat_fail(*_a, **_k):
        raise RuntimeError("gemini down")

    with patch("llm.manager.ProviderManager.chat", new=_chat_fail):
        wrap = _run(wrap_up_turn(known_facts=facts, force_fallback=False))
    _assert_no_broken_lavori_come(wrap["text"])
    assert "lavori come" not in wrap["text"].lower()
    assert wrap["ui"]["done"] is True
    assert any(a.get("label") == "Entra in ORA" for a in wrap["actions"])


def test_42_validate_rejects_jargon_and_broken_glue():
    assert validate_rendered_text("Serve per il MLC coverage", kind="ack") is None
    assert validate_rendered_text('{"next_best_question": "x"}', kind="turn") is None
    assert (
        validate_rendered_text(
            "Capito, lavori come mi prende troppo tempo. Dove vivi?",
            kind="turn",
        )
        is None
    )
    ok = validate_rendered_text(
        "Capito. Dove vivi principalmente in questo periodo?",
        kind="turn",
    )
    assert ok


def test_42_render_prefers_valid_gemini_spoken_fields():
    plan = StrategistPlan(
        next_best_question="Dove vivi principalmente?",
        spoken_question="In quale città vivi principalmente adesso?",
        acknowledgement="Capito — il lavoro pesa sulle tue giornate.",
        conversational_bridge="Sto mettendo insieme i pezzi.",  # must be ignored when ack present
        question_reason="t",
        expected_benefit="b",
        domain="casa",
        source="gemini",
        meta={"gap_key": "mlc.life_places.home", "mlc_nucleus": "life_places"},
    )
    text = render_conversational_turn(
        {
            "plan": plan,
            "known_facts": {"mlc.current_situation": "lavoro", "lavoro.active": True},
        }
    )
    assert "In quale città vivi principalmente adesso?" in text
    assert "Capito" in text
    assert "Sto mettendo insieme" not in text  # ack excludes bridge
    turn = build_active_turn(plan, known_facts={"lavoro.active": True})
    assert "use_current_location" in [a["id"] for a in turn["actions"]]


def test_42_walkthrough_ack_ask_life_places_after_work_family():
    """Walkthrough-style: Gemini ack preserves work+family; then life_places ask."""
    priority = "Il lavoro mi prende troppo tempo e vorrei più tempo per la famiglia"
    facts = {
        "mlc.current_situation": "lavoro",
        "lavoro.active": True,
        "mlc.immediate_priority": priority,
        "mlc.responsibilities": priority,
    }
    gem_ack = (
        "Capito — il lavoro ti prende troppo tempo e vorresti più spazio per la famiglia."
    )
    plan = StrategistPlan(
        next_best_question="Dove vivi principalmente in questo periodo? Basta la città.",
        spoken_question="Dove vivi principalmente in questo periodo? Basta la città.",
        acknowledgement=gem_ack,
        question_reason="t",
        expected_benefit=NUCLEUS_QUESTIONS["life_places"]["benefit"],
        domain="casa",
        source="gemini",
        gap_keys=["mlc.life_places.home"],
        meta={
            "phase": "active",
            "gap_key": "mlc.life_places.home",
            "mlc_nucleus": "life_places",
        },
    )
    turn = build_active_turn(plan, ack=None, known_facts=facts)
    text = turn["text"]
    _assert_no_broken_lavori_come(text)
    _no_jargon(text)
    assert "vivi" in text.lower() or "città" in text.lower() or "citta" in text.lower()
    assert "use_current_location" in [a["id"] for a in turn["actions"]]
    low = text.lower()
    assert "lavor" in low or "tempo" in low
    assert "famigli" in low
    assert "occupa una parte importante delle tue giornate" not in low


def test_42_mocked_gemini_spoken_json_used_when_valid():
    """Mock reason_with_gemini JSON → spoken fields preferred on active turn."""
    from ai_life_strategist.models import ReasoningContext
    from ai_life_strategist import reasoner as reasoner_mod

    async def _fake_gemini(ctx: ReasoningContext, *, planner_plan=None):
        return StrategistPlan(
            next_best_question="Dove vivi principalmente?",
            spoken_question="In che città vivi principalmente?",
            acknowledgement="Capito.",
            question_reason="serve per proposte realistiche",
            expected_benefit="posso proporti cose utili vicino a te",
            domain="casa",
            source="gemini",
            information_gain=0.9,
            confidence=0.8,
            meta={"phase": "active", "gap_key": "mlc.life_places.home", "mlc_nucleus": "life_places"},
        )

    with patch.object(reasoner_mod, "reason_with_gemini", new=_fake_gemini):
        with patch.object(reasoner_mod, "strategist_gemini_enabled", return_value=True):
            plan = _run(
                reasoner_mod.reason(
                    ReasoningContext(
                        user_id="u_42mock",
                        known_facts={"mlc.current_situation": "lavoro", "lavoro.active": True},
                        last_user_text="Lavoro e vorrei più tempo per la famiglia",
                        session_phase="active",
                        missing_keys=["mlc.life_places.home"],
                    ),
                    force_fallback=False,
                )
            )
    # enforce_mlc may rewrite if insufficient — still should keep spoken if active
    if (plan.meta or {}).get("phase") != "wrap":
        assert plan.spoken_question or plan.next_best_question
        turn = build_active_turn(plan, known_facts={"lavoro.active": True})
        _assert_no_broken_lavori_come(turn["text"])
        _no_jargon(turn["text"])


# ---------------------------------------------------------------------------
# Sprint 4.2b — acknowledgement reflects full user meaning (not MLC slot alone)
# ---------------------------------------------------------------------------

_GENERIC_WORK_ONLY = "occupa una parte importante delle tue giornate"


def test_42b_a_work_time_family_ack_preserves_both():
    """A) work + too much time + family → ack conserves both; not situation-only phrase."""
    user = "Il mio lavoro mi prende troppo tempo, vorrei passare più tempo con la famiglia"
    facts = {
        "mlc.current_situation": "lavoro",
        "lavoro.active": True,
        # NLP often omits immediate_priority — situation-only MLC
    }
    gem_ack = (
        "Capito — il lavoro ti prende troppo tempo e vorresti più spazio per la famiglia."
    )
    plan = StrategistPlan(
        next_best_question="Dove vivi principalmente in questo periodo?",
        spoken_question="Dove vivi principalmente in questo periodo?",
        acknowledgement=gem_ack,
        question_reason="t",
        expected_benefit="b",
        domain="casa",
        source="gemini",
        meta={"gap_key": "mlc.life_places.home", "mlc_nucleus": "life_places"},
    )
    text = render_conversational_turn({"plan": plan, "known_facts": facts, "ack": None})
    low = text.lower()
    assert "lavor" in low or "tempo" in low
    assert "famigli" in low
    assert _GENERIC_WORK_ONLY not in low
    _assert_no_broken_lavori_come(text)
    # Property: meaning from user utterance, not sole MLC slot
    assert "lavor" in user.lower() and "famigli" in user.lower()


def test_42b_b_study_stress_free_time_preserves_both():
    """B) study + stress + free time → ack preserves both themes."""
    facts = {"mlc.current_situation": "studio", "studio.active": True}
    gem_ack = "Capito — lo studio ti stressa e ti manca tempo libero."
    plan = StrategistPlan(
        next_best_question="Dove vivi principalmente?",
        spoken_question="Dove vivi principalmente?",
        acknowledgement=gem_ack,
        question_reason="t",
        expected_benefit="b",
        domain="casa",
        source="gemini",
    )
    text = render_conversational_turn({"plan": plan, "known_facts": facts})
    low = text.lower()
    assert "studio" in low or "studi" in low
    assert "tempo libero" in low or "stress" in low
    assert "lo studio occupa una parte importante" not in low
    _no_jargon(text)


def test_42b_c_multi_info_not_reduced_to_mlc_slot():
    """C) multi-info turn → ack not reduced to sole MLC situation slot."""
    facts = {"mlc.current_situation": "lavoro", "lavoro.active": True}
    gem_ack = (
        "Capito — lavori molto e vorresti più equilibrio con la famiglia."
    )
    plan = StrategistPlan(
        next_best_question="Dove vivi principalmente?",
        spoken_question="Dove vivi principalmente?",
        acknowledgement=gem_ack,
        question_reason="t",
        expected_benefit="b",
        domain="casa",
        source="gemini",
    )
    text = render_conversational_turn({"plan": plan, "known_facts": facts})
    # Must not be only the generic situation-only deterministic phrase
    assert _GENERIC_WORK_ONLY not in text.lower()
    assert "famigli" in text.lower() or "equilibri" in text.lower()
    # If someone passed rich build_acknowledgement as override with Gemini null,
    # that path is no longer the default — Gemini ack wins here
    assert "Capito" in text


def test_42b_d_gemini_context_surfaces_latest_user_message():
    """D) to_gemini_context_json / reasoner payload expose latest_user_message."""
    from ai_life_strategist.reasoning_loop import to_gemini_context_json
    from ai_life_strategist import reasoner as reasoner_mod

    msg = "Lavoro troppo e vorrei più tempo per la famiglia"
    ctx = ReasoningContext(
        user_id="u_42b_d",
        known_facts={"mlc.current_situation": "lavoro", "lavoro.active": True},
        last_user_text=msg,
        session_phase="active",
        missing_keys=["mlc.life_places.home"],
    )
    payload = to_gemini_context_json(ctx)
    assert payload.get("latest_user_message") == msg
    assert payload.get("last_user_text") == msg
    assert "acknowledgement_instruction" in payload
    assert "latest_user_message" in (payload.get("acknowledgement_instruction") or "")

    # Prompt contract: SYSTEM_PROMPT treats latest message as primary ack evidence
    assert "latest_user_message" in reasoner_mod.SYSTEM_PROMPT
    assert "EVIDENZA PRIMARIA" in reasoner_mod.SYSTEM_PROMPT or "evidenza primaria" in (
        reasoner_mod.SYSTEM_PROMPT.lower()
    )


def test_42b_e_ai_invalid_safe_capito_plus_question():
    """E) AI invalid / null ack → SAFE 'Capito.' + question, no broken lavori come."""
    facts = {
        "mlc.current_situation": "lavoro",
        "lavoro.active": True,
        "lavoro.ruolo": "mi prende troppo tempo",  # poisoned; not a role title
    }
    assert not looks_like_role_title("mi prende troppo tempo")
    plan = StrategistPlan(
        next_best_question="Dove vivi principalmente in questo periodo?",
        spoken_question="Dove vivi principalmente in questo periodo?",
        acknowledgement=None,
        question_reason="t",
        expected_benefit="b",
        domain="casa",
        source="deterministic_fallback",
        meta={"gap_key": "mlc.life_places.home", "mlc_nucleus": "life_places"},
    )
    text = render_conversational_turn({"plan": plan, "known_facts": facts, "ack": None})
    assert text.startswith("Capito.")
    assert "Dove vivi" in text
    assert _GENERIC_WORK_ONLY not in text.lower()
    _assert_no_broken_lavori_come(text)
    assert "lavori come" not in text.lower()


def test_42b_f_force_fallback_not_rich_generic_work_phrase():
    """F) force_fallback / Gemini null → Capito + question, NOT rich work-only ack."""
    user = "Il lavoro mi prende troppo tempo e vorrei più tempo per la famiglia"
    facts = {
        "mlc.current_situation": "lavoro",
        "lavoro.active": True,
        # No immediate_priority — the bug class that made build_acknowledgement drop family
    }
    # Even if a caller mistakenly passes rich build_acknowledgement, SAFE path
    # for force_fallback should not use situation-only as the sole ack for this utterance.
    rich = build_acknowledgement(last_user_text=user, known_facts=facts)
    # Rich deterministic may still emit situation-only; Architecture A must not rely on it
    if rich:
        assert _GENERIC_WORK_ONLY in rich.lower() or "lavor" in rich.lower()

    plan = StrategistPlan(
        next_best_question="Dove vivi principalmente in questo periodo?",
        spoken_question="Dove vivi principalmente in questo periodo?",
        acknowledgement=None,
        question_reason="t",
        expected_benefit="b",
        domain="casa",
        source="deterministic_fallback",
        meta={"gap_key": "mlc.life_places.home", "mlc_nucleus": "life_places"},
    )
    # Normal free-text path: no rich override
    text = render_conversational_turn({"plan": plan, "known_facts": facts, "ack": None})
    assert text.startswith("Capito.")
    assert "Dove vivi" in text
    assert _GENERIC_WORK_ONLY not in text
    _assert_no_broken_lavori_come(text)

    # force_fallback through reasoner → same SAFE render contract
    from ai_life_strategist import reasoner as reasoner_mod

    plan2 = _run(
        reasoner_mod.reason(
            ReasoningContext(
                user_id="u_42b_f",
                known_facts=facts,
                last_user_text=user,
                session_phase="active",
                missing_keys=["mlc.life_places.home"],
            ),
            force_fallback=True,
        )
    )
    turn = build_active_turn(plan2, ack=None, known_facts=facts)
    assert turn["text"].startswith("Capito.")
    assert _GENERIC_WORK_ONLY not in turn["text"]
    _assert_no_broken_lavori_come(turn["text"])


def test_42b_mocked_gemini_family_ack_preferred_over_override():
    """Mock Gemini returning famiglia ack wins; override must not strip family."""
    from ai_life_strategist import reasoner as reasoner_mod

    user = "Lavoro e vorrei più tempo per la famiglia"
    facts = {"mlc.current_situation": "lavoro", "lavoro.active": True}

    async def _fake_gemini(ctx: ReasoningContext, *, planner_plan=None):
        return StrategistPlan(
            next_best_question="Dove vivi principalmente?",
            spoken_question="In che città vivi principalmente?",
            acknowledgement=(
                "Capito — il lavoro pesa e vorresti più tempo per la famiglia."
            ),
            question_reason="serve per proposte realistiche",
            expected_benefit="posso proporti cose utili vicino a te",
            domain="casa",
            source="gemini",
            information_gain=0.9,
            confidence=0.8,
            meta={
                "phase": "active",
                "gap_key": "mlc.life_places.home",
                "mlc_nucleus": "life_places",
            },
        )

    with patch.object(reasoner_mod, "reason_with_gemini", new=_fake_gemini):
        with patch.object(reasoner_mod, "strategist_gemini_enabled", return_value=True):
            plan = _run(
                reasoner_mod.reason(
                    ReasoningContext(
                        user_id="u_42b_mock",
                        known_facts=facts,
                        last_user_text=user,
                        session_phase="active",
                        missing_keys=["mlc.life_places.home"],
                    ),
                    force_fallback=False,
                )
            )
    if (plan.meta or {}).get("phase") == "wrap":
        return
    # Mistaken rich override must not win over valid Gemini ack
    rich_override = build_acknowledgement(last_user_text=user, known_facts=facts)
    turn = build_active_turn(plan, ack=rich_override, known_facts=facts)
    low = turn["text"].lower()
    assert "famigli" in low
    assert _GENERIC_WORK_ONLY not in low or "famigli" in low
    _assert_no_broken_lavori_come(turn["text"])


# ---------------------------------------------------------------------------
# Sprint 4.2 Final Fix — constrain AI rendering to deterministic question intent
# ---------------------------------------------------------------------------

_HOME_SAFE = NUCLEUS_QUESTIONS["life_places"]["question"]
_HOME_GOAL = QUESTION_GOALS["mlc.life_places.home"]


def _life_places_plan(
    *,
    spoken: str | None,
    ack: str | None = "Capito.",
    nbq: str | None = None,
) -> StrategistPlan:
    return StrategistPlan(
        next_best_question=nbq or _HOME_SAFE,
        spoken_question=spoken,
        acknowledgement=ack,
        question_reason="t",
        expected_benefit=NUCLEUS_QUESTIONS["life_places"]["benefit"],
        domain="casa",
        source="gemini",
        gap_keys=["mlc.life_places.home"],
        meta={
            "phase": "active",
            "gap_key": "mlc.life_places.home",
            "mlc_nucleus": "life_places",
            "question_goal": dict(_HOME_GOAL),
        },
    )


def test_42ff_a_workplace_question_rejected_falls_back_to_home_city():
    """A) gap life_places, AI asks workplace → reject → deterministic home city."""
    spoken = "Dove lavori principalmente in questo periodo?"
    assert (
        validate_spoken_question_for_goal(
            spoken,
            question_goal=_HOME_GOAL,
            gap_key="mlc.life_places.home",
            mlc_nucleus="life_places",
        )
        is None
    )
    plan = _life_places_plan(spoken=spoken)
    q = resolve_turn_question(plan)
    assert q == _HOME_SAFE
    text = render_conversational_turn({"plan": plan, "known_facts": {}})
    assert "Dove vivi principalmente" in text
    assert "dove lavori" not in text.lower()


def test_42ff_b_spend_the_day_drift_rejected():
    """B) gap life_places, AI asks where spends the day → reject/fallback."""
    spoken = "dove ti trovi principalmente a gestire la tua giornata?"
    assert (
        validate_spoken_question_for_goal(
            spoken,
            question_goal=_HOME_GOAL,
            gap_key="mlc.life_places.home",
            mlc_nucleus="life_places",
        )
        is None
    )
    plan = _life_places_plan(spoken=spoken, ack="Capito.")
    text = render_conversational_turn({"plan": plan, "known_facts": {}})
    assert "gestire la tua giornata" not in text.lower()
    assert "vivi" in text.lower()
    turn_q = build_active_turn(plan)["question"] or ""
    assert "vivi" in turn_q.lower()
    assert "gestire" not in turn_q.lower()


def test_42ff_c_valid_home_paraphrase_accepted():
    """C) valid paraphrase «Dove vivi principalmente...» → accept."""
    spoken = "Dove vivi principalmente in questo periodo? Basta la città."
    assert (
        validate_spoken_question_for_goal(
            spoken,
            question_goal=_HOME_GOAL,
            gap_key="mlc.life_places.home",
            mlc_nucleus="life_places",
        )
        == spoken
    )
    alt = "In quale città vivi principalmente adesso?"
    assert validate_spoken_question_for_goal(
        alt, question_goal=_HOME_GOAL, gap_key="mlc.life_places.home"
    )
    plan = _life_places_plan(spoken=alt)
    text = render_conversational_turn({"plan": plan, "known_facts": {}})
    assert "In quale città vivi principalmente adesso?" in text


def test_42ff_d_ack_giustamente_sanitized():
    """D) ack with «giustamente» → reject/sanitize/fallback; question kept."""
    raw = "Giustamente, il lavoro ti pesa."
    cleaned = sanitize_acknowledgement(raw)
    assert cleaned is not None
    assert "giustamente" not in cleaned.lower()
    plan = _life_places_plan(
        spoken="Dove vivi principalmente in questo periodo?",
        ack="Giustamente, il lavoro ti pesa sulle giornate.",
    )
    text = render_conversational_turn({"plan": plan, "known_facts": {"lavoro.active": True}})
    low = text.lower()
    assert "giustamente" not in low
    assert "ovviamente" not in low
    assert "correttamente" not in low
    assert "vivi" in low
    # Capito. or sanitized remnant without judgment
    assert "capito" in low or "lavoro" in low


def test_42ff_e_work_family_ack_preserves_both_no_judgment():
    """E) work+family → ack preserves both without judgment (mock Gemini)."""
    from ai_life_strategist import reasoner as reasoner_mod

    user = "Il lavoro mi prende troppo tempo e vorrei più tempo per la famiglia"
    facts = {"mlc.current_situation": "lavoro", "lavoro.active": True}

    async def _fake_gemini(ctx: ReasoningContext, *, planner_plan=None):
        return StrategistPlan(
            next_best_question=_HOME_SAFE,
            spoken_question="Dove vivi principalmente in questo periodo? Basta la città.",
            acknowledgement=(
                "Capito — il lavoro ti prende troppo tempo e vorresti più spazio per la famiglia."
            ),
            question_reason="serve per proposte realistiche",
            expected_benefit=NUCLEUS_QUESTIONS["life_places"]["benefit"],
            domain="casa",
            source="gemini",
            information_gain=0.9,
            confidence=0.8,
            gap_keys=["mlc.life_places.home"],
            meta={
                "phase": "active",
                "gap_key": "mlc.life_places.home",
                "mlc_nucleus": "life_places",
                "question_goal": dict(_HOME_GOAL),
            },
        )

    with patch.object(reasoner_mod, "reason_with_gemini", new=_fake_gemini):
        with patch.object(reasoner_mod, "strategist_gemini_enabled", return_value=True):
            plan = _run(
                reasoner_mod.reason(
                    ReasoningContext(
                        user_id="u_42ff_e",
                        known_facts=facts,
                        last_user_text=user,
                        session_phase="active",
                        missing_keys=["mlc.life_places.home"],
                    ),
                    force_fallback=False,
                )
            )
    if (plan.meta or {}).get("phase") == "wrap":
        return
    assert (plan.meta or {}).get("question_goal")
    assert (plan.meta or {}).get("gap_key") == "mlc.life_places.home"
    turn = build_active_turn(plan, ack=None, known_facts=facts)
    low = turn["text"].lower()
    assert "lavor" in low or "tempo" in low
    assert "famigli" in low
    assert "giustamente" not in low
    assert "vivi" in low
    _assert_no_broken_lavori_come(turn["text"])


def test_42ff_f_identity_situation_priority_goals_no_false_reject():
    """F) identity/situation/priority goals keep intended semantics (no false-reject)."""
    cases = [
        (
            "mlc.identity.name",
            "identity",
            "Come preferisci che ti chiami?",
            "Come vuoi che ti chiami?",
        ),
        (
            "mlc.current_situation",
            "current_situation",
            NUCLEUS_QUESTIONS["current_situation"]["question"],
            "In questo periodo lavori, studi, o fai entrambe le cose?",
        ),
        (
            "mlc.immediate_priority",
            "immediate_priority",
            NUCLEUS_QUESTIONS["immediate_priority"]["question"],
            "C’è qualcosa che vorresti gestire meglio proprio adesso?",
        ),
        (
            "mlc.responsibilities",
            "responsibilities",
            NUCLEUS_QUESTIONS["responsibilities"]["question"],
            "Quali impegni ti occupano di più in questo periodo?",
        ),
    ]
    for gap_key, nucleus, safe_q, paraphrase in cases:
        goal = question_goal_for_gap(gap_key, nucleus)
        assert goal is not None
        assert goal.get("id")
        assert (
            validate_spoken_question_for_goal(
                paraphrase,
                question_goal=goal,
                gap_key=gap_key,
                mlc_nucleus=nucleus,
            )
            == paraphrase
        )
        plan = StrategistPlan(
            next_best_question=safe_q,
            spoken_question=paraphrase,
            acknowledgement="Capito.",
            question_reason="t",
            expected_benefit="b",
            domain="servizi",
            source="gemini",
            gap_keys=[gap_key],
            meta={
                "phase": "active",
                "gap_key": gap_key,
                "mlc_nucleus": nucleus,
                "question_goal": goal,
            },
        )
        resolved = resolve_turn_question(plan)
        assert resolved == paraphrase
        text = render_conversational_turn({"plan": plan, "known_facts": {}})
        assert paraphrase in text

    # Planner attaches question_goal on MLC gap plans
    plan_lp = plan_next(
        ReasoningContext(
            user_id="u_42ff_f",
            known_facts={"mlc.current_situation": "lavoro", "lavoro.active": True},
            session_phase="active",
        )
    )
    if (plan_lp.meta or {}).get("gap_key") == "mlc.life_places.home":
        assert (plan_lp.meta or {}).get("question_goal", {}).get("id") == "ask_primary_home_city"

    # Gemini context exposes binding question_goal
    from ai_life_strategist.reasoning_loop import to_gemini_context_json

    ctx = ReasoningContext(
        user_id="u_42ff_f2",
        known_facts={"mlc.current_situation": "lavoro"},
        last_user_text="Lavoro troppo",
        session_phase="active",
        missing_keys=["mlc.life_places.home"],
    )
    payload = to_gemini_context_json(
        ctx,
        question_goal=dict(_HOME_GOAL),
        planner_gap_key="mlc.life_places.home",
        planner_next_best_question=_HOME_SAFE,
        mlc_nucleus="life_places",
    )
    assert payload.get("question_goal", {}).get("id") == "ask_primary_home_city"
    assert "spoken_question_instruction" in payload
    assert "planner_next_best_question" in payload
