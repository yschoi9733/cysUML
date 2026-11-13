import base64
import io
import json
import re
import sys
from pathlib import Path

import anyio
import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from PIL import Image

from cysuml import (activitydiagram, boxcheck, boxdiagram, classcheck, classdiagram, componentdiagram,
                    deploymentdiagram, guide, packagediagram, sequencecheck, sequencediagram, server, statediagram,
                    usecasediagram)
from cysuml.canvas import SCALE
from cysuml.parsing import InputError
from cysuml.report import Finding

ORDER = [{"name": "Order", "left": 0, "top": 0}, {"name": "Customer", "left": 200, "top": 0}]
PLACES = [{"kind": "association", "from": "Order", "to": "Customer", "name": "places"}]
CLASS = ("draw_class_diagram", {"file_name": "order", "classes": ORDER, "relations": PLACES})
README = Path(__file__).resolve().parent.parent / "README.md"

PEOPLE = [{"name": "Customer", "kind": "actor"}, {"name": "Shop"}, {"name": "Payment"}]
TALKS = [{"from": "Customer", "to": "Shop", "name": "order()"},
         {"from": "Shop", "to": "Payment", "name": "pay(amount)"},
         {"from": "Payment", "to": "Shop", "kind": "reply", "name": "receipt"},
         {"from": "Shop", "to": "Customer", "kind": "reply"}]
CHECKS = [{"kind": "opt", "first": 1, "last": 2, "condition": "카드 결제"}]
SEQUENCE = ("draw_sequence_diagram", {"file_name": "checkout", "participants": PEOPLE, "messages": TALKS})


def run(target, *calls):
    """target(서버 객체나 stdio 실행 정보)에 붙어 안내문, 도구 목록과 calls((도구 이름, 인자))마다 결과를 받는다."""
    async def go():
        async with Client(target) as c:
            tools = {t.name: t for t in (await c.list_tools()).tools}
            return c.instructions, tools, [await c.call_tool(name, a) for name, a in calls]
    return anyio.run(go)


def draw(**args):
    return run(server.mcp, ("draw_class_diagram", args))[2][0]


def draw_seq(**args):
    return run(server.mcp, ("draw_sequence_diagram", args))[2][0]


def text(result):
    return result.content[0].text


def image(result):
    (block,) = [b for b in result.content if b.type == "image"]
    assert block.mime_type == "image/png"
    return Image.open(io.BytesIO(base64.b64decode(block.data)))


TOOLS = [  # 도구 → 필수 입력, 객체 목록 입력, 문자열 목록 입력. 도구를 더하면 줄을 더한다
    ("draw_class_diagram", ["file_name", "classes"], ("classes", "relations"), ()),
    ("draw_package_diagram", ["file_name", "elements"], ("elements", "relations"), ()),
    ("draw_component_diagram", ["file_name", "elements"], ("elements", "relations"), ()),
    ("draw_deployment_diagram", ["file_name", "elements"], ("elements", "relations"), ()),
    ("draw_use_case_diagram", ["file_name", "elements"], ("elements", "relations"), ()),
    ("draw_state_diagram", ["file_name", "elements"], ("elements", "relations"), ()),
    ("draw_activity_diagram", ["file_name", "elements"], ("elements", "relations"), ()),
    ("draw_sequence_diagram", ["file_name", "participants"], ("participants", "messages", "frames"), ("notes",)),
]
EXAMPLES = {  # README 예시 file_name → 도구. 예시를 더하면 줄을 더한다
    "order": "draw_class_diagram",
    "packages": "draw_package_diagram",
    "components": "draw_component_diagram",
    "deployment": "draw_deployment_diagram",
    "use-cases": "draw_use_case_diagram",
    "order-states": "draw_state_diagram",
    "order-flow": "draw_activity_diagram",
    "checkout": "draw_sequence_diagram",
}
PLACED_TOOLS = {  # AI가 배치하는 도구 → 그 도구 설명에 있어야 하는 배치 요령, 날 수 있는 불합격 종류, 그 도구 정의(Spec)
    "draw_class_diagram": (server.CLASS_TIPS, classcheck.KINDS, classdiagram.SPEC),
    "draw_package_diagram": (packagediagram.TIPS, boxcheck.KINDS, packagediagram.SPEC),
    "draw_component_diagram": (componentdiagram.TIPS, boxcheck.KINDS, componentdiagram.SPEC),
    "draw_deployment_diagram": (deploymentdiagram.TIPS, boxcheck.KINDS, deploymentdiagram.SPEC),
    "draw_use_case_diagram": (usecasediagram.TIPS, boxcheck.KINDS, usecasediagram.SPEC),
    "draw_state_diagram": (statediagram.TIPS, boxcheck.KINDS, statediagram.SPEC),
    "draw_activity_diagram": (activitydiagram.TIPS, activitydiagram.KINDS, activitydiagram.SPEC),
}

TRUNK_TOOLS = [n for n, (_, _, spec) in PLACED_TOOLS.items() if any(t.trunk for t in spec.relations.values())]


def test_lists_every_tool_with_its_inputs():
    _, tools, _ = run(server.mcp)
    assert set(tools) == {name for name, *_ in TOOLS}
    for name, required, lists, strings in TOOLS:
        schema = tools[name].input_schema
        assert schema["required"] == required
        props = schema["properties"]
        assert set(props) == {"file_name", *lists, *strings, "out_dir", "scale"}
        for key in lists + strings:
            assert props[key]["type"] == "array"
            assert props[key]["items"] == {"type": "string" if key in strings else "object"}


def test_each_tool_carries_its_flow_and_tips_and_the_instructions_carry_the_flows_only():
    instructions, tools, _ = run(server.mcp)
    seq_tool = tools["draw_sequence_diagram"].description
    for name, (tips, kinds, spec) in PLACED_TOOLS.items():
        tool = tools[name].description
        assert guide.flow(kinds, spec.words) in tool and tips in tool
        if name in TRUNK_TOOLS:  # 공유 줄기 안내가 든 관계 필드가 그 도구 설명에 그대로 들어간다
            assert guide.relation_fields(spec) in tool
        assert server.SEQUENCE_FLOW not in tool and guide.PLACED_FLOW not in seq_tool
        assert tips not in instructions
        assert tips not in seq_tool
    assert server.SEQUENCE_FLOW in seq_tool
    for part in (guide.flow(), server.SEQUENCE_FLOW, *tools):
        assert part in instructions
    assert "불합격(" not in instructions  # 불합격 목록은 도구 설명에만 둔다


