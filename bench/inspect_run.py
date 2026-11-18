"""실행 하나(stream.jsonl)의 인증 출처·모델별 토큰·그린 차례마다의 검사 결과 앞 세 줄을 보여 준다.

이벤트를 읽고 그린 차례를 세는 법과 그 실행의 도구를 찾는 법(run_tool)은 run_bench.py의 것을 그대로 쓴다(도구를 못 찾으면
cysUML 그리기 도구 호출을 모두 센다).
"""
import sys
from pathlib import Path

from run_bench import draw_results, draw_uses, read_events, result_text, run_tool

stream = Path(sys.argv[1])
events = read_events(stream.read_text(encoding="utf-8").splitlines())
tool = run_tool(stream.parent)
if tool is None:
    print("알림: 이 실행의 도구를 알 수 없어 cysUML 그리기 도구 호출을 모두 그린 차례로 센다(results.csv의 draws와 다를 수 있다)")

for e in events:
    if e.get("type") == "system" and e.get("subtype") == "init":
        print("init:", {k: e.get(k) for k in ("apiKeySource", "model", "permissionMode")},
              "mcp:", e.get("mcp_servers"), "tools:", e.get("tools"))
ids = [i for i, _ in draw_uses(events, tool)]
results = draw_results(events, ids)
for n, i in enumerate(ids, 1):
    text = result_text(results[i].get("content")) if i in results else "(결과 없음)"
    print(f"draw {n}:", " / ".join(text.splitlines()[:3])[:300])
for e in events:
    if e.get("type") == "result":
        keep = ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "costUSD")
        print("result:", e.get("subtype"), "turns", e.get("num_turns"), "cost", e.get("total_cost_usd"))
        for model, u in (e.get("modelUsage") or {}).items():
            print("  ", model, {k: u.get(k) for k in keep})
