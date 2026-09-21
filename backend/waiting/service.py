"""
The service that lets ORA stop, and then genuinely carry on.

Three responsibilities, kept apart on purpose:

  1. recording a blocker, once, with a server-owned pointer back to the work;
  2. accepting an answer atomically, from any surface;
  3. continuing the work — separately, retryably, and never twice.

The third is deliberately not part of the second. An answer that was given is a
fact about the person; a continuation that ran is a fact about the system. If
those share a transaction then any failure downstream costs someone their
answer, and the product asks them to repeat themselves — which is exactly the
behaviour a persistent question was supposed to end.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional

from waiting.models import (
    AnswerKind,
    AnswerSource,
    OpenQuestion,
    RequestedVariable,
    ResumePointer,
    WorkRefs,
    now_iso,
)
from waiting.repository import DuplicateQuestion, OpenQuestionRepository

logger = logging.getLogger("ora.waiting")

# What a person is shown at once. More than a handful of open questions is a
# signal that the reasoning is asking badly, not that the list needs paging.
MAX_OPEN = 20

#     OLTRE QUESTO, UNA DOMANDA NON E' PIU' QUALCOSA CHE SI ASPETTA ADESSO.
ABANDONED_AFTER_DAYS = 2


def _text(v: Any, limit: int = 400) -> str:
    return str(v or "").strip()[:limit]


def _dedupe_key(*, refs: WorkRefs, question: str, asked_refs: List[str]) -> str:
    """
    One blocker, one question.

    Built from what the question is *about* rather than from how it was
    phrased, so a retried cycle that rewords slightly still collides. The
    question text is included but normalised, because two genuinely different
    questions on the same item must still be able to coexist across time.
    """
    parts = [
        refs.session_id or "",
        refs.plan_id or "",
        refs.plan_item_id or "",
        refs.object_id or "",
        "|".join(sorted(asked_refs)),
        " ".join(_text(question, 600).lower().split()),
    ]
    return hashlib.sha256(" ".join(parts).encode("utf-8")).hexdigest()[:40]


class WaitingService:
    def __init__(self, db):
        self.db = db
        self.repo = OpenQuestionRepository(db)

    async def ensure_indexes(self) -> None:
        await self.repo.ensure_indexes()

    # ------------------------------------------------------------------
    # 1. Recording a blocker
    # ------------------------------------------------------------------

    async def record_blocking_question(
        self,
        user_id: str,
        *,
        question: str,
        why_needed: str = "",
        context_label: str = "",
        expected_answer_kind: AnswerKind = "free_text",
        refs: WorkRefs,
        resume: ResumePointer,
        requested_variables: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Persist what ORA is waiting for. Returns the public view, or None when
        there was nothing worth persisting.

        Idempotent in two layers: the dedupe key is checked first because that
        is cheap and answers the common case, and the unique index catches the
        race where two cycles reach the insert together. Either way exactly one
        open question exists afterwards.
        """
        q_text = _text(question, 600)
        if not q_text:
            return None

        key = _dedupe_key(refs=refs, question=q_text, asked_refs=list(resume.asked_refs or []))
        existing = await self.repo.find_open_by_dedupe(user_id, key)
        if existing:
            logger.info("question_created dedupe_hit id=%s", existing.get("id"))
            return OpenQuestion.model_validate(existing).public()

        q = OpenQuestion(
            user_id=user_id,
            question=q_text,
            why_needed=_text(why_needed),
            context_label=_text(context_label, 160),
            expected_answer_kind=expected_answer_kind,
            refs=refs,
            resume=resume,
            dedupe_key=key,
            requested_variables=[
                RequestedVariable.model_validate(v) for v in (requested_variables or [])
            ][:10],
        )
        try:
            await self.repo.insert(q)
        except DuplicateQuestion:
            again = await self.repo.find_open_by_dedupe(user_id, key)
            return OpenQuestion.model_validate(again).public() if again else None

        # One blocker at a time per branch. A newer question on the same item
        # means the reasoning moved on; leaving the older one open would ask
        # someone for something ORA has stopped waiting for.
        await self._supersede_siblings(user_id, q)

        logger.info(
            "question_created id=%s kind=%s plan=%s item=%s session=%s",
            q.id, q.resume.kind, refs.plan_id, refs.plan_item_id, refs.session_id,
        )
        return q.public()

    async def _supersede_siblings(self, user_id: str, q: OpenQuestion) -> None:
        match: Dict[str, Any] = {}
        if q.refs.preparation_id:
            #     UNA PREPARAZIONE ASPETTA UNA COSA PER VOLTA.
            # Confermare il numero e chiedere il via libera sono due fasi dello
            # stesso lavoro: la seconda sostituisce la prima, anche se sono
            # nate in due conversazioni diverse.
            match = {"refs.preparation_id": q.refs.preparation_id}
        elif q.refs.plan_item_id:
            match = {"refs.plan_item_id": q.refs.plan_item_id}
        elif q.refs.plan_id:
            match = {"refs.plan_id": q.refs.plan_id}
        elif q.refs.session_id:
            match = {"refs.session_id": q.refs.session_id}
        if not match:
            return
        n = await self.repo.resolve_where(
            user_id, match=match, status="superseded",
            reason="replaced_by_newer_blocker", exclude_id=q.id,
        )
        if n:
            logger.info("question_superseded count=%d by=%s", n, q.id)

    # ------------------------------------------------------------------
    # 2. Reading
    # ------------------------------------------------------------------

    async def list_open(self, user_id: str, *, limit: int = MAX_OPEN) -> List[Dict[str, Any]]:
        rows = await self.repo.list_open(user_id, limit=limit)
        return [OpenQuestion.model_validate(r).public() for r in rows]

    async def open_for_session(self, user_id: str, session_id: str) -> List[Dict[str, Any]]:
        rows = await self.repo.list_open_for_session(user_id, session_id)
        return [OpenQuestion.model_validate(r).public() for r in rows]

    # ------------------------------------------------------------------
    # 3. Answering, and continuing
    # ------------------------------------------------------------------

    async def answer(
        self,
        user_id: str,
        question_id: str,
        *,
        answer: str,
        source: AnswerSource = "unknown",
    ) -> Dict[str, Any]:
        """
        Accept an answer from wherever it came, then continue the work.

        The client says what the person typed and nothing else. Where to resume
        is read from the stored pointer — a client that could name its own
        continuation target would be a client that could be talked into naming
        someone else's.
        """
        raw = (answer or "").strip()
        if not raw:
            return {"ok": False, "error": "answer_required"}

        doc = await self.repo.answer(user_id, question_id, answer_raw=raw, source=source)
        if not doc:
            # Either it does not exist, or somebody already answered it. Both
            # are the same answer to the caller: there is nothing left to do.
            current = await self.repo.get(user_id, question_id)
            if not current:
                return {"ok": False, "error": "not_found"}
            return {
                "ok": True,
                "already": True,
                "status": current.get("status"),
                "question_id": question_id,
            }

        logger.info("question_answered id=%s source=%s", question_id, source)
        continuation = await self._continue(user_id, doc)
        return {"ok": True, "question_id": question_id, "status": "answered", **continuation}

    async def retry_continuation(self, user_id: str, question_id: str) -> Dict[str, Any]:
        """Run the work again for an answer that was accepted but never continued."""
        doc = await self.repo.get(user_id, question_id)
        if not doc:
            return {"ok": False, "error": "not_found"}
        if doc.get("status") != "answered":
            return {"ok": False, "error": "not_answered"}
        return {"ok": True, **(await self._continue(user_id, doc))}

    async def _continue(self, user_id: str, doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Put the reasoning back where it was, then let it think.

        The claim is what makes this run once: two callers reaching here
        together — a retry racing the original, say — will find that only one
        of them owns a `running` continuation, and the other returns without
        touching the work.
        """
        question_id = str(doc.get("id"))
        claimed = await self.repo.claim_continuation(user_id, question_id)
        if not claimed:
            return {"resumed": False, "reason": "already_running_or_done"}

        q = OpenQuestion.model_validate(claimed)
        if q.continuation.exhausted():
            await self.repo.finish_continuation(
                user_id, question_id, ok=False, error="attempts_exhausted"
            )
            logger.warning("resume_failed id=%s reason=attempts_exhausted", question_id)
            return {"resumed": False, "reason": "attempts_exhausted"}

        session_id = q.refs.session_id
        if not session_id:
            # Nothing to continue into. The answer is still recorded, which is
            # what matters; the reasoning will find it as context next time.
            await self.repo.finish_continuation(user_id, question_id, ok=True)
            return {"resumed": False, "reason": "no_thread"}

        logger.info("resume_started id=%s session=%s attempt=%d",
                    question_id, session_id, q.continuation.attempts)
        try:
            await self._restore_focus(user_id, q)
            out = await self._run_turn(user_id, q)
        except Exception as e:  # noqa: BLE001 - the answer must survive anything
            code = type(e).__name__[:120]
            await self.repo.finish_continuation(user_id, question_id, ok=False, error=code)
            logger.exception("resume_failed id=%s", question_id)
            return {"resumed": False, "retryable": True, "reason": code}

        if not out.get("ok"):
            code = _text(out.get("error"), 120) or "turn_failed"
            await self.repo.finish_continuation(user_id, question_id, ok=False, error=code)
            logger.warning("resume_failed id=%s reason=%s", question_id, code)
            return {"resumed": False, "retryable": True, "reason": code}

        await self.repo.finish_continuation(user_id, question_id, ok=True)
        logger.info("resume_completed id=%s session=%s", question_id, session_id)
        return {"resumed": True, "session_id": session_id}

    async def _restore_focus(self, user_id: str, q: OpenQuestion) -> None:
        """
        Hand the reasoning back the work it was on.

        This is the difference between resuming and re-reading. The session may
        have drifted — another conversation, another object — so the plan, the
        item and the object recorded when the question was asked are written
        back onto the session's own focus before the turn runs. The existing
        Life OS binding does it, so ownership is checked the same way it always
        is and no second write path appears.
        """
        if not (q.refs.plan_id or q.refs.object_id or q.refs.plan_item_id):
            return
        try:
            from life_os.service import LifeOsService

            await LifeOsService(self.db).bind_session_object_focus(
                user_id,
                session_id=q.refs.session_id or "",
                object_id=q.refs.object_id,
                plan_id=q.refs.plan_id,
                plan_item_id=q.refs.plan_item_id,
                event_type="question_resume",
            )
        except Exception:
            # A focus that could not be re-bound is worth continuing without:
            # the answer is still delivered into the right session.
            logger.info("resume focus rebind soft-fail id=%s", q.id, exc_info=True)

    async def _run_turn(self, user_id: str, q: OpenQuestion) -> Dict[str, Any]:
        """
        Deliver the answer into the thread that asked for it.

        Reusing the ordinary message path is the point: the answer lands in the
        conversation as a real turn, the transcript stays honest after a
        reload, and the message id makes a retried continuation reuse that turn
        instead of writing a second one.
        """
        from conversation_engine.ai_core.orchestrator import AICoreOrchestrator

        orch = AICoreOrchestrator(self.db)
        return await orch.message(
            user_id,
            str(q.refs.session_id),
            text=q.answer_raw or "",
            client_message_id=f"ans_{q.id}",
        )

    # ------------------------------------------------------------------
    # Lifecycle from the outside
    # ------------------------------------------------------------------

    async def cancel(self, user_id: str, question_id: str, *, reason: str = "user_cancelled") -> bool:
        doc = await self.repo.resolve(user_id, question_id, status="cancelled", reason=reason)
        if doc:
            logger.info("question_cancelled id=%s reason=%s", question_id, reason)
        return bool(doc)

    async def supersede(self, user_id: str, question_id: str, *, reason: str) -> bool:
        """ORA worked the answer out elsewhere; stop asking."""
        doc = await self.repo.resolve(user_id, question_id, status="superseded", reason=reason)
        if doc:
            logger.info("question_superseded id=%s reason=%s", question_id, reason)
        return bool(doc)

    async def resolve_by_knowledge(
        self,
        user_id: str,
        *,
        known_refs: Iterable[str],
        reason: str = "resolved_by_new_context",
    ) -> int:
        """
        Stop asking for something ORA has since found out.

        A question is a blocker, and a blocker that is no longer blocking has
        no business staying on someone's Home. When a document, a memory or an
        answer supplies what a question was waiting for, the question is
        superseded rather than left for the person to answer redundantly.

        Matching is by the reasoning's own opaque refs — the same handles the
        resume pointer recorded — so nothing here has to interpret text.
        """
        wanted = {str(r).strip() for r in known_refs if str(r).strip()}
        if not wanted:
            return 0
        closed = 0
        for row in await self.repo.list_open(user_id, limit=MAX_OPEN):
            asked = {str(r) for r in ((row.get("resume") or {}).get("asked_refs") or [])}
            requested = {
                str(v.get("ref")) for v in (row.get("requested_variables") or []) if v.get("ref")
            }
            covers = asked | requested
            # Every ref the question was waiting on must be known. Retiring a
            # bundled question because one of five values turned up would lose
            # the other four.
            if covers and covers.issubset(wanted):
                if await self.supersede(user_id, str(row.get("id")), reason=reason):
                    closed += 1
        return closed

    async def answered_in_the_thread(
        self, user_id: str, session_id: str, *, answer: str,
    ) -> int:
        """
        La persona ha risposto nella conversazione che aveva chiesto.

            UNA DOMANDA RISPOSTA NON RESTA IN HOME.

        Misurato sul vero (V3.21.3): si rispondeva nella chat e la stessa
        domanda restava aperta in Home, con il contatore sbagliato. Una domanda
        vive in una conversazione; un messaggio della persona in quella
        conversazione è la risposta. Se il lavoro ha ancora bisogno di qualcosa,
        il turno stesso farà nascere una domanda nuova.
        """
        if not session_id or not (answer or "").strip():
            return 0
        n = await self.repo.answer_in_thread(user_id, session_id, answer_raw=answer)
        if n:
            logger.info("question_answered_in_thread count=%d session=%s", n, session_id)
        return n

    async def reconcile_with_threads(self, user_id: str) -> int:
        """
        Chiude le domande a cui si è già risposto nella conversazione, prima che
        questa regola esistesse: se dopo la domanda la persona ha scritto nella
        stessa conversazione, la domanda è risposta.
        """
        chiuse = 0
        for row in await self.repo.list_open(user_id, limit=50):
            sessione = str(((row.get("refs") or {}).get("session_id")) or "")
            if not sessione:
                continue
            sess = await self.db.conversation_sessions.find_one(
                {"id": sessione, "user_id": user_id}, {"_id": 0, "history": 1},
            )
            dopo = [
                h for h in ((sess or {}).get("history") or [])
                if h.get("role") == "user" and str(h.get("at") or "") > str(row.get("created_at") or "")
            ]
            if dopo:
                chiuse += await self.repo.answer_in_thread(
                    user_id, sessione, answer_raw=str(dopo[0].get("text") or ""),
                    before=str(dopo[0].get("at") or ""),
                )
                continue
            #     E IL LAVORO FINITO NON ASPETTA PIÙ NIENTE.
            # «Vuoi che la chiami?» su una telefonata già fatta e già
            # raccontata non è una domanda: è una riga rimasta indietro.
            finita = await self.db.phone_calls.find_one({
                "owner_id": user_id,
                "chat_session_id": sessione,
                "state": {"$in": ["ended", "failed", "expired"]},
            })
            if finita:
                chiuse += await self.close_for_work(
                    user_id, session_id=sessione, reason="call_finished",
                )
        chiuse += await self._forget_finished_preparations(user_id)
        chiuse += await self._only_the_current_one(user_id)
        chiuse += await self._let_go_of_abandoned_threads(user_id)
        return chiuse

    # ------------------------------------------------------------------
    #     «DOMANDE PER TE» NON E' UNO STORICO.
    # Le tre regole qui sotto sono la differenza fra una lista di cose che ORA
    # aspetta adesso e l'archivio di tutto quello che ha chiesto una volta.
    # ------------------------------------------------------------------

    @staticmethod
    def _work_key(row: Dict[str, Any]) -> str:
        """
        Il lavoro a cui una domanda appartiene, con l'identificativo più forte.

        La preparazione di una telefonata viene prima della conversazione: la
        stessa preparazione può attraversare due chat, e resta un lavoro solo.
        """
        refs = row.get("refs") or {}
        for chiave in ("preparation_id", "plan_item_id", "plan_id", "object_id", "session_id"):
            valore = str(refs.get(chiave) or "").strip()
            if valore:
                return f"{chiave}:{valore}"
        return f"question:{row.get('id')}"

    async def _only_the_current_one(self, user_id: str) -> int:
        """Di ogni lavoro resta la domanda più recente. Le fasi prima si chiudono."""
        per_lavoro: Dict[str, list] = {}
        for row in await self.repo.list_open(user_id, limit=MAX_OPEN * 4):
            per_lavoro.setdefault(self._work_key(row), []).append(row)
        chiuse = 0
        for righe in per_lavoro.values():
            if len(righe) < 2:
                continue
            righe.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
            for vecchia in righe[1:]:
                if await self.supersede(
                    user_id, str(vecchia.get("id")), reason="replaced_by_newer_phase",
                ):
                    chiuse += 1
        return chiuse

    async def _forget_finished_preparations(self, user_id: str) -> int:
        """
        Una preparazione finita, o che non esiste più, non aspetta niente.

        Non si guarda il testo: si guarda la preparazione a cui la domanda è
        legata, e la telefonata che ne è nata.
        """
        chiuse = 0
        for row in await self.repo.list_open(user_id, limit=MAX_OPEN * 4):
            prep_id = str(((row.get("refs") or {}).get("preparation_id")) or "")
            if not prep_id:
                continue
            prep = await self.db.mission_preparations.find_one(
                {"preparation_id": prep_id, "owner_id": user_id}, {"_id": 0, "call_id": 1},
            )
            if prep is None:
                if await self.supersede(user_id, str(row.get("id")), reason="preparation_gone"):
                    chiuse += 1
                continue
            call_id = str(prep.get("call_id") or "")
            if not call_id:
                continue
            call = await self.db.phone_calls.find_one(
                {"id": call_id}, {"_id": 0, "state": 1},
            )
            if call and str(call.get("state")) in ("ended", "failed", "expired"):
                if await self.supersede(user_id, str(row.get("id")), reason="call_finished"):
                    chiuse += 1
        return chiuse

    async def _let_go_of_abandoned_threads(self, user_id: str) -> int:
        """
        Una domanda vecchia in una conversazione che nessuno ha più toccato non
        è qualcosa che ORA sta aspettando: è una riga rimasta indietro.

        Due giorni, e nessun messaggio nella conversazione da allora. Si
        chiude dicendo perché — `abandoned_thread` — non si cancella.
        """
        from datetime import datetime, timedelta, timezone

        limite = (datetime.now(timezone.utc) - timedelta(days=ABANDONED_AFTER_DAYS)).isoformat()
        chiuse = 0
        for row in await self.repo.list_open(user_id, limit=MAX_OPEN * 4):
            nata = str(row.get("created_at") or "")
            if not nata or nata >= limite:
                continue
            sessione = str(((row.get("refs") or {}).get("session_id")) or "")
            #     SI LASCIA ANDARE UN THREAD, NON UN LAVORO.
            # Una domanda che non nasce da una conversazione — da un piano, da
            # un oggetto — non ha un thread da abbandonare: la chiude chi la
            # riguarda, non il tempo.
            if not sessione:
                continue
            sess = await self.db.conversation_sessions.find_one(
                {"id": sessione, "user_id": user_id}, {"_id": 0, "history": 1},
            )
            #     «ANDATA AVANTI» VUOL DIRE CHE HA PARLATO LA PERSONA.
            # Guardare `updated_at` non funzionava: si muove anche quando a
            # scrivere è ORA — e ORA scrive proprio la domanda, un istante
            # prima che la domanda venga registrata. Ogni riga sembrava quindi
            # appartenere a una conversazione viva, e non si chiudeva mai
            # niente. Misurato sui dati veri: sette domande aperte, due di
            # conversazioni che nessuno aveva più ripreso.
            ultima_della_persona = max(
                [
                    str(h.get("at") or "")
                    for h in ((sess or {}).get("history") or [])
                    if h.get("role") == "user"
                ] or [""]
            )
            if ultima_della_persona > nata:
                # Ha risposto: se ne occupa la regola della risposta nel
                # thread, non questa.
                continue
            if await self.supersede(user_id, str(row.get("id")), reason="abandoned_thread"):
                chiuse += 1
        return chiuse

    async def close_for_work(
        self,
        user_id: str,
        *,
        plan_id: Optional[str] = None,
        plan_item_id: Optional[str] = None,
        session_id: Optional[str] = None,
        reason: str = "work_closed",
    ) -> int:
        """
        Work that has ended cannot still be waiting for something.

        Completing, cancelling or archiving a plan leaves its questions
        orphaned otherwise: a person keeps being asked about a decision that no
        longer has anything to decide.
        """
        match: Dict[str, Any] = {}
        if plan_item_id:
            match["refs.plan_item_id"] = plan_item_id
        elif plan_id:
            match["refs.plan_id"] = plan_id
        elif session_id:
            match["refs.session_id"] = session_id
        else:
            return 0
        n = await self.repo.resolve_where(
            user_id, match=match, status="cancelled", reason=reason
        )
        if n:
            logger.info("question_cancelled count=%d reason=%s", n, reason)
        return n


_SERVICE: Optional[WaitingService] = None


def get_waiting_service(db) -> WaitingService:
    global _SERVICE
    if _SERVICE is None or _SERVICE.db is not db:
        _SERVICE = WaitingService(db)
    return _SERVICE