def test_sequence_description_names_every_field_kind_and_limit_the_reader_takes():
    S = sequencediagram
    names = (S.DIAGRAM_FIELDS + S.PARTICIPANT_FIELDS + S.MESSAGE_FIELDS + S.ALL_FRAME_FIELDS + S.BRANCH_FIELDS)
    for name in names:  # 필드는 "name(필수)"·"kind:"·"from·to"처럼 바로 뒤에 괄호·쌍점·가운뎃점이 붙어 나온다
        assert re.search(rf"(?<![A-Za-z_]){name}[(:·]", server.SEQUENCE_TOOL), name
    for kind in S.PARTICIPANT_KINDS + S.MESSAGE_KINDS + S.FRAME_KINDS:
        assert f'"{kind}"' in server.SEQUENCE_TOOL, kind
    for limit in (S.MAX_PARTICIPANTS, S.MAX_MESSAGES, S.MAX_FRAMES, S.MAX_NOTES):
        assert f"{limit}개까지" in server.SEQUENCE_TOOL
    assert "반환(reply)은 나를 부른 쪽으로 보낸다" in server.SEQUENCE_TOOL


def test_description_names_the_failure_kinds_of_each_tool_in_check_order():
    assert tuple(guide.KIND_NAMES) == boxcheck.KINDS
    assert set(classcheck.KINDS) == set(boxcheck.KINDS) - set(boxcheck.NESTED_KINDS)
    # 클래스도 도구는 요소를 상자, 테두리를 변이라고 부른다(그 도구의 입력·결과·검사 글과 같은 말)
    class_names = guide.kind_names(classcheck.KINDS, boxdiagram.BOX_WORDS)
    assert ", ".join(class_names) + "." in server.CLASS_TOOL
    assert {"상자끼리 겹치거나 붙음", "선이 제 끝 상자 변에 붙어 감", "선 끝 모양이 그 선의 다른 끝 상자 변에 붙음"} <= set(class_names)
    assert not any("요소" in n or "테두리" in n for n in class_names)
    assert not any(n in server.CLASS_TOOL for n in guide.kind_names(boxcheck.NESTED_KINDS, boxdiagram.BOX_WORDS))
    assert ", ".join(guide.KIND_NAMES.values()) + "." in packagediagram.TOOL


def test_relation_fields_follow_the_relation_kinds_a_tool_takes():
    # 유즈케이스도처럼 연관·의존·일반화만 받고 연관의 기본 방향이 '없음'인 도구
    kinds = ("association", "dependency", "generalization")
    spec = boxdiagram.Spec(classdiagram.CLASS_SHAPES, {k: classdiagram.RELATIONS[k] for k in kinds}, navigable="none")
    text = guide.relation_fields(spec)
    assert '  - kind(필수): "association"·"dependency"·"generalization".' in text
    assert "의존·상속은 from이 의존하는 쪽·자식이고 화살촉·삼각형이 to 쪽에 붙는다." in text and "마름모" not in text
    assert '연관만 쓴다. navigable은 화살촉을 둘 쪽 "to"·"from"·"both"·"none"(기본)이다.' in text
    # 공유 줄기는 받는 관계 종류(상속)만 적고(종류가 하나면 두 줄기를 나누는 법은 없다), 받는 관계가 없는 도구에는 넣지 않는다
    assert "  - 공유 줄기: 같은 부모(to)로 가는 상속끼리는 여러 선을" in text and "실체화" not in text
    assert "함께 오면" not in text
    plain = boxdiagram.Spec(classdiagram.CLASS_SHAPES, {k: classdiagram.RELATIONS[k] for k in kinds[:2]}, navigable="none")
    assert "공유 줄기" not in guide.relation_fields(plain)


def test_tools_with_trunk_relations():
    assert TRUNK_TOOLS == ["draw_class_diagram", "draw_package_diagram", "draw_component_diagram", "draw_deployment_diagram",
                           "draw_use_case_diagram"]  # 상태도·액티비티도는 전이·흐름뿐이라 없다


@pytest.mark.parametrize("name", TRUNK_TOOLS)
def test_tools_taking_inheritance_tell_how_to_share_one_trunk(name):
    # 도구 설명에 관계 필드가 그대로 들어가는 것은 test_each_tool_carries_its_flow_and_tips_…가 본다
    spec = PLACED_TOOLS[name][2]
    trunks = [t for t in spec.relations.values() if t.trunk]
    assert trunks
    text = guide.relation_fields(spec)
    noun, edge = spec.words.noun, spec.words.edge
    pairs = ", ".join(f"{t.label}끼리" for t in trunks)  # 클래스도·패키지도는 "상속끼리, 실체화끼리", 유즈케이스도는 "일반화끼리"
    for phrase in (f"  - 공유 줄기: 같은 부모(to)로 가는 {pairs}는 여러 선을 한 줄기로 모아 삼각형 하나를 함께 쓰게 "
                   "그려도 된다. 삼각형이 정확히 같은 자리에 그려지면 그 선들이 포개져도 불합격이 아니다",
                   "부모를 위에, 자식들을 그 아래 한 줄에 두고", " 이렇게 준다:\n    - 가운데 x·y:",
                   f"    - 가운데 x·y: 결과의 {noun} 자리에서 왼 + 폭/2, 위 + 높이/2",
                   f"    - 줄기 높이 y는 부모 {noun}의 아래 {edge}",
                   f"자식 {noun}들의 위 {edge} 사이 가운데쯤에 정한다",
                   f"부모 아래 {edge}에서 삼각형 길이 {boxdiagram.TRIANGLE[0]}px보다 가까우면 입력 오류다",
                   "    - 자식(from)마다 via에 [자식 가운데 x, y]와 [부모 가운데 x, y] 두 점을 준다",
                   "자식 가운데 x가 부모 가운데 x와 같으면 두 점이 같아지니 [부모 가운데 x, y] 하나만 준다"):
        assert phrase in text, phrase
    outside = any(s.outside_name for s in spec.shapes.values())
    within = ", 모양 자리가 덧붙어 있으면 모양 자리로" if outside else ""
    named = ", 부모의 모양 밖 이름이 오른쪽에 있거나" if outside else ""
    two = ("    - 같은 부모로 상속·실체화가 함께 오면 종류마다 줄기를 따로 둔다",
           f"세로 줄 x2 = 부모 오른쪽 {edge}의 x(왼 + 폭{within}) + {guide.TRUNK_SIDE}, 줄기 높이 y2 = y + {guide.TRUNK_SPLIT}"
           "(첫 줄기보다 아래, 자식 쪽)",
           "via에 [자식 가운데 x, y2], [x2, y2], [x2, 부모 가운데 y] 세 점을 주어",
           "자식 가운데 x가 x2와 같으면 [x2, 부모 가운데 y] 하나만 준다.",
           f"걸리거나, 부모 오른쪽 {edge}에 다른 선이 닿거나{named}, 첫 종류 자식의 가운데 x가 x2에서 {guide.TRUNK_NEAR}px "
           f"안이면 왼쪽으로 거울처럼 x2 = 부모 왼쪽 {edge}의 x(왼{within}) − {guide.TRUNK_SIDE}로 두어",
           f"왼쪽도 그렇게 막히면 걸린 {noun}를 옮기거나 자식 차례를 바꾼다.",
           f"y2가 자식 {noun}들의 위 {edge}보다 {guide.TRUNK_CLEAR}px 이상 위여야 한다 — 부모와 자식 사이를 "
           f"{guide.TRUNK_ROOM}px 이상 띄우고, y를 가운데보다 아래로 내리지 않는다. y2를 y보다 위에 두면 첫 줄기와 포개진다.")
    for phrase in two:  # 줄기 종류가 하나인 도구(유즈케이스도)에는 두 줄기를 나누는 법이 없다
        assert (phrase in text) == (len(trunks) > 1), phrase
    # 가운데는 그 도구의 결과에 덧붙는 것으로 셈한다 — 패키지를 받는 도구는 향하는 점, 모양 밖 이름이 있는 도구(유즈케이스도의
    # 액터·컴포넌트도의 막대사탕)는 모양 자리
    aims = any(boxdiagram.aims_off_center(s) for s in spec.shapes.values())
    assert ("향하는 점이 덧붙어 있으면 그 점을 쓴다" in text) == aims == ("package" in spec.shapes)
    assert ("모양 자리가 덧붙어 있으면 모양 자리로 셈한다" in text) == outside
    assert ('모양 밖 이름은 name_side "left"·"right"로 옆에 쓴다 — 위·아래면 줄기가 이름을 지난다' in text) == outside


