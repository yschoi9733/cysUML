import copy
import math

import pytest
from PIL import Image

from cysuml import boxcheck as K
from cysuml import boxdiagram as B
from cysuml import classdiagram as C
from cysuml import geom as G
from cysuml import text as T
from cysuml.canvas import BG_MARGIN, Line, Mask, Polygon, Rect, Text


def two_boxes(**relation):
    """A(0, 0)와 B(300, 0) — 둘 다 90×48이고 가운데가 같은 높이(24)라 선은 (90, 24)에서 (300, 24)까지다."""
    data = {"classes": [{"name": "A", "left": 0, "top": 0}, {"name": "B", "left": 300, "top": 0}]}
    if relation:
        data["relations"] = [{"from": "A", "to": "B", **relation}]
    return data


def owned(drawing, owner, typ):
    return [r for r in drawing.canvas.records if r.owner == owner and isinstance(r, typ)]


def flat(points):
    return [v for p in points for v in p]


def rect_of(drawing, name):
    (r,) = owned(drawing, name, Rect)
    return r.left, r.top, r.left + r.width, r.top + r.height


def on_edge(p, rect, eps=1e-9):
    l, t, r, b = rect
    x, y = p
    on_side = (abs(x - l) < eps or abs(x - r) < eps) and t - eps <= y <= b + eps
    on_cap = (abs(y - t) < eps or abs(y - b) < eps) and l - eps <= x <= r + eps
    return on_side or on_cap


def arrow_heads(drawing, owner):
    """열린 화살촉(갈래 끝 → tip → 갈래 끝의 세 점 선)의 tip들."""
    return [r.points[1] for r in owned(drawing, owner, Line) if len(r.points) == 3 and r.dash is None]


START, END = (90.0, 24.0), (300.0, 24.0)
DIAMOND_AT_START = [START, (99, 30), (108, 24), (99, 18)]
TRIANGLE_AT_END = [END, (282, 15), (282, 33)]


@pytest.mark.parametrize("relation, dash, polygon, arrows", [
    ({"kind": "association"}, None, None, [END]),
    ({"kind": "association", "navigable": "both"}, None, None, [START, END]),  # 끝 모양은 from 쪽, to 쪽 차례로 그린다
    ({"kind": "association", "navigable": "from"}, None, None, [START]),
    ({"kind": "association", "navigable": "none"}, None, None, []),
    ({"kind": "aggregation"}, None, ("white", DIAMOND_AT_START), [END]),
    ({"kind": "aggregation", "navigable": "none"}, None, ("white", DIAMOND_AT_START), []),
    ({"kind": "composition"}, None, ("black", DIAMOND_AT_START), [END]),
    ({"kind": "generalization"}, None, ("white", TRIANGLE_AT_END), []),
    ({"kind": "realization"}, (5.0, 4.0), ("white", TRIANGLE_AT_END), []),
    ({"kind": "dependency"}, (5.0, 4.0), None, [END]),
])
def test_each_relation_kind_draws_its_line_and_end_shapes(relation, dash, polygon, arrows):
    d = C.render(two_boxes(**relation))
    lines = owned(d, "A->B", Line)
    assert lines[0].points == (START, END) and lines[0].dash == dash
    assert arrow_heads(d, "A->B") == arrows
    polys = owned(d, "A->B", Polygon)
    if polygon is None:
        assert polys == []
    else:
        (p,) = polys
        assert p.fill == polygon[0]
        assert flat(p.points) == pytest.approx(flat(polygon[1]))


def test_relation_lines_are_drawn_under_boxes_and_labels_on_top():
    d = C.render(two_boxes(kind="association", name="has", to_multiplicity="1"))
    kinds = [type(r).__name__ if r.owner == "A->B" else "box" for r in d.canvas.records]
    first_box, last_box = kinds.index("box"), len(kinds) - 1 - kinds[::-1].index("box")
    assert set(kinds[:first_box]) == {"Line"}
    assert set(kinds[last_box + 1:]) == {"Mask", "Text"}


def test_drawing_hands_over_each_relations_records():
    d = C.render({"classes": [{"name": "A", "left": 0, "top": 0}, {"name": "B", "left": 300, "top": 0}],
                  "relations": [{"kind": "association", "from": "A", "to": "B", "navigable": "both", "name": "has",
                                 "to_multiplicity": "1"},
                                {"kind": "realization", "from": "B", "to": "A", "via": [[345, 100], [45, 100]]},
                                {"kind": "composition", "from": "A", "to": "B", "via": [[45, -60], [345, -60]]}]})
    for drawn, placed in zip(d.drawn, d.layout.relations, strict=True):
        assert drawn.line.points == placed.points
        texts = [t for lines in drawn.labels for t in lines]
        assert all(r in d.canvas.records and r.owner == placed.owner for r in (drawn.line, *drawn.heads, *texts))
        assert [[t.text for t in lines] for lines in drawn.labels] == [list(lab.lines) for lab in placed.labels]
    heads = [[type(h).__name__ for h in drawn.heads] for drawn in d.drawn]
    assert heads == [["Line", "Line"], ["Polygon"], ["Polygon", "Line"]]  # 두 화살촉 / 삼각형 / 마름모와 화살촉
    assert len(d.drawn[0].labels) == 2 and d.drawn[1].labels == ()


def test_box_grows_to_fit_text_keeping_left_and_top():
    row = "-aVeryLongAttributeName: SomeLongTypeName = 42"
    d = C.render({"classes": [{"name": "Wide", "left": 10, "top": 20, "attributes": [row],
                               "operations": ["+a()", "+b()"]}]})
    (r,) = owned(d, "Wide", Rect)
    assert (r.left, r.top) == (10, 20)
    assert r.width == math.ceil(T.text_width(row) + C.ROW_PAD) > C.MIN_WIDTH
    assert r.height == 24 + (10 + 15) + (10 + 2 * 15) + 4
    for t in owned(d, "Wide", Text):
        assert r.left < t.box[0] and t.box[2] < r.left + r.width
        assert r.top < t.box[1] and t.box[3] < r.top + r.height


def test_box_keeps_larger_given_size_and_minimum_width():
    d = C.render({"classes": [{"name": "Big", "left": 0, "top": 0, "width": 400, "height": 200},
                              {"name": "Small", "left": 500, "top": 0},
                              {"name": "Narrow", "left": 700, "top": 0, "width": 10}]})
    assert [(p.width, p.height) for p in d.layout.boxes] == [
        (400, 200), (C.MIN_WIDTH, 48), (math.ceil(T.text_width("Narrow", True) + C.NAME_PAD), 48)]


def test_korean_and_long_rows_fit_inside_every_box():
    data = {"classes": [
        {"name": "결제 수단 관리자", "kind": "abstract", "left": 0, "top": 0, "stereotype": "서비스",
         "attributes": [{"name": "최대 재시도 횟수", "type": "정수", "default": "3", "static": True}],
         "operations": [{"name": "승인하기", "params": ["금액: Money", "카드: Card"], "returns": "승인 결과"}]},
        {"name": "Color", "kind": "enum", "left": 400, "top": 0, "literals": ["RED", "초록"]},
    ]}
    d = C.render(data)
    for p in d.layout.boxes:
        l, t, r, b = p.rect
        for x in owned(d, p.key, Text):
            assert l < x.box[0] and x.box[2] < r and t < x.box[1] and x.box[3] < b, x.text


def test_line_ends_are_where_center_to_center_line_meets_box_edges():
    d = C.render({"classes": [{"name": "A", "left": 0, "top": 0, "width": 100, "height": 60},
                              {"name": "B", "left": 300, "top": 200, "width": 120, "height": 80}],
                  "relations": [{"kind": "association", "from": "A", "to": "B", "navigable": "none"}]})
    (line,) = owned(d, "A->B", Line)
    start, end = line.points
    a, b = rect_of(d, "A"), rect_of(d, "B")
    assert on_edge(start, a) and on_edge(end, b)
    assert start == pytest.approx((50 + 30 * 310 / 210, 60))
    ca, cb = (50, 30), (360, 240)
    for p in (start, end):
        assert (p[0] - ca[0]) * (cb[1] - ca[1]) == pytest.approx((p[1] - ca[1]) * (cb[0] - ca[0]))


