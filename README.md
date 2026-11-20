# Supervisor / Handoff 멀티 에이전트 여행 플래너 (LangGraph)

날씨 · 맛집 · 숙소예약 3개 전문 에이전트를 세 가지 구조로 구성한 설계 골격입니다.
툴은 모두 mock이며, 실행 검증 전의 설계용 코드입니다.

| 안 | 파일 | 적합한 경우 |
|---|---|---|
| A. 슈퍼바이저 | `travel_planner/supervisor_graph.py` | "일정 다 짜줘" 원샷 일정표 (예약 불가) |
| B. 핸드오프 | `travel_planner/handoff_graph.py` | 대화하며 하나씩 정하고 예약 |
| A+B 하이브리드 | `travel_planner/hybrid_graph.py` | 초안 생성 → 사용자 승인 → 예약 대화로 이양 |

## 구조

- **A**: `supervisor ⇄ {weather, restaurant, hotel}`. 비 오면 실내 맛집 → 맛집 동선 근처 숙소 → 종합. 숙소 에이전트는 예약 툴 없음.
- **B**: `weather ⇄ restaurant ⇄ hotel`. `transfer_to_*` 툴로 제어권을 넘기며 `MemorySaver`로 멀티턴 유지.
- **A+B**: `planner(A) → approval(interrupt) → hotel_booking`. 거절/변경 시 `planner`로 복귀. `draft_plan`을 State로 넘겨 날짜·지역을 다시 묻지 않음.

## 사용 예

```python
from langchain_anthropic import ChatAnthropic
from travel_planner import build_hybrid_app

app = build_hybrid_app(ChatAnthropic(model="claude-sonnet-4-5"))
cfg = {"configurable": {"thread_id": "t1"}}
app.invoke({"messages": [("user", "이번 주말 제주도 2박 3일 코스 짜줘")]}, cfg)
# interrupt 발생 시: app.invoke(Command(resume=True), cfg)
```

## 참고

- `book_hotel`은 실서비스에서 결제 직전 `interrupt()`로 최종 확인을 받을 것.
- 모델 ID와 LangGraph 버전별 API(`langgraph-supervisor`, `Command`)는 환경에 맞게 확인 필요.
