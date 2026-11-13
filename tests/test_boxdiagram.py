"""공용 엔진(boxdiagram·boxcheck)을 시험용 모양·관계 종류·도구로 본다 — 뒤 그림 모듈이 엔진을 고치지 않고 제 모양을 더할 수
있는지, 타원·볼록 다각형 테두리, 모양 밖 이름, 열쇠, 바깥 요소가 이 틀에서 도는지."""
import math

import pytest

from cysuml import boxcheck as K
from cysuml import boxdiagram as B
from cysuml import geom as G
from cysuml import server
from cysuml import text as T
from cysuml.canvas import Ellipse, Line, Polygon, Text
from cysuml.classdiagram import CLASS_SHAPES, RELATIONS
from cysuml.parsing import InputError
from cysuml.report import fmt_rect
from cysuml.shapes import PACKAGE


def _center_lines(c, p, rect, lines):
    cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
    for s, y in zip(lines, B.line_ys(cy, len(lines))):
        c.text(cx, y, s, anchor="mm", owner=p.key)


def _width(lines, pad):
    return math.ceil(max(T.text_width(s) for s in lines)) + pad


class Oval(B.Shape):
    """시험용 타원(유즈케이스 꼴): 이름을 안 가운데에 쓴다."""

    def size(self, e):
        return max(120, _width(e.name, 40)), max(60, B.LABEL_LINE * len(e.name) + 30)

    def border(self, e, rect):
        l, t, r, b = rect
        return G.EllipseBorder((l + r) / 2, (t + b) / 2, (r - l) / 2, (b - t) / 2)

    def draw(self, c, p):
        l, t, r, b = p.shape_rect
        c.ellipse(l, t, r - l, b - t, owner=p.key)
        _center_lines(c, p, p.shape_rect, p.box.name)


class Dot(B.Shape):
    """시험용 작은 원(인터페이스 원·액터 꼴): 이름을 모양 밖에 쓴다."""

    outside_name = True
    sized = False

    def size(self, e):
        return 24, 24

    def border(self, e, rect):
        l, t, r, b = rect
        return G.EllipseBorder((l + r) / 2, (t + b) / 2, (r - l) / 2, (b - t) / 2)

    def draw(self, c, p):
        l, t, r, b = p.shape_rect
        c.ellipse(l, t, r - l, b - t, owner=p.key)


class Gem(B.Shape):
    """시험용 팔각형(볼록 다각형 테두리 — 결정 마름모·노드 꼴)."""

    CUT = 24

    def size(self, e):
        return max(100, _width(e.name, 2 * self.CUT)), 80

    def corners(self, rect):
        l, t, r, b = rect
        k = self.CUT
        return ((l + k, t), (r - k, t), (r, t + k), (r, b - k), (r - k, b), (l + k, b), (l, b - k), (l, t + k))

    def border(self, e, rect):
        return G.PolygonBorder(self.corners(rect))

    def draw(self, c, p):
        c.poly(self.corners(p.rect), owner=p.key)
        _center_lines(c, p, p.rect, p.box.name)


class Room(B.Shape):
    """시험용 바깥 요소(복합 상태 꼴): 모서리를 깎은 테두리 안쪽 위에, 이름 줄과 그 아래 글자 줄(notes)을 든 이름 칸이 있다."""

    holds = True
    fields = ("notes",)
    CUT = 6

    def read(self, r, o, path, kind):
        return tuple(r.text(s, f"{path}.notes[{i}]") for i, s in enumerate(r.items(o["notes"], f"{path}.notes"))) \
            if "notes" in o else ()

    def lines(self, e):
        return e.name + e.data

    def zone_height(self, e):
        return 10 + B.LABEL_LINE * len(self.lines(e))

    def size(self, e):
        return max(120, _width(self.lines(e), 20)), self.zone_height(e) + 40

    def insets(self, e):
        return 0, self.zone_height(e), 0, 0

    def corners(self, rect):
        l, t, r, b = rect
        k = self.CUT
        return ((l + k, t), (r - k, t), (r, t + k), (r, b - k), (r - k, b), (l + k, b), (l, b - k), (l, t + k))

    def border(self, e, rect):
        return G.PolygonBorder(self.corners(rect))

    def name_zones(self, e, rect):
        return (B.NameZone((rect[0], rect[1], rect[2], rect[1] + self.zone_height(e)), False),)

    def draw(self, c, p):
        l, t, r, b = p.rect
        c.poly(self.corners(p.rect), owner=p.key)
        z = t + self.zone_height(p.box)
        c.line([(l, z), (r, z)], owner=p.key)
        _center_lines(c, p, (l, t, r, z), self.lines(p.box))


class Spot(B.Shape):
    """시험용 이름 없는 점(시작 점 꼴)."""

    named = False
    sized = False
    stereotyped = False

    def size(self, e):
        return 16, 16

    def border(self, e, rect):
        l, t, r, b = rect
        return G.EllipseBorder((l + r) / 2, (t + b) / 2, 8, 8)

    def draw(self, c, p):
        l, t, r, b = p.rect
        c.ellipse(l, t, r - l, b - t, fill="black", owner=p.key)


