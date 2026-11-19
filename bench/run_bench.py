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
import itertools
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

from cysuml import boxdiagram as B
from cysuml.parsing import InputError
from cysuml.report import Report

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "docs" / "images"
DEFAULT_OUT = Path.home() / "Documents" / "cysUML-bench-runs"
LAYOUT_KEYS = {"left", "top", "via", "width", "height", "name_side"}
MAX_DRAWS = 10
DRAW_PREFIX = "mcp__cysuml__draw_"
FIELDS = ["model", "effort", "problem", "run", "tool", "passed", "first_pass_draw", "draws", "verdicts", "changed",
          "input_errors", "save_errors", "mcp", "api_status", "error",
          "cost_usd", "duration_s", "wall_s", "turns", "subtype", "is_error", "exit", "timed_out",
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
    if set(_set) & (set(WRITTEN) | set(PROBLEMS)):
        raise SystemExit(f"{_f.name}의 문제 이름이 다른 문제와 겹친다: {sorted(set(_set) & (set(WRITTEN) | set(PROBLEMS)))}")
    WRITTEN.update(_set)
if set(SETS) & (set(WRITTEN) | set(PROBLEMS)):  # --problems는 묶음 이름을 먼저 풀어, 겹치면 그 문제를 따로 못 고른다
    raise SystemExit(f"묶음 이름과 문제 이름이 겹친다: {sorted(set(SETS) & (set(WRITTEN) | set(PROBLEMS)))}")

def diagram_kind(tool: str) -> str:
    return tool.removeprefix("draw_").removesuffix("_diagram").replace("_", " ")


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


PROMPT_SPEC_MARK = "Elements and relations (JSON):\n"  # 이 뒤가 문제 JSON이다(spec_from_prompt가 이것으로 꺼낸다)


def prompt_for(pid: str, tool: str, spec: dict) -> str:
    return (
        f"Draw this UML {diagram_kind(tool)} diagram with the cysUML tool `{tool}`. Use file_name \"{pid}\".\n"
        "The elements and relations below have no positions — you choose every position "
        "(left/top, and bend points or sizes if they help).\n"
        "After each draw, read the check result. If it does not pass, fix the layout and draw again with the same "
        f"file_name. Stop as soon as a draw passes the check (its result starts with 합격), or after {MAX_DRAWS} draws.\n\n"
        + PROMPT_SPEC_MARK + json.dumps(spec, ensure_ascii=False, indent=1)
    )


def api_key() -> str:
    """ANTHROPIC_API_KEY가 있으면 그것을, 없으면 BENCH_KEYCHAIN_SERVICE로 지정한 맥 키체인 항목을 읽는다."""
    if key := os.environ.get("ANTHROPIC_API_KEY"):
        return key
    service = os.environ.get("BENCH_KEYCHAIN_SERVICE")
    if not service:
        sys.exit("API 키가 없다 — ANTHROPIC_API_KEY나 BENCH_KEYCHAIN_SERVICE(맥 키체인 서비스 이름)를 준다")
    try:
        key = subprocess.run(["security", "find-generic-password", "-s", service, "-w"],
                             check=True, capture_output=True, text=True).stdout.strip()
    except FileNotFoundError:
        sys.exit("security 명령이 없다(맥 키체인은 macOS에서만 읽는다) — ANTHROPIC_API_KEY를 준다")
    except subprocess.CalledProcessError:
        sys.exit(f"맥 키체인에 서비스 이름이 {service!r}인 항목이 없다 — BENCH_KEYCHAIN_SERVICE를 확인한다")
    if not key:
        sys.exit(f"맥 키체인 항목 {service!r}의 값이 비어 있다")
    return key


def result_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    return next((b.get("text", "").strip() for b in content or [] if isinstance(b, dict) and b.get("type") == "text"), "")


def verdict_of(text: str) -> str:
    """판정 머리로 시작하는 첫 줄로 가른다."""
    return next((v for v in map(verdict, text.splitlines()) if v != "other"), "other")


def verdict(line: str) -> str:
    if line.startswith(Report.PASSED):  # 그림마다 다른 합격 문구가 모두 이것으로 시작한다
        return "pass"
    if line.startswith("불합격"):
        return "fail"
    if line.startswith("입력 오류"):
        return "input_error"
    if line.startswith("그림이 너무 커서"):
        return "too_big"
    return "other"


_PARSE_LOCK = threading.Lock()


def tool_module(tool: str):
    return importlib.import_module("cysuml." + tool.removeprefix("draw_").replace("_", ""))


def _name_forms(lines: tuple[str, ...]) -> list[str]:
    """이름 줄을 잇는 꼴들: 줄 바꿈 자리마다 띄어쓰기 하나로 잇거나 붙여 잇는다(이어진 공백은 하나로). 첫째는 모두 띄운
    꼴이다. 줄이 아주 많으면 모두 띄운 꼴과 모두 붙인 꼴만 본다."""
    if not lines:
        return [""]
    breaks = len(lines) - 1
    combos = itertools.product((" ", ""), repeat=breaks) if breaks <= 6 else [(" ",) * breaks, ("",) * breaks]
    forms = []
    for seps in combos:
        form = " ".join((lines[0] + "".join(sep + line for sep, line in zip(seps, lines[1:]))).split())
        if form not in forms:
            forms.append(form)
    return forms


def _known_names(d: B.Diagram) -> dict[str, str]:
    """문제의 이름마다 견줄 열쇠. 여러 줄 이름은 줄 바꿈 자리를 붙여 이은 꼴로도 찾는다(긴 한 단어를 줄로 나눈 것일 수 있다)."""
    forms = [_name_forms(x.name) for x in (*d.boxes, *d.relations) if x.name]
    known = {f[0]: f[0] for f in forms}
    for f in forms:
        for other in f[1:]:
            known.setdefault(other, f[0])
    return known


def _name_key(lines: tuple[str, ...], known: dict[str, str]) -> str:
    """이름 줄을 견줄 꼴로. 줄 바꿈 자리는 문제·그림 어느 쪽에서든 띄어쓰기로도, 붙여 쓴 것으로도 본다(줄을 어디서 나눴든
    같은 이름이다). 'Order Service'와 'OrderService'처럼 띄어쓰기를 더하거나 뺀 것은 다른 이름이다(이어진 공백은 하나로,
    앞뒤 공백은 없는 것으로 본다)."""
    forms = _name_forms(lines)
    return next((known[f] for f in forms if f in known), forms[0])


def _digest(x) -> str:
    return hashlib.sha1(json.dumps(x, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def _diagram(data: dict, tool: str) -> B.Diagram:
    """cysUML이 그 입력을 읽은 모델. 요소 열쇠(id·이름)와 kind·navigable 기본값을 cysUML이 그대로 풀게 한다. 자리가 없는 문제
    입력도 읽히도록 빠진 left·top과 자기 자신으로 가는 관계의 꺾는 점을 채운다(자리는 견주지 않는다). 도구 입력에는 그림 밖의
    인자(file_name 등)도 있어 요소 목록과 관계만 넘긴다. 목록을 JSON 글로 보낸 것은 풀어 읽고, 꼴이 틀린 입력은 cysUML이
    InputError로 거절하게 그대로 넘긴다."""
    s = tool_module(tool).SPEC

    def listed(v):
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except json.JSONDecodeError:
                return v
        return v if v is not None else []

    items, rels = listed(data.get(s.list_field)), listed(data.get("relations"))
    if isinstance(items, list):
        items = [{"left": 0, "top": 0, **e} if isinstance(e, dict) else e for e in items]
    if isinstance(rels, list):  # 자기 자신으로 가는 관계는 꺾는 점이 둘 있어야 읽힌다(from·to는 요소의 열쇠 하나로만 가리킨다)
        rels = [{"via": [[0, 0], [1, 1]], **r} if isinstance(r, dict) and r.get("from") == r.get("to") else r
                for r in rels]
    with _PARSE_LOCK:  # parse는 글자 폭을 재려고 공유 글꼴 객체를 쓴다(서버도 그리기를 한 번에 하나씩 한다)
        return tool_module(tool).parse({s.list_field: items, "relations": rels})


def _refine(d: B.Diagram, known: dict[str, str]):
    """대조가 쓰는 꼬리표를 만든다. 이름이 하나뿐인 요소는 이름으로 가리키고(anchored), 이름 없는 점·마름모와 이름이 겹치는
    요소는 이웃(들고 나는 관계, 담긴 곳, 담은 요소)으로 더 갈라지지 않을 때까지 다듬은 꼬리표로 가리킨다. 양 끝 모양이
    고정되지 않은 관계(연관)는 양 끝을 바꾸고 다중도·navigable도 맞바꿔 적어도 같은 그림이라 두 방향을 함께 본다."""
    s = d.spec
    boxes = d.boxes
    index = {e.key: i for i, e in enumerate(boxes)}
    names = [_name_key(e.name, known) if e.name else None for e in boxes]
    counts = Counter(n for n in names if n)
    anchored = [n is not None and counts[n] == 1 for n in names]
    own = [[e.kind, names[i], e.stereotype or None, repr(e.data)] for i, e in enumerate(boxes)]
    parent = [index[e.parent] if e.parent is not None else None for e in boxes]
    flip = {"to": "from", "from": "to"}
    rels = []
    for r in d.relations:
        t = s.relations[r.kind]
        fwd = [r.kind, _name_key(r.name, known), r.stereotype or None, r.source_multiplicity, r.target_multiplicity,
               r.navigable]
        rev = fwd[:3] + [r.target_multiplicity, r.source_multiplicity, flip.get(r.navigable, r.navigable)]
        free = t.navigable and t.start is None and t.end is None
        rels.append((fwd, rev if free else None, index[r.source], index[r.target]))

    labels = [f"name:{names[i]}" if anchored[i] else _digest(own[i]) for i in range(len(boxes))]
    for _ in range(len(boxes)):
        around = [[] for _ in boxes]
        for fwd, rev, a, b in rels:
            around[a].append(["~" if rev else ">", fwd, labels[b]])
            around[b].append(["~", rev, labels[a]] if rev else ["<", fwd, labels[a]])
        for i, p in enumerate(parent):
            if p is not None:
                around[i].append(["in", labels[p]])
                around[p].append(["holds", labels[i]])
        new = [labels[i] if anchored[i] else _digest([labels[i], sorted(_digest(x) for x in around[i])])
               for i in range(len(boxes))]
        if len(set(new)) == len(set(labels)):  # 더 갈라지지 않는다
            break
        labels = new
    return labels, anchored, own, parent, rels


def _digests(refined: tuple) -> tuple[list, list]:
    labels, _, own, parent, rels = refined
    elements = sorted(_digest([labels[i], own[i], labels[parent[i]] if parent[i] is not None else None])
                      for i in range(len(labels)))
    relations = sorted(min(_digest([fwd, labels[a], labels[b]]), _digest([rev, labels[b], labels[a]])) if rev
                       else _digest([fwd, labels[a], labels[b]]) for fwd, rev, a, b in rels)
    return elements, relations

def faithful(drawn: dict, spec: dict, tool: str) -> bool:
    """그린 입력이 문제의 요소·관계를 빠짐없이, 더하거나 바꾸지 않고 담았는지(자리 칸·id는 보지 않는다). cysUML이 읽지 못하는
    입력은 문제와 같다고 볼 수 없다."""
    known, want = problem_shape(spec, tool)
    try:
        drawn_d = _diagram(drawn, tool)
        return _digests(_refine(drawn_d, known)) == want
    except InputError:
        return False


PREPARED: dict[str, tuple] = {}  # main이 미리 읽은 문제별 (도구, 문제)
_SHAPES: dict[str, tuple] = {}


def blind_spots(spec: dict, tool: str) -> list[str]:
    """이름으로 가리킬 수 없는 요소 가운데 대조가 매긴 꼬리표(_refine)가 다른 요소와 겹치는 것. 겹치면 대조가 그 요소들을
    서로 가르지 못해, 대칭으로 바꿔 이은 그림을 놓칠 수 있다(서로 바꿔도 같은 그림인 요소도 함께 걸린다)."""
    d, _, refined, _ = _problem_parts(spec, tool)
    labels, anchored = refined[:2]
    counts = Counter(labels)
    return [e.key for e, label, fixed in zip(d.boxes, labels, anchored) if not fixed and counts[label] > 1]


def problem_shape(spec: dict, tool: str) -> tuple[dict[str, str], tuple[list, list]]:
    """문제의 이름 열쇠와 견줄 꼴(같은 문제는 한 번만 만든다). cysUML이 못 읽는 문제는 InputError."""
    _, known, _, shape = _problem_parts(spec, tool)
    return known, shape


def _problem_parts(spec: dict, tool: str) -> tuple:
    """문제를 한 번만 읽어 (그림, 이름 열쇠, 꼬리표, 견줄 꼴)을 둔다(problem_shape와 blind_spots가 같이 쓴다)."""
    k = json.dumps([tool, spec], sort_keys=True, ensure_ascii=False)
    if k not in _SHAPES:
        d = _diagram(spec, tool)
        known = _known_names(d)
        refined = _refine(d, known)
        _SHAPES[k] = d, known, refined, _digests(refined)
    return _SHAPES[k]


def read_events(lines) -> list[dict]:
    events = []
    for raw in lines:
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(ev, dict):  # 감싼 도구가 찍은 null·숫자 줄 등은 이벤트가 아니다
            events.append(ev)
    return events


def draw_uses(events: list[dict], tool: str | None = None) -> list[tuple[str, dict]]:
    """그린 차례대로 (tool_use id, 보낸 그림 입력)을 낸다. tool을 주면 그 문제의 도구 호출만(허락하지 않은 도구 호출은
    그린 것이 아니다), 안 주면 cysUML 그리기 도구 호출을 모두 센다."""
    uses = []
    for ev in events:
        if ev.get("type") != "assistant":
            continue
        for b in (ev.get("message") or {}).get("content") or []:
            if not isinstance(b, dict):
                continue
            name = str(b.get("name", ""))
            if b.get("type") == "tool_use" and (name == DRAW_PREFIX + tool.removeprefix("draw_") if tool
                                                else name.startswith(DRAW_PREFIX)):
                uses.append((b["id"], b.get("input") or {}))
    return uses


def init_event(events: list[dict]) -> dict:
    return next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), {})


def mcp_status(events: list[dict]) -> str | None:
    """시작 이벤트에 적힌 cysUML MCP 서버 상태(connected 등). 서버가 안 붙으면 그린 차례가 0인 평범한 불합격처럼 보인다."""
    init = init_event(events)
    if not init:
        return None
    return next((m.get("status") for m in init.get("mcp_servers") or [] if m.get("name") == "cysuml"), "missing")


def spec_from_prompt(prompt: str) -> dict | None:
    """prompt.txt에서 그 실행에 실제로 준 문제(요소·관계 JSON)를 꺼낸다. rescore.py가 지금 문제 대신 이것과 견준다."""
    _, sep, tail = prompt.partition(PROMPT_SPEC_MARK)
    try:
        return json.loads(tail) if sep else None
    except json.JSONDecodeError:  # 잘렸거나 뒤에 다른 글이 붙은 기록
        return None


def tool_from_prompt(prompt: str) -> str | None:
    m = re.search(r"cysUML tool `(draw_\w+)`", prompt)  # prompt_for의 첫 문장
    return m.group(1) if m else None


def run_tool(run_dir: Path, fallback: str | None = None) -> str | None:
    prompt, row = run_dir / "prompt.txt", run_dir / "row.json"
    tool = tool_from_prompt(prompt.read_text(encoding="utf-8")) if prompt.exists() else None
    if tool is None and row.exists():
        tool = json.loads(row.read_text(encoding="utf-8")).get("tool")
    return tool or fallback


# 모델을 잰 것이 아닌 실행의 subtype 머리(summarize.py가 표에서 뺀다): MCP 서버가 안 붙음, claude가 시작하지 못함,
# 모델이 한 번도 답하지 않은 채 시간이 다 감, 서버 쪽 API 오류, 끝의 결과 없이 끝남(크래시 등), 하네스 오류, 멈출 때 끊김
SDK_VALIDATION = re.compile(r"validation errors? for \w+Arguments")  # MCP SDK가 인자를 거절한 글(pydantic)
NOT_MEASURED = ("mcp_failed", "no_init", "no_answer", "api_error", "no_result", "tool_error", "harness_error", "stopped")
NATURAL_ENDS = ("success", "error_max_budget_usd", "error_max_turns")  # claude가 스스로 끝낸 결과 이벤트의 subtype
BILLING = re.compile(r"credit balance", re.I)  # 크레딧이 떨어지면 400 "Your credit balance is too low"로 온다
ABORTED = re.compile(r"\babort", re.I)  # 신호를 받은 claude가 결과에 담는 중단 글(Request was aborted)
OUTAGE = re.compile(r"Connection error|Request timed out|overloaded", re.I)  # 상태 번호 없이 오는 서버 쪽 오류 글


def _api_code(row: dict) -> int | None:
    """API 오류의 상태 번호. api_error_status가 없으면 오류 글의 'API Error: NNN'이나 알려진 안내 글에서 읽는다."""
    try:
        return int(row["api_status"])
    except (TypeError, ValueError, KeyError):
        error = row.get("error") or ""
        m = re.search(r"API Error: (\d{3})", error)
        if m:
            return int(m.group(1))
        # 상태 번호 없이 CLI가 바꿔 쓴 안내 글만 올 때
        return 401 if re.search(r"invalid api key", error, re.I) else 404 if re.search(
            r"issue with the selected model", error, re.I) else None


def config_error(row: dict) -> str | None:
    """남은 실행도 같은 오류로 끝날 원인: billing(크레딧 부족)·key(401)는 모든 모델, model(404)은 그 모델만,
    forbidden(403)은 그 모델만인지 키·조직 전체인지 오류만으로 가를 수 없어 record가 겪은 대로 정한다."""
    if not row.get("is_error") or row.get("passed"):
        return None
    if BILLING.search(row.get("error") or ""):
        return "billing"
    code = _api_code(row)
    return "key" if code == 401 else "model" if code == 404 else "forbidden" if code == 403 else None


def server_side(row: dict) -> bool:
    """서버 쪽 API 오류(설정 오류·429·5xx·연결)로 끝났는지. 그 밖의 400(글이 너무 길어짐 등)은 모델 탓이라 넣지 않는다."""
    if not row["is_error"]:
        return False
    code = _api_code(row)
    return (config_error(row) is not None or code == 429 or (code is not None and code >= 500)
            or (code is None and bool(OUTAGE.search(row["error"] or ""))))


def is_measured(subtype) -> bool:
    """모델을 잰 실행인지(summarize.py가 표에 넣고 rescore.py가 바뀐 것을 알린다)."""
    return not (subtype or "").startswith(NOT_MEASURED)


class Stopped(Exception):
    """Ctrl-C로 멈출 때 띄우지 않았거나 끝낸 실행. CSV에 쓰지 않는다."""


def build_row(meta: dict, lines, tool: str, spec: dict, timed_out: bool) -> dict:
    """실행 한 줄(run_one과 rescore.py가 같이 쓴다)."""
    row = {k: meta.get(k) for k in ("model", "effort", "problem", "run")} | {"tool": tool, "exit": meta.get("exit"),
                                                                          "wall_s": meta.get("wall_s")}
    row.update(parse_stream(lines, tool, spec))
    timed_out = timed_out and row["ended"] is None  # 끝의 결과를 내고 종료만 못 했으면 그 결과(시간·비용)를 쓴다
    row["timed_out"] = timed_out
    if timed_out:  # 비용은 끝의 결과가 없어 알 수 없고, 시간은 실제로 기다린 시간으로 채운다
        row["duration_s"] = row["wall_s"]
    seq = row["verdicts"].split()
    last = (seq or [""])[-1]
    server = server_side(row)
    # 결과가 정해졌다: 합격했거나, 지시한 10번을 다 그려 10번째까지 답을 받았다(고장 난 호출도 그린 횟수에 든다 — 첫 합격
    # 차례와 같은 셈). 10번째가 답을 기다리던 중이면 아직 정해지지 않았다
    used_up = len(seq) >= MAX_DRAWS and seq[MAX_DRAWS - 1] != "missing"
    if row["passed"] or used_up:
        why = "timeout" if timed_out else None
    # 그 밖은 결과가 정해지기 전에 끝났다. 누가 끝냈는지를 차례로 본다
    elif meta.get("signaled") and not timed_out and not server and (
            row["ended"] not in NATURAL_ENDS or bool(ABORTED.search(row["error"] or ""))):
        # 멈추며 우리가 신호로 끊었다. 신호를 받고 낸 결과 이벤트(중단 글을 담은 success 포함)는 스스로 끝난 것이 아니다.
        # 서버 쪽 API 오류는 신호와 상관없이 난 것이라 아래에서 api_error로 가른다
        why = "stopped"
    elif server:  # 서버 쪽 API 오류로 끝났다(결과 이벤트의 subtype과 상관없이, MCP가 붙기 전이어도)
        why = "api_error"
    elif not row["draws"] and not row["tool_ready"]:  # 그림 도구 없이 끝났다
        why = (f"mcp_failed: {row['mcp']}" if row["mcp"] else "no_init") + (" (timeout)" if timed_out else "")
    elif last in ("mcp_error", "tool_error"):  # 그리는 도중 MCP 서버가 끊기거나 cysUML 도구가 예외를 내 그 차례로 끝났다
        why = ("mcp_failed: during run" if last == "mcp_error" else "tool_error") + (" (timeout)" if timed_out else "")
    elif timed_out:  # 그리기 전이면 API가 멈춘 것과 가를 수 없어 빼고, 한 번이라도 그렸으면 모델의 불합격으로 센다
        why = "timeout" if row["draws"] else "no_answer (timeout)"
    elif row["ended"] in NATURAL_ENDS:  # claude가 스스로 끝냈다: 모델이 끝낸 것이다
        why = None
    else:  # 끝의 결과 없이, 또는 claude 안의 오류로 끝났다(크래시) — 종료 코드는 0일 수도 있다
        why = "no_result"
    if why is not None:
        row["subtype"] = why
    return row


def draw_results(events: list[dict], ids: list[str]) -> dict[str, dict]:
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
    seq, save_errors = [], 0
    for i in ids:
        text = result_text(results[i].get("content")) if i in results else ""
        v = verdict_of(text) if i in results else "missing"
        if v == "other" and results[i].get("is_error"):
            # MCP 서버가 죽거나 요청 시간이 넘었다(mcp_error), SDK가 인자를 거절했다(input_error, 모델 탓), 도구가 예외를
            # 냈다(tool_error, cysUML 탓)
            v = ("mcp_error" if text.startswith("MCP error") else "input_error" if SDK_VALIDATION.search(text)
                 else "tool_error")
        # 저장에 실패하면 서버는 오류 결과에 검사 요약을 붙인다. 판정은 요약으로 하되, 모델은 결과가 합격으로 시작하지 않아
        # 계속 그릴 수 있어 summarize.py가 알리게 센다
        save_errors += v == "pass" and bool(results[i].get("is_error"))
        if v == "pass" and spec is not None:
            if not faithful(inputs.get(i, {}), spec, tool):
                v = "changed"
        seq.append(v)
    # 몇 번째 그리기에서 처음 합격했나(프롬프트의 10번은 고장 난 호출까지 센 그리기 횟수다)
    first_pass = next((n for n, v in enumerate(seq, 1) if v == "pass"), None)
    usage = result.get("usage") or {}
    mcp, init_tools = mcp_status(events), init_event(events).get("tools") or []
    return {
        "draws": len(seq),
        "first_pass_draw": first_pass,
        "passed": counts_as_pass(first_pass),
        "verdicts": " ".join(seq),
        "input_errors": seq.count("input_error"),
        "changed": seq.count("changed"),
        "save_errors": save_errors,
        "mcp": mcp,
        "cost_usd": result.get("total_cost_usd"),
        "turns": result.get("num_turns"),
        "duration_s": round(result["duration_ms"] / 1000, 1) if result.get("duration_ms") is not None else None,
        "subtype": result.get("subtype"),
        "ended": result.get("subtype"),  # build_row가 subtype을 바꿔도 남는다
        # 그 문제의 그리기 도구를 쓸 수 있었는지(init의 도구 목록). MCP 상태가 pending이어도 도구가 있으면 모델이 판단한 것이다
        "tool_ready": mcp == "connected" or (bool(tool) and DRAW_PREFIX + tool.removeprefix("draw_") in init_tools),
        "is_error": result.get("is_error"),
        "api_status": result.get("api_error_status"),
        "error": (str(result.get("result") or result.get("errors") or "") or None) if result.get("is_error") else None,
        "input_tokens": usage.get("input_tokens"),
        "cache_read_tokens": usage.get("cache_read_input_tokens"),
        "cache_write_tokens": usage.get("cache_creation_input_tokens"),
        "output_tokens": usage.get("output_tokens"),
    }


_RUNNING: set[subprocess.Popen] = set()
_RUNNING_LOCK = threading.RLock()  # force_exit가 이 잠금을 쥔 메인 스레드에서 불려도 막히지 않게
_STOP = threading.Event()  # 멈춘 뒤에는 새 claude를 띄우지 않는다(_RUNNING_LOCK 안에서 보고 세운다)
_SIGNALED: set[int] = set()  # _RUNNING_LOCK 안에서 넣는다
_MEMBERS: dict[int, list[int]] = {}  # 멈출 때 기억한 그룹별 구성원(force_exit도 쓴다)
# claude에 넘기는 환경 변수. 셸에 있는 Claude Code 설정(effort·생각 토큰·캐시·제공자 전환 등)이 측정에 섞이지 않게
# 이것만 넘긴다(프록시·인증서 변수는 API에 닿는 데 필요할 수 있어 넘긴다)
KEEP_ENV = {"PATH", "HOME", "USER", "LOGNAME", "SHELL", "TMPDIR", "TERM", "LANG",
            "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy",
            "NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "SSL_CERT_DIR"}


STOP_SIGNALS = tuple(getattr(signal, n) for n in ("SIGINT", "SIGTERM", "SIGHUP") if hasattr(signal, n))  # Windows엔 SIGHUP이 없다


def kill_groups(procs) -> None:
    """SIGKILL을 아직 거두지 않은 claude의 그룹과, 멈출 때 기억한 구성원 가운데 아직 그 그룹에 남은 것에만 보낸다."""
    for p in procs:
        stop_group(p, signal.SIGKILL)
    for pgid, pids in list(_MEMBERS.items()):
        for pid in pids:
            kill_if_member(pid, pgid)


def force_exit(signum, frame) -> None:
    """정리 중에 신호가 한 번 더 오면 돌던 claude와 기억한 그룹 구성원을 바로 끝내고 나간다(정리가 막혔을 때의 탈출구)."""
    # 막 띄우는 중인 claude도 목록에 든 뒤에 보도록 잠금을 잡고, 그 뒤로는 새로 띄우지 않게 한다
    _STOP.set()  # 잠금을 기다리는 동안 새 claude를 띄우지 않게 먼저 세운다
    locked = _RUNNING_LOCK.acquire(timeout=30)
    procs = list(_RUNNING)
    if locked:
        _RUNNING_LOCK.release()
    kill_groups(procs)
    try:  # print는 신호가 끊은 출력과 겹치면 RuntimeError를 낸다
        os.write(2, "정리를 기다리지 않고 바로 끝냈다(돌던 claude는 끝냈다)\n".encode("utf-8"))
    except OSError:
        pass
    os._exit(1)


def restore_stop_signals(previous: dict) -> None:
    for s, handler in previous.items():  # 파이썬 밖에서 걸린 처리기(None)는 기본값으로 둔다
        signal.signal(s, handler if handler is not None
                      else signal.default_int_handler if s == signal.SIGINT else signal.SIG_DFL)


def _parent_name() -> str:
    try:
        return subprocess.run(["ps", "-o", "comm=", "-p", str(os.getppid())], capture_output=True,
                              text=True).stdout.strip()
    except FileNotFoundError:
        return ""


def say(text: str, file=None) -> None:
    try:
        print(text, file=file or sys.stdout, flush=True)
    except (OSError, RuntimeError):  # 터미널이 닫혔거나 신호가 끊은 출력과 겹쳐도 정리는 이어 간다
        pass


def group_members(pgids) -> dict[int, list[int]]:
    """그룹마다 구성원 pid(ps 한 번으로 읽는다). 그룹을 이끄는 claude는 stop_group이 맡는다(거둔 뒤의 그 pid는 그룹 번호와
    같아 재사용되면 가를 수 없다)."""
    members = {g: [] for g in pgids}
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,pgid="], capture_output=True, text=True).stdout
    except FileNotFoundError:  # ps가 없으면 그룹째 보내는 SIGTERM에만 기댄다
        return members
    for line in out.splitlines():
        pid, pgid = (int(x) for x in line.split())
        if pgid in members and pid != pgid:
            members[pgid].append(pid)
    return members


def kill_if_member(pid: int, pgid: int) -> None:
    """pid가 아직 그 그룹에 있을 때만 SIGKILL한다. 그룹에 구성원이 남아 있는 동안 그 그룹 번호는 다시 쓰이지 않아, pid가 다른
    프로세스에 갔다면 그 그룹이 아니다."""
    try:
        if os.getpgid(pid) == pgid:
            os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def stop_group(proc: subprocess.Popen, sig: int) -> None:
    if proc.returncode is not None:  # 이미 거둔 프로세스의 pid(=그룹 번호)는 다른 프로세스가 받았을 수 있다
        return
    try:
        os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError):  # EPERM: 끝났지만 아직 거두지 않은 그룹(macOS)
        pass


def run_dir_for(base: Path, model: str, effort: str, problem: str, run) -> Path:
    return base / f"{model}_{effort}" / problem / f"run{run}"


def run_one(job: dict, key: str) -> dict:
    if _STOP.is_set():
        raise Stopped("멈춘 뒤라 띄우지 않았다")
    run_dir: Path = job["dir"]
    run_dir.mkdir(parents=True)
    tool, spec = PREPARED[job["problem"]]
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
    started, timed_out_at = time.time(), None
    with _RUNNING_LOCK:
        if _STOP.is_set():
            shutil.rmtree(run_dir, ignore_errors=True)
            raise Stopped("멈춘 뒤라 띄우지 않았다")
        # 새 프로세스 그룹으로 띄워, 끝낼 때 claude가 띄운 MCP 서버(cysuml)까지 그룹째 끝낸다
        proc = subprocess.Popen(cmd, cwd=run_dir, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", start_new_session=True)
        _RUNNING.add(proc)
    try:
        stdout, stderr = proc.communicate(timeout=job["timeout"])
        code = proc.returncode
    except subprocess.TimeoutExpired:  # 시간 초과여도 그때까지의 기록은 남긴다(비용은 끝의 결과가 없어 비운다)
        timed_out_at = time.time()  # 시간은 끝내고 기다린 동안을 빼고 잰다
        stop_group(proc, signal.SIGKILL)
        try:
            stdout, stderr = proc.communicate(timeout=60)
        except subprocess.TimeoutExpired as e:  # 그룹 밖으로 나간 자손이 출력을 쥐고 있으면 끝내도 닫히지 않는다
            stdout = (e.stdout or b"").decode("utf-8", "replace")  # 그때까지 받은 기록은 남긴다
            stderr = (e.stderr or b"").decode("utf-8", "replace") + "\n끝낸 뒤에도 출력이 닫히지 않아 그때까지 받은 기록만 남겼다"
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        code = None
    finally:
        with _RUNNING_LOCK:
            _RUNNING.discard(proc)
    (run_dir / "stream.jsonl").write_text(stdout, encoding="utf-8")
    if stderr.strip():
        (run_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
    meta = {"exit": code, "wall_s": round((timed_out_at or time.time()) - started, 1), "timed_out": code is None,
            "signaled": proc.pid in _SIGNALED}
    (run_dir / "run.json").write_text(json.dumps(meta), encoding="utf-8")  # 해석이 실패해도 rescore.py가 다시 읽게
    row = build_row(job | meta, stdout.split("\n"), tool, spec, meta["timed_out"])
    stopped = row["subtype"] == "stopped"
    (run_dir / "row.json").write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding="utf-8")
    if stopped:
        raise Stopped("멈출 때 끝냈다")
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
    if args.workers < 1 or args.runs < 1:
        ap.error("--workers와 --runs는 1 이상이다")
    args.problems = list(dict.fromkeys(p for name in args.problems for p in SETS.get(name, [name])))
    args.models = list(dict.fromkeys(args.models))  # 겹치면 같은 실행 폴더를 두 실행이 함께 쓴다
    args.efforts = list(dict.fromkeys(args.efforts))
    unknown = [p for p in args.problems if p not in PROBLEMS and p not in WRITTEN]
    if unknown:
        sys.exit(f"모르는 문제: {unknown} (있는 것: {list(PROBLEMS) + list(WRITTEN)})")
    for p in args.problems:  # 합격한 그림을 문제와 견줄 수 없으면 돈을 쓴 실행이 하네스 오류로 끝나니 미리 읽어 본다
        tool, spec = load_problem(p)
        try:
            problem_shape(spec, tool)
            PREPARED[p] = tool, spec
            if spots := blind_spots(spec, tool):
                say(f"알림: 문제 {p}의 요소 {spots}는 대조가 서로 가르지 못한다 — 대칭으로 바꿔 이은 그림을 놓칠 수 있다"
                    "(RESULTS.md 한계)", file=sys.stderr)
        except InputError as e:
            sys.exit(f"문제 {p}를 cysUML이 읽지 못한다: {e}")

    if os.name == "nt":  # 프로세스 그룹·신호로 claude를 끝낸다
        sys.exit("run_bench.py는 macOS·Linux에서만 돈다")
    if shutil.which("claude") is None:
        sys.exit("claude가 PATH에 없다 — Claude Code를 설치한다")
    if not (ROOT / ".venv" / "bin" / "cysuml").exists():
        sys.exit(f"{ROOT / '.venv/bin/cysuml'}이 없다 — 레포에서 uv sync를 먼저 돌린다")
    base = args.out / args.tag
    if base.exists() and any(base.iterdir()):  # 남은 실행 폴더에 새 기록이 섞이지 않게
        sys.exit(f"이미 기록이 있는 태그다: {base} — --tag로 다른 이름을 준다")
    jobs = [{"model": m, "effort": e, "problem": p, "run": r, "budget": args.budget, "timeout": args.timeout,
             "dir": run_dir_for(base, m, e, p, r)}
            for m in args.models for e in args.efforts for p in args.problems for r in range(1, args.runs + 1)]
    key = api_key()
    rows = []
    base.mkdir(parents=True, exist_ok=True)
    pool = cf.ThreadPoolExecutor(max_workers=args.workers)
    # 멈출 까닭. 신호 처리기와 record가 적고, 메인 루프가 정해진 자리에서 보고 멈춘다. failed는 결과를 쓰다 난 오류
    under_uv = os.path.basename(_parent_name()) == "uv"
    stop = {"why": None, "first": None, "signum": None, "spare": False, "failed": False, "skipped": [], "forbidden": set()}

    def on_stop(signum, frame):  # 예외를 던지지 않아 쓰던 줄이 잘리거나 잠금을 쥔 채 끊기지 않는다
        if stop["why"] is not None and stop["first"] is None:  # 키·크레딧 오류 등으로 이미 멈추는 중이면 첫 신호가 "한 번 더"다
            force_exit(signum, frame)
        if stop["first"] is not None:
            # uv run은 받은 신호를 python에도 그대로 넘기고 셸은 앞그룹 전체에 보내, 한 번의 Ctrl-C·터미널 닫기가 같은 신호로
            # 두 번 온다. 부모가 uv면 첫 신호와 같은 신호 하나는 그 사본으로 보고, 그 밖에 또 오면 정리가 막혔어도 바로 끝낸다
            if stop["spare"] and signum == stop["signum"]:
                stop["spare"] = False
                return
            force_exit(signum, frame)
        stop["first"], stop["signum"], stop["spare"] = time.monotonic(), signum, under_uv
        stop["why"] = stop["why"] or signal.Signals(signum).name

    previous = {s: signal.getsignal(s) for s in STOP_SIGNALS}
    # Ctrl-C·kill·터미널 닫기. claude는 새 세션이라 이 신호를 받지 못해 직접 끝낸다. nohup으로 무시하던 신호는 그대로 둔다
    watched = [s for s in STOP_SIGNALS if previous[s] is not signal.SIG_IGN]
    for s in watched:
        signal.signal(s, on_stop)
    # 결과는 실행이 끝날 때마다 한 줄씩 써서, 중간에 멈춰도 끝난 실행은 남는다
    f = (base / "results.csv").open("w", newline="", encoding="utf-8")
    try:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        f.flush()  # 멈출 때 os._exit로 끝내 버퍼가 버려지니, 끝난 실행이 없어도 머리줄은 남긴다
        futures: dict = {}
        recorded = set()

        def record(fut) -> None:
            j = futures[fut]
            if fut.cancelled():  # 쓸 수 없는 모델이라 띄우기 전에 뺀 실행
                recorded.add(fut)
                return
            try:
                row = fut.result()
            except Stopped:
                recorded.add(fut)
                return
            except Exception as e:
                row = {"model": j["model"], "effort": j["effort"], "problem": j["problem"], "run": j["run"],
                       "subtype": f"harness_error: {type(e).__name__}: {e}"}
            recorded.add(fut)  # 쓰기 전에 표시한다 — 쓰다 실패해 drain이 다시 불러도 줄을 겹쳐 쓰지 않는다(실패는 failed로 알린다)
            w.writerow(row)
            rows.append(row)
            f.flush()
            say(json.dumps({k: row.get(k) for k in ("model", "effort", "problem", "run", "passed", "first_pass_draw",
                                                     "draws", "cost_usd", "duration_s", "subtype")}, ensure_ascii=False))
            if stop["why"] is not None:
                return
            cause = config_error(row)
            if cause == "forbidden":  # 403이 두 모델째에서도 나면 키·조직 전체의 권한 문제다
                stop["forbidden"].add(j["model"])
                cause = "key" if len(stop["forbidden"]) > 1 else "model"
            if cause == "model" and j["model"] not in stop["skipped"]:  # 그 모델만 쓸 수 없다(이름 오타·권한)
                stop["skipped"].append(j["model"])
                skipped = [x for x, job in futures.items()
                           if job["model"] == j["model"] and not x.cancelled() and x.cancel()]
                say(f"{j['model']}을(를) 쓸 수 없어({_api_code(row)}) 그 모델의 남은 실행 {len(skipped)}건을 뺀다: "
                    f"{row.get('error')}",
                    file=sys.stderr)
            elif cause in ("key", "billing"):  # 키·크레딧은 모든 실행에 걸리니 바로 멈춘다(이미 뺀 모델의 404는 여기 오지 않는다)
                what = "크레딧이 떨어졌다" if cause == "billing" else "API 키가 틀렸거나 키·조직에 권한이 없다"
                stop["why"] = f"{what}({_api_code(row)}): {row.get('error')}"
            elif not any(is_measured(r.get("subtype")) for r in rows):
                started_badly = [r for r in rows if (r.get("subtype") or "").startswith(("no_init", "mcp_failed"))
                                 and "during run" not in r["subtype"]]  # 그리다가 끊긴 것은 시작은 했다
                if len(started_badly) >= 3:  # 잰 실행 없이 시작 실패만 나면 설정·환경 문제다
                    stop["why"] = f"claude가 시작하지 못하거나 MCP가 붙지 않는다({len(started_badly)}번): {row.get('subtype')}"

        try:
            for j in jobs:
                futures[pool.submit(run_one, j, key)] = j
            pending = set(futures)
            while pending and stop["why"] is None:
                done, pending = cf.wait(pending, timeout=0.5, return_when=cf.FIRST_COMPLETED)
                for fut in done:
                    record(fut)
        except Exception as e:  # 결과를 쓰다 난 오류(디스크가 가득 참 등)
            stop["why"], stop["failed"] = stop["why"] or f"오류: {type(e).__name__}: {e}", True

        def drain() -> None:  # 끝났는데 아직 쓰지 못한 실행을 실행마다 따로 쓴다(하나가 실패해도 나머지는 쓴다)
            for fut in futures:
                if fut.done() and fut not in recorded:
                    try:
                        record(fut)
                    except Exception as more:
                        stop["failed"] = True
                        say(f"끝난 실행 하나를 쓰지 못했다: {type(more).__name__}: {more}", file=sys.stderr)

        if stop["why"] is not None and all(fut.done() for fut in futures):  # 멈출 때 남은 실행이 없었다
            drain()
            say(f"알림: {stop['why']}", file=sys.stderr)
        elif stop["why"] is not None:  # 남은 실행은 띄우지 않고, 돌던 claude도 직접 끝낸다
            try:
                with _RUNNING_LOCK:
                    _STOP.set()
                    procs = list(_RUNNING)
                    live = [p for p in procs if p.poll() is None]  # 이미 스스로 끝난 실행은 신호를 보낸 실행이 아니다
                    _SIGNALED.update(p.pid for p in live)
                # 그룹 구성원(MCP 서버 등)을 지금 기억해, claude가 먼저 끝나도 남은 구성원까지 끝낸다
                _MEMBERS.update(group_members([p.pid for p in live]))
                for p in live:
                    stop_group(p, signal.SIGTERM)
                pool.shutdown(wait=False, cancel_futures=True)
                deadline = time.time() + 10  # SIGTERM을 무시하는 그룹은 10초 뒤 SIGKILL로 끝낸다
                while time.time() < deadline and any(p.poll() is None for p in procs):
                    time.sleep(0.2)
                kill_groups(procs)
                waiting = [fut for fut in futures if not fut.done()]
                if waiting:
                    # 시간 초과로 끝낸 실행은 출력이 닫히기를 60초까지 기다리니 그보다 길게 기다린다
                    say(f"끝난 실행의 기록을 기다린다(최대 75초, {len(waiting)}건)", file=sys.stderr)
                    cf.wait(waiting, timeout=75)
                drain()  # 정리하는 동안 스스로 끝난 실행도 든다
                say(f"멈췄다({stop['why']}): 끝난 {len(rows)}건은 {base / 'results.csv'}에 있다(멈추며 끊은 실행은 CSV에 "
                    "들지 않는다)", file=sys.stderr)
            except BaseException:
                force_exit(None, None)
            # 일꾼 스레드를 기다리지 않고 끝낸다(끝낸 그룹 밖 자손이 출력을 쥐고 있으면 --timeout까지 매달린다). CSV는
            # 줄마다 flush했다
            os._exit(1)
    finally:
        try:
            f.close()
        except OSError as e:  # 디스크가 가득 차 마지막 줄을 비우지 못했다
            stop["failed"] = True
            say(f"results.csv를 닫지 못했다: {e}", file=sys.stderr)
    restore_stop_signals(previous)
    pool.shutdown()
    total = sum(r.get("cost_usd") or 0 for r in rows)
    unknown_cost = sum(1 for r in rows if r.get("cost_usd") is None)
    note = f", 비용을 모르는 실행 {unknown_cost}건은 합계에 들지 않았다" if unknown_cost else ""
    say(f"끝: {len(rows)}건, 합계 ${total:.2f}{note}, 결과 {base / 'results.csv'}")
    if stop["failed"]:
        sys.exit("결과를 다 쓰지 못했다(위 알림) — results.csv가 모자랄 수 있다")
    if stop["why"] is not None and stop["first"] is None:  # 키·크레딧 오류 등 신호가 아닌 까닭으로 멈췄다
        sys.exit(f"멈춘 까닭: {stop['why']}")
    if stop["skipped"]:
        sys.exit(f"쓸 수 없어 뺀 모델이 있다: {stop['skipped']}")

if __name__ == "__main__":
    main()