def test_trunk_numbers_fit_together():
    # 둘째 줄기를 옆 변으로 들이는 끝 구간이 끝 모양보다 길고(짧으면 입력 오류), 가장 좁은 간격에서 y를 가운데에 두면 둘째 줄기가
    # 자식 위 변에서 TRUNK_CLEAR 떨어진다. 붙어 감 판정(BOX_CLEARANCE)보다 넉넉하다
    # 가장 좁은 간격에서 첫 줄기를 가운데에 두어도 첫 줄기 끝 구간이 끝 모양보다 길다
    for name in TRUNK_TOOLS:
        spec = PLACED_TOOLS[name][2]
        longest = max(t.end.length for t in spec.relations.values() if t.trunk and t.end is not None)
        assert guide.TRUNK_SIDE > longest and guide.TRUNK_ROOM / 2 > longest
    assert guide.TRUNK_ROOM / 2 - guide.TRUNK_SPLIT >= guide.TRUNK_CLEAR > boxcheck.BOX_CLEARANCE
    assert guide.TRUNK_NEAR > boxcheck.OVERLAP_GAP


NUM = r"(-?[\d.]+)"
PLACE = re.compile(rf"([^\s(),:]+)\({NUM}, {NUM}, {NUM}×{NUM}(?:, 모양 {NUM}, {NUM}, {NUM}×{NUM})?(?:, 향하는 점 {NUM}, {NUM})?\)")
INNER = {"kind": "class", "name": "Inner", "in": "P", "left": 300, "top": 44}  # 부모 패키지를 오른쪽·아래로 넓힌다


def middles(name, field, args):
    """도구를 불러 결과 글의 자리에서 요소마다 (자리, 가운데 x, 가운데 y, 향하는 점이 붙었는지)를 설명대로 읽는다 — 모양 자리가
    덧붙어 있으면 자리는 모양 자리이고, 향하는 점이 덧붙어 있으면 그 점이 가운데다."""
    (r,) = run(server.mcp, (name, args))[2]
    out = {}
    for key, *nums in PLACE.findall(text(r)):
        left, top, width, height = map(float, nums[4:8] if nums[4] else nums[:4])
        aim = tuple(map(float, nums[8:])) if nums[8] else (left + width / 2, top + height / 2)
        out[key] = ((left, top, width, height), *aim, bool(nums[8]))
    assert set(out) == {b.get("id", b.get("name")) for b in args[field]}, text(r)
    return out


@pytest.mark.parametrize("name, field, parent, children, more, kind, child_top, points", [
    ("draw_class_diagram", "classes", {"kind": "class"}, "class", [], "generalization", 120, [2, 1, 2]),
    ("draw_class_diagram", "classes", {"kind": "interface"}, "class", [], "realization", 120, [2, 1, 2]),
    ("draw_package_diagram", "elements", {"kind": "class"}, "class", [], "generalization", 120, [2, 1, 2]),
    ("draw_package_diagram", "elements", {"kind": "package"}, "package", [], "generalization", 120, [2, 1, 2]),
    ("draw_package_diagram", "elements", {"kind": "package", "width": 500}, "package", [], "generalization", 120, [2, 2, 2]),
    ("draw_package_diagram", "elements", {"kind": "package"}, "package", [INNER], "generalization", 180, [2, 2, 2]),
    ("draw_component_diagram", "elements", {"kind": "component"}, "component", [], "generalization", 120, [2, 1, 2]),
    ("draw_deployment_diagram", "elements", {"kind": "node"}, "node", [], "generalization", 120, [2, 1, 2]),
])
def test_shared_trunk_given_as_the_description_says_passes(tmp_path, name, field, parent, children, more, kind, child_top,
                                                          points):
    """부모 하나·자식 셋을 놓고, 결과의 자리에서 가운데 x(향하는 점이 덧붙어 있으면 그 x)를 읽어 설명대로 꺾는 점을 준다.
    폭을 같게 준 가운데 자식은 부모와 x가 같아 점 하나를 받는다. 넓은 부모 패키지는 향하는 점이 가운데에서 멀다."""
    boxes = [{**parent, "name": "P", "left": 200, "top": 0}, *more]
    boxes += [{"kind": children, "name": f"C{i}", "left": left, "top": child_top, "width": 140}
              for i, left in enumerate((0, 200, 400))]
    boxes[0].setdefault("width", 140)
    args = {"file_name": "trunk", field: boxes, "out_dir": str(tmp_path)}
    m = middles(name, field, args)
    assert m["P"][3] == (parent["kind"] == "package")
    (_, parent_top, _, parent_height), px = m["P"][0], m["P"][1]
    parent_bottom = parent_top + parent_height
    y = (parent_bottom + child_top) / 2
    assert y - parent_bottom > boxdiagram.TRIANGLE[0]
    via = {k: [[px, y]] if m[k][1] == px else [[m[k][1], y], [px, y]] for k in ("C0", "C1", "C2")}
    assert [len(v) for v in via.values()] == points
    relations = [{"kind": kind, "from": k, "to": "P", "via": v} for k, v in via.items()]
    (r,) = run(server.mcp, (name, {**args, "relations": relations}))[2]
    assert not r.is_error and text(r).startswith("합격"), text(r)


