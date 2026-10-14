"""Temporary branch-scoped installer. Removed before integration."""
from pathlib import Path
import hashlib
ROOT = Path(__file__).resolve().parents[1]
FENCES = {'backend/connectors/gmail/provider.py': '8d93dc3649a3ddb82dd8dd8989cfe7a774c0ca79', 'backend/connectors/gmail/service.py': '604d28bbeb224d60d6361cf977e1769afd8e9df4', 'backend/conversation_engine/ai_core/tools/registry.py': '9133d6b968feeab6597dd7e76273c01e0d065c16', 'backend/conversation_engine/ai_core/state.py': '22cc66b5d5963f68f6f5202e59d72ce79a73e023', 'backend/conversation_engine/ai_core/loop.py': 'aba5f521efcce951cb8aa9354cbb66023f6b0073'}
for path, expected in FENCES.items():
    raw = (ROOT / path).read_bytes()
    actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if actual != expected:
        raise RuntimeError('source_sha_conflict:' + path)


def patch(path, edits):
    file = ROOT / path
    original = file.read_text()
    for before, after in edits:
        expected_count = 2 if before.startswith('    async def body_of(self,') else 1
        if original.count(before) != expected_count:
            raise RuntimeError('anchor_conflict:' + path)
        original = original.replace(before, after)
    compile(original, path, 'exec')
    file.write_text(original)


patch('backend/connectors/gmail/provider.py', [
    ('from __future__ import annotations\n', 'from __future__ import annotations\n\nfrom connectors.gmail.body_text import message_text, bounded_limit\n'),
    ('    async def body_of(\n        self, *, access_token: str, message_id: str,\n    ) -> str: ...', '    async def body_of(\n        self, *, access_token: str, message_id: str, max_chars: int = MAX_BODY_CHARS,\n    ) -> str: ...'),
    ('    async def body_of(self, *, access_token: str, message_id: str) -> str:\n', '    async def body_of(self, *, access_token: str, message_id: str, max_chars: int = MAX_BODY_CHARS) -> str:\n'),
    ('        text = _plain_text(data.get("payload") or {})\n        if not text:\n            text = str(data.get("snippet") or "")\n        return text[:MAX_BODY_CHARS]',
     '        limit = bounded_limit(max_chars)\n        text = message_text(data.get("payload") or {}, max_chars=limit)\n        if not text:\n            text = str(data.get("snippet") or "")\n        return text[:limit]'),
    ('        return str(self.bodies.get(message_id) or "")[:MAX_BODY_CHARS]',
     '        return str(self.bodies.get(message_id) or "")[:bounded_limit(max_chars)]'),
])
patch('backend/connectors/gmail/service.py', [
    ('    async def body_for(self, *, user_id: str, instance_id: str, message_id: str) -> str:',
     '    async def body_for(self, *, user_id: str, instance_id: str, message_id: str, max_chars: int = 1200) -> str:'),
    ('        text = await self.provider.body_of(access_token=token, message_id=message_id)',
     '        from connectors.gmail.body_text import bounded_limit\n        limit = bounded_limit(max_chars)\n        kwargs = {"max_chars": limit} if limit != 1200 else {}\n        text = await self.provider.body_of(access_token=token, message_id=message_id, **kwargs)'),
])
patch('backend/conversation_engine/ai_core/tools/registry.py', [
    ('    def _register_defaults(self) -> None:\n',
     '    def _register_defaults(self) -> None:\n        from connected.source_read import register_source_reader\n        register_source_reader(self)\n'),
])
patch('backend/conversation_engine/ai_core/state.py', [
    ('    sess.meta["ai_core"] = state',
     '    from connected.source_read import redact_private_source_content\n    sess.meta["ai_core"] = redact_private_source_content(state)'),
])
patch('backend/conversation_engine/ai_core/loop.py', [
    ('    resume_client: bool = False,\n) -> CognitiveTurnResult:',
     '    resume_client: bool = False,\n    source_activation=None,\n) -> CognitiveTurnResult:'),
    ('    tools = ToolRegistry(db)\n    broker = ContextBroker(db)',
     '    tools = ToolRegistry(db)\n    source_instruction = ""\n    if source_activation is not None:\n        if user_message or resume_client:\n            raise ValueError("source_activation_is_not_a_user_turn")\n        await source_activation.validate(db, sess.user_id)\n        tools = source_activation.restrict_registry(tools)\n        from conversation_engine.ai_core.source_activation import SOURCE_INSTRUCTION\n        source_instruction = SOURCE_INSTRUCTION\n    broker = ContextBroker(db)'),
    ('    if not resume_client:\n        state_mod.append_turn',
     '    if not resume_client and source_activation is None:\n        state_mod.append_turn'),
    ('        _t = time.perf_counter()\n        raw = await _call_ai(',
     '        if source_activation is not None:\n            await source_activation.validate(db, sess.user_id)\n            decoded_payload = json.loads(payload)\n            decoded_payload["source_activation"] = source_activation.context\n            payload = json.dumps(decoded_payload, ensure_ascii=False)\n        _t = time.perf_counter()\n        raw = await _call_ai('),
    ('system=COGNITIVE_SYSTEM_PROMPT + followup_gate.instruction(),',
     'system=COGNITIVE_SYSTEM_PROMPT + followup_gate.instruction() + source_instruction,'),
    ('system=COGNITIVE_SYSTEM_PROMPT + followup_gate.instruction()\n                + "\\nPrevious output',
     'system=COGNITIVE_SYSTEM_PROMPT + followup_gate.instruction() + source_instruction\n                + "\\nPrevious output'),
    ('        last_decision = decision\n',
     '        if source_activation is not None and source_activation.implicit_mutations(decision):\n            observations.append(Observation(kind="system", name="source_effect_scope", status="blocked",\n                payload={"reason": "This source turn can use only the offered tools, not implicit memory, graph, Situation or act mutations. Choose a supported tool or explain the actual limitation."}).model_dump())\n            add_step(trace, event="SOURCE_IMPLICIT_MUTATION_BLOCKED")\n            continue\n        last_decision = decision\n'),
])
print('SOURCE_CORE_HOOKS_INSTALLED')
