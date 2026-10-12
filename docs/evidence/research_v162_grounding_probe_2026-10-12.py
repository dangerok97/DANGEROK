"""Exact extractor reproduction; local files only, no application imports or provider I/O."""
import ast
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace as N
from typing import Any, List
import hashlib
import json

root = Path('/workspace/scratch/abe5c63b5e73/ora/backend')
path = root / 'conversation_engine/ai_core/tools/providers/gemini_search.py'
base = root / 'conversation_engine/ai_core/tools/providers/base.py'
namespace = {'dataclass': dataclass, 'Any': Any, 'List': List}
for source, name in ((base, 'RawHit'), (path, '_extract_hits')):
    node = next(node for node in ast.parse(source.read_text()).body
                if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)

chunks = [N(web=N(uri='https://example.invalid/source-a', title='Synthetic source A')),
          N(web=N(uri='https://example.invalid/source-b', title='Synthetic source B'))]
text = 'Misura esclusivamente sintetica attribuita alla fonte B: 120 minuti.'


def extract(indices, maximum=5):
    support = N(segment=N(text=text), grounding_chunk_indices=indices)
    response = N(candidates=[N(grounding_metadata=N(grounding_chunks=chunks, grounding_supports=[support]))])
    return [dict(title=hit.title, url=hit.url, snippet=hit.snippet)
            for hit in namespace['_extract_hits'](response, max_results=maximum)]


report = {'mode': 'Exact AST extractor and RawHit class; no HTTP/SDK/model calls',
          'source_file': str(path), 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
          'grounding_support': {'segment': {'text': text}, 'grounding_chunk_indices': [1]},
          'actual_max5': extract([1]), 'expected_snippets_max5': ['', text],
          'actual_max2': extract([1], 2), 'actual_indices_missing': extract(None)}
Path('/tmp/ora_v162_gemini_grounding_index_red.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(report, ensure_ascii=False, indent=2))
