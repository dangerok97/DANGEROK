"""ORA channel-parity contract.

Every conversational channel receives its skills from the SAME ToolRegistry.
No WhatsApp-specific skill allowlist, command router or shadow capability list.

The manifest is generated from the currently registered AI Core tools, not
maintained separately. It says what cognition can discover, NOT that every
provider is configured or that a device-only tool can act within WhatsApp.
"""
from __future__ import annotations

from typing import Any


CONTRACT_VERSION = 1


def shared_ai_capability_manifest(registry: Any = None) -> dict:
    """Audit the exact visible AI Core catalog used by app and WhatsApp."""
    if registry is None:
        from conversation_engine.ai_core.tools.registry import ToolRegistry

        registry = ToolRegistry()
    visible = registry.list_public()
    capabilities: list[dict] = []
    seen: set[str] = set()

    for item in visible:
        capability = str(item.get("capability") or "").strip()
        if not capability or capability in seen:
            raise ValueError("duplicate_or_empty_shared_capability")
        spec = registry.get(capability)
        if spec is None:
            raise ValueError("shared_capability_missing_spec")
        if getattr(spec, "handler", None) is None:
            raise ValueError("shared_capability_missing_handler")
        if getattr(spec, "availability", "") == "hidden":
            raise ValueError("hidden_capability_exposed")
        seen.add(capability)
        capabilities.append({
            "capability": capability,
            "availability": str(item.get("availability") or "available"),
            "side_effect": str(item.get("side_effect") or "READ_ONLY"),
            "surface": "shared_ai_core",
        })

    # Ordering is stable for diffing across releases, even when registry
    # registration order changes. No user data, tokens or provider secrets.
    capabilities.sort(key=lambda item: item["capability"])
    return {
        "version": CONTRACT_VERSION,
        "source": "ai_core_tool_registry",
        "shared_ai_core": True,
        "capability_count": len(capabilities),
        "capabilities": capabilities,
        # Device-only capabilities are handled by the generic, authenticated
        # app handoff. This does not mean WhatsApp has device permissions.
        "device_handoff_supported": True,
        "automatic_future_skill_discovery": True,
    }


def public_whatsapp_parity_status() -> dict:
    """Small safe status projection, not an unverified E2E success claim."""
    manifest = shared_ai_capability_manifest()
    return {
        "shared_ai_core": manifest["shared_ai_core"],
        "shared_capability_count": manifest["capability_count"],
        "capability_contract_version": manifest["version"],
        "device_handoff_supported": manifest["device_handoff_supported"],
    }
