"""
Minimum Life Context (MLC) V1 — semantic coverage for first-launch Life Setup.

Version tag: **mlc-v1** (heuristic, not an irreversible domain law).

NOT a 5-question wizard. A nucleus is *addressed* when ORA already understands
it — not merely because a question was asked.

Addressed (mlc-v1) means one of:
  - covered   — positive evidence in known_facts
  - skipped   — user explicitly refused/postponed that nucleus
  - implicit  — not necessary / already resolved from rich surrounding context
  - (NOT) asked-only — `asked_keys` never marks a nucleus addressed

Wrap / ui.done only when MLC is *sufficient* under the V1 heuristic below —
not when DOMAIN_GAPS are exhausted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from ai_life_strategist.models import GapItem

MLC_VERSION = "mlc-v1"

NUCLEUS_IDS = (
    "identity",
    "current_situation",
    "life_places",
    "responsibilities",
    "immediate_priority",
)

# Keys that count as positive evidence for each nucleus (any one is enough).
NUCLEUS_EVIDENCE_KEYS: Dict[str, tuple[str, ...]] = {
    "identity": (
        "mlc.identity.name",
        "mlc.identity.preferred_name",
        "identity.name",
        "identity.preferred_name",
    ),
    "current_situation": (
        "mlc.current_situation",
        "lavoro.ruolo",
        "lavoro.active",
        "studio.active",
        "studio.universita",
    ),
    "life_places": (
        "mlc.life_places.home",
        "mlc.life_places.work",
        "mlc.life_places.study",
        "casa.citta",
        "casa.citta_residenza",
        "casa.indirizzo",
    ),
    "responsibilities": (
        "mlc.responsibilities",
        "lavoro.ruolo",
        "studio.active",
        "studio.esame",
        "studio.universita",
        "casa.owned",
        "casa.purchased",
        "casa.affitto",
        "famiglia.membri",
        "viaggi.destinazione",
    ),
    # Strong priority cues — imperfect phrasing still OK via soft keys
    "immediate_priority": (
        "mlc.immediate_priority",
        "studio.esame",
        "viaggi.destinazione",
        "mlc.immediate_priority_soft",
    ),
}

# Gap key used when asking about a missing nucleus (also used for refuse/skip).
NUCLEUS_GAP_KEY: Dict[str, str] = {
    "identity": "mlc.identity.name",
    "current_situation": "mlc.current_situation",
    "life_places": "mlc.life_places.home",
    "responsibilities": "mlc.responsibilities",
    "immediate_priority": "mlc.immediate_priority",
}

NUCLEUS_QUESTIONS: Dict[str, Dict[str, str]] = {
    "identity": {
        "label": "identità conversazionale",
        "question": "Come preferisci che ti chiami?",
        "benefit": "Mi aiuta a parlarti in modo naturale, non come a uno sconosciuto.",
        "domain": "servizi",
        "gain": "0.98",
    },
    "current_situation": {
        "label": "situazione attuale",
        "question": "In questo periodo lavori, studi, fai entrambe le cose, o qualcos’altro?",
        "benefit": "Mi aiuta a capire il ritmo delle tue giornate e a proporti cose realistiche.",
        "domain": "lavoro",
        "gain": "0.96",
    },
    "life_places": {
        "label": "luoghi di vita",
        "question": "Dove vivi principalmente in questo periodo? Basta la città.",
        "benefit": "Mi aiuta a collegare scadenze e priorità al posto in cui vivi davvero.",
        "domain": "casa",
        "gain": "0.9",
    },
    "responsibilities": {
        "label": "impegni concreti",
        "question": "Quali impegni ti occupano di più adesso?",
        "benefit": "Mi aiuta a capire su cosa posso alleggerirti davvero, senza liste da compilare.",
        "domain": "lavoro",
        "gain": "0.93",
    },
    "immediate_priority": {
        "label": "priorità immediata",
        "question": "C’è qualcosa che vorresti riuscire a gestire meglio proprio adesso?",
        "benefit": "Mi aiuta a capire da dove ha senso partire quando entri in ORA.",
        "domain": "servizi",
        "gain": "0.97",
    },
}

# Planner-owned semantic intent for AI wording (Sprint 4.2 Final Fix).
# Gemini may rephrase; must not change meaning or hit forbidden_interpretations.
QUESTION_GOALS: Dict[str, Dict[str, Any]] = {
    "mlc.life_places.home": {
        "id": "ask_primary_home_city",
        "meaning": "Ask which city the user primarily lives in during this period.",
        "required_semantics": ["primary residence / current living city"],
        "forbidden_interpretations": [
            "workplace",
            "study location",
            "place where user spends the day",
            "current GPS location",
        ],
        "safe_question": NUCLEUS_QUESTIONS["life_places"]["question"],
    },
    "mlc.identity.name": {
        "id": "ask_preferred_name",
        "meaning": "Ask how the user prefers to be called.",
        "required_semantics": ["preferred name / how to address the user"],
        "forbidden_interpretations": [
            "legal full name document request",
            "surname only",
            "username or email",
        ],
        "safe_question": NUCLEUS_QUESTIONS["identity"]["question"],
    },
    "mlc.current_situation": {
        "id": "ask_current_situation",
        "meaning": "Ask whether the user currently works, studies, both, or something else.",
        "required_semantics": ["work / study / both / other life rhythm"],
        "forbidden_interpretations": [
            "job title interview",
            "company name",
            "university enrollment paperwork",
        ],
        "safe_question": NUCLEUS_QUESTIONS["current_situation"]["question"],
    },
    "mlc.immediate_priority": {
        "id": "ask_immediate_priority",
        "meaning": "Ask what the user would most like to manage better right now.",
        "required_semantics": ["near-term priority / what to improve now"],
        "forbidden_interpretations": [
            "long-term life goals questionnaire",
            "full todo list dump",
            "therapy diagnosis",
        ],
        "safe_question": NUCLEUS_QUESTIONS["immediate_priority"]["question"],
    },
    "mlc.responsibilities": {
        "id": "ask_main_responsibilities",
        "meaning": "Ask which concrete commitments take most of the user's time now.",
        "required_semantics": ["main commitments / what occupies them"],
        "forbidden_interpretations": [
            "formal job description",
            "tax or contract details",
            "complete schedule dump",
        ],
        "safe_question": NUCLEUS_QUESTIONS["responsibilities"]["question"],
    },
}


def question_goal_for_gap(gap_key: Optional[str], nucleus: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Return a copy of the structured question goal for an MLC gap key / nucleus."""
    key = (gap_key or "").strip()
    if key in QUESTION_GOALS:
        return dict(QUESTION_GOALS[key])
    if key.startswith("mlc.life_places"):
        return dict(QUESTION_GOALS["mlc.life_places.home"])
    if nucleus:
        mapped = NUCLEUS_GAP_KEY.get(nucleus)
        if mapped and mapped in QUESTION_GOALS:
            return dict(QUESTION_GOALS[mapped])
    return None


