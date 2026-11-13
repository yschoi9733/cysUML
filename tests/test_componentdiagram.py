"""컴포넌트도: 제공 인터페이스 원과 그 막대·쓰는 쪽 화살표·소켓, 아티팩트의 «manifest», 아이콘 표기 그림, 클래스 실현 그림, 연관
기본 방향."""
import math

import pytest

from cysuml import boxcheck as K
from cysuml import componentdiagram as C
from cysuml import geom as G
from cysuml import server
from cysuml.boxdiagram import LABEL_LINE, HeadMark, NameZone
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
    # 이름 "OrderApi"는 폭이 홀수(53)라 모양 자리가 반 픽셀(16.5)에 놓인다. 원은 그 가운데를 정수로 내린 점에 그린다
    d = draw([el("lollipop", "OrderApi", 0, 0)])
    p = placed(d, "OrderApi")
    (circle,) = owned(d, "OrderApi", Ellipse)
    (name,) = owned(d, "OrderApi", Text)
    assert p.shape_rect == (16.5, 0, 36.5, C.BALL)
    assert (circle.left, circle.top, circle.width, circle.height) == (16, 0, C.BALL, C.BALL)
    assert p.anchor == (26, 10) and p.border == G.EllipseBorder(26, 10, C.BALL / 2, C.BALL / 2)
    assert p.rect[1] == p.shape_rect[1] and p.rect[3] == C.BALL + C.BALL_NAME_GAP + LABEL_LINE
    assert name.text == "OrderApi" and name.x == (p.rect[0] + p.rect[2]) / 2 > circle.left
    assert p.zones == (NameZone((0, C.BALL + C.BALL_NAME_GAP, p.rect[2], p.rect[3]), True),)
    assert not owned(d, "OrderApi", Polygon)


@pytest.mark.parametrize("name", ["OrderApi", "Api", "PaymentGatewayApi"])
def test_bar_under_a_component_stands_straight_with_whole_number_places(name):
    # 기본 폭 90 컴포넌트(가운데 x 45) 아래에 정수 left로 둔다. 원 가운데는 모양 자리 가운데를 내린 점이라, 이름 폭이 홀수면
    # 45 - 폭/2(x.5)를 올린 left에서 가운데가 45가 되어 막대가 곧다(내리기 전에는 어느 정수 left로도 곧게 세울 수 없었다)
    d = draw([el("lollipop", name, 0, 0)])
    w = placed(d, name).width
    d = draw([el("component", "Order", 0, 0), el("lollipop", name, math.ceil(45 - w / 2), 120)],
             [rel("association", "Order", name)])
    (bar,) = d.layout.relations
    assert bar.points[0][0] == bar.points[-1][0] == 45
    assert K.check(d).passed, K.check(d).summary()


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
    assert placed(d, "api").height == C.BALL + C.BALL_NAME_GAP + 2 * LABEL_LINE
    assert K.check(d).passed, K.check(d).summary()


def test_lollipop_in_a_package_grows_the_package_over_its_name():
    d = draw([el("package", "p", 0, 0), inside("p", "component", "C", 20, 44), inside("p", "lollipop", "Api", 180, 58)],
             [rel("association", "C", "Api")])
    p, api = placed(d, "p"), placed(d, "Api")
    assert p.rect[2] == api.rect[2] + 20 and p.rect[3] >= api.rect[3] + 20
    assert K.check(d).passed, K.check(d).summary()


# ---------------------------------------------------------------- 소켓


def ball_center(name_side="bottom", name="Api"):
    """원을 (0, 0)에 둘 때 원 가운데(선이 향하는 점)."""
    return placed(draw([el("lollipop", name, 0, 0, name_side=name_side)]), name).anchor


def around(name, deg, center, dist, kind="component", **more):
    """원 가운데에서 deg(수학 각도 — 위가 +)쪽으로 dist 떨어진 곳에 가운데를 둔 기본 크기 컴포넌트(90×48)."""
    x, y = center[0] + dist * math.cos(math.radians(deg)), center[1] - dist * math.sin(math.radians(deg))
    return el(kind, name, x - 45, y - 24, **more)


def socket_and(other, deg, name_side="bottom"):
    """소켓은 왼쪽(180°)에서, other 관계의 쓰는 쪽·제공하는 쪽은 deg에서 원으로 온다."""
    c = ball_center(name_side)
    return report([el("lollipop", "Api", 0, 0, name_side=name_side), around("U", 180, c, 500), around("P", deg, c, 500)],
                  [rel("requires", "U", "Api"), rel(other, "P", "Api")])


