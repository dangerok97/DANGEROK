"""
Da «chiama Lorenzo e sposta il calcetto» a una telefonata che si può fare.

    IL NUMERO NON LO SCEGLIE ORA. MAI.

Lo trova, dice da dove viene, e aspetta. È la cosa che queste prove tengono
ferma sopra tutte le altre, perché è quella che non si può correggere dopo:
una telefonata parte una volta sola, e se parte verso il numero sbagliato
qualcuno ha già risposto.

    E OGNI DOMANDA CHE ORA FA È UNA COSA CHE NON SAPEVA.

L'altra metà di questo sprint. Chiedere è gratis per chi programma e costoso
per chi risponde: un sistema che chiede quello che ha già scritto da qualche
parte insegna a non leggere le sue domande.
"""

from __future__ import annotations

import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from test_post_call_application_v315 import FintoDb  # noqa: E402

UID = "u1"

LA_PARTITA = {
    "id": "ced_calcetto",
    "user_id": UID,
    "title": "Calcetto con Lorenzo",
    "start_datetime": "2026-09-25T20:30:00+02:00",
    "end_datetime": "2026-09-25T21:30:00+02:00",
    "timezone": "Europe/Rome",
    "status": "confirmed",
}

IN_RUBRICA = {
    "id": "con_lorenzo",
    "user_id": UID,
    "name": "Lorenzo Bianchi",
    "phone": "+39 333 0000001",
    "kind": "person",
    "relationship": "calcetto del venerdì",
}


@pytest.fixture
def mondo(monkeypatch):
    """
    Un database con una partita in calendario e un Lorenzo in rubrica.

        E NESSUN MODELLO DIETRO.

    Il valutatore chiede a un modello che cosa manca, e qui il modello non
    c'è: si ripiega sulla regola scritta a mano, che è esattamente quello che
    succede in produzione quando un provider è giù. Le prove che vogliono un
    modello se lo mettono loro.
    """
    import preparation.readiness as valutatore

    async def nessun_modello(_prep):
        return None

    monkeypatch.setattr(valutatore, "_what_the_model_sees", nessun_modello)

    db = FintoDb()
    db.calendar_event_drafts.righe.append(dict(LA_PARTITA))
    db.contacts.righe.append(dict(IN_RUBRICA))
    return db


def _niente_web(monkeypatch):
    """Il web spento, che è il caso di quasi tutte queste prove."""
    import preparation.contacts as risolutore

    async def mai(self, db, *, owner_id, who):
        return []

    monkeypatch.setattr(risolutore.PublicWeb, "look_for", mai)


async def _apri(db, richiesta="Chiama Lorenzo e sposta il calcetto",
               chi="Lorenzo", operazione="reschedule"):
    from preparation.service import start

    prep, perche = await start(
        db, owner_id=UID, user_request=richiesta, counterparty=chi,
        operation=operazione,
    )
    assert perche == "", perche
    return prep


# ---------------------------------------------------------------------------
# 1 · Trovare chi chiamare
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_contact_in_the_address_book_is_found_and_asked_about(mondo, monkeypatch):
    """
    Trovato in rubrica → si mostra, e si chiede conferma.

        TROVATO NON È CONFERMATO.

    È la distinzione che tiene in piedi tutto lo sprint. Un numero con
    confidenza alta, da una fonte affidabile, unico candidato — e comunque non
    si compone finché qualcuno non guarda.
    """
    _niente_web(monkeypatch)
    prep = await _apri(mondo)

    assert prep.selected_contact is not None
    assert prep.selected_contact.number == "+393330000001"
    assert prep.selected_contact.source == "address_book"
    assert prep.number_confirmed is False
    assert prep.conversation_ready is False
    assert prep.can_become_a_call() is False