def safe_question_for_gap(gap_key: Optional[str], nucleus: Optional[str] = None) -> Optional[str]:
    """Deterministic SAFE question wording for a gap (NUCLEUS_QUESTIONS / goal template)."""
    goal = question_goal_for_gap(gap_key, nucleus)
    if goal and goal.get("safe_question"):
        return str(goal["safe_question"])
    if nucleus and nucleus in NUCLEUS_QUESTIONS:
        return NUCLEUS_QUESTIONS[nucleus]["question"]
    return None


WEAK_FOLLOWUPS: Dict[str, Dict[str, str]] = {
    "current_situation:studio": {
        "key": "mlc.responsibilities",
        "nucleus": "responsibilities",
        "question": "Cosa stai studiando in questo periodo?",
        "benefit": "Capisco il carico reale dello studio senza un questionario.",
        "domain": "studio",
        "gain": "0.94",
        "label": "approfondimento studio",
    },
}

# Statuses that count as addressed (asked-only is NEVER in this set).
ADDRESSED_STATUSES = frozenset({"covered", "skipped", "implicit"})


@dataclass
class NucleusCoverage:
    nucleus: str
    status: str  # covered | skipped | implicit | missing
    evidence_keys: List[str] = field(default_factory=list)

    @property
    def addressed(self) -> bool:
        return self.status in ADDRESSED_STATUSES


