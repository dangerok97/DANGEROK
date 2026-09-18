"""
Quali numeri si possono riusare, e quali vanno richiesti.

    LA FIDUCIA NON È DEL NUMERO: È DELLA COPPIA.

Un numero confermato per Lorenzo si riusa per Lorenzo, senza chiederlo di
nuovo a ogni telefonata. Lo stesso numero accanto al nome di uno studio non
eredita niente. E qualunque numero si può sempre cambiare, rifiutare,
correggere — perché è la contropartita di non chiederlo ogni volta.

Queste prove tengono ferme le due metà di quella frase, e quella in mezzo:
che un numero nuovo, da qualunque parte arrivi, aspetta un sì.
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
NUMERO_A = "+393330000001"
NUMERO_B = "+393330000009"

LA_PARTITA = {
    "id": "ced_calcetto", "user_id": UID, "title": "Calcetto con Lorenzo",
    "start_datetime": "2026-09-25T20:30:00+02:00",
    "end_datetime": "2026-09-25T21:30:00+02:00",
    "timezone": "Europe/Rome", "status": "confirmed",
}
IN_RUBRICA = {
    "id": "con_lorenzo", "user_id": UID, "name": "Lorenzo Bianchi",
    "phone": "+39 333 0000001", "kind": "person",
}


@pytest.fixture
def mondo(monkeypatch):
    """
    Una partita, un Lorenzo in rubrica, nessun modello e niente online.

    Online si esce solo nelle prove che lo dicono: le altre non devono poter
    toccare la rete, nemmeno su una macchina che ha le chiavi.
    """
    import preparation.contacts as risolutore
    import preparation.readiness as valutatore

    async def nessun_modello(_prep):
        return None

    async def niente(self, db, *, owner_id, who):
        return []

    monkeypatch.setattr(valutatore, "_what_the_model_sees", nessun_modello)
    monkeypatch.setattr(risolutore.PublicWeb, "look_for", niente)

    db = FintoDb()
    db.calendar_event_drafts.righe.append(dict(LA_PARTITA))
    db.contacts.righe.append(dict(IN_RUBRICA))
    return db


async def _apri(db, frase="Chiama Lorenzo e sposta il calcetto", chi="Lorenzo"):
    from preparation.service import start

    prep, perche = await start(
        db, owner_id=UID, user_request=frase, counterparty=chi,
        operation="reschedule",
    )
    assert perche == "", perche
    return prep


async def _confermato_una_volta(db):
    """La prima telefonata: trovato in rubrica, e una persona dice sì."""
    from preparation.service import confirm_number

    prep = await _apri(db)
    prep, _ = await confirm_number(db, prep, yes=True, operation="reschedule")
    return prep


def _registro(db):
    from preparation.trust import TRUSTED

    return db[TRUSTED].righe


# ---------------------------------------------------------------------------
# Prima volta
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_new_number_needs_a_yes(mondo):
    """Numero mai confermato → si chiede, e senza il sì non si telefona."""
    prep = await _apri(mondo)

    assert prep.selected_contact.number == NUMERO_A
    assert prep.number_confirmed is False
    assert prep.number_trust == ""
    assert prep.can_become_a_call() is False
    assert _registro(mondo) == []


@pytest.mark.asyncio
async def test_a_yes_makes_the_pair_trusted(mondo):
    """
    Il sì scrive la coppia identità + numero, con quando e da dove.

    È l'unica cosa che permette, la prossima volta, di non chiedere.
    """
    prep = await _confermato_una_volta(mondo)

    assert prep.number_trust == "confirmed_now"
    riga = _registro(mondo)[0]
    assert riga["contact_identity"] == "lorenzo bianchi"
    assert riga["phone_number"] == NUMERO_A
    assert riga["confirmed_by_user"] is True
    assert riga["confirmed_at"]
    assert riga["status"] == "active"
    assert riga["source"] == "address_book"


# ---------------------------------------------------------------------------
# Riuso
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_trusted_number_is_reused_without_asking_again(mondo):
    """
    §4: già confermato, ancora attivo → si usa, e non si richiede.

        «È ANCORA QUESTO?» A OGNI TELEFONATA È RUMORE.

    Una richiesta diversa, un'altra settimana: il numero arriva già usabile,
    e la scheda dice chiaramente quale sarà e perché.
    """
    from preparation.service import as_a_card

    await _confermato_una_volta(mondo)
    prep = await _apri(mondo, frase="Chiama Lorenzo per la cena di sabato")
    scheda = as_a_card(prep)

    assert prep.selected_contact.number == NUMERO_A
    assert prep.number_confirmed is True
    assert prep.number_trust == "trusted"
    assert "confirm_number" not in scheda["you_can_answer"]
    assert "È quello giusto" not in scheda["says"]
    assert "già confermato" in scheda["number_note"]
    assert scheda["contact"]["source_label"] == "Confermato da te"


@pytest.mark.asyncio
async def test_a_trusted_number_can_always_be_changed(mondo):
    """
    §4 e §9: riusarlo senza chiedere non vuol dire non poterlo cambiare.

    È la contropartita: il pulsante per cambiarlo c'è sempre.
    """
    from preparation.service import as_a_card

    await _confermato_una_volta(mondo)
    scheda = as_a_card(await _apri(mondo, frase="Chiama Lorenzo per la cena"))

    assert "change_number" in scheda["you_can_answer"]
    assert "reject_number" in scheda["you_can_answer"]


@pytest.mark.asyncio
async def test_confirming_the_same_pair_twice_changes_nothing(mondo):
    """Idempotenza: la stessa coppia confermata due volte è un record solo."""
    from preparation.service import confirm_number

    prep = await _confermato_una_volta(mondo)
    await confirm_number(mondo, prep, yes=True, operation="reschedule")

    assert len(_registro(mondo)) == 1
    assert _registro(mondo)[0]["status"] == "active"


# ---------------------------------------------------------------------------
# Cambio e rifiuto
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_replacement_needs_its_own_yes_and_retires_the_old(mondo):
    """
    §5: «usa questo invece» → il vecchio diventa vecchio, il nuovo aspetta.

        NON SI SOVRASCRIVE, E NON SI USA ANCORA.
    """
    from preparation.service import change_number, confirm_number
    from preparation.trust import still_trusted

    await _confermato_una_volta(mondo)
    prep = await _apri(mondo, frase="Chiama Lorenzo per la cena")
    prep, _ = await change_number(mondo, prep, number="+39 333 0000009")

    #     IL NUOVO ASPETTA.
    assert prep.selected_contact.number == NUMERO_B
    assert prep.selected_contact.name == "Lorenzo Bianchi"
    assert prep.number_confirmed is False
    assert prep.can_become_a_call() is False

    #     IL VECCHIO NON SI USA PIÙ, E NON È STATO CANCELLATO.
    assert await still_trusted(mondo, UID, "lorenzo bianchi", NUMERO_A) is False
    vecchio = [r for r in _registro(mondo) if r["phone_number"] == NUMERO_A][0]
    assert vecchio["status"] == "stale"
    assert "altro numero" in vecchio["status_says"]

    prep, _ = await confirm_number(mondo, prep, yes=True)
    assert await still_trusted(mondo, UID, "lorenzo bianchi", NUMERO_B) is True


@pytest.mark.asyncio
async def test_the_same_change_twice_is_the_same_change(mondo):
    """§5: il cambio è idempotente."""
    from preparation.service import change_number

    await _confermato_una_volta(mondo)
    prep = await _apri(mondo, frase="Chiama Lorenzo per la cena")
    prep, _ = await change_number(mondo, prep, number="+39 333 0000009")
    prep, _ = await change_number(mondo, prep, number="+39 333 0000009")

    assert len(_registro(mondo)) == 2
    stati = {r["phone_number"]: r["status"] for r in _registro(mondo)}
    assert stati == {NUMERO_A: "stale", NUMERO_B: "active"}


@pytest.mark.asyncio
async def test_a_rejected_number_is_not_proposed_again(mondo):
    """
    §7: «no, non è quello» → non si cancella, e non si ripropone.

    La rubrica lo ha ancora. Non importa: una persona ha detto che non è
    quello, e alla prossima richiesta ORA chiede invece di riproporlo.
    """
    from preparation.service import confirm_number

    prep = await _apri(mondo)
    await confirm_number(mondo, prep, yes=False)

    riga = _registro(mondo)[0]
    assert riga["status"] == "rejected"
    assert riga["phone_number"] == NUMERO_A

    di_nuovo = await _apri(mondo, frase="Chiama Lorenzo per la cena")
    assert di_nuovo.selected_contact is None
    assert all(c.number != NUMERO_A for c in di_nuovo.contact_candidates)
    assert di_nuovo.readiness == "BLOCKED"


# ---------------------------------------------------------------------------
# Conflitti
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_different_number_for_the_same_person_does_not_overwrite(mondo):
    """
    §6: confermato A, la rubrica adesso dice B → si mostrano tutti e due.

        NON SI SOSTITUISCE E NON SI IGNORA.
    """
    from preparation.service import as_a_card
    from preparation.trust import still_trusted

    await _confermato_una_volta(mondo)
    mondo.contacts.righe[0]["phone"] = "+39 333 0000009"

    prep = await _apri(mondo, frase="Chiama Lorenzo per la cena")
    scheda = as_a_card(prep)

    assert prep.number_conflict is True
    assert prep.selected_contact is None
    assert {c.number for c in prep.contact_candidates} == {NUMERO_A, NUMERO_B}
    assert "avevi già confermato" in prep.readiness_says
    assert "Quale devo usare" in prep.readiness_says
    assert "choose" in scheda["you_can_answer"]
    assert prep.can_become_a_call() is False
    #     E A NON È STATO TOCCATO.
    assert await still_trusted(mondo, UID, "lorenzo bianchi", NUMERO_A) is True


@pytest.mark.asyncio
async def test_choosing_the_trusted_one_in_a_conflict_needs_no_second_yes(mondo):
    """Scegliere il numero già confermato non chiede una seconda conferma."""
    from preparation.service import choose_contact

    await _confermato_una_volta(mondo)
    mondo.contacts.righe[0]["phone"] = "+39 333 0000009"
    prep = await _apri(mondo, frase="Chiama Lorenzo per la cena")

    prep, _ = await choose_contact(mondo, prep, number=NUMERO_A)
    assert prep.number_confirmed is True
    assert prep.number_trust == "trusted"


@pytest.mark.asyncio
async def test_the_same_number_for_another_identity_earns_no_trust(mondo):
    """
    §15: lo stesso numero, un'altra identità → nessuna fiducia implicita.

    Confermato per Lorenzo, trovato accanto allo Studio Bianchi: è un'altra
    coppia, e riparte da zero.
    """
    await _confermato_una_volta(mondo)
    mondo["phone_calls"].righe.append({
        "id": "tel_x", "owner_id": UID, "calling_whom": "Studio Dentistico Rossi",
        "to_number": NUMERO_A, "state": "ended",
    })

    prep = await _apri(
        mondo, frase="Chiama lo Studio Dentistico Rossi",
        chi="Studio Dentistico Rossi",
    )
    assert prep.selected_contact.number == NUMERO_A
    assert prep.selected_contact.trusted is False
    assert prep.number_confirmed is False
    assert prep.can_become_a_call() is False


# ---------------------------------------------------------------------------
# Quello che dice la persona
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_saying_whose_number_it_is_confirms_it(mondo):
    """
    §8: «il numero di Lorenzo è …» nomina persona e numero insieme: vale.
    """
    from preparation.service import set_contact_number
    from preparation.trust import still_trusted

    prep = await _apri(mondo)
    prep, _ = await set_contact_number(mondo, prep, number="+39 333 0000009")

    assert prep.number_confirmed is True
    assert await still_trusted(mondo, UID, "lorenzo bianchi", NUMERO_B) is True


@pytest.mark.asyncio
async def test_a_number_in_the_request_is_for_that_request_only(mondo):
    """
    §8: «chiama il 333…» vale per questa richiesta, non per sempre.

    Si ricorda che quel numero è passato, ma non con fiducia: la prossima
    volta si chiede.
    """
    prep = await _apri(mondo, frase="Chiama il 333 0000077 per la partita", chi="")

    assert prep.number_trust == "confirmed_now"
    assert prep.number_confirmed is True
    riga = [r for r in _registro(mondo) if r["phone_number"] == "+393330000077"][0]
    assert riga["confirmed_by_user"] is False


@pytest.mark.asyncio
async def test_saying_it_in_the_request_confirms_it_for_that_person(mondo):
    """§8: «il numero di Lorenzo è 333…» detto nella richiesta vale per Lorenzo."""
    from preparation.trust import still_trusted

    prep = await _apri(
        mondo, frase="Il numero di Lorenzo è 333 0000088, chiamalo per la partita",
        chi="",
    )
    assert prep.number_confirmed is True
    assert await still_trusted(mondo, UID, "lorenzo", "+393330000088") is True


# ---------------------------------------------------------------------------
# Il cancello
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_call_with_an_untrusted_number(mondo):
    """§10: trovato ma mai confermato → la telefonata non nasce."""
    from preparation.service import answer_question, turn_into_a_call

    prep = await _apri(mondo)
    prep, _ = await answer_question(mondo, prep, text="sabato alle 19",
                                    operation="reschedule")
    call, perche = await turn_into_a_call(mondo, prep)

    assert call is None
    assert "confermato" in perche
    assert mondo["phone_calls"].righe == []


@pytest.mark.asyncio
async def test_a_number_revoked_after_preparation_stops_the_call(mondo):
    """
    §10: la fiducia si rilegge al momento della chiamata, non si ricorda.

    Preparata con un numero affidabile; nel frattempo qualcuno l'ha
    rifiutato da un'altra parte. La chiamata non nasce.
    """
    from preparation import trust
    from preparation.service import answer_question, turn_into_a_call

    await _confermato_una_volta(mondo)
    prep = await _apri(mondo, frase="Chiama Lorenzo e sposta la partita di calcetto")
    prep, _ = await answer_question(mondo, prep, text="sabato alle 19",
                                    operation="reschedule")
    assert prep.can_become_a_call() is True

    await trust.reject(mondo, owner_id=UID, identity="lorenzo bianchi",
                       display_name="Lorenzo Bianchi", number=NUMERO_A)
    call, perche = await turn_into_a_call(mondo, prep)

    assert call is None
    assert "non è più confermato" in perche
    assert mondo["phone_calls"].righe == []


@pytest.mark.asyncio
async def test_a_trusted_number_opens_the_gate(mondo):
    """§10 B: affidabile per la stessa identità, ancora attivo → si passa."""
    from preparation.service import answer_question, turn_into_a_call

    await _confermato_una_volta(mondo)
    prep = await _apri(mondo, frase="Chiama Lorenzo e sposta la partita di calcetto")
    prep, _ = await answer_question(mondo, prep, text="sabato alle 19",
                                    operation="reschedule")
    call, perche = await turn_into_a_call(mondo, prep, operation="reschedule")

    assert call is not None, perche
    assert call.to_number == NUMERO_A


# ---------------------------------------------------------------------------
# Online
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_web_candidate_still_waits_for_a_yes(mondo, monkeypatch):
    """§12: trovato sul sito ufficiale resta un candidato."""
    import preparation.contacts as risolutore

    async def il_sito(self, db, *, owner_id, who):
        return [risolutore.ContactCandidate(
            name="Hotel Esempio", number="+390410000001", kind="business",
            source="official_site", source_detail="hotelesempio.it",
            source_url="https://hotelesempio.it/contatti",
            confidence=risolutore.QUANTO_CI_SI_FIDA["official_site"],
            contact_identity="hotel esempio", discovered_at="2026-09-18T00:00:00+00:00",
        )]

    monkeypatch.setattr(risolutore.PublicWeb, "look_for", il_sito)
    prep = await _apri(mondo, frase="Chiama l'Hotel Esempio", chi="Hotel Esempio")

    assert prep.selected_contact.source == "official_site"
    assert prep.selected_contact.source_url.startswith("https://")
    assert prep.number_confirmed is False
    assert prep.can_become_a_call() is False


@pytest.mark.asyncio
async def test_nothing_online_means_asking(mondo):
    """§11: niente di affidabile online → si chiede, senza fingere."""
    prep = await _apri(mondo, frase="Chiama l'Hotel Inesistente", chi="Hotel Inesistente")

    assert prep.selected_contact is None
    assert prep.readiness == "BLOCKED"
    assert "Me lo dici tu" in prep.readiness_says


def test_a_page_about_another_business_is_not_a_source():
    """
    Misurato sul vero: «Farmacia Crosa Torino» → il primo risultato era
    un'altra farmacia. Una pagina che non parla di chi cerchiamo non conta.
    """
    from preparation.contacts import _is_it_about

    assert _is_it_about("Farmacia Crosa Torino", "Farmacia Pozzo Strada Torino") is False
    assert _is_it_about("Hotel Excelsior Venezia Lido",
                        "Hotel Excelsior Venice Lido lungomare") is True


def test_a_portal_is_not_the_official_site():
    """Misurato sul vero: «visitlido.it» contiene «lido», e non è l'albergo."""
    from preparation.contacts import _how_official

    assert _how_official("https://www.visitlido.it/x", "Hotel Excelsior Venezia Lido", "")[0] == "web"
    assert _how_official("https://www.hotelexcelsiorvenezia.com/it/contatti",
                         "Hotel Excelsior Venezia Lido", "")[0] == "official_site"
    assert _how_official("https://www.booking.com/x",
                         "Hotel Excelsior Venezia Lido", "")[0] == "public_directory"


