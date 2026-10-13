# ORA — One brain, multiple channels (binding engineering contract)

Status: normative for ORA releases starting 2026-10-13.

## User experience

An ORA account owns its Memory, Situations, plans, calendar, connector
permissions, tools, notifications and audit history. WhatsApp is a signed
transport for that account. It must not create a separate chatbot, tool registry
or personal memory store.

When a user asks for the same server-side operation through the app or
WhatsApp, both channels must reach the **same AI Core** and the **same
ToolRegistry**, governed by the same ownership, authorization and truth guards.

This applies to every **future ORA capability**, not just the current examples.

## Automatic default: server-side skills

- Register a new skill **once** in ToolRegistry (CapabilitySpec).
- It immediately appears in the visible catalog read by the common AI Core,
  including sessions entered from WhatsApp. Do not add a per-skill WhatsApp
  keyword router or a second allowlist.
- Tool activation remains semantic/model-owned. Ownership and side-effect
  permissions remain enforced by the authoritative capability.
- The WhatsApp parity manifest is dynamically derived from that registry.
  The authenticated /whatsapp/status endpoint reports the shared catalog
  count, **not** an unverified claim of end-to-end provider readiness.
- Any new skill must have an executable handler, a bounded input schema and
  automated end-to-end tests showing the requested outcome.

## Automatic default: new interactive app features

A capability whose result requires a visual app screen can attach this trusted
tool observation (only after it actually succeeds):

    payload["ui_action"] = {
        "kind": "ora_screen",
        "path": "/vision-xray",
        "label": "Apri visione esplosa",
    }

The common AI Core turns that into a portable UI action. WhatsApp renders a
safe authenticated **ORA screen URL**, without a per-feature WhatsApp adapter.
New feature routes may use this contract without changing WhatsApp transport.

If a future tool produces an unrecognized UI action, the result must not
silently disappear on WhatsApp. The channel falls back to the already-owned
conversation in the authenticated ORA app. No untrusted arbitrary URL or login
ticket is propagated from a skill.

**Important:** a new feature that exists *only* as a frontend screen needs a
server-side skill/handoff contract before it can be invoked from WhatsApp by
natural language. Adding a React screen cannot magically turn WhatsApp into a
3D/camera runtime.

## Device and Meta boundaries

- WhatsApp may hand off Maps URLs and read photos, documents, voice notes and
  shared pins using signed Meta webhooks and the existing user-owned AI Core.
- In-app sensors, live camera, device GPS permission dialogs, interactive 3D
  models and other native UI remain in the app. WhatsApp gives a direct
  actionable handoff instead of claiming to execute unavailable hardware.
- Future proactive WhatsApp outreach requires explicit recipient opt-in,
  properly authorized template messaging outside Meta's conversation window,
  delivery/error tracking and a dedicated outbound flow. The current
  notifications_enabled setting is **false**: do not claim proactive WhatsApp
  outreach is live or create unsolicited sends.
- A handoff never means that a phone call, booking, payment or other
  consequential external action has been executed.
- Never place access tokens, phone numbers, personal data or app auth tickets
  in shared logs, public capability manifests or handoff URLs.

## Release checklist (must hold for each PR)

1. New backend skills register in common ToolRegistry, not a channel-specific
   clone; behavioral tests cover app and WhatsApp.
2. Features with app-only presentation emit a verified ora_screen UI action or
   a safe generic authenticated app handoff. Do not silently drop the result.
3. No external side effect is claimed without an authoritative observation.
4. WhatsApp identity resolves to the same account; reads/writes are
   owner-scoped. Permissions cannot be downgraded by changing the channel.
5. Device-only steps stay on the device and require appropriate consent.
6. GitHub CI runs the permanent parity gate and existing Cloud API,
   memory and navigation suites.
7. Production Railway deploy follows staging/cloud and is healthy.
   A green build does not substitute for real provider acceptance testing.

These checks are an enforceable **code-level and release-level contract**.
They do not pretend all future frontend features, external integrations or
WhatsApp message types are already fully implemented.
