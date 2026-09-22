"""
V3.21.3d — ogni fatto sotto l'area a cui appartiene, detto in italiano.

    «DI CHI TI PRENDI CURA: NELLA GUARDIA DI FINANZA».

Misurato in app: un fatto di lavoro compariva sotto «Famiglia e relazioni», e
faceva anche salire la percentuale di quell'area. Il valore era vero; la cosa
che diceva, no — e una riga così non si può né verificare né correggere,
perché non è sbagliato il dato, è sbagliato il posto.

Le cause erano due, e nessuna delle due era la stringa «Guardia di Finanza»:
il nucleo del Minimum Life Context si lasciava soddisfare da prove prese da
qualunque area, e la presentazione non chiedeva mai se un fatto appartenesse
davvero all'area in cui stava per finire.
"""

from __future__ import annotations

import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ===========================================================================
# 1 · L'appartenenza, senza guardare le parole
# ===========================================================================

def test_a_fact_belongs_to_the_area_that_owns_its_reference():
    from life_profile.human import appartiene_all_area

    assert appartiene_all_area("lavoro.ruolo", "lavoro") is True
    assert appartiene_all_area("lavoro.ruolo", "famiglia") is False
    assert appartiene_all_area("famiglia.membri", "lavoro") is False
    # Mobilità possiede anche il dominio dell'auto.
    assert appartiene_all_area("auto.rata", "mobilita") is True
    assert appartiene_all_area("auto.rata", "assicurazioni") is False


def test_a_cross_cutting_reference_needs_a_written_relation():
    """
    Nel dubbio non si mostra: `mlc.*` non possiede niente da solo, e senza una
    relazione scritta non entra in nessuna area.
    """
    from life_profile.human import appartiene_all_area

    assert appartiene_all_area("mlc.life_places.home", "casa") is True
    assert appartiene_all_area("mlc.life_places.home", "lavoro") is False
    assert appartiene_all_area("mlc.responsibilities", "famiglia") is False
    assert appartiene_all_area("qualcosa.di.ignoto", "casa") is False


def test_work_facts_never_appear_under_family():
    from life_profile.gaps import known_items

    fatti = {
        "lavoro.ruolo": "nella Guardia di Finanza",
        "mlc.responsibilities": "nella Guardia di Finanza",
        "famiglia.situazione": ["partner"],
    }
    famiglia = " | ".join(k["value"] for k in known_items("famiglia", fatti))
    assert "Guardia di Finanza" not in famiglia
    assert "Hai un partner" in famiglia


def test_family_facts_never_appear_under_work():
    from life_profile.gaps import known_items

    fatti = {"famiglia.membri": "io e mia moglie", "lavoro.ruolo": "in comune"}
    lavoro = " | ".join(k["value"] for k in known_items("lavoro", fatti))
    assert "moglie" not in lavoro


def test_a_vehicle_fact_lands_in_mobility():
    from life_profile.gaps import known_items

    fatti = {"auto.rapporto": "proprieta", "auto.rata": 305}
    mobilita = [k["value"] for k in known_items("mobilita", fatti)]
    assert "L'auto è di tua proprietà" in mobilita
    assert "Paghi 305 € al mese per l'auto" in mobilita
    # E non finisce sotto le assicurazioni solo perché un'auto si assicura.
    assert known_items("assicurazioni", fatti) == []


def test_the_family_objective_is_not_satisfied_by_a_work_fact():
    """
    La causa vera: il nucleo del Minimum Life Context raccoglieva prove da
    tutta la vita — anche da `lavoro.ruolo` — e come obiettivo di Famiglia
    rispondeva alla domanda sbagliata.
    """
    from life_profile.areas import area
    from life_profile.objectives import objectives_for_area

    fondamento = objectives_for_area(area("famiglia"))[0]
    assert fondamento.ref == "mlc.responsibilities"
    assert "lavoro.ruolo" not in fondamento.satisfied_by
    assert "studio.active" not in fondamento.satisfied_by
    assert "famiglia.membri" in fondamento.satisfied_by


def test_an_echo_from_another_area_does_not_raise_the_score():
    """Un fatto di lavoro non rende più completa la famiglia."""
    from life_profile.areas import area
    from life_profile.completeness import area_completeness

    fatti = {
        "lavoro.ruolo": "nella Guardia di Finanza",
        "mlc.responsibilities": "nella Guardia di Finanza",
    }
    c = area_completeness(
        area("famiglia"), facts=fatti, provenance={},
        declined_refs=[], not_applicable_refs=[], inferred_refs=[],
    )
    assert c.known_count == 0
    assert "mlc.responsibilities" in [g["ref"] for g in c.open_objectives]


# ===========================================================================
# 2 · Le parole: etichette, valori, frasi
# ===========================================================================