@pytest.mark.parametrize("kind, more, passes", [
    ("actor", {"name_side": "right"}, True),
    ("actor", {"name_side": "left"}, True),
    ("actor", {}, False),  # 이름이 아래(기본)면 자식 줄기가 부모 이름을 지난다 — 배치 요령이 이름을 옆에 두라고 한다
    ("actor", {"name_side": "top"}, False),  # 위면 자식 제 이름을 지난다 — 설명이 이름을 옆에 쓰라고 한다
    ("use_case", {}, True),
])
def test_use_case_trunk_given_as_the_description_says(tmp_path, kind, more, passes):
    """유즈케이스도 일반화 — 액터는 결과에 덧붙는 모양 자리(사람 모양)로 가운데와 위·아래 변을 셈한다."""
    parent = {"kind": kind, "name": "P", "left": 200, "top": 0, **more}
    first = {"file_name": "trunk", "elements": [parent], "out_dir": str(tmp_path)}
    (left, top, width, height), px, _, _ = middles("draw_use_case_diagram", "elements", first)["P"]
    child_top = top + height + 60
    boxes = [parent] + [{**more, "kind": kind, "name": f"C{i}", "left": x, "top": child_top} for i, x in enumerate((0, 200, 400))]
    args = {"file_name": "trunk", "elements": boxes, "out_dir": str(tmp_path)}
    m = middles("draw_use_case_diagram", "elements", args)
    tops = {m[f"C{i}"][0][1] for i in range(3)}
    y = (top + height + min(tops)) / 2
    via = {k: [[px, y]] if m[k][1] == px else [[m[k][1], y], [px, y]] for k in ("C0", "C1", "C2")}
    relations = [{"kind": "generalization", "from": k, "to": "P", "via": v} for k, v in via.items()]
    (r,) = run(server.mcp, ("draw_use_case_diagram", {**args, "relations": relations}))[2]
    assert not r.is_error and text(r).startswith("합격" if passes else "불합격"), text(r)


R, G = "realization", "generalization"
TWO_KINDS = (R, R, G, G), (0, 200, 400, 600)


def two_kinds(tmp_path, name, field, kinds, lefts, side="right", room=guide.TRUNK_ROOM, parent_kind="interface", more=(),
              others=()):
    """부모 P(왼 200, 폭 140) 아래 room 띄운 줄에 자식(kinds[i] — 실체화는 클래스, 상속은 인터페이스)을 두고, 설명대로 첫 종류는
    아래 변에, 다른 종류는 side 쪽 변에 모은다. more·others는 더 둘 요소·관계. (줄기를 준 그림 결과 글, 두 종류를 한 줄기로
    모은 그림 결과 글)."""
    parent = {"kind": parent_kind, "name": "P", "left": 200, "top": 0, "width": 140}
    (left, top, width, height), px, py, _ = middles(name, field, {"file_name": "trunk", field: [parent],
                                                                  "out_dir": str(tmp_path)})["P"]
    child_top = top + height + room
    boxes = [parent, *more] + [{"kind": "class" if k == R else "interface", "name": f"C{i}", "left": x, "top": child_top,
                                "width": 140} for i, (k, x) in enumerate(zip(kinds, lefts))]
    args = {"file_name": "trunk", field: boxes, "out_dir": str(tmp_path)}
    m = middles(name, field, args)
    assert m["P"][:3] == ((left, top, width, height), px, py)
    y = (top + height + child_top) / 2
    y2 = y + guide.TRUNK_SPLIT
    x2 = left + width + guide.TRUNK_SIDE if side == "right" else left - guide.TRUNK_SIDE
    trunks, together = list(others), list(others)
    for i, k in enumerate(kinds):
        cx = m[f"C{i}"][1]
        first = [[px, y]] if cx == px else [[cx, y], [px, y]]
        if k == kinds[0]:
            via = first
        else:
            via = [[x2, py]] if cx == x2 else [[cx, y2], [x2, y2], [x2, py]]
        trunks.append({"kind": k, "from": f"C{i}", "to": "P", "via": via})
        together.append({"kind": k, "from": f"C{i}", "to": "P", "via": first})
    return [text(r) for r in run(server.mcp, (name, {**args, "relations": trunks}), (name, {**args, "relations": together}))[2]]


@pytest.mark.parametrize("name, field", [("draw_class_diagram", "classes"), ("draw_package_diagram", "elements")])
@pytest.mark.parametrize("kinds", [(R, R, G, G), (G, R, G, R)])
@pytest.mark.parametrize("room", [guide.TRUNK_ROOM, 120])
def test_two_kinds_to_one_parent_given_as_the_description_says_pass(tmp_path, name, field, kinds, room):
    """인터페이스 P를 클래스가 실체화하고 인터페이스가 상속한다 — 첫 종류는 아래 변에, 다른 종류는 그보다 아래 줄기로 오른쪽 변에.
    부모와 자식 사이는 설명이 말하는 가장 좁은 간격(TRUNK_ROOM)과 넉넉한 간격. 두 종류를 한 줄기로 모으면 불합격이다."""
    passed, together = two_kinds(tmp_path, name, field, kinds, TWO_KINDS[1], room=room)
    assert passed.startswith("합격"), passed
    assert together.startswith("불합격")



@pytest.mark.parametrize("name_side, chosen, other", [("right", "left", "right"), ("left", "right", "left")])
def test_second_trunk_goes_away_from_the_parent_name_outside_the_shape(tmp_path, name_side, chosen, other):
    """컴포넌트도의 막대사탕처럼 이름을 모양 밖 옆에 쓰는 부모 — 설명대로 둘째 줄기는 이름 반대쪽 변(이름이 오른쪽이면 왼쪽 거울)에
    모으고 x2는 모양 자리로 셈한다. 이름 쪽 변으로 모으면 그 이름을 지난다."""
    parent = {"kind": "lollipop", "id": "P", "name": "Payment API", "left": 200, "top": 0, "name_side": name_side}
    first = {"file_name": "trunk", "elements": [parent], "out_dir": str(tmp_path)}
    (left, top, width, height), px, py, _ = middles("draw_component_diagram", "elements", first)["P"]
    y = top + height + 30
    kinds = (R, G, R, G)
    boxes = [parent] + [{"kind": "component", "name": f"C{i}", "left": x, "top": top + height + 60, "width": 140}
                        for i, x in enumerate(TWO_KINDS[1])]
    args = {"file_name": "trunk", "elements": boxes, "out_dir": str(tmp_path)}
    m = middles("draw_component_diagram", "elements", args)

    def draw_to(side):
        x2 = left + width + guide.TRUNK_SIDE if side == "right" else left - guide.TRUNK_SIDE
        relations = []
        for i, k in enumerate(kinds):
            cx = m[f"C{i}"][1]
            if k == kinds[0]:
                via = [[px, y]] if cx == px else [[cx, y], [px, y]]
            else:
                via = [[x2, py]] if cx == x2 else [[cx, y + guide.TRUNK_SPLIT], [x2, y + guide.TRUNK_SPLIT], [x2, py]]
            relations.append({"kind": k, "from": f"C{i}", "to": "P", "via": via})
        (r,) = run(server.mcp, ("draw_component_diagram", {**args, "relations": relations}))[2]
        return text(r)

    assert draw_to(chosen).startswith("합격"), draw_to(chosen)
    crossed = draw_to(other)
    assert crossed.startswith("불합격") and "이름 칸" in crossed

