"""
Conversational voice helpers for Life Experience (Sprint 4 / 4.1 / 4.2).

Sprint 4.2 Architecture A:
- Gemini may supply acknowledgement / spoken_question / conversational_bridge
  in the SAME StrategistPlan call; render_conversational_turn validates then falls back.
- DETERMINISTIC: MLC, gaps, gate, facts, greeting shell, actions/UI, SAFE fallbacks.
- AI: Quiet Premium Italian ack+ask (+ optional wrap synthesis). Never invent facts.
- CRITICAL: never glue free-text priority into "lavori come {x}".
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

logger = logging.getLogger("ora.ai_life_strategist.conversational_voice")

INTERNAL_JARGON_FRAGMENTS = (
    "mlc",
    "coverage",
    "life graph",
    "lifegraph",
    "minimum life",
    "strategist",
    "planner",
    "gap key",
    "gap_key",
    "nucleo",
    "nucleus",
)

_BROKEN_LAVORI_COME = re.compile(
    r"lavori\s+come\s+(?:mi\s+|il\s+mio|la\s+mia|i\s+miei|le\s+mie|"
    r"troppo|vorrei|voglio|organizz|passare|avere|bilanciar)",
    re.IGNORECASE,
)

# Judgment / lecturing markers — reject or sanitize in acknowledgements
_JUDGMENT_WORD_RE = re.compile(
    r"\b(giustamente|ovviamente|correttamente|logicamente|naturalmente)\b",
    re.IGNORECASE,
)

# life_places.home: must ask where they LIVE; reject workplace / day-spend / GPS drift
_LIFE_HOME_LIVE_MARKERS = (
    "vivi",
    "abiti",
    "abitazione",
    "residenza",
    "città di residenza",
    "citta di residenza",
    "dove vivi",
    "vivi principalmente",
    "abiti principalmente",
)
_LIFE_HOME_DRIFT_MARKERS = (
    "gestire la giornata",
    "gestisci la giornata",
    "gestire le giornate",
    "passi la giornata",
    "trascorri la giornata",
    "passi le giornate",
    "dove lavori",
    "posto di lavoro",
    "luogo di lavoro",
    "sede di lavoro",
    "dove studi",
    "luogo di studio",
    "posizione gps",
    "posizione attuale",
    "dove ti trovi ora",
    "dove ti trovi adesso",
    "dove ti trovi principalmente",
    "dove ti trovi a gestire",
)


def _s(facts: Dict[str, Any], *keys: str) -> Optional[str]:
    for k in keys:
        v = facts.get(k)
        if v is None or v is False or v == "" or v == []:
            continue
        if isinstance(v, bool):
            continue
        text = str(v).strip()
        if text and text.lower() not in {"true", "false", "1", "0"}:
            return text
    return None


class PriorityRender(NamedTuple):
    """ORA-facing priority copy. ``fragment`` embeds after 'ti preme soprattutto'."""

    text: str
    mode: str = "fragment"  # "fragment" | "sentence"


# User first-person possessives / reflexives that must not leak into ORA voice.
_USER_POSSESSIVE_NP = re.compile(
    r"\b(?:"
    r"il\s+mio|la\s+mia|lo\s+mio|i\s+miei|le\s+mie|"
    r"un\s+mio|una\s+mia|"
    r"del\s+mio|della\s+mia|dei\s+miei|delle\s+mie|"
    r"al\s+mio|alla\s+mia|col\s+mio|con\s+la\s+mia|con\s+i\s+miei|con\s+le\s+mie"
    r")\b",
    re.IGNORECASE,
)
_USER_BARE_POSSESSIVE = re.compile(r"\b(?:mio|mia|miei|mie)\b", re.IGNORECASE)
_USER_REFLEXIVE_1P = re.compile(
    r"\b(?:organizzarmi|dedicarmi|concentrarmi|gestirmi|sistemarmi|muovermi)\b",
    re.IGNORECASE,
)


def _strip_priority_shell(raw: str) -> str:
    t = (raw or "").strip().strip(" \"'«»")
    if not t:
        return ""
    t = re.sub(
        r"^(?:vorrei|voglio|vorremmo|mi\s+piacerebbe|preferirei|desidero)\s+",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()
    t = re.sub(r"^io\s+", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(
        r"^(?:riuscire\s+a|poter|di)\s+",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()
    return t


def _lc_start(t: str) -> str:
    if not t:
        return t
    return t[0].lower() + t[1:] if t[0].isupper() and not t.isupper() else t


def _has_user_perspective_leak(t: str) -> bool:
    """True if text still carries USER first-person possessives/reflexives."""
    if not t:
        return False
    if _USER_POSSESSIVE_NP.search(t) or _USER_BARE_POSSESSIVE.search(t):
        return True
    if _USER_REFLEXIVE_1P.search(t):
        return True
    # "mi + finite verb" as user experience (mi prende / mi stressa), not ORA "mi preme"
    if re.search(r"\bmi\s+(?!preme\b|manca\b)\w+", t, flags=re.IGNORECASE):
        return True
    return False


def _semantic_priority_pattern(raw: str) -> Optional[PriorityRender]:
    """
    Pattern-based Italian paraphrases for common life priorities.
    Preserves meaning; emits ORA second-person / neutral fragments.
    """
    low = (raw or "").lower()

    # Studio ↔ tempo libero / balance
    has_free = bool(re.search(r"tempo\s+libero", low))
    has_study = bool(re.search(r"\b(?:studio|studiare|studi|universit)", low))
    if has_free and has_study:
        if re.search(r"concili", low):
            return PriorityRender(
                "conciliare meglio lo studio con il tuo tempo libero",
                "fragment",
            )
        return PriorityRender(
            "trovare un equilibrio migliore tra studio e tempo libero",
            "fragment",
        )
    if has_free and re.search(r"organizz", low) and not has_study:
        return PriorityRender("organizzare meglio il tempo libero", "fragment")

    # Famiglia
    if re.search(r"\bfamigli", low):
        if re.search(r"(?:passare|pi[uù]\s+tempo|tempo\s+con|stare\s+con)", low):
            return PriorityRender("passare più tempo con la tua famiglia", "fragment")
        return PriorityRender("avere più tempo per la famiglia", "fragment")

    # Lavoro + tempo pressure
    if re.search(r"\blavoro\b", low) and re.search(r"\btempo\b", low):
        if re.search(r"(?:prende|rub|tropp|mangia|occup)", low):
            return PriorityRender("avere più tempo oltre al lavoro", "fragment")
        return PriorityRender("bilanciare meglio lavoro e tempo", "fragment")

    # Esami / organizzazione studio
    if re.search(r"\besami?\b", low):
        if re.search(r"organizz", low):
            return PriorityRender("organizzare meglio gli esami", "fragment")
        return PriorityRender("gestire meglio gli esami", "fragment")

    return None


def _perspective_rewrite_clause(t: str) -> str:
    """
    Careful USER→ORA rewrite for noun phrases / reflexives.
    Not a blind mio→tuo pass: longer, meaning-preserving phrases first.
    """
    out = t
    ordered = (
        (r"\bil\s+mio\s+tempo\s+libero\b", "il tuo tempo libero"),
        (r"\bla\s+mia\s+famiglia\b", "la tua famiglia"),
        (r"\bil\s+mio\s+lavoro\b", "il lavoro"),
        (r"\bi\s+miei\s+esami\b", "gli esami"),
        (r"\ble\s+mie\s+scadenze\b", "le scadenze"),
        (r"\bi\s+miei\s+impegni\b", "gli impegni"),
        (r"\bi\s+miei\s+progetti\b", "i progetti"),
        (r"\bcon\s+la\s+mia\s+", "con la tua "),
        (r"\bcon\s+i\s+miei\s+", "con i tuoi "),
        (r"\bcon\s+le\s+mie\s+", "con le tue "),
        (r"\bdel\s+mio\s+", "del tuo "),
        (r"\bdella\s+mia\s+", "della tua "),
        (r"\bdei\s+miei\s+", "dei tuoi "),
        (r"\bdelle\s+mie\s+", "delle tue "),
        (r"\bal\s+mio\s+", "al tuo "),
        (r"\balla\s+mia\s+", "alla tua "),
        (r"\bil\s+mio\s+", "il tuo "),
        (r"\bla\s+mia\s+", "la tua "),
        (r"\blo\s+mio\s+", "il tuo "),
        (r"\bi\s+miei\s+", "i tuoi "),
        (r"\ble\s+mie\s+", "le tue "),
        (r"\bun\s+mio\s+", "un tuo "),
        (r"\buna\s+mia\s+", "una tua "),
        (r"\borganizzarmi\b", "organizzarti"),
        (r"\bdedicarmi\b", "dedicarti"),
        (r"\bconcentrarmi\b", "concentrarti"),
        (r"\bgestirmi\b", "gestirti"),
        (r"\bsistemarmi\b", "sistemarti"),
        (r"\bmi\s+prende\b", "ti prende"),
        (r"\bmi\s+sta\b", "ti sta"),
        (r"\bmi\s+lascia\b", "ti lascia"),
    )
    for pat, repl in ordered:
        out = re.sub(pat, repl, out, flags=re.IGNORECASE)
    # Residual bare possessives only inside leftover first-person residue
    if _USER_BARE_POSSESSIVE.search(out):
        out = re.sub(r"\bmio\b", "tuo", out, flags=re.IGNORECASE)
        out = re.sub(r"\bmia\b", "tua", out, flags=re.IGNORECASE)
        out = re.sub(r"\bmiei\b", "tuoi", out, flags=re.IGNORECASE)
        out = re.sub(r"\bmie\b", "tue", out, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", out).strip()


def _looks_like_finite_statement(t: str) -> bool:
    """Heuristic: finite clause that fits poorly after 'ti preme soprattutto'."""
    low = t.lower()
    if re.search(r"\b(?:ti|mi)\s+\w+", low) and re.search(
        r"\b(?:prende|prendeva|sta|lascia|stressa|pesa)\b", low
    ):
        return True
    if re.match(r"^(?:il|la|lo|i|le)\s+\w+", low) and re.search(
        r"\b(?:è|sono|ho|hai|prende|occupa)\b", low
    ):
        return True
    return False


def render_priority_for_ora(raw: str) -> Optional[PriorityRender]:
    """
    Render-time USER→ORA perspective for free-text priority.

    Does not mutate stored facts. Prefer semantic paraphrase; otherwise rewrite
    possessives carefully. Returns a fragment for 'ti preme soprattutto …'
    or a standalone sentence when that frame would invert perspective.
    """
    original = (raw or "").strip()
    if not original:
        return None

    semantic = _semantic_priority_pattern(original)
    if semantic:
        return semantic

    t = _strip_priority_shell(original)
    if not t:
        return None

    rewritten = _perspective_rewrite_clause(t)
    rewritten = _lc_start(rewritten)

    if len(rewritten) > 100:
        rewritten = rewritten[:97].rsplit(" ", 1)[0] + "…"

    if not rewritten:
        return None

    # Still first-person-heavy → full sentence (avoid 'ti preme soprattutto {user voice}')
    if _has_user_perspective_leak(rewritten):
        core = _perspective_rewrite_clause(_strip_priority_shell(original))
        core = _lc_start(core)
        if not core:
            return None
        if re.match(
            r"^(?:organizzar|passar|aver|gestir|trovar|bilanciar|conciliar|dedicar)",
            core,
            flags=re.IGNORECASE,
        ):
            return PriorityRender(f"Vorresti riuscire a {core}.", "sentence")
        core_inf = re.sub(r"^(?:il|la|lo|i|le)\s+", "", core, flags=re.IGNORECASE)
        return PriorityRender(f"Vorresti riuscire a gestire meglio {core_inf}.", "sentence")

    # Finite statement fits poorly after 'ti preme soprattutto' → standalone
    if _looks_like_finite_statement(rewritten):
        sent = rewritten[0].upper() + rewritten[1:] if rewritten else rewritten
        return PriorityRender(sent.rstrip(".") + ".", "sentence")

    return PriorityRender(rewritten, "fragment")


def _paraphrase_priority(raw: str) -> Optional[str]:
    """Backward-compatible fragment-only helper; prefer ``render_priority_for_ora``."""
    rendered = render_priority_for_ora(raw)
    if not rendered:
        return None
    return rendered.text.rstrip(".") if rendered.mode == "sentence" else rendered.text


def looks_like_role_title(role: Optional[str]) -> bool:
    """
    True only for short structured occupation/role titles suitable for
    'lavori come {role}'. NEVER free-text priority / responsibility sentences.
    """
    if not role:
        return False
    r = str(role).strip().strip(" \"'«»")
    if not r:
        return False
    if len(r) > 48 or len(r.split()) > 6:
        return False
    if re.search(r"[.!?]", r):
        return False
    low = r.lower()
    if low in {"lavoro", "casa", "affitto", "studio", "università", "universita"}:
        return False
    # Priority / life-sentence markers — never "lavori come mi prende…"
    if re.search(
        r"\b(?:"
        r"mi\s+prende|troppo\s+tempo|tempo\s+libero|famigli|"
        r"vorrei|voglio|desidero|preferirei|"
        r"organizz(?:are|armi)|passare\s+pi[uù]|avere\s+pi[uù]|"
        r"bilanciare|conciliare|gestire\s+meglio|"
        r"prende|occupa|stressa|pesa|rub"
        r")\b",
        low,
    ):
        return False
    if _has_user_perspective_leak(r):
        return False
    # Verb-led clauses are not role titles
    if re.match(
        r"^(?:il|la|lo|i|le|un|una|mi|ti|vorrei|voglio)\b",
        low,
    ) and re.search(r"\b(?:prende|tempo|famigli|esami?)\b", low):
        return False
    return True


def structured_work_role(facts: Dict[str, Any]) -> Optional[str]:
    """Only ``lavoro.ruolo`` when it looks like a short role title — never responsibilities/priority."""
    role = _s(facts, "lavoro.ruolo")
    if role and looks_like_role_title(role):
        return role
    return None


def _work_phrase(role: Optional[str]) -> Optional[str]:
    """Natural work phrasing — avoid 'lavori come nella Guardia…' and never sentence glue."""
    if not role or not looks_like_role_title(role):
        return "il lavoro occupa una parte importante delle tue giornate"
    r = role.strip()
    low = r.lower()
    # Already a prepositional / institutional phrase
    if low.startswith(("nella ", "nel ", "in ", "presso ", "alla ", "al ", "come ")):
        return f"lavori {r}"
    # Org-like names (Guardia di Finanza, Comune, …) → "nella/presso"
    if re.search(r"\b(guardia|finanza|polizia|comune|ministero|agenzia|forze)\b", low):
        if low.startswith("la "):
            return f"lavori in {r}"
        return f"lavori nella {r}" if not low.startswith("nella ") else f"lavori {r}"
    return f"lavori come {r}"


def _situation_elements(facts: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (situation_phrase, role_detail) without binding city into the phrase.
    City must stay an independent element in synthesis.

    Role for work phrasing: structured ``lavoro.ruolo`` title only — never
    ``mlc.responsibilities`` or free-text priority sentences.
    """
    sit = _s(facts, "mlc.current_situation")
    role = structured_work_role(facts)
    study = _s(facts, "studio.universita", "studio.esame")
    # responsibilities only as study detail when short and not a life/priority sentence
    resp = _s(facts, "mlc.responsibilities")
    if (
        not study
        and resp
        and len(resp) < 48
        and not re.search(
            r"\b(?:tempo|famigli|vorrei|voglio|prende|organizz|mi\s+)\b",
            resp.lower(),
        )
        and (facts.get("studio.active") or sit == "studio")
    ):
        study = resp

    if sit == "lavoro_studio":
        return "in questo periodo lavori e studi", None
    if sit == "lavoro":
        return _work_phrase(role), None
    if sit == "studio":
        if study and study.lower() not in {"studio", "università", "universita"}:
            if facts.get("studio.active") or "universit" in (study or "").lower() or len(study) < 48:
                return "lo studio occupa una parte importante delle tue giornate", study
        return "lo studio occupa una parte importante delle tue giornate", None
    if facts.get("studio.active") and not facts.get("lavoro.active"):
        return "lo studio è centrale in questo periodo", None
    if facts.get("lavoro.active") or structured_work_role(facts):
        return _work_phrase(role), None
    return None, None


