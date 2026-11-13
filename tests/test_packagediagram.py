"""패키지도와 여러 그림이 함께 쓰는 모양(패키지·컴포넌트·아티팩트·노드): 중첩, 탭·두께 띠 규칙, 그리는 차례, 모양 기록."""
import dataclasses
import math

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


@pytest.mark.parametrize("kind", ["association", "aggregation", "composition", "realization", "dependency"])
@pytest.mark.parametrize("source, target", [("a", "b"), ("b", "a")])
def test_packages_stacked_top_to_bottom_pass_with_a_straight_line_of_any_kind(kind, source, target):
    # 선은 탭 오른쪽 몸통의 가운데를 향하므로, 같은 left로 쌓은 패키지 사이 선은 곧게 내려와 탭 오른쪽에 닿는다 — 아래 패키지
    # 윗변의 삼각형·마름모·화살촉도 탭 둘레 검사 여유에 닿지 않는다(패키지는 상속하지 않으니 삼각형은 실체화로 본다)
    d = draw([el("package", "a", 0, 0), el("package", "b", 0, 150)], [rel(kind, source, target)])
    b = placed(d, "b")
    (line,) = d.layout.relations
    assert {p[0] for p in line.points} == {b.anchor[0]} and b.anchor[0] - 9 > b.zones[0].rect[2] + K.BOX_CLEARANCE
    assert K.check(d).passed, K.check(d).summary()


@pytest.mark.parametrize("lower", ["order.domain", "infrastructure", "infrastructure.persistence"])
@pytest.mark.parametrize("kind", ["dependency", "realization"])
def test_stacked_packages_of_different_names_follow_the_tip_with_one_bend(lower, kind):
    # 이름 길이가 다르면 곧은 선은 아래 패키지 탭을 지난다 — 배치 요령대로 탭 오른쪽 끝 + 20, 아래 top - 30에 꺾는 점을 주면 합격
    # (삼각형 끝은 실체화로 본다 — 패키지는 상속하지 않는다)
    elements = [el("package", "app", 0, 0), el("package", lower, 0, 150)]
    (f,) = report(elements, [rel(kind, "app", lower)]).failures
    assert f.kind == "line_through_name"
    tab = placed(draw(elements), lower).zones[0].rect
    assert "이름 칸(" in f.problem and "꺾는 점(via)을 하나 준다" in P.TIPS
    assert report(elements, [rel(kind, "app", lower, via=[[tab[2] + 20, 150 - 30]])]).passed


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


def test_result_adds_the_aim_point_of_packages_only():
    d = draw([el("package", "P", 0, 0, width=300), inside("P", "class", "A", 20, 44), el("component", "K", 400, 0),
              el("node", "N", 400, 150)])
    (line,) = server._places(d)
    p = placed(d, "P")
    assert p.anchor == ((50 + 300) / 2, (HEAD + p.height) / 2)
    assert f"P(0, 0, 300×{p.height:g}, 향하는 점 175, {p.anchor[1]:g})" in line
    assert "A(20, 44, 90×48)" in line and line.count("향하는 점") == 1


@pytest.mark.parametrize("parent", ["base", "infrastructure.persistence"])
def test_packages_share_one_trunk_at_the_x_their_lines_aim_at(parent):
    # 공유 줄기 — 패키지의 x는 결과에 덧붙는 향하는 점(탭 오른쪽 몸통의 가운데)의 x다. 자리 가운데 x로 주면 이름이 긴 패키지는
    # 첫 구간이 제 탭을 지난다(패키지는 상속의 끝이 될 수 없어 같은 삼각형을 쓰는 실체화로 본다)
    elements = [el("package", parent, 200, 0)] + [el("package", n, left, 150) for n, left in
                                                 (("infrastructure", 0), ("web", 220), ("persistence.jpa", 420))]
    boxes = {p.key: p for p in draw(elements).layout.boxes}
    y = (boxes[parent].rect[3] + 150) / 2

    def trunk(x):
        return [rel("realization", k, parent, via=[[x(k), y], [x(parent), y]]) for k in boxes if k != parent]

    assert report(elements, trunk(lambda k: boxes[k].anchor[0])).passed
    middle = report(elements, trunk(lambda k: (boxes[k].rect[0] + boxes[k].rect[2]) / 2))
    assert "line_through_name" in kinds(middle)


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


