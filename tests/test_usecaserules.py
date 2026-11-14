"""유즈케이스도의 표기 규칙(usecasediagram.RULES): 액터는 시스템 경계 밖, 연관은 액터와 유즈케이스 사이, 일반화는 같은 종류끼리
고리 없이, «include»·«extend»는 유즈케이스 사이의 의존에만. 모두 입력 오류다."""
import random

import anyio
import pytest
from mcp import Client

from cysuml import boxcheck, server
from cysuml import usecasediagram as U
from cysuml.parsing import InputError

INCLUDE_ONLY = "«include»·«extend»는 유즈케이스 사이의 dependency에만 단다"
SAME_SYSTEM = "같은 시스템 경계 안이거나 둘 다 경계 밖인 유즈케이스는 연관으로 잇지 않는다"


def el(kind, name, left, top, **more):
    return {"kind": kind, "name": name, "left": left, "top": top, **more}


def inside(parent, kind, name, left, top, **more):
    return el(kind, name, left, top, **{"in": parent}, **more)


def rel(kind, source, target, **more):
    return {"kind": kind, "from": source, "to": target, **more}


SYSTEM = el("system", "주문 시스템", 200, 0, id="sys")
ORDER = inside("sys", "use_case", "주문한다", 240, 60)
PAY = inside("sys", "use_case", "결제한다", 240, 160)
CUSTOMER = el("actor", "고객", 40, 80, name_side="left")
BANK = el("actor", "은행", 560, 80, name_side="right")
BASE = [SYSTEM, ORDER, PAY, CUSTOMER, BANK]
LOOP = [[0, 0], [0, 10]]  # 자기 자신으로 가는 관계의 꺾는 점


def problems(relations, elements=BASE):
    with pytest.raises(InputError) as e:
        U.parse({"elements": list(elements), "relations": list(relations)})
    return e.value.problems


def reads(relations, elements=BASE):
    d = U.parse({"elements": list(elements), "relations": list(relations)})
    assert d.notices == ()
    return d


# ---------------------------------------------------------------- 이슈의 다섯 경우


ACTOR_INSIDE = [SYSTEM, ORDER, PAY, inside("sys", "actor", "고객", 240, 260)]
ISSUE_CASES = [  # (요소, 관계, 오류, 고치는 법대로 고친 요소, 고친 관계)
    (ACTOR_INSIDE, [rel("association", "고객", "주문한다")],
     "elements[3].in: 액터는 시스템 경계('sys') 안에 둘 수 없다 — 액터는 시스템 밖의 사람이나 외부 시스템이다. in을 빼고 시스템 "
     "경계 밖(왼쪽이나 오른쪽)에 둔다",
     BASE, [rel("association", "고객", "주문한다")]),
    (BASE, [rel("generalization", "고객", "주문한다")],
     "relations[0]: 일반화의 두 끝 종류가 다르다(from '고객': 'actor', to '주문한다': 'use_case') — 일반화는 액터끼리, "
     "유즈케이스끼리 긋는다. 액터가 유즈케이스를 쓰는 것이면 kind를 'association'으로 바꾸고, 아니면 이 일반화를 지운다",
     BASE, [rel("association", "고객", "주문한다")]),
    (BASE, [rel("association", "고객", "sys")],
     "relations[0]: 연관이 시스템 경계에 닿는다(to 'sys': 'system') — 연관은 액터와 유즈케이스 사이에 긋는다. 시스템 경계 쪽 끝을 "
     "그 액터가 쓰는 유즈케이스로 고친다",
     BASE, [rel("association", "고객", "주문한다")]),
    (BASE, [rel("association", "주문한다", "결제한다", stereotype="include")],
     f"relations[0].stereotype: {INCLUDE_ONLY}(이 관계는 'association', from '주문한다': 'use_case', to '결제한다': "
     "'use_case') — kind를 'dependency'로 바꾼다",
     BASE, [rel("dependency", "주문한다", "결제한다", stereotype="include")]),
    (BASE, [rel("dependency", "고객", "주문한다", stereotype="include")],
     f"relations[0].stereotype: {INCLUDE_ONLY}(이 관계는 'dependency', from '고객': 'actor', to '주문한다': 'use_case') — "
     "액터와 유즈케이스는 stereotype 없는 연관으로 잇는다. kind를 'association'으로 바꾸고 stereotype을 뺀다",
     BASE, [rel("association", "고객", "주문한다")]),
]


