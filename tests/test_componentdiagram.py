"""컴포넌트도: 제공 인터페이스 원과 그 막대·쓰는 쪽 화살표, 아티팩트의 «manifest», 클래스 실현 그림, 연관 기본 방향."""
import math

import pytest

from cysuml import boxcheck as K
from cysuml import componentdiagram as C
from cysuml import geom as G
from cysuml import server
from cysuml.boxdiagram import LABEL_LINE, NAME_SEP, NameZone
from cysuml.canvas import Ellipse, Line, Polygon, Text
from cysuml.parsing import InputError


def el(kind, name, left, top, **more):
    return {"kind": kind, "name": name, "left": left, "top": top, **more}


def inside(parent, kind, name, left, top, **more):
    return el(kind, name, left, top, **{"in": parent}, **more)


def rel(kind, source, target, **more):
    return {"kind": kind, "from": source, "to": target, **more}


def draw(elements, relations=()):
    return C.render({"elements": list(elements), "relations": list(relations)})


def report(elements, relations=()):
    return K.check(draw(elements, relations))


def kinds(r):
    return [f.kind for f in r.failures]


def owned(drawing, owner, typ=object):
    return [r for r in drawing.canvas.records if r.owner == owner and isinstance(r, typ)]


def placed(drawing, key):
    (p,) = [p for p in drawing.layout.boxes if p.key == key]
    return p


def drawn(drawing, owner):
    (d,) = [d for r, d in zip(drawing.layout.relations, drawing.drawn) if r.owner == owner]
    return d


def on_circle(p, rect, eps=1e-6):
    l, t, r, b = rect
    return abs(math.dist(p, ((l + r) / 2, (t + b) / 2)) - (r - l) / 2) < eps


# ---------------------------------------------------------------- 이슈의 확인 그림


SERVICES = [el("package", "web", 0, 0), inside("web", "component", "OrderController", 20, 44),
            inside("web", "component", "AdminController", 220, 44), el("package", "service", 0, 220),
            inside("service", "component", "OrderService", 110, 324),
            inside("service", "lollipop", "OrderApi", 70, 264, name_side="left"),
            el("artifact", "order-service.jar", 400, 324)]
USES = [rel("association", "OrderService", "OrderApi"), rel("dependency", "OrderController", "OrderApi"),
        rel("dependency", "AdminController", "OrderApi"),
        rel("dependency", "order-service.jar", "OrderService", stereotype="manifest")]


def test_two_packages_of_components_an_interface_its_users_and_an_artifact_pass():
    d = draw(SERVICES, USES)
    assert K.check(d).passed, K.check(d).summary()
    api = placed(d, "OrderApi")
    for owner in ("OrderService->OrderApi", "OrderController->OrderApi", "AdminController->OrderApi"):
        (r,) = [r for r in d.layout.relations if r.owner == owner]
        assert on_circle(r.points[-1], api.shape_rect)
    # 막대는 화살촉 없는 실선, 쓰는 쪽은 점선 의존 화살표
    bar, use = drawn(d, "OrderService->OrderApi"), drawn(d, "OrderController->OrderApi")
    assert bar.line.dash is None and bar.heads == ()
    assert use.line.dash is not None and [type(h) for h in use.heads] == [Line]


def test_one_interface_used_by_three_components_passes():
    elements = [el("component", "Provider", 0, 108), el("lollipop", "Api", 186, 120, name_side="bottom"),
                el("component", "Left", 0, -100), el("component", "Middle", 160, -150), el("component", "Right", 320, -100)]
    relations = [rel("association", "Provider", "Api"), *(rel("dependency", u, "Api") for u in ("Left", "Middle", "Right"))]
    d = draw(elements, relations)
    assert K.check(d).passed, K.check(d).summary()
    ends = [r.points[-1] for r in d.layout.relations[1:]]
    assert len(set(ends)) == 3  # 세 화살표가 원 둘레의 서로 다른 점에 닿는다


def test_component_in_nested_packages_and_a_manifest_from_an_artifact_pass():
    d = draw([el("package", "app", 0, 0), inside("app", "package", "order", 20, 44),
              inside("order", "component", "OrderService", 40, 88), el("artifact", "order.jar", 360, 88)],
             [rel("dependency", "order.jar", "OrderService", stereotype="manifest")])
    assert K.check(d).passed, K.check(d).summary()
    manifest = drawn(d, "order.jar->OrderService")
    assert manifest.line.dash is not None and [[t.text for t in label] for label in manifest.labels] == [["«manifest»"]]


