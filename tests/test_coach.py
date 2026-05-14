"""Tests for agent/tools.py and web/cost.py (no Anthropic/OpenAI calls)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from coach.agent.tools import (
    TOOL_SCHEMAS,
    _compare_to_ride,
    _fetch_ride_detail,
    _find_similar_routes,
    _get_recent_load,
    _get_wellness_window,
    execute_tool,
)
from coach.store.models import Activity, Message, Metrics
from coach.web.cost import calculate_cost, monthly_total, record_usage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(*objects):
    """Build a minimal mock SQLAlchemy session backed by a dict store."""
    store: dict[tuple, object] = {}
    scalars_results: list = []

    for obj in objects:
        key = (type(obj).__name__, getattr(obj, "id", None) or getattr(obj, "date", None))
        store[key] = obj
        scalars_results.append(obj)

    session = MagicMock()

    def _get(cls, pk):
        return store.get((cls.__name__, pk))

    session.get.side_effect = _get

    # execute().scalars() always returns empty list; tests that need rows use custom side_effects
    scalars_mock = MagicMock()
    scalars_mock.__iter__ = MagicMock(return_value=iter([]))
    scalars_mock.all.return_value = []
    execute_mock = MagicMock()
    execute_mock.scalars.return_value = scalars_mock
    execute_mock.scalar_one_or_none.return_value = None
    execute_mock.scalar.return_value = None
    execute_mock.fetchall.return_value = []
    session.execute.return_value = execute_mock

    return session


def _make_activity(activity_id=1, **kwargs) -> Activity:
    defaults = dict(
        id=activity_id,
        start_time=datetime.datetime(2026, 4, 15, 8, 0, tzinfo=datetime.UTC),
        sport="cycling",
        sub_sport="road",
        is_indoor=False,
        bike_type="road",
        distance_m=50_000,
        duration_s=7_200,
        elev_gain_m=500,
        avg_hr=140,
        max_hr=175,
        tss_proxy=80.0,
    )
    defaults.update(kwargs)
    return Activity(**defaults)


def _make_metrics(activity_id=1) -> Metrics:
    return Metrics(
        activity_id=activity_id,
        decoupling_pct=3.0,
        hr_drift_pct=2.0,
        time_in_z1=600,
        time_in_z2=4000,
        time_in_z3=1800,
        time_in_z4=800,
        time_in_z5=0,
        vam_best_20min=750,
        gap_normalized=5.0,
    )


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------


def test_tool_schemas_count():
    assert len(TOOL_SCHEMAS) == 5


def test_tool_schema_names():
    names = {t["function"]["name"] for t in TOOL_SCHEMAS}
    assert names == {
        "fetch_ride_detail",
        "compare_to_ride",
        "get_recent_load",
        "get_wellness_window",
        "find_similar_routes",
    }


def test_tool_schema_openai_shape():
    for tool in TOOL_SCHEMAS:
        assert tool["type"] == "function"
        assert "function" in tool
        assert "parameters" in tool["function"]
        assert tool["function"]["parameters"]["type"] == "object"


# ---------------------------------------------------------------------------
# execute_tool dispatch
# ---------------------------------------------------------------------------


def test_execute_tool_unknown():
    session = _make_session()
    result = execute_tool(session, "nonexistent_tool", {})
    assert "error" in result


def test_execute_tool_fetch_ride_detail_not_found():
    session = _make_session()
    result = execute_tool(session, "fetch_ride_detail", {"activity_id": 9999})
    assert "error" in result


def test_execute_tool_fetch_ride_detail_found():
    act = _make_activity()
    session = _make_session(act)
    result = execute_tool(session, "fetch_ride_detail", {"activity_id": 1})
    assert "activity" in result
    assert result["activity"]["id"] == 1
    assert result["activity"]["distance_km"] == 50.0


# ---------------------------------------------------------------------------
# _fetch_ride_detail
# ---------------------------------------------------------------------------


def test_fetch_ride_detail_returns_distance_km():
    act = _make_activity(distance_m=62_300)
    session = _make_session(act)
    result = _fetch_ride_detail(session, 1)
    assert result["activity"]["distance_km"] == 62.3


def test_fetch_ride_detail_includes_metrics():
    act = _make_activity()
    m = _make_metrics()
    session = _make_session(act, m)

    # Patch get to return correct object by type+pk
    def _get(cls, pk):
        if cls.__name__ == "Activity" and pk == 1:
            return act
        if cls.__name__ == "Metrics" and pk == 1:
            return m
        return None

    session.get.side_effect = _get
    result = _fetch_ride_detail(session, 1)
    assert result["metrics"]["decoupling_pct"] == 3.0


# ---------------------------------------------------------------------------
# _compare_to_ride
# ---------------------------------------------------------------------------


def test_compare_to_ride_both_present():
    act_a = _make_activity(activity_id=1)
    act_b = _make_activity(activity_id=2, distance_m=40_000)

    def _get(cls, pk):
        if cls.__name__ == "Activity":
            return act_a if pk == 1 else act_b if pk == 2 else None
        return None

    session = MagicMock()
    session.get.side_effect = _get
    scalars_mock = MagicMock()
    scalars_mock.__iter__ = MagicMock(return_value=iter([]))
    scalars_mock.all.return_value = []
    execute_mock = MagicMock()
    execute_mock.scalars.return_value = scalars_mock
    session.execute.return_value = execute_mock

    result = _compare_to_ride(session, 1, 2)
    assert result["ride_a"]["id"] == 1
    assert result["ride_b"]["distance_km"] == 40.0


# ---------------------------------------------------------------------------
# _get_recent_load
# ---------------------------------------------------------------------------


def test_get_recent_load_empty():
    session = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.__iter__ = MagicMock(return_value=iter([]))
    execute_mock = MagicMock()
    execute_mock.scalars.return_value = scalars_mock
    session.execute.return_value = execute_mock

    result = _get_recent_load(session, 28)
    assert result["days_requested"] == 28
    assert result["acwr"] is None
    assert result["daily_trimp"] == {}


def test_get_recent_load_with_activities():
    act = _make_activity(tss_proxy=80.0)
    session = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.__iter__ = MagicMock(return_value=iter([act]))
    execute_mock = MagicMock()
    execute_mock.scalars.return_value = scalars_mock
    session.execute.return_value = execute_mock

    result = _get_recent_load(session, 28)
    assert len(result["daily_trimp"]) == 1
    date_key = list(result["daily_trimp"].keys())[0]
    assert result["daily_trimp"][date_key] == 80.0


# ---------------------------------------------------------------------------
# _get_wellness_window
# ---------------------------------------------------------------------------


def test_get_wellness_window_structure():
    session = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.__iter__ = MagicMock(return_value=iter([]))
    execute_mock = MagicMock()
    execute_mock.scalars.return_value = scalars_mock
    session.execute.return_value = execute_mock

    result = _get_wellness_window(session, 14)
    assert result["days_requested"] == 14
    assert result["entries"] == []


# ---------------------------------------------------------------------------
# _find_similar_routes
# ---------------------------------------------------------------------------


def test_find_similar_routes_not_found():
    session = MagicMock()
    session.get.return_value = None
    result = _find_similar_routes(session, 9999)
    assert "error" in result


def test_find_similar_routes_returns_list():
    act = _make_activity()
    session = MagicMock()
    session.get.return_value = act

    scalars_mock = MagicMock()
    scalars_mock.__iter__ = MagicMock(return_value=iter([]))
    execute_mock = MagicMock()
    execute_mock.scalars.return_value = scalars_mock
    session.execute.return_value = execute_mock

    result = _find_similar_routes(session, 1)
    assert result["reference_activity_id"] == 1
    assert isinstance(result["similar_activities"], list)


# ---------------------------------------------------------------------------
# cost.py — calculate_cost
# ---------------------------------------------------------------------------


def test_calculate_cost_zero():
    assert calculate_cost() == Decimal("0")


def test_calculate_cost_input_only():
    # 1M input tokens at $0.40/MTok
    cost = calculate_cost(tokens_in=1_000_000)
    assert cost == Decimal("0.40")


def test_calculate_cost_output_only():
    # 1M output tokens at $1.60/MTok
    cost = calculate_cost(tokens_out=1_000_000)
    assert cost == Decimal("1.60")


def test_calculate_cost_cache_read():
    # 1M cached tokens at $0.10/MTok
    cost = calculate_cost(cache_read=1_000_000)
    assert cost == Decimal("0.10")


def test_calculate_cost_combined():
    cost = calculate_cost(tokens_in=500_000, tokens_out=100_000)
    # 0.5 * $0.40 + 0.1 * $1.60 = $0.20 + $0.16 = $0.36
    assert cost == Decimal("0.36")


# ---------------------------------------------------------------------------
# cost.py — record_usage
# ---------------------------------------------------------------------------


def test_record_usage_populates_message():
    from types import SimpleNamespace

    session = MagicMock()
    msg = Message(conversation_id=1, role="assistant", content_json="hi")

    usage = SimpleNamespace(
        prompt_tokens=1500,
        completion_tokens=400,
        prompt_tokens_details=SimpleNamespace(cached_tokens=1200),
    )

    cost = record_usage(session, msg, usage)

    assert msg.tokens_in == 1500  # total prompt tokens stored
    assert msg.tokens_out == 400
    assert msg.cache_read == 1200
    assert msg.cache_write == 0
    assert msg.cost_usd is not None
    assert cost > Decimal("0")


# ---------------------------------------------------------------------------
# cost.py — monthly_total
# ---------------------------------------------------------------------------


def test_monthly_total_structure():
    session = MagicMock()
    execute_mock = MagicMock()
    execute_mock.scalar.return_value = None
    session.execute.return_value = execute_mock

    result = monthly_total(session)
    assert "month" in result
    assert "total_cost_usd" in result
    assert "total_api_calls" in result
    assert "projected_monthly_usd" in result
    assert result["total_cost_usd"] == 0.0