@dataclass
class MlcCoverage:
    version: str = MLC_VERSION
    nuclei: List[NucleusCoverage] = field(default_factory=list)
    sufficient: bool = False
    missing: List[str] = field(default_factory=list)
    covered_count: int = 0
    heuristic: str = "mlc-v1"

    def public(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "heuristic": self.heuristic,
            "sufficient": self.sufficient,
            "covered_count": self.covered_count,
            "missing": list(self.missing),
            "nuclei": {
                n.nucleus: {
                    "status": n.status,
                    "addressed": n.addressed,
                    "evidence_keys": list(n.evidence_keys),
                }
                for n in self.nuclei
            },
        }


def _truthy_known(known_facts: Dict[str, Any]) -> Set[str]:
    out: Set[str] = set()
    for k, v in (known_facts or {}).items():
        if v is None or v is False or v == "" or v == []:
            continue
        out.add(k)
    return out


def _nucleus_skipped(nucleus: str, refused: Set[str], postponed: Set[str]) -> bool:
    """Explicit skip only — refused/postponed. Not asked_keys."""
    gap = NUCLEUS_GAP_KEY[nucleus]
    skip = refused | postponed
    if gap in skip:
        return True
    prefixes = {
        "identity": ("servizi._skipped",),
        "current_situation": ("lavoro._skipped", "studio._skipped"),
        "life_places": ("casa._skipped",),
        "responsibilities": ("lavoro._skipped", "studio._skipped", "casa._skipped"),
        "immediate_priority": ("servizi._skipped",),
    }
    return any(p in skip for p in prefixes.get(nucleus, ()))


def _rich_core_context(by_status: Dict[str, str]) -> bool:
    """Identity + situation + places + responsibilities all positively covered."""
    return all(
        by_status.get(n) == "covered"
        for n in ("identity", "current_situation", "life_places", "responsibilities")
    )


def evaluate_mlc_coverage(
    known_facts: Dict[str, Any],
    *,
    refused_keys: Optional[Set[str]] = None,
    postponed_keys: Optional[Set[str]] = None,
) -> MlcCoverage:
    known = _truthy_known(known_facts)
    refused = set(refused_keys or [])
    postponed = set(postponed_keys or [])
    nuclei: List[NucleusCoverage] = []
    missing: List[str] = []
    covered_count = 0

    for nid in NUCLEUS_IDS:
        evidence = [k for k in NUCLEUS_EVIDENCE_KEYS[nid] if k in known]
        if evidence:
            nuclei.append(NucleusCoverage(nid, "covered", evidence))
            covered_count += 1
        elif _nucleus_skipped(nid, refused, postponed):
            nuclei.append(NucleusCoverage(nid, "skipped", []))
        else:
            nuclei.append(NucleusCoverage(nid, "missing", []))
            missing.append(nid)

    by_status = {n.nucleus: n.status for n in nuclei}

    # mlc-v1: imperfect priority phrasing — if the other four cores are covered,
    # treat priority as implicitly addressed (still preferred as an ask when missing).
    # Does NOT use asked_keys. Planner may still prefer to ask priority first.
    if by_status.get("immediate_priority") == "missing" and _rich_core_context(by_status):
        for i, n in enumerate(nuclei):
            if n.nucleus == "immediate_priority":
                nuclei[i] = NucleusCoverage(
                    "immediate_priority",
                    "implicit",
                    ["mlc.v1.rich_core_context"],
                )
                break
        missing = [m for m in missing if m != "immediate_priority"]
        by_status["immediate_priority"] = "implicit"

    sufficient = _is_sufficient_v1(nuclei, covered_count, missing)
    return MlcCoverage(
        nuclei=nuclei,
        sufficient=sufficient,
        missing=missing,
        covered_count=covered_count,
        heuristic="mlc-v1",
    )