@pytest.mark.asyncio
async def test_the_provenance_is_shown_in_italian(mondo, monkeypatch):
    """
    §2: da dove viene il numero si dice, e si dice in italiano.

    «Rubrica» e «Trovato sul web» sono due cose molto diverse davanti alla
    stessa cifra, e chi conferma ha il diritto di sapere quale sta guardando.
    """
    _niente_web(monkeypatch)
    from preparation.service import as_a_card

    scheda = as_a_card(await _apri(mondo))

    assert scheda["contact"]["source_label"] == "Rubrica"
    assert "È questo il numero" in scheda["says"] or "quello giusto" in scheda["says"]
    assert "confirm_number" in scheda["you_can_answer"]


@pytest.mark.asyncio
async def test_a_number_ora_already_called_counts_as_context(mondo, monkeypatch):
    """
    §1B: quello che ORA ha già composto vale più di quello che si può dedurre.

    È verificato da un fatto — qualcuno ha risposto — invece che da una
    somiglianza fra stringhe.
    """
    _niente_web(monkeypatch)
    mondo.contacts.righe.clear()
    mondo["phone_calls"].righe.append({
        "id": "tel_vecchia", "owner_id": UID,
        "calling_whom": "Studio Dentistico Bianchi",
        "to_number": "+390600000002", "state": "ended",
    })

    from preparation.contacts import find_who_to_call

    trovato = await find_who_to_call(
        mondo, owner_id=UID, who="Studio Dentistico Bianchi",
    )
    uno = trovato.only_one()
    assert uno is not None
    assert uno.source == "past_call"
    assert uno.number == "+390600000002"


@pytest.mark.asyncio
async def test_a_business_nobody_knows_is_looked_for_online(mondo, monkeypatch):
    """
    §1C: un'attività che non si conosce si cerca dove ha pubblicato il numero.
    """
    import preparation.contacts as risolutore

    async def il_sito(self, db, *, owner_id, who):
        return [risolutore.ContactCandidate(
            name="Officina Rossi", number="+390600000003", kind="business",
            source="official_site", source_detail="officinarossi.it",
            confidence=risolutore.QUANTO_CI_SI_FIDA["official_site"],
            why="Pubblicato su officinarossi.it.",
        )]

    monkeypatch.setattr(risolutore.PublicWeb, "look_for", il_sito)

    trovato = await risolutore.find_who_to_call(
        mondo, owner_id=UID, who="Officina Rossi",
    )
    assert trovato.looked_online is True
    uno = trovato.only_one()
    assert uno is not None and uno.source == "official_site"


@pytest.mark.asyncio
async def test_a_private_person_is_never_looked_for_online(mondo, monkeypatch):
    """
    §12: il numero di una persona non si cerca su internet.

        UN'ATTIVITÀ PUBBLICA IL NUMERO. UNA PERSONA NO.

    Non è prudenza: sono due operazioni diverse. Se il numero di Lorenzo non
    è in rubrica e non è fra le cose di ORA, la risposta è una domanda — non
    una ricerca a nome suo.
    """
    import preparation.contacts as risolutore

    chiamate = []

    async def registra(self, db, *, owner_id, who):
        chiamate.append(who)
        return []

    monkeypatch.setattr(risolutore.PublicWeb, "look_for", registra)
    mondo.contacts.righe.clear()

    trovato = await risolutore.find_who_to_call(mondo, owner_id=UID, who="Lorenzo")

    assert chiamate == []
    assert trovato.looked_online is False
    assert "persona" in trovato.did_not_look_online
    assert trovato.found_nothing()


@pytest.mark.asyncio
async def test_more_than_one_candidate_is_never_chosen_alone(mondo, monkeypatch):
    """
    §3: più risultati → si mostrano e si chiede quale. Mai scegliere da soli.

    Il più probabile non è il giusto: è il più probabile. La differenza fra i
    due la conosce solo chi ha chiesto la telefonata.
    """
    _niente_web(monkeypatch)
    mondo.contacts.righe.append({
        "id": "con_lorenzo2", "user_id": UID, "name": "Lorenzo Verdi",
        "phone": "+39 333 0000009", "kind": "person",
    })

    from preparation.service import as_a_card

    prep = await _apri(mondo)
    scheda = as_a_card(prep)

    assert len(prep.contact_candidates) == 2
    assert prep.selected_contact is None
    assert prep.readiness == "AMBIGUOUS"
    assert len(scheda["candidates"]) == 2
    assert "choose" in scheda["you_can_answer"]
    assert prep.can_become_a_call() is False


