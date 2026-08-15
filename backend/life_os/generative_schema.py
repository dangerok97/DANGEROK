"""Declarative GenerativeObject UI schema — primitives only, no domain cognition."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

# UI primitives the renderer understands. NOT domain behaviors.
ALLOWED_BLOCK_TYPES: frozenset = frozenset(
    {
        "text",
        "heading",
        "section",
        "callout",
        "list",
        "ordered_list",
        "table",
        "card",
        "card_deck",
        "question",
        "answer_reveal",
        "choice",
        "progress",
        "timeline",
        "task",
        "task_group",
        "key_value",
        "source",
        "relation_graph",
        "formula",
        "code",
        "divider",
    }
)

ALLOWED_INTERACTIONS: frozenset = frozenset(
    {
        "reveal",
        "select",
        "next_previous",
        "complete",
        "check",
        "submit_answer",
    }
)

# Dangerous / executable content keys — reject if present anywhere.
_BANNED_KEYS: frozenset = frozenset(
    {
        "script",
        "javascript",
        "onerror",
        "onclick",
        "onload",
        "__html",
        "dangerouslySetInnerHTML",
        "eval",
        "Function",
        "iframe",
        "wasm",
    }
)

MAX_BLOCKS = 80
MAX_NESTING = 6
MAX_CONTENT_CHARS = 48_000
MAX_STRING = 4_000
MAX_CARD_ITEMS = 40
MAX_LIST_ITEMS = 60
MAX_GRAPH_NODES = 40
MAX_GRAPH_EDGES = 80


class GenerativeValidationError(Exception):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}")


def validate_generative_spec(
    spec: Dict[str, Any],
    *,
    require_content: bool = True,
) -> Dict[str, Any]:
    """
    Validate AI-authored declarative object. Returns normalized dict or raises.
    Cognition-free: does not interpret object_kind.
    """
    if not isinstance(spec, dict):
        raise GenerativeValidationError("NOT_OBJECT", "spec must be object")

    title = str(spec.get("title") or "").strip()[:200]
    if not title:
        raise GenerativeValidationError("MISSING_TITLE")

    purpose = str(spec.get("purpose") or "").strip()[:400]
    object_kind = str(spec.get("object_kind") or "workspace_object").strip()[:80]
    # Label only — never used for branching
    if any(ch in object_kind for ch in ("{", "}", "<", ">", ";")):
        raise GenerativeValidationError("BAD_OBJECT_KIND")

    content = spec.get("content")
    if require_content and not isinstance(content, dict):
        raise GenerativeValidationError("MISSING_CONTENT")
    content = content if isinstance(content, dict) else {}

    raw = _jsonish(content)
    if len(raw) > MAX_CONTENT_CHARS:
        raise GenerativeValidationError("CONTENT_TOO_LARGE", str(len(raw)))

    _reject_banned(content)

    blocks = content.get("blocks")
    if blocks is None:
        # Allow AI to send a single root block as content itself
        if content.get("type") in ALLOWED_BLOCK_TYPES:
            blocks = [content]
            content = {"blocks": blocks}
        else:
            raise GenerativeValidationError("MISSING_BLOCKS", "content.blocks required")
    if not isinstance(blocks, list) or not blocks:
        raise GenerativeValidationError("EMPTY_BLOCKS")
    if len(blocks) > MAX_BLOCKS:
        raise GenerativeValidationError("TOO_MANY_BLOCKS", str(len(blocks)))

    normalized_blocks: List[Dict[str, Any]] = []
    for i, b in enumerate(blocks):
        normalized_blocks.append(_validate_block(b, depth=0, path=f"blocks[{i}]"))

    interaction = spec.get("interaction_schema")
    if interaction is not None:
        if not isinstance(interaction, dict):
            raise GenerativeValidationError("BAD_INTERACTION_SCHEMA")
        _reject_banned(interaction)
        for k, v in list(interaction.items())[:20]:
            if str(k) not in ALLOWED_INTERACTIONS and str(k) not in (
                "default",
                "on_complete",
                "tracking",
            ):
                # Unknown interaction keys soft-drop
                interaction.pop(k, None)

    hints = spec.get("presentation_hints")
    if hints is not None and not isinstance(hints, dict):
        raise GenerativeValidationError("BAD_PRESENTATION_HINTS")
    if isinstance(hints, dict):
        _reject_banned(hints)
        hints = {str(k)[:40]: _clip(v) for k, v in list(hints.items())[:12]}

    content_schema = spec.get("content_schema")
    if content_schema is not None and not isinstance(content_schema, dict):
        raise GenerativeValidationError("BAD_CONTENT_SCHEMA")

    return {
        "title": title,
        "purpose": purpose,
        "object_kind": object_kind or "workspace_object",
        "content_schema": content_schema if isinstance(content_schema, dict) else {},
        "content": {"blocks": normalized_blocks, "schema_version": 1},
        "interaction_schema": interaction if isinstance(interaction, dict) else {},
        "presentation_hints": hints if isinstance(hints, dict) else {},
        "generation_reason": str(spec.get("generation_reason") or "")[:400],
    }


def validate_content_patch(content: Dict[str, Any]) -> Dict[str, Any]:
    return validate_generative_spec(
        {
            "title": "patch",
            "purpose": "patch",
            "object_kind": "patch",
            "content": content,
        },
        require_content=True,
    )["content"]


def normalize_reveal_card_item(
    it: Any, *, require_back: bool = False
) -> Dict[str, Any]:
    """Canonical revealable-card item: {front, back, revealable, meta}.

    Compatibility aliases (read once, small set):
      front ← front | question | prompt | title | text
      back  ← back | answer | reveal | hidden | body | detail | text(if unused)
    """
    if not isinstance(it, dict):
        return {"front": "", "back": "", "revealable": False, "meta": {}}

    front = str(
        it.get("front") or it.get("question") or it.get("prompt") or ""
    ).strip()
    back = str(
        it.get("back")
        or it.get("answer")
        or it.get("reveal")
        or it.get("hidden")
        or ""
    ).strip()
    title = str(it.get("title") or it.get("label") or "").strip()
    text = str(it.get("text") or it.get("body") or it.get("detail") or "").strip()

    if not front:
        if title:
            front, title = title, ""
        elif text:
            front, text = text, ""

    if not back:
        if text and text != front:
            back = text
        elif title and title != front:
            back = title

    # require_back is enforced by callers (card_deck); here we only shape
    _ = require_back
    out: Dict[str, Any] = {
        "front": front[:MAX_STRING],
        "back": back[:MAX_STRING],
        "revealable": bool(back),
        "meta": _safe_meta(it.get("meta")),
    }
    if title and title != front:
        out["label"] = title[:200]
    return out


def normalize_content_blocks_for_display(content: Any) -> Dict[str, Any]:
    """Non-destructive display normalize for API/FE (compat with older shapes)."""
    if not isinstance(content, dict):
        return {"blocks": [], "schema_version": 1}
    blocks_in = content.get("blocks") or []
    if not isinstance(blocks_in, list):
        return {"blocks": [], "schema_version": 1}
    blocks_out: List[Dict[str, Any]] = []
    for b in blocks_in:
        if not isinstance(b, dict):
            continue
        btype = str(b.get("type") or "")
        if btype == "card":
            card = normalize_reveal_card_item(b, require_back=False)
            if not card["front"]:
                continue  # skip unusable
            row = {
                "type": "card",
                "front": card["front"],
                "back": card["back"],
                "revealable": card["revealable"],
            }
            if b.get("id"):
                row["id"] = b["id"]
            if card.get("label"):
                row["label"] = card["label"]
            blocks_out.append(row)
        elif btype == "card_deck":
            items = []
            for it in b.get("items") or []:
                card = normalize_reveal_card_item(it, require_back=False)
                if not card["front"]:
                    continue
                # Display-time: keep item even if back empty (static + fallback)
                items.append(card)
            if not items:
                continue
            row = {"type": "card_deck", "items": items}
            if b.get("id"):
                row["id"] = b["id"]
            if b.get("purpose"):
                row["purpose"] = str(b.get("purpose"))[:200]
            blocks_out.append(row)
        else:
            blocks_out.append(b)
    return {
        "blocks": blocks_out,
        "schema_version": content.get("schema_version") or 1,
    }


def _validate_block(block: Any, *, depth: int, path: str) -> Dict[str, Any]:
    if depth > MAX_NESTING:
        raise GenerativeValidationError("NESTING_TOO_DEEP", path)
    if not isinstance(block, dict):
        raise GenerativeValidationError("BAD_BLOCK", path)
    _reject_banned(block)
    btype = str(block.get("type") or "").strip()
    if btype not in ALLOWED_BLOCK_TYPES:
        raise GenerativeValidationError("UNSUPPORTED_PRIMITIVE", f"{path}:{btype}")

    out: Dict[str, Any] = {"type": btype}
    if block.get("id"):
        out["id"] = str(block["id"])[:64]
    if block.get("purpose"):
        out["purpose"] = str(block["purpose"])[:200]

    # Common text fields
    for key in ("text", "heading", "title", "body", "label", "caption", "formula"):
        if key in block and block[key] is not None:
            out[key] = str(block[key])[:MAX_STRING]

    if btype == "section":
        kids = block.get("children") or block.get("blocks") or []
        if not isinstance(kids, list):
            raise GenerativeValidationError("BAD_SECTION", path)
        out["children"] = [
            _validate_block(c, depth=depth + 1, path=f"{path}.children[{i}]")
            for i, c in enumerate(kids[:MAX_BLOCKS])
        ]
    elif btype in ("list", "ordered_list"):
        items = block.get("items") or []
        if not isinstance(items, list):
            raise GenerativeValidationError("BAD_LIST", path)
        out["items"] = [_clip(x) for x in items[:MAX_LIST_ITEMS]]
    elif btype == "card_deck":
        items = block.get("items") or []
        if not isinstance(items, list) or not items:
            raise GenerativeValidationError("BAD_CARD_DECK", path)
        cards = []
        for i, it in enumerate(items[:MAX_CARD_ITEMS]):
            if not isinstance(it, dict):
                raise GenerativeValidationError("BAD_CARD", f"{path}[{i}]")
            card = normalize_reveal_card_item(it, require_back=True)
            if not card["front"]:
                raise GenerativeValidationError(
                    "BAD_CARD", f"{path}[{i}]: missing front after normalize"
                )
            if not card["back"]:
                raise GenerativeValidationError(
                    "BAD_CARD", f"{path}[{i}]: missing back/reveal content"
                )
            cards.append(card)
        out["items"] = cards
        if block.get("purpose"):
            out["purpose"] = str(block["purpose"])[:200]
    elif btype == "card":
        # Single revealable/static card — normalize aliases (title/text/…)
        card = normalize_reveal_card_item(block, require_back=False)
        if not card["front"]:
            raise GenerativeValidationError("BAD_CARD", f"{path}: missing front")
        out["front"] = card["front"]
        out["back"] = card["back"]
        out["revealable"] = card["revealable"]
        # Drop misleading empty duplicates; keep optional label
        out.pop("title", None)
        out.pop("text", None)
        out.pop("body", None)
        if card.get("label"):
            out["label"] = card["label"]
    elif btype == "question":
        out["prompt"] = str(block.get("prompt") or block.get("text") or "")[:MAX_STRING]
        out["answer"] = str(block.get("answer") or "")[:MAX_STRING]
        if isinstance(block.get("options"), list):
            out["options"] = [str(o)[:400] for o in block["options"][:12]]
        out["interaction"] = _safe_interaction(block.get("interaction") or "submit_answer")
    elif btype == "answer_reveal":
        out["prompt"] = str(block.get("prompt") or "")[:MAX_STRING]
        out["answer"] = str(block.get("answer") or "")[:MAX_STRING]
        out["interaction"] = "reveal"
    elif btype == "choice":
        out["prompt"] = str(block.get("prompt") or "")[:MAX_STRING]
        opts = block.get("options") or []
        if not isinstance(opts, list) or len(opts) < 2:
            raise GenerativeValidationError("BAD_CHOICE", path)
        out["options"] = [str(o)[:400] for o in opts[:12]]
        out["interaction"] = "select"
    elif btype == "timeline":
        items = block.get("items") or []
        if not isinstance(items, list):
            raise GenerativeValidationError("BAD_TIMELINE", path)
        out["items"] = []
        for it in items[:40]:
            if isinstance(it, dict):
                out["items"].append(
                    {
                        "label": str(it.get("label") or it.get("title") or "")[:200],
                        "detail": str(it.get("detail") or it.get("body") or "")[:800],
                        "when": str(it.get("when") or it.get("date") or "")[:40],
                    }
                )
    elif btype == "task":
        out["label"] = str(block.get("label") or block.get("text") or "")[:200]
        out["done"] = bool(block.get("done"))
        out["interaction"] = _safe_interaction(block.get("interaction") or "check")
    elif btype == "task_group":
        items = block.get("items") or []
        if not isinstance(items, list):
            raise GenerativeValidationError("BAD_TASK_GROUP", path)
        out["items"] = []
        for it in items[:MAX_LIST_ITEMS]:
            if isinstance(it, dict):
                out["items"].append(
                    {
                        "label": str(it.get("label") or it.get("text") or "")[:200],
                        "done": bool(it.get("done")),
                    }
                )
            else:
                out["items"].append({"label": str(it)[:200], "done": False})
        out["interaction"] = "check"
    elif btype == "key_value":
        pairs = block.get("pairs") or block.get("items") or []
        out["pairs"] = []
        if isinstance(pairs, list):
            for it in pairs[:40]:
                if isinstance(it, dict):
                    out["pairs"].append(
                        {
                            "key": str(it.get("key") or it.get("label") or "")[:120],
                            "value": str(it.get("value") or "")[:800],
                        }
                    )
    elif btype == "table":
        headers = block.get("headers") or []
        rows = block.get("rows") or []
        out["headers"] = [str(h)[:120] for h in (headers if isinstance(headers, list) else [])[:12]]
        out["rows"] = []
        if isinstance(rows, list):
            for row in rows[:40]:
                if isinstance(row, list):
                    out["rows"].append([str(c)[:400] for c in row[:12]])
    elif btype == "relation_graph":
        nodes = block.get("nodes") or []
        edges = block.get("edges") or []
        if not isinstance(nodes, list) or not nodes:
            raise GenerativeValidationError("BAD_GRAPH", path)
        out["nodes"] = []
        for n in nodes[:MAX_GRAPH_NODES]:
            if isinstance(n, dict):
                out["nodes"].append(
                    {
                        "id": str(n.get("id") or "")[:64] or f"n{len(out['nodes'])}",
                        "label": str(n.get("label") or "")[:200],
                        "description": str(n.get("description") or "")[:400],
                    }
                )
        out["edges"] = []
        if isinstance(edges, list):
            for e in edges[:MAX_GRAPH_EDGES]:
                if isinstance(e, dict):
                    out["edges"].append(
                        {
                            "source": str(e.get("source") or "")[:64],
                            "target": str(e.get("target") or "")[:64],
                            "relation": str(e.get("relation") or "")[:120],
                        }
                    )
    elif btype == "source":
        out["label"] = str(block.get("label") or block.get("title") or "")[:200]
        url = str(block.get("url") or "")[:500]
        if url and not (url.startswith("http://") or url.startswith("https://")):
            raise GenerativeValidationError("BAD_URL", path)
        out["url"] = url or None
    elif btype == "progress":
        try:
            out["value"] = float(block.get("value") or 0)
        except Exception:
            out["value"] = 0.0
        out["label"] = str(block.get("label") or "")[:200]
    elif btype == "callout":
        out["text"] = str(block.get("text") or block.get("body") or "")[:MAX_STRING]
        out["tone"] = str(block.get("tone") or "neutral")[:40]
    elif btype == "code":
        out["text"] = str(block.get("text") or block.get("code") or "")[:MAX_STRING]
        out["language"] = str(block.get("language") or "")[:40]
    elif btype == "divider":
        pass

    return out


def _safe_interaction(raw: Any) -> str:
    s = str(raw or "").strip()
    return s if s in ALLOWED_INTERACTIONS else "reveal"


def _safe_meta(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in list(raw.items())[:8]:
        out[str(k)[:40]] = _clip(v)
    return out


def _clip(v: Any) -> Any:
    if isinstance(v, str):
        return v[:MAX_STRING]
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    if isinstance(v, list):
        return [_clip(x) for x in v[:40]]
    if isinstance(v, dict):
        return {str(k)[:40]: _clip(val) for k, val in list(v.items())[:20]}
    return str(v)[:200]


def _reject_banned(obj: Any) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in _BANNED_KEYS or any(b in lk for b in ("onmouse", "onkey", "javascript:")):
                raise GenerativeValidationError("EXECUTABLE_CONTENT", str(k))
            if isinstance(v, str) and (
                "<script" in v.lower()
                or "javascript:" in v.lower()
                or "data:text/html" in v.lower()
            ):
                raise GenerativeValidationError("EXECUTABLE_CONTENT", "string")
            _reject_banned(v)
    elif isinstance(obj, list):
        for x in obj[:MAX_BLOCKS]:
            _reject_banned(x)


def _jsonish(obj: Any) -> str:
    import json

    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)
