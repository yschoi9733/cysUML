"""패키지도와 여러 그림이 함께 쓰는 모양(패키지·컴포넌트·아티팩트·노드): 중첩, 탭·두께 띠 규칙, 그리는 차례, 모양 기록."""
import dataclasses

import pytest

from cysuml import boxcheck as K
from cysuml import boxdiagram as B
from cysuml import geom as G
from cysuml import packagediagram as P
from cysuml import server
from cysuml.canvas import Line, Polygon, Rect, Text
from cysuml.classdiagram import HEAD, NAME_LINE
from cysuml.parsing import InputError
from cysuml.shapes import DEPTH


def el(kind, name, left, top, **more):
    return {"kind": kind, "name": name, "left": left, "top": top, **more}


def inside(parent, kind, name, left, top, **more):
    return el(kind, name, left, top, **{"in": parent}, **more)


def rel(kind, source, target, **more):
    return {"kind": kind, "from": source, "to": target, **more}


def draw(elements, relations=()):
    return P.render({"elements": list(elements), "relations": list(relations)})


def report(elements, relations=()):
    return K.check(draw(elements, relations))


def kinds(r):
    return [f.kind for f in r.failures]


def owned(drawing, owner, typ=object):
    return [r for r in drawing.canvas.records if r.owner == owner and isinstance(r, typ)]


def placed(drawing, key):
    (p,) = [p for p in drawing.layout.boxes if p.key == key]
    return p


# ---------------------------------------------------------------- 패키지와 중첩


NESTED = [el("package", "P", 0, 0), inside("P", "package", "Q", 20, 44), inside("Q", "class", "A", 40, 88),
          inside("Q", "class", "B", 200, 88), el("package", "R", 400, 0), inside("R", "class", "X", 420, 44),
          el("class", "Out", 400, 250)]


def test_packages_with_classes_inside_pass():
    # 두 겹 패키지 안 두 클래스를 잇는 이름 있는 선, 두 겹 밖에서 안쪽 클래스로 가는 선, 패키지끼리 «use» 의존
    r = report(NESTED, [rel("association", "A", "B", name="has"), rel("dependency", "Out", "A"),
                        rel("dependency", "P", "R", stereotype="use")])
    assert r.passed, r.summary()


def test_outer_packages_grow_right_and_down_to_cover_their_elements():
    d = draw(NESTED)
    a, b, q, p = (placed(d, k) for k in "ABQP")
    assert q.rect == (20, 44, b.rect[2] + B.NEST_PAD, b.rect[3] + B.NEST_PAD)
    assert p.rect == (0, 0, q.rect[2] + B.NEST_PAD, q.rect[3] + B.NEST_PAD)
    assert q.inner == (20, 44 + HEAD, q.rect[2], q.rect[3]) and q.border == G.RectBorder(q.inner)
    assert q.zones == (B.NameZone((20, 44, 70, 44 + HEAD), True),)


def test_packages_and_classes_inside_are_drawn_before_and_after_the_lines():
    # 품은 요소(겉에서 안으로) → 선 → 안에 요소가 없는 요소 → 선 글자. 두 겹 패키지 안의 선이 패키지 흰 바탕에 가려지지 않는다
    d = draw(NESTED, [rel("association", "A", "B", name="has")])
    order = [r.owner for r in d.canvas.records]
    last = {k: len(order) - 1 - order[::-1].index(k) for k in ("P", "Q", "A", "B", "R", "X", "A->B")}
    first = {k: order.index(k) for k in last}
    assert last["P"] < first["Q"] and last["Q"] < first["A->B"]
    line_end = max(i for i, r in enumerate(d.canvas.records) if r.owner == "A->B" and not isinstance(r, Text) and
                   not type(r).__name__ == "Mask")
    assert line_end < first["A"] and line_end < first["B"] and first["R"] < first["X"]
    assert isinstance(d.canvas.records[-1], Text) and d.canvas.records[-1].owner == "A->B"


def test_line_through_an_unrelated_package_fails():
    r = report([el("class", "A", 0, 0), el("class", "B", 400, 0), el("package", "P", 200, -10)],
               [rel("association", "A", "B", navigable="none")])
    (f,) = r.failures
    assert f.kind == "line_through_box" and f.elements == ("A->B", "P")


