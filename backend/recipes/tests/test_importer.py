"""Recipes from links, captions and photos: read what was published, invent nothing."""
import json

import pytest

from recipes import importer

PAGE = """<html><head>
<meta property="og:title" content="Carbonara">
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[
 {"@type":"WebPage","name":"x"},
 {"@type":["Recipe"],"name":"Spaghetti alla Carbonara","recipeYield":"4 persone",
  "totalTime":"PT25M","image":[{"url":"https://img.example.it/carbonara.jpg"}],
  "recipeIngredient":["320 g spaghetti","150 g guanciale","6 tuorli","50 g pecorino"],
  "recipeInstructions":[{"@type":"HowToSection","itemListElement":[
     {"@type":"HowToStep","text":"Taglia il guanciale a listarelle."},
     {"@type":"HowToStep","text":"Cuoci la pasta in acqua salata."}]},
   {"@type":"HowToStep","text":"Manteca fuori dal fuoco con i tuorli e il pecorino."}]}]}
</script></head><body>...</body></html>"""


def test_structured_recipe_is_read_as_published():
    got = importer.from_structured(PAGE)
    assert got["title"] == "Spaghetti alla Carbonara"
    assert got["ingredients"][0] == "320 g spaghetti" and len(got["ingredients"]) == 4
    assert got["steps"] == ["Taglia il guanciale a listarelle.", "Cuoci la pasta in acqua salata.",
                            "Manteca fuori dal fuoco con i tuorli e il pecorino."]
    assert got["servings"] == 4 and got["total_minutes"] == 25
    assert got["image_url"] == "https://img.example.it/carbonara.jpg"


def test_numbers_not_in_the_source_are_removed():
    source = "Pasta al pomodoro: 200 g di pasta, passata, basilico. Cuoci e condisci."
    draft, warnings = importer.grounded({
        "ingredients": ["200 g pasta", "300 ml passata", "basilico"],
        "steps": ["Cuoci la pasta."], "servings": 2, "total_minutes": 15, "tags": ["Primo"],
    }, source)
    assert draft["ingredients"] == ["200 g pasta", "passata", "basilico"]
    assert draft["servings"] is None and draft["total_minutes"] is None
    assert warnings and draft["tags"] == ["primo"]


@pytest.mark.asyncio
async def test_food_site_link_needs_no_ai(monkeypatch):
    async def fetch(url, **kw):
        return url, PAGE

    async def no_ai(text):
        raise AssertionError("structured pages are not sent to the model")

    monkeypatch.setattr(importer, "_fetch", fetch)
    monkeypatch.setattr(importer, "structure_with_ai", no_ai)
    out = await importer.from_link("https://www.example-ricette.it/carbonara?utm_source=x")
    assert out["quality"] == "structured_page" and out["warnings"] == []
    assert out["draft"]["source_url"] == "https://www.example-ricette.it/carbonara"
    assert len(out["draft"]["ingredients"]) == 4


@pytest.mark.asyncio
async def test_tiktok_caption_becomes_a_checked_draft(monkeypatch):
    caption = "Pancake proteici! 2 uova, 100 g farina d'avena, 1 banana. Frulla tutto e cuoci 2 minuti per lato"

    async def fetch(url, **kw):
        assert url.startswith("https://www.tiktok.com/oembed?url=")
        return url, json.dumps({"title": caption, "author_name": "cuoca",
                                "thumbnail_url": "https://p16.tiktokcdn.com/x.jpg"})

    async def ai(text):
        assert caption in text
        return {"is_recipe": True, "title": "Pancake proteici", "servings": None, "total_minutes": None,
                "ingredients": ["2 uova", "100 g farina d'avena", "1 banana", "30 g miele"],
                "steps": ["Frulla tutto.", "Cuoci 2 minuti per lato."], "tags": ["colazione"]}

    monkeypatch.setattr(importer, "_fetch", fetch)
    monkeypatch.setattr(importer, "structure_with_ai", ai)
    out = await importer.from_link("https://www.tiktok.com/@cuoca/video/123")
    assert out["quality"] == "ai_from_caption" and out["source_label"] == "TikTok"
    assert out["draft"]["ingredients"] == ["2 uova", "100 g farina d'avena", "1 banana", "miele"]
    assert out["draft"]["image_url"] == "https://p16.tiktokcdn.com/x.jpg"
    assert any("controllala" in w for w in out["warnings"])


@pytest.mark.asyncio
async def test_instagram_without_access_asks_for_the_caption(monkeypatch):
    async def fetch(url, **kw):
        return None

    monkeypatch.setattr(importer, "_fetch", fetch)
    out = await importer.from_link("https://www.instagram.com/reel/ABC/")
    assert out["quality"] == "link_only"
    assert "didascalia" in out["warnings"][0]


@pytest.mark.asyncio
async def test_unstructured_text_is_ordered_by_the_model(monkeypatch):
    async def ai(text):
        return {"is_recipe": True, "title": "Frittata", "servings": 2, "total_minutes": None,
                "ingredients": ["4 uova", "sale"], "steps": ["Sbatti le uova.", "Cuoci in padella."], "tags": []}

    monkeypatch.setattr(importer, "structure_with_ai", ai)
    out = await importer.from_text("frittata per 2: sbatti 4 uova con un pizzico di sale e cuoci in padella")
    assert out["quality"] == "ai_from_text"
    assert out["draft"]["ingredients"] == ["4 uova", "sale"] and out["draft"]["servings"] == 2


def test_import_rate_is_bounded():
    importer._recent.clear()
    assert all(importer.allow("u", now=0) for _ in range(importer.MAX_IMPORTS_PER_HOUR))
    assert not importer.allow("u", now=1)
    assert importer.allow("u", now=4000)


@pytest.mark.asyncio
async def test_private_addresses_are_never_fetched():
    assert await importer._fetch("https://127.0.0.1/x") is None
    assert await importer._fetch("http://example.com/") is None


@pytest.mark.asyncio
async def test_conversation_can_save_read_and_shop(monkeypatch):
    from mongomock_motor import AsyncMongoMockClient
    from recipes import caps

    db = AsyncMongoMockClient().recipes_caps
    importer._recent.clear()

    async def fetch(url, **kw):
        return url, PAGE

    monkeypatch.setattr(importer, "_fetch", fetch)
    rt = {"user_id": "u1", "db": db}
    saved = await caps.save_recipe({"source": "https://www.example-ricette.it/carbonara"}, rt)
    assert saved.payload["status"] == "saved" and saved.payload["ingredients"] == 4
    again = await caps.save_recipe({"source": "https://www.example-ricette.it/carbonara"}, rt)
    assert again.payload["status"] == "already_saved"
    found = await caps.read_recipes({"query": "guanciale"}, rt)
    assert found.payload["recipes"][0]["title"] == "Spaghetti alla Carbonara"
    shop = await caps.add_to_shopping_list({"items": ["latte", "uova", "latte"]}, rt)
    assert shop.payload["added"] == ["latte", "uova"]
    shop = await caps.add_to_shopping_list({"items": ["uova"]}, rt)
    assert shop.payload["added"] == [] and shop.payload["already_there"] == ["uova"]
    other = await caps.read_recipes({}, {"user_id": "u2", "db": db})
    assert other.payload["status"] == "NO_RECIPES"