def _is_sufficient_v1(
    nuclei: List[NucleusCoverage],
    covered_count: int,
    missing: List[str],
) -> bool:
    """
    mlc-v1 sufficiency heuristic (not irreversible domain law):

    1. No nucleus still *missing* (all addressed: covered | skipped | implicit).
    2. At least 3 nuclei with positive evidence (covered).
    3. immediate_priority is *preferred* covered; also OK if:
       - skipped with covered_count >= 4, or
       - implicit from rich core context (identity+situation+places+responsibilities).

    Asking a question alone never satisfies a nucleus.
    """
    if missing:
        return False
    if covered_count < 3:
        return False
    if any(not n.addressed for n in nuclei):
        return False
    by_id = {n.nucleus: n for n in nuclei}
    pri = by_id.get("immediate_priority")
    if not pri:
        return False
    if pri.status == "covered":
        return True
    if pri.status == "implicit" and covered_count >= 4:
        return True
    if pri.status == "skipped" and covered_count >= 4:
        return True
    return False


def is_mlc_sufficient(
    known_facts: Dict[str, Any],
    *,
    refused_keys: Optional[Set[str]] = None,
    postponed_keys: Optional[Set[str]] = None,
) -> bool:
    return evaluate_mlc_coverage(
        known_facts, refused_keys=refused_keys, postponed_keys=postponed_keys
    ).sufficient


def compute_mlc_gaps(
    known_facts: Dict[str, Any],
    *,
    asked_keys: Optional[Set[str]] = None,
    refused_keys: Optional[Set[str]] = None,
    postponed_keys: Optional[Set[str]] = None,
) -> List[GapItem]:
    """Rank unaddressed MLC nuclei.

    `asked_keys` only de-prioritizes (prefer not to repeat); they do NOT mark
    a nucleus addressed and do NOT remove the gap forever.
    Explicit refuse/postpone removes the ask (skipped).
    """
    cov = evaluate_mlc_coverage(
        known_facts, refused_keys=refused_keys, postponed_keys=postponed_keys
    )
    known = _truthy_known(known_facts)
    asked = set(asked_keys or [])
    refused = set(refused_keys or [])
    postponed = set(postponed_keys or [])
    # Only explicit skip removes the gap — not asked
    hard_skip = refused | postponed
    gaps: List[GapItem] = []

    if (
        "studio.active" in known
        and "mlc.responsibilities" not in known
        and "studio.universita" not in known
        and "studio.esame" not in known
        and NUCLEUS_GAP_KEY["responsibilities"] not in hard_skip
        and "responsibilities" in cov.missing
    ):
        fu = WEAK_FOLLOWUPS["current_situation:studio"]
        gaps.append(
            GapItem(
                key=fu["key"],
                domain=fu["domain"],  # type: ignore[arg-type]
                label=fu["label"],
                information_gain=float(fu["gain"]),
                prefer_document=False,
                benefit_code="mlc_responsibilities",
                question_template=fu["question"],
            )
        )

    for n in cov.nuclei:
        # Prefer asking missing; also prefer asking implicit priority once (strongly preferred)
        if n.status == "covered" or n.status == "skipped":
            continue
        if n.status == "implicit" and n.nucleus != "immediate_priority":
            continue
        # For implicit priority: still surface as preferred ask if not yet asked;
        # sufficiency already allows wrap — planner uses gaps only when not sufficient.
        if n.status == "implicit":
            continue
        meta = NUCLEUS_QUESTIONS[n.nucleus]
        key = NUCLEUS_GAP_KEY[n.nucleus]
        if key in hard_skip:
            continue
        if any(g.key == key for g in gaps):
            continue
        gain = float(meta["gain"])
        # Soft de-prioritize already-asked (does not address)
        if key in asked:
            gain = max(0.1, gain - 0.15)
        gaps.append(
            GapItem(
                key=key,
                domain=meta["domain"],  # type: ignore[arg-type]
                label=meta["label"],
                information_gain=gain,
                prefer_document=False,
                benefit_code=f"mlc_{n.nucleus}",
                question_template=meta["question"],
            )
        )

    gaps.sort(key=lambda g: (-g.information_gain, g.key))
    return gaps


def wrap_plan_meta(coverage: MlcCoverage) -> Dict[str, Any]:
    return {
        "phase": "wrap",
        "gaps_remaining": 0,
        "mlc": coverage.public(),
        "mlc_version": MLC_VERSION,
        "completion_reason": "minimum_life_context",
        "heuristic": "mlc-v1",
    }
