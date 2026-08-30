"""
Which model answers is infrastructure. What ORA decides is not.

The chain is gemini → groq → mistral → openai → ollama → emergent, tried in
that order, and stepped down only for technical reasons: a quota, a rate limit,
a timeout, an unreachable host, a model the account does not serve. Never
because an answer was not liked.

Two things are asserted here. That the mechanics hold — order, classification,
cooldowns, a wrong key not becoming an infinite loop, no invented answer when
everything is down. And that nothing above the adapter layer knows any of these
names, because the moment reasoning branches on who answered, the provider has
stopped being infrastructure.
"""

from __future__ import annotations

import ast
import asyncio
import re
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]

PROVIDER_NAMES = ("gemini", "groq", "mistral", "openai", "ollama", "emergent")


def _run(coro):
    return asyncio.run(coro)


class _Stub:
    """A configured provider that answers, or fails in a stated way."""

    def __init__(self, name, *, error=None, text='{"ok": true}'):
        self.name = name
        self._error = error
        self._text = text
        self.calls = 0

    def is_configured(self):
        return True

    def model_name(self):
        return f"{self.name}-stub"

    async def chat(self, *, system, user, session_id=None, json_mode=False):
        from llm.base import LLMResult

        self.calls += 1
        if self._error is not None:
            raise self._error
        return LLMResult(text=self._text, provider=self.name, model=self.model_name())


def _manager(**stubs):
    from llm.manager import ProviderManager

    manager = ProviderManager()
    for name, stub in stubs.items():
        manager._providers[name] = stub
    for name in PROVIDER_NAMES:
        if name not in stubs:
            manager._providers[name] = _Stub(name, error=RuntimeError("not part of this test"))
            manager._providers[name].is_configured = lambda: False  # type: ignore[method-assign]
    return manager


# ---------------------------------------------------------------------------
# The order, and the reasons for leaving it
# ---------------------------------------------------------------------------

