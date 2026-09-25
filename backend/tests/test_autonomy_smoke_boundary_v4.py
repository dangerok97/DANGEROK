from types import SimpleNamespace
import pytest
from scripts.autonomy_loop_smoke import isolated_call_allowed

@pytest.mark.parametrize("capability,how,allowed", [
    ("document.read", "read", True), ("document.create", "prepare", True),
    ("", "prepare", True), ("", "compare", True),
    ("web.research", "research", False), ("document.create", "research", False),
    ("email.send", "prepare", False), ("document.read", "execute", False),
    ("", "read", False),
])
def test_fixture_allows_local_reasoning_but_never_external_operations(capability, how, allowed):
    assert isolated_call_allowed(SimpleNamespace(capability_needed=capability), how) is allowed