def test_line_through_the_tab_of_the_package_holding_its_end_fails():
    # P 안의 C에서 위의 X로 가는 선이 P 탭(0, 0, 50×24)을 지난다
    r = report([el("package", "P", 0, 0), inside("P", "class", "C", 20, 44), el("class", "X", -60, -150)],
               [rel("dependency", "C", "X")])
    (f,) = r.failures
    assert f.kind == "line_through_name" and f.elements == ("C->X", "P") and "이름 칸(0, 0, 50×24)" in f.problem


def test_line_into_a_package_through_its_own_tab_fails():
    # 왼쪽 위에서 비스듬히 들어와 탭(0, 0, 50×24)을 지나 몸통 윗변에 닿는다
    r = report([el("package", "P", 0, 0), el("class", "X", -150, -150)], [rel("dependency", "X", "P")])
    (f,) = r.failures
    assert f.kind == "line_through_name" and f.elements == ("X->P", "P")


def test_dependency_from_above_onto_the_body_right_of_the_tab_passes():
    d = draw([el("package", "P", 0, 0), inside("P", "class", "C", 20, 44), el("class", "X", 60, -150)],
             [rel("dependency", "X", "P")])
    end = d.layout.relations[0].points[-1]
    assert end[1] == HEAD and end[0] > 50 + K.BOX_CLEARANCE  # 탭 오른쪽 몸통 윗변
    assert K.check(d).passed


@pytest.mark.parametrize("kind", ["association", "aggregation", "composition", "generalization", "realization",
                                  "dependency"])
@pytest.mark.parametrize("source, target", [("a", "b"), ("b", "a")])
def test_packages_stacked_top_to_bottom_pass_with_a_straight_line_of_any_kind(kind, source, target):
    # 선은 탭 오른쪽 몸통의 가운데를 향하므로, 같은 left로 쌓은 패키지 사이 선은 곧게 내려와 탭 오른쪽에 닿는다 — 아래 패키지
    # 윗변의 삼각형·마름모·화살촉도 탭 둘레 검사 여유에 닿지 않는다
    d = draw([el("package", "a", 0, 0), el("package", "b", 0, 150)], [rel(kind, source, target)])
    b = placed(d, "b")
    (line,) = d.layout.relations
    assert {p[0] for p in line.points} == {b.anchor[0]} and b.anchor[0] - 9 > b.zones[0].rect[2] + K.BOX_CLEARANCE
    assert K.check(d).passed, K.check(d).summary()


def test_lines_aim_at_the_middle_of_the_body_right_of_the_tab():
    d = draw([el("package", "p", 0, 0), el("class", "L", -200, 20), el("class", "U", 0, 150)],
             [rel("dependency", "L", "p"), rel("dependency", "U", "p")])
    p = placed(d, "p")
    assert p.anchor == ((50 + p.width) / 2, (HEAD + p.height) / 2)
    left, up = (r.points for r in d.layout.relations)
    assert left[-1][0] == 0 and up[-1][1] == p.height  # 왼쪽 변·아랫변에 닿는다(몸통 테두리)
    for points in (left, up):
        (x0, y0), (x1, y1) = points[-2], points[-1]
        (ax, ay) = p.anchor
        assert (x1 - x0) * (ay - y0) == pytest.approx((y1 - y0) * (ax - x0))  # 선이 그 점을 향한다


def test_element_right_of_a_package_tab_does_not_overlap_the_package():
    # 탭 오른쪽 빈 곳은 패키지가 아니다 — 몸통 윗변 6px 위에 놓인 요소는 패키지와 겹치지 않는다
    assert report([el("package", "p", 0, 0, width=300), el("component", "c", 150, -30)]).passed
    (f,) = report([el("package", "p", 0, 0, width=300), el("component", "c", 30, -30)]).failures
    assert f.kind == "box_overlap" and f.where == (30, 0, 50, 18)


def test_overlapping_elements_inside_a_package_fail_but_holder_and_held_do_not():
    r = report([el("package", "P", 0, 0), inside("P", "class", "A", 20, 44), inside("P", "class", "B", 80, 60)])
    (f,) = r.failures
    assert f.kind == "box_overlap" and f.elements == ("A", "B")


