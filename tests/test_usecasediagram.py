"""유즈케이스도: 액터(교류도와 같은 사람 모양, 모양 밖 이름)·유즈케이스(타원)·시스템 경계(이름 칸이 위쪽에 있는 바깥 요소)와
연관·의존(«include»·«extend»)·일반화."""
import math

import pytest

from cysuml import boxcheck as K
from cysuml import boxdiagram as B
from cysuml import server
from cysuml import text as T
from cysuml import usecasediagram as U
from cysuml.canvas import Canvas, Ellipse, Line, Polygon, Rect, Text
from cysuml.parsing import InputError
from cysuml.sequencediagram import ACTOR_FIGURE, draw_actor


def el(kind, name, left, top, **more):
    return {"kind": kind, "name": name, "left": left, "top": top, **more}


def inside(parent, kind, name, left, top, **more):
    return el(kind, name, left, top, **{"in": parent}, **more)


def rel(kind, source, target, **more):
    return {"kind": kind, "from": source, "to": target, **more}


def draw(elements, relations=()):
    return U.render({"elements": list(elements), "relations": list(relations)})


def report(elements, relations=()):
    return K.check(draw(elements, relations))


def kinds(r):
    return [f.kind for f in r.failures]


def owned(drawing, owner, typ=object):
    return [r for r in drawing.canvas.records if r.owner == owner and isinstance(r, typ)]


def placed(drawing, key):
    (p,) = [p for p in drawing.layout.boxes if p.key == key]
    return p


def on_ellipse(p, rect, eps=1e-6):
    l, t, r, b = rect
    return abs(((p[0] - (l + r) / 2) / ((r - l) / 2)) ** 2 + ((p[1] - (t + b) / 2) / ((b - t) / 2)) ** 2 - 1) < eps


def errors(elements, relations=()):
    with pytest.raises(InputError) as e:
        U.parse({"elements": list(elements), "relations": list(relations)})
    return e.value.problems


# ---------------------------------------------------------------- 한 그림


SHOP = [
    el("system", "주문 시스템", 200, 0, id="sys"),
    inside("sys", "use_case", "상품을 검색한다", 240, 60),
    inside("sys", "use_case", "주문한다", 240, 160),
    inside("sys", "use_case", "결제한다", 480, 160),
    inside("sys", "use_case", ["주문 내역을", "조회한다"], 240, 260, id="history"),
    inside("sys", "use_case", "쿠폰을 쓴다", 480, 280),
    el("actor", "고객", 40, 150, name_side="left"),
    el("actor", "회원", 40, 290, name_side="left"),
]
SHOP_RELATIONS = [
    rel("association", "고객", "상품을 검색한다"),
    rel("association", "고객", "주문한다"),
    rel("association", "회원", "history"),
    rel("generalization", "회원", "고객"),
    rel("dependency", "주문한다", "결제한다", stereotype="include"),
    rel("dependency", "쿠폰을 쓴다", "결제한다", stereotype="extend"),
]


def test_actors_use_cases_in_a_system_include_extend_and_generalization_pass():
    d = draw(SHOP, SHOP_RELATIONS)
    r = K.check(d)
    assert r.passed, r.summary()
    sys_, history = placed(d, "sys"), placed(d, "history")
    assert [t.text for t in owned(d, "history", Text)] == ["주문 내역을", "조회한다"]
    for p in d.layout.boxes:  # 유즈케이스는 모두 시스템 경계 안, 액터는 모두 밖(왼쪽)
        if p.box.kind == "use_case":
            assert p.box.parent == "sys" and sys_.inner[0] < p.rect[0] and p.rect[2] < sys_.inner[2]
        elif p.box.kind == "actor":
            assert p.box.parent is None and p.rect[2] < sys_.rect[0]
    assert history.height > placed(d, "주문한다").height
    labels = {p.owner: [lab.lines for lab in p.labels] for p in d.layout.relations}
    assert labels["주문한다->결제한다"] == [("«include»",)] and labels["쿠폰을 쓴다->결제한다"] == [("«extend»",)]


