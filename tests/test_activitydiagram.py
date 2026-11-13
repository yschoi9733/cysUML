"""액티비티도: 행동·결정·합류·시작·끝 점과 흐름, 조건 글자, 입력, 도구 설명."""
import math

import pytest

from cysuml import activitydiagram as A
from cysuml import boxcheck as K
from cysuml import guide
from cysuml.canvas import Polygon, Text
from cysuml.flowshapes import ACTION_RADIUS, ACTION_SIDE, DIAMOND, rounded
from cysuml.parsing import InputError
from cysuml.text import text_width


def el(kind, name=None, left=0, top=0, **more):
    return {"kind": kind, "left": left, "top": top, **more, **({} if name is None else {"name": name})}


def fl(source, target, **more):
    return {"from": source, "to": target, **more}


def draw(elements, relations=()):
    return A.render({"elements": list(elements), "relations": list(relations)})


def report(elements, relations=()):
    return K.check(draw(elements, relations))


def kinds(r):
    return [f.kind for f in r.failures]


def owned(drawing, owner, typ=object):
    return [r for r in drawing.canvas.records if r.owner == owner and isinstance(r, typ)]


def placed(drawing, key):
    (p,) = [p for p in drawing.layout.boxes if p.key == key]
    return p


FULL = [
    el("initial", id="start", left=190, top=0),
    el("action", "주문 받기", left=155, top=60),
    el("decision", id="stock?", left=185, top=160),
    el("action", "결제 요청", left=40, top=240),
    el("action", "입고 요청", left=270, top=240),
    el("action", "배송 준비", left=40, top=340),
    el("merge", id="join", left=185, top=440),
    el("action", ["주문 결과", "알리기"], id="notify", left=155, top=520),
    el("final", id="end", left=188, top=640),
]
FULL_FLOWS = [
    fl("start", "주문 받기"),
    fl("주문 받기", "stock?"),
    fl("stock?", "결제 요청", name="[재고 있음]", via=[[85, 175]]),
    fl("stock?", "입고 요청", name="[재고 없음]", via=[[315, 175]]),
    fl("결제 요청", "배송 준비"),
    fl("배송 준비", "join", via=[[85, 455]]),
    fl("입고 요청", "join", via=[[315, 455]]),
    fl("join", "notify"),
    fl("notify", "end"),
]


def test_activity_diagram_with_five_actions_a_decision_and_a_merge_passes():
    r = report(FULL, FULL_FLOWS)
    assert r.passed, r.summary()


def test_relation_without_kind_is_a_flow_and_the_guard_is_written_as_given():
    d = draw(FULL, FULL_FLOWS + [fl("배송 준비", "결제 요청", kind="flow", via=[[0, 360], [0, 260]])])
    assert {p.relation.kind for p in d.layout.relations} == {"flow"}
    assert [t.text for t in owned(d, "stock?->결제 요청", Text)] == ["[재고 있음]"]


def test_flow_through_another_action_or_a_guard_fails():
    # 위 행동에서 아래 행동으로 곧게 가는 흐름이 가운데 행동을 지난다
    r = report([el("action", "가"), el("action", "나", top=100), el("action", "다", top=200)], [fl("가", "다")])
    assert kinds(r) == ["line_through_box"] and r.failures[0].elements == ("가->다", "나")
    # 결정에서 오른쪽으로 나가는 흐름의 조건 글자를 위에서 내려오는 흐름이 지난다
    elements = [el("decision", id="d", left=0, top=100), el("action", "오른쪽", left=200, top=95),
                el("action", "위", left=40, top=-60), el("action", "아래", left=40, top=200)]
    r = report(elements, [fl("d", "오른쪽", name="[아주 긴 조건 글자]"), fl("위", "아래")])
    assert "line_through_text" in kinds(r)


def test_decision_and_merge_are_the_same_diamond():
    assert A.SHAPES["decision"] is A.SHAPES["merge"] is DIAMOND


def test_action_is_a_rounder_box_with_its_name_in_the_middle():
    d = draw([el("action", "결제 요청"), el("action", ["두 줄", "행동"], id="two", left=200)])
    p, two = placed(d, "결제 요청"), placed(d, "two")
    (poly,) = owned(d, "결제 요청", Polygon)
    assert poly.points == rounded(p.rect, ACTION_RADIUS) == p.border.points
    assert p.height == 40 and two.height == 55 and p.width == max(90, math.ceil(text_width("결제 요청") + 2 * ACTION_SIDE))
    (name,) = owned(d, "결제 요청", Text)
    assert (name.x, name.y, name.bold, name.anchor) == (p.rect[0] + p.width / 2, 20, False, "mm")
    tall = placed(draw([el("action", "높이", height=100)]), "높이")
    assert tall.height == 100


@pytest.mark.parametrize("elements, relations, expected", [
    ([el("action", "A"), el("action", "B", left=20, top=60, **{"in": "A"})], [],
     "안에 요소를 둘 수 없다 — 안에 요소를 두는 종류: 없음"),
    ([el("state", "A")], [], "'initial' · 'final' · 'action' · 'decision' · 'merge' 가운데 하나"),
    ([el("decision", "결정")], [], "elements[0].name: 모르는 필드다"),
    ([el("merge")], [], "'id' 필드가 빠졌다"),
    ([el("action", "A", actions=["do / x"])], [], "elements[0].actions: 모르는 필드다"),
    ([el("action", "A"), el("action", "B", top=100)], [fl("A", "B", kind="transition")], "relations[0].kind: 'flow' 가운데"),
    ([el("action", "A"), el("action", "B", top=100)], [fl("A", "B", navigable="none")], "relations[0].navigable: 모르는 필드다"),
])
def test_wrong_input(elements, relations, expected):
    with pytest.raises(InputError) as e:
        draw(elements, relations)
    assert any(expected in p for p in e.value.problems), e.value.problems


def test_tool_description_uses_the_shared_pieces_and_names_only_its_failure_kinds():
    assert A.KINDS == tuple(k for k in K.KINDS if k not in K.NESTED_KINDS)
    for part in (guide.flow(A.KINDS, A.SPEC.words), guide.NEW_INPUT, guide.PLACES_RESULT, A.TIPS):
        assert part in A.TOOL
    assert guide.NESTING not in A.TOOL and guide.relation_fields(A.SPEC) not in A.TOOL
    assert not any(n in A.TOOL for n in guide.kind_names(K.NESTED_KINDS))
    for kind in A.SHAPES:
        assert f'"{kind}"' in A.TOOL
    assert '"flow". 관계 종류가 하나뿐이라 빼도 된다' in A.TOOL
