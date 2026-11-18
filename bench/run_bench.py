"""모델별 배치 실력 측정 — 자리를 지운 문제(README 예시 그림과 problems_*.json)를 claude -p --bare로 풀게 하고, 합격 여부·그린 횟수·비용을 잰다.

쓰는 법(방법·결과는 bench/RESULTS.md):
  uv run python bench/run_bench.py --models claude-haiku-5-5 --problems order billing --runs 1
  uv run python bench/run_bench.py --models claude-sonnet-5-5 --efforts medium --problems hard --runs 3 --budget 3
API 키는 ANTHROPIC_API_KEY나 맥 키체인(BENCH_KEYCHAIN_SERVICE)에서 읽어 자식 프로세스 환경에만 넣는다.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "docs" / "images"
DEFAULT_OUT = Path.home() / "Documents" / "cysUML-bench-runs"
LAYOUT_KEYS = {"left", "top", "via", "width", "height", "name_side"}
MAX_DRAWS = 10

# 같은 그림의 한국어판·고친 판은 하나로 친다(fixed가 first-try의 합격판). 교류도(checkout)는 도구가 배치하니 뺀다.
PROBLEMS = {
    "order": "order",
    "classes": "fixed",
    "billing": "billing",
    "components": "components",
    "deployment": "deployment",
    "packages": "packages",
    "use-cases": "use-cases",
    "order-states": "order-states",
    "order-flow": "order-flow",
}

# 자리 없이 쓴 문제 묶음(README 예시만으로는 모델 차이가 안 보여서 더함). problems_<묶음>.json을 --problems <묶음>으로 고른다.
SETS = {"readme": list(PROBLEMS)}
WRITTEN: dict = {}
for _f in sorted(Path(__file__).parent.glob("problems_*.json")):
    _set = json.loads(_f.read_text(encoding="utf-8"))
    SETS[_f.stem.removeprefix("problems_")] = list(_set)
    WRITTEN.update(_set)

KIND = {
    "draw_class_diagram": "class",
    "draw_package_diagram": "package",
    "draw_component_diagram": "component",
    "draw_deployment_diagram": "deployment",
    "draw_use_case_diagram": "use case",
    "draw_state_diagram": "state",
    "draw_activity_diagram": "activity",
}


def strip_layout(x):
    if isinstance(x, dict):
        return {k: strip_layout(v) for k, v in x.items() if k not in LAYOUT_KEYS}
    if isinstance(x, list):
        return [strip_layout(v) for v in x]
    return x


def load_problem(pid: str) -> tuple[str, dict]:
    if pid in WRITTEN:
        data = dict(WRITTEN[pid])
        return data.pop("tool"), strip_layout(data)
    data = json.loads((EXAMPLES / f"{PROBLEMS[pid]}.cysuml.json").read_text(encoding="utf-8"))
    tool = data.pop("tool")
    for k in ("file_name", "scale"):
        data.pop(k, None)
    return tool, strip_layout(data)


def prompt_for(pid: str, tool: str, spec: dict) -> str:
    return (
        f"Draw this UML {KIND[tool]} diagram with the cysUML tool `{tool}`. Use file_name \"{pid}\".\n"
        "The elements and relations below have no positions — you choose every position "
        "(left/top, and bend points or sizes if they help).\n"
        "After each draw, read the check result. If it does not pass, fix the layout and draw again with the same "
        f"file_name. Stop as soon as a draw passes the check (its result starts with 합격), or after {MAX_DRAWS} draws.\n\n"
        "Elements and relations (JSON):\n" + json.dumps(spec, ensure_ascii=False, indent=1)
    )


def api_key() -> str:
    """ANTHROPIC_API_KEY가 있으면 그것을, 없으면 BENCH_KEYCHAIN_SERVICE로 지정한 맥 키체인 항목을 읽는다."""
    if key := os.environ.get("ANTHROPIC_API_KEY"):
        return key
    service = os.environ.get("BENCH_KEYCHAIN_SERVICE")
    if not service:
        sys.exit("API 키가 없다 — ANTHROPIC_API_KEY나 BENCH_KEYCHAIN_SERVICE(맥 키체인 서비스 이름)를 준다")
    return subprocess.run(["security", "find-generic-password", "-s", service, "-w"],
                          check=True, capture_output=True, text=True).stdout.strip()


def first_line(content) -> str:
    if isinstance(content, str):
        return content.strip().splitlines()[0] if content.strip() else ""
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text", "").strip()
            return text.splitlines()[0] if text else ""
    return ""


def verdict(line: str) -> str:
    if line.startswith("합격"):
        return "pass"
    if line.startswith("불합격"):
        return "fail"
    if line.startswith("입력 오류"):
        return "input_error"
    return "other"


def parse_stream(lines: list[str]) -> dict:
    draw_ids: list[str] = []
    verdicts: dict[str, str] = {}
    result: dict = {}
    for raw in lines:
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError:
            continue
        msg = ev.get("message") or {}
        if ev.get("type") == "assistant":
            for b in msg.get("content") or []:
                if b.get("type") == "tool_use" and str(b.get("name", "")).startswith("mcp__cysuml__draw_"):
                    draw_ids.append(b["id"])
        elif ev.get("type") == "user":
            for b in msg.get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in draw_ids:
                    verdicts[b["tool_use_id"]] = verdict(first_line(b.get("content")))
        elif ev.get("type") == "result":
            result = ev
    seq = [verdicts.get(i, "missing") for i in draw_ids]
    first_pass = next((n for n, v in enumerate(seq, 1) if v == "pass"), None)
    if first_pass is not None and first_pass > MAX_DRAWS:  # 지시한 최대 횟수를 넘겨 합격한 것은 불합격으로 친다
        first_pass = None
    usage = result.get("usage") or {}
    return {
        "draws": len(seq),
        "first_pass_draw": first_pass,
        "passed": first_pass is not None,
        "verdicts": " ".join(seq),
        "input_errors": seq.count("input_error"),
        "cost_usd": result.get("total_cost_usd"),
        "turns": result.get("num_turns"),
        "duration_s": round(result["duration_ms"] / 1000, 1) if result.get("duration_ms") is not None else None,
        "subtype": result.get("subtype"),
        "is_error": result.get("is_error"),
        "input_tokens": usage.get("input_tokens"),
        "cache_read_tokens": usage.get("cache_read_input_tokens"),
        "cache_write_tokens": usage.get("cache_creation_input_tokens"),
        "output_tokens": usage.get("output_tokens"),
    }


def _text(out) -> str:
    return out.decode("utf-8", "replace") if isinstance(out, bytes) else (out or "")


def run_one(job: dict, key: str) -> dict:
    run_dir: Path = job["dir"]
    run_dir.mkdir(parents=True, exist_ok=True)
    tool, spec = load_problem(job["problem"])
    prompt = prompt_for(job["problem"], tool, spec)
    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    mcp = {"mcpServers": {"cysuml": {"command": str(ROOT / ".venv" / "bin" / "cysuml")}}}
    cmd = [
        "claude", "-p", "--bare",
        "--model", job["model"], "--effort", job["effort"],
        "--tools", "",
        "--strict-mcp-config", "--mcp-config", json.dumps(mcp),
        "--allowedTools", f"mcp__cysuml__{tool}",
        "--output-format", "stream-json", "--verbose",
        "--max-turns", str(MAX_DRAWS + 4),
        "--max-budget-usd", str(job["budget"]),
        "--no-session-persistence",
        prompt,
    ]
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE_CODE_OAUTH"))}
    env["ANTHROPIC_API_KEY"] = key
    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=run_dir, env=env, capture_output=True, text=True, timeout=job["timeout"])
        stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:  # 시간 초과여도 그때까지의 기록은 남긴다(비용은 끝의 결과가 없어 비운다)
        stdout, stderr, code = _text(e.stdout), _text(e.stderr), None
    (run_dir / "stream.jsonl").write_text(stdout, encoding="utf-8")
    if stderr.strip():
        (run_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
    row = {"model": job["model"], "effort": job["effort"], "problem": job["problem"], "run": job["run"],
           "exit": code, "wall_s": round(time.time() - started, 1)}
    row.update(parse_stream(stdout.splitlines()))
    if code is None:
        row["subtype"] = "timeout"
    (run_dir / "row.json").write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding="utf-8")
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--efforts", nargs="+", default=["high"])
    ap.add_argument("--problems", nargs="+", default=["readme"], help="문제 이름이나 묶음(readme·hard·xl·xxl)")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--budget", type=float, default=5.0,
                    help="실행 한 번의 비용 상한(달러). bench/RESULTS.md의 표는 readme·hard $3, xl $5, xxl $4로 쟀다")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--tag", default=dt.datetime.now().strftime("%m%d-%H%M%S"))
    args = ap.parse_args()
    args.problems = list(dict.fromkeys(p for name in args.problems for p in SETS.get(name, [name])))
    unknown = [p for p in args.problems if p not in PROBLEMS and p not in WRITTEN]
    if unknown:
        sys.exit(f"모르는 문제: {unknown} (있는 것: {list(PROBLEMS) + list(WRITTEN)})")

    base = args.out / args.tag
    if (base / "results.csv").exists():
        sys.exit(f"이미 결과가 있는 태그다: {base} — --tag로 다른 이름을 준다")
    jobs = [{"model": m, "effort": e, "problem": p, "run": r, "budget": args.budget, "timeout": args.timeout,
             "dir": base / f"{m}_{e}" / p / f"run{r}"}
            for m in args.models for e in args.efforts for p in args.problems for r in range(1, args.runs + 1)]
    key = api_key()
    rows = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_one, j, key): j for j in jobs}
        for fut in cf.as_completed(futures):
            j = futures[fut]
            try:
                row = fut.result()
            except Exception as e:  # 한 실행이 죽어도 나머지는 계속 잰다
                row = {"model": j["model"], "effort": j["effort"], "problem": j["problem"], "run": j["run"],
                       "subtype": f"harness_error: {type(e).__name__}: {e}"}
            rows.append(row)
            print(json.dumps({k: row.get(k) for k in ("model", "effort", "problem", "run", "passed",
                                                       "first_pass_draw", "draws", "cost_usd", "duration_s",
                                                       "subtype")}, ensure_ascii=False), flush=True)
    base.mkdir(parents=True, exist_ok=True)
    fields = sorted({k for r in rows for k in r})
    with (base / "results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    total = sum(r.get("cost_usd") or 0 for r in rows)
    print(f"끝: {len(rows)}건, 합계 ${total:.2f}, 결과 {base / 'results.csv'}", flush=True)


if __name__ == "__main__":
    main()
