"""기준선(Baseline): 단일 에이전트 - 도구 전부를 한 에이전트가 직접 호출한다.

도구가 적고 도메인 규칙이 충돌하지 않는 규모에서는 이쪽이 가장 빠르고 저렴하다.
슈퍼바이저/핸드오프/계층형은 이 기준선보다 나을 때만 도입한다 (benchmark.py 참고).
"""
from langgraph.prebuilt import create_react_agent

from .tools import book_hotel, get_weather, search_hotels, search_restaurants


def build_single_app(model):
    return create_react_agent(
        model,
        [get_weather, search_restaurants, search_hotels, book_hotel],
        name="single",
        prompt="여행 도우미. 필요한 도구를 한꺼번에 호출해 결과를 반영해 바로 답한다. 예약 요청이 있을 때만 book_hotel 호출.",
    )
