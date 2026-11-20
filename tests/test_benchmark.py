import pytest

from travel_planner.benchmark import PATTERNS, ScriptedChatModel, measure


@pytest.mark.parametrize("scenario", ["info", "booking"])
def test_single_agent_is_cheapest(scenario):
    res = {p: measure(p, scenario, ScriptedChatModel()) for p in PATTERNS}
    single = res["single"]
    for p in PATTERNS[1:]:
        assert res[p].llm_calls > single.llm_calls, p
        assert res[p].in_chars > single.in_chars, p


def test_single_agent_two_calls_for_three_tools():
    r = measure("single", "info", ScriptedChatModel())
    assert (r.llm_calls, r.tool_calls) == (2, 3)  # 도구 한꺼번에 요청 → 결과 반영해 응답


def test_deeper_hierarchy_costs_more():
    c = {p: measure(p, "info", ScriptedChatModel()).llm_calls for p in ("supervisor", "hierarchical")}
    assert c["hierarchical"] > c["supervisor"]
