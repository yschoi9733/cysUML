"""유즈케이스도의 표기 규칙(usecasediagram.RULES): 액터는 시스템 경계 밖, 연관은 액터와 유즈케이스 사이, 일반화는 같은 종류끼리
고리 없이, «include»·«extend»는 유즈케이스 사이의 의존에만. 모두 입력 오류다."""
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
     "유즈케이스끼리 긋는다. 액터가 유즈케이스를 쓰는 것이면 kind를 'association'으로 바꾼다",
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


# ---------------------------------------------------------------- 일반화


@pytest.mark.parametrize("source, target", [("고객", "sys"), ("sys", "은행")])
def test_a_system_is_never_an_end_of_a_generalization(source, target):
    assert problems([rel("generalization", source, target)]) == (
        "relations[0]: 시스템 경계('sys')는 일반화의 끝이 될 수 없다 — 일반화는 액터끼리, 유즈케이스끼리 긋는다. from·to를 "
        "액터나 유즈케이스로 고친다",)


def test_generalization_between_systems_is_an_input_error():
    other = el("system", "결제 시스템", 700, 0, id="pay")
    (p,) = problems([rel("generalization", "pay", "sys")], [*BASE, other])
    assert p.startswith("relations[0]: 시스템 경계('pay')는 일반화의 끝이 될 수 없다")


def test_generalization_between_an_actor_and_a_use_case_already_joined_says_to_delete_it():
    assert problems([rel("association", "주문한다", "고객"), rel("generalization", "주문한다", "고객")]) == (
        "relations[1]: 일반화의 두 끝 종류가 다르다(from '주문한다': 'use_case', to '고객': 'actor') — 일반화는 액터끼리, "
        "유즈케이스끼리 긋는다. 두 끝을 잇는 association이 이미 있다. 이 일반화를 지운다",)


def test_generalization_to_itself_is_refused_even_with_bend_points():
    assert problems([rel("generalization", "고객", "고객", via=LOOP)]) == (
        "relations[0]: 일반화는 자기 자신으로 갈 수 없다 — from과 to를 다른 요소로 고친다",)


def test_generalization_loops_are_told_once_per_loop():
    assert problems([rel("generalization", "고객", "은행"), rel("generalization", "은행", "고객")]) == (
        "relations[0]: 일반화가 고리를 이룬다('고객' → '은행' → '고객') — 조상이 다시 자식이 될 수 없다. 고리 안의 일반화 하나를 "
        "지우거나 from·to를 바꾼다",)
    three = [*BASE, inside("sys", "use_case", "환불한다", 480, 160)]
    (p,) = problems([rel("generalization", "주문한다", "결제한다"), rel("generalization", "결제한다", "환불한다"),
                     rel("generalization", "환불한다", "주문한다")], three)
    assert p.startswith("relations[0]: 일반화가 고리를 이룬다('주문한다' → '결제한다' → '환불한다' → '주문한다')")


def test_generalization_between_actors_or_between_use_cases_reads():
    reads([rel("generalization", "은행", "고객"), rel("generalization", "결제한다", "주문한다")])


# ---------------------------------------------------------------- 연관


def test_association_touching_a_system_names_the_system_ends():
    other = el("system", "결제 시스템", 700, 0, id="pay")
    assert problems([rel("association", "sys", "pay")], [*BASE, other]) == (
        "relations[0]: 연관이 시스템 경계에 닿는다(from 'sys': 'system', to 'pay': 'system') — 연관은 액터와 유즈케이스 사이에 "
        "긋는다. from·to를 액터와 유즈케이스로 고친다",)
    outside = el("use_case", "문의한다", 0, 300)
    (p,) = problems([rel("association", "문의한다", "sys")], [*BASE, outside])
    assert p.endswith("시스템 경계 쪽 끝을 그 유즈케이스를 쓰는 액터로 고친다")


@pytest.mark.parametrize("relations, fix", [
    ([rel("association", "고객", "은행")],
     "한 액터가 다른 액터의 한 종류면 kind를 'generalization'으로 바꾸고(from이 자식), 아니면 이 연관을 지운다"),
    ([rel("generalization", "고객", "은행"), rel("association", "은행", "고객")],
     "두 액터는 이미 일반화로 이어져 있다('고객' → '은행'). 이 연관을 지운다"),
    ([rel("association", "고객", "고객", via=LOOP)], "자기 자신과 잇는 연관은 지운다"),
])
def test_association_between_actors_is_an_input_error(relations, fix):
    (p,) = problems(relations)
    i = len(relations) - 1
    a, b = relations[-1]["from"], relations[-1]["to"]
    assert p == (f"relations[{i}]: 액터끼리 잇는 연관이다(from '{a}': 'actor', to '{b}': 'actor') — 액터는 유즈케이스와 연관으로 "
                 f"잇는다. {fix}")