def test_line_with_bends_starts_toward_first_and_ends_toward_last_bend():
    d = C.render({"classes": [{"name": "A", "left": 0, "top": 0, "width": 100, "height": 60},
                              {"name": "B", "left": 300, "top": 0, "width": 120, "height": 60}],
                  "relations": [{"kind": "dependency", "from": "A", "to": "B", "via": [[50, 150], [360, 150]]}]})
    line = owned(d, "A->B", Line)[0]
    assert line.points == ((50, 60), (50, 150), (360, 150), (360, 60))
    assert arrow_heads(d, "A->B") == [(360, 60)]


def test_self_relation_with_bends_is_drawn():
    d = C.render({"classes": [{"name": "Node", "left": 0, "top": 0, "width": 100, "height": 60}],
                  "relations": [{"kind": "association", "from": "Node", "to": "Node", "name": "next",
                                 "via": [[50, 120], [160, 120], [160, 30]]}]})
    line = owned(d, "Node->Node", Line)[0]
    assert line.points == ((50, 60), (50, 120), (160, 120), (160, 30), (100, 30))


def test_static_rows_are_underlined_and_push_the_next_row_down():
    d = C.render({"classes": [{"name": "Policy", "left": 0, "top": 0, "attributes": [
        {"name": "RATE", "type": "double", "default": "0.1", "static": True}, {"name": "name"}],
        "operations": [{"name": "of", "static": True}]}]})
    rows = [t for t in owned(d, "Policy", Text) if not t.bold]
    assert [t.text for t in rows] == ["-RATE: double = 0.1", "-name", "+of()"]
    assert rows[1].y - rows[0].y == C.ROW + C.STATIC_PAD
    underlines = [r for r in owned(d, "Policy", Line) if r.points[0][0] == C.ROW_LEFT]
    assert [r.points for r in underlines] == [
        ((5, rows[0].y + C.UNDERLINE), (5 + T.text_width(rows[0].text), rows[0].y + C.UNDERLINE)),
        ((5, rows[2].y + C.UNDERLINE), (5 + T.text_width(rows[2].text), rows[2].y + C.UNDERLINE)),
    ]
    assert underlines[0].points[0][1] < rows[1].box[1]


def test_member_text_from_objects_and_strings():
    d = C.render({"classes": [{"name": "Shop", "left": 0, "top": 0,
                               "attributes": ["+id: Long", {"name": "count", "visibility": ""},
                                              {"name": "tag", "visibility": "#", "type": "String", "default": "\"a\""}],
                               "operations": [{"name": "find", "params": ["id: Long", "all: bool"], "returns": "Item"},
                                              {"name": "reset", "visibility": "~"}]}]})
    assert [t.text for t in owned(d, "Shop", Text)] == [
        "Shop", "+id: Long", "count", "#tag: String = \"a\"", "+find(id: Long, all: bool): Item", "~reset()"]


def test_default_value_may_be_a_json_number_or_boolean():
    d = C.render({"classes": [{"name": "Cfg", "left": 0, "top": 0, "attributes": [
        {"name": "count", "type": "int", "default": 0}, {"name": "rate", "default": 0.5},
        {"name": "on", "type": "bool", "default": True}, {"name": "label", "default": "\"x\""}]}]})
    assert [t.text for t in owned(d, "Cfg", Text)][1:] == [
        "-count: int = 0", "-rate = 0.5", "-on: bool = true", "-label = \"x\""]


@pytest.mark.parametrize("box, keyword", [
    ({"kind": "interface", "stereotype": "interface"}, "«interface»"),
    ({"kind": "enum", "stereotype": "enumeration"}, "«enumeration»"),
    ({"kind": "enum", "stereotype": "enum"}, "«enumeration»"),
    ({"stereotype": "interface"}, "«interface»"),
    ({"kind": "interface", "stereotype": "Interface"}, "«interface»"),
    ({"kind": "enum", "stereotype": "Enumeration"}, "«enumeration»"),
    ({"kind": "abstract", "stereotype": "abstract"}, None),
    ({"kind": "interface", "stereotype": " interface "}, "«interface»"),
    ({"stereotype": " entity "}, "«entity»"),
    ({"kind": "abstract", "stereotype": "entity"}, "«entity»"),
    ({"kind": "enum", "stereotype": "flags"}, "«enumeration, flags»"),
])
def test_stereotype_that_repeats_the_kind_is_written_once(box, keyword):
    assert C.CLASS_SHAPE.keyword(C.parse({"classes": [{"name": "X", "left": 0, "top": 0, **box}]}).boxes[0]) == keyword


@pytest.mark.parametrize("box, texts, height", [
    ({"kind": "interface"}, [("«interface»", False, 12), ("X", True, 27)], 42),
    ({"kind": "interface", "stereotype": "remote", "operations": ["+go()"]},
     [("«interface, remote»", False, 12), ("X", True, 27), ("+go()", False, 38 + 12.5)], 42 + 25),
    ({"kind": "enum", "literals": ["ON", "OFF"]},
     [("«enumeration»", False, 12), ("X", True, 27), ("ON", False, 50.5), ("OFF", False, 65.5)], 42 + 40),
    ({"kind": "abstract"}, [("X", True, 13), ("{abstract}", False, 27)], 38 + 10 + 10 + 4),
    ({"stereotype": "entity"}, [("«entity»", False, 12), ("X", True, 27)], 38 + 10 + 10 + 4),
    ({}, [("X", True, 13)], 48),
])
def test_head_and_sections_by_kind(box, texts, height):
    d = C.render({"classes": [{"name": "X", "left": 0, "top": 0, **box}]})
    assert [(t.text, t.bold, t.y) for t in owned(d, "X", Text)] == texts
    assert d.layout.boxes[0].height == height


def test_interface_and_enum_hide_empty_sections_but_class_keeps_them():
    def section_lines(box):
        d = C.render({"classes": [{"name": "X", "left": 0, "top": 0, **box}]})
        return len([r for r in owned(d, "X", Line) if r.points[0][0] == 0])

    assert section_lines({}) == 2
    assert section_lines({"kind": "abstract"}) == 2
    assert section_lines({"kind": "interface"}) == 0
    assert section_lines({"kind": "interface", "attributes": ["+A"]}) == 1
    assert section_lines({"kind": "enum"}) == 1
    assert section_lines({"kind": "enum", "operations": ["+of()"]}) == 2


def touches_a_line(drawing, box):
    """글자의 흰 바탕이 관계선이나 선 끝 모양(그린 기록 그대로)에 닿는지."""
    owners = {r.owner for r in drawing.layout.relations}
    drawn = [r for r in drawing.canvas.records if r.owner in owners and isinstance(r, (Line, Polygon))]
    wide = G.grow(box, C.LABEL_CLEAR)
    return any(G.hits(p, q, wide) for p, q in G.outline(drawn))


def test_association_name_sits_on_the_middle_of_its_line_over_one_white_patch():
    # 이름은 선 가운데에 얹고, 글자 덩어리를 덮는 흰 바탕 하나(줄 상자 둘레 BG_MARGIN) 뒤로 선이 끊긴다
    d = C.render(two_boxes(kind="association", name="places"))
    (name,) = owned(d, "A->B", Text)
    assert (name.text, name.x, name.y, name.anchor, name.bg) == ("places", 195, 24, "mm", False)
    assert d.layout.relations[0].labels == (C.Label("name", ("places",), 195, 24, 0),)
    (patch,) = owned(d, "A->B", Mask)
    assert (patch.left, patch.top, patch.right, patch.bottom) == pytest.approx(G.grow(name.box, BG_MARGIN))
    assert K.check(d).passed


def test_name_beside_a_rightward_line_sits_above_its_middle(monkeypatch):
    beside_only(monkeypatch)
    d = C.render(two_boxes(kind="association", name="places"))
    (name,) = [t for t in owned(d, "A->B", Text)]
    assert (name.text, name.x, name.anchor, name.bg) == ("places", 195, "mm", True)
    assert name.box[3] == pytest.approx(24 - C.NAME_GAP)
    assert d.layout.relations[0].labels == (C.Label("name", ("places",), name.x, name.y),)


