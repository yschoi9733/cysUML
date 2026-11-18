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
import hashlib
import importlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "docs" / "images"
DEFAULT_OUT = Path.home() / "Documents" / "cysUML-bench-runs"
LAYOUT_KEYS = {"left", "top", "via", "width", "height", "name_side"}
MAX_DRAWS = 10
DRAW_PREFIX = "mcp__cysuml__draw_"  # 그린 차례로 세는 도구 호출(inspect_run.py도 이것을 쓴다)
FIELDS = ["model", "effort", "problem", "run", "tool", "passed", "first_pass_draw", "draws", "verdicts", "changed",
          "input_errors", "mcp",
          "cost_usd", "duration_s", "wall_s", "turns", "subtype", "is_error", "exit",
          "input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens"]

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
        + PROMPT_SPEC_MARK + json.dumps(spec, ensure_ascii=False, indent=1)
    )


PROMPT_SPEC_MARK = "Elements and relations (JSON):\n"  # 이 뒤가 문제 JSON이다(spec_from_prompt가 이것으로 꺼낸다)


def api_key() -> str:
    """ANTHROPIC_API_KEY가 있으면 그것을, 없으면 BENCH_KEYCHAIN_SERVICE로 지정한 맥 키체인 항목을 읽는다."""
    if key := os.environ.get("ANTHROPIC_API_KEY"):
        return key
    service = os.environ.get("BENCH_KEYCHAIN_SERVICE")
    if not service:
        sys.exit("API 키가 없다 — ANTHROPIC_API_KEY나 BENCH_KEYCHAIN_SERVICE(맥 키체인 서비스 이름)를 준다")
    try:
        return subprocess.run(["security", "find-generic-password", "-s", service, "-w"],
                              check=True, capture_output=True, text=True).stdout.strip()
    except FileNotFoundError:
        sys.exit("security 명령이 없다(맥 키체인은 macOS에서만 읽는다) — ANTHROPIC_API_KEY를 준다")
    except subprocess.CalledProcessError:
        sys.exit(f"맥 키체인에 서비스 이름이 {service!r}인 항목이 없다 — BENCH_KEYCHAIN_SERVICE를 확인한다")


def result_text(content) -> str:
    """tool_result 내용(문자열이나 블록 목록)에서 글을 꺼낸다."""
    if isinstance(content, str):
        return content.strip()
    return next((b.get("text", "").strip() for b in content or [] if isinstance(b, dict) and b.get("type") == "text"), "")


def first_line(content) -> str:
    text = result_text(content)
    return text.splitlines()[0] if text else ""


def verdict(line: str) -> str:
    if line.startswith("합격"):
        return "pass"
    if line.startswith("불합격"):
        return "fail"
    if line.startswith("입력 오류"):
        return "input_error"
    if line.startswith("그림이 너무 커서"):
        return "too_big"
    return "other"


TOOL_MODULE = {
    "draw_class_diagram": "classdiagram",
    "draw_package_diagram": "packagediagram",
    "draw_component_diagram": "componentdiagram",
    "draw_deployment_diagram": "deploymentdiagram",
    "draw_use_case_diagram": "usecasediagram",
    "draw_state_diagram": "statediagram",
    "draw_activity_diagram": "activitydiagram",
}
EMPTY = (None, "", [], {})  # 이 값인 칸은 빠진 칸과 같게 본다
REFINE_ROUNDS = 4  # 이름으로 못 가리키는 요소의 꼬리표를 이웃으로 다듬는 횟수


def tool_spec(tool: str):
    """cysUML이 그 도구에 쓰는 Spec. 기본값(요소 목록 칸·kind·navigable)을 손으로 옮겨 적지 않으려고 그대로 읽는다."""
    return importlib.import_module(f"cysuml.{TOOL_MODULE[tool]}").SPEC


def _text_key(v):
    """이름을 견줄 꼴로 바꾼다. 여러 줄 이름(줄마다 문자열인 목록)은 줄을 이어 붙이고, 공백은 지운다."""
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        v = "".join(v)
    return "".join(v.split()) if isinstance(v, str) else v