FLOW = B.RelationType("흐름", end=B.ARROW_HEAD)  # 실선·열린 화살촉, 방향 필드 없음
SHAPES = {**CLASS_SHAPES, "package": PACKAGE, "oval": Oval(), "dot": Dot(), "gem": Gem(), "room": Room(), "spot": Spot()}
SPEC = B.Spec(SHAPES, {**RELATIONS, "flow": FLOW})


def draw(elements, relations=(), spec=SPEC):
    return B.render(spec, {"elements": list(elements), "relations": list(relations)})


def report(elements, relations=(), spec=SPEC):
    return K.check(draw(elements, relations, spec))


def kinds(r):
    return [f.kind for f in r.failures]


def el(kind, name, left, top, **more):
    return {"kind": kind, "name": name, "left": left, "top": top, **more}


def rel(kind, source, target, **more):
    return {"kind": kind, "from": source, "to": target, **more}


def owned(drawing, owner, typ):
    return [r for r in drawing.canvas.records if r.owner == owner and isinstance(r, typ)]


def on_ellipse(p, rect, eps=1e-6):
    l, t, r, b = rect
    return abs(((p[0] - (l + r) / 2) / ((r - l) / 2)) ** 2 + ((p[1] - (t + b) / 2) / ((b - t) / 2)) ** 2 - 1) < eps


# ---------------------------------------------------------------- 타원·볼록 다각형 테두리


CORNER = [[-10, 14], [14, -10], [105, -10]]  # (0, 0)에 놓인 요소의 왼쪽 위 모서리를 비스듬히 깎고 그 위로 가는 꺾는 점


def past_the_corner(kind):
    """A(-150, -10)→B(60, -150) 선이 (0, 0) 요소의 왼쪽 위 모서리를 x+y=4로 깎고 위(y=-10)로 지나간다."""
    return report([el("class", "A", -150, -10), el("class", "B", 60, -150), el(kind, "O", 0, 0)],
                  [rel("association", "A", "B", navigable="none", via=CORNER)])


def test_line_through_the_empty_corner_of_an_ellipse_passes_but_not_of_a_box():
    assert past_the_corner("oval").passed  # 타원은 (0, 0, 120, 60)을 덮지만 그 모서리 쪽은 비어 있다
    assert kinds(past_the_corner("class")) == ["line_through_box"]


def test_line_through_the_cut_corner_of_a_convex_polygon_passes():
    assert past_the_corner("gem").passed


def test_line_ends_on_the_real_ellipse_and_polygon():
    d = draw([el("oval", "O", 0, 0), el("gem", "G", 300, 150), el("class", "C", 0, 250)],
             [rel("dependency", "O", "G"), rel("dependency", "C", "O"), rel("dependency", "C", "G")])
    (o,) = [p for p in d.layout.boxes if p.key == "O"]
    (g,) = [p for p in d.layout.boxes if p.key == "G"]
    first, second, third = (r.points for r in d.layout.relations)
    assert on_ellipse(first[0], o.rect) and on_ellipse(second[-1], o.rect)
    corners = Gem().corners(g.rect)
    on_gem = [any(G.distance((p, p), e, 1e-9) < 1e-6 for e in zip(corners, corners[1:] + corners[:1]))
              for p in (first[-1], third[-1])]
    assert on_gem == [True, True]
    assert K.check(d).passed, K.check(d).summary()


@pytest.mark.parametrize("kind", ["oval", "gem"])
@pytest.mark.parametrize("relation", ["dependency", "generalization", "realization"])
def test_lines_coming_in_at_a_slant_pass_with_arrowheads_and_triangles(kind, relation):
    # 선이 납작한 타원·팔각형(240×60·240×80)에 가로·세로가 아닌 방향(가운데를 향해 비스듬히)으로 들어온다
    for left, top in [(-260, -200), (420, -160), (-200, 230), (380, 260), (120, -220), (-300, 10)]:
        r = report([el(kind, "O", 0, 0, width=240), el("class", "A", left, top)], [rel(relation, "A", "O")])
        assert r.passed, (left, top, r.summary())


# ---------------------------------------------------------------- 모양 밖 이름


def dot(name="Api", left=0, top=0, **more):
    return el("dot", name, left, top, **more)


def test_outside_name_goes_below_the_shape_and_the_place_covers_both():
    d = draw([dot("LongInterfaceName")])
    (p,) = d.layout.boxes
    tw = math.ceil(T.text_width("LongInterfaceName"))
    assert p.rect == (0, 0, tw, 24 + B.NAME_SEP + B.LABEL_LINE)
    assert p.shape_rect == ((tw - 24) / 2, 0, (tw + 24) / 2, 24)
    (t,) = owned(d, "LongInterfaceName", Text)
    assert t.text == "LongInterfaceName" and t.y == pytest.approx(24 + B.NAME_SEP + B.LABEL_LINE / 2)
    assert p.zones == (B.NameZone((0, 24 + B.NAME_SEP, tw, p.rect[3]), True),)
    assert server._places(d) == [f"요소 자리(왼, 위, 폭×높이): LongInterfaceName({fmt_rect(p.rect)}, 모양 {fmt_rect(p.shape_rect)})"]


