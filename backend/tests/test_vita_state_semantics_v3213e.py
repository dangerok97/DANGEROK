"""
V3.21.3e — selezionata, in corso e completa sono tre cose diverse.

    FAMIGLIA AL 100%, CLICCATA, DICEVA «IN CORSO».

Misurato in app su V3.21.3d, e due volte: Famiglia al 100% e Lavoro al 100%
mostravano «In corso» appena selezionate, e sotto il titolo comparivano
«Continua con Lavoro» e «Lo faccio più tardi» — cioè un invito a continuare
una cosa finita e il permesso di rimandare il niente.

Le cause erano due, e nessuna delle due era il testo:

  - la selezione scriveva sopra lo stato: `if (area.current) return 'In corso'`
    metteva la stessa etichetta a un'area vuota e a una completa, purché fosse
    quella aperta;
  - la «prossima area» la sceglieva il client, come «la prima della lista che
    non sia piena» — l'ordine del menu travestito da consiglio, con accanto
    una frase («Casa è quasi completa») che nessuno aveva verificato.

Qui si fissano le due semantiche: quello che ORA sa non dipende da dove stai
guardando, e un consiglio ha un motivo che si può controllare.
"""

from __future__ import annotations

import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def _area(area_id: str, percent: int, aperti: int = 0, *, ordine: int = 1, titolo: str = "") -> dict:
    """Un'area come la vede la schermata, ridotta a quello che conta qui."""
    return {
        "area_id": area_id,
        "title": titolo or area_id.capitalize(),
        "percent": percent,
        "order": ordine,
        "open_objectives": [
            {"ref": "%s.x%d" % (area_id, i), "label": "cosa %d" % i} for i in range(aperti)
        ],
    }


# ===========================================================================
# 1 · Il consiglio ha un motivo, e il motivo si controlla
# ===========================================================================

def test_the_next_area_always_comes_with_a_reason_code():
    from life_profile.recommend import MOTIVI, next_recommended_area

    scelta = next_recommended_area([_area("casa", 86, 1), _area("salute", 0, 4, ordine=10)])
    assert scelta is not None
    assert scelta["reason_code"] in MOTIVI
    assert scelta["reason"], "la UI deve poter mostrare una frase, non un codice"


def test_an_area_one_step_from_the_end_wins_over_an_empty_one():
    """
    Il passo più corto prima: chiudere Casa costa una risposta, cominciare
    Salute ne costa cinque. È questa la regola che rende vera la frase.
    """
    from life_profile.recommend import next_recommended_area

    scelta = next_recommended_area([
        _area("salute", 0, 5, ordine=10),
        _area("casa", 86, 1, ordine=1, titolo="Casa"),
    ])
    assert scelta["area_id"] == "casa"
    assert scelta["reason_code"] == "quasi_completa"
    assert scelta["reason"] == "Casa è quasi completa: manca solo una cosa."


def test_almost_complete_needs_to_be_almost_complete():
    """A metà strada «quasi completa» sarebbe una bugia piccola, ma una bugia."""
    from life_profile.recommend import next_recommended_area

    scelta = next_recommended_area([_area("casa", 40, 1), _area("lavoro", 20, 3, ordine=2)])
    assert scelta["reason_code"] == "un_solo_passo"
    assert scelta["area_id"] == "casa"


def test_an_area_ora_knows_nothing_about_comes_before_a_half_done_one():
    from life_profile.recommend import next_recommended_area

    scelta = next_recommended_area([
        _area("lavoro", 45, 3, ordine=2),
        _area("casa", 0, 4, ordine=1, titolo="Casa"),
    ])
    assert scelta["area_id"] == "casa"
    assert scelta["reason_code"] == "mai_iniziata"
    assert scelta["reason"] == "Di Casa non so ancora niente."


def test_a_complete_area_is_never_recommended():
    from life_profile.recommend import next_recommended_area

    assert next_recommended_area([_area("casa", 100), _area("lavoro", 100)]) is None
    scelta = next_recommended_area([_area("casa", 100), _area("lavoro", 50, 2)])
    assert scelta["area_id"] == "lavoro"


def test_an_area_with_nothing_left_to_ask_is_never_recommended():
    """95% senza più niente da chiedere non è un passo: è un vicolo cieco."""
    from life_profile.recommend import next_recommended_area

    scelta = next_recommended_area([_area("casa", 95, 0), _area("lavoro", 30, 2)])
    assert scelta["area_id"] == "lavoro"