@pytest.mark.parametrize("elements, relations, error, fixed_elements, fixed_relations", ISSUE_CASES)
def test_the_inputs_the_issue_lists_are_input_errors_that_say_where_and_how_to_fix(elements, relations, error,
                                                                                   fixed_elements, fixed_relations):
    assert problems(relations, elements) == (error,)
    reads(fixed_relations, fixed_elements)


def test_rule_errors_come_together_with_other_input_errors():
    found = problems([rel("generalization", "고객", "주문한다")], [SYSTEM, ORDER, {**PAY, "left": "x"}, ACTOR_INSIDE[3]])
    assert [p.split(":")[0] for p in found] == ["elements[2].left", "elements[3].in", "relations[0]"]
    # 다른 곳이 틀려 읽히지 않은 요소의 관계는 규칙이 보지 않는다(그 요소의 문제는 이미 알렸다)
    found = problems([rel("generalization", "고객", "주문한다")], [*ACTOR_INSIDE[:3], {**ACTOR_INSIDE[3], "left": "x"}])
    assert [p.split(":")[0] for p in found] == ["elements[3].left"]


# ---------------------------------------------------------------- 액터와 시스템 경계


def test_an_actor_inside_a_nested_system_is_an_input_error_and_a_bad_in_is_told_once():
    nested = [SYSTEM, inside("sys", "system", "결제 시스템", 240, 60, id="pay"), inside("pay", "actor", "카드사", 260, 100)]
    (p,) = problems([], nested)
    assert p.startswith("elements[2].in: 액터는 시스템 경계('pay') 안에 둘 수 없다")
    # in이 없는 요소를 가리키면 그 오류만 낸다(규칙은 읽힌 시스템 경계만 본다)
    (p,) = problems([], [SYSTEM, inside("nowhere", "actor", "고객", 0, 0)])
    assert p.startswith("elements[1].in: 열쇠가 'nowhere'인 요소가 없다")


@pytest.mark.parametrize("kind, told", [("actor", False), ("use_case", True)])
def test_the_overlap_hint_offers_in_only_for_elements_a_system_may_hold(kind, told):
    # 시스템 경계 칸에 놓였지만 in이 없는 요소 — 액터에게는 in을 권하지 않는다(그러면 입력 오류다)
    d = U.render({"elements": [el("system", "S", 0, 0, id="s", width=600, height=400), inside("s", "use_case", "U", 40, 60),
                               el(kind, "X", 300, 200)]})
    (f,) = [f for f in boxcheck.check(d).failures if f.kind == "box_overlap"]
    assert ("X의 in에 s를 준다" in f.hint) is told, f.hint


def test_a_use_case_in_a_system_that_did_not_read_is_not_told_it_is_outside():
    # 경계가 다른 곳이 틀려 읽히지 않았으면 주체를 모르니 유즈케이스끼리 연관 규칙을 보지 않는다(경계의 문제만 알린다)
    found = problems([rel("association", "U1", "U2")],
                     [el("system", "S", 0, 0, id="s", width=-5), inside("s", "use_case", "U1", 20, 40),
                      el("use_case", "U2", 400, 0)])
    assert found == ("elements[0].width: 0~1000000 사이여야 한다(받은 값 -5)",)


def test_an_in_pointing_at_an_element_that_holds_nothing_is_told_once():
    # 품을 수 없는 요소를 가리킨 in은 엔진이 알린다 — 액터 규칙도, 유즈케이스끼리 연관 규칙도 덧붙이지 않는다
    elements = [*BASE, inside("주문한다", "actor", "직원", 0, 300), inside("고객", "use_case", "문의한다", 0, 400),
                el("use_case", "환불한다", 600, 300)]
    found = problems([rel("association", "문의한다", "환불한다")], elements)
    assert [p.split(":")[0] for p in found] == ["elements[5].in", "elements[6].in"]
    assert all("안에 요소를 둘 수 없다" in p for p in found), found


# ---------------------------------------------------------------- 일반화


OUTSIDE = el("use_case", "문의한다", 0, 300)  # 시스템 경계 밖의 유즈케이스
OTHER_SYSTEM = el("system", "결제 시스템", 700, 0, id="pay")


