"""실행 하나(stream.jsonl)의 인증 출처·모델별 토큰·그린 차례마다의 검사 결과 앞 세 줄을 보여 준다.

이벤트를 읽고 그린 차례를 세는 법은 run_bench.py의 것을 그대로 쓴다. 그 문제의 도구는 같은 폴더의 row.json에서 읽고,
그것이 없는 옛 기록은 prompt.txt에서 읽는다(둘 다 없으면 cysUML 그리기 도구 호출을 모두 센다).
"""
import json
import re
import sys
from pathlib import Path

from run_bench import draw_calls, draw_results, read_events, result_text

stream = Path(sys.argv[1])
events = read_events(stream.read_text(encoding="utf-8").splitlines())
row = stream.with_name("row.json")
tool = json.loads(row.read_text(encoding="utf-8")).get("tool") if row.exists() else None
if tool is None and stream.with_name("prompt.txt").exists():
    m = re.search(r"cysUML tool `(draw_\w+)`", stream.with_name("prompt.txt").read_text(encoding="utf-8"))
    tool = m.group(1) if m else None
if tool is None:
    print("알림: 이 실행의 도구를 알 수 없어 cysUML 그리기 도구 호출을 모두 그린 차례로 센다(results.csv의 draws와 다를 수 있다)")

for e in events:
    if e.get("type") == "system" and e.get("subtype") == "init":
        print("init:", {k: e.get(k) for k in ("apiKeySource", "model", "permissionMode")},
              "mcp:", e.get("mcp_servers"), "tools:", e.get("tools"))
ids = draw_calls(events, tool)
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