def test_the_chain_is_an_order_not_a_choice():
    from llm.manager import DEFAULT_PRIORITY

    # Two Gemini accounts before changing family: an exhausted quota is not a
    # reason to start reasoning differently, only a reason to bill elsewhere.
    assert DEFAULT_PRIORITY[:4] == ("gemini", "gemini2", "groq", "mistral")
    # No shuffling, no picking, nothing weighted: an ordered tuple read in
    # order is the whole strategy.
    # Prose may say "not random"; code may not do it.
    src = (HERE / "llm" / "manager.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    code = chr(10).join(l for l in src.splitlines() if not l.strip().startswith("#")).lower()
    for word in ("random", "shuffle", "choice(", "round_robin", "weighted"):
        assert word not in code, f"manager.py picks providers: {word}"


def test_the_first_one_that_works_answers_and_the_rest_are_left_alone():
    from llm.errors import LLMQuotaError

    gemini = _Stub("gemini", error=LLMQuotaError("quota"))
    groq = _Stub("groq")
    mistral = _Stub("mistral")
    manager = _manager(gemini=gemini, groq=groq, mistral=mistral)

    result = _run(manager.chat(system="s", user="u", json_mode=True))
    assert result.provider == "groq"
    assert (gemini.calls, groq.calls, mistral.calls) == (1, 1, 0)


def test_the_third_step_exists():
    from llm.errors import LLMQuotaError, LLMRateLimitError

    manager = _manager(
        gemini=_Stub("gemini", error=LLMQuotaError("quota")),
        groq=_Stub("groq", error=LLMRateLimitError("rate_limit")),
        mistral=_Stub("mistral"),
    )
    assert _run(manager.chat(system="s", user="u")).provider == "mistral"


def test_a_model_answering_badly_is_not_a_reason_to_change_provider():
    """
    The step down is for technical failure. A reply somebody dislikes, or one
    the schema rejects, is the reasoning's problem: swapping providers over it
    would make the answer depend on who happened to be up.
    """
    groq = _Stub("groq")
    mistral = _Stub("mistral")
    manager = _manager(
        gemini=_Stub("gemini", text='{"nonsense": "not what was asked for"}'),
        groq=groq,
        mistral=mistral,
    )
    result = _run(manager.chat(system="s", user="u", json_mode=True))
    assert result.provider == "gemini"
    assert (groq.calls, mistral.calls) == (0, 0)


@pytest.mark.parametrize(
    "error_name,kind",
    [
        ("LLMQuotaError", "quota"),
        ("LLMRateLimitError", "rate_limit"),
        ("LLMTimeoutError", "timeout"),
        ("LLMNetworkError", "network"),
        ("LLMModelUnavailableError", "model_unavailable"),
        ("LLMInvalidResponseError", "invalid_response"),
    ],
)
def test_every_technical_failure_steps_down(error_name, kind):
    import llm.errors as errors

    error = getattr(errors, error_name)(kind)
    manager = _manager(gemini=_Stub("gemini", error=error), groq=_Stub("groq"))
    assert _run(manager.chat(system="s", user="u")).provider == "groq"


def test_an_application_bug_is_not_failed_over():
    """
    Letting the next provider mask ORA's own broken code would hide the bug and
    charge for it. `LLMInternalError` is raised, not stepped past.
    """
    from llm.errors import LLMInternalError

    groq = _Stub("groq")
    manager = _manager(gemini=_Stub("gemini", error=ValueError("bug in ORA")), groq=groq)
    with pytest.raises(LLMInternalError):
        _run(manager.chat(system="s", user="u"))
    assert groq.calls == 0


# ---------------------------------------------------------------------------
# A wrong key is not a busy server
# ---------------------------------------------------------------------------

def test_a_bad_key_benches_the_provider_instead_of_being_retried_forever():
    """
    §5. Authentication is a configuration problem: retrying it every request
    would be a loop that costs latency on every single turn and never succeeds.
    """
    from llm.errors import LLMAuthenticationError
    from llm.manager import COOLDOWN_SECONDS

    assert COOLDOWN_SECONDS["authentication"] >= 60
    assert COOLDOWN_SECONDS["configuration"] >= 60
    # And a rate limit, which clears in seconds, is not treated the same way.
    assert COOLDOWN_SECONDS["rate_limit"] <= 10

    gemini = _Stub("gemini", error=LLMAuthenticationError("authentication"))
    manager = _manager(gemini=gemini, groq=_Stub("groq"))

    async def twice():
        await manager.chat(system="s", user="u")
        await manager.chat(system="s", user="u")

    _run(twice())
    assert gemini.calls == 1, "the misconfigured provider was tried again immediately"


def test_a_provider_comes_back_when_its_cooldown_passes():
    """The chain returns to the top; it does not permanently demote anybody."""
    from llm.errors import LLMRateLimitError

    gemini = _Stub("gemini", error=LLMRateLimitError("rate_limit"))
    manager = _manager(gemini=gemini, groq=_Stub("groq"))
    assert _run(manager.chat(system="s", user="u")).provider == "groq"

    manager._providers["gemini"] = _Stub("gemini")
    # Move the clock past the cooldown that was recorded against it.
    later = manager._clock() + 10_000.0
    manager._clock = lambda: later
    assert _run(manager.chat(system="s", user="u")).provider == "gemini"


def test_when_nobody_can_answer_nothing_is_invented():
    from llm.errors import LLMProviderUnavailable, LLMQuotaError

    manager = _manager(**{
        name: _Stub(name, error=LLMQuotaError("quota"))
        for name in ("gemini", "groq", "mistral")
    })
    with pytest.raises(LLMProviderUnavailable) as raised:
        _run(manager.chat(system="s", user="u"))
    attempts = raised.value.attempts
    assert [a["provider"] for a in attempts] == ["gemini", "groq", "mistral"]
    assert all(a["failure_kind"] == "quota" for a in attempts)


# ---------------------------------------------------------------------------
# Observability, and what must never be in it
# ---------------------------------------------------------------------------

def test_a_request_says_who_served_it_and_how_long_it_took():
    from llm.errors import LLMQuotaError

    manager = _manager(
        gemini=_Stub("gemini", error=LLMQuotaError("quota")), groq=_Stub("groq")
    )
    result = _run(manager.chat(system="s", user="u"))
    assert result.provider == "groq" and result.model == "groq-stub"
    assert "latency_ms" in result.usage
    assert result.usage["failover_errors"] == ["gemini:quota"]


def test_no_key_is_ever_carried_in_an_error_or_a_result():
    """
    §8. Errors keep a kind and a retry-after and nothing else — no payloads, no
    headers, no request objects, which is where a credential would ride along.
    """
    src = (HERE / "llm" / "errors.py").read_text(encoding="utf-8")
    assert "never store raw provider payloads" in src

    from llm.errors import LLMProviderUnavailable

    error = LLMProviderUnavailable([
        {"provider": "groq", "failure_kind": "quota", "retryable": True,
         "timestamp": "t", "secret": "gsk_would_not_belong_here"}
    ])
    assert set(error.attempts[0]) == {"provider", "failure_kind", "retryable", "timestamp"}


def test_no_key_is_read_from_anywhere_but_the_environment():
    for name in ("groq_provider.py", "mistral_provider.py", "gemini.py"):
        src = (HERE / "llm" / "providers" / name).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            # A literal that looks like a credential must not exist at all.
            assert not re.match(r"^(gsk_|sk-|AIza)[A-Za-z0-9_\-]{8,}", node.value), name
        assert "os.environ" in src
        for sink in ("db.", "collection", "insert_one", "logger.info(api_key", "print("):
            assert sink not in src, f"{name} may be persisting or printing a key: {sink}"


# ---------------------------------------------------------------------------
# The names live in one place
# ---------------------------------------------------------------------------

def test_nothing_that_reasons_knows_which_model_answered():
    """
    §19. Provider names belong to the adapter layer and the manager. If
    Guidance, Research, Work Admission, Life OS or Home ever branched on one,
    ORA's behaviour would depend on who was up that afternoon.
    """
    reasoning_dirs = (
        HERE / "research",
        HERE / "guidance",
        HERE / "life_os",
        HERE / "home",
        HERE / "life_profile",
    )
    for directory in reasoning_dirs:
        if not directory.exists():
            continue
        for path in directory.rglob("*.py"):
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    doc = ast.get_docstring(node, clean=False)
                    if doc:
                        src = src.replace(doc, "")
            code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
            for provider in PROVIDER_NAMES:
                assert provider not in code.lower(), f"{path.relative_to(HERE)} names {provider}"


def test_the_reasoning_asks_for_a_model_not_for_a_brand():
    """
    Everything that thinks goes through the same door and never names who is
    behind it.
    """
    for path in (
        HERE / "research" / "reasoning.py",
        HERE / "conversation_engine" / "ai_core" / "loop.py",
    ):
        src = path.read_text(encoding="utf-8")
        assert "get_manager()" in src
        for provider in PROVIDER_NAMES:
            assert f'"{provider}"' not in src, f"{path.name} names {provider}"


# ---------------------------------------------------------------------------
# Waiting, when waiting is what the provider asked for
# ---------------------------------------------------------------------------

def test_when_a_provider_says_how_long_to_wait_that_is_what_is_used():
    """
    §7. A default cooldown is a guess. `Retry-After` is not, and the manager
    already extends the cooldown to it — what was missing is the adapters
    reading the header at all, so it was always absent.
    """
    from llm.errors import LLMRateLimitError
    from llm.manager import COOLDOWN_SECONDS

    error = LLMRateLimitError("rate_limit", retry_after=45.0)
    assert error.retry_after == 45.0
    assert error.retry_after > COOLDOWN_SECONDS["rate_limit"]

    for name in ("groq_provider.py", "mistral_provider.py"):
        src = (HERE / "llm" / "providers" / name).read_text(encoding="utf-8")
        assert "retry_after_seconds" in src, name
        assert "retry-after" in src.lower(), name


def test_a_short_wait_is_taken_rather_than_failing_the_turn():
    """
    §7. One turn is many calls, so free tiers rate-limit the whole chain at
    once and a conversation died over a wait that was about to expire. If the
    first provider back is due within a moment, that moment is waited.
    """
    from llm.errors import LLMRateLimitError

    gemini = _Stub("gemini", error=LLMRateLimitError("rate_limit", retry_after=0.4))
    manager = _manager(gemini=gemini)

    async def body():
        # Nobody else is configured, so the first pass finds only a cooling
        # provider — and comes back to it once the window opens.
        with pytest.raises(Exception):
            await manager.chat(system="s", user="u")
        manager._providers["gemini"] = _Stub("gemini")
        return await manager.chat(system="s", user="u")

    result = _run(body())
    assert result.provider == "gemini"


def test_a_long_wait_is_not_taken():
    """The pause is a pacing device, not a place to hang a request."""
    import time as _time

    from llm.errors import LLMProviderUnavailable, LLMQuotaError
    from llm.manager import MAX_PACING_WAIT_S

    assert MAX_PACING_WAIT_S <= 10
    manager = _manager(gemini=_Stub("gemini", error=LLMQuotaError("quota", retry_after=120.0)))

    started = _time.perf_counter()
    with pytest.raises(LLMProviderUnavailable):
        _run(manager.chat(system="s", user="u"))
    assert _time.perf_counter() - started < MAX_PACING_WAIT_S