def test_name_beside_a_vertical_line_clears_it_by_the_gap(monkeypatch):
    beside_only(monkeypatch)
    d = C.render({"classes": [{"name": "A", "left": 0, "top": 0, "width": 100, "height": 60},
                              {"name": "B", "left": 0, "top": 200, "width": 100, "height": 60}],
                  "relations": [{"kind": "association", "from": "A", "to": "B", "name": "owns"}]})
    (name,) = owned(d, "A->B", Text)
    assert name.y == pytest.approx(130)
    assert name.box[0] == pytest.approx(50 + C.NAME_GAP)  # 아래로 가는 선의 왼쪽은 화면 오른쪽
    assert not touches_a_line(d, name.box)


def test_name_spots_keep_the_gap_on_both_sides_even_for_tall_glyphs():
    text = "█"  # 잉크가 줄 상자 아래로 나가 글자 상자의 위아래가 비대칭이다
    b = T.place(0, 0, text, False, "mm").box
    assert b[3] > -b[1] + 1
    above, below = C.name_spots(((0, 0), (100, 0)), text)
    assert T.place(*above, text, False, "mm").box[3] == pytest.approx(-C.NAME_GAP)
    assert T.place(*below, text, False, "mm").box[1] == pytest.approx(C.NAME_GAP)


def test_long_names_are_cut_in_messages():
    long = "N" * 500
    with pytest.raises(C.InputError) as e:
        C.parse({"classes": [{"name": long, "left": 0, "top": 0}],
                 "relations": [{"kind": "association", "from": long, "to": "M" * 500}]})
    (problem,) = e.value.problems
    assert problem.startswith("relations[0].to: 이름이 'MMM") and len(problem) < 150


def test_name_goes_on_the_middle_of_the_longest_segment_and_moves_along_it_if_blocked():
    data = two_boxes(kind="dependency", name="«use»", via=[[150, 200], [450, 200]])
    (label,) = C.render(data).layout.relations[0].labels
    assert (label.x, label.y, label.segment) == (300, 200, 1)
    data["classes"].append({"name": "Lid", "left": 270, "top": 145})  # 아래 변(y 193)이 선 위 7px — 선 위 가운데 자리의 글자에 겹친다
    d = C.render(data)
    (label,) = d.layout.relations[0].labels
    assert (label.y, label.segment) == (200, 1) and label.x != 300 and K.check(d).passed


def test_name_beside_goes_on_the_longest_segment_and_other_side_if_blocked(monkeypatch):
    beside_only(monkeypatch)
    d = C.render(two_boxes(kind="dependency", name="«use»", via=[[150, 200], [450, 200]]))
    (name,) = owned(d, "A->B", Text)
    assert name.x == pytest.approx(300) and name.y < 200
    assert not touches_a_line(d, name.box)

    blocked = two_boxes(kind="dependency", name="«use»", via=[[150, 200], [450, 200]])
    blocked["classes"].append({"name": "Lid", "left": 270, "top": 150, "width": 60, "height": 40})
    d2 = C.render(blocked)
    (name2,) = owned(d2, "A->B", Text)
    assert name2.y > 200 and not touches_a_line(d2, name2.box)


def walled(left, right, **relation):
    """two_boxes 선(y=24) 위아래에 상자 Up·Down(선에서 5px)을 x left~right에 둔다."""
    data = two_boxes(**relation)
    data["classes"] += [{"name": "Up", "left": left, "top": -40, "width": right - left, "height": 59},
                        {"name": "Down", "left": left, "top": 29, "width": right - left}]
    return data


def test_name_on_its_line_blocked_in_the_middle_moves_along_it_to_the_nearest_free_spot():
    # 선 위 가운데 자리(195, 24)가 위아래 상자에 걸리면 선 위에 얹은 채 NAME_STEP씩 옮겨 가장 먼저 빈 자리에 둔다
    d = C.render(walled(120, 260, kind="dependency", name="has"))
    (label,) = d.layout.relations[0].labels
    assert K.check(d).passed and (label.y, label.segment) == (24, 0)
    away = abs(label.x - 195)
    assert away > 0 and away % B.NAME_STEP == 0
    closer = 195 + (away - B.NAME_STEP) * (1 if label.x > 195 else -1)  # 가운데 쪽으로 한 칸 덜 옮긴 자리
    wide = G.grow(B.lines_box(closer, 24, ("has",)), C.LABEL_CLEAR)
    assert any(G.gap(wide, p.rect) < 0 for p in d.layout.boxes if p.key in ("Up", "Down"))


def test_name_beside_blocked_on_both_sides_moves_to_the_nearest_free_spot_along_the_line(monkeypatch):
    # 선 옆에 놓는 이름은 선 가운데(x 195) 위아래가 다 막혀 있으면 선을 따라 NAME_STEP씩 옮겨 가장 먼저 빈 자리에 둔다
    beside_only(monkeypatch)
    d = C.render(walled(120, 260, kind="dependency", name="has"))
    (name,) = owned(d, "A->B", Text)
    (label,) = d.layout.relations[0].labels
    assert K.check(d).passed
    away = abs(label.x - 195)
    assert away > 0 and away % B.NAME_STEP == 0 and label.y in (s[1] for s in C.name_spots(((90, 24), (300, 24)), "has"))
    closer = 195 + (away - B.NAME_STEP) * (1 if label.x > 195 else -1)  # 가운데 쪽으로 한 칸 덜 옮긴 자리
    for spot in C.name_spots(((closer - 1, 24), (closer + 1, 24)), "has"):
        wide = G.grow(B.lines_box(*spot, ("has",)), C.LABEL_CLEAR)
        assert any(G.gap(wide, p.rect) < 0 for p in d.layout.boxes if p.key in ("Up", "Down"))


def test_name_moves_to_another_segment_when_the_longest_one_has_no_room():
    # 가장 긴 구간(가로 310px)은 위아래가 다 막혀 있고, 다음 구간(세로 276px)의 가운데는 비어 있다
    data = {"classes": [{"name": "A", "left": 0, "top": 0}, {"name": "B", "left": 355, "top": 300},
                        {"name": "Up", "left": 95, "top": -40, "width": 300, "height": 59},
                        {"name": "Down", "left": 95, "top": 29, "width": 295}],
            "relations": [{"kind": "dependency", "from": "A", "to": "B", "name": "has", "via": [[400, 24]]}]}
    d = C.render(data)
    (r,) = d.layout.relations
    assert [math.dist(p, q) for p, q in zip(r.points, r.points[1:])] == [310, 276]
    (label,) = r.labels
    assert (label.x, label.y, label.segment) == (400, 162, 1)
    assert K.check(d).passed


def test_name_moves_even_with_multiplicities_when_they_keep_their_free_spots():
    d = C.render(walled(120, 260, kind="association", name="has", from_multiplicity="1", to_multiplicity="0..*"))
    (r,) = d.layout.relations
    assert (r.labels[0].y, r.labels[0].segment) == (24, 0) and r.labels[0].x != 195
    assert [lab.role for lab in r.labels] == ["name", "from_multiplicity", "to_multiplicity"] and K.check(d).passed


def beside_only(monkeypatch):
    """이름을 선 위에 얹지 않고 모두 선 옆에 놓는다(선 옆 배치와 같다) — 선 옆 이름의 자리 고르기를 보려고."""
    monkeypatch.setattr(B._Spots, "pick_on_line", lambda self, *args, **kwargs: None)


def middle_only(monkeypatch):
    """선을 따라 더 볼 자리(선 옆 slide_spots·선 위 on_spots)를 없애 이름 글자를 가운데에만 둔다 — 선 위 가운데 자리가 빈
    자리면 거기, 아니면 선 옆 가운데 후보다."""
    monkeypatch.setattr(B, "slide_spots", lambda points, lines: iter(()))
    monkeypatch.setattr(B, "on_spots", lambda points, lines: iter(()))


def kinds_of(drawing):
    return [f.kind for f in K.check(drawing).failures]


def without_multiplicities(data):
    bare = copy.deepcopy(data)
    for r in bare["relations"]:
        r.pop("from_multiplicity", None)
        r.pop("to_multiplicity", None)
    return bare


