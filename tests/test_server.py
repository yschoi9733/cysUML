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

from cysuml import (boxcheck, boxdiagram, classcheck, deploymentdiagram, guide, packagediagram, sequencecheck,
                    sequencediagram, server, usecasediagram)
from cysuml.canvas import SCALE
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
    ("draw_deployment_diagram", ["file_name", "elements"], ("elements", "relations"), ()),
    ("draw_use_case_diagram", ["file_name", "elements"], ("elements", "relations"), ()),
    ("draw_sequence_diagram", ["file_name", "participants"], ("participants", "messages", "frames"), ("notes",)),
]
EXAMPLES = {  # README 예시 file_name → 도구. 예시를 더하면 줄을 더한다
    "order": "draw_class_diagram",
    "packages": "draw_package_diagram",
    "deployment": "draw_deployment_diagram",
    "use-cases": "draw_use_case_diagram",
    "checkout": "draw_sequence_diagram",
}
PLACED_TOOLS = {  # AI가 배치하는 도구 → 그 도구 설명에 있어야 하는 배치 요령, 날 수 있는 불합격 종류, 그 도구의 말
    "draw_class_diagram": (server.CLASS_TIPS, classcheck.KINDS, boxdiagram.BOX_WORDS),
    "draw_package_diagram": (packagediagram.TIPS, boxcheck.KINDS, boxdiagram.ELEMENT_WORDS),
    "draw_deployment_diagram": (deploymentdiagram.TIPS, boxcheck.KINDS, boxdiagram.ELEMENT_WORDS),
    "draw_use_case_diagram": (usecasediagram.TIPS, boxcheck.KINDS, boxdiagram.ELEMENT_WORDS),
}


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
    for name, (tips, kinds, words) in PLACED_TOOLS.items():
        tool = tools[name].description
        assert guide.flow(kinds, words) in tool and tips in tool
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
    from cysuml import boxdiagram, classdiagram
    kinds = ("association", "dependency", "generalization")
    spec = boxdiagram.Spec(classdiagram.CLASS_SHAPES, {k: classdiagram.RELATIONS[k] for k in kinds}, navigable="none")
    text = guide.relation_fields(spec)
    assert '  - kind(필수): "association"·"dependency"·"generalization".' in text
    assert "의존·상속은 from이 의존하는 쪽·자식이고 화살촉·삼각형이 to 쪽에 붙는다." in text and "마름모" not in text
    assert '연관만 쓴다. navigable은 화살촉을 둘 쪽 "to"·"from"·"both"·"none"(기본)이다.' in text


def test_relation_fields_say_where_lines_start_for_each_tool():
    # 클래스도는 상자 가운데, 새 도구는 요소 종류에 따로 적은 점(패키지는 탭 오른쪽 몸통의 가운데)
    assert "선은 상자 가운데에서 첫 꺾는 점(없으면 상대 상자 가운데)으로 가는 선이 상자 변과" in server.CLASS_TOOL
    assert "선은 요소 가운데(요소 종류에 따로 적은 모양은 그 점)에서" in packagediagram.TOOL
    assert "탭 오른쪽 몸통의 가운데를 향한다" in packagediagram.TOOL
    # 패키지도에는 모양 밖 이름이 있는 요소가 없어 그 결과 문장을 넣지 않는다
    assert guide.PLACES_RESULT in packagediagram.TOOL and guide.OUTSIDE_PLACES not in packagediagram.TOOL


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