@pytest.mark.parametrize("source, target, fix, fixed", [
    ("고객", "sys", "시스템 경계 쪽 끝을 액터로 고친다", ("고객", "은행")),
    ("sys", "은행", "시스템 경계 쪽 끝을 액터로 고친다", ("고객", "은행")),
    ("문의한다", "sys", "시스템 경계 쪽 끝을 유즈케이스로 고친다", ("문의한다", "주문한다")),
])
def test_a_system_is_never_an_end_of_a_generalization(source, target, fix, fixed):
    assert problems([rel("generalization", source, target)], [*BASE, OUTSIDE]) == (
        f"relations[0]: 시스템 경계('sys')는 일반화의 끝이 될 수 없다 — 일반화는 액터끼리, 유즈케이스끼리 긋는다. {fix}",)
    reads([rel("generalization", *fixed)], [*BASE, OUTSIDE])


def test_generalization_between_systems_is_an_input_error():
    (p,) = problems([rel("generalization", "pay", "sys")], [*BASE, OTHER_SYSTEM])
    assert p == ("relations[0]: 시스템 경계('pay')는 일반화의 끝이 될 수 없다 — 일반화는 액터끼리, 유즈케이스끼리 긋는다. "
                 "from·to를 둘 다 액터나 둘 다 유즈케이스로 고친다")


def test_generalization_between_an_actor_and_a_use_case_already_joined_says_to_delete_it():
    assert problems([rel("association", "주문한다", "고객"), rel("generalization", "주문한다", "고객")]) == (
        "relations[1]: 일반화의 두 끝 종류가 다르다(from '주문한다': 'use_case', to '고객': 'actor') — 일반화는 액터끼리, "
        "유즈케이스끼리 긋는다. 두 끝을 잇는 association이 이미 있다. 이 일반화를 지운다",)


def test_generalization_to_itself_is_refused_even_with_bend_points():
    assert problems([rel("generalization", "고객", "고객", via=LOOP)]) == (
        "relations[0]: 일반화는 자기 자신으로 갈 수 없다 — from과 to를 다른 요소로 고친다",)


def test_generalization_loops_are_told_once_per_loop():
    assert problems([rel("generalization", "고객", "은행"), rel("generalization", "은행", "고객")]) == (
        "relations[0]: 일반화가 고리를 이룬다('고객' → '은행' → '고객') — 조상이 다시 자식이 될 수 없다. 둘 가운데 하나를 지운다",)
    three = [*BASE, inside("sys", "use_case", "환불한다", 480, 160)]
    (p,) = problems([rel("generalization", "주문한다", "결제한다"), rel("generalization", "결제한다", "환불한다"),
                     rel("generalization", "환불한다", "주문한다")], three)
    assert p.startswith("relations[0]: 일반화가 고리를 이룬다('주문한다' → '결제한다' → '환불한다' → '주문한다')")


def test_generalization_between_actors_or_between_use_cases_reads():
    reads([rel("generalization", "은행", "고객"), rel("generalization", "결제한다", "주문한다")])


# ---------------------------------------------------------------- 연관


def test_association_touching_a_system_names_the_system_ends():
    assert problems([rel("association", "sys", "pay")], [*BASE, OTHER_SYSTEM]) == (
        "relations[0]: 연관이 시스템 경계에 닿는다(from 'sys': 'system', to 'pay': 'system') — 연관은 액터와 유즈케이스 사이에 "
        "긋는다. from·to를 액터와 유즈케이스로 고친다",)
    (p,) = problems([rel("association", "문의한다", "sys")], [*BASE, OUTSIDE])
    assert p.endswith("시스템 경계 쪽 끝을 그 유즈케이스를 쓰는 액터로 고친다")
    reads([rel("association", "문의한다", "고객")], [*BASE, OUTSIDE])


CARD = el("actor", "카드사", 560, 200, name_side="right")


@pytest.mark.parametrize("relations, fix", [
    ([rel("association", "고객", "은행")],
     "한 액터가 다른 액터의 한 종류면 kind를 'generalization'으로 바꾸고(from이 자식), 아니면 이 연관을 지운다"),
    ([rel("generalization", "고객", "은행"), rel("association", "은행", "고객")],
     "일반화로 두면 고리가 된다('은행' → '고객' → '은행'). 이 연관을 지운다"),
    # 일반화로 바꾸면 여러 단계 고리가 된다
    ([rel("generalization", "고객", "은행"), rel("generalization", "은행", "카드사"), rel("association", "카드사", "고객")],
     "일반화로 두면 고리가 된다('카드사' → '고객' → '은행' → '카드사'). 이 연관을 지운다"),
    ([rel("association", "고객", "고객", via=LOOP)], "자기 자신과 잇는 연관은 지운다"),
])
def test_association_between_actors_is_an_input_error(relations, fix):
    (p,) = problems(relations, [*BASE, CARD])
    i = len(relations) - 1
    a, b = relations[-1]["from"], relations[-1]["to"]
    assert p == (f"relations[{i}]: 액터끼리 잇는 연관이다(from '{a}': 'actor', to '{b}': 'actor') — 액터는 유즈케이스와 연관으로 "
                 f"잇는다. {fix}")


