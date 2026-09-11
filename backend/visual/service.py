"""
Dal file caricato a quello che ORA ha visto.

    PARSED TEXT FIRST. VISION WHEN NEEDED.

Non si guarda tutto sempre. Un PDF con il suo testo dentro si legge, e
mandarne le pagine a un modello che le guardi sarebbe pagare due volte per
sapere la stessa cosa peggio. Si guarda quando non c'è testo — una foto, una
schermata catturata, una pagina scansionata — o quando è il ragionamento a
chiedere di guardare, perché sospetta che il significato stia nella forma:
una tabella, una firma, un timbro, un grafico.

Quello che torna è un'osservazione, non un fatto. La differenza è tutto il
punto di questo modulo e sta scritta in `models.py`.

Niente di quello che si vede finisce in un log, e i byte dell'immagine non
vengono conservati qui: stanno già in Documents V2, e tenerne una seconda
copia accanto all'osservazione vorrebbe dire moltiplicare i posti da cui
qualcosa di privato può uscire.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from visual.models import (
    LifeTie,
    VisualObservation,
    fingerprint,
    now_iso,
)

logger = logging.getLogger("ora.visual.service")

OBSERVATIONS = "visual_observations"

# Quante parti di vita si mettono davanti a chi guarda. Non è una selezione
# di rilevanza: è un limite di quanto si è disposti a far leggere.
MAX_SITUATIONS = 12


class VisualService:
    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        try:
            await self.db[OBSERVATIONS].create_index("id", unique=True)
            await self.db[OBSERVATIONS].create_index(
                [("owner_id", 1), ("content_fingerprint", 1)]
            )
        except Exception:
            logger.exception("indici osservazioni non creati (non fatale)")

    # --- guardare ---------------------------------------------------------

    async def look(
        self,
        owner_id: str,
        *,
        document_ref: str,
        session_ref: str = "",
        what_they_asked: str = "",
        language: str = "it",
    ) -> Dict[str, Any]:
        """
        Guarda un'immagine già caricata, e scrivi cosa ci si vede.

        La stessa immagine guardata due volte non si guarda due volte: torna
        quello che si era visto, con la sua data. È un fatto tecnico —
        l'impronta dei byte — e non una deduzione sul significato.
        """
        from visual.seeing import (
            can_see,
            first_page_as_an_image,
            is_a_page,
            is_an_image,
            look_at,
        )
        from conversation_engine.ai_core.files.service import worth_reading

        blob, meta = await self._bytes_of(owner_id, document_ref)
        if blob is None:
            return {"ok": False, "reason": "not_found"}

        mime = str(meta.get("mime_type") or "")
        looking_at, looking_mime = blob, mime
        if not is_an_image(mime):
            #     PRIMA IL TESTO, GLI OCCHI QUANDO SERVE.
            #
            # Un PDF che il testo ce l'ha dentro si legge, e leggerlo costa
            # niente: guardarlo sarebbe pagare per vedere in una fotografia
            # quello che si puo' avere in chiaro. Ma una scansione non ha
            # nessun testo — e' la fotografia di un foglio dentro una busta —
            # e fino a ieri si fermava qui contro «non e' un'immagine»: l'unico
            # documento che avrebbe davvero avuto bisogno degli occhi era
            # l'unico a cui non arrivavano.
            if not is_a_page(mime):
                return {"ok": False, "reason": "not_an_image", "mime_type": mime}
            if worth_reading(str(meta.get("extracted_text") or "")):
                return {"ok": False, "reason": "the_text_is_there", "mime_type": mime}
            drawn = first_page_as_an_image(blob)
            if drawn is None:
                return {"ok": False, "reason": "cannot_draw_the_page", "mime_type": mime}
            looking_at, looking_mime = drawn, "image/png"

        # L'impronta e' quella del documento che la persona ha mandato, non
        # quella del disegno: la stessa scansione ricaricata e' la stessa cosa
        # anche se il disegno viene un pixel diverso.
        mark = fingerprint(blob)
        already = await self._seen_before(owner_id, mark)
        if already is not None:
            # Già vista. Non si paga due volte e non si scrive due volte.
            return {
                "ok": True,
                "already_seen": True,
                "observation": already.for_ai(),
                "observation_id": already.id,
            }

        if not can_see():
            return {"ok": False, "reason": "cannot_look"}

        seen = await look_at(
            looking_at,
            mime_type=looking_mime,
            what_they_asked=what_they_asked,
            life_around_it=await self._life_around(owner_id),
            language=language,
        )
        if seen is None:
            # Non aver guardato non è aver guardato e non aver capito: la
            # prima è l'assenza di un'osservazione, la seconda è
            # un'osservazione che dice di non aver capito. Scriverle uguali
            # renderebbe impossibile distinguerle dopo.
            return {"ok": False, "reason": "unavailable"}

        observation = self._read(
            owner_id,
            seen,
            document_ref=document_ref,
            session_ref=session_ref,
            mime_type=mime,
            mark=mark,
            uploaded_at=str(meta.get("created_at") or ""),
        )
        await self._keep(observation)
        return {
            "ok": True,
            "already_seen": False,
            "observation": observation.for_ai(),
            "observation_id": observation.id,
        }

    async def seen_in_session(
        self, owner_id: str, session_ref: str, *, limit: int = 4
    ) -> List[VisualObservation]:
        """Quello che è stato mostrato in questa conversazione, per rileggerlo."""
        if not session_ref:
            return []
        try:
            rows = await self.db[OBSERVATIONS].find(
                {"owner_id": owner_id, "session_ref": session_ref}, {"_id": 0},
            ).sort("observed_at", -1).to_list(limit)
        except Exception as e:
            logger.info("lettura osservazioni soft-fail: %s", type(e).__name__)
            return []
        out: List[VisualObservation] = []
        for row in rows:
            try:
                out.append(VisualObservation(**row))
            except Exception:
                continue
        return out

    # --- i pezzi ----------------------------------------------------------

    def _read(
        self,
        owner_id: str,
        seen: Dict[str, Any],
        *,
        document_ref: str,
        session_ref: str,
        mime_type: str,
        mark: str,
        uploaded_at: str,
    ) -> VisualObservation:
        """
        La risposta di chi ha guardato, dentro il contratto.

        Quello che non entra nel contratto cade: un legame senza la frase che
        lo motiva non è un legame, e un grado di leggibilità inventato torna a
        essere «non è chiaro». Il codice non aggiunge niente — controlla che
        ci sia quello che deve esserci.
        """
        def words(key: str, cap: int = 12) -> List[str]:
            raw = seen.get(key)
            if not isinstance(raw, list):
                return []
            return [str(v)[:120] for v in raw if str(v).strip()][:cap]

        ties: List[LifeTie] = []
        for row in seen.get("about_life") or []:
            if not isinstance(row, dict):
                continue
            ref = str(row.get("ref") or "").strip()
            why = str(row.get("ties_it_here") or "").strip()
            #     SENZA UN PERCHÉ, NON È UN LEGAME.
            # Una relazione senza la frase che dice cosa lega questa immagine
            # a *quella* parte di vita è un'associazione per argomento, ed è
            # esattamente ciò che V3.12 ha smesso di accettare.
            if not ref or not why:
                continue
            #     UN LEGAME CHE NON DICE QUANTO REGGE, REGGE POCO.
            # Una forza inventata o assente non diventa la piu' comoda: torna
            # `plausible`, che e' il livello onesto per quasi tutti i legami e
            # quello che impedisce a una coincidenza di nome di arrivare a chi
            # risponde indistinguibile da una prova.
            how = str(row.get("how_strong") or "").strip().lower()
            if how not in ("observed", "supported", "plausible", "unknown"):
                how = "plausible"
            settle = str(row.get("what_would_settle_it") or "").strip()
            try:
                ties.append(LifeTie(
                    ref=ref[:64], ties_it_here=why[:300],
                    how_strong=how, what_would_settle_it=settle[:300],
                ))
            except Exception:
                continue

        readability = str(seen.get("readability") or "").strip().lower()
        if readability not in ("readable", "partially_readable", "unreadable", "ambiguous"):
            readability = "ambiguous"

        confidence = str(seen.get("confidence") or "").strip().lower()
        if confidence not in ("weak", "reasonable", "strong"):
            confidence = "reasonable"

        return VisualObservation(
            owner_id=owner_id,
            document_ref=document_ref[:64],
            source_ref=document_ref[:64],
            session_ref=session_ref[:64],
            mime_type=mime_type[:80],
            content_fingerprint=mark,
            uploaded_at=uploaded_at or now_iso(),
            what_i_see=str(seen.get("what_i_see") or "")[:400],
            readability=readability,  # type: ignore[arg-type]
            observed_text=str(seen.get("observed_text") or "")[:1200],
            what_i_could_not_read=str(seen.get("what_i_could_not_read") or "")[:400],
            observed_entities=words("observed_entities"),
            observed_numbers=words("observed_numbers"),
            observed_dates=words("observed_dates"),
            observed_amounts=words("observed_amounts"),
            interpretation=str(seen.get("interpretation") or "")[:600],
            uncertainty=str(seen.get("uncertainty") or "")[:400],
            confidence=confidence,  # type: ignore[arg-type]
            about_life=ties,
            # Nasce come osservazione, e resta tale. Diventare conoscenza è
            # una decisione della governance, non di chi ha guardato.
            standing="seen",
            worth_keeping=bool(seen.get("worth_keeping")),
            why_keep=str(seen.get("why_keep") or "")[:300],
        )

    async def _seen_before(
        self, owner_id: str, mark: str
    ) -> Optional[VisualObservation]:
        try:
            row = await self.db[OBSERVATIONS].find_one(
                {"owner_id": owner_id, "content_fingerprint": mark}, {"_id": 0},
            )
        except Exception as e:
            logger.info("ricerca impronta soft-fail: %s", type(e).__name__)
            return None
        if not row:
            return None
        try:
            return VisualObservation(**row)
        except Exception:
            return None

    async def _keep(self, observation: VisualObservation) -> None:
        try:
            await self.db[OBSERVATIONS].update_one(
                {"id": observation.id},
                {"$set": observation.model_dump()},
                upsert=True,
            )
        except Exception as e:
            logger.info("scrittura osservazione soft-fail: %s", type(e).__name__)

    async def _bytes_of(self, owner_id: str, document_ref: str):
        """
        I byte del documento, presi da dove stanno già.

        Attraverso Documents V2 e non con una lettura per conto proprio: e'
        quel servizio a sapere dove finisce un file, se e' stato cancellato e
        se appartiene davvero a chi lo chiede. Una seconda strada verso lo
        stesso disco sarebbe una seconda strada da tenere sicura.
        """
        try:
            from documents.service import DocumentService
            from documents.storage import build_default_storage

            service = DocumentService(db=self.db, storage=build_default_storage())
            doc, blob = await service.read_bytes(user_id=owner_id, doc_id=document_ref)
        except Exception as e:
            logger.info("documento non leggibile: %s", type(e).__name__)
            return None, {}
        return blob, doc

    async def _life_around(self, owner_id: str) -> Dict[str, Any]:
        """
        La vita intorno all'immagine: le parti aperte, e cosa ORA già sa.

            UN'IMMAGINE NON SI GUARDA NEL VUOTO.

        Senza le situazioni, chi guarda può solo descrivere un rettangolo con
        dei numeri dentro. Senza quello che ORA già sa, può solo ripetere:
        una schermata che mostra i quattromila euro del notaio è una novità
        soltanto se quei quattromila euro non erano già noti, e dirli di nuovo
        come se fossero una scoperta è il modo più rapido di far sembrare
        distratta un'assistente che sapeva già tutto.

        Niente di tutto questo è un elenco fra cui scegliere per forza: «non
        c'entra con niente» resta la risposta giusta e la più frequente.
        """
        around: Dict[str, Any] = {"situations": [], "nearby": []}

        try:
            rows = await self.db.life_objects.find(
                {"user_id": owner_id, "status": {"$ne": "archived"}},
                {"_id": 0, "id": 1, "title": 1, "type": 1, "ai_summary": 1},
            ).to_list(MAX_SITUATIONS)
            around["situations"] = [
                {
                    "ref": r["id"],
                    "what_it_is": str(r.get("title") or "")[:100],
                    "in_a_line": str(r.get("ai_summary") or "")[:160],
                }
                for r in rows
                if r.get("title")
            ]
        except Exception as e:
            logger.info("lettura situazioni soft-fail: %s", type(e).__name__)

        # Cosa ORA sa già dei soldi, con i gradi intatti: serve a riconoscere
        # un movimento che conosce invece di annunciarlo.
        try:
            from financial.knowledge import what_ora_knows

            said = await what_ora_knows(self.db, owner_id)
            for row in ((said.get("so") or []) + (said.get("ho_letto") or []))[:6]:
                around["nearby"].append({
                    "kind": "money",
                    "what": str(row.get("cosa") or "")[:80],
                    "how_much": str(row.get("quanto") or "")[:40],
                    "how_ora_knows": str(row.get("come_lo_so") or "")[:80],
                })
        except Exception as e:
            logger.info("lettura denaro soft-fail: %s", type(e).__name__)

        # E gli impegni che stanno in piedi: un appuntamento in una schermata
        # o è quello che c'è già, o è un'altra cosa — e non si può dire quale
        # senza aver davanti quelli che ci sono.
        try:
            from datetime import datetime, timedelta, timezone

            from opportunities.snapshot import _appointments_that_still_stand

            now = datetime.now(timezone.utc)
            for row in (
                await _appointments_that_still_stand(
                    self.db, owner_id, now, now + timedelta(days=30),
                )
            )[:6]:
                around["nearby"].append({
                    "kind": "appointment",
                    "ref": row.get("ref"),
                    "what": str(row.get("title") or "")[:100],
                    "when": row.get("starts_at"),
                })
        except Exception as e:
            logger.info("lettura impegni soft-fail: %s", type(e).__name__)

        return around
