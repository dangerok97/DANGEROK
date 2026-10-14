"""Temporary exact-blob integration helper; removed before review/merge."""
from pathlib import Path
import hashlib
p = Path(__file__).resolve().parents[1] / 'backend/conversation_engine/ai_core/loop.py'
b = p.read_bytes()
assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest() == '6477976cfca3185ef1eaa7a774c1d7ea8056aea2', 'loop_blob_changed'
s = b.decode()
old = '        _t = time.perf_counter()\n        raw = await _call_ai('
new = '''        from conversation_engine.ai_core.instruction_contract import (
            instruction_surface, input_surface, compact_source_enabled,
        )
        source_turn = source_activation is not None
        payload = input_surface(payload, source_turn=source_turn)
        cognitive_system = instruction_surface(
            legacy=COGNITIVE_SYSTEM_PROMPT, source_turn=source_turn,
            source_instruction=source_instruction,
            followup_instruction=followup_gate.instruction(),
        )
        add_step(trace, event="COGNITIVE_CONTRACT",
                 compact=compact_source_enabled(source_turn),
                 system_chars=len(cognitive_system), payload_chars=len(payload))
        _t = time.perf_counter()
        raw = await _call_ai('''
assert s.count(old) == 1, 'call_anchor_changed'
s = s.replace(old, new)
old = 'system=COGNITIVE_SYSTEM_PROMPT + followup_gate.instruction() + source_instruction'
assert s.count(old) == 2, 'system_anchor_changed'
s = s.replace(old, 'system=cognitive_system')
compile(s, str(p), 'exec')
p.write_text(s)
print('CORE_CONTRACT_HOOK_INSTALLED')