@pytest.mark.parametrize("corner", ["top-left", "bottom-right"])
def test_element_close_to_the_cut_corner_of_a_node_fails(corner):
    # 노드(100, 100)의 깎인 모서리 대각선 테두리에 0.7px까지 다가온 상자는 붙은 것이다
    n = placed(draw([el("node", "N", 100, 100)]), "N")
    left, top = (0, 0) if corner == "top-left" else (n.rect[2] - 3.5, n.rect[3] - 3.5)
    (f,) = report([el("node", "N", 100, 100), el("class", "E", left, top, width=103.5, height=103.5)]).failures
    assert f.kind == "box_overlap" and "0.7px밖에" in f.problem


def test_child_touching_the_name_area_edge_is_close_not_on_it():
    # 안의 요소 윗변이 노드 이름 칸 아랫변(y=32)에 맞닿기만 하면 "걸친다"가 아니라 칸 테두리에 붙은 것이다
    (f,) = report([el("node", "N", 0, 0), inside("N", "class", "C", 20, DEPTH + HEAD)]).failures
    assert f.kind == "inner_off_area" and "0px밖에 떨어지지 않았다" in f.problem


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


def test_long_node_name_leaves_room_beside_it_on_the_front():
    d = draw([el("node", "ApplicationServerCluster", 0, 0, stereotype="executionEnvironment")])
    n = placed(d, "ApplicationServerCluster")
    (zone,) = n.zones
    assert zone.rect[0] == pytest.approx(B.NEST_PAD) and zone.rect[2] == pytest.approx(n.rect[2] - DEPTH - B.NEST_PAD)


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


# ---------------------------------------------------------------- 아이콘 표기(UML 1 표기 컴포넌트·문서 아이콘 아티팩트)


def test_component_icon_is_a_box_with_two_parts_straddling_its_left_edge():
    d = draw([el("component_icon", "C", 0, 0, stereotype="component")])
    p = placed(d, "C")
    w, h = p.width, p.height
    box, *parts = owned(d, "C", Rect)
    assert (box.left, box.top, box.width, box.height) == (8, 0, w - 8, h)
    cy = h / 2
    assert [(r.left, r.top, r.width, r.height) for r in parts] == [(0, cy - 18, 16, 6), (0, cy + 12, 16, 6)]
    assert p.border == G.RectBorder((8, 0, w, h))
    assert w % 2 == 1 and p.anchor == (math.floor((8 + w) / 2), cy)  # 폭이 홀수(123)라 상자 가운데 65.5를 정수로 내린다
    assert p.zones == tuple(B.NameZone((0, top, 16, top + 6), True, "부품 네모", lettered=False) for top in (cy - 18, cy + 12))
    texts = owned(d, "C", Text)
    assert [t.text for t in texts] == ["«component»", "C"] and texts[0].x == texts[1].x == (8 + w) / 2


@pytest.mark.parametrize("where, kind", [((150, -150), "dependency"), ((-100, 150), "dependency"),
                                         ((250, -60), "dependency"), ((-200, 0), "realization")])
def test_lines_into_a_component_icon_pass_from_above_below_right_and_straight_from_the_left(where, kind):
    d = draw([el("component_icon", "C", 0, 0), el("class", "A", *where)], [rel(kind, "A", "C")])
    end = d.layout.relations[0].points[-1]
    assert any(G.distance((end, end), e, 0) < 1e-9 for e in placed(d, "C").border.edges())
    assert K.check(d).passed, K.check(d).summary()


@pytest.mark.parametrize("kind", ["aggregation", "composition"])
def test_diamond_leaving_a_component_icon_straight_to_the_left_passes_between_its_parts(kind):
    # 마름모(반폭 6)도 네모 사이(24px)로 지나간다 — 부품 네모 간격(PART_OFF 12)의 근거
    r = report([el("component_icon", "C", 0, 0), el("class", "A", -200, 0)], [rel(kind, "C", "A")])
    assert r.passed, r.summary()


