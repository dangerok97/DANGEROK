"""Restrict infrastructure failover to operator-selected provider/model pairs.

A candidate set is NOT a certificate of model quality. Evaluation must establish
that separately. No content, subject, user prompt or model output selects this
set. An absent contract preserves the legacy chain. Invalid configuration fails
closed. Context-local state avoids changing simultaneous conversational calls.
"""
from __future__ import annotations
from contextlib import contextmanager
from contextvars import ContextVar
import json
from typing import Optional

_active: ContextVar[Optional[tuple[tuple[str, str], ...]]] = ContextVar('ora_model_contract', default=None)


def parse_contract(raw: Optional[str]):
    if raw is None or raw == '':
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        raise ValueError('invalid_model_contract') from None
    if not isinstance(data, dict) or not 1 <= len(data) <= 16:
        raise ValueError('invalid_model_contract')
    if any(not isinstance(k, str) or not k or len(k) > 48
           or not isinstance(v, str) or not v or len(v) > 160
           for k, v in data.items()):
        raise ValueError('invalid_model_contract')
    return tuple(sorted(data.items()))


@contextmanager
def scoped_model_contract(raw: Optional[str]):
    selected = parse_contract(raw)
    previous = _active.get()
    # An inner call cannot widen an outer infrastructure contract, even if it
    # omits configuration. Unknown providers lead to no eligible provider.
    if previous is not None:
        selected = previous if selected is None else tuple(pair for pair in selected if pair in previous)
    token = _active.set(selected)
    try:
        yield selected
    finally:
        _active.reset(token)


def eligible_names(ordered: list[str], providers) -> list[str]:
    selected = _active.get()
    if selected is None:
        return ordered
    allowed = dict(selected)
    return [name for name in ordered if name in allowed and name in providers
            and providers[name].model_name() == allowed[name]]


def active_contract():
    selected = _active.get()
    return None if selected is None else dict(selected)
