"""Old Home updates leave by themselves (23/10/2026: a 12 October question and an
"11 giorni fa" deadline were still on Home)."""
from datetime import datetime, timedelta, timezone

from agent.models import AutonomousGoal
from home.freshness import STALE_AFTER_HOURS, current_only, is_current

NOW = datetime(2026, 10, 23, 10, 40, tzinfo=timezone.utc)


def iso(delta_hours):
    return (NOW + timedelta(hours=delta_hours)).isoformat()


def test_passed_validity_is_removed_even_if_recent():
    assert not is_current({"created_at": iso(-1), "valid_until": iso(-0.1)}, NOW)
    assert not is_current({"created_at": iso(-1), "expires_at": iso(-0.1)}, NOW)


def test_future_validity_keeps_an_old_entry():
    assert is_current({"created_at": iso(-24 * 20), "valid_until": iso(5)}, NOW)


def test_date_only_validity_lasts_through_that_day():
    assert is_current({"valid_until": "2026-10-23"}, NOW)
    assert not is_current({"valid_until": "2026-10-22"}, NOW)


def test_no_validity_expires_after_inactivity():
    assert is_current({"created_at": iso(-(STALE_AFTER_HOURS - 1))}, NOW)
    assert not is_current({"created_at": iso(-(STALE_AFTER_HOURS + 1))}, NOW)
    # The production cases: 12 October question, "11 giorni fa" deadline.
    assert not is_current({"created_at": "2026-10-12T22:19:00+02:00"}, NOW)
    assert not is_current({"created_at": iso(-24 * 11)}, NOW)


def test_recent_activity_keeps_long_running_work():
    assert is_current({"created_at": iso(-24 * 10), "updated_at": iso(-2)}, NOW)


def test_unknown_age_is_never_hidden_on_a_guess():
    assert is_current({"what": "senza date"}, NOW)
    assert is_current({"created_at": "non una data"}, NOW)


def test_current_only_keeps_order_and_drops_stale():
    rows = [{"id": "a", "created_at": iso(-1)}, {"id": "b", "created_at": iso(-200)},
            {"id": "c", "valid_until": iso(3), "created_at": iso(-300)}]
    assert [r["id"] for r in current_only(rows, NOW)] == ["a", "c"]


def test_agent_work_exposes_last_activity_for_freshness():
    goal = AutonomousGoal(owner_id="user_syn", objective="Lavoro sintetico in corso",
                          desired_outcome="Esito sintetico utile",
                          created_at=iso(-24 * 10), updated_at=iso(-1))
    row = goal.for_human()
    assert row["updated_at"] == iso(-1)
    assert is_current(row, NOW)