def test_no_internal_label_ever_reaches_a_person():
    from life_profile.areas import all_areas
    from life_profile.human import ETICHETTE, come_si_chiama
    from life_profile.objectives import objectives_for_area

    vietate = {"citta", "city", "family_core", "relationship_status",
               "car_ownership", "study_year", "active", "tipo"}
    for a in all_areas():
        for o in objectives_for_area(a):
            nome = come_si_chiama(o.ref)
            if not nome:
                continue
            assert nome.lower() not in vietate, f"{o.ref} → {nome}"
    # E il registro è uno solo: se manca un nome, si aggiunge lì.
    assert "casa.citta" in ETICHETTE and ETICHETTE["casa.citta"] == "Città"


def test_raw_values_never_reach_a_person():
    from life_profile.human import come_si_dice_il_valore

    for muto in (None, "", "null", "unknown", "N/A", "other", "  "):
        assert come_si_dice_il_valore(muto) == "", muto
    assert come_si_dice_il_valore(True) == "Sì"
    assert come_si_dice_il_valore(False) == "No"
    assert come_si_dice_il_valore("true") == "Sì"
    assert come_si_dice_il_valore(["a", None, "b"]) == "a, b"


def test_an_internal_code_is_never_shown_as_a_fact():
    """«Polizza: doc_bd558d6789de» non è una cosa che qualcuno possa leggere."""
    from life_profile.gaps import known_items

    righe = known_items("assicurazioni", {"doc.polizza": "doc_bd558d6789de"})
    detti = [r["value"] for r in righe]
    assert detti == ["Hai caricato una polizza"]
    assert not any("doc_" in d for d in detti)


def test_facts_read_like_memory_not_like_a_form():
    from life_profile.gaps import known_items

    prove = {
        "lavoro": ({"lavoro.ruolo": "nella Guardia di Finanza"}, "Lavori nella Guardia di Finanza"),
        "mobilita": ({"mobilita.mezzi": ["auto"]}, "Hai un'auto"),
        "famiglia": ({"famiglia.situazione": ["partner"]}, "Hai un partner"),
        "casa": ({"casa.situazione": "affitto"}, "Vivi in affitto"),
    }
    for area_id, (fatti, atteso) in prove.items():
        detti = [k["value"] for k in known_items(area_id, fatti)]
        assert atteso in detti, (area_id, detti)


def test_zero_is_a_fact_and_says_so():
    from life_profile.gaps import known_items

    detti = [k["value"] for k in known_items("famiglia", {"famiglia.figli_numero": 0})]
    assert "Non hai figli" in detti
    assert "Figli: 0" not in detti


def test_every_shown_fact_says_where_it_is_written():
    """
    Si deve poter correggere *quella* cosa, là dov'è scritta — non creare una
    seconda copia accanto alla prima.
    """
    from life_profile.gaps import known_items

    for riga in known_items("casa", {"casa.situazione": "affitto", "casa.citta": "Roma"}):
        assert riga["source_ref"], riga
        assert riga["source_ref"] == riga["ref"]


# ===========================================================================
# 3 · Le dieci aree, tutte insieme
# ===========================================================================

def test_no_area_shows_a_fact_that_is_not_its_own():
    """
    L'audit vero: un profilo pieno, e nessuna area che mostri roba d'altri.
    """
    from life_profile.areas import all_areas
    from life_profile.gaps import known_items
    from life_profile.human import appartiene_all_area

    fatti = {
        "casa.situazione": "affitto", "casa.citta": "Roma", "casa.utenze": "inclusi",
        "lavoro.ruolo": "nella Guardia di Finanza", "lavoro.active": True,
        "studio.active": True, "studio.tipo": "universita",
        "mobilita.mezzi": ["auto"], "auto.rata": 305,
        "famiglia.situazione": ["partner"], "famiglia.membri": "io e mia moglie",
        "patrimonio.risparmi": "nessuno", "finanze.reddito": "2000_3000",
        "assicurazioni.tipo": ["auto"], "servizi.fornitori": "Enel",
        "salute.obiettivi": ["movimento"],
        "mlc.responsibilities": "nella Guardia di Finanza",
        "mlc.current_situation": "studio",
    }
    for a in all_areas():
        for riga in known_items(a.id, fatti):
            assert appartiene_all_area(riga["ref"], a.id), (a.id, riga)


def test_a_complete_area_still_opens_when_it_is_chosen():
    """
    Cliccando «Lavoro», che non aveva più niente da chiedere, il pannello
    mostrava Studio: la scelta veniva scartata in silenzio.
    """
    from life_profile.setup import GuidedSetupService

    servizio = GuidedSetupService(db=None)
    scelto = servizio._pick_area(
        current="lavoro",
        facts={},
        answered=[],
        declined=[],
        not_applicable=[],
        skipped=[],
        areas=[{"area_id": "lavoro", "open_objectives": []}],
        scelta_esplicita=True,
    )
    assert scelto == "lavoro"
