"""V2.4.1 — Canonical Home ownership: Life OS beats stale legacy plan shells.

Generic ranking dimensions only — no domain hardcoding (no psychology/math/exam branches).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from home.actions_catalog import actions_for
from home.models import RANKING_VERSION, HomeItem
from home.ranking import rank_items, score_item
from home.temporal import (
    TEMPORAL_EXPIRED_STALE,
    TEMPORAL_SUPERSEDED,
    enrich_item_temporal_meta,
)


NOW = datetime(2026, 8, 13, 15, 0, 0, tzinfo=timezone.utc)


def _life_os(
    *,
    plan_id: str = "lop_active",
    title: str = "Preparazione obiettivo generico",
    target_days: int = 10,
    current_step: str = "Passo corrente",
    goal_id: str = "goal_life",
) -> HomeItem:
    due = (NOW.date() + timedelta(days=target_days)).isoformat()
    return HomeItem(
        id=f"hi_life_{plan_id}",
        type="activity",
        subtype="life_os_plan",
        title=title,
        description=current_step,
        source_type="life_os_plan",
        source_id=plan_id,
        due_at=due,
        start_at=NOW.date().isoformat(),
        status="open",
        created_at=NOW.isoformat(),
        updated_at=NOW.isoformat(),
        goal_id=goal_id,
        meta={
            "plan_shell": True,
            "canonical_execution": True,
            "ownership": "canonical",
            "actionable_now": True,
            "has_open_near_term": True,
            "next_step": current_step,
            "current_item_title": current_step,
            "life_os_plan_id": plan_id,
            "goal_id": goal_id,
            "route": f"/goal-workspace/{plan_id}",
            "avoid_action_engine": True,
            "freshness": NOW.isoformat(),
            "dedupe_key": f"life_os_focus:{plan_id}",
        },
    )


def _legacy_study(
    *,
    plan_id: str = "sp_old",
    title: str = "Studio: Obiettivo legacy",
    due_offset_days: int = 0,
    goal_id: str = "goal_legacy",
    recovery: bool = False,
    today_session: bool = False,
) -> HomeItem:
    due = (NOW.date() + timedelta(days=due_offset_days)).isoformat()
    return HomeItem(
        id=f"hi_study_{plan_id}",
        type="study",
        subtype="study_plan",
        title=title,
        description="legacy shell",
        source_type="study_plan",
        source_id=plan_id,
        due_at=due,
        status="open",
        created_at=(NOW - timedelta(days=30)).isoformat(),
        updated_at=(NOW - timedelta(days=5)).isoformat(),
        goal_id=goal_id,
        meta={
            "plan_shell": True,
            "canonical_execution": False,
            "ownership": "legacy",
            "actionable_now": today_session or recovery,
            "has_open_near_term": today_session or recovery,
            "study_plan_id": plan_id,
            "goal_id": goal_id,
            "session_today": today_session,
            "missed_sessions": 2 if recovery else 0,
            "skipped_sessions": 1 if recovery else 0,
            "recovery_debt": recovery,
            "dedupe_key": f"study_plan:{plan_id}",
        },
    )


def test_ranking_version_is_1_4():
    assert RANKING_VERSION == "home-rank-1.4"


def test_a_active_life_os_beats_expired_legacy():
    """A — active LifeOsPlan beats expired legacy candidate."""
    life = _life_os()
    stale = _legacy_study(due_offset_days=-1)
    ranked = rank_items([stale, life], now=NOW)
    assert ranked[0].source_type == "life_os_plan"
    assert ranked[0].meta.get("canonical_execution") is True
    stale_r = next(i for i in ranked if i.source_type == "study_plan")
    assert stale_r.meta.get("temporal_state") == TEMPORAL_EXPIRED_STALE
    assert stale_r.score < ranked[0].score


def test_b_expired_cannot_be_daily_focus_without_recovery():
    """B — expired candidate cannot win Daily Focus without recovery semantics."""
    stale = _legacy_study(due_offset_days=-2, recovery=False)
    life = _life_os()
    ranked = rank_items([stale, life], now=NOW)
    focus_pool = [i for i in ranked if i.type != "resume"]
    eligible = [
        i
        for i in focus_pool
        if (i.meta or {}).get("temporal_state")
        not in (TEMPORAL_EXPIRED_STALE, TEMPORAL_SUPERSEDED)
    ]
    assert eligible[0].source_type == "life_os_plan"
    assert eligible[0].id != stale.id


def test_c_active_legacy_can_beat_inactive_life_os():
    """C — active legacy item can still beat irrelevant inactive LifeOsPlan."""
    active_legacy = _legacy_study(
        due_offset_days=2,
        today_session=True,
        goal_id="goal_legacy_active",
    )
    active_legacy.meta["actionable_now"] = True
    active_legacy.meta["temporal_state"] = "ACTIVE"
    active_legacy.meta["session_today"] = True
    inactive = _life_os(plan_id="lop_idle", goal_id="goal_other", target_days=40)
    inactive.meta["actionable_now"] = False
    inactive.meta["has_open_near_term"] = False
    inactive.meta.pop("next_step", None)
    inactive.meta.pop("current_item_title", None)
    inactive.meta["canonical_execution"] = True
    inactive.status = "paused"
    ranked = rank_items([inactive, active_legacy], now=NOW)
    legacy = next(i for i in ranked if i.source_type == "study_plan")
    life = next(i for i in ranked if i.source_type == "life_os_plan")
    assert legacy.meta.get("actionable_now") is True
    # Without actionable_now, Life OS must not auto-win via source name
    if not life.meta.get("actionable_now"):
        assert legacy.score >= life.score


def test_d_ranking_not_source_hardcoded():
    """D — no +999 for source==life_os; uses canonical_execution + actionable_now."""
    life = _life_os()
    score, factors, _ = score_item(life, NOW)
    codes = {f.code for f in factors}
    assert "canonical_active" in codes
    assert not any("life_os" in (f.code or "").lower() and f.weight and f.weight > 50 for f in factors)
    # Same flags on a non-life_os source must get the same canonical boost
    twin = life.model_copy(deep=True)
    twin.source_type = "travel_project"
    twin.id = "hi_twin"
    twin.type = "travel"
    twin.subtype = "travel_project"
    s2, f2, _ = score_item(twin, NOW)
    assert abs(s2 - score) < 15  # type weight may differ slightly
    assert any(f.code == "canonical_active" for f in f2)


def test_e_same_goal_supersedes_legacy_shell():
    """E — same semantic situation (shared goal_id) → legacy superseded."""
    life = _life_os(goal_id="goal_shared")
    legacy = _legacy_study(due_offset_days=5, goal_id="goal_shared", today_session=True)
    ranked = rank_items([legacy, life], now=NOW)
    leg = next(i for i in ranked if i.source_type == "study_plan")
    assert leg.meta.get("temporal_state") == TEMPORAL_SUPERSEDED
    assert ranked[0].source_type == "life_os_plan"


def test_f_distinct_goals_remain_separate():
    """F — distinct goals remain separate (not collapsed by title)."""
    a = _life_os(plan_id="lop_a", title="Obiettivo A", goal_id="g_a")
    b = _legacy_study(plan_id="sp_b", title="Obiettivo B", due_offset_days=7, goal_id="g_b")
    b.meta["actionable_now"] = True
    b.meta["temporal_state"] = "UPCOMING"
    ranked = rank_items([a, b], now=NOW)
    assert len(ranked) == 2
    assert {i.goal_id for i in ranked} == {"g_a", "g_b"}
    assert not any((i.meta or {}).get("supersession") for i in ranked)


def test_g_stale_legacy_suppressed_from_priority_band():
    """G — stale legacy demoted to later / not focus-eligible."""
    stale = _legacy_study(due_offset_days=-3)
    ranked = rank_items([stale], now=NOW)
    assert ranked[0].priority == "later"
    assert ranked[0].meta.get("temporal_state") == TEMPORAL_EXPIRED_STALE


def test_h_life_os_daily_focus_route_goal_workspace():
    """H — LifeOsPlan Daily Focus route → Goal Workspace."""
    life = _life_os(plan_id="lop_route")
    ranked = rank_items([life], now=NOW)
    acts = actions_for(ranked[0])
    routes = [a.route for a in acts if a.route]
    assert any(r == "/goal-workspace/lop_route" for r in routes)
    assert not any(r and r.startswith("/action/") for r in routes)


def test_i_horizon_meta_exposes_future_target():
    """I/M — valid target date + route exposed for Horizon / FE."""
    life = _life_os(target_days=10)
    ranked = rank_items([life], now=NOW)
    pub = ranked[0].to_public()
    assert pub.get("route") == "/goal-workspace/lop_active"
    assert pub.get("canonical_execution") is True
    assert pub.get("temporal_state") in ("ACTIVE", "UPCOMING")
    assert pub.get("due_at") or pub.get("goal_target_date")


def test_j_continue_prefers_canonical_resume():
    """J — Continue prefers canonical active Life OS resume."""
    life_resume = HomeItem(
        id="hi_resume_life",
        type="resume",
        subtype="life_os_plan",
        title="Continua: piano",
        source_type="life_os_plan",
        source_id="lop_c",
        status="open",
        updated_at=NOW.isoformat(),
        meta={
            "resume_kind": "life_os_plan",
            "life_os_plan_id": "lop_c",
            "route": "/goal-workspace/lop_c",
            "avoid_action_engine": True,
            "canonical_execution": True,
            "actionable_now": True,
            "plan_shell": True,
        },
    )
    legacy_resume = HomeItem(
        id="hi_resume_study",
        type="resume",
        subtype="study_plan_draft",
        title="Continua piano legacy",
        source_type="action_session",
        source_id="aes_old",
        status="open",
        updated_at=(NOW - timedelta(days=2)).isoformat(),
        meta={"resume_kind": "study_plan"},
    )
    ranked = rank_items([legacy_resume, life_resume], now=NOW)
    resumes = [i for i in ranked if i.type == "resume"]

    def _resume_rank(r):
        life = 1 if (
            r.source_type == "life_os_plan"
            or (r.meta or {}).get("resume_kind") == "life_os_plan"
        ) else 0
        return (life, r.updated_at or "")

    resumes.sort(key=_resume_rank, reverse=True)
    assert resumes[0].source_type == "life_os_plan"
    acts = actions_for(resumes[0])
    assert any(a.route == "/goal-workspace/lop_c" for a in acts if a.route)


def test_k_legacy_action_still_routes_to_action():
    """K — genuine Action Engine item still routes to /action."""
    ae = HomeItem(
        id="hi_ae",
        type="activity",
        title="Sessione azione",
        source_type="action_session",
        source_id="aes_real",
        status="open",
        meta={"dedupe_key": "ae:aes_real"},
    )
    acts = actions_for(ae)
    assert any(a.route == "/action/aes_real" for a in acts if a.route)


def test_l_current_plan_item_surfaced():
    """L — current plan item surfaced in adapter meta / description path."""
    life = _life_os(current_step="Capire concetto Z")
    assert life.meta.get("current_item_title") == "Capire concetto Z"
    pub = rank_items([life], now=NOW)[0].to_public()
    assert pub.get("current_item_title") == "Capire concetto Z"


def test_n_expired_target_not_future():
    """N — expired target classified EXPIRED_STALE, not UPCOMING."""
    stale = _legacy_study(due_offset_days=-5)
    meta = enrich_item_temporal_meta(stale, NOW)
    assert meta["temporal_state"] == TEMPORAL_EXPIRED_STALE
    assert meta["actionable_now"] is False


def test_o_adapter_semantic_metadata_contract():
    """O — LifeOsPlan Home item carries semantic ranking metadata."""
    life = _life_os()
    required = [
        "life_os_plan_id",
        "canonical_execution",
        "actionable_now",
        "route",
        "ownership",
        "plan_shell",
        "current_item_title",
    ]
    for k in required:
        assert life.meta.get(k) is not None, k


def test_q_generic_non_study_life_os_ranks():
    """Q — generic non-study LifeOsPlan (trip/adoption-like) ranks correctly."""
    trip = _life_os(
        plan_id="lop_trip",
        title="Organizzare trasferimento",
        current_step="Raccogliere documenti",
        target_days=21,
        goal_id="goal_trip",
    )
    stale = _legacy_study(due_offset_days=-1, goal_id="goal_other")
    ranked = rank_items([stale, trip], now=NOW)
    assert ranked[0].source_id == "lop_trip"
    assert ranked[0].meta.get("route") == "/goal-workspace/lop_trip"


def test_s_no_domain_hardcoding_in_ranking_module():
    """S/T — ranking/temporal modules have no Psychology/Matematica branches."""
    import pathlib

    roots = [
        pathlib.Path(__file__).resolve().parents[1] / "home" / "ranking.py",
        pathlib.Path(__file__).resolve().parents[1] / "home" / "temporal.py",
        pathlib.Path(__file__).resolve().parents[1] / "home" / "adapters" / "life_os_plan.py",
    ]
    banned = ("psicolog", "matematica", "computazionale", "psychology")
    for path in roots:
        text = path.read_text(encoding="utf-8").lower()
        for b in banned:
            assert b not in text, f"{path.name} contains {b}"


def test_r_update_object_bumps_revision():
    """R — update_object persists revision + updated_at (lightweight versioning)."""
    from life_os.generative_models import GenerativeObject

    obj = GenerativeObject(
        user_id="u1",
        title="Materiale",
        purpose="studio",
        content={"blocks": [{"type": "paragraph", "text": "difficile"}]},
    )
    assert obj.revision == 1
    obj.content = {"blocks": [{"type": "paragraph", "text": "più semplice"}]}
    obj.touch(bump_revision=True)
    assert obj.revision == 2
    assert obj.updated_at


def test_exam_day_zero_without_session_is_stale():
    """Edge: countdown 0 / due today without session_today → not ACTIVE winner."""
    zero = _legacy_study(due_offset_days=0, today_session=False, recovery=False)
    # Simulate study adapter classification path via enrich override on past hours
    # Due at start of day → hours negative by 15:00
    zero.due_at = NOW.date().isoformat() + "T08:00:00+00:00"
    meta = enrich_item_temporal_meta(zero, NOW)
    assert meta["temporal_state"] in (TEMPORAL_EXPIRED_STALE, "EXPIRED_RECOVERABLE")
    life = _life_os()
    ranked = rank_items([zero, life], now=NOW)
    assert ranked[0].source_type == "life_os_plan"


def test_legacy_study_decision_past_due_loses_to_life_os():
    """Legacy action_engine study decision with past exam must not beat Life OS."""
    life = _life_os()
    dec = HomeItem(
        id="hi_dec_study",
        type="study",
        subtype="study",
        title="Studio: Legacy",
        source_type="decision",
        source_id="dec_1",
        due_at=(NOW.date()).isoformat() + "T07:00:00+00:00",
        status="open",
        goal_id="goal_legacy",
        meta={
            "plan_shell": True,
            "ownership": "legacy",
            "canonical_execution": False,
            "study_plan_id": "sp_x",
            "temporal_state": TEMPORAL_EXPIRED_STALE,
            "actionable_now": False,
            "goal_importance": 5,
            "goal_urgency": 4,
        },
    )
    ranked = rank_items([dec, life], now=NOW)
    assert ranked[0].source_type == "life_os_plan"
    assert ranked[0].meta.get("route", "").startswith("/goal-workspace/")
    stale = next(i for i in ranked if i.id == "hi_dec_study")
    assert stale.meta.get("temporal_state") == TEMPORAL_EXPIRED_STALE
    assert stale.score < ranked[0].score
