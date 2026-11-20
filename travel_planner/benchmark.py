"""구조별 비교 측정: 단일 에이전트 vs 슈퍼바이저(A) vs 핸드오프(B) vs A+B vs 계층형.

같은 요청을 실제 LangGraph 그래프(각 build_* 함수)에 넣고 LLM 호출 수 / 도구 호출 수 / 소요 시간 /
입력 컨텍스트 크기를 콜백으로 센다.

- 기본(스크립트 모드): ScriptedChatModel 이 "합리적인 LLM"처럼 행동한다 (LLM·API 키 불필요).
  * LLM 호출 수·도구 호출 수·입력 크기는 그래프 구조가 만드는 값이라 구조 비교에 의미가 있다.
  * 소요 시간은 호출당 지연(llm_latency)을 sleep 으로 흉내 낸 값이다. 절대값이 아니라 비율을 볼 것.
- 실제 모델(--live): 실제 LLM 으로 같은 측정을 한다. 이 경우 호출 수와 시간이 실측값이다.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

PATTERNS = ["single", "supervisor", "handoff", "hybrid", "hierarchical"]
LABELS = {
    "single": "단일 에이전트 (기준선)",
    "supervisor": "A. 슈퍼바이저",
    "handoff": "B. 핸드오프",
    "hybrid": "A+B 하이브리드",
    "hierarchical": "계층형",
}
SCENARIOS = {
    "info": "이번 주말 제주 날씨랑 맛집, 숙소 추천해줘",  # 도구 3개로 충분한 조회형
    "booking": "이번 주말 제주도 맛집 투어 짜주고 호텔도 예약해 줘",  # 예약까지
}


# ======================================================================= 스크립트 모델
def _date() -> str:
    d = datetime.now()
    return (d + timedelta(days=(5 - d.weekday()) % 7)).strftime("%Y-%m-%d")


def _args(tool: str) -> dict:
    d = _date()
    return {
        "get_weather": {"city": "제주", "date": d},
        "search_restaurants": {"city": "제주", "indoor_only": True},
        "search_hotels": {"city": "제주", "near": "제주시내", "checkin": d, "nights": 1},
        "check_room": {"hotel_id": "h1", "checkin": d, "nights": 1},
        "book_hotel": {"hotel_id": "h1", "guests": 2, "checkin": d, "nights": 1},
    }.get(tool, {})


def _calls(*names: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": n, "args": _args(n), "id": f"c{uuid.uuid4().hex[:8]}"} for n in names])


# 슈퍼바이저가 위임하는 우선순위 (A 의 이름 / 계층형의 이름)
_SUP_ORDER = ["weather", "restaurant", "hotel", "planning_lead", "booking_lead",
              "weather_agent", "restaurant_agent", "hotel_agent"]
_WORKER_TOOLS = ["get_weather", "search_restaurants", "search_hotels", "check_room", "book_hotel"]
_HANDOFF_ORDER = ["weather", "restaurant", "hotel"]


def decide(messages: list, tool_names: tuple) -> AIMessage:
    """도구 구성과 대화 이력만 보고 다음 행동을 정하는 규칙 기반 '합리적 LLM'."""
    names = set(tool_names)
    transfers = {n.removeprefix("transfer_to_") for n in names if n.startswith("transfer_to_")}
    domain = [n for n in _WORKER_TOOLS if n in names]
    question = next((m.content for m in messages if isinstance(m, HumanMessage)), "")
    wants_booking = "예약" in question
    wants_hotel = wants_booking or any(k in question for k in ("호텔", "숙소"))
    last = messages[-1]

    # --- 1) 슈퍼바이저 (도메인 툴 없이 transfer 툴만 가짐): 순서대로 위임, 끝나면 종합
    if not domain:
        def needed(t: str) -> bool:
            return wants_hotel if t in ("hotel", "booking_lead", "hotel_agent") else True

        seq = [t for t in _SUP_ORDER if t in transfers and needed(t)]
        done = {m.name for m in messages if isinstance(m, AIMessage) and m.name} | {
            m.name.removeprefix("transfer_back_to_") for m in messages if isinstance(m, ToolMessage) and m.name
            and m.name.startswith("transfer_back_to_")
        }
        # 계층형: 팀장 이름이 done 에 있으면 그 팀 완료
        nxt = next((t for t in seq if t not in done), None)
        if nxt:
            return _calls(f"transfer_to_{nxt}")
        return AIMessage(content="두 팀 보고를 종합한 최종 답변입니다.")

    # --- 2) 단일 에이전트 (날씨·맛집·숙소 도구를 모두 가짐): 한꺼번에 병렬 호출 → 종합
    if {"get_weather", "search_restaurants", "search_hotels"} <= names:
        called = {m.name for m in messages if isinstance(m, ToolMessage)}
        if not called:
            return _calls("get_weather", "search_restaurants", "search_hotels")
        if wants_booking and "book_hotel" in names and "book_hotel" not in called:
            return _calls("book_hotel")  # 예약은 검색 결과(hotel_id)가 필요해 직렬
        return AIMessage(content="도구 결과를 반영한 최종 답변입니다.")

    # --- 3) 전문 에이전트: 자기 도구를 순서대로 → (핸드오프면 다음 에이전트로 전달) → 최종 응답
    seq = [t for t in domain if wants_booking or t not in ("check_room", "book_hotel")]
    if "book_hotel" in seq and "search_hotels" in seq and "check_room" in seq and not wants_booking:
        seq = [t for t in seq if t != "check_room"]
    if "search_hotels" in seq and "check_room" in seq:
        pass  # 계층형 hotel_agent: 검색 → 재고 확인 → 예약
    elif "check_room" in seq:
        seq.remove("check_room")
    called = {m.name for m in messages if isinstance(m, ToolMessage)}
    pending = next((t for t in seq if t not in called), None)
    if pending:
        return _calls(pending)
    me = {"get_weather": "weather", "search_restaurants": "restaurant", "search_hotels": "hotel"}.get(
        domain[0], "hotel")
    if isinstance(last, ToolMessage) and me in _HANDOFF_ORDER:
        later = _HANDOFF_ORDER[_HANDOFF_ORDER.index(me) + 1:]
        nxt = next((t for t in later if t in transfers and (wants_hotel or t != "hotel")), None)
        if nxt:
            return AIMessage(content="", tool_calls=[{"name": f"transfer_to_{nxt}", "args": {}, "id": f"t{uuid.uuid4().hex[:8]}"}])
    return AIMessage(content="담당 영역 결과를 정리했습니다.")


class ScriptedChatModel(BaseChatModel):
    """decide() 규칙으로 도구 호출/응답을 만드는 가짜 LLM. latency 초만큼 sleep 해 호출 비용을 흉내 낸다."""

    latency: float = 0.0
    tool_names: tuple = ()

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        names = tuple(getattr(t, "name", None) or (t.get("name") if isinstance(t, dict) else str(t)) for t in tools)
        return self.model_copy(update={"tool_names": names})

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if self.latency:
            time.sleep(self.latency)
        return ChatResult(generations=[ChatGeneration(message=decide(list(messages), self.tool_names))])


# ======================================================================= 측정
class Meter(BaseCallbackHandler):
    """LLM 호출 / 도구 호출 / 입력 크기 / 토큰(있으면)을 센다. tool_latency 로 도구 지연도 흉내 낼 수 있다."""

    def __init__(self, tool_latency: float = 0.0):
        self.llm_calls = 0
        self.tool_calls = 0
        self.in_chars = 0
        self.tokens = 0
        self.by_agent: Counter = Counter()
        self.tool_latency = tool_latency
        self._lock = threading.Lock()

    def on_chat_model_start(self, serialized, messages, *, metadata=None, **kwargs):
        md = metadata or {}
        with self._lock:
            self.llm_calls += 1
            self.in_chars += sum(len(str(m.content)) for m in messages[0])
            self.by_agent[md.get("lc_agent_name") or md.get("langgraph_node") or "?"] += 1

    def on_llm_end(self, response, **kwargs):
        for gens in response.generations:
            for g in gens:
                usage = getattr(getattr(g, "message", None), "usage_metadata", None)
                if usage:
                    with self._lock:
                        self.tokens += int(usage.get("total_tokens", 0))

    def on_tool_start(self, serialized, input_str, **kwargs):
        with self._lock:
            self.tool_calls += 1
        if self.tool_latency:
            time.sleep(self.tool_latency)


@dataclass
class Result:
    pattern: str
    scenario: str
    llm_calls: int
    tool_calls: int
    seconds: float
    in_chars: int
    tokens: int
    by_agent: dict = field(default_factory=dict)
    note: str = ""


def build_app(pattern: str, model: Any):
    from .handoff_graph import build_handoff_app
    from .hierarchical_graph import build_hierarchical_app
    from .hybrid_graph import build_hybrid_app
    from .single_graph import build_single_app
    from .supervisor_graph import build_supervisor_app

    b = {"single": build_single_app, "supervisor": build_supervisor_app, "handoff": build_handoff_app,
         "hybrid": build_hybrid_app, "hierarchical": build_hierarchical_app}[pattern]
    return b(model)


def measure(pattern: str, scenario: str, model: Any, *, tool_latency: float = 0.0) -> Result:
    app = build_app(pattern, model)
    meter = Meter(tool_latency)
    cfg = {"callbacks": [meter], "recursion_limit": 60, "configurable": {"thread_id": f"bench-{pattern}-{scenario}"}}
    q = SCENARIOS[scenario]
    note = ""
    t0 = time.perf_counter()
    out = app.invoke({"messages": [("user", q)]}, cfg)
    if pattern == "hybrid":
        if "__interrupt__" in out:
            if scenario == "booking":
                app.invoke(Command(resume=True), cfg)  # 사용자 승인 후 예약 대화로 이양
                note = "초안 → 승인 → 예약"
            else:
                note = "초안까지 (승인 대기에서 종료)"
    seconds = time.perf_counter() - t0
    if pattern == "supervisor" and scenario == "booking":
        note = "예약 도구 없음 (숙소 후보까지)"
    return Result(pattern, scenario, meter.llm_calls, meter.tool_calls, seconds, meter.in_chars, meter.tokens,
                  dict(meter.by_agent), note)


def run_all(*, live_model: Any = None, llm_latency: float = 0.5, tool_latency: float = 0.1,
            scenarios: tuple = ("info", "booking"), patterns: tuple = tuple(PATTERNS)) -> list[Result]:
    results = []
    for sc in scenarios:
        for p in patterns:
            model = live_model or ScriptedChatModel(latency=llm_latency)
            results.append(measure(p, sc, model, tool_latency=0.0 if live_model else tool_latency))
    return results


def render(results: list[Result], *, simulated: bool = True) -> str:
    out = []
    for sc in dict.fromkeys(r.scenario for r in results):
        rows = [r for r in results if r.scenario == sc]
        base = next((r for r in rows if r.pattern == "single"), rows[0])
        out += [f"### 시나리오 `{sc}`: {SCENARIOS[sc]}", "",
                "| 구조 | LLM 호출 | 도구 호출 | 소요(초) | 단일 대비 시간 | 입력 컨텍스트(자) | 비고 |",
                "|---|---:|---:|---:|---:|---:|---|"]
        for r in rows:
            out.append(f"| {LABELS[r.pattern]} | {r.llm_calls} | {r.tool_calls} | {r.seconds:.1f} | "
                       f"x{r.seconds / base.seconds:.1f} | {r.in_chars:,} | {r.note} |")
        out.append("")
    if simulated:
        out.append("> 스크립트 모드: 호출 수·입력 크기는 구조에서 나온 값, 소요 시간은 호출당 지연을 sleep 으로 흉내 낸 값입니다.")
    return "\n".join(out)