def test_class_realization_of_a_component_passes():
    r = report([el("component", "OrderService", 150, 0, stereotype="component"), el("package", "order.impl", 0, 150),
                inside("order.impl", "class", "OrderServiceImpl", 20, 194),
                inside("order.impl", "class", "OrderRepository", 240, 194), inside("order.impl", "class", "Order", 240, 330)],
               [rel("realization", "OrderServiceImpl", "OrderService"), rel("dependency", "OrderService", "OrderRepository"),
                rel("association", "OrderServiceImpl", "OrderRepository", navigable="to"),
                rel("association", "OrderRepository", "Order", name="stores", to_multiplicity="*")])
    assert r.passed, r.summary()


def test_class_shaped_interface_and_realization_still_work():
    r = report([el("component", "Billing", 0, 0), el("interface", "Payment", 0, 150, operations=["+pay(): void"]),
                el("class", "CardPayment", 250, 150)],
               [rel("realization", "CardPayment", "Payment"), rel("dependency", "Billing", "Payment", stereotype="use")])
    assert r.passed, r.summary()


# ---------------------------------------------------------------- 원과 이름에 걸리는 것


def test_line_through_an_interface_circle_fails():
    r = report([el("lollipop", "Api", 140, 0), el("class", "A", 0, -14), el("class", "B", 300, -14)],
               [rel("association", "A", "B")])
    assert kinds(r) == ["line_through_box"] and r.failures[0].elements == ("A->B", "Api")


def test_line_through_the_name_of_an_interface_fails():
    # 상관없는 선이 이름을 지나면 그 요소를 지나간 것, 원으로 오는 선이 제 이름을 지나면 이름 칸을 지난 것
    other = report([el("lollipop", "Api", 140, 0), el("class", "A", 0, 10), el("class", "B", 300, 10)],
                   [rel("association", "A", "B")])
    assert kinds(other) == ["line_through_box"] and other.failures[0].elements == ("A->B", "Api")
    own = report([el("lollipop", "Api", 0, 0), el("component", "C", -40, 150)], [rel("association", "C", "Api")])
    assert kinds(own) == ["line_through_name"] and own.failures[0].elements == ("C->Api", "Api")


def test_element_or_label_on_the_name_of_an_interface_fails():
    assert kinds(report([el("lollipop", "Api", 0, 0), el("class", "A", 0, 34)])) == ["box_overlap"]
    # 관계 이름 자리 둘(선 가운데 위아래) 가운데 아래는 상자 C가 막고, 위에는 Api 이름이 있다
    r = report([el("lollipop", "Api", 172, -28), el("class", "A", 0, 0), el("class", "B", 300, 0),
                el("class", "C", 150, 29)], [rel("association", "A", "B", name="has")])
    (f,) = r.failures
    assert f.kind == "text_on_box" and f.elements == ("A->B", "Api")


@pytest.mark.parametrize("gap, passed", [(20, False), (30, False), (40, True), (90, True)])
def test_arrows_into_one_circle_need_room_between_them(gap, passed):
    # 배치 요령의 "들어오는 방향이 40°쯤 넘게 벌어지게". 쓰는 쪽은 서로 겹치지 않게 멀리 둔다
    d = draw([el("lollipop", "Api", 0, 0)])
    api = placed(d, "Api")
    cx, cy = (api.shape_rect[0] + api.shape_rect[2]) / 2, (api.shape_rect[1] + api.shape_rect[3]) / 2
    users = []
    for i, a in enumerate((90 - gap / 2, 90 + gap / 2)):
        x, y = cx + 400 * math.cos(math.radians(a)), cy - 400 * math.sin(math.radians(a))
        users.append(el("component", f"U{i}", x - 45, y - 24))
    r = report([el("lollipop", "Api", 0, 0), *users], [rel("dependency", u["name"], "Api") for u in users])
    assert r.passed == passed, r.summary()
    assert passed or kinds(r) == ["head_overlap"]


@pytest.mark.parametrize("gap, passed", [(10, False), (40, True)])
def test_arrow_into_a_circle_needs_room_from_the_bar(gap, passed):
    # 막대는 원 아래(270°)에서, 쓰는 쪽은 그보다 gap만큼 돈 쪽에서 온다. 이름은 왼쪽. 두 컴포넌트가 겹치지 않게 멀리 둔다
    d = draw([el("lollipop", "Api", 0, 0, name_side="left")])
    api = placed(d, "Api")
    cx, cy = (api.shape_rect[0] + api.shape_rect[2]) / 2, (api.shape_rect[1] + api.shape_rect[3]) / 2
    ends = []
    for name, a in (("P", 270), ("U", 270 + gap)):
        x, y = cx + 700 * math.cos(math.radians(a)), cy - 700 * math.sin(math.radians(a))
        ends.append(el("component", name, x - 45, y - 24))
    r = report([el("lollipop", "Api", 0, 0, name_side="left"), *ends],
               [rel("association", "P", "Api"), rel("dependency", "U", "Api")])
    assert r.passed == passed, r.summary()
    assert passed or kinds(r) == ["line_through_head"]


