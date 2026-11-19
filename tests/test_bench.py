"""bench/(모델별 배치 측정)는 cysUML 내부(도구별 SPEC·parse)에 기대어 그린 입력을 문제와 견준다. 그 내부를 바꿔도 측정이
조용히 깨지지 않는지 본다."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
import run_bench as bench  # noqa: E402

PROBLEM_IDS = list(bench.PROBLEMS) + list(bench.WRITTEN)


@pytest.mark.parametrize("pid", PROBLEM_IDS)
def test_problem_is_read_and_matches_itself(pid):
    tool, spec = bench.load_problem(pid)
    bench.problem_shape(spec, tool)
    assert bench.faithful(json.loads(json.dumps(spec)), spec, tool)


@pytest.mark.parametrize("pid", list(bench.PROBLEMS))
def test_layout_fields_are_not_compared(pid):
    # 자리가 든 README 예시 입력과, 거기서 자리를 지운 문제는 같은 그림으로 본다(자리 칸은 견주지 않는다)
    drawn = json.loads((bench.EXAMPLES / f"{bench.PROBLEMS[pid]}.cysuml.json").read_text(encoding="utf-8"))
    tool, spec = bench.load_problem(pid)
    assert bench.faithful(drawn, spec, tool)


def test_changed_diagram_is_not_faithful():
    tool, spec = bench.load_problem("order")
    dropped = json.loads(json.dumps(spec))
    dropped["relations"].pop()
    assert not bench.faithful(dropped, spec, tool)


CLASS = "draw_class_diagram"
NODES = "draw_deployment_diagram"
TWO_CLASSES = {"classes": [{"name": "A"}, {"name": "B"}]}


@pytest.mark.parametrize("given, drawn, same", [
    # 연관은 양 끝을 바꾸면서 navigable·다중도도 맞바꾸면 같은 그림이다
    ({"kind": "association", "from": "A", "to": "B"},
     {"kind": "association", "from": "B", "to": "A", "navigable": "from"}, True),
    ({"kind": "association", "from": "A", "to": "B", "navigable": "none", "from_multiplicity": "1", "to_multiplicity": "*"},
     {"kind": "association", "from": "B", "to": "A", "navigable": "none", "from_multiplicity": "*", "to_multiplicity": "1"},
     True),
    ({"kind": "association", "from": "A", "to": "B"}, {"kind": "association", "from": "B", "to": "A"}, False),
    # navigable: none으로 화살촉을 없애면 바뀐 그림이다(모델이 실제로 이렇게 바꿔 합격했다)
    ({"kind": "association", "from": "A", "to": "B"},
     {"kind": "association", "from": "A", "to": "B", "navigable": "none"}, False),
    # 집합은 마름모 쪽이 정해져 있어 뒤집으면 바뀐 그림이다
    ({"kind": "aggregation", "from": "A", "to": "B", "navigable": "none"},
     {"kind": "aggregation", "from": "B", "to": "A", "navigable": "none"}, False),
])
def test_relation_direction(given, drawn, same):
    assert bench.faithful({**TWO_CLASSES, "relations": [drawn]}, {**TWO_CLASSES, "relations": [given]}, CLASS) == same


def test_renamed_ids_are_the_same_but_rewired_flows_are_not():
    tool, spec = bench.load_problem("loan-xxl")
    renamed = json.loads(json.dumps(spec))
    ids = {e["id"]: f"n{i}" for i, e in enumerate(renamed["elements"]) if not e.get("name")}
    for e in renamed["elements"]:
        if e.get("id") in ids:
            e["id"] = ids[e["id"]]
    for r in renamed["relations"]:
        r["from"], r["to"] = ids.get(r["from"], r["from"]), ids.get(r["to"], r["to"])
    assert bench.faithful(renamed, spec, tool)
    rewired = json.loads(json.dumps(spec))
    flow = next(r for r in rewired["relations"] if r["from"] == "score ok?" and r.get("name") == "[no]")
    flow["to"] = "approved"
    assert not bench.faithful(rewired, spec, tool)


@pytest.mark.parametrize("given, drawn, same", [
    ("PaymentGatewayAdapter", ["PaymentGateway", "Adapter"], True),  # 긴 한 단어를 줄로 나눔
    ("Order Service", ["Order", "Service"], True),
    ("Order Service", "OrderService", False),  # 띄어쓰기를 빼면 다른 이름이다
])
def test_names(given, drawn, same):
    def one(name):
        return {"elements": [{"kind": "node", "id": "n", "name": name}], "relations": []}

    assert bench.faithful(one(drawn), one(given), NODES) == same


INIT = {"type": "system", "subtype": "init", "mcp_servers": [{"name": "cysuml", "status": "connected"}],
           "tools": ["mcp__cysuml__draw_class_diagram"]}


def _draws(spec, verdicts):
    events = []
    for n, text in enumerate(verdicts):
        events.append({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": f"t{n}", "name": "mcp__cysuml__draw_class_diagram", "input": spec}]}})
        events.append({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": f"t{n}", "content": text}]}})
    return events


FAIL, PASS = "불합격 — 1건", "합격 — 끝"
ENDED = {"type": "result", "subtype": "success"}


@pytest.mark.parametrize("events, exit, timed_out, subtype, measured", [
    ([INIT, lambda s: _draws(s, [FAIL, PASS]), ENDED], 0, False, "success", True),
    ([INIT, lambda s: _draws(s, [FAIL]), {"type": "result", "subtype": "error_max_budget_usd", "is_error": True}],
     1, False, "error_max_budget_usd", True),
    # 서버 쪽 오류로 10번 전에 끊김(상태 칸, 오류 글, 크레딧 부족)은 잰 것이 아니다
    ([INIT, {"type": "result", "subtype": "success", "is_error": True, "api_error_status": 529}], 1, False, "api_error",
     False),
    ([INIT, {"type": "result", "subtype": "success", "is_error": True, "result": "API Error: 401 bad key"}], 1, False,
     "api_error", False),
    ([INIT, {"type": "result", "subtype": "success", "is_error": True, "api_error_status": 400,
             "result": "Your credit balance is too low"}], 1, False, "api_error", False),
    # 모델 탓인 400은 잰 불합격이다
    ([INIT, lambda s: _draws(s, [FAIL]), {"type": "result", "subtype": "success", "is_error": True,
                                          "api_error_status": 400, "result": "Prompt is too long"}],
     1, False, "success", True),
    ([], 1, False, "no_init", False),
    ([INIT], None, True, "no_answer (timeout)", False),
    ([INIT, lambda s: _draws(s, [FAIL])], None, True, "timeout", True),
    ([INIT, lambda s: _draws(s, [FAIL])], 0, False, "no_result", False),
])
def test_run_classification(events, exit, timed_out, subtype, measured):
    # 실행 기록(stream-json 이벤트)에서 실행을 어떻게 가르는지: 잰 실행인지, 표에서 뺄 실행인지
    tool, spec = bench.load_problem("order")
    flat = [x for e in events for x in (e(spec) if callable(e) else [e])]
    meta = {"model": "m", "effort": "high", "problem": "order", "run": 1, "exit": exit, "wall_s": 9.0}
    row = bench.build_row(meta, [json.dumps(x) for x in flat], tool, spec, timed_out)
    assert row["subtype"] == subtype and bench.is_measured(row["subtype"]) == measured


def test_tool_listed_at_init_means_the_model_could_draw():
    # MCP 상태가 pending이어도 그리기 도구가 목록에 있었으면, 그리지 않고 끝난 것은 모델의 판단이다
    tool, spec = bench.load_problem("order")
    pending = {**INIT, "mcp_servers": [{"name": "cysuml", "status": "pending"}]}
    row = bench.build_row({"model": "m", "effort": "high", "problem": "order", "run": 1, "exit": 1, "wall_s": 9.0},
                          [json.dumps(e) for e in [pending, {"type": "result", "subtype": "error_max_turns"}]],
                          tool, spec, False)
    assert row["subtype"] == "error_max_turns" and bench.is_measured(row["subtype"])


def test_tool_call_rejected_by_the_sdk_is_an_input_error():
    tool, spec = bench.load_problem("order")
    events = [INIT, *_draws(spec, ["Error executing tool draw_class_diagram: 1 validation error"])]
    events[-1]["message"]["content"][0]["is_error"] = True
    row = bench.build_row({"model": "m", "effort": "high", "problem": "order", "run": 1, "exit": 0, "wall_s": 9.0},
                          [json.dumps(e) for e in [*events, ENDED]], tool, spec, False)
    assert row["verdicts"] == "input_error" and row["input_errors"] == 1


def test_config_errors_stop_the_bench():
    assert bench.config_error({"is_error": True, "api_status": 401, "error": ""})
    assert bench.config_error({"is_error": True, "api_status": 400, "error": "Your credit balance is too low"})
    assert not bench.config_error({"is_error": True, "api_status": 529, "error": ""})
    assert not bench.config_error({"is_error": True, "api_status": 400, "error": "Prompt is too long"})
    # 문제 이름(billing·BillingService)이 오류 글에 인용돼도 크레딧 부족이 아니다
    assert not bench.config_error({"is_error": True, "api_status": 400, "error": "invalid input near BillingService"})


@pytest.mark.parametrize("ended, draws, stopped", [
    (None, 2, True),  # 결과 없이 끊김
    ("error_during_execution", 2, True),  # 신호를 받고 낸 결과는 스스로 끝난 것이 아니다
    ("success", 2, False),  # 신호 전에 스스로 끝났다(모델이 포기함)
    (None, 10, False),  # 10번을 다 그렸으면 잰 불합격이다
])
def test_signaled_runs(ended, draws, stopped):
    tool, spec = bench.load_problem("order")
    events = [INIT, *_draws(spec, [FAIL] * draws)] + ([{"type": "result", "subtype": ended}] if ended else [])
    meta = {"model": "m", "effort": "high", "problem": "order", "run": 1, "exit": 143, "wall_s": 9.0, "signaled": True}
    row = bench.build_row(meta, [json.dumps(e) for e in events], tool, spec, False)
    assert (row["subtype"] == "stopped") == stopped and bench.is_measured(row["subtype"]) != stopped


def test_lists_sent_as_json_text_are_read():
    tool, spec = bench.load_problem("order")
    as_text = {key: json.dumps(value) for key, value in spec.items()}
    assert bench.faithful(as_text, spec, tool)