@pytest.mark.asyncio
async def test_when_nothing_is_found_ora_asks_for_the_number(mondo, monkeypatch):
    """§1D: nessun numero affidabile → si chiede, e si dice che si sta chiedendo."""
    _niente_web(monkeypatch)
    mondo.contacts.righe.clear()

    from preparation.service import as_a_card

    prep = await _apri(mondo)
    scheda = as_a_card(prep)

    assert prep.readiness == "BLOCKED"
    assert "Me lo dici tu" in prep.readiness_says
    assert scheda["you_can_answer"] == ["give_number"]


# ---------------------------------------------------------------------------
# 2 · Il cancello del numero
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_rejected_number_means_zero_calls(mondo, monkeypatch):
    """
    §9: numero rifiutato → nessuna telefonata, e si dice perché.

        E NESSUN RIPIEGO SUL SECONDO CANDIDATO.

    Il secondo era meno probabile del primo, e il primo era sbagliato.
    """
    _niente_web(monkeypatch)
    from preparation.service import confirm_number, turn_into_a_call

    prep = await _apri(mondo)
    prep, _ = await confirm_number(mondo, prep, yes=False)

    assert prep.number_confirmed is False
    assert prep.number_rejected is True
    assert prep.readiness == "BLOCKED"
    assert prep.can_become_a_call() is False

    call, perche = await turn_into_a_call(mondo, prep)
    assert call is None
    assert "non l'hai ancora confermato" in perche
    assert mondo["phone_calls"].righe == []


@pytest.mark.asyncio
async def test_an_unconfirmed_number_means_zero_calls(mondo, monkeypatch):
    """
    §9: non confermato non è rifiutato, e nemmeno da lì si telefona.

    Il silenzio non è un sì. È la differenza fra un cancello e una formalità.
    """
    _niente_web(monkeypatch)
    from preparation.service import answer_question, turn_into_a_call

    prep = await _apri(mondo)
    prep, _ = await answer_question(
        mondo, prep, text="sabato alle 19", operation="reschedule",
    )

    assert prep.number_confirmed is False
    call, perche = await turn_into_a_call(mondo, prep)
    assert call is None
    assert mondo["phone_calls"].righe == []


@pytest.mark.asyncio
async def test_a_replacement_number_waits_for_its_own_yes(mondo, monkeypatch):
    """
    Un numero scritto come sostituto non è ancora confermato.

        CAMBIATO IN V3.20.1 FINAL, E DI PROPOSITO.

    Prima un numero scritto da chi risponde valeva come confermato. La
    politica di fiducia dice il contrario: «usa questo invece» è un candidato
    nuovo, e si usa solo dopo il suo sì. Il nome trovato prima resta.
    """
    _niente_web(monkeypatch)
    from preparation.service import confirm_number

    prep = await _apri(mondo)
    prep, _ = await confirm_number(
        mondo, prep, yes=False, instead="+39 333 1112222",
    )

    assert prep.selected_contact.number == "+393331112222"
    assert prep.selected_contact.name == "Lorenzo Bianchi"
    assert prep.number_confirmed is False
    assert prep.number_rejected is False
    assert prep.can_become_a_call() is False

    prep, _ = await confirm_number(mondo, prep, yes=True)
    assert prep.number_confirmed is True
    assert prep.number_trust == "confirmed_now"


