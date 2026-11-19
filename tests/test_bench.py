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


def test_mcp_transport_error_is_not_the_models_failure():
    # 그리는 도중 MCP 서버가 끊긴 실행은 모델을 잰 것이 아니다
    tool, spec = bench.load_problem("order")
    events = [INIT, *_draws(spec, [FAIL, "MCP error -32000: Connection closed"])]
    events[-1]["message"]["content"][0]["is_error"] = True
    row = bench.build_row({"model": "m", "effort": "high", "problem": "order", "run": 1, "exit": 0, "wall_s": 9.0},
                          [json.dumps(e) for e in [*events, ENDED]], tool, spec, False)
    assert row["verdicts"] == "fail mcp_error" and not bench.is_measured(row["subtype"])


def test_mcp_error_then_more_draws_is_measured():
    # MCP가 잠깐 끊긴 뒤에도 계속 그렸으면 모델을 잰 실행이다
    tool, spec = bench.load_problem("order")
    events = [INIT, *_draws(spec, [FAIL, "MCP error -32001: Request timed out", FAIL])]
    events[4]["message"]["content"][0]["is_error"] = True  # 두 번째 차례의 도구 결과
    row = bench.build_row({"model": "m", "effort": "high", "problem": "order", "run": 1, "exit": 0, "wall_s": 9.0},
                          [json.dumps(e) for e in [*events, ENDED]], tool, spec, False)
    assert row["verdicts"] == "fail mcp_error fail" and bench.is_measured(row["subtype"])


def test_timeout_before_any_draw_is_not_measured_even_after_text():
    # 말만 하고 한 번도 그리지 않은 채 시간이 다 가면 API가 멈춘 것과 가를 수 없어 뺀다
    tool, spec = bench.load_problem("order")
    talk = {"type": "assistant", "message": {"content": [{"type": "text", "text": "생각 중"}]}}
    row = bench.build_row({"model": "m", "effort": "high", "problem": "order", "run": 1, "exit": None, "wall_s": 9.0},
                          [json.dumps(e) for e in [INIT, talk]], tool, spec, True)
    assert row["subtype"] == "no_answer (timeout)"


def test_tool_exception_and_internal_crash_are_not_the_models_failure():
    tool, spec = bench.load_problem("order")
    meta = {"model": "m", "effort": "high", "problem": "order", "run": 1, "exit": 0, "wall_s": 9.0}
    # cysUML 도구가 예외를 내 그 차례로 끝났다
    events = [INIT, *_draws(spec, [FAIL, "Error executing tool draw_class_diagram: KeyError 'x'"])]
    events[-1]["message"]["content"][0]["is_error"] = True
    row = bench.build_row(meta, [json.dumps(e) for e in [*events, ENDED]], tool, spec, False)
    assert row["verdicts"] == "fail tool_error" and row["subtype"] == "tool_error"
    # claude 안의 오류로 끝났다(결과 이벤트는 냈다)
    crash = {"type": "result", "subtype": "error_during_execution", "is_error": True}
    row = bench.build_row(meta, [json.dumps(e) for e in [INIT, *_draws(spec, [FAIL]), crash]], tool, spec, False)
    assert row["subtype"] == "no_result"


def test_timeout_after_a_draw_is_the_models_failure_even_mid_tool_call():
    # 한 번이라도 그린 뒤의 시간 초과는 모델의 불합격이다(도구 호출 중에 끊겼어도 — 큰 그림은 그리는 데도 시간이 든다)
    tool, spec = bench.load_problem("order")
    unanswered = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "late", "name": "mcp__cysuml__draw_class_diagram", "input": spec}]}}
    row = bench.build_row({"model": "m", "effort": "high", "problem": "order", "run": 1, "exit": None, "wall_s": 9.0},
                          [json.dumps(e) for e in [INIT, *_draws(spec, [FAIL]), unanswered]], tool, spec, True)
    assert row["verdicts"] == "fail missing" and row["subtype"] == "timeout" and bench.is_measured(row["subtype"])


def test_budget_cut_during_a_tool_call_is_the_models_failure():
    # 옛 기록에 실제로 있는 꼴: 도구 호출이 끝나기 전에 비용 상한으로 claude가 스스로 끝났다(도구가 멈춘 것이 아니다)
    tool, spec = bench.load_problem("order")
    pending = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "late", "name": "mcp__cysuml__draw_class_diagram", "input": spec}]}}
    budget = {"type": "result", "subtype": "error_max_budget_usd", "is_error": True}
    row = bench.build_row({"model": "m", "effort": "high", "problem": "order", "run": 1, "exit": 1, "wall_s": 9.0},
                          [json.dumps(e) for e in [INIT, *_draws(spec, [FAIL]), pending, budget]], tool, spec, False)
    assert row["verdicts"] == "fail missing" and row["subtype"] == "error_max_budget_usd"


