import copy
import math

import pytest
from PIL import Image

from cysuml import boxdiagram as B
from cysuml import classdiagram as C
from cysuml import geom as G
from cysuml import text as T
from cysuml.canvas import Line, Polygon, Rect, Text


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
    ({"kind": "association", "navigable": "both"}, None, None, [END, START]),
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


def test_association_name_sits_above_the_middle_of_a_rightward_line():
    d = C.render(two_boxes(kind="association", name="places"))
    (name,) = [t for t in owned(d, "A->B", Text)]
    assert (name.text, name.x, name.anchor, name.bg) == ("places", 195, "mm", True)
    assert name.box[3] == pytest.approx(24 - C.NAME_GAP)
    assert d.layout.relations[0].labels == (C.Label("name", ("places",), name.x, name.y),)


def test_name_on_a_vertical_line_clears_it_by_the_gap():
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


def test_name_goes_on_the_longest_segment_and_other_side_if_blocked():
    d = C.render(two_boxes(kind="dependency", name="«use»", via=[[150, 200], [450, 200]]))
    (name,) = owned(d, "A->B", Text)
    assert name.x == pytest.approx(300) and name.y < 200
    assert not touches_a_line(d, name.box)

    blocked = two_boxes(kind="dependency", name="«use»", via=[[150, 200], [450, 200]])
    blocked["classes"].append({"name": "Lid", "left": 270, "top": 150, "width": 60, "height": 40})
    d2 = C.render(blocked)
    (name2,) = owned(d2, "A->B", Text)
    assert name2.y > 200 and not touches_a_line(d2, name2.box)


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
    labels = [t for t in d.canvas.records if isinstance(t, Text) and t.bg]
    assert len(labels) == 5
    for i, t in enumerate(labels):
        wide = G.grow(t.box, C.LABEL_CLEAR)
        assert not touches_a_line(d, t.box), t.text
        assert all(G.gap(wide, p.rect) >= 0 for p in d.layout.boxes), t.text
        assert all(G.gap(wide, u.box) >= 0 for u in labels[:i]), t.text


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