@pytest.mark.parametrize("more, x", [({}, 53), ({"stereotype": "component"}, 65)])
def test_line_to_a_component_icon_is_straight_when_aligned_to_the_box_without_its_parts(more, x):
    # 도구 설명대로 선이 향하는 점(부품 네모를 뺀 상자 가운데 — 자리 가운데보다 4px 오른쪽, 반 픽셀이면 내림)에 A의 가운데를 맞춘다.
    # 상자 폭: 90(가운데 53), «component»가 붙으면 115(자리 가운데 61.5 + 4 = 65.5 → 65)
    d = draw([el("component_icon", "C", 0, 0, **more), el("class", "A", x - 45, -150)], [rel("dependency", "A", "C")])
    (line,) = d.layout.relations
    assert line.points[0][0] == line.points[-1][0] == x
    assert K.check(d).passed, K.check(d).summary()


@pytest.mark.parametrize("source, target, via", [("A", "C", [[-40, 24]]), ("C", "A", [[-40, 24], [-90, -76]])])
def test_slanted_line_on_the_left_passes_with_the_bend_next_to_the_component_at_the_aim_height(source, target, via):
    # 도구 설명의 요령: 컴포넌트 쪽 끝에 붙은 꺾는 점(들어오는 선은 마지막, 나가는 선은 첫 꺾는 점)을 선이 향하는 점의 높이(24)에
    # 두면 컴포넌트에 닿는 구간이 가로가 되어 부품 네모 사이로 지난다
    d = draw([el("component_icon", "C", 0, 0), el("class", "A", -200, -100)], [rel("dependency", source, target, via=via)])
    assert K.check(d).passed, K.check(d).summary()


def test_line_through_a_part_of_a_component_icon_fails_and_is_not_called_a_name_area():
    # 왼쪽에서 비스듬히 들어와 위쪽 부품 네모에 걸린다 — 그 컴포넌트가 끝인 선이어도 불합격
    r = report([el("component_icon", "C", 0, 0), el("class", "A", -200, -100)], [rel("dependency", "A", "C")])
    (f,) = r.failures
    assert f.kind == "line_through_name" and "부품 네모(0, 6, 16×6)" in f.problem and "이름 칸" not in f.problem + f.hint


def test_element_or_label_on_a_part_of_a_component_icon_fails():
    # A는 상자(x 8부터)에는 닿지 않고 튀어나온 부품 네모(x 0~16)에만 걸친다
    assert kinds(report([el("component_icon", "C", 0, 0), el("class", "A", -88, 0)])) == ["box_overlap"]
    # 세로선 T→U(x −30)의 가운데가 위쪽 부품 네모(0, 6, 16×6) 높이에 온다. 이름 자리 둘 가운데 왼쪽은 상자 D가 막아 오른쪽(네모 위)에 놓인다
    r = report([el("component_icon", "C", 0, 0), el("class", "T", -75, -246), el("class", "U", -75, 206),
                el("class", "D", -135, -20)], [rel("association", "T", "U", name="uses")])
    (f,) = r.failures
    assert f.kind == "text_on_box" and f.elements == ("T->U", "C")


def test_returned_place_of_a_component_icon_draws_the_same():
    elements = [el("component_icon", "C", 0, 0, stereotype="subsystem"), el("class", "A", 300, 0)]
    relations = [rel("dependency", "A", "C")]
    d = draw(elements, relations)
    p = placed(d, "C")
    again = [{**elements[0], "width": p.width, "height": p.height}, elements[1]]
    assert [repr(r) for r in draw(again, relations).canvas.records] == [repr(r) for r in d.canvas.records]


