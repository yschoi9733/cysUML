"""실행 하나(stream.jsonl)의 인증 출처·모델별 토큰·그린 차례마다의 검사 결과 앞 세 줄을 보여 준다.

그린 차례를 세는 규칙과 결과 글을 꺼내는 법은 run_bench.py의 것을 그대로 쓴다.
"""
import json
import sys

from run_bench import DRAW_PREFIX, result_text

draws = {}
for line in open(sys.argv[1], encoding="utf-8"):
    try:
        e = json.loads(line)
    except json.JSONDecodeError:
        continue
    msg = e.get("message") or {}
    if e.get("type") == "system" and e.get("subtype") == "init":
        print("init:", {k: e.get(k) for k in ("apiKeySource", "model", "permissionMode")},
              "mcp:", e.get("mcp_servers"), "tools:", e.get("tools"))
    elif e.get("type") == "assistant":
        for b in msg.get("content") or []:
            if b.get("type") == "tool_use" and str(b.get("name", "")).startswith(DRAW_PREFIX):
                draws[b["id"]] = len(draws) + 1
    elif e.get("type") == "user":
        for b in msg.get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in draws:
                text = result_text(b.get("content"))
                print(f"draw {draws[b['tool_use_id']]}:", " / ".join(text.splitlines()[:3])[:300])
    elif e.get("type") == "result":
        keep = ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "costUSD")
        print("result:", e.get("subtype"), "turns", e.get("num_turns"), "cost", e.get("total_cost_usd"))
        for m, u in (e.get("modelUsage") or {}).items():
            print("  ", m, {k: u.get(k) for k in keep})