def _situation_phrase(facts: Dict[str, Any]) -> Optional[str]:
    sit, _ = _situation_elements(facts)
    return sit


def build_acknowledgement(
    *,
    last_user_text: Optional[str],
    known_facts: Dict[str, Any],
    previous_ack: Optional[str] = None,
) -> Optional[str]:
    """Short natural ack from real facts. None if nothing solid to acknowledge."""
    if not (last_user_text or "").strip():
        return None
    facts = known_facts or {}
    bits: List[str] = []

    name = _s(facts, "mlc.identity.name", "identity.preferred_name", "identity.name")
    city = _s(facts, "mlc.life_places.home", "casa.citta")
    situation = _situation_phrase(facts)
    priority_raw = _s(facts, "mlc.immediate_priority")
    priority = render_priority_for_ora(priority_raw) if priority_raw else None

    # Thin knowledge (e.g. only name + studio): light, fact-grounded ack — never "quadro chiaro"
    if situation and city:
        bits.append(f"quindi in questo periodo {situation}, e vivi a {city}")
    elif situation:
        bits.append(f"quindi in questo periodo {situation}")
    elif city:
        bits.append(f"quindi il tuo contesto è legato a {city}")
    elif name:
        bits.append(f"{name}")

    if priority and not situation:
        if priority.mode == "sentence":
            bits.append(_lc_start(priority.text.rstrip(".")))
        else:
            bits.append(f"la cosa che ti preme di più ora è {priority.text}")

    if not bits:
        t = last_user_text.strip()
        if len(t) < 12:
            return None
        return "Capito."

    core = bits[0]
    if core == name:
        ack = f"Piacere, {name}."
    elif core.startswith("quindi"):
        ack = f"Capito, {core}."
    else:
        ack = f"Capito — {core}."

    if previous_ack and previous_ack.strip().lower() == ack.strip().lower():
        return None
    if last_user_text and ack.lower() in last_user_text.lower():
        return None
    return ack