def test_association_between_use_cases_of_one_subject_is_an_input_error():
    assert problems([rel("association", "주문한다", "결제한다")]) == (
        "relations[0]: 같은 시스템 경계('sys') 안의 유즈케이스끼리 잇는 연관이다(from '주문한다': 'use_case', to '결제한다': "
        f"'use_case') — {SAME_SYSTEM}. 포함·확장이면 kind를 'dependency'로 바꾸고 stereotype 'include'나 'extend'를 단다",)
    bare = [el("use_case", "A", 0, 0), el("use_case", "B", 300, 0)]
    (p,) = problems([rel("association", "A", "B")], bare)
    assert p.startswith("relations[0]: 시스템 경계 밖의 유즈케이스끼리 잇는 연관이다")
    reads([rel("dependency", "A", "B", stereotype="extend")], bare)


@pytest.mark.parametrize("other", [rel("dependency", "결제한다", "주문한다"), rel("generalization", "주문한다", "결제한다")])
def test_association_between_use_cases_already_joined_says_to_delete_it(other):
    (p,) = problems([other, rel("association", "주문한다", "결제한다")])
    assert p.endswith(f"{SAME_SYSTEM}. 두 유즈케이스는 이미 다른 관계로 이어져 있다. 이 연관을 지운다")


def test_association_between_use_cases_of_different_subjects_reads():
    # 서로 다른 시스템 경계 안이거나, 하나만 경계 안이면 주체가 다르다
    other = [el("system", "결제 시스템", 700, 0, id="pay"), inside("pay", "use_case", "승인한다", 740, 60),
             el("use_case", "문의한다", 0, 300)]
    reads([rel("association", "결제한다", "승인한다"), rel("association", "문의한다", "주문한다")], [*BASE, *other])


def test_association_between_an_actor_and_a_use_case_reads_both_ways():
    reads([rel("association", "고객", "주문한다"), rel("association", "결제한다", "은행", navigable="to")])


# ---------------------------------------------------------------- «include»·«extend»


@pytest.mark.parametrize("relations, fix", [
    ([rel("generalization", "주문한다", "결제한다", stereotype="extend")],
     "포함·확장이면 kind를 'dependency'로 바꾸고, 일반화를 뜻했으면 stereotype을 뺀다"),
    # 일반화로 두면 고리가 된다
    ([rel("generalization", "결제한다", "주문한다"), rel("generalization", "주문한다", "결제한다", stereotype="extend")],
     "kind를 'dependency'로 바꾼다"),
    ([rel("dependency", "주문한다", "결제한다"), rel("association", "주문한다", "결제한다", stereotype="include")],
     "같은 from·to의 dependency가 이미 있다. 이 관계를 지운다"),
    ([rel("association", "고객", "주문한다", stereotype="Include")],
     "액터와 유즈케이스는 stereotype 없는 연관으로 잇는다. stereotype을 뺀다"),
    ([rel("association", "고객", "주문한다"), rel("dependency", "고객", "주문한다", stereotype="include")],
     "두 끝을 잇는 association이 이미 있다. 이 관계를 지운다"),
    ([rel("dependency", "고객", "sys", stereotype="include")], "시스템 경계 쪽 끝을 유즈케이스로 고친다"),
    ([rel("association", "고객", "sys", stereotype="extend")], "시스템 경계 쪽 끝을 유즈케이스로 고친다"),
    ([rel("generalization", "고객", "은행", stereotype="include")], "액터 사이 일반화를 뜻했으면 stereotype을 뺀다"),
    ([rel("generalization", "은행", "고객"), rel("generalization", "고객", "은행", stereotype="include")],
     "두 액터는 이미 일반화로 이어져 있다('은행' → '고객'). 이 관계를 지운다"),
    ([rel("dependency", "고객", "은행", stereotype="include")],
     "액터끼리는 일반화만 긋는다. 한 액터가 다른 액터의 한 종류면 stereotype을 빼고 kind를 'generalization'으로 바꾸고(from이 "
     "자식), 아니면 이 관계를 지운다"),
])
def test_include_and_extend_off_a_dependency_between_use_cases_is_one_input_error(relations, fix):
    (p,) = problems(relations)  # 관계 하나에는 오류 하나 — 시스템 경계에 닿는 연관도 «include»·«extend» 오류만 낸다
    i = len(relations) - 1
    assert p.startswith(f"relations[{i}].stereotype: {INCLUDE_ONLY}(이 관계는 {relations[-1]['kind']!r}, ")
    assert p.endswith(f") — {fix}")


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
                 "다른 관계에 달면 입력 오류다. 다른 스테레오타입은 어느 관계에든 단다."]:
        assert line in U.TOOL.splitlines(), line
    assert "자기 자신으로 가는 관계는 꺾는 점이 둘 이상 있어야 한다(일반화는 꺾는 점이 있어도 자기 자신으로 갈 수 없다)." in U.TOOL
    # 액터를 경계 밖에 두는 것은 규칙이 되었으니 배치 요령에는 왼쪽·오른쪽만 남는다
    assert "- 액터는 시스템 경계의 왼쪽과 오른쪽에 두고, 이름은" in U.TIPS and "오른쪽 밖에" not in U.TIPS


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