@pytest.mark.parametrize("side", ["right", "left"])
def test_two_kinds_to_a_package_parent_pass_on_either_side(tmp_path, side):
    # 패키지는 향하는 점(탭 오른쪽 몸통의 가운데)이 가운데다 — 왼쪽 변으로 들어가는 선도 탭 아래 몸통에 닿는다
    passed, _ = two_kinds(tmp_path, "draw_package_diagram", "elements", (G, R, G, R), TWO_KINDS[1], side=side,
                          parent_kind="package")
    assert passed.startswith("합격"), passed


@pytest.mark.parametrize("kinds, lefts, more", [
    ((R, R, G, G), TWO_KINDS[1], [{"kind": "class", "name": "S", "left": 360, "top": 0}]),  # x2 줄에 다른 상자
    ((G, R, G), (0, 500, 300), []),  # 첫 종류 자식 C2의 가운데 x(370)가 x2와 같다
])
def test_second_trunk_goes_to_the_left_when_the_right_column_is_taken(tmp_path, kinds, lefts, more):
    right, _ = two_kinds(tmp_path, "draw_class_diagram", "classes", kinds, lefts, more=more)
    assert right.startswith("불합격")
    left, _ = two_kinds(tmp_path, "draw_class_diagram", "classes", kinds, lefts, side="left", more=more)
    assert left.startswith("합격"), left


def test_second_trunk_goes_to_the_left_when_a_line_leaves_the_right_side(tmp_path):
    # 부모 오른쪽 변 가운데에서 같은 높이의 Q로 연관선이 나가면 둘째 줄기 끝 구간이 그 선과 포개진다
    more = [{"kind": "class", "name": "Q", "left": 480, "top": 0}]
    others = [{"kind": "association", "from": "P", "to": "Q", "navigable": "none"}]
    right, _ = two_kinds(tmp_path, "draw_class_diagram", "classes", (R, G, R, G), TWO_KINDS[1], more=more, others=others)
    assert right.startswith("불합격") and "선끼리 포개진다" in right
    left, _ = two_kinds(tmp_path, "draw_class_diagram", "classes", (R, G, R, G), TWO_KINDS[1], side="left", more=more,
                        others=others)
    assert left.startswith("합격"), left


@pytest.mark.parametrize("lefts, side", [((0, 300), "right"), ((300, 100), "left")])
def test_second_kind_child_right_under_the_column_gets_one_point(tmp_path, lefts, side):
    # 둘째 종류 자식의 가운데 x가 x2(오른쪽 370, 왼쪽 170)와 같으면 [x2, 부모 가운데 y] 하나만 — 세 점을 주면 앞 점과 같아 입력 오류
    kinds = (G, R) if side == "right" else (R, G)
    passed, _ = two_kinds(tmp_path, "draw_class_diagram", "classes", kinds, lefts, side=side)
    assert passed.startswith("합격"), passed


def test_relation_fields_say_where_lines_start_for_each_tool():
    # 클래스도는 상자 가운데, 새 도구는 요소 종류에 따로 적은 점(패키지는 탭 오른쪽 몸통의 가운데)
    assert "선은 상자 가운데에서 첫 꺾는 점(없으면 상대 상자 가운데)으로 가는 선이 상자 변과" in server.CLASS_TOOL
    assert "선은 요소 가운데(요소 종류에 따로 적은 모양은 그 점)에서" in packagediagram.TOOL
    assert "탭 오른쪽 몸통의 가운데를 향한다" in packagediagram.TOOL
    # 패키지도에는 모양 밖 이름이 있는 요소가 없어 그 결과 문장을 넣지 않는다
    assert guide.PLACES_RESULT in packagediagram.TOOL and guide.OUTSIDE_PLACES not in packagediagram.TOOL


def test_new_tools_tell_what_the_result_adds_to_the_places_of_their_shapes():
    aim = '  선이 모양 가운데에서 비켜난 점을 향하는 요소(kind "package")는 그 뒤에 그 점을 "향하는 점 x, y"로 덧붙인다'
    _, tools, _ = run(server.mcp)
    for name, (_, _, spec) in PLACED_TOOLS.items():
        if spec.extended:
            assert guide.places_result(spec) in tools[name].description, name
    assert guide.places_result(packagediagram.SPEC).startswith(guide.PLACES_RESULT + "\n" + aim)
    # 유즈케이스도: 액터의 모양 자리는 붙고, 액터·유즈케이스가 향하는 점은 가운데를 정수로 내린 점이라 붙이지 않는다
    assert guide.places_result(usecasediagram.SPEC) == guide.PLACES_RESULT + "\n" + guide.OUTSIDE_PLACES
    assert "향하는 점" not in server.CLASS_TOOL and "향하는 점" not in usecasediagram.TOOL
    # 비켜난 점을 향하는 모양도 모양 밖 이름도 없는 도구는 PLACES_RESULT만
    plain = boxdiagram.Spec({k: s for k, s in packagediagram.SPEC.shapes.items() if not boxdiagram.aims_off_center(s)},
                            classdiagram.RELATIONS, extended=True)
    assert guide.places_result(plain) == guide.PLACES_RESULT


def test_shapes_that_aim_aside_are_the_shapes_whose_lines_aim_away_from_the_middle():
    # aims_aside는 모양이 손으로 켠다 — 모든 도구의 모든 모양을 그려, 향하는 점이 모양 가운데에서 1px 넘게 비켜났는지와 맞춰 본다
    # (액터·유즈케이스는 가운데를 정수로 내린 점이라 0.5px 안이다)
    for _, _, spec in PLACED_TOOLS.values():
        for kind, shape in spec.shapes.items():
            element = {"kind": kind, "left": 0.5, "top": 0.5, **({"id": "X"} if spec.extended else {})}
            try:
                d = boxdiagram.render(spec, {spec.list_field: [{**element, "name": "X"}]})
            except InputError:  # 이름을 받지 않는 모양
                d = boxdiagram.render(spec, {spec.list_field: [element]})
            (p,) = d.layout.boxes
            l, t, r, b = p.shape_rect
            aside = abs(p.anchor[0] - (l + r) / 2) > 1 or abs(p.anchor[1] - (t + b) / 2) > 1
            assert boxdiagram.aims_off_center(shape) == aside, kind


def test_component_description_carries_the_lollipop_its_name_side_and_its_circle_place():
    # 컴포넌트도는 모양 밖 이름이 있는 제공 인터페이스 원을 받으므로 이름 쪽(바)과 모양 자리 결과 문장을 넣고, 연관 기본 방향은 '없음'이다
    tool = componentdiagram.TOOL
    for part in (guide.PLACED_ELEMENTS, guide.NEW_INPUT, guide.NESTING, guide.NAME_SIDE, guide.PLACES_RESULT,
                 guide.OUTSIDE_PLACES):
        assert part in tool
    assert 'kind "lollipop"' in tool and '"to"·"from"·"both"·"none"(기본)' in tool