def test_include_and_extend_are_dashed_arrows_and_generalization_is_a_hollow_triangle():
    d = draw(SHOP, SHOP_RELATIONS)
    drawn = dict(zip((p.owner for p in d.layout.relations), d.drawn))
    for owner in ("주문한다->결제한다", "쿠폰을 쓴다->결제한다"):
        assert drawn[owner].line.dash == B.DASH and [type(h) for h in drawn[owner].heads] == [Line]
    triangle = drawn["회원->고객"]
    assert triangle.line.dash is None and [(type(h), h.fill) for h in triangle.heads] == [(Polygon, "white")]


def test_association_has_no_arrowhead_unless_navigable_is_given():
    elements = [el("actor", "고객", 0, 0, name_side="left"), el("use_case", "주문한다", 200, -7)]
    plain, arrow = (draw(elements, [rel("association", "고객", "주문한다", **more)]) for more in ({}, {"navigable": "to"}))
    assert plain.layout.relations[0].relation.navigable == "none" and plain.drawn[0].heads == ()
    assert len(arrow.drawn[0].heads) == 1


def test_use_case_generalization_shares_a_trunk():
    # 부모 유즈케이스 아래 두 자식이 한 줄기로 모여 삼각형 하나를 함께 쓴다
    r = report([el("use_case", "결제한다", 150, 0), el("use_case", "카드로 결제한다", 0, 160),
                el("use_case", "계좌로 결제한다", 300, 160)],
               [rel("generalization", "카드로 결제한다", "결제한다", via=[[70, 110], [210, 110]]),
                rel("generalization", "계좌로 결제한다", "결제한다", via=[[370, 110], [210, 110]])])
    assert r.passed, r.summary()


# ---------------------------------------------------------------- 시스템 경계


def test_line_through_the_system_name_fails_but_beside_it_passes():
    system = [el("system", "주문 시스템", 0, 0, id="sys", width=400), inside("sys", "use_case", "주문한다", 140, 80)]
    zone = placed(draw(system), "sys").zones[0].rect
    # 시스템 위의 액터(이름은 위)에서 곧게 내려오는 선이 위쪽 가운데의 이름 칸을 지나간다
    r = report(system + [el("actor", "고객", 191, -120, name_side="top")], [rel("association", "고객", "주문한다")])
    assert kinds(r) == ["line_through_name"] and r.failures[0].elements == ("고객->주문한다", "sys")
    # 이름 칸 옆으로 윗변을 건너는 선은 합격한다
    left = zone[0] - 30
    r = report(system + [el("actor", "고객", left - 9, -120, name_side="top")],
               [rel("association", "고객", "주문한다", via=[[left, 105]])])
    assert r.passed, r.summary()


def test_system_name_zone_is_as_wide_as_the_name_and_inner_area_is_below_it():
    d = draw([el("system", ["주문", "시스템"], 0, 0, id="sys", width=400)])
    (p,) = d.layout.boxes
    w = math.ceil(max(T.text_width(s, True) for s in ("주문", "시스템"))) + 2 * U.SYSTEM_NAME_SIDE
    h = 2 * B.LABEL_LINE + 2 * U.SYSTEM_NAME_PAD
    assert p.zones == (B.NameZone((200 - w / 2, 0, 200 + w / 2, h), False),)
    assert p.inner == (0, h, 400, p.rect[3])
    assert [(t.text, t.bold) for t in owned(d, "sys", Text)] == [("주문", True), ("시스템", True)]


def test_use_case_on_the_system_name_fails():
    r = report([el("system", "주문 시스템", 0, 0, id="sys"), inside("sys", "use_case", "주문한다", 20, 30)])
    assert kinds(r) == ["inner_off_area"]
    r = report([el("system", "주문 시스템", 0, 0, id="sys"), inside("sys", "use_case", "주문한다", 20, 45)])
    assert r.passed, r.summary()


