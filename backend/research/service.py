"""
Running a piece of research.

The division of labour here is the whole point of the phase:

    the model decides    whether something already looked up will do, what
                         would answer the question, which searches to run,
                         whether what came back settles it, whether two
                         sources disagree, whether to look again, when to
                         stop, and what to say
    the code decides     nothing about any of that

What the code does is keep the thing bounded and honest: it caps the rounds,
caps the searches, refuses to run the same search twice, strips personal
identifiers out of anything leaving the machine, records what was fetched and
when, and writes it all down so it can be cited later and not repeated
needlessly. Guardrails, not strategy.

And research produces evidence. It does not produce work. Nothing in this
module writes a task, a card, an attention item or a notification: what was
found goes back to the reasoning that asked for it, and that reasoning decides
— through the paths that already exist — whether any of it changes anything for
the person. A search that turns up nothing interesting must be able to leave
the day completely untouched.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from research.models import (
    EvidenceSource,
    ResearchNeed,
    ResearchRun,
    new_source_id,
)
from research.reasoning import (
    assess_evidence,
    consider_reuse,
    plan_research,
    synthesize,
)
from research.repository import ResearchRepository

logger = logging.getLogger("ora.research.service")

# Guardrails. Every one of these is a limit on cost or time, and none of them
# is a judgement about research: the model stops when it has what it needs,
# and these only decide how much rope it has before the attempt is called
# partial and handed back honestly.
MAX_ITERATIONS = 3
MAX_QUERIES = 8
MAX_QUERIES_PER_ROUND = 4
MAX_SOURCES = 24
MAX_RESULTS_PER_QUERY = 5
# What a run is worth if the model declined to say. Deliberately short: an
# unstated shelf life should expire quickly rather than be assumed generous.
DEFAULT_VALID_HOURS = 6.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize(query: str) -> str:
    """For telling two searches apart. Not for understanding either of them."""
    return " ".join((query or "").lower().split())


class ResearchService:
    def __init__(self, db):
        self.db = db
        self.repo = ResearchRepository(db)

    async def run(
        self,
        user_id: str,
        need: ResearchNeed,
        *,
        session_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        plan_item_id: Optional[str] = None,
        situation_ref: Optional[str] = None,
        reasoning_epoch: Optional[int] = None,
        context_lines: Optional[List[str]] = None,
        locale_hint: str = "",
        allow_reuse: bool = True,
    ) -> ResearchRun:
        """
        Answer the need, or say honestly why it could not be answered.

        The work refs are carried through untouched. Research happens inside
        the reasoning that asked for it — same session, same plan, same
        situation — and never starts anything of its own.
        """
        run = ResearchRun(
            user_id=user_id,
            need=need,
            session_id=session_id,
            plan_id=plan_id,
            plan_item_id=plan_item_id,
            situation_ref=situation_ref,
            reasoning_epoch=reasoning_epoch,
        )

        if allow_reuse:
            reused = await self._reuse(user_id, need)
            if reused is not None:
                return reused

        plan = await plan_research(
            need, context_lines=list(context_lines or []), locale_hint=locale_hint
        )
        if plan is None:
            run.status = "failed"
            run.outcome_note = "Non sono riuscita a impostare la ricerca."
            run.failures.append("no_plan")
            run.completed_at = _now().isoformat()
            await self.repo.save(run)
            return run
        run.plan = plan

        pending: List[str] = []
        for question in plan.questions:
            pending.extend(question.queries)

        assessment = None
        for iteration in range(1, MAX_ITERATIONS + 1):
            run.iterations = iteration
            batch = self._next_batch(pending, run.queries_run)
            pending = []
            if not batch:
                break

            found = await self._search_all(batch, run)
            run.sources.extend(found)
            run.sources = run.sources[:MAX_SOURCES]

            assessment = await assess_evidence(
                plan=plan,
                sources=run.sources,
                already_run=run.queries_run,
                iteration=iteration,
                iterations_left=MAX_ITERATIONS - iteration,
            )
            if assessment is None:
                run.failures.append(f"no_assessment_round_{iteration}")
                break
            run.assessments.append(assessment)

            if assessment.sufficiency == "sufficient":
                break
            # Not settled. The model says what to look for next; if it has
            # nothing to add, looking again would be the same search twice.
            pending = list(assessment.next_queries or [])
            if not pending:
                break

        if not run.sources:
            run.status = "failed" if run.failures else "insufficient"
            run.outcome_note = (
                "Non sono riuscita a raggiungere le fonti."
                if run.failures
                else "Non ho trovato informazioni utilizzabili."
            )
            run.completed_at = _now().isoformat()
            await self.repo.save(run)
            return run

        if assessment is None:
            run.status = "partial"
            run.outcome_note = "Ho trovato del materiale ma non sono riuscita a valutarlo."
            run.completed_at = _now().isoformat()
            await self.repo.save(run)
            return run

        run.synthesis = await synthesize(
            plan=plan, sources=run.sources, assessment=assessment
        )
        if run.synthesis is None:
            run.status = "partial"
            run.outcome_note = "Ho raccolto le fonti ma non sono riuscita a tirarne le somme."
        elif assessment.sufficiency == "sufficient":
            run.status = "completed"
            run.outcome_note = ""
        elif assessment.sufficiency == "conflicted":
            unresolved = [c for c in assessment.conflicts if not c.resolved]
            run.status = "partial"
            run.outcome_note = (
                "Le fonti non concordano su tutto."
                if unresolved
                else ""
            )
            if not unresolved:
                run.status = "completed"
        else:
            run.status = "insufficient"
            run.outcome_note = "Quello che ho trovato non basta a rispondere del tutto."

        hours = plan.valid_for_hours if plan.valid_for_hours else DEFAULT_VALID_HOURS
        run.valid_until = (_now() + timedelta(hours=float(hours))).isoformat()
        run.completed_at = _now().isoformat()
        await self.repo.save(run)
        return run

    # -- reuse ----------------------------------------------------------

    async def _reuse(self, user_id: str, need: ResearchNeed) -> Optional[ResearchRun]:
        """
        Something already looked up, if it genuinely answers this.

        Two steps, deliberately separated: the code drops everything whose own
        stated shelf life has passed, which is arithmetic; the model decides
        whether what is left is about the same question, which is not.
        """
        try:
            candidates = await self.repo.still_valid(user_id)
        except Exception as e:
            logger.info("reuse lookup soft-fail: %s", type(e).__name__)
            return None
        if not candidates:
            return None

        summaries = [
            {
                "run_id": c.id,
                "question": c.need.question,
                "goal": c.plan.goal if c.plan else "",
                "answer": (c.synthesis.answer[:400] if c.synthesis else ""),
                "looked_up_at": c.started_at,
                "considered_valid_until": c.valid_until,
                "status": c.status,
            }
            for c in candidates
        ]
        chosen_id = await consider_reuse(need, summaries)
        if not chosen_id:
            return None
        for candidate in candidates:
            if candidate.id == chosen_id:
                logger.info("research reused run=%s user=%s", candidate.id, user_id)
                return candidate
        return None

    # -- searching ------------------------------------------------------

    def _next_batch(self, wanted: List[str], already: List[str]) -> List[str]:
        """What of this round's searches is left to run, within budget."""
        seen = {_normalize(q) for q in already}
        budget = MAX_QUERIES - len(already)
        batch: List[str] = []
        for query in wanted:
            if budget <= 0 or len(batch) >= MAX_QUERIES_PER_ROUND:
                break
            key = _normalize(query)
            if not key or key in seen:
                continue
            seen.add(key)
            batch.append(query)
            budget -= 1
        return batch

    async def _search_all(self, queries: List[str], run: ResearchRun) -> List[EvidenceSource]:
        """
        Run them, through the capability ORA already has.

        The tool is semantically blind and stays that way: it is handed a
        sentence and returns what it found. It is not told what the question is
        about, and there is nothing here that would let it prefer one publisher
        over another.
        """
        from conversation_engine.ai_core.tools.web_search import execute_web_search

        known_urls = {s.url for s in run.sources if s.url}
        out: List[EvidenceSource] = []
        for query in queries:
            run.queries_run.append(query)
            try:
                observation = await execute_web_search(
                    {"query": query, "max_results": MAX_RESULTS_PER_QUERY},
                    {},
                )
            except Exception as e:
                logger.info("search failed: %s", type(e).__name__)
                run.failures.append(f"search_error:{type(e).__name__}")
                continue

            payload = (observation.payload or {}).get("external") or {}
            if observation.status == "failed":
                run.failures.append(f"search_failed:{payload.get('failure_code') or 'UNKNOWN'}")
                continue

            for hit in payload.get("sources") or []:
                url = str(hit.get("url") or "")
                if url and url in known_urls:
                    continue
                if url:
                    known_urls.add(url)
                out.append(
                    EvidenceSource(
                        source_id=new_source_id(),
                        url=url,
                        title=str(hit.get("title") or ""),
                        publisher=_publisher_of(url),
                        snippet=str(hit.get("snippet") or ""),
                        found_by_query=query,
                        authority_hint=str(hit.get("authority_hint") or "UNKNOWN"),
                    )
                )
        return out


def _publisher_of(url: str) -> str:
    """The host, which is observable. What it is worth is not decided here."""
    raw = (url or "").strip()
    if "://" not in raw:
        return ""
    host = raw.split("://", 1)[1].split("/", 1)[0]
    return host[4:] if host.startswith("www.") else host


_service: Dict[int, ResearchService] = {}


def get_research_service(db) -> ResearchService:
    key = id(db)
    if key not in _service:
        _service[key] = ResearchService(db)
    return _service[key]


def research_available() -> bool:
    """Whether looking things up is possible at all right now."""
    try:
        from conversation_engine.ai_core.tools.web_search import availability

        return availability() == "available"
    except Exception:
        return False


def public_research_payload(run: ResearchRun) -> Dict[str, Any]:
    """
    What may be shown to a person.

    The sources are the ones a claim actually rests on — never everything that
    came back from a search, and never a search snippet ORA did not use. What
    ORA did internally (queries, providers, rounds, how sure it felt) is not
    part of what somebody is told.
    """
    return {
        "status": run.status,
        "answer": run.synthesis.answer if run.synthesis else "",
        "note": run.outcome_note,
        "sources": run.citable_sources(),
    }