# ---------------------------------------------------------------------------
# 3 · Quello che ORA sa già
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ora_finds_the_match_before_asking_anything(mondo, monkeypatch):
    """
    §5: «sposta il calcetto» → prima si guarda in calendario, poi si chiede.

        NON SI CHIEDE QUELLO CHE È GIÀ SCRITTO DA QUALCHE PARTE.
    """
    _niente_web(monkeypatch)
    prep = await _apri(mondo)

    assert any("Calcetto" in f for f in prep.known_context)
    assert any("20:30" in f for f in prep.known_context)
    assert prep.context_refs.get("calendar") == "ced_calcetto"


@pytest.mark.asyncio
async def test_the_question_asks_only_what_is_missing(mondo, monkeypatch):
    """
    §7: si chiede l'orario nuovo, e la domanda porta dentro quello che si sa.

    «A quando vuoi spostarla?» detto a chi ha appena nominato la partita è una
    domanda; detto senza aver guardato il calendario è un interrogatorio.
    """
    _niente_web(monkeypatch)
    from preparation.service import as_a_card, confirm_number

    prep = await _apri(mondo)
    prep, _ = await confirm_number(mondo, prep, yes=True, operation="reschedule")
    scheda = as_a_card(prep)

    assert prep.readiness == "NEEDS_INFO"
    assert "quando" in (scheda["says"] or "").lower()
    assert any("Calcetto" in f for f in scheda["what_ora_knows"])
    #     E NON SI CHIEDE QUELLO CHE SI È APPENA TROVATO.
    assert "chi" not in (scheda["says"] or "").lower()[:12]


@pytest.mark.asyncio
async def test_the_answer_becomes_target_and_authority(mondo, monkeypatch):
    """
    §7: «Sabato alle 19, al massimo alle 20» → obiettivo **e** confine.

        IL PRIMO ORARIO È DOVE SI VUOLE ARRIVARE. L'ULTIMO È FIN DOVE SI PUÒ.

    È la forma di quasi tutte le risposte a «a quando?», e leggerne solo una
    vorrebbe dire buttare via metà di quello che una persona ha detto.
    """
    _niente_web(monkeypatch)
    from preparation.service import answer_question, confirm_number

    prep = await _apri(mondo)
    prep, _ = await confirm_number(mondo, prep, yes=True, operation="reschedule")
    prep, _ = await answer_question(
        mondo, prep, text="Sabato alle 19, al massimo alle 20",
        operation="reschedule",
    )

    assert prep.desired_state["start_datetime"].endswith("T19:00:00")
    assert prep.structured_authority["desired"].endswith("T19:00:00")
    assert any(a.endswith("T20:00:00")
               for a in prep.structured_authority["alternatives"])
    assert prep.structured_authority["latest"].endswith("T20:00:00")


@pytest.mark.asyncio
async def test_a_complete_request_becomes_ready(mondo, monkeypatch):
    """§6: controparte, numero confermato, obiettivo, contesto, orario → READY."""
    _niente_web(monkeypatch)
    from preparation.service import answer_question, confirm_number

    prep = await _apri(mondo)
    prep, _ = await confirm_number(mondo, prep, yes=True, operation="reschedule")
    prep, _ = await answer_question(
        mondo, prep, text="sabato alle 19", operation="reschedule",
    )

    assert prep.readiness == "READY"
    assert prep.conversation_ready is True
    assert prep.can_become_a_call() is True


# ---------------------------------------------------------------------------
# 4 · Il riassunto
# ---------------------------------------------------------------------------

async def _pronta(db, monkeypatch):
    _niente_web(monkeypatch)
    from preparation.service import answer_question, confirm_number

    prep = await _apri(db)
    prep, _ = await confirm_number(db, prep, yes=True, operation="reschedule")
    prep, _ = await answer_question(
        db, prep, text="Sabato alle 19, al massimo alle 20",
        operation="reschedule",
    )
    return prep