def test_outside_name_shape_ignores_a_default_width():
    class WideDot(Dot):
        default_width = 200  # 모양 밖 이름이 있는 모양은 크기를 받지 않으므로 자리를 늘리지 않는다

    spec = B.Spec({"dot": Dot(), "wide": WideDot()}, {"flow": FLOW})
    plain, wide = (draw([el(k, "Api", 0, 0)], spec=spec).layout.boxes[0] for k in ("dot", "wide"))
    assert (wide.rect, wide.shape_rect, wide.zones) == (plain.rect, plain.shape_rect, plain.zones)


def test_placed_elements_and_borders_are_hashable():
    d = draw([el("class", "A", 0, 0), el("gem", "G", 200, 0), el("oval", "O", 400, 0), dot("D", 600, 0)])
    assert len({hash(p) for p in d.layout.boxes}) == 4
    assert G.PolygonBorder([(0, 0), (1, 0), (0, 1)]) in {G.PolygonBorder([(0, 0), (1, 0), (0, 1)])}


def test_two_line_outside_name_is_two_texts_and_a_taller_place():
    one, two = draw([dot("Api")]).layout.boxes[0], draw([dot(["Api", "v2"], id="api")])
    (p,) = two.layout.boxes
    assert p.height == one.height + B.LABEL_LINE
    assert [t.text for t in owned(two, "api", Text)] == ["Api", "v2"]


@pytest.mark.parametrize("side, shop", [("top", (-19, 150)), ("left", (200, -12)), ("right", (-200, -12)),
                                        ("bottom", (-19, -150))])
def test_outside_name_side_passes_and_the_returned_place_draws_the_same(side, shop):
    # Shop은 이름 반대쪽에 두어 선이 이름을 지나지 않고 원에 닿게 한다
    elements = [dot("Payment", 0, 0, name_side=side), el("class", "Shop", *shop)]
    relations = [rel("dependency", "Shop", "Payment")]
    d = draw(elements, relations)
    assert K.check(d).passed, K.check(d).summary()
    p = d.layout.boxes[0]
    again = [dot("Payment", p.rect[0], p.rect[1], name_side=side), elements[1]]
    assert [repr(r) for r in draw(again, relations).canvas.records] == [repr(r) for r in d.canvas.records]
    shape, name = p.shape_rect, p.zones[0].rect
    where = {"top": name[3] <= shape[1], "bottom": name[1] >= shape[3], "left": name[2] <= shape[0],
             "right": name[0] >= shape[2]}
    assert where[side]


def test_lines_end_on_the_shape_and_may_not_pass_the_outside_name():
    # 선이 Payment 모양(원) 아래쪽에서 올라와 이름을 지나 원에 닿는다 — 제 끝 요소의 이름이라도 불합격
    r = report([dot("Payment", 0, 0), el("class", "Shop", -33, 150)], [rel("dependency", "Shop", "Payment")])
    (f,) = r.failures
    assert f.kind == "line_through_name" and f.elements == ("Shop->Payment", "Payment")
    d = draw([dot("Payment", 0, 0), el("class", "Shop", -33, 150)], [rel("dependency", "Shop", "Payment", via=[[-60, 174],
                                                                                                         [-60, 12]])])
    p = d.layout.boxes[0]
    assert on_ellipse(d.layout.relations[0].points[-1], p.shape_rect) and K.check(d).passed


def test_line_through_the_outside_name_of_another_element_fails():
    r = report([dot("Payment", 100, 0), el("class", "A", -100, 0), el("class", "B", 300, 0)],
               [rel("association", "A", "B", navigable="none", via=[[0, 35], [200, 35]])])
    assert kinds(r) == ["line_through_box"] and r.failures[0].elements == ("A->B", "Payment")


def test_element_or_label_on_the_outside_name_fails():
    assert kinds(report([dot("Payment", 0, 0), el("class", "A", 0, 34)])) == ["box_overlap"]
    # 관계 이름 자리 둘(선 y=24 가운데 위아래) 가운데 아래는 상자 C가 막고, 위에는 Payment 이름(선에서 9px)이 있다
    r = report([dot("Payment", 165, -28), el("class", "A", 0, 0), el("class", "B", 300, 0), el("class", "C", 150, 29)],
               [rel("association", "A", "B", name="has")])
    (f,) = r.failures
    assert f.kind == "text_on_box" and f.elements == ("A->B", "Payment")


def test_outer_element_grows_to_cover_the_outside_name():
    d = draw([el("package", "p", 0, 0), dot("Payment", 20, 44, **{"in": "p"})])
    p, d_ = d.layout.boxes
    assert p.inner[3] == d_.rect[3] + B.NEST_PAD > d_.shape_rect[3] + B.NEST_PAD
    assert K.check(d).passed


# ---------------------------------------------------------------- 열쇠·이름


