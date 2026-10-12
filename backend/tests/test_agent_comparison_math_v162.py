"""Conservative comparisons: no invented terms, source authority or periods."""
import pytest
from agent.comparison_math import complete_explicit_price_comparison as complete


SOURCE = (
    "Nota salvata in ORA, dati riferiti dall'utente e non confermati dal fornitore: "
    "il piano costa 15 euro mensili; 12 mesi costano 180 euro. "
    "La seconda opzione costa 120 euro anticipati per 12 mesi."
)


@pytest.mark.parametrize("second,expected", [(120, 60), (150, 30)])
def test_same_period_comparison_uses_derived_difference_and_source_limit(second, expected):
    source = SOURCE.replace("120 euro", f"{second} euro")
    draft = ("Il mensile costa 15 euro al mese, per un totale di 180 euro in 12 mesi. "
             f"L'altra formula costa {second} euro anticipati per 12 mesi.")
    actual = complete(draft, source, "Preparare una sintesi comparativa dei costi")
    assert f"{expected} euro" in actual
    assert actual.count(f"{expected} euro") == 1
    assert "Fonte: nota salvata in ORA" in actual
    assert "non confermati dal fornitore" in actual
    assert "condizioni contrattuali non specificate" in actual
    assert "nessuna penale" not in actual and "disdetta libera" not in actual


def test_existing_difference_is_not_duplicated():
    draft = "Confronto: 180 euro per 12 mesi contro 120 euro per 12 mesi, differenza 60 euro."
    assert complete(draft, SOURCE, "confronto").count("60 euro") == 1


@pytest.mark.parametrize("source,draft,purpose", [
    ("A costa 120 euro per 12 mesi.", "A costa 120 euro per 12 mesi.", "confronto"),
    ("A 120 euro per 12 mesi. B 60 euro per 6 mesi.",
     "A 120 euro per 12 mesi. B 60 euro per 6 mesi.", "confronto"),
    ("A 120 euro per 12 mesi. B 100 euro per 12 mesi. C 80 euro per 12 mesi.",
     "A 120 euro per 12 mesi. B 100 euro per 12 mesi. C 80 euro per 12 mesi.", "confronto"),
    (SOURCE, "Solo il mensile costa 180 euro per 12 mesi.", "confronto"),
    (SOURCE, "Il mensile 180 euro per 12 mesi, l'annuale 120 euro per 12 mesi.", "promemoria"),
])
def test_ambiguous_or_irrelevant_case_remains_unchanged(source, draft, purpose):
    assert complete(draft, source, purpose) == draft


def test_existing_note_attribution_is_preserved():
    draft = ("Secondo la nota dell'utente, il mensile costa 180 euro per 12 mesi "
             "e l'annuale costa 120 euro per 12 mesi.")
    actual = complete(draft, SOURCE, "comparare le formule")
    assert actual.startswith("Secondo la nota") and actual.count("nota") == 1


def test_do_not_expand_a_full_draft():
    draft = "A 180 euro per 12 mesi. B 120 euro per 12 mesi." + " !" * 2100
    assert complete(draft, SOURCE, "confronto") == draft


def test_monthly_unit_rate_is_not_treated_as_a_total():
    source = ("A costa 15 euro al mese, per un totale di 180 euro in 12 mesi. "
              "B costa 120 euro per 12 mesi.")
    draft = "A costa 15 euro al mese, 180 euro in 12 mesi. B 120 euro per 12 mesi."
    actual = complete(draft, source, "confrontare i costi")
    assert "60 euro" in actual and "165 euro" not in actual
