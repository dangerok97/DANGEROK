"""
The three places research thinks, and they are all the model.

    plan_research        what would answer this, and what to go and look for
    assess_evidence      is what I now have enough, and does any of it disagree
    synthesize           what the reasoning that asked should be told

Nothing in this file decides anything semantic. It builds a prompt, calls the
model, and validates the shape of what comes back. If the model does not
answer, the caller is told so and the run ends honestly — there is no
deterministic fallback that would quietly write a plan of its own, because a
plan written by code is exactly what this phase exists not to have.

There is no subject anywhere in here. The prompts describe *how to research*,
never what is being researched: the same words go out for a loan, a tariff, a
job market or a language school, and the difference is entirely in the
question the reasoning asked.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from research.models import (
    EvidenceSource,
    ResearchAssessment,
    ResearchNeed,
    ResearchPlan,
    ResearchSynthesis,
)

logger = logging.getLogger("ora.research.reasoning")


# One retry, because a provider returning nothing is a technical failure and
# retrying technical failures is the code's job. It is not a second attempt at
# thinking: the same question is asked again, unchanged, and if the answer is
# still nothing the run says so.
_ATTEMPTS = 2


async def _ask_model(system: str, user: str) -> Optional[Dict[str, Any]]:
    """
    One JSON answer from the model, or nothing — and a line saying which.

    The logging here is not decoration. A reasoning layer that swallows every
    failure into `None` is a layer where "the model said nothing" and "the
    provider refused" and "the JSON was truncated" all look identical, and
    an afternoon gets spent guessing between them. Each attempt now says
    where it stopped.

    What is recorded is deliberately thin: which provider answered, whether
    anything came back, how long it was, whether it parsed, and a safe error
    type. Never the prompt, never the payload, never a key — a log line that
    carries what somebody was asked about is a privacy leak that survives in
    a file nobody is watching.
    """
    for attempt in range(_ATTEMPTS):
        stage = "call"
        try:
            from llm.manager import get_manager

            result = await get_manager().chat(system=system, user=user, json_mode=True)
            stage = "response"
            text = getattr(result, "text", None) or ""
            provider = getattr(result, "provider", "?")
            model = getattr(result, "model", None) or "?"
            if not text.strip():
                logger.warning(
                    "model boundary attempt=%s provider=%s model=%s response=yes "
                    "payload=empty parse=n/a outcome=empty_response",
                    attempt + 1, provider, model,
                )
                continue

            stage = "parse"
            data = _parse_json(text)
            if data is None:
                # Truncation looks exactly like malformed JSON from here, so
                # say which is more likely rather than guessing: a payload
                # that ends without a closing brace was cut off.
                cut = not text.rstrip().endswith(("}", "]", "`"))
                logger.warning(
                    "model boundary attempt=%s provider=%s model=%s response=yes "
                    "payload=%s parse=fail outcome=%s",
                    attempt + 1, provider, model, len(text),
                    "truncated" if cut else "malformed_json",
                )
                continue

            logger.info(
                "model boundary attempt=%s provider=%s model=%s response=yes "
                "payload=%s parse=ok outcome=ok",
                attempt + 1, provider, model, len(text),
            )
            return data
        except Exception as e:
            # `attempts` is the manager's own record of who was tried and why
            # each one declined. Kinds only — no messages, which is where
            # providers put URLs and echoed content.
            kinds = ""
            try:
                from llm.manager import get_manager

                kinds = ",".join(
                    f"{a.get('provider')}:{a.get('failure_kind')}"
                    for a in (get_manager()._last_attempts or [])
                )
            except Exception:
                pass
            logger.warning(
                "model boundary attempt=%s stage=%s outcome=%s tried=[%s]",
                attempt + 1, stage, type(e).__name__, kinds,
            )
    return None


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start : end + 1])
                return data if isinstance(data, dict) else None
            except Exception:
                return None
        return None


def _fit(data: Dict[str, Any], model) -> Dict[str, Any]:
    """
    Trim over-long lists to what the contract allows.

    A model that returns nine next searches instead of five has not
    misunderstood the question; it has overshot a bound. Throwing the whole
    assessment away for that would lose real reasoning to a technicality, and
    inventing a shorter one would be worse. So the first few are kept, in the
    order the model put them, and nothing else is touched.
    """
    if not isinstance(data, dict):
        return data
    out = dict(data)
    for name, field in model.model_fields.items():
        value = out.get(name)
        if not isinstance(value, list):
            continue
        cap = next(
            (m.max_length for m in getattr(field, "metadata", []) if hasattr(m, "max_length")),
            None,
        )
        if cap and len(value) > cap:
            out[name] = value[:cap]
    # Same for a sentence that ran long. Cutting it keeps what was said;
    # discarding the object would lose a whole round of real reasoning to a
    # character count.
    for name, field in model.model_fields.items():
        value = out.get(name)
        if not isinstance(value, str):
            continue
        cap = next(
            (m.max_length for m in getattr(field, "metadata", []) if hasattr(m, "max_length")),
            None,
        )
        if cap and len(value) > cap:
            out[name] = value[:cap]
    return out


_DISCIPLINE = """You are the part of ORA that goes and finds things out.

