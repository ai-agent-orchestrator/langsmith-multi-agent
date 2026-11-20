"""구조별 LLM 호출 수 / 소요 시간 비교 (단일 · A · B · A+B · 계층형).

  python -I examples/benchmark_structures.py                       # 스크립트 모드 (LLM·키 불필요)
  python -I examples/benchmark_structures.py --llm-latency 1.5     # 호출당 지연을 키워 비율 변화 보기
  python -I examples/benchmark_structures.py --live --model claude-sonnet-4-5   # 실제 LLM 실측 (API 키 필요)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from travel_planner.benchmark import PATTERNS, render, run_all  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--llm-latency", type=float, default=0.5, help="스크립트 모드: LLM 1회당 지연(초)")
ap.add_argument("--tool-latency", type=float, default=0.1, help="스크립트 모드: 도구 1회당 지연(초)")
ap.add_argument("--scenario", choices=["info", "booking", "both"], default="both")
ap.add_argument("--patterns", nargs="+", choices=PATTERNS, default=PATTERNS)
ap.add_argument("--live", action="store_true", help="실제 모델로 측정 (ANTHROPIC_API_KEY 필요)")
ap.add_argument("--model", default="claude-sonnet-4-5")
args = ap.parse_args()

live = None
if args.live:
    from langchain_anthropic import ChatAnthropic

    live = ChatAnthropic(model=args.model)

scenarios = ("info", "booking") if args.scenario == "both" else (args.scenario,)
results = run_all(live_model=live, llm_latency=args.llm_latency, tool_latency=args.tool_latency,
                  scenarios=scenarios, patterns=tuple(args.patterns))
print(render(results, simulated=not args.live))