def test_socket_is_a_half_circle_around_the_ball_and_its_line_stops_short_of_the_ball():
    c = ball_center()
    d = draw([el("lollipop", "Api", 0, 0), around("U", 180, c, 300)], [rel("requires", "U", "Api")])
    assert K.check(d).passed, K.check(d).summary()
    (r,) = d.layout.relations
    assert r.points[-1] == pytest.approx((c[0] - C.SOCKET, c[1]))  # 원 둘레(반지름 10)에서 5 앞
    socket = drawn(d, "U->Api")
    assert socket.line.dash is None
    (arc,) = socket.heads
    assert isinstance(arc, Line) and socket.marks == (HeadMark("소켓 반원", r.points[-1]),)
    assert all(math.dist(p, c) == pytest.approx(C.SOCKET) for p in arc.points)
    # 쓰는 쪽(왼쪽) 절반만 감싼다 — 양 끝은 원 바로 위·아래, 가운데는 선 끝
    ends = sorted((arc.points[0], arc.points[-1]), key=lambda p: p[1])
    assert ends == [pytest.approx((c[0], c[1] - C.SOCKET)), pytest.approx((c[0], c[1] + C.SOCKET))]
    assert all(p[0] <= c[0] + 1e-9 for p in arc.points) and r.points[-1] in arc.points


def test_socket_with_bends_keeps_its_half_circle_on_the_ball_center():
    c = ball_center()
    d = draw([el("lollipop", "Api", 0, 0), el("component", "U", -300, -200)],
             [rel("requires", "U", "Api", via=[[c[0] - 80, -176], [c[0] - 80, c[1] - 80]])])
    assert K.check(d).passed, K.check(d).summary()
    (arc,) = drawn(d, "U->Api").heads
    assert all(math.dist(p, c) == pytest.approx(C.SOCKET) for p in arc.points)
    (r,) = d.layout.relations
    assert math.dist(r.points[-1], c) == pytest.approx(C.SOCKET)  # 마지막 구간도 원 가운데를 향한다


@pytest.mark.parametrize("dx, ok", [(16, False), (20, False), (21, True)])
def test_bend_next_to_a_socket_must_clear_its_half_circle(dx, ok):
    # 원 왼쪽 dx에 꺾는 점을 두고 위에서 곧게 내려와 꺾어 들어온다. 원 쪽 끝 구간(dx − 10)이 띄운 거리 5와 소켓 반원 길이 5를
    # 더한 10보다 길어야 한다 — 16이면 세로 구간이 반원 꼭대기(dx 15) 1px 옆을 지나 반원과 한데 붙어 보인다
    c = ball_center(name_side="right")
    data = ([el("lollipop", "Api", 0, 0, name_side="right"), el("component", "U", c[0] - dx - 45, c[1] - 250)],
            [rel("requires", "U", "Api", via=[[c[0] - dx, c[1]]])])
    if ok:
        assert report(*data).passed
    else:
        with pytest.raises(InputError, match=r"to 쪽 끝 구간 길이 .*끝 모양 길이와 띄운 거리를 더한 길이\(10\)보다 길지 않다"):
            draw(*data)


@pytest.mark.parametrize("side", ["bottom", "top"])
def test_bar_ball_and_socket_in_a_straight_line_pass_with_the_name_beside(side):
    assert socket_and("association", 0, name_side=side).passed


@pytest.mark.parametrize("gap, passed", [(C.BALL_NAME_GAP - 1, False), (C.BALL_NAME_GAP, True)])
def test_ball_name_sits_far_enough_that_a_socket_misses_it(monkeypatch, gap, passed):
    # 이름 칸을 원에서 BALL_NAME_GAP보다 1px만 덜 떼도 소켓 반원 아래 끝이 이름 칸 검사 여유에 걸린다(실측)
    monkeypatch.setattr(C.LOLLIPOP, "name_gap", gap)
    r = socket_and("association", 0)
    assert r.passed == passed and (passed or kinds(r) == ["line_through_name"]), r.summary()


@pytest.mark.parametrize("other, turn, passed", [("association", 95, False), ("association", 100, True),
                                                 ("dependency", 105, False), ("dependency", 110, True)])
def test_bar_and_arrow_need_room_from_the_socket(other, turn, passed):
    # 배치 요령의 "막대는 100°, 화살표는 110° 넘게"(실측 경계는 98°·108°). 막대는 반원 끝에 닿고, 화살표는 화살촉이 반원에 겹친다
    r = socket_and(other, 180 - turn)
    assert r.passed == passed, r.summary()
    assert passed or kinds(r) == ["line_through_head" if other == "association" else "head_overlap"]


def test_one_ball_used_by_a_socket_and_a_dependency_arrow_passes():
    c = ball_center()
    r = report([el("lollipop", "Api", 0, 0), around("U", 180, c, 300), around("P", 0, c, 300), around("V", 60, c, 300)],
               [rel("requires", "U", "Api"), rel("association", "P", "Api"), rel("dependency", "V", "Api")])
    assert r.passed, r.summary()


def test_two_sockets_on_one_ball_overlap():
    c = ball_center()
    r = report([el("lollipop", "Api", 0, 0), around("U", 180, c, 300), around("V", 120, c, 300)],
               [rel("requires", "U", "Api"), rel("requires", "V", "Api")])
    assert "head_overlap" in kinds(r)
    (f,) = [f for f in r.failures if f.kind == "head_overlap"]
    assert f.problem.count("소켓 반원") == 2