# ---------------------------------------------------------------- 제공 인터페이스 원 모양·자리


def test_lollipop_is_a_small_circle_with_its_name_below():
    d = draw([el("lollipop", "OrderApi", 0, 0)])
    p = placed(d, "OrderApi")
    (circle,) = owned(d, "OrderApi", Ellipse)
    (name,) = owned(d, "OrderApi", Text)
    assert (circle.width, circle.height) == (C.BALL, C.BALL)
    assert (circle.left, circle.top, circle.left + C.BALL, circle.top + C.BALL) == p.shape_rect
    assert p.rect[1] == p.shape_rect[1] and p.rect[3] == C.BALL + NAME_SEP + LABEL_LINE
    assert name.text == "OrderApi" and name.x == (p.rect[0] + p.rect[2]) / 2 > circle.left
    assert p.zones == (NameZone((0, C.BALL + NAME_SEP, p.rect[2], p.rect[3]), True),)
    assert p.border == G.EllipseBorder(*(p.shape_rect[0] + C.BALL / 2, C.BALL / 2), C.BALL / 2, C.BALL / 2)
    assert not owned(d, "OrderApi", Polygon)


def test_place_of_a_lollipop_lists_its_circle_too():
    d = draw([el("lollipop", "Api", 0, 0), el("component", "C", 0, 120)])
    (line,) = server._places(d)
    p = placed(d, "Api")
    assert f"Api(0, 0, {p.width:g}×{p.height:g}, 모양 " in line and "C(0, 120, " in line


@pytest.mark.parametrize("side, user", [("bottom", (-40, -150)), ("top", (-40, 150)), ("left", (200, -12)),
                                        ("right", (-200, -12))])
def test_name_side_passes_and_the_returned_place_draws_the_same(side, user):
    elements = [el("lollipop", "Payment", 0, 0, name_side=side), el("component", "Shop", *user)]
    relations = [rel("dependency", "Shop", "Payment")]
    d = draw(elements, relations)
    assert K.check(d).passed, K.check(d).summary()
    p = placed(d, "Payment")
    again = [el("lollipop", "Payment", p.rect[0], p.rect[1], name_side=side), elements[1]]
    assert [repr(r) for r in draw(again, relations).canvas.records] == [repr(r) for r in d.canvas.records]


def test_two_line_lollipop_name_takes_an_id():
    d = draw([el("lollipop", ["Order", "Api"], 0, 0, id="api"), el("component", "C", -200, -12)],
             [rel("association", "C", "api")])
    assert [t.text for t in owned(d, "api", Text)] == ["Order", "Api"]
    assert placed(d, "api").height == C.BALL + NAME_SEP + 2 * LABEL_LINE
    assert K.check(d).passed, K.check(d).summary()


def test_lollipop_in_a_package_grows_the_package_over_its_name():
    d = draw([el("package", "p", 0, 0), inside("p", "component", "C", 20, 44), inside("p", "lollipop", "Api", 180, 58)],
             [rel("association", "C", "Api")])
    p, api = placed(d, "p"), placed(d, "Api")
    assert p.rect[2] == api.rect[2] + 20 and p.rect[3] >= api.rect[3] + 20
    assert K.check(d).passed, K.check(d).summary()


# ---------------------------------------------------------------- 도구 정의


def test_associations_have_no_arrowhead_unless_given_a_direction():
    d = draw([el("component", "A", 0, 0), el("component", "B", 300, 0), el("class", "X", 0, 150), el("class", "Y", 300, 150)],
             [rel("association", "A", "B"), rel("association", "X", "Y", navigable="to")])
    assert [r.relation.navigable for r in d.layout.relations] == ["none", "to"]
    assert drawn(d, "A->B").heads == () and len(drawn(d, "X->Y").heads) == 1


def test_lollipop_input_errors():
    with pytest.raises(InputError) as e:
        draw([el("lollipop", "Api", 0, 0, stereotype="interface", width=40)])
    assert [p.split(":")[0] for p in e.value.problems] == ["elements[0].stereotype", "elements[0].width"]
    with pytest.raises(InputError, match=r"elements\[1\]\.in: elements\[0\]\('lollipop'\)는 안에 요소를 둘 수 없다"):
        draw([el("lollipop", "Api", 0, 0), inside("Api", "component", "C", 0, 100)])
    with pytest.raises(InputError, match=r"elements\[0\]: 'id' 필드가 빠졌다"):
        draw([el("lollipop", ["Order", "Api"], 0, 0)])
    with pytest.raises(InputError, match="'node' · 'lollipop' 가운데 하나여야 한다"):
        draw([el("ball", "Api", 0, 0)])
    with pytest.raises(InputError, match=r"elements\[0\]\.name_side: 모르는 필드다"):
        draw([el("component", "C", 0, 0, name_side="top")])
