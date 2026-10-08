"""AI Core orchestrator — session lifecycle for the cognitive loop."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from copy import deepcopy
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from conversation_engine.ai_core.loop import DecisionFn, run_cognitive_loop
from conversation_engine.ai_core.activity import public_activity, report_activity
from conversation_engine.ai_core import state as state_mod
from conversation_engine.models import ConversationSession, new_session_id
from conversation_engine.repository import ConversationRepository

logger = logging.getLogger("ora.ai_core.orchestrator")


def _new_message_id() -> str:
    return f"msg_{uuid.uuid4().hex[:14]}"



# An ORA answer is stored whole enough to be read again.
#
# History used to keep 400 characters of it, which is fine for a summary line
# and wrong for the surface that replays the conversation: any articulate reply
# came back cut mid-sentence after a refresh, and "reconstruct the same
# conversation" was not something the data could support. Still bounded — a
# session document must not grow without limit — just bounded above the length
# of a real answer rather than below it.
ORA_HISTORY_TEXT_LIMIT = 4000

# Keep retry receipts bounded, without copying the whole conversation into
# every receipt. Older user entries retain the completion marker, so eviction
# cannot turn a duplicate request back into permission to execute it.
MESSAGE_RECEIPT_LIMIT = 20
MESSAGE_RECEIPT_MAX_BYTES = 96 * 1024


def _message_fingerprint(text: str, attachments: list, response_channel: str) -> str:
    request = {"text": text, "attachments": attachments, "response_channel": response_channel}
    encoded = json.dumps(request, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _record_message_result(sess: ConversationSession, mid: str, fingerprint: str, out: dict) -> None:
    entry = next((h for h in sess.history if h.role == "user" and
                  (h.step_id == mid or (h.meta or {}).get("message_id") == mid)), None)
    if entry is None:
        return
    entry.meta = {**(entry.meta or {}), "request_fingerprint": fingerprint, "result_recorded": True}
    response = deepcopy({key: value for key, value in out.items() if key != "history"})
    receipt = {"response": response, "history_length": len(sess.history)}
    if len(json.dumps(receipt, ensure_ascii=False, default=str).encode("utf-8")) <= MESSAGE_RECEIPT_MAX_BYTES:
        entry.meta["result_receipt"] = receipt
    else:
        entry.meta.pop("result_receipt", None)
    retained = [h for h in sess.history if h.role == "user" and (h.meta or {}).get("result_receipt")]
    for older in retained[:-MESSAGE_RECEIPT_LIMIT]:
        older.meta.pop("result_receipt", None)


def _replay_message_result(sess: ConversationSession, entry) -> Dict[str, Any]:
    receipt = (entry.meta or {}).get("result_receipt") or {}
    response = receipt.get("response")
    history_length = receipt.get("history_length")
    if not isinstance(response, dict) or not isinstance(history_length, int) or not 0 < history_length <= len(sess.history):
        # Legacy/evicted receipts must not silently repeat a completed write.
        return {"ok": False, "error": "message_result_unavailable"}
    out = deepcopy(response)
    snapshot = sess.model_copy(update={"history": sess.history[:history_length]})
    out["history"] = _public_history(snapshot)
    return out

def _public_attachments(meta: Optional[Dict[str, Any]]) -> list:
    """Attachment names for one past turn — display names only.

    The bind step stores the full ContextFile record on the history entry, and
    none of it belongs on a screen: file ids, document ids, previews and plan
    refs are how the system finds the file, not how a person recognises it. But
    dropping the whole meta, which is what the projections used to do, made the
    attachment vanish from the turn as soon as any response replaced the
    optimistic one — the user could no longer see what they had sent.
    """
    items = (meta or {}).get("attachments") or []
    out = []
    for a in items:
        if not isinstance(a, dict):
            continue
        name = str(a.get("name") or "").strip()[:120]
        if name:
            out.append({"name": name, "text_available": bool(a.get("text_available"))})
    return out[:6]


def _ui_actions(actions) -> list:
    """Project only destinations that this client knows how to open."""
    out = []
    for action in (actions or [])[:3]:
        if not isinstance(action, dict):
            continue
        if action.get("kind") == "amazon_search":
            url = str(action.get("url") or "")
            try:
                parsed = urlparse(url)
                if parsed.scheme == "https" and parsed.netloc == "www.amazon.it" and parsed.path == "/s" and parse_qs(parsed.query).get("k") and len(url) <= 600:
                    out.append({"kind": "amazon_search", "label": "Apri la ricerca su Amazon", "url": url})
            except ValueError:
                continue
        elif action.get("kind") == "workspace":
            plan_id = str(action.get("plan_id") or "")
            if re.fullmatch(r"lop_[A-Za-z0-9_-]{4,76}", plan_id):
                out.append({"kind": "workspace", "label": "Apri il piano", "plan_id": plan_id})
    return out[:2]


def _answer_meta(message_id: str, result) -> dict:
    meta = {"message_id": message_id}
    for key, limit in (("sources", 5), ("navigation", 3)):
        values = getattr(result, key, None) or []
        if values:
            meta[key] = [v for v in values[:limit] if isinstance(v, dict)]
    journey = getattr(result, "journey", None)
    if isinstance(journey, dict) and journey:
        meta["journey"] = journey
    actions = _ui_actions(getattr(result, "ui_actions", None))
    if actions:
        meta["ui_actions"] = actions
    return meta


def _public_history(sess: ConversationSession) -> list:
    turns = []
    for h in (sess.history or [])[-40:]:
        meta = h.meta or {}
        display_meta = {key: meta[key] for key in ("sources", "navigation", "journey") if meta.get(key)}
        attachments = _public_attachments(meta)
        if attachments:
            display_meta["attachments"] = attachments
        actions = _ui_actions(meta.get("ui_actions"))
        if actions:
            display_meta["ui_actions"] = actions
        turns.append({
            "role": h.role, "text": h.text, "kind": h.kind,
            "message_id": h.step_id or meta.get("message_id"), "at": h.at,
            "meta": display_meta or None,
        })
    return turns


class AICoreOrchestrator:
    def __init__(self, db, *, decision_fn: Optional[DecisionFn] = None):
        self.db = db
        self.repo = ConversationRepository(db)
        self.decision_fn = decision_fn

    async def _observed_turn(self, **kwargs):
        sess = kwargs["sess"]
        await report_activity(self.db, sess, "processing", reset=not kwargs.get("resume_client", False))
        phase = "error"
        try:
            result = await run_cognitive_loop(**kwargs)
            phase = "error" if result.error else "done"
            return result
        finally:
            await report_activity(self.db, sess, phase, keep_area=True)

    async def start(
        self,
        user_id: str,
        *,
        text: str,
        origin: str = "text",
        entry_point: Optional[str] = None,
        plan_id: Optional[str] = None,
        object_id: Optional[str] = None,
        opportunity_id: Optional[str] = None,
        attachments: Optional[list] = None,
        activity_request_id: Optional[str] = None,
        response_channel: str = "text",
    ) -> Dict[str, Any]:
        text = (text or "").strip()
        attachments = list(attachments or [])
        if not text and not attachments:
            return {"ok": False, "error": "text_required"}

        ep = (entry_point or origin or "text").strip()[:40]
        sess = ConversationSession(
            id=new_session_id(),
            user_id=user_id,
            origin=(
                origin
                if origin
                in (
                    "home",
                    "voice",
                    "text",
                    "documents",
                    "notifications",
                    "proactive",
                    "life_setup",
                    "memoria",
                )
                else "text"
            ),
            input=text or "[attachment]",
            status="waiting_user",
            engine_version="ai-core-1.0",
            meta={
                "ui_mode": "ai_core",
                "ai_core": {},
                "entry_point": ep,
                "activity_request_id": activity_request_id,
                "response_channel": "voice" if response_channel == "voice" else "text",
            },
        )
        if opportunity_id:
            # What the thread is about, so the reasoning does not have to guess
            # from a first message that assumes ORA already knows. Bound, never
            # acted on: "vediamo" opens a conversation, it does not accept
            # anything.
            state_mod.get_ai_state(sess)["active_opportunity_id"] = str(
                opportunity_id
            )[:64]

        # Soft-bind opaque Life OS refs on in-memory session (ownership enforced on later bind/get)
        if plan_id or object_id:
            st = state_mod.get_ai_state(sess)
            if plan_id:
                st["active_plan_id"] = str(plan_id)[:64]
            if object_id:
                st["active_object_ref"] = {
                    "id": str(object_id)[:64],
                    "source": "entry_bind",
                }
            state_mod.save_ai_state(sess, st)

        # Persist session early so ContextFile can bind ownership-scoped refs
        await self.repo.insert(sess)

        bound: list = []
        if attachments:
            try:
                from conversation_engine.ai_core.files.service import ContextFileService

                bound = await ContextFileService(self.db).bind_message_attachments(
                    sess, attachments
                )
            except Exception:
                logger.exception("start bind attachments soft-fail")

        user_msg = text
        if not user_msg and bound:
            names = ", ".join(
                (b.get("name") or b.get("file_id") or "file")[:60] for b in bound[:3]
            )
            user_msg = f"[Allegato: {names}]"
        user_mid = _new_message_id()
        sess.append_history(
            role="user",
            kind="start",
            text=(text or user_msg)[:400],
            step_id=user_mid,
            meta=(
                {"attachments": bound, "message_id": user_mid}
                if bound
                else {"message_id": user_mid}
            ),
        )
        from conversation_engine.ai_core.amazon_handoff import explicit_amazon_handoff
        result = await explicit_amazon_handoff(user_msg) if not bound else None
        if result is None:
            result = await self._observed_turn(
                sess=sess,
                user_message=user_msg,
                db=self.db,
                decision_fn=self.decision_fn,
            )
        if (result.ora_text or "").strip():
            ora_mid = _new_message_id()
            sess.append_history(
                role="ora",
                kind=result.mode,
                text=result.ora_text[:ORA_HISTORY_TEXT_LIMIT],
                step_id=ora_mid,
                meta=_answer_meta(ora_mid, result),
            )
            st = state_mod.get_ai_state(sess)
            if not (getattr(result, "client_actions", None) or []):
                state_mod.clear_pending_turn(st, status="completed")
                state_mod.save_ai_state(sess, st)
        sess.summary = (
            result.active_goal.summary if result.active_goal else ""
        ) or user_msg[:120]
        sess.status = "waiting_user"
        #     FINITO IL TURNO, NON STA PIÙ FACENDO NIENTE.
        sess.meta = {k: v for k, v in (sess.meta or {}).items() if k != "working_on"}
        durable = await self._persist_blocking_ask(sess, result)
        # A blocking question the person can see must already exist in the
        # database. Returning before `replace` is what enforces that: the
        # assistant turn is still only in memory here, so nothing was shown and
        # nothing needs undoing. The client retries the same message id, the
        # same reasoning produces the same dedupe key, and one question is
        # created — not a second.
        if durable == "failed":
            return {"ok": False, "error": "blocking_question_not_durable"}
        # Observability (no PII)
        meta = dict(sess.meta or {})
        meta["entry_point"] = ep
        meta["session_created"] = True
        meta["had_plan_ref"] = bool(plan_id)
        meta["had_object_ref"] = bool(object_id)
        meta["had_attachments"] = bool(bound)
        sess.meta = meta
        await self.repo.replace(sess)
        # Authoritative ownership bind after persist (plan/object must belong to user)
        if plan_id or object_id:
            try:
                from life_os.service import LifeOsService

                await LifeOsService(self.db).bind_session_object_focus(
                    user_id,
                    session_id=sess.id,
                    object_id=object_id,
                    plan_id=plan_id,
                    event_type="entry_bind",
                )
            except Exception:
                logger.debug("post-insert entry bind soft-fail", exc_info=True)
        out = self._public(sess, result)
        if bound:
            out["attachments"] = bound
        return out

    async def _persist_blocking_ask(self, sess, result) -> str:
        """
        Turn a blocking question into something that outlives the conversation.

        The reasoning has already decided it cannot proceed and named the
        information it is missing. What it has no way to do is remember that
        across a closed app, a restarted process or a different screen — so the
        question, the work it belongs to, and the point to continue from are
        written down here, from the session's own focus rather than from
        anything a client said.

        Returns `"none"` when this turn was not a blocker, `"ok"` when the
        question is durable, and `"failed"` when it is not.

        The last case is deliberately not swallowed. A blocking question the
        person can see but the database never took is the worst state this
        design can produce: it looks exactly like a question ORA is waiting on,
        it appears nowhere on Home or Attività, and it is gone the moment the
        page reloads. The turn fails instead, and the caller retries — which is
        safe, because the same reasoning produces the same dedupe key.
        """
        ask = getattr(result, "blocking_ask", None)
        if not isinstance(ask, dict) or not (ask.get("question") or "").strip():
            return "none"
        try:
            from waiting.models import ResumePointer, WorkRefs
            from waiting.service import get_waiting_service

            st = state_mod.get_ai_state(sess)
            item_ref = st.get("current_plan_item_ref") or {}
            obj_ref = st.get("active_object_ref") or {}
            situation = st.get("active_situation_ref") or {}
            goal = st.get("active_goal") or {}

            plan_id = str(st.get("active_plan_id") or "") or None
            object_id = str(obj_ref.get("id") or "") or None
            # The step the question actually came from, when guidance said so.
            # The session's focus is where this used to come from, and it is
            # only the same step by coincidence: a question about scheduling a
            # meeting was filed — and shown — under "definire la data esatta di
            # fine rapporto", because that was the plan item in focus.
            step_title = str(ask.get("step_title") or "").strip()
            step_item_id = str(ask.get("plan_item_id") or "").strip() or None
            refs = WorkRefs(
                session_id=sess.id,
                plan_id=plan_id,
                plan_item_id=step_item_id or str(item_ref.get("id") or "") or None,
                object_id=object_id,
                situation_id=str(situation.get("id") or "") or None,
                preparation_id=str(st.get("active_preparation_id") or "") or None,
            )
            # What sort of thread this is, so a resume knows what it is
            # resuming without having to inspect the refs itself.
            kind = "plan_work" if plan_id else ("object_work" if object_id else "conversation")
            resume = ResumePointer(
                kind=kind,
                target_id=refs.plan_item_id or plan_id or object_id or sess.id,
                reasoning_epoch=str(st.get("reasoning_epoch") or "") or None,
                goal_summary=str(goal.get("summary") or "")[:400],
                asked_refs=[str(r)[:120] for r in (ask.get("asked_refs") or [])][:8],
                focus={
                    "plan_item_title": (
                        step_title[:120] or str(item_ref.get("title") or "")[:120]
                    ),
                    "object_kind": str(obj_ref.get("source") or "")[:60],
                    "sensitive": bool(ask.get("sensitive")),
                },
            )
            saved = await get_waiting_service(self.db).record_blocking_question(
                sess.user_id,
                question=ask.get("question") or "",
                why_needed=ask.get("why_needed") or "",
                # Human words for the work, never an id: the plan item first,
                # then the goal it belongs to.
                context_label=(
                    step_title[:160]
                    or str(item_ref.get("title") or "")[:160]
                    or str(goal.get("summary") or "")[:160]
                ),
                expected_answer_kind=(
                    "bundle" if ask.get("answer_kind") == "bundle" else "free_text"
                ),
                refs=refs,
                resume=resume,
                # Present only when guidance bundled several things the same
                # next step needs. A partial answer is then legible: what is
                # still missing can be asked, and what was given cannot be.
                requested_variables=list(ask.get("requested_variables") or []),
            )
        except Exception:
            logger.exception("question_persist_failed session=%s", sess.id)
            return "failed"
        # `None` means the service found nothing durable to point at — an empty
        # question, or the losing side of an insert race whose winner has since
        # gone. Either way there is no open question, so there is no blocking
        # question to show.
        if not saved:
            logger.warning("question_persist_empty session=%s", sess.id)
            return "failed"
        return "ok"

    async def message(
        self,
        user_id: str,
        session_id: str,
        *,
        text: str,
        attachments: Optional[list] = None,
        activity_request_id: Optional[str] = None,
        response_channel: str = "text",
        client_message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        text = (text or "").strip()
        attachments = list(attachments or [])
        if not text and not attachments:
            return {"ok": False, "error": "text_required"}
        client_id = (client_message_id or "").strip()
        if len(client_id) > 64:
            return {"ok": False, "error": "invalid_client_message_id"}
        response_channel = "voice" if response_channel == "voice" else "text"
        sess = await self.repo.get(user_id, session_id)
        if not sess:
            return {"ok": False, "error": "not_found"}
        if sess.status in ("completed", "cancelled"):
            return {"ok": False, "error": "session_closed"}
        mid = client_id or _new_message_id()
        fingerprint = _message_fingerprint(text, attachments, response_channel)
        previous = next((h for h in sess.history if h.role == "user" and
                         (h.step_id == mid or (h.meta or {}).get("message_id") == mid)), None)
        if previous is not None:
            saved_fingerprint = (previous.meta or {}).get("request_fingerprint")
            if saved_fingerprint and saved_fingerprint != fingerprint:
                return {"ok": False, "error": "client_message_id_conflict"}
            if (previous.meta or {}).get("result_recorded"):
                return _replay_message_result(sess, previous)
            if not saved_fingerprint:
                # A pre-receipt session cannot prove which result belongs to
                # this id. Never guess using the latest assistant response.
                return {"ok": False, "error": "message_result_unavailable"}
        sess.meta["activity_request_id"] = activity_request_id
        sess.meta["response_channel"] = "voice" if response_channel == "voice" else "text"

        # Bind attachments before cognition (ownership enforced)
        bound: list = []
        if attachments:
            try:
                from conversation_engine.ai_core.files.service import ContextFileService

                bound = await ContextFileService(self.db).bind_message_attachments(
                    sess, attachments
                )
            except Exception:
                logger.exception("bind attachments soft-fail")
                bound = []

        user_msg = text
        if not user_msg and bound:
            names = ", ".join(
                (b.get("name") or b.get("file_id") or "file")[:60] for b in bound[:3]
            )
            user_msg = f"[Allegato: {names}]"

        # A new id is a new request, even when the text is identical. The
        # complete request hash also distinguishes text beyond history's cap.
        if previous is None:
            hist_meta: Dict[str, Any] = {"message_id": mid, "request_fingerprint": fingerprint}
            if bound:
                hist_meta["attachments"] = bound
            sess.append_history(
                role="user",
                kind="answer",
                text=(text or user_msg)[:400],
                step_id=mid,
                meta=hist_meta,
            )
            #     LA RISPOSTA NELLA CONVERSAZIONE CHIUDE LA DOMANDA IN HOME.
            # V3.21.3: prima restava aperta finché qualcuno non premeva
            # «Rispondi» dalla Home. Soft: la conversazione non si ferma se
            # questa scrittura non riesce.
            try:
                from waiting.service import get_waiting_service

                await get_waiting_service(self.db).answered_in_the_thread(
                    sess.user_id, sess.id, answer=(text or user_msg),
                )
            except Exception as e:  # pragma: no cover
                logger.info("open questions not closed: %s", type(e).__name__)

        from conversation_engine.ai_core.amazon_handoff import explicit_amazon_handoff
        result = await explicit_amazon_handoff(user_msg) if not bound else None
        if result is None:
            result = await self._observed_turn(
                sess=sess,
                user_message=user_msg,
                db=self.db,
                decision_fn=self.decision_fn,
            )
        # Memory candidates are governed inside the cognitive loop. Keeping a
        # second pending queue would create a competing, unaudited write path.

        if (result.ora_text or "").strip():
            ora_mid = _new_message_id()
            sess.append_history(
                role="ora",
                kind=result.mode,
                text=result.ora_text[:ORA_HISTORY_TEXT_LIMIT],
                step_id=ora_mid,
                meta=_answer_meta(ora_mid, result),
            )
            if not (getattr(result, "client_actions", None) or []):
                st = state_mod.get_ai_state(sess)
                state_mod.clear_pending_turn(st, status="completed")
                state_mod.save_ai_state(sess, st)
        sess.status = "waiting_user"
        #     FINITO IL TURNO, NON STA PIÙ FACENDO NIENTE.
        sess.meta = {k: v for k, v in (sess.meta or {}).items() if k != "working_on"}
        durable = await self._persist_blocking_ask(sess, result)
        # A blocking question the person can see must already exist in the
        # database. Returning before `replace` is what enforces that: the
        # assistant turn is still only in memory here, so nothing was shown and
        # nothing needs undoing. The client retries the same message id, the
        # same reasoning produces the same dedupe key, and one question is
        # created — not a second.
        if durable == "failed":
            return {"ok": False, "error": "blocking_question_not_durable"}
        out = self._public(sess, result)
        if bound:
            out["attachments"] = bound
        st = state_mod.get_ai_state(sess)
        if client_id and out.get("client_actions"):
            st["pending_client_message_id"] = mid
        else:
            st.pop("pending_client_message_id", None)
        state_mod.save_ai_state(sess, st)
        if client_id:
            _record_message_result(sess, mid, fingerprint, out)
        # The result and its receipt become durable in the same session write.
        # A crash before this write is not a completed request: this does not
        # claim transactional exactly-once semantics for external side effects.
        await self.repo.replace(sess)
        return out

    async def client_resume(
        self,
        user_id: str,
        session_id: str,
        *,
        completed: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Continue cognition after client-side capability (e.g. foreground GPS)."""
        sess = await self.repo.get(user_id, session_id)
        if not sess:
            return {"ok": False, "error": "not_found"}
        if sess.status in ("completed", "cancelled"):
            return {"ok": False, "error": "session_closed"}
        st = state_mod.get_ai_state(sess)
        resumed_message_id = st.get("pending_client_message_id")
        pending = (st.get("pending_client_resume_message") or "").strip()
        if not pending:
            for h in reversed(sess.history or []):
                matches_request = not resumed_message_id or h.step_id == resumed_message_id or (h.meta or {}).get("message_id") == resumed_message_id
                if h.role == "user" and matches_request and (h.text or "").strip():
                    pending = h.text.strip()
                    break
        if not pending:
            return {"ok": False, "error": "nothing_to_resume"}
        st["pending_client_resume_message"] = None
        st["client_actions_completed"] = list(completed or [])[-8:]
        state_mod.save_ai_state(sess, st)

        result = await self._observed_turn(
            sess=sess,
            user_message=pending,
            db=self.db,
            decision_fn=self.decision_fn,
            resume_client=True,
        )
        st = state_mod.get_ai_state(sess)

        if (result.ora_text or "").strip():
            ora_mid = _new_message_id()
            sess.append_history(
                role="ora",
                kind=result.mode,
                text=result.ora_text[:ORA_HISTORY_TEXT_LIMIT],
                step_id=ora_mid,
                meta=_answer_meta(ora_mid, result),
            )
        more_actions = list(getattr(result, "client_actions", None) or [])
        st = state_mod.get_ai_state(sess)
        if more_actions:
            pt = dict(st.get("pending_turn") or {})
            pt["status"] = "awaiting_client"
            pt["client_actions"] = more_actions
            if not pt.get("id"):
                pt["id"] = f"pt_{uuid.uuid4().hex[:12]}"
            st["pending_turn"] = pt
            st["pending_client_resume_message"] = pending
            state_mod.save_ai_state(sess, st)
        elif (result.ora_text or "").strip():
            state_mod.clear_pending_turn(st, status="completed")
            state_mod.save_ai_state(sess, st)
        sess.status = "waiting_user"
        #     FINITO IL TURNO, NON STA PIÙ FACENDO NIENTE.
        sess.meta = {k: v for k, v in (sess.meta or {}).items() if k != "working_on"}
        out = self._public(sess, result)
        # Client capability completion belongs to the same user request. A
        # later retry must return this saved continuation, not stale GPS work.
        # The pointer was persisted when the action was first handed off; the
        # latest history entry alone cannot prove which request is resuming.
        previous = next((h for h in sess.history if h.role == "user" and resumed_message_id and
                         (h.step_id == resumed_message_id or (h.meta or {}).get("message_id") == resumed_message_id)), None)
        if previous is not None and (previous.meta or {}).get("result_recorded"):
            _record_message_result(
                sess, resumed_message_id,
                previous.meta["request_fingerprint"], out,
            )
        if not out.get("client_actions"):
            st = state_mod.get_ai_state(sess)
            st.pop("pending_client_message_id", None)
            state_mod.save_ai_state(sess, st)
        await self.repo.replace(sess)
        return out

    async def get(self, user_id: str, session_id: str) -> Dict[str, Any]:
        sess = await self.repo.get(user_id, session_id)
        if not sess:
            return {"ok": False, "error": "not_found"}
        st = state_mod.get_ai_state(sess)
        last = None
        for h in reversed(sess.history or []):
            if h.role == "ora" and h.text:
                last = h.text
                break
        pending = state_mod.public_pending_turn(st)
        return {
            "ok": True,
            "session_id": sess.id,
            "ora_text": last or "",
            "active_goal": st.get("active_goal"),
            "active_plan_id": st.get("active_plan_id"),
            "active_goal_id": st.get("active_goal_id"),
            "active_situation": st.get("active_situation_ref"),
            "artifact_ids": list(st.get("artifact_ids") or [])[-12:],
            "history": _public_history(sess),
            "pending_turn": pending,
            "client_actions": (
                list(pending.get("client_actions") or [])
                if pending.get("status") == "awaiting_client"
                else []
            ),
            "ui_mode": "ai_core",
            "route": f"/ora/{sess.id}",
            "entry_point": (sess.meta or {}).get("entry_point"),
        }

    def _public(self, sess: ConversationSession, result) -> Dict[str, Any]:
        st = state_mod.get_ai_state(sess)
        pending = state_mod.public_pending_turn(st)
        actions = list(getattr(result, "client_actions", None) or [])
        if not actions and pending.get("status") == "awaiting_client":
            actions = list(pending.get("client_actions") or [])
        return {
            "ok": True,
            "session_id": sess.id,
            "ora_text": result.ora_text,
            "display_focus_ref": getattr(result, "display_focus_ref", None),
            "question": result.question,
            "mode": result.mode,
            "active_goal": (
                result.active_goal.model_dump() if result.active_goal else None
            ),
            "memory_candidates": [m.model_dump() for m in result.memory_candidates],
            "situation": getattr(result, "situation", None)
            or st.get("active_situation_ref"),
            "ui_mode": "ai_core",
            "route": f"/ora/{sess.id}",
            "entry_point": (sess.meta or {}).get("entry_point"),
            "ai_calls": result.ai_calls,
            "tool_calls": result.tool_calls,
            "context_calls": result.context_calls,
            "external_queries": getattr(result, "external_queries", 0) or 0,
            "elapsed_ms": result.elapsed_ms,
            "sources": list(getattr(result, "sources", None) or [])[:5],
            # The map apps ORA offered, if it offered any. Same channel as
            # sources and for the same reason: something the answer refers to
            # that the person has to be able to actually reach. A sentence
            # ending "con quale app vuoi navigare?" beside no buttons is a
            # question nobody can answer.
            "navigation": list(getattr(result, "navigation", None) or [])[:3],
            "ui_actions": _ui_actions(getattr(result, "ui_actions", None)),
            # Come arrivarci, confrontato: la chat lo disegna come modulo.
            "journey": dict(getattr(result, "journey", None) or {}),
            "working_hint": getattr(result, "working_hint", None),
            "activity": public_activity(sess.meta),
            "client_actions": actions,
            "pending_turn": pending,
            "trace": result.trace,
            "error": result.error,
            "history": _public_history(sess),
        }