# ---------------------------------------------------------------- 고치는 법끼리(앞 오류의 고치는 법이 만들 관계를 본다)


LOOP_BACK = "일반화로 두면 고리가 된다('은행' → '고객' → '은행')"


@pytest.mark.parametrize("second, fix", [
    (rel("association", "은행", "고객"), f"{LOOP_BACK}. 이 연관을 지운다"),
    # 액터 사이 의존은 받으니 stereotype만 빼라고 하고, 일반화는 고리가 되어 권하지 않는다
    (rel("dependency", "은행", "고객", stereotype="include"), "의존을 뜻했으면 stereotype을 빼고, 아니면 이 관계를 지운다"),
    (rel("generalization", "은행", "고객", stereotype="include"), f"{LOOP_BACK}. 이 관계를 지운다"),
])
def test_a_later_error_is_not_told_to_close_a_loop_with_the_fix_of_an_earlier_one(second, fix):
    first, then = problems([rel("association", "고객", "은행"), second])
    assert first.endswith("kind를 'generalization'으로 바꾸고(from이 자식), 아니면 이 연관을 지운다")
    assert then.endswith(f" {fix}")
    reads([rel("generalization", "고객", "은행")])


def test_errors_whose_fixes_would_close_a_loop_of_three_are_told_to_go():
    found = problems([rel("association", "고객", "은행"), rel("association", "은행", "카드사"), rel("association", "카드사", "고객")],
                     [*BASE, CARD])
    assert [p.split(" — ")[-1] for p in found] == [
        "액터는 유즈케이스와 연관으로 잇는다. 한 액터가 다른 액터의 한 종류면 kind를 'generalization'으로 바꾸고(from이 자식), 아니면 "
        "이 연관을 지운다"] * 2 + [
        "액터는 유즈케이스와 연관으로 잇는다. 일반화로 두면 고리가 된다('카드사' → '고객' → '은행' → '카드사'). 이 연관을 지운다"]
    found = problems([rel("association", "고객", "은행"), rel("association", "은행", "카드사"),
                      rel("generalization", "카드사", "고객")], [*BASE, CARD])
    assert found[1].endswith("일반화로 두면 고리가 된다('은행' → '카드사' → '고객' → '은행'). 이 연관을 지운다")
    reads([rel("generalization", "고객", "은행"), rel("generalization", "카드사", "고객")], [*BASE, CARD])


def test_two_fixes_that_would_make_the_same_association_are_not_both_given():
    first, then = problems([rel("generalization", "고객", "주문한다"), rel("dependency", "고객", "주문한다", stereotype="include")])
    assert first.endswith("kind를 'association'으로 바꾸고, 아니면 이 일반화를 지운다")
    assert then.endswith("— 액터와 유즈케이스는 stereotype 없는 연관으로 잇는다. 두 끝을 잇는 association이 생긴다(relations[0]의 "
                         "고치는 법). 이 관계를 지운다")


def test_two_use_case_generalizations_with_extend_the_other_way_round_get_one_fix():
    first, then = problems([rel("generalization", "주문한다", "결제한다", stereotype="extend"),
                            rel("generalization", "결제한다", "주문한다", stereotype="extend")])
    assert first.endswith(") — 포함·확장이면 kind를 'dependency'로 바꾸고, 일반화를 뜻했으면 stereotype을 빼고, 아니면 이 관계를 지운다")
    assert then.endswith(") — 포함·확장이면 kind를 'dependency'로 바꾸고, 아니면 이 관계를 지운다")  # 일반화는 앞 것과 고리가 된다


def test_two_use_case_associations_the_other_way_round_do_not_become_includes_of_each_other():
    first, then = problems([rel("association", "주문한다", "결제한다"), rel("association", "결제한다", "주문한다")])
    assert first.endswith("포함·확장이면 kind를 'dependency'로 바꾸고 stereotype을 'include'나 'extend'로 하고, 아니면 이 연관을 지운다")
    assert then.endswith("확장이면 kind를 'dependency'로 바꾸고 stereotype을 'extend'로 하고(«include»는 안 된다 — «include»로 두면 "
                         "고리가 된다('결제한다' → '주문한다' → '결제한다')), 아니면 이 연관을 지운다")