def test_keys_point_to_nameless_two_line_and_same_named_elements():
    d = draw([el("room", "본체", 0, 0, id="room"),
              {"kind": "spot", "id": "start", "left": 20, "top": 60, "in": "room"},
              el("oval", ["주문을", "받는다"], 100, 50, id="take", **{"in": "room"}),
              el("class", "Item", 300, 0, id="item1"), el("class", "Item", 300, 100, id="item2")],
             [rel("flow", "start", "take"), rel("dependency", "item1", "item2"), rel("dependency", "take", "item1")])
    assert [p.key for p in d.layout.boxes] == ["room", "start", "take", "item1", "item2"]
    assert [r.owner for r in d.layout.relations] == ["start->take", "item1->item2", "take->item1"]
    assert [t.text for t in owned(d, "item1", Text)] == ["Item"] == [t.text for t in owned(d, "item2", Text)]
    assert [t.text for t in owned(d, "take", Text)] == ["주문을", "받는다"]
    assert K.check(d).passed, K.check(d).summary()
    (places,) = server._places(d)
    assert [part.split("(")[0] for part in places.split(": ", 1)[1].split("), ")] == ["room", "start", "take", "item1",
                                                                                     "item2"]


@pytest.mark.parametrize("element, expected", [
    (el("oval", ["두", "줄"], 0, 0), "elements[0]: 'id' 필드가 빠졌다 — 이름이 여러 줄이면"),
    ({"kind": "spot", "left": 0, "top": 0}, "elements[0]: 'id' 필드가 빠졌다 — 이름이 없는 요소는"),
    ({"kind": "spot", "name": "x", "id": "s", "left": 0, "top": 0}, "elements[0].name: 모르는 필드다"),
    (el("oval", [], 0, 0, id="o"), "elements[0].name: 비어 있다"),
    (el("oval", "a\nb", 0, 0), "elements[0].name: 제어·서식 문자나 줄 나눔은"),
    (el("oval", 3, 0, 0), "elements[0].name: 문자열이나 줄마다 문자열인 목록이어야 한다"),
    (el("triangle", "x", 0, 0), "elements[0].kind: 'class' · 'abstract'"),
    ({"name": "x", "left": 0, "top": 0}, "elements[0]: 'kind' 필드가 빠졌다"),
    ({"kind": "oval", "left": 0, "top": 0}, "elements[0]: 'name' 필드가 빠졌다"),
    (el("oval", "x", 0, 0, name_side="top"), "elements[0].name_side: 모르는 필드다"),
    (el("dot", "x", 0, 0, name_side="up"), "elements[0].name_side: 'bottom' · 'top' · 'left' · 'right'"),
    (el("dot", "x", 0, 0, width=40), "elements[0].width: 모르는 필드다"),
])
def test_wrong_element_input(element, expected):
    with pytest.raises(InputError) as e:
        draw([element])
    assert any(p.startswith(expected) for p in e.value.problems), e.value.problems


@pytest.mark.parametrize("elements, relations, expected", [
    ([el("class", "A", 0, 0), el("class", "A", 200, 0)], [], "elements[1].name: elements[0]와 열쇠가 같다 — id가 없으면"),
    ([el("class", "A", 0, 0, id="x"), el("class", "B", 200, 0, id="x")], [], "elements[1].id: elements[0]와 열쇠가 같다"),
    ([el("class", "A", 0, 0)], [rel("flow", "A", "Z")], "relations[0].to: 열쇠가 'Z'인 요소가 없다(있는 요소: 'A')"),
    ([el("class", "A", 0, 0)], [rel("arrow", "A", "A")], "relations[0].kind: 'association'"),
    ([el("class", "A", 0, 0), el("class", "B", 20, 44, **{"in": "A"})], [], "elements[1].in: elements[0]('class')는 안에 "
                                                                            "요소를 둘 수 없다 — 안에 요소를 두는 종류: 'package' · 'room'"),
    ([el("package", "P", 0, 0, **{"in": "Q"})], [], "elements[0].in: 열쇠가 'Q'인 요소가 없다"),
    ([el("package", "P", 0, 0, **{"in": "P"})], [], "elements[0].in: 제 자신 안에 둘 수 없다"),
    ([el("package", "P", 0, 0, **{"in": "Q"}), el("package", "Q", 0, 0, **{"in": "P"})], [],
     "elements[0].in: in이 고리를 이룬다('P' → 'Q' → 'P')"),
    ([el("package", "P", 0, 0), el("class", "C", 20, 44, **{"in": "P"})], [rel("dependency", "C", "P")],
     "relations[0]: 한 끝('C')이 다른 끝('P') 안에 있다 — 품은 요소와 그 안의 요소는 선으로 잇지 않는다"),
    ([el("class", "A", 0, 0), el("class", "B", 200, 0)], [rel("flow", "A", "B", navigable="to")],
     "relations[0].navigable: 방향은 연관·집합·합성에만 쓴다(이 관계는 'flow' — 화살촉은 늘 to 쪽이다)"),
    ([el("class", "A", 0, 0), el("class", "B", 200, 0)], [rel("flow", "A", "B", stereotype="«x»")],
     "relations[0].stereotype: «» 없이 이름만 쓴다"),
    ([el("class", "A", 0, 0), el("class", "B", 200, 0)], [rel("flow", "A", "B", name=["a", ""])],
     "relations[0].name[1]: 비어 있다"),
])
def test_wrong_keys_nesting_and_relations(elements, relations, expected):
    with pytest.raises(InputError) as e:
        draw(elements, relations)
    assert any(p.startswith(expected) for p in e.value.problems), e.value.problems