@pytest.mark.asyncio
async def test_the_brief_carries_no_internal_ids(mondo, monkeypatch):
    """
    §8: il riassunto porta il nome del campo, mai gli identificativi.

        IL PACCHETTO PORTA IL NOME DEL CAMPO, MAI IL VALORE.

    La stessa regola di V3.15, sullo stesso motivo: chi telefona non sceglie
    l'evento, quindi non deve sapere che gli eventi hanno un nome. E nemmeno
    il numero serve a chi parla — sta già componendo.
    """
    import json

    prep = await _pronta(mondo, monkeypatch)
    testo = json.dumps(prep.mission_brief, ensure_ascii=False)

    assert "ced_calcetto" not in testo
    assert prep.preparation_id not in testo
    assert "+393330000001" not in testo
    assert prep.idempotency_key not in testo


@pytest.mark.asyncio
async def test_the_brief_says_what_it_cannot_decide(mondo, monkeypatch):
    """
    §8: quello che non si può decidere va detto, più di quello che si può.

    Un mandato scritto solo in positivo lascia intendere che il resto sia
    trattabile.
    """
    prep = await _pronta(mondo, monkeypatch)
    vietato = prep.mission_brief["non_posso_decidere"]

    assert any("costi" in v for v in vietato)
    assert any("impegni" in v for v in vietato)


@pytest.mark.asyncio
async def test_the_summary_reads_like_a_person_wrote_it(mondo, monkeypatch):
    """
    §15.4: la frase che una persona legge prima di dire di sì.

    È l'ultima occasione per accorgersi che ORA ha capito storto, e quindi non
    può contenere niente che assomigli a uno stato interno.
    """
    from preparation.brief import reads_like

    prep = await _pronta(mondo, monkeypatch)
    frase = reads_like(prep)

    assert frase.startswith("Chiamerò Lorenzo")
    assert "19:00" in frase
    assert "posso accettare" in frase
    for tecnico in ("plan_", "prep_", "ced_", "READY", "authority", "{"):
        assert tecnico not in frase


# ---------------------------------------------------------------------------
# 5 · Il piano, che resta lo stesso
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_same_request_opens_one_preparation_and_one_plan(mondo, monkeypatch):
    """
    §11: la stessa frase detta due volte è la stessa richiesta.

        LA STESSA FRASE NON APRE DUE PRATICHE.

    Chi ripete — perché la rete è caduta, perché ha premuto due volte —
    ritrova quella di prima, con dentro le risposte già date.
    """
    _niente_web(monkeypatch)
    from autonomy.orchestrator import plan_a_request
    from autonomy.plan import PLANS
    from preparation.preparation import PREPARATIONS

    frase = "Chiama Lorenzo e sposta il calcetto"
    primo, prep1, _ = await plan_a_request(
        mondo, owner_id=UID, user_request=frase, counterparty="Lorenzo",
        operation="reschedule",
    )
    secondo, prep2, _ = await plan_a_request(
        mondo, owner_id=UID, user_request=frase, counterparty="Lorenzo",
        operation="reschedule",
    )

    assert primo.plan_id == secondo.plan_id
    assert prep1.preparation_id == prep2.preparation_id
    assert len(mondo[PLANS].righe) == 1
    assert len(mondo[PREPARATIONS].righe) == 1


@pytest.mark.asyncio
async def test_the_plan_keeps_its_identity_when_the_call_arrives(mondo, monkeypatch):
    """
    §10: lo stesso `plan_id` dalla frase fino alla telefonata.

        IL PIANO IMPARA IL NOME DELLA MISSIONE. NON NE PRENDE UNO NUOVO.

    L'identità è la richiesta, e la richiesta non cambia. Se cambiasse qui, si
    avrebbero due propositi per una cosa sola — e due posti in cui dire
    «fatto».
    """
    _niente_web(monkeypatch)
    from autonomy.plan import PLANS, by_id
    from autonomy.orchestrator import plan_a_request
    from preparation.service import answer_question, confirm_number, turn_into_a_call

    plan, prep, _ = await plan_a_request(
        mondo, owner_id=UID, user_request="Chiama Lorenzo e sposta il calcetto",
        counterparty="Lorenzo", operation="reschedule",
    )
    prima = plan.plan_id
    chiave = plan.idempotency_key
    assert plan.state == "proposed"

    prep, _ = await confirm_number(mondo, prep, yes=True, operation="reschedule")
    prep, _ = await answer_question(
        mondo, prep, text="sabato alle 19", operation="reschedule",
    )
    call, perche = await turn_into_a_call(mondo, prep, operation="reschedule")

    assert call is not None, perche
    dopo = await by_id(mondo, UID, prima)
    assert dopo.plan_id == prima
    assert dopo.idempotency_key == chiave
    assert dopo.call_id == call.id
    assert dopo.state == "waiting_authority"
    assert len(mondo[PLANS].righe) == 1