def test_the_same_relation_twice_is_not_offered():
    first, then = problems([rel("association", "고객", "은행"), rel("association", "고객", "은행")])
    assert then.endswith(" 같은 from·to의 generalization이 생긴다(relations[0]의 고치는 법). 이 연관을 지운다")


# ---------------------------------------------------------------- 유즈케이스끼리 연관


def test_association_between_use_cases_of_one_subject_is_an_input_error():
    assert problems([rel("association", "주문한다", "결제한다", stereotype="trace")]) == (
        "relations[0]: 같은 시스템 경계('sys') 안의 유즈케이스끼리 잇는 연관이다(from '주문한다': 'use_case', to '결제한다': "
        f"'use_case') — {SAME_SYSTEM}. 포함·확장이면 kind를 'dependency'로 바꾸고 stereotype을 'include'나 'extend'로 하고, 아니면 "
        "이 연관을 지운다",)
    bare = [el("use_case", "A", 0, 0), el("use_case", "B", 300, 0)]
    (p,) = problems([rel("association", "A", "B")], bare)
    assert p.startswith("relations[0]: 시스템 경계 밖의 유즈케이스끼리 잇는 연관이다")
    reads([rel("dependency", "A", "B", stereotype="extend")], bare)


@pytest.mark.parametrize("other", [rel("dependency", "결제한다", "주문한다"), rel("generalization", "주문한다", "결제한다")])
def test_association_between_use_cases_joined_by_another_kind_is_told_to_become_a_dependency(other):
    # 다른 관계와 선이 포개지는 것은 검사가 알리고 꺾는 점으로 푼다 — 지우라고 하지 않는다
    (p,) = problems([other, rel("association", "주문한다", "결제한다")])
    assert p.endswith(f"{SAME_SYSTEM}. 포함·확장이면 kind를 'dependency'로 바꾸고 stereotype을 'include'나 'extend'로 하고, 아니면 이 "
                      "연관을 지운다")


def test_association_between_use_cases_already_included_may_only_extend():
    (p,) = problems([rel("dependency", "주문한다", "결제한다", stereotype="include"), rel("association", "주문한다", "결제한다")])
    assert p.endswith("«include»는 안 된다 — 같은 from·to의 dependency가 이미 있다), 아니면 이 연관을 지운다")
    (p,) = problems([rel("dependency", "주문한다", "결제한다", stereotype="extend"), rel("association", "주문한다", "결제한다")])
    assert p.endswith(f"{SAME_SYSTEM}. 포함이면 kind를 'dependency'로 바꾸고 stereotype을 'include'로 하고(«extend»는 안 된다 — 같은 "
                      "from·to의 dependency가 이미 있다), 아니면 이 연관을 지운다")


def test_the_same_use_case_association_twice_is_offered_a_dependency_once():
    first, then = problems([rel("association", "주문한다", "결제한다"), rel("association", "주문한다", "결제한다")])
    assert first.endswith("stereotype을 'include'나 'extend'로 하고, 아니면 이 연관을 지운다")
    assert then.endswith(f"{SAME_SYSTEM}. 같은 from·to의 dependency가 생긴다(relations[0]의 고치는 법). 이 연관을 지운다")


def test_association_between_use_cases_that_would_close_an_include_loop_may_only_extend():
    three = [*BASE, inside("sys", "use_case", "환불한다", 480, 160)]
    (p,) = problems([rel("dependency", "결제한다", "환불한다", stereotype="include"),
                     rel("dependency", "환불한다", "주문한다", stereotype="include"), rel("association", "주문한다", "결제한다")], three)
    assert p.endswith(f"{SAME_SYSTEM}. 확장이면 kind를 'dependency'로 바꾸고 stereotype을 'extend'로 하고(«include»는 안 된다 — "
                      "«include»로 두면 고리가 된다('주문한다' → '결제한다' → '환불한다' → '주문한다')), 아니면 이 연관을 지운다")


def test_association_between_use_cases_of_different_subjects_reads():
    # 서로 다른 시스템 경계 안이거나, 하나만 경계 안이면 주체가 다르다
    other = [el("system", "결제 시스템", 700, 0, id="pay"), inside("pay", "use_case", "승인한다", 740, 60),
             el("use_case", "문의한다", 0, 300)]
    reads([rel("association", "결제한다", "승인한다"), rel("association", "문의한다", "주문한다")], [*BASE, *other])