def test_name_is_not_moved_when_its_multiplicities_would_fail_more(monkeypatch):
    # 짧고 비스듬한 선이라 선 옆에 놓는 이름의 가운데 자리 둘이 상자에 붙는다. 다중도가 없으면 이름을 선을 따라 옮겨 합격한다. 다중도가
    # 있으면 옮긴 이름 때문에 다중도가 선에 닿고 서로 겹쳐(걸린 것 둘) 가운데에 둔 것(이름이 상자에 붙음, 하나)보다 나쁘니 옮기지 않는다
    beside_only(monkeypatch)
    data = {"classes": [{"name": "A", "left": 30, "top": 180}, {"name": "B", "left": -10, "top": 270}],
            "relations": [{"kind": "aggregation", "from": "A", "to": "B", "name": "«use»",
                           "from_multiplicity": "1..*", "to_multiplicity": "1"}]}
    moved = C.render(without_multiplicities(data))
    (r,) = moved.layout.relations
    assert (r.labels[0].x, r.labels[0].y) not in C.name_spots(r.points, "«use»") and K.check(moved).passed
    d = C.render(data)
    assert kinds_of(d) == ["text_on_box"]
    with monkeypatch.context() as m:
        middle_only(m)
        assert d.layout.relations[0].labels == C.render(data).layout.relations[0].labels
    with monkeypatch.context() as m:
        m.setattr(B._Spots, "misses", lambda self, start: (0, 0))  # 견주지 않고 옮긴 쪽을 쓰면 다중도가 걸린다
        assert kinds_of(C.render(data)) == ["line_through_text", "text_overlap"]


def test_name_moves_when_that_trades_a_box_overlap_for_one_label_overlap(monkeypatch):
    # 선 옆에 놓는 이름의 걸린 것이 가운데(이름이 상자에 붙음)와 옮긴 쪽(다중도가 이름에 겹침) 모두 하나면, 피할 것에 걸린 글자가
    # 없는 옮긴 쪽을 쓴다
    beside_only(monkeypatch)
    data = {"classes": [{"name": "A", "left": 120, "top": -100}, {"name": "B", "left": 160, "top": -20}],
            "relations": [{"kind": "composition", "from": "A", "to": "B", "name": "has",
                           "from_multiplicity": "1..*", "to_multiplicity": "*"}]}
    d = C.render(data)
    (r,) = d.layout.relations
    assert (r.labels[0].x, r.labels[0].y) not in C.name_spots(r.points, "has") and kinds_of(d) == ["text_overlap"]
    middle_only(monkeypatch)
    assert kinds_of(C.render(data)) == ["text_on_box"]


def test_name_on_its_line_stays_in_the_middle_when_moving_it_does_not_help_its_multiplicities(monkeypatch):
    # 짧은 연관(C1→C4, 52px)의 선 위 가운데 자리 (225, 324)는 옆 실체화 선(C1→C2)과 NAME_GAP 안이라 빈 자리가 아니어서, 이름을
    # 선 위에서 한 칸(NAME_STEP) 옮기면 빈 자리다. 그래도 다중도 "0..*"가 빈 자리를 못 찾아 걸린 것이 가운데에 둔 것과 같으니,
    # 빈 자리가 아닌 선 위 가운데 자리에 둔다(선 위에 얹은 이름의 다중도 견주기)
    data = {"classes": [{"name": "C1", "left": 175, "top": 350}, {"name": "C2", "left": 80, "top": 210},
                        {"name": "C4", "left": 185, "top": 250}],
            "relations": [{"kind": "association", "from": "C1", "to": "C4", "name": "주문한다", "from_multiplicity": "0..1",
                           "to_multiplicity": "0..*"},
                          {"kind": "realization", "from": "C1", "to": "C2", "name": "places"}]}
    d = C.render(data)
    name = d.layout.relations[0].labels[0]
    assert (name.x, name.y, name.segment) == (225, 324, 0)
    near = G.grow(B.lines_box(225, 324, name.lines), C.NAME_GAP)
    assert G.hits(*d.layout.relations[1].points, near)
    monkeypatch.setattr(B._Spots, "misses", lambda self, start: (0, 0))  # 견주지 않으면 옮긴 자리를 쓴다
    moved = C.render(data)
    slid = moved.layout.relations[0].labels[0]
    assert slid.segment == 0 and math.dist((slid.x, slid.y), (225, 324)) == pytest.approx(B.NAME_STEP)
    assert kinds_of(moved) == kinds_of(d) == ["line_through_text", "text_overlap"]


def test_name_with_no_free_spot_stays_in_the_middle_even_beside_a_spot_that_only_touches_lines(monkeypatch):
    # 가운데는 Up·Down이 막고, 그 옆 빈 곳(x 90~120, 260~300)은 세로선 U0→D0(x 105)·U1→D1(x 280)이 지난다. 선 위에는 빈 자리가
    # 없어 이름을 선 옆에 놓는다. 상자에는 안 걸리고 선에만 닿는 자리는 있지만 빈 자리가 아니라 옮기지 않는다 — 그런 자리는 선 여러
    # 개에 닿아 불합격이 늘 수 있다
    data = walled(120, 260, kind="dependency", name="has")
    for i, x in enumerate((105, 280)):
        data["classes"] += [{"name": f"U{i}", "left": x - 45, "top": -300}, {"name": f"D{i}", "left": x - 45, "top": 300}]
        data["relations"].append({"kind": "association", "from": f"U{i}", "to": f"D{i}", "navigable": "none"})
    d = C.render(data)
    label = d.layout.relations[0].labels[0]
    assert (label.x, label.y) in C.name_spots(((90, 24), (300, 24)), "has") and label.segment is None
    assert kinds_of(d) == ["text_on_box"]
    middle_only(monkeypatch)
    assert C.render(data).layout.relations[0].labels == d.layout.relations[0].labels


def test_name_with_no_free_spot_on_or_beside_the_line_stays_beside_its_middle():
    # A와 B 쪽 화살촉 사이를 다 막아 선 위에도 선 옆에도 빈 자리가 없다 — 그 이름만 선 옆 가운데 후보에 둔다
    d = C.render(walled(95, 285, kind="association", name="has"))
    (r,) = d.layout.relations
    (label,) = r.labels
    assert (label.x, label.y) in C.name_spots(r.points, "has") and label.segment is None
    assert [f.kind for f in K.check(d).failures] == ["text_on_box"]


def test_names_of_crossing_lines_sit_on_their_own_lines_away_from_the_crossing(monkeypatch):
    # A→B 의존(점선, y 24)의 "has"와 U→D 연관(세로선, x 195)의 "owns" — 두 선은 가운데끼리 (195, 24)에서 엇갈린다. 둘 다 선 위
    # 가운데 자리가 다른 선에 걸려 각자의 선 위에서 옮겨 앉는다. 다른 관계의 선과는 NAME_GAP 넘게 떨어진다: "has"는 세로선에서
    # 9.5px, "owns"는 점선에서 12.7px
    data = two_boxes(kind="dependency", name="has")
    data["classes"] += [{"name": "U", "left": 150, "top": -150}, {"name": "D", "left": 150, "top": 150}]
    data["relations"].append({"kind": "association", "from": "U", "to": "D", "name": "owns"})
    d = C.render(data)
    has, owns = (r.labels[0] for r in d.layout.relations)
    assert (has.x, has.y, has.segment) == (215, 24, 0) and (owns.x, owns.y, owns.segment) == (195, 44, 0)
    assert B.lines_box(has.x, has.y, has.lines)[0] - 195 == pytest.approx(9.5, abs=0.05)
    assert B.lines_box(owns.x, owns.y, owns.lines)[1] - 24 == pytest.approx(12.7, abs=0.05)
    assert K.check(d).passed
    middle_only(monkeypatch)  # 가운데에만 두면 선 옆 가운데 후보에 놓여 다른 선이 이름을 지나고 두 이름이 엇갈리는 곳에서 겹친다
    assert kinds_of(C.render(data)) == ["line_through_text", "line_through_text", "text_overlap"]


# 상자 둘 사이에 관계 넷이 포개진 그림 — 선 옆 배치에서 넓혀서 옮긴 이름이 뒤 글자를 밀어 좁은 조건의 배치로 돌아간다
STACKED = {"classes": [{"name": "C0", "left": -10, "top": 190}, {"name": "C1", "left": -30, "top": 80}],
           "relations": [{"kind": "aggregation", "from": "C1", "to": "C0", "name": "«use»", "to_multiplicity": "*"},
                         {"kind": "dependency", "from": "C1", "to": "C0", "name": "«use»"},
                         {"kind": "composition", "from": "C0", "to": "C1", "from_multiplicity": "0..*"},
                         {"kind": "composition", "from": "C0", "to": "C1", "name": "places", "from_multiplicity": "0..*"}]}