def test_the_area_you_are_in_is_not_where_to_go_next():
    from life_profile.recommend import next_recommended_area

    scelta = next_recommended_area([_area("casa", 86, 1), _area("lavoro", 30, 2)], exclude="casa")
    assert scelta["area_id"] == "lavoro"
    assert next_recommended_area([_area("casa", 86, 1)], exclude="casa") is None


def test_the_same_profile_always_gets_the_same_advice():
    """Un consiglio che cambia a ogni ricarica non è un consiglio."""
    from life_profile.recommend import next_recommended_area

    aree = [_area("casa", 50, 2, ordine=1), _area("lavoro", 50, 2, ordine=2)]
    prima = next_recommended_area(aree)
    for _ in range(5):
        assert next_recommended_area(list(reversed(aree))) == prima


def test_there_is_only_one_ranking_in_the_backend():
    """
    `_suggest` e il pannello di Vita devono consigliare la stessa area: due
    classifiche scritte in due file finiscono per dirne due diverse.
    """
    from life_profile.completeness import _suggest, profile_completeness
    from life_profile.recommend import next_recommended_area

    comp = profile_completeness(facts={"casa.situazione": "affitto", "casa.citta": "Roma"})
    atteso = next_recommended_area([a.model_dump() for a in comp.areas if a.has_room])
    assert _suggest(comp.areas, ()) == atteso["area_id"]


# ===========================================================================
# 2 · Lo stato non dipende da dove stai guardando
# ===========================================================================

def _servizio(monkeypatch, *, area_corrente: str, aree: list, risposte: list, active=False):
    """Il servizio guidato con dentro un profilo deciso dal test."""
    from life_profile.completeness import ProfileCompleteness
    from life_profile.setup import GuidedSetupService

    servizio = GuidedSetupService(db=None)
    meta = {
        "guided_current_area": area_corrente,
        "first_run_finished": True,
        "guided_question_active": active,
        "guided_answered": risposte,
    }

    class FintoProfilo:
        async def completeness(self, user_id):
            return ProfileCompleteness(percent=88, areas=aree)

    async def finto_load(user_id, create=False):
        return None, None, meta

    async def finti_fatti(user_id):
        return {}

    async def finto_nome(user_id):
        return True

    monkeypatch.setattr(servizio, "_load", finto_load)
    monkeypatch.setattr(servizio, "_facts", finti_fatti)
    monkeypatch.setattr(servizio, "_has_name", finto_nome)
    monkeypatch.setattr(servizio, "profile", FintoProfilo())
    return servizio


def _profilo_reale(completa: str) -> list:
    """Le dieci aree vere, con una portata al 100% e senza più buchi."""
    from life_profile.areas import all_areas
    from life_profile.completeness import AreaCompleteness

    aree = []
    for a in all_areas():
        piena = a.id == completa
        aree.append(AreaCompleteness(
            area_id=a.id, title=a.title, description=a.description, purpose=a.purpose,
            icon_key=a.icon_key, sensitivity=a.sensitivity, order=a.order,
            percent=100 if piena else 40,
            state="known_enough" if piena else "started",
            state_label="Conosciuta" if piena else "Buon punto di partenza",
            known_count=8 if piena else 3, applicable_count=8,
            open_objectives=[] if piena else [{"ref": a.id + ".manca", "label": "Qualcosa"}],
        ))
    return aree


def _tutte_le_risposte(area_id: str) -> list:
    from life_profile.guided import for_area

    return [o.id for o in for_area(area_id)]


@pytest.mark.asyncio
@pytest.mark.parametrize("area_id", ["famiglia", "lavoro"])
async def test_selecting_a_complete_area_does_not_make_it_in_progress(monkeypatch, area_id):
    """I due casi visti in app, tutti e due."""
    servizio = _servizio(
        monkeypatch,
        area_corrente=area_id,
        aree=_profilo_reale(area_id),
        risposte=_tutte_le_risposte(area_id),
    )
    stato = await servizio.state("u1")
    scelta = next(a for a in stato["areas"] if a["area_id"] == area_id)

    assert scelta["selected"] is True, "è l'area aperta"
    assert scelta["in_progress"] is False, "ma non le si sta chiedendo niente"
    assert scelta["percent"] == 100
    assert scelta["state_label"] == "Conosciuta"
    assert stato["objective"] is None, "un'area completa non apre una domanda"


