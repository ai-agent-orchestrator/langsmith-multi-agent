# Supervisor / Handoff 멀티 에이전트 여행 플래너 (LangGraph)

날씨 · 맛집 · 숙소예약 3개 전문 에이전트를 네 가지 구조로 구성한 설계 골격입니다.
툴은 모두 mock이며, 실행 검증 전의 설계용 코드입니다.

| 안 | 파일 | 적합한 경우 |
|---|---|---|
| A. 슈퍼바이저 | `travel_planner/supervisor_graph.py` | "일정 다 짜줘" 원샷 일정표 (예약 불가) |
| B. 핸드오프 | `travel_planner/handoff_graph.py` | 대화하며 하나씩 정하고 예약 |
| A+B 하이브리드 | `travel_planner/hybrid_graph.py` | 초안 생성 → 사용자 승인 → 예약 대화로 이양 |
| 계층형 (Hierarchical) | 브랜치 `01-hierarchical-supervisor` | 하위 에이전트 8개 이상: 총괄 → 팀장 → 실무자 |

## 구조

- **A**: `supervisor ⇄ {weather, restaurant, hotel}`. 비 오면 실내 맛집 → 맛집 동선 근처 숙소 → 종합. 숙소 에이전트는 예약 툴 없음.
- **B**: `weather ⇄ restaurant ⇄ hotel`. `transfer_to_*` 툴로 제어권을 넘기며 `MemorySaver`로 멀티턴 유지.
- **A+B**: `planner(A) → approval(interrupt) → hotel_booking`. 거절/변경 시 `planner`로 복귀. `draft_plan`을 State로 넘겨 날짜·지역을 다시 묻지 않음.

## 브랜치

| 번호 | 브랜치 | 내용 |
|---|---|---|
| 01 | `01-hierarchical-supervisor` | 계층형 코드 (`hierarchical_graph.py`, `hierarchical_tools.py`) + 흐름 시뮬레이션 `examples/simulate_hierarchical.py` |

`main`에는 설계 문서(이 README)와 A / B / A+B 코드가 있고, 계층형 구현은 위 브랜치에 있습니다.

## 계층형(Hierarchical) 구조

하위 에이전트가 많아져 단일 슈퍼바이저가 감당하기 어려울 때, 중간 관리자(팀장) 슈퍼바이저를 두고 그 위에 총괄 슈퍼바이저를 배치하는 피라미드식 구조입니다.
도메인(팀) 단위로 나눠 각 관리자가 보는 선택지(프롬프트 길이)를 3~5개 이하로 제한하는 것이 핵심입니다.

### 설계 로직 flowchart

![계층형 설계 로직](docs/diagrams/hierarchical-design.png)

- 총괄(Travel Director)은 팀장 3명만 보고, 각 팀장은 자기 팀원만 봅니다.
- 에이전트당 툴은 3개 이하입니다: 날씨 2 / 맛집 3 / 관광지 2 / 항공 3 / 숙소 3 / 렌터카 2 / 번역 1 / 긴급연락 1.

### 작동 흐름 예시 (설계 로직에 요청을 대입한 flowchart)

요청: **"이번 주말 제주도 맛집 투어 짜주고 호텔도 예약해 줘"**

![요청 대입 흐름](docs/diagrams/hierarchical-example.png)

1. **총괄**: 일정 기획과 예약/결제 두 팀이 필요하다고 판단해 `planning_lead`를 먼저 호출합니다.
2. **일정 기획 팀장**: 팀원 `weather_agent`, `restaurant_agent`만 호출해 코스 초안을 만들고 총괄에게 보고합니다. (강수확률 70%이므로 실내 맛집만 선택)
3. **총괄**: 코스 완성을 확인하고 `booking_lead`에게 숙소 예약을 지시합니다.
4. **예약/결제 팀장**: `hotel_agent`가 검색 → 재고 확인 → 예약을 실행하고, 결과를 보고받습니다.
5. **최종 완료**: 총괄이 두 팀장의 보고를 합쳐 사용자에게 답변합니다.