def test_other_problems_are_told_with_a_wrong_in():
    # E의 in이 틀려도(클래스 안) C→P(품은 요소와 그 안의 요소) 관계 문제를 함께 알린다
    with pytest.raises(InputError) as e:
        draw([el("package", "P", 0, 0), el("class", "C", 20, 44, **{"in": "P"}), el("class", "K", 300, 0),
              el("class", "E", 320, 44, **{"in": "K"})], [rel("dependency", "C", "P")])
    assert [p.split(":")[0] for p in e.value.problems] == ["elements[3].in", "relations[0]"]


def test_wrong_id_does_not_make_relations_to_the_name_missing():
    with pytest.raises(InputError) as e:
        draw([el("class", "A", 0, 0, id=5), el("class", "B", 300, 0)], [rel("dependency", "A", "B")])
    assert [p.split(":")[0] for p in e.value.problems] == ["elements[0].id"]


def test_a_loop_of_in_is_told_once():
    with pytest.raises(InputError) as e:
        draw([el("package", "A", 0, 0, **{"in": "C"}), el("package", "B", 0, 0, **{"in": "A"}),
              el("package", "C", 0, 0, **{"in": "B"})])
    assert e.value.problems == ("elements[0].in: in이 고리를 이룬다('A' → 'C' → 'B' → 'A')",)


def test_report_passed_text_follows_the_tool_words():
    assert K.Report.PASSED == "합격 — 선이 상자·글자를 지나거나 겹친 곳이 없다."  # 클래스에서 읽으면 클래스도 도구의 말
    r = report([el("class", "A", 0, 0)])
    assert r.PASSED == "합격 — 선이 요소·글자를 지나거나 겹친 곳이 없다." and r.summary().startswith(r.PASSED)
    assert r.SHRINK == "요소를 가까이 모으거나 배율을 낮춘다"


def test_large_ellipse_uses_more_sides_to_stay_close():
    big = G.EllipseBorder(0, 0, 1000, 600)
    n = len(big.polygon.points)
    assert n > G.ELLIPSE_SIDES and 1000 * (1 - math.cos(math.pi / n)) <= G.ELLIPSE_SAG
    assert len(G.EllipseBorder(0, 0, 50, 30).polygon.points) == G.ELLIPSE_SIDES


def test_only_elements_in_a_loop_are_told_about_it():
    # A가 제 자신 안에 있으면 A만 알린다 — A 안의 B는 고리가 아니다
    with pytest.raises(InputError) as e:
        draw([el("package", "A", 0, 0, **{"in": "A"}), el("package", "B", 20, 44, **{"in": "A"})])
    assert e.value.problems == ("elements[0].in: 제 자신 안에 둘 수 없다",)


def test_class_diagram_tool_keeps_its_own_input():
    from cysuml import classdiagram as C
    with pytest.raises(InputError) as e:
        C.parse({"classes": [{"name": ["A", "B"], "left": 0, "top": 0, "id": "a", "in": "p"}],
                 "relations": [rel("association", "A", "A", stereotype="x")]})
    assert {p.split(":")[0] for p in e.value.problems} >= {"classes[0].id", "classes[0].in", "classes[0].name",
                                                            "relations[0].stereotype"}


def test_stereotype_and_name_of_a_relation_are_two_lines_and_pass():
    d = draw([el("class", "A", 0, 0), el("class", "B", 300, 0)],
             [rel("association", "A", "B", stereotype="use", name="places")])
    assert [t.text for t in owned(d, "A->B", Text)] == ["«use»", "places"]
    a, b = owned(d, "A->B", Text)
    assert b.y - a.y == B.LABEL_LINE and a.box[3] <= b.box[1] and b.box[3] < 24  # 두 줄 모두 선(y=24) 위
    assert K.check(d).passed


def test_two_line_relation_name_goes_under_the_stereotype_and_passes():
    d = draw([el("class", "A", 0, 0), el("class", "B", 0, 300)],
             [rel("flow", "A", "B", stereotype="include", name=["긴 전이 글자", "[조건]"])])
    assert [t.text for t in owned(d, "A->B", Text)] == ["«include»", "긴 전이 글자", "[조건]"]
    assert d.layout.relations[0].labels[0].lines == ("«include»", "긴 전이 글자", "[조건]")
    assert K.check(d).passed


# ---------------------------------------------------------------- 도구마다 정하는 것


def test_default_direction_of_associations_is_set_per_tool():
    elements, relations = [el("class", "A", 0, 0), el("class", "B", 300, 0)], [rel("aggregation", "A", "B")]
    plain = B.Spec(SHAPES, RELATIONS, navigable="none")
    arrows = [r for r in draw(elements, relations, plain).canvas.records if isinstance(r, Line) and len(r.points) == 3]
    assert arrows == []
    assert len([r for r in draw(elements, relations).canvas.records if isinstance(r, Line) and len(r.points) == 3]) == 1
    assert draw(elements, [rel("association", "A", "B")], plain).layout.relations[0].relation.navigable == "none"