@pytest.mark.asyncio
async def test_in_progress_means_a_question_is_open_right_now(monkeypatch):
    servizio = _servizio(
        monkeypatch, area_corrente="casa", aree=_profilo_reale("famiglia"), risposte=[], active=True,
    )
    stato = await servizio.state("u1")
    casa = next(a for a in stato["areas"] if a["area_id"] == "casa")

    assert stato["objective"] is not None
    assert casa["in_progress"] is True
    assert casa["selected"] is True
    # E una sola area per volta può esserlo.
    assert [a["area_id"] for a in stato["areas"] if a["in_progress"]] == ["casa"]


@pytest.mark.asyncio
async def test_selection_never_touches_what_ora_knows(monkeypatch):
    """
    L'audit sulle dieci aree: si apre ognuna, e nessuna delle altre nove
    cambia percentuale o stato per il fatto che una sia stata scelta.
    """
    from life_profile.areas import all_areas

    riferimento = None
    for a in all_areas():
        servizio = _servizio(
            monkeypatch, area_corrente=a.id, aree=_profilo_reale("famiglia"),
            risposte=_tutte_le_risposte(a.id),
        )
        stato = await servizio.state("u1")
        istantanea = {
            x["area_id"]: (x["percent"], x["state"], x["state_label"])
            for x in stato["areas"]
        }
        if riferimento is None:
            riferimento = istantanea
        assert istantanea == riferimento, "aprire %s ha cambiato lo stato di un'altra area" % a.id
        assert sum(1 for x in stato["areas"] if x["selected"]) == 1


@pytest.mark.asyncio
async def test_a_complete_area_has_nothing_left_to_show_as_missing(monkeypatch):
    """Senza buchi non c'è «cosa manca» da disegnare, e nemmeno da promettere."""
    servizio = _servizio(
        monkeypatch, area_corrente="lavoro", aree=_profilo_reale("lavoro"),
        risposte=_tutte_le_risposte("lavoro"),
    )
    stato = await servizio.state("u1")
    lavoro = next(a for a in stato["areas"] if a["area_id"] == "lavoro")
    assert lavoro["open_objectives"] == []


@pytest.mark.asyncio
async def test_the_advice_never_points_at_the_area_you_are_already_in(monkeypatch):
    servizio = _servizio(
        monkeypatch, area_corrente="lavoro", aree=_profilo_reale("lavoro"),
        risposte=_tutte_le_risposte("lavoro"),
    )
    stato = await servizio.state("u1")
    consiglio = stato["recommended"]

    assert consiglio is not None
    assert consiglio["area_id"] != "lavoro"
    assert consiglio["reason_code"]
    assert consiglio["reason"]


@pytest.mark.asyncio
async def test_the_panel_and_the_rail_read_the_same_numbers(monkeypatch):
    """
    Pannello e colonna di destra disegnano la stessa lista: non esiste un
    secondo posto dove la percentuale possa diventare un altro numero.
    """
    servizio = _servizio(
        monkeypatch, area_corrente="famiglia", aree=_profilo_reale("famiglia"),
        risposte=_tutte_le_risposte("famiglia"),
    )
    stato = await servizio.state("u1")
    for a in stato["areas"]:
        if a["percent"] == 100:
            assert a["state_label"] == "Conosciuta"
            assert a["open_objectives"] == []
        if a["percent"] == 0:
            assert a["state_label"] == "Non iniziata"


# ===========================================================================
# 3 · Un rifiuto è una risposta, e si scrive in un posto solo
# ===========================================================================

@pytest.mark.asyncio
async def test_a_refusal_reaches_the_projection_that_lists_what_is_missing(monkeypatch):
    """
    Misurato in app: «salute.visita» era stato rifiutato mesi prima, ma la
    completezza legge i rifiuti da `refused_keys` e quello lì non ci era mai
    arrivato. Restava fra i «cosa manca» di Salute — pastiglia cliccabile e
    «Continua con Salute» compresi — e non apriva niente, perché il flusso il
    rifiuto se lo ricordava benissimo.
    """
    from life_profile.setup import GuidedSetupService

    class FintaSessione:
        def __init__(self):
            self.meta = {}
            self.refused_keys = []
            self.status = "active"

        def touch(self):
            pass

    class FintoRepo:
        async def save_session(self, sess):
            pass

    sess = FintaSessione()
    servizio = GuidedSetupService(db=None)

    async def finto_load(user_id, create=False):
        return FintoRepo(), sess, sess.meta

    async def finti_fatti(user_id):
        return {}

    async def finto_state(user_id):
        return {"ok": True}

    monkeypatch.setattr(servizio, "_load", finto_load)
    monkeypatch.setattr(servizio, "_facts", finti_fatti)
    monkeypatch.setattr(servizio, "state", finto_state)

    await servizio.answer("u1", objective_id="salute.visita", action="decline")

    assert "salute.visita" in sess.meta["guided_declined"], "il flusso non lo richiede"
    assert "salute.visita" in sess.refused_keys, "e nemmeno la schermata lo ripropone"


