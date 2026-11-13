"""상태도와 상태도·액티비티도가 함께 쓰는 모양(시작·끝 점, 둥근 모서리 상자, 마름모): 복합 상태의 이름 칸, 전이, 그린 기록."""
import math

import pytest

from cysuml import boxcheck as K
from cysuml import geom as G
from cysuml import guide
from cysuml import statediagram as S
from cysuml.canvas import Ellipse, Line, Polygon, Text
from cysuml.flowshapes import ACTION_LEFT, DIAMOND_SIZE, FINAL, FINAL_CORE, START, STATE_RADIUS, rounded
from cysuml.parsing import InputError


def el(kind, name=None, left=0, top=0, **more):
    return {"kind": kind, "left": left, "top": top, **more, **({} if name is None else {"name": name})}


def tr(source, target, **more):
    return {"from": source, "to": target, **more}


def draw(elements, relations=()):
    return S.render({"elements": list(elements), "relations": list(relations)})


def report(elements, relations=()):
    return K.check(draw(elements, relations))


def kinds(r):
    return [f.kind for f in r.failures]


def owned(drawing, owner, typ=object):
    return [r for r in drawing.canvas.records if r.owner == owner and isinstance(r, typ)]


def placed(drawing, key):
    (p,) = [p for p in drawing.layout.boxes if p.key == key]
    return p


# ---------------------------------------------------------------- 합격하는 상태도


FULL = [
    el("initial", id="start", left=0, top=90),
    el("state", "대기", left=60, top=80),
    el("state", "처리 중", left=300, top=0, actions=["entry / 잠금", "do / 감시"]),
    el("initial", id="in-start", left=320, top=110, **{"in": "처리 중"}),
    el("state", "검증", left=380, top=100, **{"in": "처리 중"}),
    el("state", "저장", left=380, top=200, **{"in": "처리 중"}),
    el("choice", id="ok?", left=620, top=205),
    el("state", "완료", left=700, top=200),
    el("final", id="end", left=733, top=320),
]
FULL_TRANSITIONS = [
    tr("start", "대기"),
    tr("대기", "처리 중", name="요청 [권한 있음] / 기록"),
    tr("in-start", "검증"),
    tr("검증", "저장", name="[통과]"),
    tr("저장", "ok?"),
    tr("ok?", "완료", name="[성공]"),
    tr("ok?", "대기", name="[실패]", via=[[635, 300], [105, 300]]),
    tr("완료", "완료", name="tick", via=[[745, 170], [815, 170], [815, 220]]),  # 오른쪽 위 모서리를 도는 자기 전이
    tr("완료", "end"),
]


def test_state_diagram_with_every_part_passes():
    # 시작·상태 넷 넘게·끝, 조건 있는 전이, 자기 전이, 복합 상태, entry/·do/ 칸, 선택 마름모
    r = report(FULL, FULL_TRANSITIONS)
    assert r.passed, r.summary()


def test_relation_without_kind_is_a_transition_and_its_text_is_written_as_given():
    d = draw(FULL, FULL_TRANSITIONS)
    assert {p.relation.kind for p in d.layout.relations} == {"transition"}
    texts = [t.text for t in owned(d, "대기->처리 중", Text)]
    assert texts == ["요청 [권한 있음] / 기록"]  # 도구가 대괄호를 씌우거나 빗금을 고치지 않는다
    assert [t.text for t in owned(d, "ok?->완료", Text)] == ["[성공]"]


def test_transition_kind_may_be_given_and_takes_a_stereotype_and_two_line_text():
    d = draw([el("state", "A"), el("state", "B", left=0, top=160)],
             [tr("A", "B", kind="transition", stereotype="timer", name=["after(5s)", "/ 다시 묻기"])])
    assert [t.text for t in owned(d, "A->B", Text)] == ["«timer»", "after(5s)", "/ 다시 묻기"]
    assert K.check(d).passed


# ---------------------------------------------------------------- 불합격


COMPOSITE = [el("state", "처리 중", left=0, top=0, actions=["entry / 잠금", "exit / 풀기"]),
             el("state", "검증", left=20, top=105, **{"in": "처리 중"})]


def test_line_through_the_actions_of_a_composite_state_fails():
    # 안의 상태에서 위쪽 밖 상태로 가는 전이가 이름·동작 칸을 지난다
    elements = COMPOSITE + [el("state", "밖", left=20, top=-150)]
    r = report(elements, [tr("검증", "밖")])
    assert kinds(r) == ["line_through_name"] and r.failures[0].elements == ("검증->밖", "처리 중")
    # 오른쪽 테두리로 건너면 합격한다
    assert report(elements, [tr("검증", "밖", via=[[160, 125], [160, -130]])]).passed