# 선 위에 얹으면 그림 전체가 더 걸려 선 옆 배치로 돌아가는 그림(#71 시제품이 무작위 클래스도에서 고른 입력)
BACK_BESIDE = {"classes": [{"name": "C0", "left": 120, "top": 30}, {"name": "C1", "left": 360, "top": 140},
                           {"name": "C2", "left": 60, "top": 290}, {"name": "P", "left": 285, "top": 94}],
               "relations": [{"kind": "realization", "from": "C1", "to": "C0", "name": "has", "via": [[355, 79]]},
                             {"kind": "generalization", "from": "C0", "to": "C1", "name": "reads from"},
                             {"kind": "association", "from": "C1", "to": "C0", "name": "관리한다",
                              "from_multiplicity": "*", "to_multiplicity": "0..*"}]}


def test_widened_moves_are_undone_when_the_whole_diagram_gets_more_faults(monkeypatch):
    # 상자 둘 사이에 관계 넷이 포개진 그림(선 옆 배치). 둘째 관계의 이름은 가운데가 선과 앞 이름에만 닿아(상자에는 안 걸려) 옮기는
    # 조건을 넓혀야 옮겨 가는데, 그 자리를 뒤 관계의 글자가 쓰고 있어 뒤 글자가 밀린다. 넓히기만 하면 그림 전체의 걸린 것이 (4, 0)으로
    # 좁은 조건의 (3, 0)보다 많으니 좁은 조건의 배치를 쓴다
    beside_only(monkeypatch)
    data = STACKED
    real = B._labels
    seen = {}

    def spy(spots, *args, wide, on):
        out = real(spots, *args, wide=wide, on=on)
        seen[wide] = spots.misses(0)
        return out

    def labels_of(drawing):
        return [r.labels for r in drawing.layout.relations]

    with monkeypatch.context() as m:
        m.setattr(B, "_labels", spy)
        d = C.render(data)
    assert seen == {True: (4, 0), False: (3, 0)}
    with monkeypatch.context() as m:
        m.setattr(B, "_labels", lambda spots, *args, wide, on: real(spots, *args, wide=False, on=on))
        narrow = C.render(data)
    with monkeypatch.context() as m:
        m.setattr(B, "_beside_layout", lambda *args: ([], (math.inf, math.inf)))  # 견주지 않고 넓힌 쪽(첫 배치)을 쓴다
        wide = C.render(data)
    assert labels_of(d) == labels_of(narrow) != labels_of(wide)
    assert (len(K.check(wide).failures), len(K.check(d).failures)) == (5, 4)


def test_names_go_back_beside_their_lines_when_putting_them_on_lines_gets_more_faults(monkeypatch):
    # 선 위에 얹은 이름이 뒤 관계의 글자가 쓸 자리를 차지해 그림 전체의 걸린 것이 선 옆 배치보다 많으면, 그림 전체를 선 옆 배치로
    # 되돌린다(선 위 배치 (2, 1), 선 옆 배치 (1, 1))
    data = BACK_BESIDE
    real_labels, real_beside = B._labels, B._beside_layout
    seen = {}

    def spy_labels(spots, *args, wide, on):
        out = real_labels(spots, *args, wide=wide, on=on)
        if on:
            seen["on"] = spots.misses(0)
        return out

    def spy_beside(*args):
        out = real_beside(*args)
        seen["beside"] = out[1]
        return out

    with monkeypatch.context() as m:
        m.setattr(B, "_labels", spy_labels)
        m.setattr(B, "_beside_layout", spy_beside)
        d = C.render(data)
    assert seen == {"on": (2, 1), "beside": (1, 1)}
    assert all(lab.segment is None for r in d.layout.relations for lab in r.labels)
    monkeypatch.setattr(B, "_beside_layout", lambda *args: ([], (math.inf, math.inf)))  # 되돌리지 않는다
    kept = C.render(data)
    assert any(lab.segment is not None for r in kept.layout.relations for lab in r.labels)
    assert len(K.check(kept).failures) > len(K.check(d).failures)


def test_layouts_are_laid_out_again_only_when_they_can_do_better(monkeypatch):
    calls = []
    real = B._labels
    monkeypatch.setattr(B, "_labels", lambda spots, *args, wide, on: calls.append((on, wide)) or real(spots, *args, wide=wide,
                                                                                                         on=on))
    # 선 위 배치에 걸린 것이 없으면 선 옆 배치로 다시 놓지 않는다
    d = C.render(walled(120, 260, kind="association", name="has", from_multiplicity="1"))
    assert calls == [(True, True)] and d.layout.relations[0].labels[0].segment == 0
    # 걸린 것이 있어도 선 위에 얹은 이름도 넓혀서 옮긴 이름도 없으면(이름이 상자에 막혀 선 옆 가운데 후보에 있다) 선 옆 배치가 이
    # 배치와 같으니 다시 놓지 않는다
    calls.clear()
    d = C.render(walled(95, 285, kind="association", name="has"))
    assert calls == [(True, True)] and d.layout.relations[0].labels[0].segment is None
    # 선 위에 얹은 이름이 있으면 선 옆 배치로도 놓는다. 선 옆 배치에 넓혀서 옮긴 이름이 없으면 좁은 조건으로 다시 놓지 않는다
    calls.clear()
    C.render(BACK_BESIDE)
    assert calls == [(True, True), (False, True)]
    # 선 위에 얹은 이름이 없어도 넓혀서 옮긴 이름이 있으면 선 옆 배치를 넓힌 조건·좁은 조건으로 놓는다
    calls.clear()
    C.render(STACKED)
    assert calls == [(True, True), (False, True), (False, False)]


def test_label_faults_count_each_element_each_relation_line_and_each_label():
    # 글자 하나가 요소 둘, 끝을 품은 요소의 테두리 선 둘, 관계 r1의 선분 둘과 r2의 선분 하나, 앞서 놓은 글자 하나에 걸리면 걸린 것은
    # 요소 둘 + 테두리 하나 + 관계 둘 + 글자 하나 = 6이다(검사도 요소마다·관계마다·글자 쌍마다 하나씩 알린다)
    spots = B._Spots([((-30, -2), (30, -2)), ((-30, 2), (30, 2)), ((0, -30), (0, 30))], ["r1", "r1", "r2"])
    spots.labels.append((-5, -5, 5, 5))
    avoid = B.Obstacles((G.RectBorder((-20, -20, -5, 20)), G.RectBorder((5, -20, 20, 20))),
                        (((-40, -1), (40, -1)), ((-40, 1), (40, 1))), ("X", "Y"), ("H", "H"))
    best = spots._best(("abc",), [(0, 0)], avoid)
    assert (best.off, best.free, best.faults) == (False, False, 6)
    spots._keep(best)
    assert spots.misses(0) == (6, 1)


def test_label_faults_count_an_element_once_and_lines_through_one_place_once():
    # 끝을 품은 요소 H의 이름 칸과 테두리 선에 함께 걸리면 H 하나, 또 다른 품은 요소 K의 테두리 선에도 걸리면 둘이다. 같은 자리를
    # 지나는(포개진) 관계 둘의 선은 하나다(검사도 요소마다, 같은 자리의 선들은 한 항목으로 알린다)
    spots = B._Spots([((-30, 0), (30, 0)), ((-30, 0), (30, 0))], ["r1", "r2"])
    avoid = B.Obstacles((G.RectBorder((-20, -20, 20, -3)),), (((-40, 3), (40, 3)), ((-40, 4), (40, 4))), ("H",), ("H", "K"))
    assert spots._best(("abc",), [(0, 0)], avoid).faults == 2 + 1


def test_name_on_a_line_skips_its_segment_and_keeps_the_name_gap_only_from_other_relations():
    # 관계 r1의 구간 0(가로선 y 0)에 얹은 글자는 그 구간을 빼고 본다. 글자 상자 오른쪽 5px에 세로선이 있으면 — LABEL_CLEAR(3px)
    # 밖이라 걸린 것은 아니지만 — 다른 관계 r2의 선분이나 선 끝 모양 테두리(구간 번호 없음)면 NAME_GAP(8px) 안이라 빈 자리가 아니고,
    # 같은 관계 r1의 다른 구간이나 선 끝 모양이면 빈 자리다
    box = B.lines_box(0, 0, ("abc",))
    x = box[2] + 5
    for owner, path, free in (("r2", 1, False), ("r2", None, False), ("r1", 1, True), ("r1", None, True)):
        spots = B._Spots([((-60, 0), (60, 0)), ((x, -30), (x, 30))], ["r1", owner], [0, path])
        best = spots._best(("abc",), [(0, 0)], B.Obstacles(()), on=("r1", 0))
        assert (best.free, best.faults) == (free, 0), (owner, path)
    # 얹은 구간이 아닌 구간에 두면 그 구간이 글자를 지나 걸린다(검사와 같이 LABEL_CLEAR로 센다)
    spots = B._Spots([((-60, 0), (60, 0)), ((x, -30), (x, 30))], ["r1", "r1"], [0, 1])
    assert spots._best(("abc",), [(0, 0)], B.Obstacles(()), on=("r1", 1)).faults == 1


