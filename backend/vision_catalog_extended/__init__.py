"""Additive seed pack: 50 new families, separately from the original 25.

No model weights, photographs, external meshes or executable generated content.
The nine supported primitives express *groups* and are not measured real parts.
"""
from urllib.parse import urlsplit
from . import kitchen, home_desk, electronics_leisure

EXTENSION_VERSION = "everyday-50-v1"
EXPECTED_ADDITIONS = 50


def extended_recipes(recipe, part):
    def r(key, title, category, aliases, parts, *, note="", refs=()):
        entry = recipe(key, title, category, aliases, parts, note=note)
        references = []
        for label, url in refs:
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Invalid seed reference URL")
            references.append({"title": label, "url": url})
        # A source supports general construction/principles, not this specimen.
        entry["sources"] = references
        return entry
    entries = (kitchen.recipes(r, part) + home_desk.recipes(r, part)
               + electronics_leisure.recipes(r, part))
    keys = [entry["key"] for entry in entries]
    if len(entries) != EXPECTED_ADDITIONS or len(set(keys)) != len(keys):
        raise ValueError("The 50-family seed extension is incomplete or duplicated")
    return entries