def test_element_placed_over_a_package_without_in_is_an_overlap_with_a_hint():
    (f,) = report([el("package", "P", 0, 0, width=200, height=150), el("class", "A", 40, 60)]).failures
    assert f.kind == "box_overlap" and "A를 P 안에 두려면 A의 in에 P를 준다" in f.hint
    (f,) = report([el("package", "결제", 0, 0, width=200, height=150), el("class", "주문", 40, 60)]).failures
    assert "주문을 결제 안에 두려면 주문의 in에 결제를 준다" in f.hint
    # 탭 오른쪽에서 몸통으로 걸친 요소는 in을 줘도 칸 밖이라 그 힌트를 붙이지 않는다
    (f,) = report([el("package", "P", 0, 0, width=300, height=150), el("class", "A", 150, 10)]).failures
    assert f.kind == "box_overlap" and "in에" not in f.hint


def test_nodes_whose_cut_corners_face_each_other_do_not_overlap():
    # N1의 오른쪽 아래와 N2의 왼쪽 위 깎인 모서리가 자리 사각형으로는 3px 겹치지만, 두 입체 상자는 7px 떨어져 있다
    n1 = placed(draw([el("node", "N1", 0, 0)]), "N1")
    assert report([el("node", "N1", 0, 0), el("node", "N2", n1.rect[2] - 3, n1.rect[3] - 3)]).passed


@pytest.mark.parametrize("left, top, phrase", [(10, 44, "칸 테두리에서 10px밖에"), (20, 10, "이름 칸에 걸친다"),
                                               (-20, 44, "칸 밖으로 나간다")])
def test_element_too_close_to_the_package_edge_or_on_its_tab_fails(left, top, phrase):
    (f,) = report([el("package", "P", 0, 0), inside("P", "class", "C", left, top)]).failures
    assert f.kind == "inner_off_area" and f.elements == ("C", "P") and phrase in f.problem


def test_label_on_a_package_tab_fails():
    d = draw([el("package", "P", 0, 0), inside("P", "class", "A", 20, 44), inside("P", "class", "B", 200, 44)],
             [rel("association", "A", "B", name="has")])
    assert K.check(d).passed
    on_tab = Text(25, 12, "has", False, "mm", True, "A->B")
    moved = dataclasses.replace(d, drawn=(dataclasses.replace(d.drawn[0], labels=((on_tab,),)),))
    (f,) = K.check(moved).failures
    assert f.kind == "text_on_box" and f.elements == ("A->B", "P") and "이름 칸에 겹친다" in f.problem


def test_two_line_package_name_makes_a_taller_tab():
    d = draw([el("package", ["주문", "관리"], 0, 0, id="p"), inside("p", "class", "C", 20, 58 + NAME_LINE)])
    p = placed(d, "p")
    assert p.zones[0].rect[3] == HEAD + NAME_LINE and p.inner[1] == HEAD + NAME_LINE
    assert [t.text for t in owned(d, "p", Text)] == ["주문", "관리"]
    assert K.check(d).passed
    (f,) = report([el("package", ["주문", "관리"], 0, 0, id="p"), inside("p", "class", "C", 20, 44)]).failures
    assert f.kind == "inner_off_area"


def test_package_stereotype_goes_above_the_name_in_the_tab():
    d = draw([el("package", "core", 0, 0, stereotype="subsystem")])
    assert [(t.text, t.bold) for t in owned(d, "core", Text)] == [("«subsystem»", False), ("core", True)]
    assert placed(d, "core").zones[0].rect[3] == HEAD + NAME_LINE


# ---------------------------------------------------------------- 노드


SERVER = [el("node", "서버", 0, 0), inside("서버", "component", "Api", 20, 52), inside("서버", "component", "Db", 130, 52)]


def test_nodes_hold_components_artifacts_and_nodes():
    # 바깥 노드 이름이 두 줄(«device»·서버)이라 안의 요소는 y=66부터, 안쪽 노드 jvm의 요소는 jvm 이름 줄 아래 y=252부터 둔다
    r = report([el("node", "서버", 0, 0, stereotype="device"), inside("서버", "component", "Api", 20, 66),
                inside("서버", "artifact", "app.jar", 220, 66), inside("서버", "node", "jvm", 20, 200),
                inside("jvm", "component", "Svc", 40, 252), inside("jvm", "component", "Cache", 150, 252)],
               [rel("dependency", "Api", "Svc", stereotype="use"), rel("dependency", "app.jar", "Api", stereotype="manifest")])
    assert r.passed, r.summary()