You are not answering the person. You are working out how to answer a question
that ORA could not answer from what it already knows, by looking at the world.

Hold to these:

- Say what would actually settle the question, not what sounds thorough.
- Do not look for what you have already been told. What is known is listed for
  you; treat it as answered.
- A search is a sentence somebody would type. Write the ones that would find
  the answer, in the language of the place the answer belongs to.
- Fitness depends on the claim. What a rule requires is settled by whoever sets
  the rule; what something actually costs is settled by whoever is selling it,
  or by somebody who surveyed them. A question with both halves needs both
  kinds of source, and saying "official sources are better" for the price half
  would be as wrong as taking a rule from an advertisement. Say, per question,
  what would settle it.
- Recency matters differently for different questions. Decide what it means
  for this one, and say how long your answer should be trusted.
- Only ask for what the world needs to know about this person. A public search
  does not need a name, an address, an income or an identifier to return what
  is generally true. If a detail genuinely changes the answer, include the
  detail and not the person.

Answer with one JSON object and nothing else."""


async def plan_research(
    need: ResearchNeed,
    *,
    context_lines: List[str],
    locale_hint: str = "",
) -> Optional[ResearchPlan]:
    """How to answer this — the model's plan, or nothing."""
    user = json.dumps(
        {
            "question_to_answer": need.question,
            "why_it_matters_now": need.purpose,
            "already_known": (need.already_known or []) + list(context_lines or []),
            "locale_hint": locale_hint,
            "produce": {
                "goal": "what answering this would establish",
                "reason": "why the answer cannot come from what is already known",
                "known_context": ["what you are treating as already answered"],
                "unknowns": ["what is genuinely missing"],
                "questions": [
                    {
                        "ref": "short stable id",
                        "question": "one thing to find out",
                        "evidence_needed": "what would count as an answer",
                        "source_fitness": (
                            "what kind of source would settle THIS question, in "
                            "words — never a named site. Say so when only "
                            "whoever sets a rule can tell you what the rule is, "
                            "and equally when what you need is what things "
                            "actually cost, which is published by the people "
                            "selling them"
                        ),
                        "queries": ["the searches to run for it"],
                    }
                ],
                "preferred_source_characteristics": [
                    "described in words, never a named website"
                ],
                "freshness_requirement": "how recent evidence has to be, and why",
                "valid_for_hours": "how long your answer should be trusted, a number",
                "geographic_scope": "where the answer must apply, or null",
                "stop_condition": "what would make you stop looking",
                "disclosable_context": [
                    "what about this person may appear in a public search"
                ],
                "withheld_context": [
                    "what must not leave, and why it is not needed out there"
                ],
            },
        },
        ensure_ascii=False,
    )
    data = await _ask_model(_DISCIPLINE, user)
    if not data:
        return None
    try:
        plan = ResearchPlan.model_validate(_fit(data, ResearchPlan))
    except Exception as e:
        logger.info("research plan rejected: %s", type(e).__name__)
        return None
    # The only structural requirement: a plan with nothing to run is not a
    # plan. What to run, and how much of it, stays the model's.
    if not any(q.queries for q in plan.questions):
        return None
    return plan


async def assess_evidence(
    *,
    plan: ResearchPlan,
    sources: List[EvidenceSource],
    already_run: List[str],
    iteration: int,
    iterations_left: int,
) -> Optional[ResearchAssessment]:
    """Enough, not enough, or contradictory — the model reading its own haul."""
    user = json.dumps(
        {
            "goal": plan.goal,
            "questions": [
                {
                    "ref": q.ref,
                    "question": q.question,
                    "evidence_needed": q.evidence_needed,
                    "source_fitness": q.source_fitness,
                }
                for q in plan.questions
            ],
            "freshness_requirement": plan.freshness_requirement,
            "stop_condition": plan.stop_condition,
            "searches_already_run": already_run,
            "round": iteration,
            "further_rounds_available": iterations_left,
            "what_was_found": [
                {
                    "source_id": s.source_id,
                    "title": s.title,
                    "url": s.url,
                    "publisher": s.publisher,
                    "snippet": s.snippet,
                    "found_by_query": s.found_by_query,
                    "retrieved_at": s.retrieved_at,
                }
                for s in sources
            ],
            "produce": {
                "sufficiency": "sufficient | insufficient | conflicted",
                "reason": "why, judged against the goal and not against a count",
                "missing_evidence": ["what is still not established"],
                "conflicts": [
                    {
                        "about": "what the sources disagree on",
                        "positions": ["each incompatible reading"],
                        "source_ids": ["which sources"],
                        "resolution": "which reading applies here and why, or that you cannot tell",
                        "resolved": "true only if you can actually settle it",
                    }
                ],
                "next_queries": [
                    "if not sufficient, the searches to run next — different "
                    "from the ones already run"
                ],
            },
            "note": (
                "Judge against the goal. A single source that answers it is "
                "enough; ten that talk around it are not. If nothing found "
                "actually addresses the question, say insufficient. And judge "
                "each source against what it is being used for: a page that "
                "reports a price well may be the wrong place to read a rule "
                "from, and vice versa. If what you have is the wrong kind of "
                "source for part of the question, that part is not settled."
            ),
        },
        ensure_ascii=False,
    )
    data = await _ask_model(_DISCIPLINE, user)
    if not data:
        return None
    try:
        return ResearchAssessment.model_validate(_fit(data, ResearchAssessment))
    except Exception as e:
        logger.info("research assessment rejected: %s", type(e).__name__)
        return None