def test_artifact_icon_is_a_folded_page_with_its_name_outside():
    # 이름 "order.jar"(폭 49)가 문서(폭 30)보다 넓어 모양 자리가 반 픽셀(9.5)에 놓인다 — 문서는 결과의 모양 자리 그대로 그리고,
    # 선이 향하는 점만 정수로 내린다
    d = draw([el("artifact_icon", "order.jar", 0, 0)])
    p = placed(d, "order.jar")
    assert p.rect == (0, 0, 49, 38 + B.NAME_SEP + B.LABEL_LINE) and p.shape_rect == (9.5, 0, 39.5, 38)
    (page,) = owned(d, "order.jar", Polygon)
    (fold,) = owned(d, "order.jar", Line)
    assert page.points == ((9.5, 0), (29.5, 0), (39.5, 10), (39.5, 38), (9.5, 38))
    assert fold.points == ((29.5, 0), (29.5, 10), (39.5, 10))
    assert p.anchor == (24, 19) and p.border == G.PolygonBorder(page.points)
    (name,) = owned(d, "order.jar", Text)
    assert name.text == "order.jar" and p.zones == (B.NameZone((0, 42, 49, 57), True),)


@pytest.mark.parametrize("side, user", [("bottom", (-20, -150)), ("top", (-20, 150)), ("left", (200, -5)),
                                        ("right", (-200, -5))])
def test_artifact_icon_name_sides_pass_and_the_returned_place_draws_the_same(side, user):
    elements = [el("artifact_icon", "order.jar", 0, 0, name_side=side), el("class", "A", *user)]
    relations = [rel("dependency", "A", "order.jar")]
    d = draw(elements, relations)
    assert K.check(d).passed, K.check(d).summary()
    p = placed(d, "order.jar")
    again = [el("artifact_icon", "order.jar", p.rect[0], p.rect[1], name_side=side), elements[1]]
    assert [repr(r) for r in draw(again, relations).canvas.records] == [repr(r) for r in d.canvas.records]


@pytest.mark.parametrize("where", [(-200, -100), (200, -100), (200, 0), (-200, 0)])
def test_slanted_lines_into_an_artifact_icon_end_on_the_page(where):
    d = draw([el("artifact_icon", "app.jar", 0, 0), el("class", "A", *where)], [rel("dependency", "A", "app.jar")])
    end = d.layout.relations[0].points[-1]
    assert any(G.distance((end, end), e, 0) < 1e-9 for e in placed(d, "app.jar").border.edges())
    assert K.check(d).passed, K.check(d).summary()


def test_line_through_the_name_of_an_artifact_icon_fails():
    r = report([el("artifact_icon", "order.jar", 0, 0), el("class", "A", -20, 150)], [rel("dependency", "A", "order.jar")])
    (f,) = r.failures
    assert f.kind == "line_through_name" and "이름 칸(0, 42, 49×15)" in f.problem


@pytest.mark.parametrize("name", ["order.jar", "a.jar", "order-service.jar"])
def test_vertical_line_from_a_centred_component_to_an_artifact_icon_is_straight(name):
    # 기본 폭 90 컴포넌트(가운데 x 45) 아래에, 문서 가운데가 45가 되는 정수 left로 문서 아이콘 아티팩트를 둔다
    w = placed(draw([el("artifact_icon", name, 0, 0)]), name).width
    d = draw([el("component", "Order", 0, 0), el("artifact_icon", name, math.ceil(45 - w / 2), 120)],
             [rel("dependency", name, "Order", stereotype="manifest")])
    (line,) = d.layout.relations
    assert line.points[0][0] == line.points[-1][0] == 45
    assert K.check(d).passed, K.check(d).summary()


def test_icon_kinds_sit_in_packages_and_nodes_and_the_outer_element_covers_them():
    d = draw([el("package", "p", 0, 0), inside("p", "component_icon", "C", 20, 44),
              inside("p", "artifact_icon", "c.jar", 230, 50), el("node", "n", 0, 200),
              inside("n", "component_icon", "D", 20, 252), inside("n", "artifact_icon", "d.jar", 230, 257)],
             [rel("dependency", "c.jar", "C", stereotype="manifest"), rel("dependency", "d.jar", "D", stereotype="manifest")])
    assert K.check(d).passed, K.check(d).summary()
    for outer, inner in (("p", "C"), ("p", "c.jar"), ("n", "D"), ("n", "d.jar")):
        o, i = placed(d, outer), placed(d, inner)
        assert o.inner[0] + B.NEST_PAD <= i.rect[0] and i.rect[2] + B.NEST_PAD <= o.inner[2]
        assert i.rect[3] + B.NEST_PAD <= o.inner[3]


