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


def test_lists_sent_as_json_text_are_read():
    tool, spec = bench.load_problem("order")
    as_text = {key: json.dumps(value) for key, value in spec.items()}
    assert bench.faithful(as_text, spec, tool)
