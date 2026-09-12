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

        from telephone.bridge import can_call, can_speak_live, why_not

        return {
            "capability": capability,
            "known": resolution.known,
            "permitted": resolution.permitted,
            "executable": resolution.executable,
            "granted": granted,
            "denied": denied,
            "provider_ready": can_call() and can_speak_live(),
            "why_not": why_not(),
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

    async def by_provider_ref(self, ref: str) -> Optional[PhoneCall]:
        row = await self.db[CALLS].find_one({"provider_ref": ref}, {"_id": 0})
        return PhoneCall.model_validate(row) if row else None

    async def _save(self, call: PhoneCall) -> None:
        await self.db[CALLS].update_one(
            {"owner_id": call.owner_id, "id": call.id},
            {"$set": call.model_dump()},
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
