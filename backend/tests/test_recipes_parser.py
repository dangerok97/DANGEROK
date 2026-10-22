"""Cucina MVP: source honesty, never invent amounts, stable dedup identity."""
from recipes.parser import canonical_url, preview, source_fingerprint
from recipes.service import RecipeWrite, RecipeService
import pytest


def test_structured_text_keeps_exact_ingredients_and_steps():
    data = preview("Pasta con zucchine\nIngredienti:\n- 250 g pasta\n- 2 zucchine\nProcedimento:\n1. Cuoci la pasta\n2. Salta le zucchine")
    assert data["quality"] == "structured_text"
    assert data["draft"]["title"] == "Pasta con zucchine"
    assert data["draft"]["ingredients"] == ["250 g pasta", "2 zucchine"]
    assert data["draft"]["steps"] == ["Cuoci la pasta", "Salta le zucchine"]


def test_link_only_never_claims_transcription():
    data = preview("https://www.instagram.com/reel/test/?utm_source=x&fbclid=abc")
    assert data["quality"] == "link_only"
    assert not data["draft"]["ingredients"]
    assert not data["draft"]["steps"]
    assert "analizzati" in data["warnings"][0]
    assert data["draft"]["source_url"] == "https://www.instagram.com/reel/test/"


def test_no_guessing_from_unstructured_caption():
    data = preview("La mia pasta buonissima!\nAggiungi un po' di farina e inforna.")
    assert data["draft"]["ingredients"] == []
    assert data["quality"] == "partial_text"


def test_only_https_and_no_internal_links():
    for source in ("javascript:alert(1)", "http://example.com/x", "https://localhost/x",
                   "https://user:pass@example.com/", "https://example.com:8443/"):
        with pytest.raises(ValueError):
            canonical_url(source)


def test_user_scoped_deterministic_duplicates():
    body = RecipeWrite(title="Pasta", source_url="https://example.com/a/?utm_source=b")
    again = RecipeWrite(title="Different", source_url="https://example.com/a/")
    assert RecipeService.record_id("user_1", body) == RecipeService.record_id("user_1", again)
    assert RecipeService.record_id("user_1", body) != RecipeService.record_id("user_2", body)


def test_link_requires_original_source():
    with pytest.raises(ValueError):
        RecipeWrite(title="Invented", source_url="", source_text="")
