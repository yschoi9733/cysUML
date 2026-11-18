"""실행 하나(stream.jsonl)의 인증 출처·모델별 토큰·그린 차례마다의 검사 결과 앞 세 줄을 보여 준다."""
import json
import sys

draws = {}
for line in open(sys.argv[1], encoding="utf-8"):
    e = json.loads(line)
    msg = e.get("message") or {}
    if e.get("type") == "system" and e.get("subtype") == "init":
        print("init:", {k: e.get(k) for k in ("apiKeySource", "model", "permissionMode")},
              "mcp:", e.get("mcp_servers"), "tools:", e.get("tools"))
    elif e.get("type") == "assistant":
        for b in msg.get("content") or []:
            if b.get("type") == "tool_use":
                draws[b["id"]] = len(draws) + 1
    elif e.get("type") == "user":
        for b in msg.get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in draws:
                c = b.get("content")
                text = c if isinstance(c, str) else next((x.get("text", "") for x in c or [] if x.get("type") == "text"), "")
                print(f"draw {draws[b['tool_use_id']]}:", " / ".join(text.strip().splitlines()[:3])[:300])
    elif e.get("type") == "result":
        keep = ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "costUSD")
        print("result:", e.get("subtype"), "turns", e.get("num_turns"), "cost", e.get("total_cost_usd"))
        for m, u in (e.get("modelUsage") or {}).items():
            print("  ", m, {k: u.get(k) for k in keep})