def test_system_grows_to_hold_its_use_cases():
    d = draw([el("system", "주문 시스템", 0, 0, id="sys"), inside("sys", "use_case", "주문한다", 20, 45),
              inside("sys", "use_case", "결제한다", 300, 200)])
    sys_, pay = placed(d, "sys"), placed(d, "결제한다")
    assert sys_.rect[2:] == (pay.rect[2] + B.NEST_PAD, pay.rect[3] + B.NEST_PAD)


# ---------------------------------------------------------------- 유즈케이스 타원


def test_line_through_another_use_case_fails_and_lines_end_on_the_ellipse():
    elements = [el("use_case", "주문한다", 0, 0), el("use_case", "확인한다", 200, 0), el("use_case", "결제한다", 400, 0)]
    r = report(elements, [rel("dependency", "주문한다", "결제한다")])
    assert kinds(r) == ["line_through_box"] and r.failures[0].elements == ("주문한다->결제한다", "확인한다")
    d = draw(elements, [rel("dependency", "주문한다", "확인한다"), rel("dependency", "결제한다", "확인한다", via=[[460, 90],
                                                                                                    [300, 90]])])
    first, second = (p.points for p in d.layout.relations)
    assert on_ellipse(first[0], placed(d, "주문한다").rect) and on_ellipse(first[-1], placed(d, "확인한다").rect)
    assert on_ellipse(second[0], placed(d, "결제한다").rect) and on_ellipse(second[-1], placed(d, "확인한다").rect)
    assert K.check(d).passed, K.check(d).summary()


def test_line_past_the_empty_corner_of_the_ellipse_passes():
    # 선이 가운데 유즈케이스를 둘러싼 사각형의 왼쪽 위 모서리 쪽(타원 밖)을 비스듬히 지나간다
    elements = [el("use_case", "확인한다", 200, 0), el("actor", "고객", 0, 120, name_side="left"),
                el("use_case", "결제한다", 360, -120)]
    assert report(elements, [rel("association", "고객", "결제한다", via=[[190, 18], [215, -7]])]).passed


def test_use_cases_close_at_the_corners_do_not_overlap_but_their_ellipses_do():
    a = el("use_case", "주문한다", 0, 0)
    assert report([a, el("use_case", "결제한다", 105, 40)]).passed  # 자리 사각형은 모서리가 겹치지만 타원은 떨어졌다
    assert kinds(report([a, el("use_case", "결제한다", 90, 20)])) == ["box_overlap"]


def test_use_case_grows_to_cover_its_name():
    short = placed(draw([el("use_case", "주문", 0, 0)]), "주문")
    assert (short.width, short.height) == U.USE_CASE_MIN
    name = "아주 긴 이름의 유즈케이스를 그린다"
    d = draw([el("use_case", name, 0, 0)])
    p = placed(d, name)
    assert p.width > U.USE_CASE_MIN[0]
    (t,) = owned(d, name, Text)
    box = T.place(t.x, t.y, t.text, False, "mm").box
    a, b = p.width / 2, p.height / 2
    for x, y in ((box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3])):  # 글자 상자 네 모서리가 타원 안
        assert ((x - a) / a) ** 2 + ((y - b) / b) ** 2 < 1
    assert [type(r) for r in owned(d, name)] == [Ellipse, Text]


# ---------------------------------------------------------------- 액터


def test_actor_is_the_sequence_diagram_figure_with_the_name_outside():
    d = draw([el("actor", "고객", 0, 0)])
    (p,) = d.layout.boxes
    assert (p.shape_rect[2] - p.shape_rect[0], p.shape_rect[3] - p.shape_rect[1]) == ACTOR_FIGURE
    c = Canvas()
    draw_actor(c, (p.shape_rect[0] + p.shape_rect[2]) / 2, p.shape_rect[1], "고객")
    figure = [r for r in owned(d, "고객") if not isinstance(r, Text)]
    assert [repr(r) for r in figure] == [repr(r) for r in c.records]
    (name,) = owned(d, "고객", Text)
    assert name.text == "고객" and name.y > p.shape_rect[3]