def test_blind_spots_are_elements_the_comparison_cannot_tell_apart():
    # 이름 있는 행동 A에서 저마다 흐름을 받는 이름 없는 합류 6개의 고리: 모두 이름 있는 요소에 닿지만 꼬리표가 겹친다
    ring = {"elements": [{"kind": "initial", "id": "s"}, {"kind": "action", "name": "A"}]
            + [{"kind": "merge", "id": f"m{i}"} for i in range(6)],
            "relations": [{"from": "s", "to": "A"}] + [{"from": "A", "to": f"m{i}"} for i in range(6)]
            + [{"from": f"m{i}", "to": f"m{(i + 1) % 6}"} for i in range(6)]}
    assert set(bench.blind_spots(ring, "draw_activity_diagram")) == {f"m{i}" for i in range(6)}
    # 이름이 겹쳐도 비대칭 사슬은 꼬리표가 모두 갈려 경고하지 않는다
    chain = {"elements": [{"kind": "initial", "id": "s"}, {"kind": "action", "id": "a1", "name": "Item"},
                          {"kind": "action", "id": "a2", "name": "Item"}, {"kind": "merge", "id": "m1"},
                          {"kind": "final", "id": "f"}],
             "relations": [{"from": "s", "to": "a1"}, {"from": "a1", "to": "m1"}, {"from": "m1", "to": "a2"},
                           {"from": "a2", "to": "f"}]}
    assert bench.blind_spots(chain, "draw_activity_diagram") == []


@pytest.mark.parametrize("pid", PROBLEM_IDS)
def test_every_problem_is_fully_told_apart(pid):
    # RESULTS.md 한계 절의 근거: 지금 문제는 대조가 모든 요소를 서로 다른 꼬리표로 가른다
    tool, spec = bench.load_problem(pid)
    assert bench.blind_spots(spec, tool) == []


def test_non_object_lines_are_skipped():
    tool, spec = bench.load_problem("order")
    lines = ["null", "3", '"x"', *[json.dumps(e) for e in [INIT, *_draws(spec, [PASS]), ENDED]]]
    row = bench.build_row({"model": "m", "effort": "high", "problem": "order", "run": 1, "exit": 0, "wall_s": 9.0},
                          lines, tool, spec, False)
    assert row["passed"] and row["subtype"] == "success"


def test_classification_does_not_depend_on_branch_order():
    # 고장 판정은 시간 초과보다, 서버 쪽 오류는 끝난 꼴보다 먼저 본다. 신호를 받고 낸 중단 오류도 끊긴 실행이다
    tool, spec = bench.load_problem("order")
    meta = {"model": "m", "effort": "high", "problem": "order", "run": 1, "exit": None, "wall_s": 9.0}
    broken = [INIT, *_draws(spec, [FAIL, "MCP error -32000: Connection closed"])]
    broken[-1]["message"]["content"][0]["is_error"] = True
    row = bench.build_row(meta, [json.dumps(e) for e in broken], tool, spec, True)
    assert row["subtype"] == "mcp_failed: during run (timeout)" and not bench.is_measured(row["subtype"])
    aborted = {"type": "result", "subtype": "success", "is_error": True, "result": "API Error: Request was aborted."}
    row = bench.build_row(meta | {"exit": 143, "signaled": True},
                          [json.dumps(e) for e in [INIT, *_draws(spec, [FAIL]), aborted]], tool, spec, False)
    assert row["subtype"] == "stopped"
    overload = {"type": "result", "subtype": "error_during_execution", "is_error": True, "api_error_status": 529}
    row = bench.build_row(meta | {"exit": 1}, [json.dumps(e) for e in [INIT, *_draws(spec, [FAIL]), overload]],
                          tool, spec, False)
    assert row["subtype"] == "api_error"