def test_transition_text_on_the_actions_of_a_composite_state_fails():
    # 칸 바로 아래 두 상태를 잇는 전이의 세 줄 글자는 위로 놓으면 동작 칸에, 아래로 놓으면 복합 상태 아래 테두리에 걸린다
    elements = COMPOSITE + [el("state", "저장", left=200, top=105, **{"in": "처리 중"})]
    r = report(elements, [tr("검증", "저장", name=["검증이", "끝나면", "저장한다"])])
    assert kinds(r) == ["text_on_box"]
    assert "끝을 품은 요소의 이름 칸에 겹친다" in r.failures[0].problem and r.failures[0].elements == ("검증->저장", "처리 중")


def test_line_through_another_state_and_through_a_transition_text_fail():
    elements = [el("state", "A", left=0, top=0), el("state", "B", left=0, top=120), el("state", "C", left=0, top=240)]
    r = report(elements, [tr("A", "C")])
    assert kinds(r) == ["line_through_box"] and r.failures[0].elements == ("A->C", "B")
    # 다른 전이가 글자를 지난다: A→B 글자는 선 오른쪽에 놓이는데, 왼쪽의 X→Y 선이 그 자리를 가로지른다
    elements = [el("state", "A", left=0, top=0), el("state", "B", left=0, top=160),
                el("state", "X", left=-200, top=80), el("state", "Y", left=200, top=80)]
    r = report(elements, [tr("A", "B", name="아주 긴 전이 글자"), tr("X", "Y")])
    assert "line_through_text" in kinds(r)


# ---------------------------------------------------------------- 모양과 크기


def test_state_is_a_rounded_polygon_that_is_both_drawn_and_checked():
    d = draw([el("state", "대기", left=10, top=20)])
    p = placed(d, "대기")
    (poly,) = owned(d, "대기", Polygon)
    assert poly.points == rounded(p.rect, STATE_RADIUS) == p.border.points
    assert p.border.bounds == p.rect and p.parts == (p.border,)
    # 모서리 호는 꼭짓점이 반지름 안쪽 원 위에 있다
    l, t = p.rect[:2]
    corner = [pt for pt in poly.points if pt[0] < l + STATE_RADIUS and pt[1] < t + STATE_RADIUS]
    assert corner and all(math.dist(pt, (l + STATE_RADIUS, t + STATE_RADIUS)) == pytest.approx(STATE_RADIUS) for pt in corner)


def test_rounded_corners_meet_the_straight_edges_exactly():
    pts = rounded((0.1, 0.2, 100.3, 40.4), 10)
    edges = list(zip(pts, pts[1:] + pts[:1]))
    straight = [(a, b) for a, b in edges if a[0] == b[0] or a[1] == b[1]]
    assert len(straight) == 4 and len(pts) == 4 * 7  # 호마다 7점, 곧은 변 넷
    assert G.PolygonBorder(pts).points == pts  # 겹치거나 한 줄 위의 꼭짓점이 없다


def test_line_into_a_rounded_corner_ends_on_the_arc():
    # A(0, 0, 90×40) 가운데 (45, 20)에서 (−42, −17) 쪽으로 가는 선은 왼쪽 위 모서리 호로 나간다
    d = draw([el("state", "A", left=0, top=0), el("state", "B", left=-252, top=-102)], [tr("A", "B")])
    end = d.layout.relations[0].points[0]
    assert end[0] < STATE_RADIUS and end[1] < STATE_RADIUS
    assert math.dist(end, (STATE_RADIUS, STATE_RADIUS)) == pytest.approx(STATE_RADIUS, abs=0.5)


def test_state_name_zone_covers_the_name_and_the_actions():
    plain, two, acts = draw([el("state", "A"), el("state", ["두 줄", "이름"], id="B", left=200),
                             el("state", "C", left=400, actions=["entry / 하나", "do / 둘"])]).layout.boxes
    assert plain.zones[0].rect == (0, 0, plain.rect[2], 40) and plain.height == 40
    assert two.zones[0].rect[3] == 55 and two.height == 55
    assert acts.zones[0].rect[3] == 40 + 10 + 2 * 15 and acts.height == 80
    assert not any(z.outside for p in (plain, two, acts) for z in p.zones)


def test_children_go_under_the_name_zone_as_the_description_says():
    # 이름 한 줄·동작 없는 복합 상태 안의 요소는 top + 60부터 둔다
    assert "top + 60부터" in S.TOOL
    outer = el("state", "밖", left=0, top=0)
    assert report([outer, el("state", "안", left=20, top=60, **{"in": "밖"})]).passed
    assert kinds(report([outer, el("state", "안", left=20, top=59, **{"in": "밖"})])) == ["inner_off_area"]


def test_lines_under_the_name_and_under_the_zone_are_drawn_only_when_something_is_below():
    d = draw([el("state", "단순"), el("state", "동작", left=200, actions=["do / 일"]),
              el("state", "복합", left=0, top=200), el("state", "안", left=20, top=260, **{"in": "복합"})])
    assert owned(d, "단순", Line) == []
    act = placed(d, "동작")
    (line,) = owned(d, "동작", Line)
    assert line.points == ((act.rect[0], 40), (act.rect[2], 40))
    (row,) = [t for t in owned(d, "동작", Text) if t.text == "do / 일"]
    assert row.x == act.rect[0] + ACTION_LEFT
    comp = placed(d, "복합")
    (line,) = owned(d, "복합", Line)
    assert line.points == ((comp.rect[0], 240), (comp.rect[2], 240))