def test_component_tool_returns_the_circle_place_of_a_lollipop(tmp_path):
    elements = [{"kind": "component", "name": "Order", "left": 0, "top": 0},
                {"kind": "lollipop", "name": "OrderApi", "left": 160, "top": 14, "name_side": "right"}]
    relations = [{"kind": "association", "from": "Order", "to": "OrderApi"}]
    (r,) = run(server.mcp, ("draw_component_diagram", {"file_name": "c", "elements": elements, "relations": relations,
                                                         "out_dir": str(tmp_path)}))[2]
    assert not r.is_error and text(r).startswith("합격"), text(r)
    assert "OrderApi(160, 14, " in text(r) and ", 모양 160, 14, 20×20)" in text(r)


def test_deployment_diagram_always_carries_its_english_name():
    # 이 레포는 "배치"를 자리 잡기 뜻으로도 쓰므로, 도구 설명·안내문·README 한국어 부분은 그림 이름에 늘 영어 이름을 붙인다
    korean = README.read_text(encoding="utf-8").split("\n## 한국어\n", 1)[1]
    for text in (deploymentdiagram.TOOL, server.INSTRUCTIONS, korean):
        assert "배치도" in text
        assert not re.search(r"배치도(?!(\*\*)?\(deployment diagram\))", text)
    assert deploymentdiagram.TIPS.startswith("배치도(deployment diagram) 자리 잡기 요령:")


def test_draws_saves_and_returns_the_check_the_boxes_and_the_image(tmp_path):
    r = draw(file_name="order", classes=ORDER, relations=PLACES, out_dir=str(tmp_path))
    assert not r.is_error
    saved = tmp_path / "order.png"
    t = text(r)
    assert t.startswith("합격")
    assert "상자 자리(왼, 위, 폭×높이): Order(0, 0, 90×48), Customer(200, 0, 90×48)" in t
    with Image.open(saved) as f:
        assert f"저장한 파일: {saved} ({f.width}×{f.height}px)" in t
        assert image(r).size == f.size


def test_failed_check_is_not_a_tool_error_and_still_saves(tmp_path):
    boxes = ORDER + [{"name": "Payment", "left": 100, "top": 0}]
    r = draw(file_name="order", classes=boxes, relations=PLACES, out_dir=str(tmp_path))
    assert not r.is_error
    assert text(r).startswith("불합격")
    assert (tmp_path / "order.png").exists()


def test_saves_under_diagrams_in_the_working_folder_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = draw(file_name="order", classes=ORDER)
    assert not r.is_error
    assert (tmp_path / "diagrams" / "order.png").exists()


def test_relative_out_dir_is_under_the_working_folder_and_png_suffix_is_not_doubled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    draw(file_name="주문 모델.png", classes=ORDER, out_dir="docs/img")
    assert [p.name for p in (tmp_path / "docs" / "img").iterdir()] == ["주문 모델.png"]


def test_same_file_name_overwrites(tmp_path):
    draw(file_name="order", classes=ORDER, out_dir=str(tmp_path))
    first = (tmp_path / "order.png").read_bytes()
    draw(file_name="order", classes=ORDER, relations=PLACES, out_dir=str(tmp_path))
    assert (tmp_path / "order.png").read_bytes() != first


def test_unwritable_folder_is_a_clear_error(tmp_path):
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("")
    r = draw(file_name="order", classes=ORDER, out_dir=str(blocker / "sub"))
    assert r.is_error
    assert text(r).startswith(f"그림을 저장하지 못했다 — out_dir {blocker / 'sub'}에")
    assert "out_dir에 절대 경로로 준다" in text(r)
    assert "상자 자리(왼, 위, 폭×높이): Order(0, 0, 90×48)" in text(r)