def test_node_area_is_the_front_below_its_name():
    d = draw(SERVER)
    n, db = placed(d, "서버"), placed(d, "Db")
    assert n.inner == (0, DEPTH + HEAD, n.rect[2] - DEPTH, n.rect[3])
    assert n.rect[2] == db.rect[2] + B.NEST_PAD + DEPTH
    assert n.border == G.PolygonBorder(((0, DEPTH), (DEPTH, 0), (n.rect[2], 0), (n.rect[2], n.rect[3] - DEPTH),
                                        (n.rect[2] - DEPTH, n.rect[3]), (0, n.rect[3])))


def test_element_on_the_thickness_band_of_a_node_fails():
    (f,) = report([el("node", "서버", 0, 0), inside("서버", "component", "Api", 20, 4)]).failures
    assert f.kind == "inner_off_area" and f.elements == ("Api", "서버")


def test_label_of_a_line_leaving_a_node_upward_keeps_off_the_band():
    # Api(20, 52)에서 바로 위 T(바닥 y=-24)로 가는 선의 from 쪽이 아니라 to 쪽 다중도: T 밑 가까운 후보는 두께 띠(y 0~8)에
    # 걸리므로 도구가 띠를 비킨 자리를 고른다
    d = draw([*SERVER, el("class", "T", 20, -72)], [rel("association", "Api", "T", to_multiplicity="0..*")])
    r = K.check(d)
    assert r.passed, r.summary()
    (label,) = d.layout.relations[0].labels
    end, toward = d.layout.relations[0].points[-1], d.layout.relations[0].points[-2]
    first = B.lines_box(*B.multiplicity_spots(end, toward)[0], ("0..*",))
    band = placed(d, "서버").frame
    assert any(G.hits(p, q, G.grow(first, B.LABEL_CLEAR)) for p, q in band)
    chosen = B.lines_box(label.x, label.y, label.lines)
    assert not any(G.hits(p, q, G.grow(chosen, B.LABEL_CLEAR)) for p, q in band)


def test_label_on_the_band_and_line_along_the_front_top_edge_fail():
    # 선 가운데가 띠 높이(y=8)라 이름 자리 둘 다 띠에 걸린다
    r = report([*SERVER, el("class", "T", 20, -84)], [rel("association", "Api", "T", name="uses")])
    assert kinds(r) == ["text_on_box"] and r.failures[0].elements == ("Api->T", "서버")
    # 앞면 윗변(y=8) 3px 아래를 따라 왼쪽으로 가다 위로 나간다
    r = report([*SERVER, el("class", "T", -33, -200)],
               [rel("dependency", "Api", "T", via=[[65, 11], [12, 11], [12, -100]])])
    (f,) = r.failures
    assert f.kind == "line_along_container" and f.elements == ("Api->T", "서버")


def test_line_through_the_empty_corner_of_a_node_passes_but_not_of_a_box():
    via = [[-22, 22], [22, -22], [145, -22]]  # 왼쪽 위 모서리를 x+y=0으로 깎는다(노드 모서리 빈 곳은 띠 폭 8)
    elements = [el("class", "A", -160, -2), el("class", "B", 100, -150)]
    relations = [rel("association", "A", "B", navigable="none", via=via)]
    assert report([*elements, el("node", "N", 0, 0)], relations).passed
    assert kinds(report([*elements, el("class", "N", 0, 0)], relations)) == ["line_through_box"]


def test_lines_end_on_the_outer_edge_of_a_node():
    d = draw([el("node", "N", 0, 0), el("class", "A", 300, -150)], [rel("dependency", "A", "N")])
    end = d.layout.relations[0].points[-1]
    n = placed(d, "N")
    assert any(G.distance((end, end), e, 0) < 1e-9 for e in n.border.edges())
    assert end[1] < DEPTH or end[0] > n.rect[2] - DEPTH  # 앞면이 아니라 두께 띠 바깥 테두리
    assert K.check(d).passed


def test_returned_place_of_a_node_and_component_draws_the_same():
    elements = [el("node", "N", 0, 0, stereotype="device"), inside("N", "component", "C", 20, 66)]
    d = draw(elements)
    again = [{**e, "left": p.rect[0], "top": p.rect[1], "width": p.width, "height": p.height}
             for e, p in zip(elements, d.layout.boxes)]
    assert [repr(r) for r in draw(again).canvas.records] == [repr(r) for r in d.canvas.records]