def test_a_tool_with_one_relation_kind_reads_a_relation_without_kind_as_that_kind():
    one = B.Spec(SHAPES, {"flow": FLOW})
    d = draw([el("class", "A", 0, 0), el("class", "B", 300, 0)], [{"from": "A", "to": "B"}], one)
    assert d.layout.relations[0].relation.kind == "flow"
    with pytest.raises(InputError, match=r"relations\[0\]: 'kind' 필드가 빠졌다"):
        draw([el("class", "A", 0, 0), el("class", "B", 300, 0)], [{"from": "A", "to": "B"}])


def test_kinds_a_tool_does_not_take_are_input_errors():
    small = B.Spec({"oval": SHAPES["oval"]}, {"flow": FLOW})
    with pytest.raises(InputError) as e:
        draw([el("class", "A", 0, 0), el("oval", "O", 300, 0), el("oval", "P", 600, 0)],
             [{"kind": "dependency", "from": "O", "to": "P"}], small)
    assert [p.split(":")[0] for p in e.value.problems] == ["elements[0].kind", "relations[0].kind"]


def test_new_relation_kind_is_drawn_and_checked_without_changing_the_engine():
    d = draw([el("class", "A", 0, 0), el("class", "B", 300, 0)], [rel("flow", "A", "B")])
    (line,) = [r for r in owned(d, "A->B", Line) if len(r.points) == 2]
    assert line.dash is None and line.points == ((90, 24), (300, 24))
    (head,) = d.drawn[0].heads
    assert isinstance(head, Line) and head.points[1] == (300, 24)
    assert K.check(d).passed
    # 다른 선이 그 화살촉을 지나면 걸린다
    r = report([el("class", "A", 0, 0), el("class", "B", 300, 0), el("class", "C", 250, -200), el("class", "D", 250, 200)],
               [rel("flow", "A", "B"), rel("association", "C", "D", navigable="none")])
    assert kinds(r) == ["line_through_head"] and "화살촉" in r.failures[0].problem


def test_words_take_only_a_noun_without_a_final_consonant():
    # 검사·오류 글의 조사(가·를·와·는)가 받침 없는 말에 맞춰져 있다 — "활동가 …", "활동를 …"이 나가지 않게 만들 때 막는다
    with pytest.raises(ValueError, match="받침 없는 말"):
        B.Words("활동", "테두리", "열쇠")
    assert B.Words("노드", "테두리", "열쇠").noun == "노드"


def test_spec_refuses_a_navigable_relation_with_its_own_end_shape_and_odd_defaults():
    with pytest.raises(ValueError):
        B.RelationType("x", end=B.ARROW_HEAD, navigable=True)
    with pytest.raises(ValueError, match="공유 줄기"):  # 자식 선들이 함께 쓸 끝 모양이 없다
        B.RelationType("x", trunk=True)
    with pytest.raises(ValueError):
        B.Spec(SHAPES, RELATIONS, navigable="both")


# ---------------------------------------------------------------- 시험용 바깥 요소


def room(**more):
    return el("room", "작업", 0, 0, notes=["entry / 준비", "exit / 정리"], **more)


def test_outer_element_from_another_module_holds_elements_and_recomputes_its_corners():
    d = draw([room(), el("oval", "일", 20, 75, **{"in": "작업"})])
    r, o = d.layout.boxes
    zone = Room().zone_height(r.box)
    assert r.zones == (B.NameZone((0, 0, r.rect[2], zone), False),)
    assert r.inner == (0, zone, r.rect[2], r.rect[3])
    assert (r.rect[2], r.rect[3]) == (o.rect[2] + B.NEST_PAD, o.rect[3] + B.NEST_PAD)
    assert r.border == G.PolygonBorder(Room().corners(r.rect))
    assert [p.points for p in owned(d, "작업", Polygon)] == [Room().corners(r.rect)]
    assert K.check(d).passed


def test_element_outside_the_area_of_the_outer_element_fails():
    # 안의 요소를 이름 칸(위 55px) 안에 두거나 칸 테두리에 붙이면 걸린다
    for top, phrase in [(40, "이름 칸에 걸친다"), (60, "5px밖에 떨어지지 않았다")]:
        r = report([room(), el("oval", "일", 20, top, **{"in": "작업"})])
        (f,) = r.failures
        assert f.kind == "inner_off_area" and f.elements == ("일", "작업") and phrase in f.problem
    (f,) = report([room(), el("oval", "일", -30, 80, **{"in": "작업"})]).failures
    assert f.kind == "inner_off_area" and "칸 밖으로 나간다" in f.problem