def test_a_declined_thing_stops_being_something_that_is_missing():
    """
    Sparisce da «cosa manca», ma non dalla percentuale: un rifiuto dice
    qualcosa sulla conversazione, non sulla vita, e ORA continua a non sapere
    quella cosa. Farla salire perché qualcuno ha detto di no sarebbe l'unica
    lettura di questo numero che è una bugia.
    """
    from life_profile.areas import area
    from life_profile.completeness import area_completeness

    senza = area_completeness(
        area("salute"), facts={"salute.obiettivi": ["movimento"]}, provenance={},
        declined_refs=[], not_applicable_refs=[], inferred_refs=[],
    )
    con = area_completeness(
        area("salute"), facts={"salute.obiettivi": ["movimento"]}, provenance={},
        declined_refs=["salute.visita"], not_applicable_refs=[], inferred_refs=[],
    )
    assert "salute.visita" in [o["ref"] for o in senza.open_objectives]
    assert "salute.visita" not in [o["ref"] for o in con.open_objectives]
    assert con.percent == senza.percent, "un no non è un sì"


def test_an_area_with_only_refusals_left_is_not_a_complete_area():
    """
    52% e niente più da chiedere: «so già tutto quello che mi serve» sarebbe
    falso, e nessun consiglio deve mandare lì una persona.
    """
    from life_profile.recommend import next_recommended_area

    salute = _area("salute", 52, 0)
    assert next_recommended_area([salute]) is None
    scelta = next_recommended_area([salute, _area("casa", 92, 1, ordine=1)])
    assert scelta["area_id"] == "casa"


def test_a_refusal_said_before_the_two_stores_talked_still_counts():
    """
    Il caso vero trovato in app: «salute.visita» rifiutato tempo prima e
    scritto solo nel meta del flusso. La proiezione non lo vedeva, e Salute
    continuava a chiederlo in eterno.
    """
    from life_profile.service import rifiuti_di

    class FintaSessione:
        refused_keys = ["casa.mutuo"]

    uniti = rifiuti_di(FintaSessione(), {"guided_declined": ["salute.visita", "casa.mutuo"]})
    assert uniti == ["casa.mutuo", "salute.visita"], "uniti, e senza doppioni"
    assert rifiuti_di(FintaSessione(), {}) == ["casa.mutuo"]


@pytest.mark.asyncio
async def test_reviewing_an_incomplete_area_does_not_start_its_question(monkeypatch):
    servizio = _servizio(
        monkeypatch, area_corrente="casa", aree=_profilo_reale("famiglia"), risposte=[],
    )
    stato = await servizio.state("u1")
    casa = next(a for a in stato["areas"] if a["area_id"] == "casa")
    assert stato["objective"] is not None
    assert casa["selected"] is True
    assert casa["in_progress"] is False
    assert stato["finished"] is True


@pytest.mark.asyncio
async def test_continue_then_select_then_reload_preserves_question_state(monkeypatch):
    from types import SimpleNamespace
    servizio = _servizio(
        monkeypatch, area_corrente="casa", aree=_profilo_reale("famiglia"), risposte=[],
    )
    sess = SimpleNamespace(meta={"first_run_finished": True}, refused_keys=[], touch=lambda: None)
    class Repo:
        async def save_session(self, session):
            assert session is sess
    async def load(user_id, create=False):
        return Repo(), sess, dict(sess.meta)
    monkeypatch.setattr(servizio, "_load", load)
    for start in (False, True, False):
        state = await servizio.go_to_area("u1", "casa", start_question=start)
        casa = next(a for a in state["areas"] if a["area_id"] == "casa")
        assert casa["in_progress"] is start
        reloaded = await servizio.state("u1")
        assert next(a for a in reloaded["areas"] if a["area_id"] == "casa")["in_progress"] is start


def test_declined_resumable_area_does_not_hide_other_recommendations():
    from life_profile.completeness import AreaCompleteness, _suggest
    base = dict(description="", icon_key="home", sensitivity="normal", applicable_count=3)
    declined = AreaCompleteness(**base, area_id="salute", title="Salute", order=10,
        percent=40, state="started", open_objectives=[])
    available = AreaCompleteness(**base, area_id="casa", title="Casa", order=1,
        percent=92, state="known_enough", open_objectives=[{"ref": "casa.citta"}])
    assert _suggest([declined, available], ["salute"]) == "casa"
