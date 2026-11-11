import base64
import io
import json
import sys

import anyio
import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from PIL import Image

from cysuml import classcheck, server
from cysuml.canvas import SCALE

ORDER = [{"name": "Order", "left": 0, "top": 0}, {"name": "Customer", "left": 200, "top": 0}]
PLACES = [{"kind": "association", "from": "Order", "to": "Customer", "name": "places"}]


def run(target, *calls):
    """target(서버 객체나 stdio 실행 정보)에 붙어 도구 목록과 calls(도구 인자)마다 결과를 받는다."""
    async def go():
        async with Client(target) as c:
            tools = (await c.list_tools()).tools
            return c.instructions, tools, [await c.call_tool("draw_class_diagram", a) for a in calls]
    return anyio.run(go)


def draw(**args):
    return run(server.mcp, args)[2][0]


def text(result):
    return result.content[0].text


def image(result):
    (block,) = [b for b in result.content if b.type == "image"]
    assert block.mime_type == "image/png"
    return Image.open(io.BytesIO(base64.b64decode(block.data)))


def test_lists_one_tool_with_flow_and_tips_in_its_description_and_the_instructions():
    instructions, tools, _ = run(server.mcp)
    (tool,) = tools
    assert tool.name == "draw_class_diagram"
    assert tool.input_schema["required"] == ["file_name", "classes"]
    props = tool.input_schema["properties"]
    assert set(props) == {"file_name", "classes", "relations", "out_dir", "scale"}
    for key in ("classes", "relations"):
        assert props[key]["type"] == "array" and props[key]["items"] == {"type": "object"}
    for part in (server.FLOW, server.TIPS):
        assert part in tool.description and part in instructions


def test_description_names_every_failure_kind_in_check_order():
    assert tuple(server.KIND_NAMES) == classcheck.KINDS
    assert ", ".join(server.KIND_NAMES.values()) in server.CLASS_TOOL


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


def test_command_serves_over_stdio(tmp_path):
    params = StdioServerParameters(command=sys.executable, args=["-m", "cysuml"], cwd=str(tmp_path))
    _, tools, (r,) = run(params, {"file_name": "order", "classes": ORDER, "relations": PLACES})
    assert [t.name for t in tools] == ["draw_class_diagram"]
    assert not r.is_error
    assert (tmp_path / "diagrams" / "order.png").exists()