# ---------------------------------------------------------------- 제 화살촉 옆을 지나는 선


@pytest.mark.parametrize("end, passed", [(10, False), (11, True)])
def test_dependency_bent_beside_its_own_arrowhead(end, passed):
    # 클래스 B(0, 0)의 왼쪽 가운데로 오는 의존을 via [[−end, 24]]에서 직각으로 꺾는다. 끝 구간이 화살촉 길이(10)와 같으면 앞 세로
    # 구간이 화살촉 갈래 끝(x ≈ −8.83)에서 1.2px 떨어져 지나 갈래와 한데 붙어 보인다
    r = report([el("class", "B", 0, 0), el("class", "A", -end - 45, 200)], [rel("dependency", "A", "B", via=[[-end, 24]])])
    assert r.passed is passed, r.summary()
    if not passed:
        (f,) = r.failures
        assert f.kind == "line_through_head" and f.elements == ("A->B",)
        assert "선이 제 선 끝 모양에 닿는다" in f.problem and "화살촉" in f.problem
        assert K.bend_away(P.SPEC.words) in f.hint


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("beta", [0, 30, 50])
def test_bend_at_the_advised_distance_clears_its_own_arrowhead(beta, side):
    # 도구 설명이 권하는 거리(ARROW_BEND)에 꺾는 점을 두면, 꺾은 앞 구간(길이 20)이 직각에서 화살촉 쪽으로 β만큼 더 기울어도(꺾는
    # 점을 요소 가운데 줄에서 비켜 둔 꼴) 화살촉 갈래 끝에서 OVERLAP_GAP 넘게 떨어진다. 아래(side 1)·위(−1)에서 와도 같다
    corner = (-K.ARROW_BEND, 24)
    b = math.radians(beta)
    p = (corner[0] + 20 * math.sin(b), corner[1] + side * 20 * math.cos(b))
    r = report([el("class", "B", 0, 0), el("class", "A", p[0] - 300, p[1] - 24 + side * 200)],
               [rel("dependency", "A", "B", via=[list(p), list(corner)])])
    assert r.passed, r.summary()


def test_hint_tells_the_bend_distance_only_when_a_longer_end_segment_would_help():
    # 앞 구간이 직각에서 화살촉 쪽으로 60° 더 기울면 권하는 거리(ARROW_BEND)로도 갈래 끝에 붙는다. 꺾는 점이 이미 그만큼 떨어져
    # 있으니 고치는 법은 거리를 다시 말하지 않는다
    corner = (-K.ARROW_BEND, 24)
    p = (corner[0] + 20 * math.sin(math.radians(60)), corner[1] + 20 * math.cos(math.radians(60)))
    r = report([el("class", "B", 0, 0), el("class", "A", p[0] - 300, p[1] + 176)],
               [rel("dependency", "A", "B", via=[list(p), list(corner)])])
    (f,) = r.failures
    assert f.kind == "line_through_head" and "화살촉" in f.problem
    assert K.bend_away(P.SPEC.words) not in f.hint


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
    # 꺾는 점이 끝 요소 안이라는 오류는 실제로 본 테두리(패키지는 탭 아래 몸통)를 보인다
    with pytest.raises(InputError, match=r"from 요소 'P'\(0, 24, 90×40\) 안이나 테두리 위에 있다"):
        draw([el("package", "P", 0, 0), el("class", "B", 300, 0)], [rel("dependency", "P", "B", via=[[20, 40]])])
    # kind가 빠져도(모든 종류가 이름을 받으므로) 이름이 빠진 것을 함께 알린다
    with pytest.raises(InputError) as e:
        draw([{"left": 0, "top": 0}])
    assert e.value.problems == ("elements[0]: 'name' 필드가 빠졌다", "elements[0]: 'kind' 필드가 빠졌다")


def test_result_lists_the_place_of_every_element_by_key():
    d = draw(NESTED)
    (line,) = server._places(d)
    assert line.startswith("요소 자리(왼, 위, 폭×높이): P(0, 0, ") and "A(40, 88, 90×48)" in line
