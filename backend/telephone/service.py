"""
Chiamare, seguire la chiamata, e dire com'è andata.

    L'AUTORITÀ SI CHIEDE PRIMA DI COMPORRE IL NUMERO.
    L'ESITO SI LEGGE DOPO AVER RIAGGANCIATO.

In mezzo, mentre si parla, non si decide niente: quel pezzo è il ponte, e il
ponte non ha autorità. Questo file è le due estremità.

Sull'esito c'è una cosa che vale la pena dire per intera. La tentazione, dopo
una telefonata, è di riempire i campi: c'era un orario nella conversazione,
lo si mette. Ma «facciamo giovedì?» «eh, giovedì ho pieno, vediamo» non è un
appuntamento giovedì, ed è esattamente la trascrizione da cui un estrattore
disattento tira fuori un giovedì. Per questo `understood` è una domanda a sé,
e `worth_writing_down` ne vuole due: aver capito, e avere un momento.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from telephone.models import (
    CallOutcome,
    CallTurn,
    Mandate,
    PhoneCall,
    now_iso,
)

logger = logging.getLogger("ora.telephone.service")

CALLS = "phone_calls"


class TelephoneService:
    def __init__(self, db) -> None:
        self.db = db

    # --- prima ------------------------------------------------------------

    async def may_i_call(self, owner_id: str, *, capability: str = "phone.call") -> Dict[str, Any]:
        """
        Si può telefonare? Lo chiede a chi decide già tutto il resto.

        Non c'è nessun giudizio qui dentro, e non deve essercene: una seconda
        opinione sull'autorità è una seconda autorità, e due autorità sono
        zero autorità.
        """
        from agent.authority import AuthorityService
        from agent.capabilities import CapabilityResolver

        resolution = await CapabilityResolver(self.db).resolve(owner_id, capability)
        authority = AuthorityService(self.db)
        granted = await authority.has_grant(owner_id, capability)
        denied = await authority.is_denied(owner_id, capability)

        # Due cose diverse: se c'è una linea telefonica, e se c'è qualcuno
        # capace di ascoltare e rispondere in italiano. Mancarne una sola
        # basta a non poter telefonare, e dirlo per nome è la differenza fra
        # «non si può» e «non si può, perché».
        from telephone import deepgram
        from telephone.carrier import can_call, why_not as no_line
        from telephone.runtime import GEMINI_LIVE, which_runtime

        if which_runtime() == GEMINI_LIVE:
            from telephone.live import live_is_configured

            voice_reason = live_is_configured()
        else:
            voice_reason = (
                "nessuna voce che possa ascoltare e rispondere in linea"
                if not deepgram.is_configured() else ""
            )
        why = "; ".join(
            p for p in (
                no_line(),
                voice_reason,
            ) if p
        )

        return {
            "capability": capability,
            "known": resolution.known,
            "permitted": resolution.permitted,
            "executable": resolution.executable,
            "granted": granted,
            "denied": denied,
            "provider_ready": can_call() and not voice_reason,
            "why_not": why,
            # Una chiamata non parte mai da sola: anche con il permesso, la
            # persona deve dire di sì a *questa* chiamata.
            "needs_explicit_yes": True,
        }

    async def prepare(
        self,
        owner_id: str,
        *,
        to_number: str,
        calling_whom: str,
        mandate: Mandate,
        session_ref: str = "",
        authority_ref: str = "",
    ) -> PhoneCall:
        """
        Scrive la chiamata prima che esista, con il suo mandato.

        Prepararla e farla sono due momenti: fra i due c'è la persona che
        guarda cosa ORA sta per dire e a chi, e dice di sì. Quel sì è
        `authority_ref`.
        """
        call = PhoneCall(
            owner_id=owner_id,
            to_number=_national(to_number),
            calling_whom=calling_whom[:120],
            mandate=mandate,
            session_ref=session_ref[:64],
            authority_ref=authority_ref[:64],
        )
        await self.db[CALLS].insert_one(call.model_dump())
        return call

    async def get(self, owner_id: str, call_id: str) -> Optional[PhoneCall]:
        row = await self.db[CALLS].find_one(
            {"owner_id": owner_id, "id": call_id}, {"_id": 0},
        )
        return PhoneCall.model_validate(row) if row else None

    async def recent(
        self,
        owner_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
        status: str = "",
        days: int = 0,
        before: str = "",
    ) -> "tuple":
        """
        Le telefonate di questa persona, le piu' recenti per prime.

            LA PIU' RECENTE E' QUELLA CHE SI STA CERCANDO.

        Torna la pagina chiesta e quante ce ne sono in tutto, perche' «mostrati
        dieci di quarantadue» ha bisogno del quarantadue — e quel numero non
        si puo' chiedere al database quando il filtro e' uno stato che il
        database non conosce.

        `days` restringe la finestra: zero vuol dire tutte.

            UNA PAGINA SI CHIEDE AL DATABASE, NON SI RITAGLIA IN MEMORIA.

        Prima si leggevano fino a trecento telefonate e si tagliava la pagina
        qui. Adesso il database ordina (`authorised_at`, poi `id`, così due
        telefonate nello stesso istante hanno comunque un ordine), filtra per
        stato sul campo `status_reads` scritto a ogni salvataggio, e torna solo
        la pagina — più una, per sapere se ce n'è un'altra. `before` è il
        cursore: «authorised_at|id» dell'ultima riga vista.

        Torna (pagina, quante in tutto, cursore della prossima pagina).
        """
        quante = max(1, min(int(limit), 100))
        query: Dict[str, Any] = {"owner_id": owner_id}
        if days and days > 0:
            from datetime import datetime, timedelta, timezone

            da = datetime.now(timezone.utc) - timedelta(days=int(days))
            query["authorised_at"] = {"$gte": da.isoformat()}
        if status:
            query["status_reads"] = status

        in_tutto = await self.db[CALLS].count_documents(query)

        pagina_query = dict(query)
        quando, _, ident = (before or "").partition("|")
        if quando:
            pagina_query["$or"] = [
                {"authorised_at": {"$lt": quando}},
                {"authorised_at": quando, "id": {"$lt": ident}},
            ]
        cursore = (
            self.db[CALLS]
            .find(pagina_query, {"_id": 0})
            .sort([("authorised_at", -1), ("id", -1)])
        )
        if not quando and offset:
            cursore = cursore.skip(max(0, int(offset)))
        righe = await cursore.limit(quante + 1).to_list(quante + 1)
        chiamate = [PhoneCall.model_validate(r) for r in righe]

        altre = len(chiamate) > quante
        chiamate = chiamate[:quante]
        prossima = (
            f"{chiamate[-1].authorised_at}|{chiamate[-1].id}"
            if altre and chiamate else ""
        )
        return chiamate, in_tutto, prossima

    async def by_provider_ref(self, ref: str) -> Optional[PhoneCall]:
        row = await self.db[CALLS].find_one({"provider_ref": ref}, {"_id": 0})
        return PhoneCall.model_validate(row) if row else None

    async def _save(self, call: PhoneCall) -> None:
        from telephone.history import how_it_reads

        campi = call.model_dump(exclude={"told_the_chat", "chat_told_at"})
        #     COME SI LEGGE, SCRITTO ACCANTO: E' QUELLO SU CUI SI FILTRA.
        campi["status_reads"] = how_it_reads(call)
        await self.db[CALLS].update_one(
            {"owner_id": call.owner_id, "id": call.id},
            #     L'ESITO RIPORTATO IN CHAT LO SCRIVE SOLO CHI LO RIPORTA.
            # Una copia vecchia della telefonata, salvata dopo, non deve
            # poter dire «non l'hai ancora raccontato».
            {"$set": campi},
            upsert=True,
        )

    # --- mentre -----------------------------------------------------------

    async def mark(self, call: PhoneCall, state: str, **fields: Any) -> PhoneCall:
        call.state = state  # type: ignore[assignment]
        for key, value in fields.items():
            setattr(call, key, value)
        await self._save(call)
        return call

    async def heard(self, call: PhoneCall, who: str, said: str) -> None:
        """Una battuta, appena è stata detta."""
        if not said.strip():
            return
        call.turns.append(CallTurn(who=who, said=said[:2000]))  # type: ignore[arg-type]
        call.turns = call.turns[-120:]
        await self._save(call)

    # --- dopo -------------------------------------------------------------

    async def read_what_happened(self, call: PhoneCall) -> CallOutcome:
        """
        Che cosa è successo, letto dalla conversazione vera.

        Il modello che legge è quello di sempre — lo stesso gestore, la stessa
        catena di provider, la stessa disciplina — e non è quello che ha
        parlato: chi ha condotto una conversazione è la persona meno adatta a
        dire se è andata bene.
        """
        spoken = [
            {"chi": "ORA" if t.who == "ora" else "loro", "ha_detto": t.said}
            for t in call.turns
        ]
        if not spoken:
            return CallOutcome(
                understood=False,
                in_a_line="Non è stata detta una parola.",
                unclear="La chiamata non ha prodotto nessuna conversazione.",
            )

        system = (
            "Leggi una telefonata vera e di' che cosa ne è venuto fuori.\n\n"
            "    NON AVER CAPITO È UN ESITO.\n\n"
            "La tentazione è riempire i campi. C'era un orario nella "
            "conversazione, quindi si mette. Ma «facciamo giovedì?» «eh, "
            "giovedì ho pieno, vediamo» non è un appuntamento di giovedì, ed è "
            "esattamente la trascrizione da cui esce un giovedì sbagliato. Un "
            "fatto vale solo se è stato detto e confermato: se è rimasto "
            "un'ipotesi, va in `still_open`, non in `when`.\n\n"
            "`understood` è vero solo quando sapresti spiegare a questa "
            "persona cosa succede adesso. `when` è una data e un'ora ISO "
            "soltanto se sono state dette e non contraddette; altrimenti è "
            "vuoto, e non ci va «probabilmente giovedì».\n\n"
            "`agreed_to` è quello che ORA ha accettato in linea, con le "
            "parole con cui l'ha accettato. `brought_back` è quello che ha "
            "detto di dover chiedere. Se ORA ha accettato qualcosa che non "
            "doveva, scrivilo lo stesso in `agreed_to`: serve a scoprirlo.\n\n"
            "`outside_the_mandate` è la riga che conta per la sicurezza: di "
            "ogni cosa in `agreed_to`, di' se sta dentro `poteva_accettare` "
            "oppure no, e riporta qui solo quelle che non ci stanno. Un "
            "permesso è scritto in astratto — «un appuntamento fra giovedì e "
            "sabato, in orario di studio» — e quello che ORA ha accettato è "
            "concreto — «venerdì diciotto alle dieci»: quelle due cose sono "
            "la stessa cosa, e non vanno segnalate. Segnala solo ciò che "
            "davvero esce dal permesso: un giorno fuori dall'intervallo, una "
            "prestazione diversa, un costo, un impegno che nessuno aveva "
            "autorizzato. Se `poteva_accettare` è vuoto, allora qualunque "
            "cosa ORA abbia accettato è fuori.\n\n"
            "Rispondi in italiano, nei campi. Solo JSON:\n"
            '{"understood": false, "in_a_line": "", "when": null, "where": '
            'null, "with_whom": null, "how_much": null, "still_open": [], '
            '"brought_back": [], "agreed_to": [], "outside_the_mandate": [], '
            '"unclear": ""}'
        )
        user = json.dumps(
            {
                "oggi": now_iso()[:10],
                "perche_chiamava": call.mandate.why_calling,
                "poteva_accettare": call.mandate.may_agree_to,
                "la_telefonata": spoken,
            },
            ensure_ascii=False,
        )[:12000]

        try:
            from llm.manager import ProviderManager

            answer = await ProviderManager().chat(system=system, user=user, json_mode=True)
            parsed = json.loads(answer.text or "{}")
        except Exception as e:
            logger.info("lettura esito soft-fail: %s", type(e).__name__)
            return CallOutcome(
                understood=False,
                in_a_line="La telefonata è avvenuta, ma non sono riuscita a rileggerla.",
                unclear="Non è stato possibile ricostruire l'esito.",
            )

        outcome = CallOutcome(
            understood=bool(parsed.get("understood")),
            in_a_line=str(parsed.get("in_a_line") or "")[:400],
            when=_clean(parsed.get("when")),
            where=_clean(parsed.get("where")),
            with_whom=_clean(parsed.get("with_whom")),
            how_much=_clean(parsed.get("how_much")),
            still_open=_words(parsed.get("still_open")),
            brought_back=_words(parsed.get("brought_back")),
            agreed_to=_words(parsed.get("agreed_to")),
            outside_the_mandate=_words(parsed.get("outside_the_mandate")),
            unclear=str(parsed.get("unclear") or "")[:400],
        )
        call.outcome = outcome
        await self._save(call)
        return outcome

    def kept_the_mandate(self, call: PhoneCall) -> Dict[str, Any]:
        """
        Se quello che ORA ha accettato stava nel mandato.

            IL MANDATO SI CONTROLLA ANCHE DOPO.

        Prima serve a impedire; dopo serve a sapere. Se un giorno il modello
        accettasse qualcosa fuori mandato, l'unico modo di accorgersene è
        guardare qui — e accorgersene è la condizione per poterlo dire alla
        persona invece di scoprirlo dal dentista.
        """
        outcome = call.outcome
        if outcome is None:
            return {"checked": False}

        # Il verdetto lo porta la rilettura, che aveva davanti sia il permesso
        # astratto sia la cosa concreta. Il confronto testuale resta come rete
        # sotto: se il mandato era vuoto, qualunque cosa accettata è fuori, e
        # quello lo sa dire il codice senza bisogno di nessuno.
        overstepped = list(outcome.outside_the_mandate)
        if not call.mandate.may_agree_to:
            for thing in outcome.agreed_to:
                if thing not in overstepped:
                    overstepped.append(thing)

        return {
            "checked": True,
            "kept": not overstepped,
            "agreed_to": list(outcome.agreed_to),
            "outside_the_mandate": overstepped,
        }


#     UN SÌ HA UNA DATA DI SCADENZA.
#
# Due telefonate del 18/09 sono rimaste «autorizzate» per sempre: preparate da
# un percorso della chat che non aveva un tasto per comporle, e da allora
# nessuno le aveva più guardate. Un sì dato ieri su un mandato di ieri non è un
# sì per oggi: dopo due ore una telefonata mai partita si dichiara «non
# avviata», e comporla richiede un sì nuovo.
GHOST_AFTER_S = 2 * 3600

#     E UNA TELEFONATA «IN CORSO» DA ORE NON E' IN CORSO.
# Se l'operatore smette di mandare notizie — un tunnel caduto, un processo
# riavviato a metà — la telefonata resterebbe «in corso» e il suo piano
# «executing» per sempre. Oltre la durata massima del mandato più un margine,
# non è più in corso: è finita e non sappiamo come.
STALE_MARGIN_S = 15 * 60


def _age_s(quando: str) -> float:
    from datetime import datetime, timezone

    try:
        t = datetime.fromisoformat(str(quando).replace("Z", "+00:00"))
    except Exception:
        return 0.0
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds()


def is_a_ghost(call) -> bool:
    """Preparata, mai composta, e troppo vecchia per essere composta adesso."""
    return (call.state in ("authorised", "expired")
            and _age_s(call.authorised_at) > GHOST_AFTER_S) or call.state == "expired"


def is_stale(call) -> bool:
    """«In corso» da più di quanto una telefonata possa durare."""
    if call.state not in ("dialling", "talking"):
        return False
    massimo = max(60, int(getattr(call.mandate, "minutes", 5) or 5) * 60)
    return _age_s(call.started_at or call.authorised_at) > massimo + STALE_MARGIN_S


async def write_how_they_read(db, limit: int = 500) -> int:
    """
    Scrive `status_reads` sulle telefonate che non ce l'hanno ancora.

    Le righe nate prima della paginazione vera non hanno il campo su cui si
    filtra: senza, un filtro «nessuna risposta» non le troverebbe. Una volta
    all'avvio, a lotti; torna quante ne ha sistemate.
    """
    from telephone.history import how_it_reads

    righe = await db[CALLS].find(
        {"status_reads": {"$exists": False}}, {"_id": 0},
    ).to_list(max(1, limit))
    fatte = 0
    for riga in righe:
        try:
            call = PhoneCall.model_validate(riga)
        except Exception:  # pragma: no cover
            continue
        await db[CALLS].update_one(
            {"id": call.id}, {"$set": {"status_reads": how_it_reads(call)}})
        fatte += 1
    return fatte


async def settle_the_forgotten(db, limit: int = 50) -> int:
    """
    Chiude le telefonate rimaste a metà: mai composte, o senza più notizie.

    Non inventa esiti: le mai composte diventano `expired` («non avviata»), le
    senza notizie `failed` con `how_it_ended="unknown"` («si è interrotta»).
    Torna quante ne ha chiuse.
    """
    chiuse = 0
    #     E QUELLE CHE LA RETE HA RACCONTATO STORTE.
    # Mai risposte (niente `started_at`), nessun esito, eppure «hanno
    # riagganciato»: è la race di `completed` + `ring_timeout` vista sul vero.
    # La stessa regola della rotta degli eventi, applicata a chi c'era prima.
    for riga in await db[CALLS].find(
        {"state": "ended", "how_it_ended": {"$in": ["they_hung_up", "we_hung_up"]},
         "started_at": None, "metrics.outcome": None}, {"_id": 0},
    ).to_list(max(1, min(limit, 200))):
        try:
            call = PhoneCall.model_validate(riga)
        except Exception:  # pragma: no cover
            continue
        await TelephoneService(db).mark(call, "failed", how_it_ended="no_answer")
        chiuse += 1

    righe = await db[CALLS].find(
        {"state": {"$in": ["authorised", "dialling", "talking"]}}, {"_id": 0},
    ).to_list(max(1, min(limit, 200)))
    service = TelephoneService(db)
    for riga in righe:
        try:
            call = PhoneCall.model_validate(riga)
        except Exception:  # pragma: no cover
            continue
        if call.state == "authorised" and is_a_ghost(call):
            await service.mark(call, "expired")
            chiuse += 1
        elif is_stale(call):
            await service.mark(call, "failed", how_it_ended="unknown",
                               why_the_network_refused="nessuna notizia dall'operatore")
            chiuse += 1
    return chiuse


def _national(number: str) -> str:
    """
    Il numero, se è italiano. Altrimenti niente.

        SOLO CHIAMATE NAZIONALI.

    Non è una precauzione sui costi: è che questo pilota è stato pensato,
    provato e autorizzato per un paese solo, e un prefisso diverso è una cosa
    di cui nessuno ha discusso.
    """
    clean = "".join(ch for ch in str(number or "") if ch.isdigit() or ch == "+")
    if clean.startswith("+39") and len(clean) >= 12:
        return clean
    if clean.startswith("0039"):
        return "+" + clean[2:]
    #     UN NUMERO SCRITTO COME LO SCRIVE UN OPERATORE È UN NUMERO.
    #
    # `393000000000` — prefisso internazionale, solo cifre, senza il più — è
    # la forma in cui i fornitori di telefonia lo chiedono e lo restituiscono,
    # ed era l'unica che qui tornava vuota: dodici cifre che cominciano per
    # tre non entravano in nessun caso, e la chiamata si fermava con «numero
    # non italiano» prima di arrivare alla rete. Un numero rifiutato per come
    # è scritto è il difetto più frustrante che esista, perché sembra un
    # rifiuto di merito.
    if clean.startswith("39") and 12 <= len(clean) <= 13:
        return "+" + clean
    if clean.startswith("3") and len(clean) in (9, 10):
        return "+39" + clean
    if clean.startswith("0") and len(clean) >= 9:
        return "+39" + clean
    return ""


def _clean(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text[:200] if text and text.lower() not in ("null", "none", "") else None


def _words(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip()[:160] for v in value if str(v).strip()][:6]
