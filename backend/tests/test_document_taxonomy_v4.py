from pathlib import Path

import pytest

from documents.intelligence.taxonomy import refine_taxonomy
from documents.intelligence.analyzer import analyze_document


@pytest.mark.parametrize("text", [
    "Documento dimostrativo: costo mensile 15 euro.",
    "Il fornitore comunica le spese erogate.",
    "Il decorso della pratica è documentato nel riepilogo.",
])
def test_embedded_words_do_not_invent_categories(text):
    result = refine_taxonomy(type_key="generic", text=text)
    assert result["macro_category"] == "generic"


@pytest.mark.parametrize("text,macro,sub", [
    ("Biglietto per la mostra: ingresso alle ore 18.", "event", "exhibition_ticket"),
    ("Prenotazione hotel", "travel", "hotel_booking"),
    ("Visita specialistica in ambulatorio", "medical", "medical_appointment"),
    ("Appunti università", "education", "university_notes"),
])
def test_real_lexical_hints_still_work(text, macro, sub):
    result = refine_taxonomy(type_key="generic", text=text)
    assert (result["macro_category"], result["subcategory"]) == (macro, sub)


@pytest.mark.asyncio
async def test_uploaded_cost_fixture_has_no_invented_calendar_event():
    text = (Path(__file__).parent / "fixtures/ora_autonomy_contract_test.txt").read_text()
    result = await analyze_document({
        "id": "synthetic-contract", "user_id": "synthetic-user",
        "original_filename": "ora_autonomy_contract_test.txt", "extracted_text": text,
    }, force_local=True)
    assert result["analysis"]["macro_category"] != "event"
    assert not result["event_candidates"]