def test_association_between_an_actor_and_a_use_case_reads_both_ways():
    reads([rel("association", "고객", "주문한다"), rel("association", "결제한다", "은행", navigable="to")])


# ---------------------------------------------------------------- «include»·«extend»


REFUND = inside("sys", "use_case", "환불한다", 480, 160)


@pytest.mark.parametrize("relations, fix", [
    ([rel("generalization", "주문한다", "결제한다", stereotype="extend")],
     "포함·확장이면 kind를 'dependency'로 바꾸고, 일반화를 뜻했으면 stereotype을 빼고, 아니면 이 관계를 지운다"),
    # 일반화로 두면 고리가 된다
    ([rel("generalization", "결제한다", "환불한다"), rel("generalization", "환불한다", "주문한다"),
      rel("generalization", "주문한다", "결제한다", stereotype="extend")],
     "포함·확장이면 kind를 'dependency'로 바꾸고, 아니면 이 관계를 지운다"),
    ([rel("dependency", "주문한다", "결제한다", stereotype="include"),
      rel("association", "주문한다", "결제한다", stereotype="include")], "같은 from·to의 dependency가 이미 있다. 이 관계를 지운다"),
    # 종류·stereotype이 다른 관계와 선이 포개지는 것은 꺾는 점으로 푼다
    ([rel("dependency", "주문한다", "결제한다", stereotype="trace"),
      rel("association", "주문한다", "결제한다", stereotype="include")], "kind를 'dependency'로 바꾼다"),
    ([rel("association", "결제한다", "주문한다", stereotype="include")], "kind를 'dependency'로 바꾼다"),
    ([rel("association", "고객", "주문한다", stereotype="Include")],
     "액터와 유즈케이스는 stereotype 없는 연관으로 잇는다. stereotype을 뺀다"),
    ([rel("association", "고객", "주문한다"), rel("association", "고객", "주문한다", stereotype="include")],
     "액터와 유즈케이스는 stereotype 없는 연관으로 잇는다. 두 끝을 잇는 association이 이미 있다. 이 관계를 지운다"),
    ([rel("association", "고객", "주문한다"), rel("dependency", "고객", "주문한다", stereotype="include")],
     "액터와 유즈케이스는 stereotype 없는 연관으로 잇는다. 두 끝을 잇는 association이 이미 있다. 이 관계를 지운다"),
    ([rel("dependency", "고객", "sys", stereotype="include")],
     "액터와 유즈케이스는 stereotype 없는 연관으로 잇는다. 시스템 경계 쪽 끝을 그 액터가 쓰는 유즈케이스로 고치고 kind를 "
     "'association'으로 바꾸고 stereotype을 뺀다"),
    ([rel("association", "sys", "은행", stereotype="extend")],
     "액터와 유즈케이스는 stereotype 없는 연관으로 잇는다. 시스템 경계 쪽 끝을 그 액터가 쓰는 유즈케이스로 고치고 stereotype을 뺀다"),
    ([rel("generalization", "고객", "은행", stereotype="include")], "액터 사이 일반화를 뜻했으면 stereotype을 빼고, 아니면 이 관계를 지운다"),
    ([rel("generalization", "은행", "고객"), rel("generalization", "고객", "은행", stereotype="include")],
     "일반화로 두면 고리가 된다('고객' → '은행' → '고객'). 이 관계를 지운다"),
    ([rel("association", "주문한다", "주문한다", stereotype="extend", via=LOOP)], "자기 자신과 잇는 관계는 지운다"),
    ([rel("dependency", "고객", "은행", stereotype="include")],
     "의존을 뜻했으면 stereotype을 빼고, 한 액터가 다른 액터의 한 종류면 stereotype을 빼고 kind를 'generalization'으로 "
     "바꾸고(from이 자식), 아니면 이 관계를 지운다"),
])
def test_include_and_extend_off_a_dependency_between_use_cases_is_one_input_error(relations, fix):
    (p,) = problems(relations, [*BASE, REFUND])  # 관계 하나에는 오류 하나 — 시스템 경계에 닿는 연관도 «include»·«extend» 오류만 낸다
    i = len(relations) - 1
    assert p.startswith(f"relations[{i}].stereotype: {INCLUDE_ONLY}(이 관계는 {relations[-1]['kind']!r}, ")
    assert p.endswith(f") — {fix}")


def test_a_use_case_including_itself_is_an_input_error():
    assert problems([rel("dependency", "주문한다", "주문한다", stereotype="include", via=LOOP)]) == (
        "relations[0]: 유즈케이스는 자기 자신을 포함할 수 없다(«include») — 이 관계를 지운다",)
    reads([rel("dependency", "주문한다", "주문한다", stereotype="extend", via=LOOP)])