def test_line_through_the_name_area_of_the_outer_element_fails():
    # 안의 일 → 바깥 X 선이 위로 나가며 이름 칸(위 55px)을 지난다
    elements = [room(), el("oval", "일", 20, 80, **{"in": "작업"}), el("class", "X", 35, -150)]
    r = report(elements, [rel("dependency", "일", "X")])
    assert kinds(r) == ["line_through_name"] and r.failures[0].elements == ("일->X", "작업")
    assert report(elements, [rel("dependency", "일", "X", via=[[200, 110], [200, -126]])]).passed


def test_line_from_above_onto_the_top_edge_of_the_outer_element_passes():
    # 바깥 요소가 끝인 선은 이름 칸 쪽 윗변에 닿아도 된다(그 바깥 요소는 선보다 먼저 그린다)
    elements = [room(), el("oval", "일", 20, 80, **{"in": "작업"}), el("class", "X", 35, -150)]
    r = report(elements, [rel("generalization", "X", "작업")])
    assert r.passed, r.summary()


def test_slanted_line_whose_triangle_goes_into_the_name_area_fails():
    # 넓은 바깥 요소(600×160)의 가운데로 18°쯤 누운 선이 윗변 (52, 0)에 닿아, 삼각형 밑변 한쪽 꼭짓점이 이름 칸으로 3px 들어간다
    elements = [room(width=600), el("oval", "일", 20, 80, **{"in": "작업"}), el("class", "X", -400, -110)]
    r = report(elements, [rel("generalization", "X", "작업", via=[[-165, -70]])])
    (f,) = r.failures
    assert f.kind == "head_under_own_box" and f.elements == ("X->작업", "작업")
    assert "선 끝 모양이 그 요소 안으로 들어간다" in f.problem and "삼각형" in f.problem


def test_line_through_the_inside_of_its_end_outer_element_is_an_input_error():
    elements = [room(), el("oval", "일", 20, 80, **{"in": "작업"}), el("class", "X", 300, 0)]
    with pytest.raises(InputError, match="relations\\[0\\]: 선이 to 요소 '작업'.* 안을 지난다"):
        draw(elements, [rel("dependency", "X", "작업", via=[[-50, 100]])])


# ---------------------------------------------------------------- 테두리 기하


def test_polygon_border_grows_like_a_box_and_shrinks_to_nothing():
    square = G.PolygonBorder([(0, 0), (10, 0), (10, 10), (0, 10)])
    assert square.grown(2).points == ((-2.0, -2.0), (12.0, -2.0), (12.0, 12.0), (-2.0, 12.0))
    assert square.grown(-6).empty and not square.grown(-6).hits((5, -5), (5, 15))
    assert square.exit(square.center(), (20, 5)) == (10, 5) and square.exit(square.center(), (8, 5)) is None


def test_polygon_border_meets_and_measures_boxes():
    cut = G.PolygonBorder([(0, 8), (8, 0), (100, 0), (100, 60), (0, 60)])
    assert not cut.meets((0, 0, 3, 3)) and cut.gap((0, 0, 3, 3)) == pytest.approx(math.sqrt(2))
    assert cut.meets((99, 59, 120, 80)) and cut.gap((99, 59, 120, 80)) == -1
    assert cut.clip((-10, 30), (200, 30)) == ((0, 30), (100, 30))


def test_ellipse_border_ends_lines_on_the_ellipse():
    e = G.EllipseBorder(50, 30, 50, 30)
    p = e.exit((50, 30), (100, 60))
    assert ((p[0] - 50) / 50) ** 2 + ((p[1] - 30) / 30) ** 2 == pytest.approx(1)
    assert e.exit((50, 30), (60, 35)) is None and not e.hits((0, 0), (5, 5)) and e.hits((0, 0), (30, 30))
    assert isinstance(e.grown(4), G.PolygonBorder)


def test_ellipse_is_drawn_by_its_shape():
    d = draw([el("oval", "O", 0, 0)])
    (e,) = owned(d, "O", Ellipse)
    assert (e.left, e.top, e.width, e.height) == (0, 0, 120, 60)


# ---------------------------------------------------------------- 선 끝 띄우기·끝 모양 이름·모양 밖 이름 거리


def _socket(c, tip, frm, at, o):
    """시험용 끝 모양: 끝 요소가 향하게 한 점(at)을 가운데로, 선 끝(tip)을 지나는 반원(점 여러 개짜리 열린 선)."""
    r = math.dist(at, tip)
    th = math.atan2(tip[1] - at[1], tip[0] - at[0])
    return c.line([(at[0] + r * math.cos(th + a), at[1] + r * math.sin(th + a))
                   for a in (math.pi / 2 * (k / 4 - 1) for k in range(9))], owner=o)


SOCKET = B.EndShape("반원", 0, _socket, gap=6)
USES = B.RelationType("소켓", end=SOCKET)
SOCKET_SPEC = B.Spec(SHAPES, {**RELATIONS, "uses": USES})


def socket_drawing(*more_elements, relations=(), via=None):
    # 원(지름 24, 가운데 12, 12)의 이름은 오른쪽, A(가운데 y 12)는 왼쪽에서 가로로 들어온다
    uses = rel("uses", "A", "Api", **({"via": via} if via else {}))
    return draw([dot("Api", 0, 0, name_side="right"), el("class", "A", -200, -12), *more_elements], [uses, *relations],
                spec=SOCKET_SPEC)


