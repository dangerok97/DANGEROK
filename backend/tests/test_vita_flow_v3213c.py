"""
V3.21.3c — Vita: quello che manca si può davvero rispondere.

    UN'AREA AL 92% HA ANCORA QUALCOSA DA CHIEDERE.
    E QUELLO CHE ORA SA SI DICE CON I FATTI, NON CON I NUMERI.

Misurato in app: Casa era al 92%, «Continua con Casa» non apriva niente, e
Studio al 67% aveva tre cose mancanti — nessuna raggiungibile. Il motivo stava
sotto: le domande scritte a mano erano tutte risposte, e i buchi rimasti
vivevano solo nel catalogo della completezza, senza nessun modo di essere
riempiti.
"""

from __future__ import annotations

import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ===========================================================================
# 1 · Un buco senza domanda diventa una domanda
# ===========================================================================

def test_a_gap_without_a_written_question_gets_one():
    from life_profile.gaps import derived_objective

    costruita = derived_objective("mlc.life_places.home")
    assert costruita is not None
    assert costruita.area_id == "casa"
    # L'etichetta è quella che la persona legge fra i «cosa manca»: si tocca
    # solo la maiuscola e il punto interrogativo.
    assert costruita.question == "Dove vivi?"
    assert costruita.control in ("text", "document_upload")


def test_a_written_question_always_wins():
    """Quella scritta a mano conosce le opzioni: non si sostituisce."""
    from life_profile.gaps import any_objective, derived_objective
    from life_profile.guided import objective

    assert derived_objective("casa.situazione") is None
    scritta = any_objective("casa.situazione")
    assert scritta is objective("casa.situazione")
    assert scritta.options, "una domanda scritta a mano ha le sue opzioni"


def test_a_label_that_is_not_a_question_stays_a_label():
    """«Date esami e scadenze» non diventa «Date esami e scadenze?»."""
    from life_profile.gaps import _come_si_chiede

    assert _come_si_chiede("date esami e scadenze") == "Date esami e scadenze"
    assert _come_si_chiede("dove vivi") == "Dove vivi?"
    assert _come_si_chiede("Quanti figli?") == "Quanti figli?"
    assert _come_si_chiede("") == ""


def test_the_first_answerable_gap_skips_what_cannot_be_asked():
    from life_profile.gaps import first_answerable_gap

    area = {
        "open_objectives": [
            {"ref": "questo.non.esiste", "label": "Niente"},
            {"ref": "casa.utenze", "label": "Utenze"},
        ],
    }
    scelto = first_answerable_gap(area)
    assert scelto is not None and scelto.id == "casa.utenze"

    # Quello che la persona ha già visto non si ripropone.
    assert first_answerable_gap(area, seen={"casa.utenze"}) is None


def test_a_gap_belongs_to_its_area():
    """Un link non può mandare la persona in una stanza sbagliata."""
    from life_profile.gaps import area_of

    assert area_of("casa.utenze") == "casa"
    assert area_of("mlc.life_places.home") == "casa"
    assert area_of("niente.di.niente") is None


# ===========================================================================
# 2 · Quello che ORA sa già, detto con i fatti
# ===========================================================================

def test_known_facts_are_said_with_the_words_the_person_chose():
    """
    Nel profilo un'opzione è salvata con il suo identificativo — `universita`,
    `fine` — e mostrarlo così è mostrare il magazzino.
    """
    from life_profile.gaps import known_items

    fatti = known_items("studio", {"studio.tipo": "universita", "studio.fase": "fine"})
    detti = {f["ref"]: f["value"] for f in fatti}
    assert detti["studio.tipo"] == "Università"
    assert detti["studio.fase"] == "Verso la fine"


def test_a_yes_keeps_the_question_that_makes_it_mean_something():
    """«Active: sì» non è un fatto che qualcuno possa verificare."""
    from life_profile.gaps import known_items

    fatti = {f["ref"]: f for f in known_items("studio", {"studio.active": "si"})}
    riga = fatti["studio.active"]
    assert riga["label"] == "Attualmente studi"
    assert riga["value"] == "Sì"


def test_a_long_question_becomes_a_short_label():
    from life_profile.gaps import known_items

    fatti = {f["ref"]: f for f in known_items("casa", {"casa.citta": "Tarquinia"})}
    # «Dove si trova la casa?» davanti al valore si legge male.
    assert fatti["casa.citta"]["label"] == "Citta"
    assert fatti["casa.citta"]["value"] == "Tarquinia"


def test_nothing_known_says_nothing():
    from life_profile.gaps import known_items

    assert known_items("casa", {}) == []
    assert known_items("area_che_non_esiste", {"x": "y"}) == []


def test_every_area_says_what_it_is_for():
    """
    Chiedere com'è fatta la vita di qualcuno senza dire che cosa te ne farai è
    chiedere fiducia senza darne motivo.
    """
    from life_profile.areas import all_areas

    for a in all_areas():
        assert a.purpose, f"{a.id} non dice a cosa serve"
        assert len(a.purpose) > 30


# ===========================================================================
# 3 · Il giro completo: aprire un buco, rispondere, vedere la percentuale
# ===========================================================================

@pytest.mark.asyncio
async def test_opening_a_specific_gap_asks_that_thing(monkeypatch):
    """
    Il click su una voce di «cosa manca» apre quella cosa lì — non la prima
    della lista, e non un'altra area.
    """
    from life_profile.setup import GuidedSetupService

    class FintaSessione:
        def __init__(self):
            self.meta = {}
            self.status = "active"

        def touch(self):
            pass

    class FintoRepo:
        def __init__(self):
            self.salvate = []

        async def save_session(self, sess):
            self.salvate.append(sess)

    sess = FintaSessione()
    repo = FintoRepo()
    servizio = GuidedSetupService(db=None)

    async def finto_load(user_id, create=False):
        return repo, sess, sess.meta

    async def finto_state(user_id):
        return {"ok": True, "meta": dict(sess.meta)}

    monkeypatch.setattr(servizio, "_load", finto_load)
    monkeypatch.setattr(servizio, "state", finto_state)

    await servizio.go_to_area("u1", "studio", ref="casa.utenze")
    # L'area la decide il riferimento, non chi ha scritto il link.
    assert sess.meta["guided_current_area"] == "casa"
    assert sess.meta["guided_open_ref"] == "casa.utenze"


@pytest.mark.asyncio
async def test_moving_to_an_area_forgets_a_previously_opened_gap(monkeypatch):
    from life_profile.setup import GuidedSetupService

    class FintaSessione:
        def __init__(self):
            self.meta = {"guided_open_ref": "casa.utenze"}
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

    async def finto_state(user_id):
        return {"ok": True}

    monkeypatch.setattr(servizio, "_load", finto_load)
    monkeypatch.setattr(servizio, "state", finto_state)

    await servizio.go_to_area("u1", "studio")
    assert "guided_open_ref" not in sess.meta
    assert sess.meta["guided_current_area"] == "studio"