def test_include_loops_are_input_errors():
    assert problems([rel("dependency", "주문한다", "결제한다", stereotype="include"),
                     rel("dependency", "결제한다", "주문한다", stereotype="Include")]) == (
        "relations[0]: «include»가 고리를 이룬다('주문한다' → '결제한다' → '주문한다') — 유즈케이스는 저를 포함하는 유즈케이스를 "
        "다시 포함할 수 없다. 둘 가운데 하나를 지운다",)
    (p,) = problems([rel("dependency", "주문한다", "결제한다", stereotype="include"),
                     rel("dependency", "결제한다", "환불한다", stereotype="include"),
                     rel("dependency", "환불한다", "주문한다", stereotype="include")], [*BASE, REFUND])
    assert p.endswith("다시 포함할 수 없다. 고리 안의 «include» 하나를 지우거나 from·to를 바꾼다")
    # «extend»가 섞인 고리는 막지 않는다
    reads([rel("dependency", "주문한다", "결제한다", stereotype="include"), rel("dependency", "결제한다", "주문한다", stereotype="extend")])


@pytest.mark.parametrize("relation, fix, fixed", [
    (rel("dependency", "문의한다", "sys", stereotype="include"), "시스템 경계 쪽 끝을 유즈케이스로 고친다",
     rel("dependency", "문의한다", "주문한다", stereotype="include")),
    (rel("association", "문의한다", "sys", stereotype="include"), "시스템 경계 쪽 끝을 유즈케이스로 고치고 kind를 'dependency'로 바꾼다",
     rel("dependency", "문의한다", "주문한다", stereotype="include")),
    (rel("dependency", "pay", "sys", stereotype="extend"), "from·to를 유즈케이스로 고친다",
     rel("dependency", "문의한다", "주문한다", stereotype="extend")),
    (rel("association", "고객", "sys", stereotype="include"),
     "액터와 유즈케이스는 stereotype 없는 연관으로 잇는다. 시스템 경계 쪽 끝을 그 액터가 쓰는 유즈케이스로 고치고 stereotype을 뺀다",
     rel("association", "고객", "주문한다")),
])
def test_include_touching_a_system_is_fixed_by_the_kind_of_the_other_end(relation, fix, fixed):
    elements = [*BASE, OUTSIDE, OTHER_SYSTEM]
    (p,) = problems([relation], elements)
    assert p.startswith("relations[0].stereotype: ") and p.endswith(f") — {fix}")
    reads([fixed], elements)


def test_include_extend_and_other_stereotypes_read_where_they_belong():
    reads([rel("dependency", "주문한다", "결제한다", stereotype="include"),
           rel("dependency", "결제한다", "주문한다", stereotype="extend"),
           rel("association", "고객", "주문한다", stereotype="communicate"),
           rel("dependency", "고객", "sys", stereotype="use"),
           rel("generalization", "은행", "고객", stereotype="human")])


# ---------------------------------------------------------------- 도구 설명과 서버


def test_tool_description_states_the_rules():
    for line in ["  - in: 이 요소를 품은 시스템 경계의 열쇠. \"요소 안에 요소 두기(중첩)\" 절. 규칙: 액터는 시스템 밖의 사람이나 외부 "
                 "시스템이라 시스템 경계 안에 두면(in) 입력 오류다.",
                 "  - 규칙: 연관은 액터와 유즈케이스 사이에 긋는다. 시스템 경계에 닿는 연관, 액터끼리 잇는 연관, 같은 시스템 경계 안이거나 "
                 "둘 다 경계 밖인 유즈케이스끼리 잇는 연관은 입력 오류다(서로 다른 시스템 경계의 유즈케이스끼리는 받는다).",
                 "  - 규칙: 일반화는 액터끼리, 유즈케이스끼리 긋는다. 종류가 다른 일반화, 시스템 경계가 끝인 일반화, 고리를 이루는 "
                 "일반화(A의 부모가 B이고 B의 부모가 다시 A인 것 — 여러 단계도)는 입력 오류다.",
                 '  - 규칙: stereotype이 "include"·"extend"인 관계(«include»·«extend»)는 유즈케이스 사이의 dependency여야 한다 — '
                 "다른 관계에 달면 입력 오류다. 다른 스테레오타입은 어느 관계에든 단다. 자기 자신을 포함하는 «include»와 고리를 이루는 "
                 "«include»(A가 B를, B가 다시 A를 포함하는 것 — 여러 단계도)도 입력 오류다."]:
        assert line in U.TOOL.splitlines(), line
    assert "자기 자신으로 가는 관계는 꺾는 점이 둘 이상 있어야 한다(일반화는 꺾는 점이 있어도 자기 자신으로 갈 수 없다)." in U.TOOL
    # 규칙은 in만 본다 — 자리(경계 밖)는 배치 요령이 말한다
    assert "- 액터는 시스템 경계의 왼쪽과 오른쪽 밖에 두고, 이름은" in U.TIPS