def _digest(x) -> str:
    return hashlib.sha1(json.dumps(x, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def _fields(d: dict, spec, default_kind: str | None, skip: set) -> dict:
    """요소·관계 하나에서 견줄 칸만 남긴다. 자리 칸·skip·빈 칸·기본값 칸(kind·navigable)은 빼고, 이름은 _text_key로."""
    out = {}
    for k, v in d.items():
        if (k in LAYOUT_KEYS or k in skip or v in EMPTY or (k == "kind" and v == default_kind)
                or (k == "navigable" and v == spec.navigable)):
            continue
        out[k] = _text_key(v) if k == "name" else v
    return out


def _shape(drawing: dict, tool: str) -> tuple[list, list]:
    """그림 입력을 견줄 꼴(요소 목록, 관계 목록)로 만든다. id는 쓰지 않는다 — 이름이 하나뿐인 요소는 이름으로 가리키고,
    이름 없는 점·마름모와 이름이 겹치는 요소는 이웃(들고 나는 관계, 담긴 곳, 담은 요소)으로 REFINE_ROUNDS번 다듬은
    꼬리표로 가리킨다. 그래서 id를 어떻게 바꿔 써도 같은 그림이면 같은 꼴이 나오고, 흐름을 바꿔 이으면 달라진다. 방향이 없는
    연관(navigable이 none이고 다중도가 없음)은 양 끝 차례를 보지 않는다."""
    s = tool_spec(tool)
    items = drawing.get(s.list_field) or []
    ref = {}
    for i, e in enumerate(items):
        for k in (e.get("id"), e.get("name") if isinstance(e.get("name"), str) else None):
            if k is not None:
                ref.setdefault(k, i)

    def end(k):  # 가리키는 요소의 번호, 모르는 열쇠면 그 열쇠 자체
        return ref.get(k, ("?", k))

    fields = [_fields(e, s, s.default_kind, {"id", "in"}) for e in items]
    parent = [end(e["in"]) if e.get("in") is not None else None for e in items]
    names = [_text_key(e["name"]) if e.get("name") else None for e in items]
    counts = Counter(n for n in names if n is not None)
    anchored = [n is not None and counts[n] == 1 for n in names]
    relations = []
    for r in drawing.get("relations") or []:
        undirected = (r.get("kind", s.default_relation) == "association" and r.get("navigable", s.navigable) == "none"
                      and not r.get("from_multiplicity") and not r.get("to_multiplicity"))
        relations.append((_fields(r, s, s.default_relation, {"from", "to"}), end(r.get("from")), end(r.get("to")),
                          undirected))

    labels = [f"name:{names[i]}" if anchored[i] else _digest(fields[i]) for i in range(len(items))]

    def label(x) -> str:
        return labels[x] if isinstance(x, int) else _digest(list(x))

    for _ in range(REFINE_ROUNDS):
        around = [[] for _ in items]
        for f, a, b, undirected in relations:
            if isinstance(a, int):
                around[a].append(["~" if undirected else ">", f, label(b)])
            if isinstance(b, int):
                around[b].append(["~" if undirected else "<", f, label(a)])
        for i, p in enumerate(parent):
            if p is not None:
                around[i].append(["in", {}, label(p)])
                if isinstance(p, int):
                    around[p].append(["holds", {}, labels[i]])
        labels = [labels[i] if anchored[i] else _digest([labels[i], sorted(_digest(x) for x in around[i])])
                  for i in range(len(items))]

    elements = sorted(_digest([label(i), fields[i], label(parent[i]) if parent[i] is not None else None])
                      for i in range(len(items)))
    rels = sorted(_digest([f, sorted([label(a), label(b)]) if undirected else [label(a), label(b)]])
                  for f, a, b, undirected in relations)
    return elements, rels


def faithful(drawn: dict, spec: dict, tool: str) -> bool:
    """그린 입력이 문제의 요소·관계를 빠짐없이, 더하거나 바꾸지 않고 담았는지(자리 칸·id·빈 칸·기본값 칸은 보지 않는다)."""
    return _shape(drawn, tool) == _shape(spec, tool)


def read_events(lines) -> list[dict]:
    """stream-json 출력의 줄들을 이벤트로 읽는다. JSON이 아닌 줄은 건너뛴다."""
    events = []
    for raw in lines:
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return events


def draw_uses(events: list[dict], tool: str | None = None) -> list[tuple[str, dict]]:
    """그린 차례대로 (tool_use id, 보낸 그림 입력)을 낸다. tool을 주면 그 문제의 도구 호출만(허락하지 않은 도구 호출은
    그린 것이 아니다), 안 주면 cysUML 그리기 도구 호출을 모두 센다."""
    uses = []
    for ev in events:
        if ev.get("type") != "assistant":
            continue
        for b in (ev.get("message") or {}).get("content") or []:
            name = str(b.get("name", ""))
            if b.get("type") == "tool_use" and (name == DRAW_PREFIX + tool.removeprefix("draw_") if tool
                                                else name.startswith(DRAW_PREFIX)):
                uses.append((b["id"], b.get("input") or {}))
    return uses


def draw_calls(events: list[dict], tool: str | None = None) -> list[str]:
    return [i for i, _ in draw_uses(events, tool)]


def mcp_status(events: list[dict]) -> str | None:
    """시작 이벤트에 적힌 cysUML MCP 서버 상태(connected 등). 서버가 안 붙으면 그린 차례가 0인 평범한 불합격처럼 보인다."""
    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), {})
    return next((m.get("status") for m in init.get("mcp_servers") or [] if m.get("name") == "cysuml"), None)