def test_name_too_wide_for_the_longest_segment_has_no_middle_on_the_line():
    # 가장 긴 구간(가로 150px)보다 넓은 이름은 선 위 가운데 자리가 없다 — 넘치면 흰 바탕이 꺾인 곳을 지운다. 선을 따라 다음 구간(세로
    # 100px — 글자 높이만 들면 된다) 가운데에 얹고, 다중도 견주기의 다시 놓기(slide 아님)에는 선 위 가운데 자리를 내지 않는다
    lines = ("a_name_wider_than_the_horizontal_segment",)
    points = ((0, 0), (150, 0), (150, 100))
    assert B.lines_box(0, 0, lines)[2] > 75
    spots = B._Spots(list(zip(points, points[1:])), ["r", "r"], [0, 1])
    assert spots.pick_on_line(lines, points, B.Obstacles(()), "r", slide=False) is None
    assert spots.pick_on_line(lines, points, B.Obstacles(()), "r") == ((150, 50), 1, True)
    # 글자 상자는 들어도 LABEL_CLEAR만큼 넓힌 것이 들지 않으면(구간이 글자보다 4px 길다) 선 위 가운데 자리가 없다 — 흰 바탕
    # (BG_MARGIN)이 꺾인 곳에 닿는다
    width = B.lines_box(0, 0, ("abc",))[2] * 2
    snug = ((0, 0), (width + 4, 0), (width + 4, 10))
    spots = B._Spots(list(zip(snug, snug[1:])), ["r", "r"], [0, 1])
    assert spots.pick_on_line(("abc",), snug, B.Obstacles(()), "r", slide=False) is None


