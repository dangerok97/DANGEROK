"""Test-only observation of source Core choices; no prompt or verdict changes.

Only structural decision fields are logged, never model chain-of-thought or
credentials. The original four synthetic fixtures, authority and oracle remain
unchanged. Diagnostic runs are not additional independent acceptance cases.
"""
from __future__ import annotations
import argparse
import asyncio
from collections import Counter
import json
from pathlib import Path
from unittest.mock import patch


def structural_decision(text):
    try:
        raw = str(text).strip()
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[-1].rsplit('```', 1)[0]
        data = json.loads(raw)
        call = data.get('tool_call') or {}
        situation = data.get('situation_update') or {}
        return {
            'mode': data.get('response_mode'),
            'tool': call.get('capability') or call.get('name'),
            'has_memory_candidates': bool(data.get('memory_candidates')),
            'has_graph_updates': bool(data.get('context_graph_updates')),
            'situation_operation': situation.get('operation') if isinstance(situation, dict) else 'invalid',
            'has_question': bool(data.get('question')),
        }
    except (ValueError, TypeError, AttributeError):
        return {'invalid_json': True}


async def main(output):
    from llm.manager import ProviderManager
    from conversation_engine.ai_core import source_activation
    from scripts import source_core_live_v166 as driver
    original_chat = ProviderManager.chat
    original_turn = source_activation.run_source_turn
    decisions, turns = [], []

    async def observe_chat(manager, **kwargs):
        result = await original_chat(manager, **kwargs)
        frame = {}
        try:
            payload = json.loads(kwargs.get('user') or '{}')
            frame = payload.get('source_activation') or {}
        except (TypeError, ValueError):
            pass
        decisions.append({
            'source_ref': frame.get('source_ref'),
            'resource_state': (frame.get('content_access') or {}).get('state'),
            'model': getattr(result, 'model', None),
            'provider': result.provider,
            'system_chars': len(kwargs.get('system') or ''),
            'payload_chars': len(kwargs.get('user') or ''),
            **structural_decision(result.text),
        })
        return result

    async def observe_turn(*args, **kwargs):
        result = await original_turn(*args, **kwargs)
        trace = result['result'].trace or {}
        steps = trace.get('steps') or []
        turns.append({
            'source_ref': result['source_ref'],
            'guard_events': dict(Counter(str(s.get('event')) for s in steps)),
            'decision_path': [{k: s[k] for k in ('event', 'mode', 'tool', 'status', 'errors') if k in s}
                              for s in steps if s.get('event') in {
                                  'AI_DECISION', 'AI_DECISION_RETRY', 'MALFORMED_FALLBACK',
                                  'SOURCE_IMPLICIT_MUTATION_BLOCKED', 'GOVERNANCE_BLOCK'}],
        })
        return result

    with patch.object(ProviderManager, 'chat', observe_chat), patch.object(source_activation, 'run_source_turn', observe_turn):
        report = await driver.run(output)
    details = {'model_decisions': decisions, 'turns': turns, 'oracle_changed': False,
               'runtime_prompts_changed': False, 'passed': report['passed']}
    Path(output + '.diagnostics.json').write_text(json.dumps(details, ensure_ascii=False, indent=2))
    print('ORA_SOURCE166_DIAGNOSTICS ' + json.dumps(details, ensure_ascii=False), flush=True)
    return report['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='/tmp/source166-diagnostics-run.json')
    args = parser.parse_args()
    raise SystemExit(0 if asyncio.run(main(args.output)) else 1)