def spec_from_prompt(prompt: str) -> dict | None:
    """prompt.txt에서 그 실행에 실제로 준 문제(요소·관계 JSON)를 꺼낸다. rescore.py가 지금 문제 대신 이것과 견준다."""
    _, sep, tail = prompt.partition(PROMPT_SPEC_MARK)
    return json.loads(tail) if sep else None


def tool_from_prompt(prompt: str) -> str | None:
    """prompt.txt에서 그 실행의 도구 이름을 꺼낸다(row.json이 없는 옛 기록용, prompt_for의 첫 문장을 읽는다)."""
    m = re.search(r"cysUML tool `(draw_\w+)`", prompt)
    return m.group(1) if m else None


def finish_row(row: dict, timed_out: bool) -> dict:
    """parse_stream 뒤 실행 한 줄의 마무리(run_one과 rescore.py가 같이 쓴다)."""
    if timed_out:  # 비용은 끝의 결과가 없어 알 수 없고, 시간은 실제로 기다린 시간으로 채운다
        row["subtype"] = "timeout"
        row["duration_s"] = row.get("wall_s")
    elif row.get("mcp") != "connected":  # 그림 도구가 없던 실행은 모델의 불합격이 아니다
        row["subtype"] = f"mcp_failed: {row.get('mcp')}"
    return row


def draw_results(events: list[dict], ids: list[str]) -> dict[str, dict]:
    """tool_use id마다 그 tool_result 블록을 낸다."""
    wanted, found = set(ids), {}
    for ev in events:
        if ev.get("type") != "user":
            continue
        for b in (ev.get("message") or {}).get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in wanted:
                found[b["tool_use_id"]] = b
    return found


def counts_as_pass(first_pass: int | None) -> bool:
    """지시한 최대 횟수를 넘겨 합격한 것은 불합격으로 친다(summarize.py도 이것으로 가른다)."""
    return first_pass is not None and first_pass <= MAX_DRAWS