# ---------------------------------------------------------------- 모양 기록


def test_component_is_a_box_with_a_part_icon_and_a_centred_name():
    d = draw([el("component", "Payment", 0, 0, stereotype="component")])
    p = placed(d, "Payment")
    box, icon, *nubs = owned(d, "Payment", Rect)
    assert (box.left, box.top, box.width, box.height) == (0, 0, p.width, p.height)
    assert (icon.left + icon.width, icon.top) == (p.width - 6, 6) and (icon.width, icon.height) == (12, 15)
    assert [(n.left, n.top, n.width, n.height) for n in nubs] == [(icon.left - 3, 9, 6, 3), (icon.left - 3, 15, 6, 3)]
    texts = owned(d, "Payment", Text)
    assert [t.text for t in texts] == ["«component»", "Payment"] and texts[0].x == texts[1].x == p.width / 2
    assert texts[-1].box[2] < icon.left - 3  # 이름이 아이콘과 겹치지 않는다


def test_artifact_is_a_box_with_a_folded_document_icon():
    d = draw([el("artifact", "app.jar", 0, 0)])
    p = placed(d, "app.jar")
    (box,) = owned(d, "app.jar", Rect)
    (page,) = owned(d, "app.jar", Polygon)
    (fold,) = owned(d, "app.jar", Line)
    x = p.width - 6 - 12
    assert page.points == ((x, 6), (x + 8, 6), (x + 12, 10), (x + 12, 21), (x, 21))
    assert fold.points == ((x + 8, 6), (x + 8, 10), (x + 12, 10))
    assert [t.text for t in owned(d, "app.jar", Text)] == ["app.jar"]


def test_node_is_drawn_as_a_box_with_thickness():
    d = draw([el("node", "N", 0, 0)])
    n = placed(d, "N")
    w, h = n.width, n.height
    (body,) = owned(d, "N", Polygon)
    edges = [r.points for r in owned(d, "N", Line)]
    assert body.points == ((0, 8), (8, 0), (w, 0), (w, h - 8), (w - 8, h), (0, h))
    assert edges == [((0, 8), (w - 8, 8), (w - 8, h)), ((w - 8, 8), (w, 0))]
    (t,) = owned(d, "N", Text)
    assert t.x == (w - 8) / 2 and t.y == 8 + 13


# ---------------------------------------------------------------- 섞어 그리기·도구


def test_classes_and_components_in_one_picture_pass():
    r = report([el("component", "Order", 0, 0), el("interface", "OrderService", 0, 150, operations=["+place(): Order"]),
                el("class", "OrderServiceImpl", 250, 150)],
               [rel("realization", "OrderServiceImpl", "OrderService"),
                rel("dependency", "Order", "OrderService", stereotype="use")])
    assert r.passed, r.summary()


def test_component_realized_by_classes_in_a_package_passes():
    r = report([el("component", "Billing", 120, 0), el("package", "billing", 0, 140),
                inside("billing", "class", "Invoice", 20, 184), inside("billing", "class", "Tax", 200, 184)],
               [rel("realization", "Invoice", "Billing"), rel("realization", "Tax", "Billing")])
    assert r.passed, r.summary()


def test_package_tool_input_errors():
    with pytest.raises(InputError) as e:
        draw([el("class", "A", 0, 0), inside("A", "class", "B", 20, 44), el("usecase", "U", 0, 200)])
    assert [p.split(":")[0] for p in e.value.problems] == ["elements[2].kind", "elements[1].in"]
    # kind가 빠져도(모든 종류가 이름을 받으므로) 이름이 빠진 것을 함께 알린다
    with pytest.raises(InputError) as e:
        draw([{"left": 0, "top": 0}])
    assert e.value.problems == ("elements[0]: 'name' 필드가 빠졌다", "elements[0]: 'kind' 필드가 빠졌다")


def test_result_lists_the_place_of_every_element_by_key():
    d = draw(NESTED)
    (line,) = server._places(d)
    assert line.startswith("요소 자리(왼, 위, 폭×높이): P(0, 0, ") and "A(40, 88, 90×48)" in line