@pytest.mark.asyncio
async def test_the_official_site_is_proposed_first_and_still_needs_a_yes(mondo, monkeypatch):
    """
    §11: si preferisce il sito ufficiale — lo si propone, non lo si decide.

    Gli altri numeri restano visibili, come alternativa.
    """
    import preparation.contacts as risolutore
    from preparation.service import as_a_card

    Q = risolutore.QUANTO_CI_SI_FIDA

    async def tre(self, db, *, owner_id, who):
        return [
            risolutore.ContactCandidate(name=who, number="+390410000001", kind="business",
                                        source="official_site", confidence=Q["official_site"],
                                        contact_identity="hotel esempio"),
            risolutore.ContactCandidate(name=who, number="+390410000002", kind="business",
                                        source="web", confidence=Q["web"],
                                        contact_identity="hotel esempio"),
        ]

    monkeypatch.setattr(risolutore.PublicWeb, "look_for", tre)
    prep = await _apri(mondo, frase="Chiama l'Hotel Esempio", chi="Hotel Esempio")
    scheda = as_a_card(prep)

    assert prep.selected_contact.number == "+390410000001"
    assert prep.number_confirmed is False
    assert [c["number"] for c in scheda["other_candidates"]] == ["+390410000002"]
    assert scheda["candidates"] == []


def test_an_impossible_italian_number_is_not_a_candidate():
    """Misurato sul vero: «+3939041271680» non è un numero, è un prefisso ripetuto."""
    from preparation.contacts import _clean_number

    assert _clean_number("+3939041271680") == ""
    assert _clean_number("+39 041 526 0201") == "+390415260201"
    assert _clean_number("+39 333 0000001") == "+393330000001"