def test_on_spots_walk_out_from_the_middle_and_stay_on_their_segment():
    points = ((0, 0), (100, 0), (100, 30))  # 가로 100px 구간 다음 세로 30px 구간
    lines = ("uses",)
    b = B.lines_box(0, 0, lines)
    banded = list(B.on_spots(points, lines))
    assert [k for k, _, _ in banded] == [0, 1]  # 구간마다 (구간 번호, 띠, 묶음들)
    # 구간의 띠는 그 구간 묶음들의 글자 상자를 NAME_GAP만큼 넓힌 것을 다 덮는다
    assert all(span_in(G.grow(B.lines_box(x, y, lines), C.NAME_GAP), band)
               for _, band, rings in banded for ring in rings for x, y in ring)
    across, down = banded[0][2], banded[1][2]
    # 가로 구간: 가운데(50)에서 진행 방향 앞쪽·뒤쪽으로 5px씩 옮긴 두 자리씩, 선 위(y 0)에서 글자 상자가 구간 밖으로 나가기 전까지
    n = int((50 - max(-b[0], b[2])) // B.NAME_STEP)
    assert across == [[(50 + k * B.NAME_STEP, 0), (50 - k * B.NAME_STEP, 0)] for k in range(1, n + 1)]
    # 세로 구간: 가운데 한 자리 다음에 5px씩 옮긴 두 자리
    assert down[0] == [(100, 15)] and [len(r) for r in down] == [1] + [2] * int((15 - max(-b[1], b[3])) // B.NAME_STEP)
    assert all(0 <= y + b[1] and y + b[3] <= 30 and x == 100 for r in down for x, y in r)


def test_obstacle_keys_are_one_per_obstacle_or_none():
    # 열쇠가 모자라면 짝을 지을 때 열쇠 없는 피할 것이 빠져 글자가 그 위에 놓일 수 있으니 만들 때 막는다
    with pytest.raises(ValueError, match="요소 열쇠"):
        B.Obstacles((G.RectBorder((0, 0, 1, 1)), G.RectBorder((2, 2, 3, 3))), (), ("A",))
    assert len(B.Obstacles((G.RectBorder((0, 0, 1, 1)), G.RectBorder((2, 2, 3, 3)))).keyed[0]) == 2


def span_in(inner, outer):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def test_slide_spots_walk_out_from_the_middle_and_stay_beside_their_segment():
    points = ((0, 0), (100, 0), (100, 30))  # 가로 100px 구간 다음 세로 30px 구간
    lines = ("uses",)
    b = B.lines_box(0, 0, lines)
    banded = list(B.slide_spots(points, lines))
    assert len(banded) == 2  # 구간마다 (띠, 묶음들)
    rings = [ring for _, rings in banded for ring in rings]
    # 구간의 띠는 그 구간 묶음들의 흰 바탕을 다 덮는다
    assert all(span_in(G.grow(B.lines_box(x, y, lines), C.LABEL_CLEAR), band)
               for band, rings in banded for ring in rings for x, y in ring)
    n = int((50 - max(-b[0], b[2])) // B.NAME_STEP)  # 가로 구간에서 글자 상자가 구간 안에 드는 묶음 수
    across, down = rings[:n], rings[n:]
    # 가로 구간: 가운데(50)에서 앞쪽·뒤쪽으로 5px씩 옮긴 네 자리씩, 글자 상자가 구간(x 0~100) 밖으로 나가기 전까지
    assert [sorted({x for x, _ in r}) for r in across] == [[50 - k * B.NAME_STEP, 50 + k * B.NAME_STEP] for k in range(1, n + 1)]
    assert all(len(r) == 4 for r in across) and all(0 <= x + b[0] and x + b[2] <= 100 for r in across for x, _ in r)
    # 세로 구간: 가운데 두 자리 다음에 5px씩 옮긴 네 자리, 글자 상자가 구간(y 0~30) 안이다
    assert [len(r) for r in down] == [2] + [4] * int((15 - max(-b[1], b[3])) // B.NAME_STEP)
    assert {y for _, y in down[0]} == {15} and len(down) > 1
    assert all(0 <= y + b[1] and y + b[3] <= 30 for r in down for _, y in r)


def test_multiplicities_avoid_boxes():
    data = two_boxes(kind="association", from_multiplicity="1", to_multiplicity="0..*")
    d = C.render(data)
    rects = [p.rect for p in d.layout.boxes]
    labels = {t.text: t for t in owned(d, "A->B", Text)}
    assert set(labels) == {"1", "0..*"} and all(t.bg for t in labels.values())
    for t in labels.values():
        assert all(G.gap(t.box, r) >= C.MULT_ENOUGH for r in rects)
        assert math.dist((t.x, t.y), START if t.text == "1" else END) <= max(C.MULT_DISTANCES)

    blocked = copy.deepcopy(data)
    blocked["classes"].append({"name": "Above", "left": 95, "top": -34})  # 아래 변이 y=14 — 선(y=24) 바로 위를 막는다
    d2 = C.render(blocked)
    one = next(t for t in owned(d2, "A->B", Text) if t.text == "1")
    assert one.y > 24
    assert all(G.gap(one.box, p.rect) > 0 for p in d2.layout.boxes)
    assert labels["1"].y < 24


def test_multiplicities_keep_off_lines_and_each_other():
    d = C.render({"classes": [{"name": "A", "left": 0, "top": 0, "width": 100, "height": 60},
                              {"name": "B", "left": 0, "top": 200, "width": 100, "height": 60},
                              {"name": "C", "left": 200, "top": 200, "width": 100, "height": 60}],
                  "relations": [{"kind": "association", "from": "A", "to": "B", "name": "owns",
                                 "from_multiplicity": "0..*", "to_multiplicity": "1..*"},
                                {"kind": "association", "from": "A", "to": "C",
                                 "from_multiplicity": "0..*", "to_multiplicity": "1"}]})
    name = d.layout.relations[0].labels[0]
    assert name.segment == 0 and K.check(d).passed  # 이름은 제 선 위에 얹는다
    labels = [t for t in d.canvas.records if isinstance(t, Text) and t.bg]  # 다중도는 선 옆에 흰 바탕을 깔고 쓴다
    assert len(labels) == 4
    for i, t in enumerate(labels):
        wide = G.grow(t.box, C.LABEL_CLEAR)
        assert not touches_a_line(d, t.box), t.text
        assert all(G.gap(wide, p.rect) >= 0 for p in d.layout.boxes), t.text
        assert all(G.gap(wide, u.box) >= 0 for u in labels[:i]), t.text
        assert G.gap(wide, B.lines_box(name.x, name.y, name.lines)) >= 0, t.text


def test_labels_keep_off_end_shapes_of_other_relations():
    d = C.render({"classes": [{"name": "A", "left": 0, "top": 0, "width": 100, "height": 60},
                              {"name": "B", "left": 0, "top": 200, "width": 100, "height": 60},
                              {"name": "C", "left": 150, "top": 130, "width": 100, "height": 40}],
                  "relations": [{"kind": "generalization", "from": "C", "to": "B"},
                                {"kind": "association", "from": "A", "to": "B", "to_multiplicity": "1..*"}]})
    (label,) = [t for t in d.canvas.records if isinstance(t, Text) and t.bg]
    assert not touches_a_line(d, label.box)

    triangle = Polygon(((60, 40), (80, 30), (80, 50)))
    spots = B._Spots(G.outline([triangle]))
    first = (70, 40)  # 삼각형 위 — 선분만 보면 닿는 데가 없다
    assert spots.pick(("1",), [first, (0, 0)], B.Obstacles((G.RectBorder((-500, -500, -400, -400)),))) == (0, 0)


def test_generalization_tree_may_share_one_trunk():
    d = C.render({"classes": [{"name": "P", "left": 200, "top": 0}, {"name": "X", "left": 100, "top": 200},
                              {"name": "Y", "left": 300, "top": 200}],
                  "relations": [{"kind": "generalization", "from": "X", "to": "P", "via": [[145, 150], [245, 150]]},
                                {"kind": "generalization", "from": "Y", "to": "P", "via": [[345, 150], [245, 150]]}]})
    assert [r.points[-2:] for r in d.layout.relations] == [((245, 150), (245, 48))] * 2


def test_lines_drawn_over_each_other_are_left_to_the_check():
    """포개진 선(같은 두 상자를 꺾는 점 없이 잇는 두 관계, 왔던 길을 되짚는 선)은 그릴 수는 있으므로 입력 오류로 막지
    않는다. 상속 트리의 공유 줄기처럼 정상인 포개짐과 가르는 것은 그림 검사의 몫이다."""
    data = two_boxes(kind="association")
    data["relations"].append({"kind": "dependency", "from": "B", "to": "A"})
    assert len(C.render(data).layout.relations) == 2
    assert C.render(two_boxes(kind="association", via=[[200, 24], [150, 24]])).layout.relations[0].points == (
        (90, 24), (200, 24), (150, 24), (300, 24))


def test_lines_that_only_meet_or_run_straight_through_a_bend_are_fine():
    data = two_boxes(kind="association", via=[[200, 24]])
    data["relations"].append({"kind": "dependency", "from": "A", "to": "B", "via": [[195, 120]]})
    data["relations"].append({"kind": "dependency", "from": "B", "to": "A", "via": [[195, -80]]})
    assert len(C.render(data).layout.relations) == 3


def test_names_that_point_to_boxes_ignore_surrounding_spaces():
    d = C.render({"classes": [{"name": " A ", "left": 0, "top": 0}, {"name": "B", "left": 300, "top": 0}],
                  "relations": [{"kind": "association", "from": "A", "to": "B  "}]})
    assert [p.key for p in d.layout.boxes] == ["A", "B"] and d.layout.relations[0].owner == "A->B"


def test_relation_owners_are_unique():
    d = C.render({"classes": [{"name": "A", "left": 0, "top": 0}, {"name": "B", "left": 300, "top": 0},
                              {"name": "A->B", "left": 0, "top": 200}],
                  "relations": [{"kind": "association", "from": "A", "to": "B"},
                                {"kind": "dependency", "from": "A", "to": "B", "via": [[195, 120]]}]})
    assert [r.owner for r in d.layout.relations] == ["A->B#2", "A->B#3"]
    assert owned(d, "A->B", Rect)
    assert all(200 <= y <= 248 for r in owned(d, "A->B", Line) for _, y in r.points)  # 그 이름의 상자 구획선뿐


def test_png_is_drawn_from_the_records(tmp_path):
    d = C.render(two_boxes(kind="composition", name="has", from_multiplicity="1", to_multiplicity="*"))
    size = d.canvas.save(tmp_path / "out.png")
    img = Image.open(tmp_path / "out.png")
    assert img.size == size and img.format == "PNG"
    assert img.convert("L").getextrema()[0] < 50


def test_names_are_matched_after_nfc():
    nfd = "가"  # "가"를 풀어 쓴 것
    d = C.render({"classes": [{"name": nfd, "left": 0, "top": 0}, {"name": "B", "left": 300, "top": 0}],
                  "relations": [{"kind": "association", "from": "가", "to": "B"}]})
    assert d.layout.boxes[0].key == "가"
    assert d.layout.relations[0].owner == "가->B"


def mutate(change):
    data = {"classes": [{"name": "A", "left": 0, "top": 0}, {"name": "B", "left": 300, "top": 0}], "relations": []}
    change(data)
    return data


def rel(**r):
    return lambda d: d["relations"].append({"kind": "association", "from": "A", "to": "B", **r})


def cls0(**fields):
    return lambda d: d["classes"][0].update(fields)


@pytest.mark.parametrize("change, expected", [
    (rel(to="Custmer"), "relations[0].to: 이름이 'Custmer'인 상자가 없다(있는 상자: 'A', 'B')"),
    (lambda d: d["classes"][0].pop("left"), "classes[0]: 'left' 필드가 빠졌다"),
    (lambda d: d["classes"][1].pop("top"), "classes[1]: 'top' 필드가 빠졌다"),
    (lambda d: d["classes"][0].pop("name"), "classes[0]: 'name' 필드가 빠졌다"),
    (cls0(x=1), "classes[0].x: 모르는 필드다. 쓸 수 있는 필드: name, kind,"),
    (cls0(kind="struct"), "classes[0].kind: 'class' · 'abstract' · 'interface' · 'enum' 가운데 하나여야 한다"),
    (cls0(left="10"), "classes[0].left: 수여야 한다(받은 값 '10')"),
    (cls0(top=True), "classes[0].top: 수여야 한다"),
    (cls0(left=float("nan")), "classes[0].left: 수여야 한다"),
    (cls0(left=1e9), "classes[0].left: -1000000~1000000 사이여야 한다"),
    (cls0(width=-5), "classes[0].width: 0~1000000 사이여야 한다"),
    (cls0(name="B"), "classes[1].name: classes[0]와 이름이 같다"),
    (cls0(name="  "), "classes[0].name: 비어 있다"),
    (cls0(name=3), "classes[0].name: 문자열이어야 한다"),
    (cls0(name="A😀"), "classes[0].name: 함께 넣은 글꼴에 없는 글자다"),
    (cls0(attributes=["-a\n-b"]), "classes[0].attributes[0]: 제어·서식 문자나 줄 나눔은"),
    (cls0(attributes="-a"), "classes[0].attributes: 목록이어야 한다"),
    (cls0(attributes=[{"type": "int"}]), "classes[0].attributes[0]: 'name' 필드가 빠졌다"),
    (cls0(attributes=[{"name": "a", "params": []}]), "classes[0].attributes[0].params: 모르는 필드다"),
    (cls0(attributes=[{"name": "a", "default": None}]), "classes[0].attributes[0].default: 문자열이나 수, true·false여야"),
    (cls0(attributes=[{"name": "a", "default": float("nan")}]), "classes[0].attributes[0].default: 유한한 수여야"),
    (cls0(attributes=[{"name": "a", "default": ""}]), "classes[0].attributes[0].default: 비어 있다"),
    (cls0(attributes=[{"name": "a", "type": 3}]), "classes[0].attributes[0].type: 문자열이어야 한다"),
    (cls0(operations=[{"name": "go", "static": "yes"}]), "classes[0].operations[0].static: true나 false여야 한다"),
    (cls0(operations=[{"name": "go", "visibility": "public"}]), "classes[0].operations[0].visibility: '+' · '-'"),
    (cls0(operations=[{"name": "go", "params": "a, b"}]), "classes[0].operations[0].params: 목록이어야 한다"),
    (cls0(operations=[{"name": "go", "params": [1]}]), "classes[0].operations[0].params[0]: 문자열이어야 한다"),
    (cls0(literals=["X"]), "classes[0].literals: 열거 값은 kind가 'enum'인 상자에만 쓴다(이 상자는 'class')"),
    (cls0(stereotype="«entity»"), "classes[0].stereotype: «» 없이 이름만 쓴다"),
    (cls0(stereotype="<<entity>>"), "classes[0].stereotype: «» 없이 이름만 쓴다"),
    (rel(kind="inheritance"), "relations[0].kind: 'association' · 'aggregation'"),
    (lambda d: d["relations"].append({"from": "A", "to": "B"}), "relations[0]: 'kind' 필드가 빠졌다"),
    (rel(kind="generalization", to_multiplicity="1"), "relations[0].to_multiplicity: 다중도는 연관·집합·합성에만 쓴다"),
    (rel(kind="dependency", navigable="to"), "relations[0].navigable: 방향은 연관·집합·합성에만 쓴다"),
    (rel(kind="composition", navigable="both"), "relations[0].navigable: 집합·합성은 마름모가 있는 from 쪽에"),
    (rel(navigable="forward"), "relations[0].navigable: 'to' · 'from' · 'both' · 'none' 가운데 하나여야 한다"),
    (rel(to="A"), "relations[0]: 자기 자신으로 가는 관계는 꺾는 점(via)이 둘 이상 있어야"),
    (rel(to="A", via=[[200, 24]]), "relations[0]: 자기 자신으로 가는 관계는 꺾는 점(via)이 둘 이상 있어야"),
    (cls0(left=10 ** 400), "classes[0].left: -1000000~1000000 사이여야 한다(받은 값 1000"),
    (cls0(left=float("inf")), "classes[0].left: -1000000~1000000 사이여야 한다(받은 값 inf)"),
    (cls0(left=10 ** 5000), "classes[0].left: -1000000~1000000 사이여야 한다(받은 값 (아주 큰 정수))"),
    (cls0(attributes=[{"name": "a", "default": 10 ** 5000}]), "classes[0].attributes[0].default: 수가 너무 크다"),
    (rel(via=[[1]]), "relations[0].via[0]: [x, y]여야 한다"),
    (rel(via=[[1, "2"]]), "relations[0].via[0][1]: 수여야 한다"),
    (rel(via=[[150, 100], [150, 100]]), "relations[0].via[1]: 앞 꺾는 점과 같다 (150.0, 100.0)"),
    (rel(name=""), "relations[0].name: 비어 있다"),
    (lambda d: d.update(relations={}), "relations: 목록이어야 한다"),
    (lambda d: d.update(classes=[]), "classes: 상자가 하나 이상 있어야 한다"),
    (lambda d: d.pop("classes"), "입력: 'classes' 필드가 빠졌다"),
    (lambda d: d.update(title="x"), "title: 모르는 필드다"),
    (rel(stereotype="<<use>>"), "relations[0].stereotype: 모르는 필드다"),
])
def test_wrong_input_says_where_and_what(change, expected):
    with pytest.raises(C.InputError) as e:
        C.render(mutate(change))
    assert any(p.startswith(expected) for p in e.value.problems), e.value.problems


def test_field_the_class_tool_does_not_take_is_told_once():
    with pytest.raises(C.InputError) as e:
        C.parse(mutate(rel(stereotype="<<use>>")))
    assert len(e.value.problems) == 1 and "모르는 필드다" in e.value.problems[0]


def test_wrong_kind_still_reports_problems_in_members():
    # kind가 틀려도 속성·연산의 문제를 함께 알린다(열거 값은 kind를 알아야 가리므로 보지 않는다)
    with pytest.raises(C.InputError) as e:
        C.parse({"classes": [{"name": "A", "kind": "klass", "left": 0, "top": 0, "attributes": [{"nam": "x"}],
                              "literals": ["X"]}]})
    assert [p.split(":")[0] for p in e.value.problems] == ["classes[0].kind", "classes[0].attributes[0].nam",
                                                           "classes[0].attributes[0]"]


@pytest.mark.parametrize("box", [{"name": "A", "top": 0}, {"name": "A", "left": 0, "top": 0, "x": 1}])
def test_box_missing_or_unknown_field_is_not_built(box):
    reader = B._Reader(C.SPEC)
    key, _, element = reader.element(box, "classes[0]")
    assert (key, element) == ("A", None) and len(reader.problems) == 1


def test_wrong_input_that_is_not_an_object():
    with pytest.raises(C.InputError, match="^입력: 객체여야 한다"):
        C.parse([1, 2])


def test_all_problems_are_reported_at_once():
    data = mutate(lambda d: (d["classes"][0].pop("left"), d["classes"][1].update(kind="x"),
                             d["relations"].append({"kind": "association", "from": "A", "to": "Z"})))
    with pytest.raises(C.InputError) as e:
        C.parse(data)
    assert [p.split(":")[0] for p in e.value.problems] == ["classes[0]", "classes[1].kind", "relations[0].to"]
    assert isinstance(e.value, ValueError) and str(e.value) == "\n".join(e.value.problems)


def test_missing_box_is_reported_even_when_the_relation_has_other_problems():
    data = mutate(rel(kind="bogus", **{"from": "X"}, navigable="sideways"))
    with pytest.raises(C.InputError) as e:
        C.parse(data)
    assert [p.split(":")[0] for p in e.value.problems] == ["relations[0].kind", "relations[0].from"]


@pytest.mark.parametrize("change, expected", [
    (rel(via=[[10, 10]]), "relations[0].via[0]: 꺾는 점 (10.0, 10.0)이 from 상자 'A'(0, 0, 90×48) 안이나 변 위에 있다"),
    (rel(via=[[150, 100], [300, 24]]), "relations[0].via[1]: 꺾는 점 (300.0, 24.0)이 to 상자 'B'"),
    (lambda d: d["classes"][1].update(left=20, top=10) or rel()(d),
     "relations[0]: 상자 'A'와 'B'가 겹치거나 맞닿아 둘 사이에 선을 그을 자리가 없다"),
    (lambda d: d["classes"][1].update(left=90) or rel(navigable="none")(d), "relations[0]: 상자 'A'와 'B'가 겹치거나 맞닿아"),
    (lambda d: d["classes"][1].update(left=60) or rel()(d), "relations[0]: 상자 'A'와 'B'가 겹치거나 맞닿아"),
    (lambda d: d["classes"][1].update(left=110) or rel(kind="composition")(d),
     "relations[0]: 선 길이 20가 양 끝 모양 길이(18+10)보다 짧다"),
    (rel(kind="composition", navigable="none", via=[[95, 24], [195, 200]]),
     "relations[0]: from 쪽 끝 구간 길이 5가 끝 모양 길이(18)보다 짧다 — 첫 꺾는 점을"),
    (rel(kind="generalization", via=[[195, 200], [345, 60]]),
     "relations[0]: to 쪽 끝 구간 길이 12가 끝 모양 길이(18)보다 짧다 — 마지막 꺾는 점을"),
    (lambda d: d["classes"][0].update(left=-999_000) or rel(kind="dependency")(d), "relations[0]: 선 길이 999210가 200000을 넘는다"),
    (rel(to="A", via=[[200, 24], [300, 24]]), "relations[0]: 선의 두 끝이 같은 점 (90.0, 24.0)이다"),
    (rel(via=[[-50, 24]]), "relations[0]: 선이 from 상자 'A'(0, 0, 90×48) 안을 지난다"),
    (rel(via=[[320, 24], [345, -60]]), "relations[0]: 선이 to 상자 'B'(300, 0, 90×48) 안을 지난다"),
    (rel(to="A", via=[[120, 24], [-30, 24]]), "relations[0]: 선이 from 상자 'A'"),
])
def test_layout_refuses_lines_it_cannot_draw(change, expected):
    diagram = C.parse(mutate(change))
    with pytest.raises(C.InputError) as e:
        C.layout(diagram)
    assert any(p.startswith(expected) for p in e.value.problems), e.value.problems