@pytest.mark.parametrize("side", ["bottom", "top", "left", "right"])
def test_actor_name_side_and_the_returned_place_draws_the_same(side):
    actor = el("actor", "고객", 0, 0, name_side=side)
    target = {"bottom": (-200, -100), "top": (-200, 150), "left": (200, 0), "right": (-300, 0)}[side]
    relations = [rel("association", "고객", "주문한다")]
    elements = [actor, el("use_case", "주문한다", *target)]
    d = draw(elements, relations)
    assert K.check(d).passed, (side, K.check(d).summary())
    p = placed(d, "고객")
    again = [{**actor, "left": p.rect[0], "top": p.rect[1]}, elements[1]]
    assert [repr(r) for r in draw(again, relations).canvas.records] == [repr(r) for r in d.canvas.records]


def test_line_through_the_actor_name_fails():
    # 이름이 아래(기본)인 액터에서 아래쪽 유즈케이스로 가는 선이 이름을 지나간다
    r = report([el("actor", "고객", 0, 0), el("use_case", "주문한다", -50, 150)], [rel("association", "고객", "주문한다")])
    assert kinds(r) == ["line_through_name"] and r.failures[0].elements == ("고객->주문한다", "고객")


def test_actor_line_aims_at_a_whole_pixel_so_level_lines_stay_level():
    # 사람 모양 높이(37)는 홀수 — 정수 top의 액터와 높이가 짝수인 타원을 가로로 맞추면 선이 수평이다
    d = draw([el("actor", "고객", 0, 7, name_side="left"), el("use_case", "주문한다", 200, 0)],
             [rel("association", "고객", "주문한다")])
    (pts,) = (p.points for p in d.layout.relations)
    assert pts[0][1] == pts[-1][1] == 25


def test_places_list_the_actor_figure():
    d = draw([el("actor", "고객", 0, 0)])
    p = d.layout.boxes[0]
    assert server._places(d) == [f"요소 자리(왼, 위, 폭×높이): 고객({B.fmt_rect(p.rect)}, 모양 {B.fmt_rect(p.shape_rect)})"]


# ---------------------------------------------------------------- 입력


def test_takes_only_its_element_and_relation_kinds():
    problems = errors([el("class", "A", 0, 0), el("use_case", "주문한다", 200, 0)],
                      [rel("realization", "주문한다", "A")])
    assert any(p.startswith("elements[0].kind:") for p in problems)
    assert any(p.startswith("relations[0].kind:") for p in problems)


def test_only_a_system_holds_elements():
    problems = errors([el("use_case", "주문한다", 0, 0), inside("주문한다", "use_case", "결제한다", 20, 20)])
    assert len(problems) == 1 and problems[0].startswith("elements[1].in:") and "'system'" in problems[0]


def test_actor_takes_no_size_and_no_element_takes_a_stereotype():
    problems = errors([el("actor", "고객", 0, 0, width=40), el("use_case", "주문한다", 200, 0, stereotype="core"),
                       el("system", "주문 시스템", 0, 200, stereotype="subsystem")])
    assert [p.split(":")[0] for p in problems] == ["elements[0].width", "elements[1].stereotype",
                                                    "elements[2].stereotype"]
    assert all("모르는 필드" in p for p in problems), problems


def test_name_side_is_only_for_actors_and_relation_names_take_two_lines():
    problems = errors([el("use_case", "주문한다", 0, 0, name_side="left")])
    assert len(problems) == 1 and "name_side" in problems[0]
    d = draw([el("use_case", "주문한다", 0, 0), el("use_case", "결제한다", 300, 0)],
             [rel("dependency", "주문한다", "결제한다", stereotype="include", name=["결제를", "부른다"])])
    assert d.layout.relations[0].labels[0].lines == ("«include»", "결제를", "부른다")
    assert K.check(d).passed, K.check(d).summary()


def test_drawing_order_puts_the_system_behind_the_lines():
    d = draw(SHOP, SHOP_RELATIONS)
    records = d.canvas.records
    first_line = min(i for i, r in enumerate(records) if r.owner == "고객->주문한다")
    assert all(i < first_line for i, r in enumerate(records) if r.owner == "sys")
    assert isinstance(owned(d, "sys")[0], Rect)