def synthesize_first_picture(known_facts: Dict[str, Any]) -> str:
    """
    True paraphrase wrap: preferred name when natural, 2–4 independent elements,
    paraphrased priority, no invented relations, no double periods.
    """
    facts = known_facts or {}
    name = _s(facts, "mlc.identity.name", "identity.preferred_name", "identity.name")
    city = _s(facts, "mlc.life_places.home", "casa.citta")
    situation, study_detail = _situation_elements(facts)
    priority = render_priority_for_ora(_s(facts, "mlc.immediate_priority") or "")
    role = structured_work_role(facts)
    resp = _s(facts, "mlc.responsibilities")

    elements: List[str] = []

    # Situation (work/study) — never glue city into the same clause unless related
    if situation:
        elements.append(situation[0].upper() + situation[1:] if situation else situation)
    elif facts.get("studio.active"):
        elements.append("Lo studio è centrale in questo periodo")
    elif facts.get("lavoro.active"):
        elements.append("Il lavoro è centrale in questo periodo")

    # Study detail only if distinct and not already implied by situation/role
    if study_detail and situation and "studio" in situation.lower():
        sd = study_detail.strip()
        if sd.lower() not in situation.lower() and (not role or sd.lower() != role.lower()):
            if sd.lower() not in {"studio", "università", "universita"}:
                elements.append(f"ti stai dedicando a {sd}")

    # Work role if situation didn't already include it (structured title only)
    if role and situation and "lavor" in situation.lower():
        if role.lower() not in situation.lower():
            wp = _work_phrase(role)
            if wp and wp.lower() not in " ".join(elements).lower():
                if elements and "lavoro occupa" in elements[0].lower():
                    elements[0] = wp[0].upper() + wp[1:]
                elif wp.lower() not in " ".join(e.lower() for e in elements):
                    elements.append(wp)

    # Responsibilities only when short structured label — never priority sentences
    if (
        resp
        and looks_like_role_title(resp)
        and resp.lower() not in " ".join(elements).lower()
        and (not role or resp.lower() != role.lower())
        and resp.lower() not in {"lavoro", "studio", "casa"}
    ):
        elements.append(f"tra i tuoi impegni c’è {resp}")

    # City — always its own element (no "studi a Tarquinia" implication)
    if city:
        elements.append(f"vivi principalmente a {city}")

    # Priority — ORA-perspective render (never raw user first-person)
    if priority:
        if priority.mode == "sentence":
            elements.append(priority.text.rstrip("."))
        else:
            elements.append(f"ti preme soprattutto {priority.text}")

    # Cap at 4 significant elements (situation/city/priority/role-ish)
    elements = elements[:4]

    if name:
        opener = f"Perfetto, {name}. Adesso ho un primo quadro."
    else:
        opener = "Perfetto. Adesso ho un primo quadro."

    def _sent(e: str) -> str:
        t = e.strip().rstrip(".")
        if not t:
            return ""
        return (t[0].upper() + t[1:] if t[0].islower() else t) + "."

    if not elements:
        body = "Ho abbastanza contesto su come sono organizzate le tue giornate."
    else:
        # Independent short sentences — clearer than one run-on; no invented joins
        body = " ".join(s for s in (_sent(e) for e in elements) if s)

    closer = "È abbastanza per iniziare. Continueremo a conoscerci mentre userai ORA."

    text = f"{opener} {body} {closer}"
    # Normalize double periods / spacing
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def near_mlc_bridge(
    *,
    covered_count: int,
    missing: List[str],
    sufficient: bool,
    known_facts: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Soft progress only when context is truly near-complete.
    Never claim 'quadro chiaro' on thin knowledge (e.g. name + studio only).
    Prefer None so fact-grounded ack can carry the turn.
    """
    if sufficient:
        return None
    facts = known_facts or {}
    # Substantial signals beyond bare nuclei count
    rich = 0
    if _s(facts, "mlc.life_places.home", "casa.citta"):
        rich += 1
    if _s(facts, "lavoro.ruolo") or facts.get("lavoro.active"):
        rich += 1
    if _s(facts, "studio.universita", "studio.esame") or facts.get("studio.active"):
        rich += 1
    if _s(facts, "mlc.immediate_priority"):
        rich += 1
    if _s(facts, "mlc.responsibilities") and _s(facts, "mlc.current_situation"):
        rich += 1

    missing_n = len(missing or [])
    # Only one nucleus left AND we already have some concrete detail
    if covered_count >= 4 and missing_n == 1 and rich >= 2:
        return "Mi manca solo una cosa per capire da dove possiamo iniziare."
    # covered>=3 alone is NOT enough — avoid false "quadro chiaro"
    if covered_count >= 4 and missing_n <= 2 and rich >= 3:
        return "Sto mettendo insieme i pezzi che contano."
    return None


def location_confirm_prompt(city: str) -> str:
    city = (city or "").strip()
    return f"Sembra che tu sia a {city}. È qui che vivi principalmente?"


# ---------------------------------------------------------------------------
# Sprint 4.2 — AI render validation + SAFE deterministic fallbacks
# ---------------------------------------------------------------------------


def _collect_allowed_fact_values(known_facts: Optional[Dict[str, Any]]) -> List[str]:
    facts = known_facts or {}
    keys = (
        "mlc.identity.name",
        "identity.preferred_name",
        "identity.name",
        "mlc.life_places.home",
        "casa.citta",
        "lavoro.ruolo",
        "studio.universita",
        "studio.esame",
        "mlc.current_situation",
    )
    out: List[str] = []
    for k in keys:
        v = facts.get(k)
        if v is None or v is False or v == "" or v == []:
            continue
        text = str(v).strip()
        if text and text.lower() not in {"true", "false", "1", "0", "lavoro", "studio"}:
            out.append(text)
    return out


def validate_rendered_text(
    text: Optional[str],
    *,
    allowed_fact_values: Optional[List[str]] = None,
    kind: str = "turn",
) -> Optional[str]:
    """
    Accept user-facing Italian copy or return None.

    Checks: empty, length, jargon, JSON smell, broken 'lavori come' glue,
    user-perspective leak, light hallucination vs known fact values.
    """
    t = (text or "").strip()
    if not t:
        return None
    if len(t) > 700:
        return None
    if kind == "ack" and len(t) > 280:
        return None
    if kind == "question" and len(t) > 320:
        return None

    low = t.lower()
    for j in INTERNAL_JARGON_FRAGMENTS:
        if j in low:
            return None
    if t.lstrip().startswith(("{", "[")) or '"next_best_question"' in t:
        return None
    if "```" in t:
        return None
    if _BROKEN_LAVORI_COME.search(t):
        return None
    # Any 'lavori come' followed by a long/sentence-like fragment
    m = re.search(r"lavori\s+come\s+(.+?)(?:[.!?]|$)", t, flags=re.IGNORECASE)
    if m and not looks_like_role_title(m.group(1).strip().rstrip(".,;")):
        return None

    # Perspective: ORA voice must not echo USER first-person possessives
    if kind in ("turn", "ack", "bridge", "wrap") and _has_user_perspective_leak(t):
        return None

    # Light hallucination: invented "lavori a {City}" / "studi a {City}" relation
    # only when city is known but no structured work/study-in-city fact exists
    allowed = [a.lower() for a in (allowed_fact_values or [])]
    city_hit = re.search(
        r"\b(?:lavori|lavori\s+come|studi|studiando)\s+a\s+([A-ZÀ-Ú][\w'à-ú-]+)",
        t,
        flags=re.IGNORECASE,
    )
    if city_hit:
        city = city_hit.group(1).strip()
        # Allow only if city is among known values (still no invented workplace link
        # beyond mentioning the known city — reject "lavori a X" form entirely unless
        # structured role implies institutional phrasing without city glue)
        if re.search(r"\blavori\s+a\s+", low) and city.lower() in allowed:
            # Prefer not inventing workplace-in-city; reject this pattern
            return None
        if city.lower() not in allowed and len(city) > 2:
            return None

    return t


def _gap_meta_from_plan(plan: Any) -> Tuple[Optional[str], Optional[str], Optional[Dict[str, Any]]]:
    if plan is None:
        return None, None, None
    meta = plan.get("meta") if isinstance(plan, dict) else getattr(plan, "meta", None)
    meta = meta or {}
    gap_key = str(meta.get("gap_key") or "") or None
    nucleus = str(meta.get("mlc_nucleus") or "") or None
    goal = meta.get("question_goal")
    if isinstance(goal, dict):
        return gap_key, nucleus, goal
    return gap_key, nucleus, None


def _is_life_places_home_gap(
    gap_key: Optional[str],
    nucleus: Optional[str],
    question_goal: Optional[Dict[str, Any]],
) -> bool:
    if question_goal and question_goal.get("id") == "ask_primary_home_city":
        return True
    gk = (gap_key or "").strip()
    if gk in {"mlc.life_places.home", "mlc.life_places"} or gk.startswith("mlc.life_places"):
        return True
    return (nucleus or "") == "life_places"


def validate_spoken_question_for_goal(
    text: Optional[str],
    *,
    question_goal: Optional[Dict[str, Any]] = None,
    gap_key: Optional[str] = None,
    mlc_nucleus: Optional[str] = None,
) -> Optional[str]:
    """
    Lightweight semantic check (no second LLM).

    For life_places.home: reject workplace / spend-the-day / GPS drift that does
    not ask where the user LIVES. Other MLC goals: accept clear on-intent paraphrases;
    do not false-reject good questions.
    """
    t = (text or "").strip()
    if not t:
        return None
    low = t.lower()

    if _is_life_places_home_gap(gap_key, mlc_nucleus, question_goal):
        has_live = any(m in low for m in _LIFE_HOME_LIVE_MARKERS)
        has_drift = any(m in low for m in _LIFE_HOME_DRIFT_MARKERS)
        # Explicit workplace / day-management / GPS without live → reject
        if has_drift and not has_live:
            return None
        if has_live:
            return t
        # Soft accept: city ask without work/day drift (e.g. "In che città?")
        if ("città" in low or "citta" in low) and not has_drift:
            return t
        # Unclear / drifted → reject so caller falls back to deterministic SAFE question
        return None

    goal_id = (question_goal or {}).get("id") if question_goal else None
    # Light positive checks — accept good paraphrases; avoid false rejects
    if goal_id == "ask_preferred_name" or gap_key == "mlc.identity.name" or mlc_nucleus == "identity":
        if any(x in low for x in ("chiami", "chiamarti", "nome", "come ti")):
            return t
        return t  # do not false-reject mild paraphrases
    if (
        goal_id == "ask_current_situation"
        or gap_key == "mlc.current_situation"
        or mlc_nucleus == "current_situation"
    ):
        if any(x in low for x in ("lavor", "stud", "periodo", "giornate", "entrambe")):
            return t
        return t
    if (
        goal_id == "ask_immediate_priority"
        or gap_key == "mlc.immediate_priority"
        or mlc_nucleus == "immediate_priority"
    ):
        if any(x in low for x in ("gestire", "meglio", "preme", "priorit", "adesso", "vorresti")):
            return t
        return t
    if (
        goal_id == "ask_main_responsibilities"
        or gap_key == "mlc.responsibilities"
        or mlc_nucleus == "responsibilities"
    ):
        if any(x in low for x in ("impegni", "occupano", "cosa stai", "studiando", "ruolo")):
            return t
        return t

    return t


def sanitize_acknowledgement(text: Optional[str]) -> Optional[str]:
    """Drop judgment words or fall back to Capito. / None; keep question path intact."""
    t = (text or "").strip()
    if not t:
        return None
    if not _JUDGMENT_WORD_RE.search(t):
        return t
    cleaned = _JUDGMENT_WORD_RE.sub("", t)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.!?;:])", r"\1", cleaned)
    cleaned = re.sub(r"^[,\s.—–-]+", "", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned and len(cleaned) >= 8 and validate_rendered_text(cleaned, kind="ack"):
        # Avoid awkward leftovers like "Capito — ." after stripping
        if re.match(r"^capito\s*[—\-–,.]?\s*$", cleaned, flags=re.IGNORECASE):
            return "Capito."
        return cleaned
    return "Capito."


def resolve_turn_question(
    plan: Any,
    *,
    allowed_fact_values: Optional[List[str]] = None,
) -> Optional[str]:
    """Validated spoken_question matching question_goal, else deterministic next_best_question."""
    from ai_life_strategist.minimum_life_context import safe_question_for_gap

    gap_key, nucleus, goal = _gap_meta_from_plan(plan)
    raw_spoken = _plan_field(plan, "spoken_question")
    gem_q = validate_rendered_text(
        raw_spoken, allowed_fact_values=allowed_fact_values, kind="question"
    )
    gem_q = validate_spoken_question_for_goal(
        gem_q, question_goal=goal, gap_key=gap_key, mlc_nucleus=nucleus
    )
    if gem_q:
        return gem_q
    if isinstance(plan, dict):
        nbq = (plan.get("next_best_question") or "").strip() or None
    elif plan is not None:
        nbq = (getattr(plan, "next_best_question", None) or "").strip() or None
    else:
        nbq = None
    if nbq:
        return nbq
    return safe_question_for_gap(gap_key, nucleus)



def safe_active_turn_fallback(
    *,
    question: Optional[str],
    acknowledgement: Optional[str] = None,
    bridge: Optional[str] = None,
) -> str:
    """Minimal correct Italian ack+ask — no smart occupation/priority glue."""
    parts: List[str] = []
    ack = (acknowledgement or "").strip()
    br = (bridge or "").strip()
    q = (question or "").strip()
    if ack:
        # Strip any broken lavori-come residue from upstream
        if validate_rendered_text(ack, kind="ack"):
            parts.append(ack)
        else:
            parts.append("Capito.")
    elif br and validate_rendered_text(br, kind="bridge"):
        parts.append(br)
    if q:
        parts.append(q)
    text = " ".join(parts).strip()
    return text or (q or "Puoi raccontarmi un altro pezzo della tua situazione?")


def safe_wrap_fallback(known_facts: Optional[Dict[str, Any]] = None) -> str:
    """Short generic wrap — never concatenates raw priority into 'lavori come'."""
    facts = known_facts or {}
    name = _s(facts, "mlc.identity.name", "identity.preferred_name", "identity.name")
    city = _s(facts, "mlc.life_places.home", "casa.citta")
    opener = f"Perfetto, {name}. Adesso ho un primo quadro." if name else "Perfetto. Adesso ho un primo quadro."
    bits: List[str] = []
    sit = _s(facts, "mlc.current_situation")
    if sit == "lavoro_studio" or (facts.get("lavoro.active") and facts.get("studio.active")):
        bits.append("In questo periodo lavori e studi.")
    elif sit == "studio" or (facts.get("studio.active") and not facts.get("lavoro.active")):
        bits.append("Lo studio conta in questo periodo.")
    elif sit == "lavoro" or facts.get("lavoro.active") or structured_work_role(facts):
        bits.append("Il lavoro conta nelle tue giornate.")
    if city:
        bits.append(f"Vivi principalmente a {city}.")
    if _s(facts, "mlc.immediate_priority"):
        bits.append("Ho capito cosa ti preme di più adesso.")
    body = " ".join(bits) if bits else "Ho abbastanza contesto su come sono organizzate le tue giornate."
    closer = "È abbastanza per iniziare. Continueremo a conoscerci mentre userai ORA."
    text = f"{opener} {body} {closer}"
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _plan_field(plan: Any, name: str) -> Optional[str]:
    if plan is None:
        return None
    if isinstance(plan, dict):
        v = plan.get(name)
    else:
        v = getattr(plan, name, None)
        if v is None and name == "conversational_bridge":
            meta = getattr(plan, "meta", None) or {}
            v = meta.get("conversational_bridge")
    if v is None and isinstance(plan, dict):
        meta = plan.get("meta") or {}
        if name == "conversational_bridge":
            v = meta.get("conversational_bridge")
    if v is None:
        return None
    text = str(v).strip()
    return text or None


def render_conversational_turn(context: Dict[str, Any]) -> str:
    """
    Assemble ORA bubble text from Gemini spoken fields when valid; else SAFE fallback.

    context:
      plan — StrategistPlan or dict (acknowledgement, spoken_question, conversational_bridge,
             next_best_question)
      ack — optional session override (refusals / system acks win when Gemini ack missing)
      last_bridge — de-dupe soft progress
      known_facts — for validation
    """
    plan = context.get("plan")
    ack_override = (context.get("ack") or None)
    if isinstance(ack_override, str):
        ack_override = ack_override.strip() or None
    last_bridge = context.get("last_bridge")
    known_facts = context.get("known_facts") or {}
    allowed = _collect_allowed_fact_values(known_facts)

    gem_ack = validate_rendered_text(
        _plan_field(plan, "acknowledgement"),
        allowed_fact_values=allowed,
        kind="ack",
    )
    # Judgment words → sanitize (drop) or Capito.; keep question
    gem_ack = sanitize_acknowledgement(gem_ack)
    gem_bridge = validate_rendered_text(
        _plan_field(plan, "conversational_bridge"),
        allowed_fact_values=allowed,
        kind="bridge",
    )

    # Never combine ack + bridge (Architecture A). Prefer validated Gemini ack.
    ack = gem_ack or (
        sanitize_acknowledgement(
            validate_rendered_text(ack_override, allowed_fact_values=allowed, kind="ack")
        )
        if ack_override
        else None
    )
    # System/refusal acks may fail perspective/jargon checks — keep short safe overrides
    # (skip/refuse/doc/location). Do NOT use rich build_acknowledgement as default override.
    if not ack and ack_override and len(ack_override) < 160:
        low = ack_override.lower()
        if any(
            low.startswith(p)
            for p in (
                "ok,",
                "ok ",
                "va bene",
                "ho ricevuto",
                "ho letto",
                "hai comprato",
                "nessun problema",
                "capito",
            )
        ):
            ack = sanitize_acknowledgement(ack_override) or "Capito."

    bridge = None
    if not ack and gem_bridge:
        if last_bridge and gem_bridge.strip() == str(last_bridge).strip():
            bridge = None
        else:
            bridge = gem_bridge
    elif not ack and not gem_bridge:
        # Deterministic bridge from plan.meta
        meta_bridge = _plan_field(plan, "conversational_bridge")
        if meta_bridge and (not last_bridge or meta_bridge.strip() != str(last_bridge).strip()):
            bridge = validate_rendered_text(meta_bridge, allowed_fact_values=allowed, kind="bridge")

    # spoken_question must match question_goal; else deterministic next_best_question / SAFE
    question = resolve_turn_question(plan, allowed_fact_values=allowed)
    if isinstance(plan, dict):
        nbq = (plan.get("next_best_question") or "").strip() or None
    elif plan is not None:
        nbq = (getattr(plan, "next_best_question", None) or "").strip() or None
    else:
        nbq = None

    # SAFE ack when Gemini ack/bridge missing: plain "Capito." — never rich situation-only phrases
    if not ack and not bridge and question:
        ack = "Capito."
    text = safe_active_turn_fallback(
        question=question,
        acknowledgement=ack,
        bridge=bridge if not ack else None,
    )
    validated = validate_rendered_text(text, allowed_fact_values=allowed, kind="turn")
    if validated:
        return validated
    return safe_active_turn_fallback(question=nbq or question, acknowledgement=None, bridge=None)


WRAP_SYNTHESIS_SYSTEM = """Sei ORA. Scrivi UNA breve sintesi finale in italiano Quiet Premium.
Usa SOLO i fatti strutturati forniti. Non inventare professione, città-lavoro o relazioni.
Mai termini MLC/coverage/Life Graph/strategist. Massimo 4 frasi corte + chiusura
«È abbastanza per iniziare. Continueremo a conoscerci mentre userai ORA.»
Rispondi SOLO con JSON: {"spoken_text": "..."}.
"""


async def render_wrap_synthesis(
    known_facts: Optional[Dict[str, Any]] = None,
    *,
    force_fallback: bool = False,
) -> str:
    """
    Optional ONE Gemini call at wrap with structured facts.

    - force_fallback / Gemini off → hardened synthesize_first_picture (SAFE if invalid)
    - Gemini attempted but failed/invalid → SAFE simple wrap (not broken concatenation)
    """
    facts = known_facts or {}
    allowed = _collect_allowed_fact_values(facts)

    def _deterministic() -> str:
        try:
            text = synthesize_first_picture(facts)
            ok = validate_rendered_text(text, allowed_fact_values=allowed, kind="wrap")
            if ok:
                return ok
        except Exception:
            pass
        return safe_wrap_fallback(facts)

    if force_fallback:
        return _deterministic()

    ai_attempted = False
    try:
        from llm.manager import ProviderManager

        payload = {
            "facts": {
                k: facts.get(k)
                for k in (
                    "mlc.identity.name",
                    "identity.preferred_name",
                    "mlc.life_places.home",
                    "casa.citta",
                    "mlc.current_situation",
                    "lavoro.ruolo",
                    "lavoro.active",
                    "studio.active",
                    "studio.universita",
                    "studio.esame",
                    "mlc.immediate_priority",
                )
                if facts.get(k) not in (None, "", [], False)
            },
            "rules": [
                "Solo fatti forniti",
                "Non inventare professione da priorità",
                "Città e lavoro/studio restano elementi separati",
                "Niente gergo interno",
            ],
        }
        if "lavoro.ruolo" in payload["facts"] and not looks_like_role_title(
            str(payload["facts"]["lavoro.ruolo"])
        ):
            payload["facts"].pop("lavoro.ruolo", None)

        ai_attempted = True
        mgr = ProviderManager()
        res = await mgr.chat(
            system=WRAP_SYNTHESIS_SYSTEM,
            user=json.dumps(payload, ensure_ascii=False, default=str),
            json_mode=True,
            user_preference="gemini",
        )
        raw = getattr(res, "text", None) if not isinstance(res, dict) else res.get("text")
        data = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(data, dict):
            spoken = validate_rendered_text(
                data.get("spoken_text") or data.get("text"),
                allowed_fact_values=allowed,
                kind="wrap",
            )
            if spoken:
                return spoken
    except Exception as e:
        logger.info("wrap synthesis AI skipped: %s", e)
        ai_attempted = True

    if ai_attempted:
        return safe_wrap_fallback(facts)
    return _deterministic()