def test_line_through_a_socket_half_circle_fails_and_is_not_called_an_arrowhead():
    # 세로선 A→B가 소켓 반원 왼쪽 끝 바로 옆(원 가운데에서 왼쪽 SOCKET)을 지난다
    c = ball_center(name_side="right")
    x = c[0] - C.SOCKET
    r = report([el("lollipop", "Api", 0, 0, name_side="right"), around("U", 180, c, 300),
                el("class", "A", x - 45, c[1] - 200), el("class", "B", x - 45, c[1] + 150)],
               [rel("requires", "U", "Api"), rel("dependency", "A", "B")])
    assert "line_through_head" in kinds(r)
    (f,) = [f for f in r.failures if f.kind == "line_through_head"]
    assert "소켓 반원" in f.problem and "화살촉" not in f.problem


def test_socket_input_errors():
    c = ball_center()
    users = [el("lollipop", "Api", 0, 0), around("U", 180, c, 300), el("lollipop", "Other", 300, 300)]
    with pytest.raises(InputError) as e:
        draw(users, [rel("requires", "U", "U2")])
    assert e.value.problems[0].startswith("relations[0].to: ")  # 없는 요소는 엔진이 먼저 알린다
    with pytest.raises(InputError) as e:
        draw([*users, around("V", 0, c, 300)], [rel("requires", "Api", "V"), rel("requires", "U", "V"),
                                                rel("requires", "Other", "Api")])
    assert e.value.problems == (
        "relations[0].from: 소켓(requires)의 from은 인터페이스를 쓰는 쪽이다 — from 요소 'Api'의 종류가 'lollipop'이다",
        "relations[0].to: 소켓(requires)은 제공 인터페이스 원(kind \"lollipop\")으로 긋는다 — to 요소 'V'의 종류가 'component'다",
        "relations[1].to: 소켓(requires)은 제공 인터페이스 원(kind \"lollipop\")으로 긋는다 — to 요소 'V'의 종류가 'component'다",
        "relations[2].from: 소켓(requires)의 from은 인터페이스를 쓰는 쪽이다 — from 요소 'Other'의 종류가 'lollipop'이다")
    with pytest.raises(InputError) as e:
        draw(users, [rel("requires", "U", "Api", to_multiplicity="1", navigable="to")])
    assert [p.split(":")[0] for p in e.value.problems] == ["relations[0].to_multiplicity", "relations[0].navigable"]


# ---------------------------------------------------------------- 아이콘 표기와 소켓을 함께 쓴 그림


def chain(name_side="bottom"):
    """아이콘 표기 컴포넌트 다섯을 가로로 늘어놓고, 이웃 사이마다 원을 둔다 — 왼쪽 컴포넌트가 막대로 제공하고 오른쪽 컴포넌트가
    부품 네모 사이로 소켓을 긋는다. 컴포넌트마다 위에 문서 아이콘 아티팩트가 «manifest»로 내려온다."""
    off = ball_center(name_side, "Api1")
    elements, relations = [], []
    for i in range(5):
        left = 260 * i
        elements += [el("component_icon", f"Comp{i + 1}", left, 200),
                     el("artifact_icon", f"comp{i + 1}.jar", left + 38, 80, name_side="right")]
        relations.append(rel("dependency", f"comp{i + 1}.jar", f"Comp{i + 1}", stereotype="manifest"))
    for i in range(4):
        cx = 260 * i + 179  # 왼쪽 컴포넌트 오른쪽 변(98)과 오른쪽 컴포넌트 부품 네모(260) 사이
        elements.append(el("lollipop", f"Api{i + 1}", cx - off[0], 224 - off[1], name_side=name_side))
        relations += [rel("association", f"Comp{i + 1}", f"Api{i + 1}"), rel("requires", f"Comp{i + 2}", f"Api{i + 1}")]
    return elements, relations


def test_icon_components_balls_sockets_and_page_artifacts_pass():
    elements, relations = chain()
    kinds_ = [e["kind"] for e in elements]
    assert (kinds_.count("component_icon"), kinds_.count("lollipop"), kinds_.count("artifact_icon")) == (5, 4, 5)
    d = draw(elements, relations)
    assert K.check(d).passed, K.check(d).summary()
    for r in d.layout.relations:  # 막대·소켓·«manifest»가 모두 곧다
        assert r.points[0][0] == r.points[-1][0] or r.points[0][1] == r.points[-1][1], r.owner


# ---------------------------------------------------------------- 도구 정의


def test_tool_description_tells_how_to_draw_sockets():
    assert C.SOCKET_INPUT in C.TOOL and C.TIPS in C.TOOL
    assert '"requires"' in C.TOOL and "소켓 반원" in C.TOOL
    assert "막대는 100°, 화살표는 110° 넘게" in C.TIPS and "한 원에 하나" in C.TIPS
    assert f"이름은 원에서 {C.BALL_NAME_GAP:g}px 떨어진다" in C.TOOL


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