def test_home_of_an_unknown_user_is_an_error_not_a_folder_named_tilde(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = draw(file_name="order", classes=ORDER, out_dir="~no-such-user-for-cysuml/img")
    assert r.is_error
    assert text(r).startswith("out_dir '~no-such-user-for-cysuml/img'의 '~'를 홈 폴더로 풀 수 없다")
    assert list(tmp_path.iterdir()) == []


def test_unwritable_default_folder_names_the_working_folder(tmp_path, monkeypatch):
    (tmp_path / "diagrams").write_text("")
    monkeypatch.chdir(tmp_path)
    r = draw(file_name="order", classes=ORDER)
    assert r.is_error
    assert f"기본 폴더 {tmp_path / 'diagrams'}(서버 작업 폴더 아래 diagrams/)" in text(r)


def test_null_character_in_out_dir_is_a_clear_error(tmp_path):
    r = draw(file_name="order", classes=ORDER, out_dir=str(tmp_path) + "/a\0b")
    assert r.is_error
    assert text(r).startswith("그림을 저장하지 못했다 — out_dir ")
    assert list(tmp_path.iterdir()) == []


def test_blank_out_dir_means_the_default_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    draw(file_name="order", classes=ORDER, out_dir="   ")
    assert [p.name for p in tmp_path.iterdir()] == ["diagrams"]
    assert (tmp_path / "diagrams" / "order.png").exists()


def test_a_folder_in_the_way_of_the_file_is_an_error_and_leaves_no_temporary_file(tmp_path):
    (tmp_path / "order.png").mkdir()
    r = draw(file_name="order", classes=ORDER, out_dir=str(tmp_path))
    assert r.is_error
    assert [p.name for p in tmp_path.iterdir()] == ["order.png"]
    assert list((tmp_path / "order.png").iterdir()) == []


def test_saving_leaves_only_the_png(tmp_path):
    draw(file_name="order", classes=ORDER, out_dir=str(tmp_path))
    draw(file_name="order", classes=ORDER, relations=PLACES, out_dir=str(tmp_path))
    assert [p.name for p in tmp_path.iterdir()] == ["order.png"]


@pytest.mark.parametrize("name, problem", [
    ("", "비어 있다"),
    (" .png ", "비어 있다"),
    ("docs/order", "'/'"),
    ("a\\b", "'\\\\'"),
    ("tab\there", "'\\t'"),
    (".hidden", "점(.)으로 시작할 수 없다"),
    ("가" * 67, "너무 길다"),
])
def test_bad_file_name_is_an_input_error_and_nothing_is_written(tmp_path, monkeypatch, name, problem):
    monkeypatch.chdir(tmp_path)
    r = draw(file_name=name, classes=ORDER)
    assert r.is_error
    assert text(r).startswith("입력 오류 — 1건\n- ") and problem in text(r)
    assert list(tmp_path.iterdir()) == []


def test_input_errors_come_back_with_their_place_and_nothing_is_written(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = draw(file_name="order", classes=[{"name": "A", "left": "x", "top": 0}],
             relations=[{"kind": "association", "from": "A", "to": "B"}])
    assert r.is_error
    assert text(r).splitlines() == [
        "입력 오류 — 2건",
        "- classes[0].left: 수여야 한다(받은 값 'x')",
        "- relations[0].to: 이름이 'B'인 상자가 없다(있는 상자: 'A')",
    ]
    assert list(tmp_path.iterdir()) == []


def test_a_bad_file_name_comes_back_with_the_other_input_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = draw(file_name="docs/order", classes=[{"name": "A", "left": "x", "top": 0}])
    assert r.is_error
    lines = text(r).splitlines()
    assert lines[0] == "입력 오류 — 2건"
    assert lines[1].startswith("- file_name에 파일 이름으로 쓸 수 없는 글자가 있다: '/'")
    assert lines[2] == "- classes[0].left: 수여야 한다(받은 값 'x')"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("args, problems", [
    ({"classes": "nope"}, ["classes: 목록이어야 한다(받은 값 'nope')"]),
    ({"classes": ["A"], "relations": {"kind": "association"}},
     ["classes[0]: 객체여야 한다(받은 값 'A')", "relations: 목록이어야 한다(받은 값 {'kind': 'association'})"]),
])
def test_classes_and_relations_of_the_wrong_shape_come_back_from_the_reader(tmp_path, args, problems):
    r = draw(**{"file_name": "order", "out_dir": str(tmp_path), **args})
    assert r.is_error
    assert text(r).splitlines() == [f"입력 오류 — {len(problems)}건"] + [f"- {p}" for p in problems]
    assert list(tmp_path.iterdir()) == []


def test_classes_sent_as_a_json_string_still_draw(tmp_path):
    r = draw(file_name="order", classes=json.dumps(ORDER), relations=json.dumps(PLACES), out_dir=str(tmp_path))
    assert not r.is_error
    assert (tmp_path / "order.png").exists()


def test_scale_below_the_least_is_a_tool_error(tmp_path):
    r = draw(file_name="order", classes=ORDER, out_dir=str(tmp_path), scale=0.1)
    assert r.is_error
    assert list(tmp_path.iterdir()) == []


def test_too_big_to_draw_is_an_error_with_the_check_and_nothing_is_saved(tmp_path):
    far = [{"name": "A", "left": 0, "top": 0}, {"name": "B", "left": 100_000, "top": 0}]
    r = draw(file_name="far", classes=far, out_dir=str(tmp_path))
    assert r.is_error
    t = text(r)
    assert t.startswith("그림이 너무 커서 PNG를 그리지 않았다")
    assert f"배율 {SCALE:g}로는 PNG로 그리기에 너무 크다" in t
    assert "상자 자리" in t
    assert list(tmp_path.iterdir()) == []


def test_big_image_is_shrunk_for_the_answer_but_saved_at_full_size(tmp_path):
    wide = [{"name": "A", "left": 0, "top": 0}, {"name": "B", "left": 1200, "top": 0}]
    r = draw(file_name="wide", classes=wide, out_dir=str(tmp_path))
    shown = image(r)
    with Image.open(tmp_path / "wide.png") as f:
        full = f.size
    assert full[0] > server.MAX_IMAGE_EDGE
    assert shown.width == server.MAX_IMAGE_EDGE
    assert shown.height == round(full[1] * server.MAX_IMAGE_EDGE / full[0])
    assert f"긴 변을 {server.MAX_IMAGE_EDGE}px로 줄였다({shown.width}×{shown.height}px)" in text(r)


def test_scale_changes_the_saved_size(tmp_path):
    big = draw(file_name="big", classes=ORDER, out_dir=str(tmp_path))
    small = draw(file_name="small", classes=ORDER, out_dir=str(tmp_path), scale=0.8)
    assert not small.is_error
    assert image(small).width < image(big).width


def test_calls_at_the_same_time_all_draw(tmp_path):
    async def go():
        async with Client(server.mcp) as c:
            results = {}

            async def one(i):
                results[i] = await c.call_tool("draw_class_diagram", {
                    "file_name": f"d{i}", "classes": ORDER, "relations": PLACES, "out_dir": str(tmp_path)})
            async with anyio.create_task_group() as tg:
                for i in range(4):
                    tg.start_soon(one, i)
            return results
    results = anyio.run(go)
    assert not any(r.is_error for r in results.values())
    assert len({(tmp_path / f"d{i}.png").read_bytes() for i in range(4)}) == 1


def test_readme_examples_draw_and_pass(tmp_path):
    blocks = [json.loads(b) for b in re.findall(r"```json\n(.*?)```", README.read_text(encoding="utf-8"), re.S)]
    examples = [b for b in blocks if "file_name" in b]
    assert sorted(b["file_name"] for b in examples) == sorted(EXAMPLES)
    for b in examples:
        (r,) = run(server.mcp, (EXAMPLES[b["file_name"]], {**b, "out_dir": str(tmp_path)}))[2]
        assert not r.is_error and text(r).startswith("합격"), text(r)


def test_command_serves_over_stdio(tmp_path):
    params = StdioServerParameters(command=sys.executable, args=["-m", "cysuml"], cwd=str(tmp_path))
    _, tools, results = run(params, CLASS, SEQUENCE)
    assert {"draw_class_diagram", "draw_sequence_diagram"} <= set(tools)
    assert not any(r.is_error for r in results)
    assert sorted(p.name for p in (tmp_path / "diagrams").iterdir()) == ["checkout.png", "order.png"]


# ---------------------------------------------------------------- 교류도


def test_draws_a_sequence_diagram_and_returns_the_check_and_the_image_without_box_places(tmp_path):
    r = draw_seq(file_name="checkout", participants=PEOPLE, messages=TALKS, frames=CHECKS,
                 notes=["결제는 카드만 받는다"], out_dir=str(tmp_path))
    assert not r.is_error
    lines = text(r).splitlines()
    assert lines[0] == sequencecheck.Report.PASSED
    assert lines[1].startswith("알림 — 그림 크기: 논리 좌표 ")
    saved = tmp_path / "checkout.png"
    with Image.open(saved) as f:
        assert lines[2:] == [f"저장한 파일: {saved} ({f.width}×{f.height}px)"]
        assert image(r).size == f.size


def test_participants_alone_draw(tmp_path):
    r = draw_seq(file_name="alone", participants=PEOPLE, out_dir=str(tmp_path))
    assert not r.is_error
    assert (tmp_path / "alone.png").exists()


def test_null_sequence_lists_are_not_given(tmp_path):
    r = draw_seq(file_name="checkout", participants=PEOPLE, messages=TALKS, frames=None, notes=None,
                 out_dir=str(tmp_path))
    assert not r.is_error


def test_sequence_input_errors_come_back_with_their_place_and_nothing_is_written(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = draw_seq(file_name="docs/checkout", participants=PEOPLE,
                 messages=[{"from": "Shop", "to": "Bank", "name": "pay()"},
                           {"from": "Shop", "to": "Shop", "name": "log()"}],
                 frames=[{"kind": "opt", "first": 0, "last": 5}], notes=[""])
    assert r.is_error
    lines = text(r).splitlines()
    assert lines[0] == "입력 오류 — 5건"
    assert lines[1].startswith("- file_name에 파일 이름으로 쓸 수 없는 글자가 있다: '/'")
    assert lines[2] == "- messages[0].to: 이름이 'Bank'인 참여자가 없다(있는 참여자: 'Customer', 'Shop', 'Payment')"
    assert lines[3].startswith("- messages[1]: 자기 자신('Shop')에게 보내는 메시지는 그리지 않는다")
    assert lines[4] == "- frames[0].last: 0~1 사이여야 한다(받은 값 5)"
    assert lines[5] == "- notes[0]: 비어 있다"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("args, problem", [
    ({"participants": "nope"}, "participants: 목록이어야 한다(받은 값 'nope')"),
    ({"participants": None}, "participants: 목록이어야 한다(받은 값 None)"),
    ({"participants": PEOPLE, "notes": "메모"}, "notes: 목록이어야 한다(받은 값 '메모')"),
])
def test_sequence_lists_of_the_wrong_shape_come_back_from_the_reader(tmp_path, args, problem):
    r = draw_seq(**{"file_name": "checkout", "out_dir": str(tmp_path), **args})
    assert r.is_error
    assert text(r).splitlines() == ["입력 오류 — 1건", f"- {problem}"]
    assert list(tmp_path.iterdir()) == []


def test_sequence_lists_sent_as_json_strings_still_draw(tmp_path):
    r = draw_seq(file_name="checkout", participants=json.dumps(PEOPLE), messages=json.dumps(TALKS),
                 frames=json.dumps(CHECKS), notes=json.dumps(["메모"]), out_dir=str(tmp_path))
    assert not r.is_error
    assert (tmp_path / "checkout.png").exists()


def test_a_failed_sequence_check_says_it_is_a_cysuml_bug_and_still_saves(tmp_path, monkeypatch):
    finding = Finding("text_on_bar", ("messages[1]",), (0, 0, 10, 10), "글자가 막대를 가린다.", sequencecheck.TEXT_HINT)
    monkeypatch.setattr(sequencecheck, "find", lambda layout: (finding,))
    r = draw_seq(file_name="checkout", participants=PEOPLE, messages=TALKS, out_dir=str(tmp_path))
    assert not r.is_error
    lines = text(r).splitlines()
    assert lines[0] == "불합격 — 1건" + sequencecheck.Report.FAILED
    assert lines[1] == f"1. 글자가 막대를 가린다. {sequencecheck.TEXT_HINT}"
    assert (tmp_path / "checkout.png").exists()


def _layout_bug(diagram):
    raise sequencediagram.LayoutError("배치 버그: 시험")


def test_a_layout_bug_is_an_error_with_a_way_around_and_nothing_is_written(tmp_path, monkeypatch):
    monkeypatch.setattr(sequencediagram, "layout", _layout_bug)
    r = draw_seq(file_name="checkout", participants=PEOPLE, messages=TALKS, out_dir=str(tmp_path))
    assert r.is_error
    assert text(r) == ("교류도를 배치하지 못했다 — 배치 버그: 시험. 파일은 저장하지 않았다. 입력은 맞는데 cysUML이 자리를 "
                       f"찾지 못한 것이라, 비켜 가려면 {server.SEQUENCE_WAY_AROUND}.")
    assert server.SEQUENCE_WAY_AROUND in server.SEQUENCE_FLOW
    assert list(tmp_path.iterdir()) == []


def test_another_runtime_error_is_not_told_as_a_layout_bug(tmp_path, monkeypatch):
    def broken(diagram):
        raise RuntimeError("코드 실수")
    monkeypatch.setattr(sequencediagram, "layout", broken)
    r = draw_seq(file_name="checkout", participants=PEOPLE, messages=TALKS, out_dir=str(tmp_path))
    assert r.is_error
    assert "배치하지 못했다" not in text(r)
    assert list(tmp_path.iterdir()) == []


def test_a_bad_file_name_is_told_before_a_layout_bug(tmp_path, monkeypatch):
    monkeypatch.setattr(sequencediagram, "layout", _layout_bug)
    r = draw_seq(file_name="", participants=PEOPLE, out_dir=str(tmp_path))
    assert r.is_error
    assert text(r).splitlines() == ["입력 오류 — 1건", "- file_name이 비어 있다"]


def test_a_sequence_too_big_to_draw_is_an_error_with_the_check_and_nothing_is_saved(tmp_path):
    r = draw_seq(file_name="huge", participants=PEOPLE, messages=TALKS, out_dir=str(tmp_path), scale=40)
    assert r.is_error
    lines = text(r).splitlines()
    assert lines[0] == "그림이 너무 커서 PNG를 그리지 않았다(파일도 저장하지 않았다)."
    assert lines[1] == sequencecheck.Report.PASSED
    assert lines[2].endswith(f"배율 40로는 PNG로 그리기에 너무 크다 — {sequencecheck.Report.SHRINK}")
    assert len(lines) == 3
    assert list(tmp_path.iterdir()) == []


def test_a_sequence_that_cannot_be_saved_is_an_error_with_the_check(tmp_path):
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("")
    r = draw_seq(file_name="checkout", participants=PEOPLE, messages=TALKS, out_dir=str(blocker / "sub"))
    assert r.is_error
    lines = text(r).splitlines()
    assert lines[0].startswith(f"그림을 저장하지 못했다 — out_dir {blocker / 'sub'}에")
    assert lines[1:3] == ["", sequencecheck.Report.PASSED]
    assert len(lines) == 4


def test_a_long_sequence_is_shrunk_for_the_answer_but_saved_at_full_size(tmp_path):
    talks = [{"from": "Customer", "to": "Shop", "name": f"step{i}()"} for i in range(40)]
    r = draw_seq(file_name="long", participants=PEOPLE, messages=talks, out_dir=str(tmp_path))
    assert not r.is_error
    with Image.open(tmp_path / "long.png") as f:
        full = f.size
    assert full[1] > server.MAX_IMAGE_EDGE
    assert image(r).height == server.MAX_IMAGE_EDGE
    assert f"긴 변을 {server.MAX_IMAGE_EDGE}px로 줄였다" in text(r)


def test_class_and_sequence_calls_at_the_same_time_all_draw(tmp_path):
    async def go():
        async with Client(server.mcp) as c:
            results = {}

            async def one(i):
                name, args = (CLASS, SEQUENCE)[i % 2]
                results[i] = await c.call_tool(name, {**args, "file_name": f"d{i}", "out_dir": str(tmp_path)})
            async with anyio.create_task_group() as tg:
                for i in range(6):
                    tg.start_soon(one, i)
            return results
    results = anyio.run(go)
    assert not any(r.is_error for r in results.values())
    assert len({(tmp_path / f"d{i}.png").read_bytes() for i in range(0, 6, 2)}) == 1
    assert len({(tmp_path / f"d{i}.png").read_bytes() for i in range(1, 6, 2)}) == 1