def test_start_final_and_choice_are_drawn_as_their_shapes():
    d = draw([el("initial", id="s"), el("final", id="f", left=100), el("choice", id="c", left=200)])
    (dot,) = owned(d, "s", Ellipse)
    assert (dot.width, dot.height, dot.fill) == (START, START, "black")
    outer, core = owned(d, "f", Ellipse)
    assert (outer.width, outer.fill) == (FINAL, "white") and (core.width, core.fill) == (FINAL_CORE, "black")
    assert (core.left + core.width / 2, core.top + core.height / 2) == (outer.left + FINAL / 2, outer.top + FINAL / 2)
    c = placed(d, "c")
    (poly,) = owned(d, "c", Polygon)
    assert c.rect == (200, 0, 200 + DIAMOND_SIZE, DIAMOND_SIZE) and poly.points == c.border.points
    assert len(poly.points) == 4 and all(isinstance(p.border, G.EllipseBorder) for p in (placed(d, "s"), placed(d, "f")))


def test_lines_end_on_the_real_circle_and_diamond():
    d = draw([el("initial", id="s"), el("choice", id="c", left=100, top=100)], [tr("s", "c")])
    start, end = d.layout.relations[0].points
    assert math.dist(start, (10, 10)) == pytest.approx(START / 2, abs=0.01)
    assert abs(end[0] - 115) + abs(end[1] - 115) == pytest.approx(DIAMOND_SIZE / 2)  # 마름모 변 위


def test_two_diamonds_whose_boxes_overlap_but_not_their_shapes_pass():
    # 두 마름모를 비스듬히 놓으면 둘레 사각형은 겹쳐도 마름모끼리는 떨어져 있다
    assert report([el("choice", id="a"), el("choice", id="b", left=24, top=24)]).passed


# ---------------------------------------------------------------- 입력


@pytest.mark.parametrize("elements, relations, expected", [
    ([el("initial", "시작")], [], "elements[0].name: 모르는 필드다"),
    ([el("initial")], [], "elements[0]: 'id' 필드가 빠졌다 — 이름이 없는 요소는"),
    ([el("choice", id="c", actions=["x"])], [], "elements[0].actions: 모르는 필드다"),
    ([el("state", "A", stereotype="x")], [], "elements[0].stereotype: 모르는 필드다"),
    ([el("final", id="f", width=40)], [], "elements[0].width: 모르는 필드다"),
    ([el("action", "A")], [], "elements[0].kind: 'initial' · 'final' · 'state' · 'choice' 가운데 하나"),
    ([el("state", "A"), el("state", "B", left=200)], [tr("A", "B", kind="flow")], "relations[0].kind: 'transition' 가운데"),
    ([el("state", "A"), el("state", "B", left=200)], [tr("A", "B", navigable="to")], "relations[0].navigable: 모르는 필드다"),
    ([el("state", "A"), el("state", "B", left=200)], [tr("A", "B", to_multiplicity="1")],
     "relations[0].to_multiplicity: 모르는 필드다"),
    ([el("state", "A", actions="entry / x")], [], "elements[0].actions: 목록이어야 한다"),
    ([el("state", "A"), el("initial", id="s", left=200, **{"in": "s"})], [], "elements[1].in: 제 자신 안에"),
    ([el("choice", id="c"), el("state", "A", left=200, **{"in": "c"})], [], "안에 요소를 둘 수 없다 — 안에 요소를 두는 종류: 'state'"),
    ([el("state", "A")], [tr("A", "A", via=[[200, 0]])], "꺾는 점(via)이 둘 이상"),
])
def test_wrong_input(elements, relations, expected):
    with pytest.raises(InputError) as e:
        draw(elements, relations)
    assert any(expected in p for p in e.value.problems), e.value.problems


# ---------------------------------------------------------------- 도구 설명


def test_tool_description_uses_the_shared_pieces_and_its_own_relation_fields():
    for part in (guide.flow(K.KINDS, S.SPEC.words), guide.NEW_INPUT, guide.NESTING, guide.PLACES_RESULT, S.TIPS):
        assert part in S.TOOL
    assert guide.relation_fields(S.SPEC) not in S.TOOL and guide.OUTSIDE_PLACES not in S.TOOL
    assert guide.PLACED_ELEMENTS not in S.TOOL
    for kind in S.SHAPES:
        assert f'"{kind}"' in S.TOOL
    assert '"transition". 관계 종류가 하나뿐이라 빼도 된다' in S.TOOL
    for field in ("from·to(필수)", "name:", "via:", "actions:", "in:", "width·height:"):
        assert field in S.TOOL