async def synthesize(
    *,
    plan: ResearchPlan,
    sources: List[EvidenceSource],
    assessment: ResearchAssessment,
) -> Optional[ResearchSynthesis]:
    """The evidence package that goes back to the reasoning that asked."""
    user = json.dumps(
        {
            "goal": plan.goal,
            "sufficiency": assessment.sufficiency,
            "still_missing": assessment.missing_evidence,
            "conflicts": [
                {"about": c.about, "positions": c.positions, "resolution": c.resolution}
                for c in assessment.conflicts
            ],
            "sources": [
                {
                    "source_id": s.source_id,
                    "title": s.title,
                    "url": s.url,
                    "publisher": s.publisher,
                    "snippet": s.snippet,
                    "retrieved_at": s.retrieved_at,
                }
                for s in sources
            ],
            "produce": {
                "answer": (
                    "what the evidence establishes, in plain Italian, as ORA "
                    "would say it to the person. Say what is uncertain as "
                    "uncertain. Never claim to have checked something you did "
                    "not find."
                ),
                "claims": [
                    {
                        "statement": "one thing the evidence establishes",
                        "supported_by": ["the source_ids it rests on — never empty"],
                        "scope": "external_fact | general_inference | person_specific",
                        "person_evidence_used": [
                            "for person_specific only: the facts about this "
                            "person the conclusion rests on"
                        ],
                        "certainty": "in words",
                        "conflicts_with": ["source_ids that say otherwise"],
                    }
                ],
                "unresolved": ["what stayed open"],
                "caveats": ["what would make this wrong or out of date"],
            },
            "note": (
                "Every claim names the sources it came from. If you cannot "
                "point at a source for something, leave it out. "
                "And say who each claim is about. What the sources report is "
                "external_fact. What is generally true of situations like this "
                "is general_inference — write it as general, not as a verdict. "
                "A conclusion about *this* person is person_specific, and you "
                "may only make one when you actually know enough about them to "
                "stand behind it: decide for yourself what that conclusion "
                "would need, and if you do not have it, either say the general "
                "thing properly or say what you would need to know. Telling "
                "somebody they are in a strong position, when all you hold is "
                "one fact about them and a page about a market, is a verdict "
                "you have not earned."
            ),
        },
        ensure_ascii=False,
    )
    data = await _ask_model(_DISCIPLINE, user)
    if not data:
        return None
    try:
        synthesis = ResearchSynthesis.model_validate(_fit(data, ResearchSynthesis))
    except Exception as e:
        logger.info("research synthesis rejected: %s", type(e).__name__)
        return None

    # A claim that names no source is the model talking, not evidence. Dropped
    # here rather than shown to somebody as something ORA found out.
    known_ids = {s.source_id for s in sources}
    kept = []
    for claim in synthesis.claims:
        if not (claim.supported_by and set(claim.supported_by) & known_ids):
            continue
        # A verdict on a person that names nothing about that person is not a
        # conclusion, it is a compliment. The shape is checked here; what a
        # given conclusion needs stays the model's to decide.
        if claim.scope == "person_specific" and not claim.person_evidence_used:
            logger.info("dropped ungrounded person-specific claim")
            continue
        claim.supported_by = [sid for sid in claim.supported_by if sid in known_ids]
        kept.append(claim)
    synthesis.claims = kept
    return synthesis


async def consider_reuse(
    need: ResearchNeed,
    candidates: List[Dict[str, Any]],
) -> Optional[str]:
    """
    Whether something already looked up answers this, or nothing.

    The code has already discarded everything whose own freshness window has
    closed — that is a timestamp comparison and nothing more. Whether a run
    about one question answers another is meaning, so it is asked here. A run
    about last month's tariffs does not answer a question about switching
    supplier just because both mention electricity, and only a reader can tell.
    """
    if not candidates:
        return None
    user = json.dumps(
        {
            "question_i_need_answered": need.question,
            "why": need.purpose,
            "already_looked_up": candidates,
            "produce": {
                "reuse_run_id": (
                    "the id of a run that genuinely answers my question, or null. "
                    "Null unless it really does — looking again is cheap next to "
                    "telling somebody something that was about a different question."
                ),
                "why": "one sentence",
            },
        },
        ensure_ascii=False,
    )
    data = await _ask_model(_DISCIPLINE, user)
    if not data:
        return None
    chosen = data.get("reuse_run_id")
    if not isinstance(chosen, str) or not chosen.strip():
        return None
    valid = {c.get("run_id") for c in candidates}
    return chosen.strip() if chosen.strip() in valid else None
