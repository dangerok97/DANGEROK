"""
The one door between the outside world and everything ORA already is.

    LIFE → PERSONAL LIFE MODEL → UNDERSTANDING → ACTION.

The temptation this file exists against is building a second ORA for
connected data: its own reviewer, its own goals, its own way of reaching
somebody. That is how a product ends up with a "Google Calendar" section that
knows things the rest of it does not.

So there is no new engine here. What happens is a translation and a knock on
an existing door:

    provider → ingestion (V2.8) → signal (new) → judgement (new)
      → MeaningfulChange (V3.7) → AmbientWake (V3.8) → agent (V3.9)

The change log, the wake, the opportunity review, the goal decision, the
delivery judgement and the authority ceiling are all already built and all
already tested. Connected Life speaks to them; it does not replace any of
them, and there is deliberately nowhere in this file that creates a goal.

    THE CODE PRODUCES THE SIGNAL. THE AI DECIDES WHETHER IT MEANS ANYTHING.
    NO GOAL IS EVER CREATED BY AN `IF`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from connected.models import ConnectedSignal, ConnectedSource, now_iso
from connected.signals import SignalService
from connected.sources import ATTEMPTS, SourceRegistry

logger = logging.getLogger("ora.connected")

# How soon after a change worth looking at the agent is asked to look. Not
# immediately: a person moving three appointments in a row should produce one
# think, not three, and the wake layer coalesces what arrives in the same
# window.
WAKE_DELAY_SECONDS = 90

# How many judgements one pass will pay for. The bound is the point: a
# fortnight of catching up must not become a fortnight of model calls.
MAX_INTERPRETED = 6

# How many link judgements one pass will pay for. Lower than the number of
# interpretations because linking is the second call about the same event,
# and a pass that interpreted six things does not need to relate all six.
MAX_LINKED = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ConnectedLifeService:
    def __init__(self, db):
        self.db = db
        self.sources = SourceRegistry(db)
        self.signals = SignalService(db)

    async def ensure_indexes(self) -> None:
        from connected import content, situations
        from connected.seen import SeenState

        await self.sources.ensure_indexes()
        await self.signals.ensure_indexes()
        await SeenState(self.db).ensure_indexes()
        await content.ensure_indexes(self.db)
        await situations.ensure_indexes(self.db)

    # --- looking ----------------------------------------------------------

    async def sync(self, owner_id: str, source_id: str) -> Dict[str, Any]:
        """
        Read one instrument, and turn what moved into observations.

            A FAILED READING IS NOT AN EMPTY WORLD.

        Every exit from here leaves the source honest about itself. That is
        the whole reason this wraps the connector rather than calling it
        directly from a scheduler: a sync that throws must leave a source
        saying "I could not read this", never a source saying nothing and a
        world that looks empty.
        """
        source = await self.sources.get(owner_id, source_id)
        if source is None:
            return {"ok": False, "reason": "unknown_source"}
        if not source.is_readable:
            return {"ok": False, "reason": "not_connected", "state": source.status}

        await self.sources.note_attempt(owner_id, source_id)
        watermark = await self._watermark(owner_id, source_id)

        try:
            if source.source_type == "email":
                await self._sync_mail(owner_id, source)
                from connected import email_sensor

                observed = await email_sensor.read_changes(
                    self.db, owner_id, source_id=source_id, since=watermark,
                )
            elif source.source_type == "calendar":
                await self._sync_calendar(owner_id, source)
                from connected import calendar_sensor

                observed = await calendar_sensor.read_changes(
                    self.db, owner_id, source_id=source_id, since=watermark,
                    # Which account this is, so "who organised it" can be
                    # compared against "who this person is". Without it every
                    # invitation looks like their own arrangement.
                    account=source.account_ref,
                )
            elif source.source_type == "bank":
                await self._sync_bank(owner_id, source)
                # I movimenti diventano osservazioni bancarie, non segnali:
                # sono di un'altra natura e vivono nel loro registro. Quello
                # che ne esce lo decide il giudizio finanziario, altrove.
                observed = []
            else:
                from connected import documents_sensor

                observed = await documents_sensor.read_changes(
                    self.db, owner_id, since=watermark,
                )
        except Exception as e:
            logger.info("sync failed source=%s: %s", source_id, type(e).__name__)
            await self.sources.note_failure(owner_id, source_id, error=type(e).__name__)
            return {"ok": False, "reason": "sync_failed", "state": "degraded"}

        recorded = 0
        deduped = 0
        for signal in observed:
            kept, what = await self.signals.record(signal)
            if kept is None:
                deduped += 1
            else:
                recorded += 1

        await self.sources.note_success(owner_id, source_id)
        await self._set_watermark(owner_id, source_id, observed)
        logger.info(
            "connected sync source=%s seen=%d recorded=%d deduped=%d",
            source.source_type, len(observed), recorded, deduped,
        )
        return {
            "ok": True, "seen": len(observed),
            "recorded": recorded, "deduped": deduped,
        }

    async def _sync_mail(self, owner_id: str, source: ConnectedSource) -> None:
        """
        Ask the mailbox for a reading, incrementally.

        The connector owns the history cursor and the resync-after-expiry
        rule, exactly as the calendar connector owns its sync token. What
        this layer knows about a mailbox is what it knows about any
        instrument: whether reading it worked.
        """
        from deps import get_gmail_service

        await get_gmail_service().sync(user_id=owner_id, instance_id=source.id)

    async def _sync_bank(self, owner_id: str, source: ConnectedSource) -> None:
        """
        Chiedi alla banca cosa e' successo. Il connettore sa come.

        Stessa forma del calendario e della casella: questo livello sa solo
        se la lettura e' riuscita, e il connettore possiede il proprio
        segnaposto — un secondo cursore qui sarebbe un secondo posto da
        tenere in fila con il primo.
        """
        import deps
        from connectors.bank.service import BankReadService

        service = BankReadService(
            db=self.db,
            permissions=deps.get_permissions_service(),
            vault=deps.get_token_vault(),
        )
        read = await service.sync(user_id=owner_id, instance_id=source.id)

        # E poi, se sono arrivate righe nuove, si prova a capirle — a gruppi.
        #
        #     SEI BONIFICI UGUALI SONO UNA DOMANDA, NON SEI.
        #
        # Il raggruppamento e' aritmetico e sta altrove; qui si sa solo che
        # dopo una lettura c'e' qualcosa di nuovo da guardare, e che
        # guardarlo e' parte del mestiere di ORA e non un compito della
        # persona. Se il giudizio non e' disponibile la lettura resta
        # comunque valida: le osservazioni sono gia' scritte.
        if not read.get("ok") or not (read.get("written") or read.get("updated")):
            return
        try:
            from financial.batching import read_what_is_new

            await read_what_is_new(self.db, owner_id)
        except Exception as e:
            logger.info("bank interpretation soft-fail: %s", type(e).__name__)

    async def _sync_calendar(self, owner_id: str, source: ConnectedSource) -> None:
        """
        Ask the connector for a reading, incrementally.

        The connector already holds a per-calendar sync token and already
        knows how to page. Re-implementing either here would be a second
        cursor to keep in step with the first, and the two would diverge on
        the first partial failure.
        """
        from deps import get_google_calendar_service

        gcal = get_google_calendar_service()
        result = await gcal.sync(user_id=owner_id, instance_id=source.id)
        if (result.get("totals") or {}).get("failed"):
            raise RuntimeError("calendar_sync_incomplete")

    # --- understanding ----------------------------------------------------

    async def interpret(
        self, owner_id: str, *, limit: int = MAX_INTERPRETED, language: str = "it",
    ) -> Dict[str, Any]:
        """
        Ask what the pending observations mean, and pass on the ones that do.

        The routing below is the only place Connected Life touches the rest
        of ORA, and every branch ends in something that already existed. What
        it never does is decide: `noise` is the model's word, `may_need_action`
        is the model's word, and the difference between them is not computed
        anywhere in this file.
        """
        pending = await self.signals.pending(owner_id, limit=limit)
        if not pending:
            return {"ok": True, "looked_at": 0, "noise": 0, "passed_on": 0}

        from connected.reasoning import interpret_signal

        life = await self._life(owner_id)
        sources = {s.id: s for s in await self.sources.list(owner_id)}
        looked_at = noise = passed_on = own = asked_for_content = linked = 0

        for signal in pending:
            # ORA's own work coming back round. Recorded as seen, never
            # passed on: an effect this system produced is not news about the
            # world, and treating it as news is how an agent ends up doing
            # the same thing twice.
            if signal.origin == "self_originated":
                await self.signals.settle(
                    owner_id, signal.id, outcome="own_work_confirmed"
                )
                own += 1
                continue

            source = sources.get(signal.source_id)
            recent = [
                s.for_ai() for s in
                await self.signals.history(owner_id, signal.source_object_ref, limit=3)
                if s.id != signal.id
            ]
            answer = await interpret_signal(
                signal.for_ai(),
                life=life,
                source=source.for_ai() if source else {},
                recent=recent,
                language=language,
            )
            looked_at += 1

            if answer is None:
                # No judgement available — a provider outage, a refusal, a
                # malformed reply. Left pending on purpose: silence here is a
                # missing answer, not an answer of "nothing", and the signal
                # will be asked about again.
                #
                # This check sits above everything that reads the answer, and
                # that placement is the whole point: it was once below the
                # re-ask block, where the first outage would have crashed the
                # pass on `None.get` instead of leaving the world untouched.
                continue

            # It said it cannot decide without seeing what was withheld.
            #
            #     WITHHELD IS NOT UNREACHABLE. IT IS UNKEPT.
            #
            # Fetched here, once, put in front of one call, and gone. The
            # local name below is the only place it ever lives: nothing in
            # this branch stores it, and the audit row records that a read
            # happened without recording what was read.
            if answer.get("needs_content"):
                from connected import content as private

                seen_content = await private.read_transiently(
                    self.db, owner_id, signal,
                    why=str(answer.get("why_content") or answer.get("reasoning") or "")[:200],
                )
                if seen_content:
                    second = await interpret_signal(
                        signal.for_ai(),
                        life=life,
                        source=source.for_ai() if source else {},
                        recent=recent,
                        language=language,
                        content=seen_content,
                    )
                    looked_at += 1
                    asked_for_content += 1
                    if second is not None:
                        answer = second

            outcome = answer["outcome"]
            if outcome == "noise":
                await self.signals.skip(owner_id, signal.id, why="noise")
                noise += 1
                continue

            # Whether this is about something already known. Asked only for
            # observations that meant something — linking noise to anything
            # would be paying a judgement to relate a thing nobody needed to
            # hear about — and bounded per pass, because a fortnight of
            # catching up must not become a fortnight of link calls.
            link = None
            if linked < MAX_LINKED:
                link = await self._link_to_what_is_known(owner_id, signal, answer, life)
                if link is not None:
                    linked += 1

            await self._pass_on(owner_id, signal, answer, link=link)
            await self.signals.settle(owner_id, signal.id, outcome=outcome)
            passed_on += 1

        return {
            "ok": True, "looked_at": looked_at, "noise": noise,
            "passed_on": passed_on, "own_work": own,
            "asked_for_content": asked_for_content,
            "linked": linked,
        }

    async def _link_to_what_is_known(
        self, owner_id: str, signal: ConnectedSignal, answer: Dict[str, Any],
        life: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Ask whether this is another angle on something already known.

            MULTIPLE SOURCES CAN REFER TO THE SAME THING IN A PERSON'S LIFE.

        Code gathers what is nearby and hands it over as facts; the model
        decides the relationship. The two halves are kept apart on purpose,
        and the seam is visible here: everything above this line is
        retrieval, everything below it is a recorded answer, and there is no
        branch in between where code picks a target.
        """
        from connected import situations
        from connected.reasoning import decide_link

        candidates = await situations.candidates_for(self.db, owner_id, signal)
        if not candidates:
            return None

        # Disagreements travel with the candidate they are about, so the
        # judgement sees "the calendar says 10, this says 16, and here is
        # when each was observed" rather than a single reconciled time that
        # somebody's code chose.
        shown = [
            dict(c, disagreements=situations.disagreements_between(signal, c))
            for c in candidates
        ]
        decision = await decide_link(
            signal.for_ai(), candidates=shown, life=life,
            meaning={k: answer.get(k) for k in ("outcome", "what_it_means", "relates_to")},
        )
        if decision is None:
            return None

        chosen = next(
            (c for c in candidates if str(c.get("ref")) == decision.get("target_ref")),
            None,
        )
        return await situations.record_link(
            self.db, owner_id, signal, decision, candidate=chosen,
        )

    async def _pass_on(
        self, owner_id: str, signal: ConnectedSignal, answer: Dict[str, Any],
        *, link: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Hand a meaningful change to the machinery that already handles them.

        Three doors, and none of them is new. The change log is where V3.7
        already collects "something moved" and where its own dedupe and
        staleness rules apply. Governance is the only thing allowed to write
        to the Life Model, exactly as it is for the agent. The wake is how
        V3.8 arranges for somebody to look again — and it is a knock, not an
        instruction: what comes of it is decided by the loop that wakes up.
        """
        # 0. Se parla di soldi, i soldi sanno cosa farne.
        #
        #     NON OGNI EMAIL PASSA DAL RAGIONAMENTO FINANZIARIO.
        #
        # Chi decide non e' una parola chiave — «fattura» quindi finanza —
        # ma il giudizio che si e' gia' fatto su questo segnale: gli si e'
        # chiesto, nella stessa chiamata, se dice qualcosa dei soldi di
        # questa persona. Una pubblicita' di prestiti nomina somme e non dice
        # niente delle sue, e muore prima di arrivare qui perche' e' `noise`.
        #
        # Nessun secondo giro, nessuno scheduler in piu', nessun parser
        # parallelo: e' lo stesso passaggio, con una porta in piu' in fondo.
        if answer.get("touches_money"):
            try:
                from financial.bridge import read_money_in
                from financial.models import Provenance

                await read_money_in(
                    self.db, owner_id,
                    observation=signal.for_ai(),
                    provenance=Provenance(
                        source=signal.source_type,
                        source_ref=signal.source_object_ref,
                        how_directly=signal.payload_summary[:200],
                    ),
                    source_refs=[signal.raw_ref] if signal.raw_ref else [],
                )
            except Exception as e:
                logger.info("financial soft-fail: %s", type(e).__name__)

        # 1. Something moved.
        try:
            from opportunities.changes import ChangeLog

            payload = signal.as_change()
            await ChangeLog(self.db).record(owner_id, **payload)
        except Exception as e:
            logger.info("change log soft-fail: %s", type(e).__name__)

        # 2. Something ORA believed may now be out of date. Proposed, never
        #    written: the same governance the agent proposes through, and it
        #    is free to refuse.
        if answer["outcome"] == "changes_something_known":
            await self._propose_observation(owner_id, signal, answer, link=link)

        # 3. Somebody should look again.
        try:
            from ambient.service import AmbientService

            await AmbientService(self.db).schedule(
                owner_id,
                reason="state_changed",
                when=_now() + timedelta(seconds=WAKE_DELAY_SECONDS),
                # Deliberately not this signal's id. A wake is a knock —
                # "something moved, come and look" — and what to look at is
                # the pending signals, which are in their own collection with
                # their own provenance. Naming one signal here made the wake's
                # identity unique per signal, so three messages arriving in
                # the same minute booked three separate thinks: the loop woke,
                # found the same world, and did it twice more. The comment at
                # the top of this file claimed coalescing; this is what makes
                # the claim true.
                provenance="code_schedule",
            )
        except Exception as e:
            logger.info("wake soft-fail: %s", type(e).__name__)

    async def _propose_observation(
        self, owner_id: str, signal: ConnectedSignal, answer: Dict[str, Any],
        *, link: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        What the world now says, offered to the model of this person's life.

            OBSERVED != TRUE. PROPOSED != WRITTEN.

        Nothing here writes a memory. It proposes one, through the governance
        that already owns durable learning, and that governance may refuse,
        ask, or find it contradicts something already known. The provenance
        travels with it so that a fact learned this way can always be traced
        back to the reading it came from — which is what makes a wrong one
        correctable rather than mysterious.
        """
        try:
            from conversation_engine.ai_core.models import MemoryCandidate
            from life_memory.governance import MemoryGovernanceService
        except Exception as e:
            logger.info("governance import soft-fail: %s", type(e).__name__)
            return ""

        meaning = str(answer.get("what_it_means") or "").strip()
        if not meaning:
            return ""

        candidate = MemoryCandidate(
            operation="propose",
            summary=meaning[:600],
            kind="connected_observation",
            authority="structured",
            epistemic_status="asserted",
            confidence=0.6,
            permanence="unknown",
            # Handles, so anybody asking «how do you know» has somewhere to
            # look — the signal, the thing it was about, and which reading of
            # the world produced it. Never the content of an event or a file.
            provenance=[
                f"connected_signal:{signal.id}",
                f"{signal.source_type}:{signal.source_object_ref}"[:120],
                f"interpretation:{INTERPRETATION_VERSION}",
            ] + ([
                # Which situation this was judged to be about, when it was
                # judged to be about one. A handle, so "why does ORA think
                # these are the same thing" has somewhere to look.
                f"situation_link:{link['id']}",
                f"{link['target_kind']}:{link['target_ref']}"[:120],
            ] if link and link.get("target_ref") else []),
            reason_for_future_utility=(
                "Osservato da una sorgente collegata della sua vita."
            ),
        )

        try:
            outcome = await MemoryGovernanceService(self.db).apply(
                user_id=owner_id,
                session_id=f"connected:{signal.id}",
                # The same observation proposing twice is the same proposal,
                # and governance keys off this to say so rather than
                # duplicating what it already decided about.
                reasoning_epoch=f"connected:{signal.fingerprint}",
                candidate=candidate,
                candidate_index=0,
            )
            logger.info(
                "connected observation signal=%s decision=%s persisted=%s",
                signal.id, outcome.decision, outcome.persisted,
            )
            # Returned so a caller can say what governance decided rather than
            # inferring it from whether a memory appeared. "Nothing was
            # written" and "nothing was proposed" look identical from the
            # outside and are entirely different facts about the system.
            return f"{outcome.decision}/persisted={outcome.persisted}"
        except Exception as e:
            logger.info("observation proposal soft-fail: %s", type(e).__name__)
        return ""

    # --- odds and ends ----------------------------------------------------

    async def _life(self, owner_id: str) -> Dict[str, Any]:
        """
        Enough about this person for a judgement to be about them.

        Deliberately small. A change means something in the context of a
        life, and a judgement given no context judges in the abstract — but
        the whole life in a prompt is both expensive and a privacy problem, so
        what travels is the short known facts and nothing else.
        """
        try:
            docs = await self.db.memories.find(
                {"user_id": owner_id, "status": "known"},
                {"_id": 0, "summary": 1},
            ).sort("updated_at", -1).to_list(8)
        except Exception as e:
            logger.info("life read soft-fail: %s", type(e).__name__)
            return {}
        return {
            "things_ora_knows": [
                str(d.get("summary") or "")[:200] for d in docs if d.get("summary")
            ]
        }

    async def _watermark(self, owner_id: str, source_id: str) -> Optional[str]:
        found = await self.db[ATTEMPTS].find_one(
            {"owner_id": owner_id, "source_id": source_id},
            {"_id": 0, "watermark": 1},
        )
        return (found or {}).get("watermark")

    async def _set_watermark(
        self, owner_id: str, source_id: str, observed: List[ConnectedSignal],
    ) -> None:
        """
        How far we have read. Efficiency only, never correctness.

        The fingerprint is what stops a duplicate, so a watermark that is
        wrong or missing costs a re-read and nothing else. Moved only when
        something was actually seen: advancing it on an empty pass would skip
        rows that arrived while we were looking.
        """
        if not observed:
            return
        newest = max(s.observed_at for s in observed)
        await self.db[ATTEMPTS].update_one(
            {"owner_id": owner_id, "source_id": source_id},
            {"$set": {"watermark": newest}},
            upsert=True,
        )

    async def disconnect(self, owner_id: str, source_id: str) -> Dict[str, Any]:
        """
        They took a source away. Stop looking; keep what was learned.

        Future readings stop, pending observations are dropped because they
        describe a world we no longer have permission to watch, and what
        already reached the Life Model stays — deleting somebody's memories
        because they unplugged a calendar is a decision governance owns, not
        this file.
        """
        dropped = await self.db["connected_signals"].update_many(
            {"owner_id": owner_id, "source_id": source_id, "status": "pending"},
            {"$set": {"status": "skipped", "outcome": "source_disconnected"}},
        )
        await self.db[ATTEMPTS].update_one(
            {"owner_id": owner_id, "source_id": source_id},
            {"$set": {"owner_id": owner_id, "source_id": source_id,
                      "health": "scollegata", "last_error": ""}},
            upsert=True,
        )
        return {"ok": True, "dropped_pending": dropped.modified_count}

    async def forget_all(self, owner_id: str) -> Dict[str, int]:
        from connected import content, situations
        from connected.seen import SeenState

        return {
            "signals": await self.signals.forget_all(owner_id),
            "sources": await self.sources.forget_all(owner_id),
            "seen": await SeenState(self.db).forget_all(owner_id),
            "content_reads": await content.forget_all(self.db, owner_id),
            "situation_links": await situations.forget_all(self.db, owner_id),
        }


# Bumped when the meaning of an interpretation changes, so a fact learned
# under an older reading can be told apart from one learned under this.
INTERPRETATION_VERSION = "v3.10.1"
