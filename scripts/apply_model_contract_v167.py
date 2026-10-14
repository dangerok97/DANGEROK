"""Temporary exact-blob integration helper, removed before review."""
from pathlib import Path
import hashlib
root = Path(__file__).resolve().parents[1]
expected = {
    'backend/llm/manager.py': '55499677e3bf841dfb05c33afd12ec2999a69afc',
    'backend/conversation_engine/ai_core/source_activation.py': '52db6a0b051c18043c97b4f9e06b1e8aa0e67c2e',
}
for path, sha in expected.items():
    raw = (root/path).read_bytes()
    assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest() == sha, path
p = root/'backend/llm/manager.py'
s = p.read_text()
a = '        return order\n\n    async def _available'
b = '        from llm.model_contract import eligible_names\n        return eligible_names(order, self._providers)\n\n    async def _available'
assert s.count(a) == 1
s = s.replace(a,b); compile(s, str(p), 'exec'); p.write_text(s)
p = root/'backend/conversation_engine/ai_core/source_activation.py'
s = p.read_text()
a = '''    result = await run_cognitive_loop(sess=sess, user_message='', db=db,
        decision_fn=decision_fn, max_steps=min(max(1, max_steps), 8), source_activation=activation)'''
b = '''    import os
    from llm.model_contract import scoped_model_contract
    # Infrastructure configuration, never sourced from a message or AI output.
    # No eligible model means no silent downgrade; the caller owns recovery.
    with scoped_model_contract(os.environ.get('ORA_SOURCE_MODEL_CONTRACT')):
        result = await run_cognitive_loop(sess=sess, user_message='', db=db,
            decision_fn=decision_fn, max_steps=min(max(1, max_steps), 8), source_activation=activation)'''
assert s.count(a) == 1
s = s.replace(a,b); compile(s, str(p), 'exec'); p.write_text(s)
print('MODEL_CONTRACT_HOOKS_INSTALLED')