@pytest.mark.asyncio
async def test_a_blocked_preparation_never_becomes_a_call(mondo, monkeypatch):
    """
    §9 e §16: senza i due sì non nasce nessuna telefonata, e il piano lo dice.

    È il cancello visto dall'alto: non «la chiamata fallisce», ma «la chiamata
    non esiste».
    """
    _niente_web(monkeypatch)
    from autonomy.orchestrator import plan_a_request
    from autonomy.plan import by_id
    from preparation.service import confirm_number, turn_into_a_call

    plan, prep, _ = await plan_a_request(
        mondo, owner_id=UID, user_request="Chiama Lorenzo e sposta il calcetto",
        counterparty="Lorenzo", operation="reschedule",
    )
    prep, _ = await confirm_number(mondo, prep, yes=False)

    call, perche = await turn_into_a_call(mondo, prep, operation="reschedule")
    assert call is None
    assert mondo["phone_calls"].righe == []

    dopo = await by_id(mondo, UID, plan.plan_id)
    assert dopo.state == "proposed"
    assert dopo.call_id == ""


# ---------------------------------------------------------------------------
# 6 · Quello che si mostra
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_nothing_technical_reaches_the_person(mondo, monkeypatch):
    """
    §16: la scheda non espone stato interno.

    Non la chiave, non i riferimenti canonici, non l'autorità grezza, non il
    verdetto in inglese. Se una cosa non si sa tradurre, non esce.
    """
    import json

    prep = await _pronta(mondo, monkeypatch)
    from preparation.service import as_a_card

    testo = json.dumps(as_a_card(prep), ensure_ascii=False)

    assert prep.idempotency_key not in testo
    assert "ced_calcetto" not in testo
    assert "structured_authority" not in testo
    assert "context_refs" not in testo
    assert "READY" not in testo
    assert "Pronta" in testo


def test_every_readiness_has_words_a_person_can_read():
    """Un verdetto senza una frase è un verdetto che nessuno può mostrare."""
    from preparation.preparation import COME_SI_LEGGE

    for verdetto in ("READY", "NEEDS_INFO", "AMBIGUOUS", "BLOCKED"):
        assert COME_SI_LEGGE.get(verdetto)


def test_every_provenance_has_words_a_person_can_read():
    """Lo stesso per le fonti: una provenienza muta non si può mostrare."""
    from preparation.contacts import COME_SI_DICE, QUANTO_CI_SI_FIDA

    for fonte in QUANTO_CI_SI_FIDA:
        assert COME_SI_DICE.get(fonte), fonte


@pytest.mark.asyncio
async def test_prepare_call_is_idempotent_while_call_is_active(mondo, monkeypatch):
    """A retry after prepare-call returns the same active PhoneCall."""
    prep = await _pronta(mondo, monkeypatch)

    from preparation.service import turn_into_a_call

    first, why = await turn_into_a_call(mondo, prep, operation="reschedule")
    assert first is not None, why
    assert first.state == "authorised"

    second, why = await turn_into_a_call(mondo, prep, operation="reschedule")
    assert second is not None, why
    assert second.id == first.id
    assert len(mondo["phone_calls"].righe) == 1