def test_server_returns_rule_errors_as_input_errors(tmp_path):
    async def go():
        async with Client(server.mcp) as c:
            return await c.call_tool("draw_use_case_diagram", {
                "file_name": "bad", "out_dir": str(tmp_path), "elements": ACTOR_INSIDE,
                "relations": [rel("association", "고객", "주문한다")]})
    result = anyio.run(go)
    assert result.is_error and not (tmp_path / "bad.png").exists()
    assert result.content[0].text == f"입력 오류 — 1건\n- {ISSUE_CASES[0][2]}"


def test_the_drawing_and_check_of_inputs_that_keep_the_rules_are_as_before():
    r = boxcheck.check(U.render({"elements": BASE, "relations": [rel("association", "고객", "주문한다"),
                                                                 rel("dependency", "주문한다", "결제한다", stereotype="include"),
                                                                 rel("association", "결제한다", "은행")]}))
    assert r.notices == () and "표기 규칙" not in r.summary()


# ---------------------------------------------------------------- 고치는 법을 모두 따르면 읽힌다


def _random_input(rng):
    elements = [SYSTEM, el("system", "결제 시스템", 900, 0, id="pay")]
    elements += [inside(rng.choice(["sys", "pay"]), "use_case", f"U{i}", 0, 0) for i in range(rng.randint(2, 5))]
    elements += [el("use_case", f"O{i}", 0, 0) for i in range(rng.randint(0, 2))]
    elements += [el("actor", f"A{i}", 0, 0) for i in range(rng.randint(1, 4))]
    keys = {e.get("id", e["name"]): e for e in elements}
    relations = []
    for _ in range(rng.randint(1, 8)):
        a, b = rng.sample(list(keys), 2)
        if keys[a].get("in") == b or keys[b].get("in") == a:  # 품은 경계와 그 안의 유즈케이스는 엔진이 막는다
            continue
        r = rel(rng.choice(["association", "dependency", "generalization"]), a, b)
        if (st := rng.choice([None, None, "include", "extend", "Include", "trace"])) is not None:
            r["stereotype"] = st
        relations.append(r)
    return elements, relations


def test_following_the_first_fix_of_every_error_reads(monkeypatch):
    """오류마다 고치는 법이 먼저 권한 관계로 바꾸고(권한 것이 없으면 지우고) 다시 읽으면 오류가 없다 — 앞 오류의 고치는 법이 만들
    관계와 겹치거나 고리를 이루는 것은 권하지 않기 때문이다. 처음부터 고리가 있는 입력은 뺀다(그 고치는 법은 사람이 고른다)."""
    offered: dict[str, tuple] = {}
    add = U._Plan.add

    def logged(self, edge, origin=None):
        if origin is not None:
            offered.setdefault(origin, edge)
        add(self, edge, origin)

    monkeypatch.setattr(U._Plan, "add", logged)
    rng, checked = random.Random(42), 0
    for _ in range(600):
        elements, relations = _random_input(rng)
        offered.clear()
        try:
            U.parse({"elements": elements, "relations": relations})
            continue
        except InputError as e:
            found = e.problems
        if any("고리를 이룬다" in p or "자기 자신을 포함할 수 없다" in p for p in found):
            continue
        bad = {int(p.split("]")[0].split("[")[1]) for p in found}
        fixed = [r for i, r in enumerate(relations) if i not in bad]
        same = [U._same((r["kind"], r["from"], r["to"], r.get("stereotype", "").casefold() or None)) for r in fixed]
        for path, edge in offered.items():
            assert U._same(edge) not in same, (relations, path)  # 같은 관계가 둘이면 선이 포개진다
            same.append(U._same(edge))
            kind, a, b, stereotype = edge
            fixed.append(rel(kind, a, b, **({"stereotype": stereotype} if stereotype else {})))
        U.parse({"elements": elements, "relations": fixed})
        checked += 1
    assert checked > 200