### 실행 결과

`examples/simulate_hierarchical.py` (브랜치 `01-hierarchical-supervisor`)를 실행한 출력입니다.
LLM 없이 라우팅을 스크립트로 고정하고 mock 툴을 실제로 호출하므로, 값은 mock 데이터입니다.

```text
요청: 이번 주말 제주도 맛집 투어 짜주고 호텔도 예약해 줘

① 최상위 총괄 (travel_director)
  [LLM #1] travel_director: 일정 기획 + 예약/결제 두 팀 필요 → planning_lead 먼저 호출

② 일정 기획 팀장 (planning_lead)
  [LLM #2] planning_lead: weather_agent 호출
      · tool get_weather(city='제주', date='2026-11-21') -> {'city': '제주', 'date': '2026-11-21', 'rain_prob': 70, 'summary': '비'}
      · tool get_hourly_forecast(city='제주', date='2026-11-21') -> [{'hour': 9, 'rain_prob': 40}, {'hour': 12, 'rain_prob': 70}, {'hour': 15, 'rain_prob': 80}, {'hour': 18, 'rain_prob': 60}]
  [LLM #3] planning_lead: 강수확률 70% → 실내 위주로 restaurant_agent 호출
      · tool search_restaurants(city='제주', indoor_only=True) -> [{'id': 'r1', 'name': '제주 고기국수 맛집', 'indoor': True}, {'id': 'r2', 'name': '제주 흑돼지 구이집', 'indoor': True}]
  [LLM #4] planning_lead: 코스 초안 완성 ['제주 고기국수 맛집', '제주 흑돼지 구이집'] → 총괄에게 보고

③ 최상위 총괄
  [LLM #5] travel_director: 코스 완성 확인 → booking_lead 에게 숙소 예약 지시

④ 예약/결제 팀장 (booking_lead)
  [LLM #6] booking_lead: hotel_agent 호출
      · tool search_hotels(city='제주', near='제주시내', checkin='2026-11-21', nights=1) -> [{'id': 'h1', 'name': '제주시내 호텔', 'price_per_night': 180000, 'checkin': '2026-11-21', 'nights': 1}]
      · tool check_room(hotel_id='h1', checkin='2026-11-21', nights=1) -> {'hotel_id': 'h1', 'available': True}
      · tool book_hotel(hotel_id='h1', guests=2, checkin='2026-11-21', nights=1) -> {'status': 'confirmed', 'hotel_id': 'h1', 'guests': 2, 'checkin': '2026-11-21', 'nights': 1}
  [LLM #7] booking_lead: 예약 confirmed → 총괄에게 보고

⑤ 최종 완료 (travel_director)
  [LLM #8] travel_director: 두 팀 보고 종합 → 사용자에게 최종 답변

최종 답변:
  - 날씨: 2026-11-21 강수확률 70% → 실내 위주 코스
  - 맛집 코스: 제주 고기국수 맛집 → 제주 흑돼지 구이집
  - 숙소: 제주시내 호텔 (2026-11-21 체크인, 1박, 2명) 예약 confirmed, 180,000원

슈퍼바이저 판단용 LLM 호출 8회 (실무자 에이전트의 툴 호출용 LLM 호출은 제외)
```

### 계층형 구조 도입 시 주의할 점

- **응답 지연(Latency)과 비용 증가**: `총괄 → 팀장 → 실무자 → 팀장 → 총괄` 순으로 LLM 호출 단계가 깊어지므로 응답이 느려지고 토큰 소모가 큽니다.
- **실무 팁**: 처음부터 계층형으로 짜지 말고 단일 슈퍼바이저나 핸드오프로 시작하세요. 에이전트 개수가 7~8개를 넘어가며 정확도가 떨어질 때 팀을 나누어 계층형으로 승격시키는 것이 좋습니다.

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
