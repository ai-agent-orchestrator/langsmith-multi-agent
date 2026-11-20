"""계층형(Hierarchical) 슈퍼바이저 - 총괄 1 + 팀장 3 + 전문 에이전트 8.

Travel Director
├─ 일정 기획 팀장: 날씨(툴2) / 맛집(툴3) / 관광지(툴2)
├─ 예약/결제 팀장: 항공(툴3) / 숙소(툴3) / 렌터카(툴2)
└─ 현지 지원 팀장: 번역 / 긴급연락

각 슈퍼바이저가 보는 선택지는 3개 이하, 에이전트당 툴은 3개 이하로 유지한다.
모든 툴은 mock 이다.
"""
from langgraph.prebuilt import create_react_agent
from langgraph_supervisor import create_supervisor

from .hierarchical_tools import (
    book_car, book_flight, book_hotel, check_room, check_seat, check_wait_time,
    get_emergency_contacts, get_hourly_forecast, get_menu, get_opening_hours,
    get_weather, search_attractions, search_cars, search_flights, search_hotels,
    search_restaurants, translate,
)


def _agent(model, name, tools, prompt):
    return create_react_agent(model, tools, name=name, prompt=prompt)


def _team(model, name, prompt, members):
    """팀장 슈퍼바이저를 서브그래프로 컴파일 (이름 필수: 상위가 에이전트로 호출)."""
    return create_supervisor(members, model=model, prompt=prompt, supervisor_name=name,
                             output_mode="last_message").compile(name=name)


def build_hierarchical_app(model, checkpointer=None):
    weather = _agent(model, "weather_agent", [get_weather, get_hourly_forecast], "날씨/시간대별 예보 담당")
    restaurant = _agent(model, "restaurant_agent", [search_restaurants, get_menu, check_wait_time], "맛집 담당")
    attraction = _agent(model, "attraction_agent", [search_attractions, get_opening_hours], "관광지 담당")

    flight = _agent(model, "flight_agent", [search_flights, check_seat, book_flight], "항공 예약 담당")
    hotel = _agent(model, "hotel_agent", [search_hotels, check_room, book_hotel], "숙소 예약 담당")
    car = _agent(model, "car_agent", [search_cars, book_car], "렌터카 예약 담당")

    translator = _agent(model, "translation_agent", [translate], "번역 담당")
    emergency = _agent(model, "emergency_agent", [get_emergency_contacts], "긴급 연락 담당")

    planning = _team(model, "planning_lead",
                     "일정 기획 팀장. 날씨를 먼저 확인하고, 비면 실내 위주 맛집/관광지로 일정 초안을 만든다.",
                     [weather, restaurant, attraction])
    booking = _team(model, "booking_lead",
                    "예약/결제 팀장. 항공 → 숙소 → 렌터카 순으로 예약한다. 사용자가 승인한 항목만 예약.",
                    [flight, hotel, car])
    support = _team(model, "support_lead",
                    "현지 지원 팀장. 번역과 긴급 연락 요청만 처리한다.",
                    [translator, emergency])

    director = create_supervisor(
        [planning, booking, support],
        model=model,
        supervisor_name="travel_director",
        prompt=(
            "너는 Travel Director 다. 요청을 팀 단위로만 분배한다: "
            "일정 기획(planning_lead) / 예약·결제(booking_lead) / 현지 지원(support_lead). "
            "일정이 확정되기 전에는 booking_lead 를 호출하지 말고, 팀 결과를 종합해 최종 답을 낸다."
        ),
        output_mode="last_message",
    )
    return director.compile(checkpointer=checkpointer)
