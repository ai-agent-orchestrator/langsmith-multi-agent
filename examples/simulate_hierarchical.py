"""계층형 흐름 시뮬레이션 (LLM 미사용, 라우팅은 스크립트로 고정).

요청: "이번 주말 제주도 맛집 투어 짜주고 호텔도 예약해 줘"
실제 mock 툴을 호출해 총괄 → 팀장 → 실무자 → 팀장 → 총괄 흐름과 결과값을 출력한다.

실행: python -I examples/simulate_hierarchical.py   (저장소 루트에서)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from travel_planner.hierarchical_tools import (  # noqa: E402
    book_hotel, check_room, get_hourly_forecast, get_weather,
    search_hotels, search_restaurants,
)

REQUEST = "이번 주말 제주도 맛집 투어 짜주고 호텔도 예약해 줘"
CITY, DATE, CHECKIN, NIGHTS, GUESTS = "제주", "2026-11-21", "2026-11-21", 1, 2

llm_calls = 0


def llm(who: str, msg: str):
    """LLM 호출 1회로 계산 (라우팅/종합 판단)."""
    global llm_calls
    llm_calls += 1
    print(f"  [LLM #{llm_calls}] {who}: {msg}")


def tool(name: str, fn, **kw):
    out = fn.invoke(kw)
    print(f"      · tool {name}({', '.join(f'{k}={v!r}' for k, v in kw.items())}) -> {out}")
    return out


print(f"요청: {REQUEST}\n")

print("① 최상위 총괄 (travel_director)")
llm("travel_director", "일정 기획 + 예약/결제 두 팀 필요 → planning_lead 먼저 호출")

print("\n② 일정 기획 팀장 (planning_lead)")
llm("planning_lead", "weather_agent 호출")
w = tool("get_weather", get_weather, city=CITY, date=DATE)
tool("get_hourly_forecast", get_hourly_forecast, city=CITY, date=DATE)
llm("planning_lead", f"강수확률 {w['rain_prob']}% → 실내 위주로 restaurant_agent 호출")
indoor = w["rain_prob"] >= 60
rest = tool("search_restaurants", search_restaurants, city=CITY, indoor_only=indoor)
course = [r["name"] for r in rest]
llm("planning_lead", f"코스 초안 완성 {course} → 총괄에게 보고")

print("\n③ 최상위 총괄")
llm("travel_director", "코스 완성 확인 → booking_lead 에게 숙소 예약 지시")

print("\n④ 예약/결제 팀장 (booking_lead)")
llm("booking_lead", "hotel_agent 호출")
hotels = tool("search_hotels", search_hotels, city=CITY, near=rest[0]["name"].split()[0] + "시내", checkin=CHECKIN, nights=NIGHTS)
room = tool("check_room", check_room, hotel_id=hotels[0]["id"], checkin=CHECKIN, nights=NIGHTS)
assert room["available"]
booked = tool("book_hotel", book_hotel, hotel_id=hotels[0]["id"], guests=GUESTS, checkin=CHECKIN, nights=NIGHTS)
llm("booking_lead", f"예약 {booked['status']} → 총괄에게 보고")

print("\n⑤ 최종 완료 (travel_director)")
llm("travel_director", "두 팀 보고 종합 → 사용자에게 최종 답변")
total = hotels[0]["price_per_night"] * NIGHTS
print(
    f"\n최종 답변:\n"
    f"  - 날씨: {DATE} 강수확률 {w['rain_prob']}% → 실내 위주 코스\n"
    f"  - 맛집 코스: {' → '.join(course)}\n"
    f"  - 숙소: {hotels[0]['name']} ({CHECKIN} 체크인, {NIGHTS}박, {GUESTS}명) 예약 {booked['status']}, {total:,}원\n"
    f"\n슈퍼바이저 판단용 LLM 호출 {llm_calls}회 (실무자 에이전트의 툴 호출용 LLM 호출은 제외)"
)