def test_result_is_settled_when_the_ten_draws_are_answered():
    # 10번째 그리기가 답을 기다리는 중이면 결과가 정해진 것이 아니고, 고장으로라도 답을 받았으면 정해졌다
    tool, spec = bench.load_problem("order")
    meta = {"model": "m", "effort": "high", "problem": "order", "run": 1, "exit": 143, "wall_s": 9.0, "signaled": True}
    pending = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "late", "name": "mcp__cysuml__draw_class_diagram", "input": spec}]}}
    row = bench.build_row(meta, [json.dumps(e) for e in [INIT, *_draws(spec, [FAIL] * 9), pending]], tool, spec, False)
    assert row["draws"] == 10 and row["subtype"] == "stopped"
    broken = [INIT, *_draws(spec, [FAIL] * 9 + ["MCP error -32000: Connection closed"])]
    broken[-1]["message"]["content"][0]["is_error"] = True
    row = bench.build_row(meta | {"signaled": False, "exit": 0}, [json.dumps(e) for e in [*broken, ENDED]], tool, spec,
                          False)
    # 10번째 호출이 고장으로 끝났어도 지시한 10번을 다 써 결과가 정해졌다(그 뒤 합격해도 지시를 넘긴 것이다)
    assert row["subtype"] == "success" and not row["passed"] and bench.is_measured(row["subtype"])


def test_broken_draws_still_count_toward_the_ten_draws():
    # 프롬프트의 "10번 뒤에는 멈춘다"는 고장 난 호출까지 센다: 고장 하나 뒤 11번째 호출에서 합격하면 지시를 넘긴 것이다
    tool, spec = bench.load_problem("order")
    events = [INIT, *_draws(spec, ["MCP error -32001: Request timed out"] + [FAIL] * 9 + [PASS])]
    events[2]["message"]["content"][0]["is_error"] = True
    row = bench.build_row({"model": "m", "effort": "high", "problem": "order", "run": 1, "exit": 0, "wall_s": 9.0},
                          [json.dumps(e) for e in [*events, ENDED]], tool, spec, False)
    assert row["draws"] == 11 and row["first_pass_draw"] == 11 and not row["passed"]
    assert bench.is_measured(row["subtype"])  # 그리기 10번을 다 써 결과가 정해진 잰 실행이다


def test_key_and_model_errors_are_read_from_the_cli_text_too():
    assert bench.config_error({"is_error": True, "api_status": None, "error": "Invalid API key · Fix external API key"}) == "key"
    assert bench.config_error({"is_error": True, "api_status": None,
                               "error": "There's an issue with the selected model (claude-x)."}) == "model"


def test_server_errors_win_over_stop_and_missing_tool():
    tool, spec = bench.load_problem("order")
    meta = {"model": "m", "effort": "high", "problem": "order", "run": 1, "exit": 1, "wall_s": 9.0}
    overload = {"type": "result", "subtype": "error_during_execution", "is_error": True, "api_error_status": 529}
    row = bench.build_row(meta | {"signaled": True}, [json.dumps(e) for e in [INIT, *_draws(spec, [FAIL]), overload]],
                          tool, spec, False)
    assert row["subtype"] == "api_error"  # 멈출 때 났어도 서버 쪽 오류다
    pending = {"type": "system", "subtype": "init", "mcp_servers": [{"name": "cysuml", "status": "pending"}], "tools": []}
    outage = {"type": "result", "subtype": "success", "is_error": True, "result": "overloaded"}
    row = bench.build_row(meta, [json.dumps(e) for e in [pending, outage]], tool, spec, False)
    assert row["subtype"] == "api_error"  # MCP가 붙기 전이어도 API 장애다(시작 실패로 세지 않는다)
    # 신호와 같은 때 모델 탓 오류로 스스로 끝난 것은 잰 실행이다(중단 글만 끊긴 것으로 본다)
    too_long = {"type": "result", "subtype": "success", "is_error": True, "api_error_status": 400, "result": "Prompt is too long"}
    row = bench.build_row(meta | {"signaled": True}, [json.dumps(e) for e in [INIT, *_draws(spec, [FAIL]), too_long]],
                          tool, spec, False)
    assert row["subtype"] == "success"


def test_tool_call_rejected_by_the_sdk_is_an_input_error():
    tool, spec = bench.load_problem("order")
    sdk = "Error executing tool draw_class_diagram: 1 validation error for draw_class_diagramArguments\nfile_name"
    events = [INIT, *_draws(spec, [sdk])]
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
    # 403은 그 모델만인지 키·조직 전체인지 오류만으로 가를 수 없다(record가 두 모델째에서 전체를 멈춘다)
    assert bench.config_error({"is_error": True, "api_status": 403, "error": "permission to use the model"}) == "forbidden"


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