def test_end_shape_with_a_gap_ends_the_line_before_the_border_and_passes():
    d = socket_drawing()
    (r,) = d.layout.relations
    assert r.points[-1] == pytest.approx((-6, 12))  # 원 왼쪽(0, 12)에서 6 앞
    (drawn,) = d.drawn
    (arc,) = drawn.heads
    assert isinstance(arc, Line) and len(arc.points) == 9
    assert all(math.dist(p, (12, 12)) == pytest.approx(18) for p in arc.points)  # 원 가운데를 둘러 원에서 6 떨어진다
    assert drawn.marks == (B.HeadMark("반원", r.points[-1]),)
    assert K.check(d).passed, K.check(d).summary()


def test_check_names_an_end_shape_by_its_definition_not_by_its_points():
    # 세로선 B→C(x −6)가 반원 꼭대기를 지나간다 — 점이 아홉 개인 열린 선이지만 "화살촉"이 아니라 제 이름으로 부른다
    r = K.check(socket_drawing(el("class", "B", -51, -150), el("class", "C", -51, 150),
                               relations=[rel("dependency", "B", "C")]))
    assert "line_through_head" in kinds(r)
    (f,) = [f for f in r.failures if f.kind == "line_through_head"]
    assert "반원" in f.problem and "화살촉" not in f.problem


def _hook(c, tip, frm, at, o):
    """시험용 열린 끝 모양: 양 끝은 선 쪽 밖에 있고 가운데 점이 끝 요소 안으로 5px 들어간다."""
    d = math.dist(tip, frm)
    ux, uy = (tip[0] - frm[0]) / d, (tip[1] - frm[1]) / d
    return c.line([(tip[0] - 6 * ux - 5 * uy, tip[1] - 6 * uy + 5 * ux), (tip[0] + 5 * ux, tip[1] + 5 * uy),
                   (tip[0] - 6 * ux + 5 * uy, tip[1] - 6 * uy - 5 * ux)], owner=o)


def test_open_end_shape_whose_middle_point_goes_into_its_element_fails():
    hooked = B.Spec(SHAPES, {**RELATIONS, "hooks": B.RelationType("갈고리", end=B.EndShape("갈고리", 6, _hook))})
    r = report([el("class", "A", 0, 0), el("class", "B", 300, 0)], [rel("hooks", "A", "B")], spec=hooked)
    (f,) = r.failures
    assert f.kind == "head_under_own_box" and "갈고리" in f.problem


@pytest.mark.parametrize("via, problem", [
    ([[-3, 12]], r"to 쪽 끝 구간 길이 3가 끝 모양 길이와 띄운 거리\(6\)보다 길지 않다"),
    # 띄운 거리와 꼭 같아도 — 당긴 선 끝이 앞 점에 겹쳐 길이 0인 선이 되므로 입력 오류다
    ([[-6, 12]], r"to 쪽 끝 구간 길이 6가 끝 모양 길이와 띄운 거리\(6\)보다 길지 않다"),
])
def test_end_segment_not_longer_than_the_gap_is_an_input_error(via, problem):
    with pytest.raises(InputError, match=problem):
        socket_drawing(via=via)


def test_only_the_end_with_a_gap_speaks_of_the_gap():
    # from 쪽은 마름모(길이 18, 띄우지 않음), to 쪽은 소켓(띄움 6). 첫 구간 10이 모자란 from 쪽 글에는 띄운 거리가 없다
    both = B.Spec(SHAPES, {**RELATIONS, "has": B.RelationType("소켓 집합", start=B.OPEN_DIAMOND, end=SOCKET)})
    with pytest.raises(InputError) as e:
        draw([dot("Api", 0, 0, name_side="right"), el("class", "A", -200, -12)],
             [rel("has", "A", "Api", via=[[-100, 12], [-50, 12]])], spec=both)
    assert e.value.problems == ("relations[0]: from 쪽 끝 구간 길이 10가 끝 모양 길이(18)보다 짧다 — 첫 꺾는 점을 요소에서 더 "
                                "떼어 놓는다",)


def test_a_straight_line_exactly_as_long_as_the_gap_is_an_input_error_not_a_crash():
    with pytest.raises(InputError, match=r"선 길이 6가 양 끝 모양 길이와 띄운 거리\(0\+6\)보다 길지 않다"):
        draw([dot("Api", 0, 0, name_side="right"), el("class", "A", -96, -12)], [rel("uses", "A", "Api")], spec=SOCKET_SPEC)


def test_shape_sets_the_gap_between_itself_and_its_outside_name():
    class FarDot(Dot):
        name_gap = 12

    spec = B.Spec({"dot": Dot(), "far": FarDot()}, {"flow": FLOW})
    near, far = (draw([el(k, "Api", 0, 0)], spec=spec).layout.boxes[0] for k in ("dot", "far"))
    assert far.height == near.height + 12 - B.NAME_SEP
    assert far.zones[0].rect[1] == 24 + 12 and near.zones[0].rect[1] == 24 + B.NAME_SEP