def parse_stream(lines, tool: str | None = None, spec: dict | None = None) -> dict:
    """spec(문제)을 주면, 검사에 합격했어도 문제를 바꿔 그린 차례(요소·관계를 빼거나 더하거나 바꿈)는 changed로 적고
    합격으로 치지 않는다."""
    events = read_events(lines)
    uses = draw_uses(events, tool)
    ids, inputs = [i for i, _ in uses], dict(uses)
    results = draw_results(events, ids)
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    seq = []
    for i in ids:
        v = verdict(first_line(results[i].get("content"))) if i in results else "missing"
        if v == "pass" and spec is not None and not faithful(inputs.get(i, {}), spec, tool):
            v = "changed"
        seq.append(v)
    first_pass = next((n for n, v in enumerate(seq, 1) if v == "pass"), None)
    usage = result.get("usage") or {}
    return {
        "draws": len(seq),
        "first_pass_draw": first_pass,
        "passed": counts_as_pass(first_pass),
        "verdicts": " ".join(seq),
        "input_errors": seq.count("input_error"),
        "changed": seq.count("changed"),
        "mcp": mcp_status(events),
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


_RUNNING: set[subprocess.Popen] = set()  # 멈출 때 직접 끝낼 claude 프로세스
_RUNNING_LOCK = threading.Lock()
_STOP = threading.Event()  # 멈춘 뒤에는 새 claude를 띄우지 않는다(_RUNNING_LOCK 안에서 보고 세운다)
# claude에 넘기는 환경 변수. 셸에 있는 Claude Code 설정(effort·생각 토큰·캐시·제공자 전환 등)이 측정에 섞이지 않게
# 이것만 넘긴다(프록시·인증서 변수는 API에 닿는 데 필요할 수 있어 넘긴다)
KEEP_ENV = {"PATH", "HOME", "USER", "LOGNAME", "SHELL", "TMPDIR", "TERM", "LANG",
            "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy",
            "NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "SSL_CERT_DIR"}


def stop_group(proc: subprocess.Popen, sig: int) -> None:
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        pass


def run_dir_for(base: Path, model: str, effort: str, problem: str, run) -> Path:
    """실행 하나의 기록 폴더(rescore.py도 이것으로 찾는다)."""
    return base / f"{model}_{effort}" / problem / f"run{run}"


def run_one(job: dict, key: str) -> dict:
    if _STOP.is_set():  # 멈춘 뒤에는 폴더도 건드리지 않는다
        raise RuntimeError("멈춘 뒤라 띄우지 않았다")
    run_dir: Path = job["dir"]
    if run_dir.exists():  # 멈췄던 실행의 옛 파일(stderr.txt·그림)이 새 기록 옆에 남지 않게 비우고 시작한다
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    tool, spec = load_problem(job["problem"])
    prompt = prompt_for(job["problem"], tool, spec)
    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    mcp = {"mcpServers": {"cysuml": {"command": str(ROOT / ".venv" / "bin" / "cysuml")}}}
    cmd = [
        "claude", "-p", "--bare",
        "--setting-sources", "",  # 사용자·프로젝트 설정 파일(env·model·permissions)도 측정에 섞이지 않게 읽지 않는다
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
    env = {k: v for k, v in os.environ.items() if k in KEEP_ENV or k.startswith("LC_")}
    env["ANTHROPIC_API_KEY"] = key
    started = time.time()
    with _RUNNING_LOCK:
        if _STOP.is_set():
            raise RuntimeError("멈춘 뒤라 띄우지 않았다")
        # 새 프로세스 그룹으로 띄워, 끝낼 때 claude가 띄운 MCP 서버(cysuml)까지 그룹째 끝낸다
        proc = subprocess.Popen(cmd, cwd=run_dir, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", start_new_session=True)
        _RUNNING.add(proc)
    try:
        stdout, stderr = proc.communicate(timeout=job["timeout"])
        code = proc.returncode
    except subprocess.TimeoutExpired:  # 시간 초과여도 그때까지의 기록은 남긴다(비용은 끝의 결과가 없어 비운다)
        stop_group(proc, signal.SIGKILL)
        try:
            stdout, stderr = proc.communicate(timeout=60)
        except subprocess.TimeoutExpired:  # 그룹 밖으로 나간 자손이 출력을 쥐고 있으면 끝내도 닫히지 않는다
            stdout, stderr = "", "끝낸 뒤에도 출력이 닫히지 않아 기록을 읽지 못했다"
        code = None
    finally:
        with _RUNNING_LOCK:
            _RUNNING.discard(proc)
    (run_dir / "stream.jsonl").write_text(stdout, encoding="utf-8")
    if stderr.strip():
        (run_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
    row = {"model": job["model"], "effort": job["effort"], "problem": job["problem"], "run": job["run"], "tool": tool,
           "exit": code, "wall_s": round(time.time() - started, 1)}
    row.update(parse_stream(stdout.splitlines(), tool, spec))
    finish_row(row, timed_out=code is None)
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
    args.models = list(dict.fromkeys(args.models))  # 겹치면 같은 실행 폴더를 두 실행이 함께 쓴다
    args.efforts = list(dict.fromkeys(args.efforts))
    unknown = [p for p in args.problems if p not in PROBLEMS and p not in WRITTEN]
    if unknown:
        sys.exit(f"모르는 문제: {unknown} (있는 것: {list(PROBLEMS) + list(WRITTEN)})")

    if not (ROOT / ".venv" / "bin" / "cysuml").exists():
        sys.exit(f"{ROOT / '.venv/bin/cysuml'}이 없다 — 레포에서 uv sync를 먼저 돌린다")
    base = args.out / args.tag
    if (base / "results.csv").exists():
        sys.exit(f"이미 결과가 있는 태그다: {base} — --tag로 다른 이름을 준다")
    jobs = [{"model": m, "effort": e, "problem": p, "run": r, "budget": args.budget, "timeout": args.timeout,
             "dir": run_dir_for(base, m, e, p, r)}
            for m in args.models for e in args.efforts for p in args.problems for r in range(1, args.runs + 1)]
    key = api_key()
    rows = []
    base.mkdir(parents=True, exist_ok=True)
    pool = cf.ThreadPoolExecutor(max_workers=args.workers)
    # 결과는 실행이 끝날 때마다 한 줄씩 써서, 중간에 멈춰도 끝난 실행은 남는다
    with (base / "results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        futures: dict = {}
        written = set()

        def record(fut) -> dict:
            written.add(fut)  # 쓰기 전에 표시해, 쓰는 도중 Ctrl-C가 와도 아래 정리에서 같은 줄을 두 번 쓰지 않는다
            j = futures[fut]
            try:
                row = fut.result()
            except Exception as e:  # 한 실행이 죽어도 나머지는 계속 잰다
                row = {"model": j["model"], "effort": j["effort"], "problem": j["problem"], "run": j["run"],
                       "subtype": f"harness_error: {type(e).__name__}: {e}"}
            rows.append(row)
            w.writerow(row)
            f.flush()
            return row

        try:  # 띄우기부터 정리까지 어디서 Ctrl-C가 와도 아래에서 멈춘다
            for j in jobs:
                futures[pool.submit(run_one, j, key)] = j
            for fut in cf.as_completed(futures):
                row = record(fut)
                print(json.dumps({k: row.get(k) for k in ("model", "effort", "problem", "run", "passed",
                                                           "first_pass_draw", "draws", "cost_usd", "duration_s",
                                                           "subtype")}, ensure_ascii=False), flush=True)
            pool.shutdown()
        except KeyboardInterrupt:  # 남은 실행은 띄우지 않고, 돌던 claude도 직접 끝낸다(SIGINT가 파이썬에만 왔을 수 있다)
            finished = [fut for fut in futures if fut.done() and not fut.cancelled() and fut not in written]
            with _RUNNING_LOCK:
                _STOP.set()
                procs = list(_RUNNING)
            for p in procs:
                stop_group(p, signal.SIGTERM)
            pool.shutdown(wait=False, cancel_futures=True)
            deadline = time.time() + 10  # SIGTERM을 무시하는 그룹은 10초 뒤 SIGKILL로 끝낸다
            while time.time() < deadline and any(p.poll() is None for p in procs):
                time.sleep(0.2)
            for p in procs:
                if p.poll() is None:
                    stop_group(p, signal.SIGKILL)
            for fut in finished:  # 멈추기 전에 이미 끝났는데 아직 쓰지 못한 실행만 남긴다(끊긴 실행은 쓰지 않는다)
                record(fut)
            sys.exit(f"멈췄다: 끝난 {len(rows)}건은 {base / 'results.csv'}에 있다(돌던 실행은 끝냈고 CSV에 들지 않는다)")
    total = sum(r.get("cost_usd") or 0 for r in rows)
    unknown_cost = sum(1 for r in rows if r.get("cost_usd") is None)
    note = f", 비용을 모르는 실행 {unknown_cost}건은 합계에 들지 않았다" if unknown_cost else ""
    print(f"끝: {len(rows)}건, 합계 ${total:.2f}{note}, 결과 {base / 'results.csv'}", flush=True)


if __name__ == "__main__":
    main()
