"""클래스도 관계 여섯 가지의 표기 규칙(classdiagram.RULES): 상속은 같은 종류끼리, 고리·자기 자신 금지, 인터페이스가 아닌 것으로
가는 실체화는 알림. 이 관계를 받는 패키지도·컴포넌트도·배치도(deployment diagram)도 같은 규칙을 쓴다."""
import json
import re

import anyio
import pytest
from mcp import Client

from cysuml import activitydiagram, boxcheck, classcheck
from cysuml import classdiagram as C
from cysuml import componentdiagram as CD
from cysuml import deploymentdiagram as D
from cysuml import packagediagram as P
from cysuml import server, statediagram, usecasediagram
from cysuml.parsing import InputError

ROW = [{"name": "A", "left": 0, "top": 0}, {"name": "B", "left": 300, "top": 0}, {"name": "C", "left": 600, "top": 0}]
SELF_FIX = "from과 to를 다른 상자로 고친다"
NOTICE_HEAD = "알림 — 표기 규칙 {}건(불합격은 아니다 — 뜻한 대로면 그대로 둔다)"


def box(name, left, top=0, kind="class"):
    return {"name": name, "left": left, "top": top, "kind": kind}


def el(kind, name, left, top=0, **more):
    return {"kind": kind, "name": name, "left": left, "top": top, **more}


def rel(kind, source, target, **more):
    return {"kind": kind, "from": source, "to": target, **more}


def class_problems(classes, relations):
    with pytest.raises(InputError) as e:
        C.parse({"classes": classes, "relations": relations})
    return e.value.problems


def class_report(classes, relations):
    return classcheck.check(C.render({"classes": classes, "relations": relations}))


def problems(module, elements, relations):
    with pytest.raises(InputError) as e:
        module.parse({"elements": elements, "relations": relations})
    return e.value.problems


def report(module, elements, relations):
    return boxcheck.check(module.render({"elements": elements, "relations": relations}))


# ---------------------------------------------------------------- 상속의 두 끝


@pytest.mark.parametrize("source, target", [("class", "class"), ("abstract", "class"), ("class", "abstract"),
                                            ("interface", "interface"), ("enum", "enum")])
def test_inheritance_between_the_same_kind_reads_and_checks_as_before(source, target):
    r = class_report([box("A", 0, kind=source), box("B", 300, kind=target)], [rel("generalization", "A", "B")])
    assert r.passed and r.notices == () and "표기 규칙" not in r.summary(), r.summary()


def test_class_inheriting_an_interface_is_an_input_error_that_points_to_realization():
    (p,) = class_problems([box("Circle", 0), box("Shape", 300, kind="interface")], [rel("generalization", "Circle", "Shape")])
    assert p == ("relations[0]: 상속의 두 끝 종류가 다르다(from 'Circle': 'class', to 'Shape': 'interface') — 상속은 같은 "
                 "종류끼리 긋는다(class와 abstract는 같은 종류로 친다). 인터페이스를 구현하는 것이면 kind를 'realization'으로 바꾼다")


@pytest.mark.parametrize("source, target, tail", [
    ("class", "enum", "from·to나 요소의 kind를 고친다"), ("enum", "abstract", "from·to나 요소의 kind를 고친다"),
    # 인터페이스 -> 클래스·열거형은 실체화를 거꾸로 적었을 수 있다(바꾸면 알림 없이 받아진다)
    ("interface", "class", "방향이 거꾸로인 실체화를 뜻했으면 from과 to를 바꾸고 kind를 'realization'으로 바꾼다"),
    ("interface", "enum", "방향이 거꾸로인 실체화를 뜻했으면 from과 to를 바꾸고 kind를 'realization'으로 바꾼다"),
])
def test_inheritance_between_different_kinds_is_an_input_error(source, target, tail):
    (p,) = class_problems([box("A", 0, kind=source), box("B", 300, kind=target)], [rel("generalization", "A", "B")])
    assert p.startswith(f"relations[0]: 상속의 두 끝 종류가 다르다(from 'A': {source!r}, to 'B': {target!r})")
    assert p.endswith(f"상속은 같은 종류끼리 긋는다(class와 abstract는 같은 종류로 친다). {tail}")
    swapped = class_report([box("A", 0, kind=source), box("B", 300, kind=target)], [rel("realization", "B", "A")])
    assert (swapped.notices == ()) == tail.startswith("방향이 거꾸로")


def test_names_never_take_a_particle_whose_form_depends_on_their_last_sound():
    # 영어 이름은 받침을 알 수 없어(Circle은, Shape는) 이름 바로 뒤에 은·는·이·가·을·를을 붙이지 않는다
    classes = [box("Circle", 0), box("Shape", 300), box("Shape2", 600, kind="interface")]
    (p,) = class_problems(classes, [rel("generalization", "Circle", "Shape2")])
    (n,) = class_report(classes[:2], [rel("realization", "Circle", "Shape")]).notices
    for text in (p, n.problem, n.hint):
        assert not any(f"'{name}'{j}" in text for name in ("Circle", "Shape", "Shape2") for j in "은는이가을를")


def test_the_issue_example_now_reports_the_interface_inheriting_a_class():
    # 인터페이스 Shape, 클래스 Circle·Canvas에 Shape -> Circle 상속, Circle -> Shape 실체화, Canvas -> Circle 실체화
    classes = [box("Shape", 150, 0, kind="interface"), box("Circle", 0, 150), box("Canvas", 300, 150)]
    (p,) = class_problems(classes, [rel("generalization", "Shape", "Circle"), rel("realization", "Circle", "Shape"),
                                    rel("realization", "Canvas", "Circle")])
    assert p.startswith("relations[0]: 상속의 두 끝 종류가 다르다(from 'Shape': 'interface', to 'Circle': 'class')")


# ---------------------------------------------------------------- 자기 자신, 고리


@pytest.mark.parametrize("kind, label", [("generalization", "상속은"), ("realization", "실체화는")])
@pytest.mark.parametrize("via", [None, [[200, -60], [45, -60], [-60, 24]]])
def test_inheritance_or_realization_to_itself_is_one_input_error(kind, label, via):
    # 꺾는 점이 모자라도 "꺾는 점이 둘 이상" 오류를 함께 내지 않는다 — 꺾는 점을 더해도 그릴 수 없는 관계라서
    more = {} if via is None else {"via": via}
    assert class_problems([box("A", 0)], [rel(kind, "A", "A", **more)]) == (
        f"relations[0]: {label} 자기 자신으로 갈 수 없다 — {SELF_FIX}",)


def test_other_relations_to_itself_still_need_two_bends_and_then_draw():
    (p,) = class_problems([box("A", 0)], [rel("dependency", "A", "A")])
    assert "꺾는 점(via)이 둘 이상 있어야" in p
    r = class_report([box("A", 0)], [rel("dependency", "A", "A", via=[[45, -60], [-60, -60], [-60, 24]])])
    assert r.notices == ()


def test_two_classes_inheriting_each_other_are_one_cycle_at_the_first_relation():
    assert class_problems(ROW[:2], [rel("generalization", "A", "B"), rel("generalization", "B", "A")]) == (
        "relations[0]: 상속이 고리를 이룬다('A' → 'B' → 'A') — 조상을 다시 상속할 수 없다. 고리 안의 상속 하나를 지우거나 "
        "from·to를 바꾼다",)


def test_a_longer_cycle_names_every_class_on_it():
    (p,) = class_problems(ROW, [rel("association", "A", "C"), rel("generalization", "A", "B"),
                                rel("generalization", "B", "C"), rel("generalization", "C", "A")])
    assert p.startswith("relations[1]: 상속이 고리를 이룬다('A' → 'B' → 'C' → 'A')")


def test_cycles_sharing_classes_are_each_reported_once_by_their_relations():
    # 세 클래스가 서로 상속한다 — 상속마다 가장 짧은 고리(두 클래스끼리)를 찾고, 같은 상속들로 된 고리는 한 번만 알린다
    found = class_problems(ROW, [rel("generalization", "A", "B"), rel("generalization", "B", "C"),
                                 rel("generalization", "C", "A"), rel("generalization", "A", "C"),
                                 rel("generalization", "C", "B"), rel("generalization", "B", "A")])
    assert [p.split(" — ")[0] for p in found] == [
        "relations[0]: 상속이 고리를 이룬다('A' → 'B' → 'A')", "relations[1]: 상속이 고리를 이룬다('B' → 'C' → 'B')",
        "relations[2]: 상속이 고리를 이룬다('C' → 'A' → 'C')"]


def test_each_separate_cycle_is_reported():
    classes = ROW + [box("D", 900)]
    found = class_problems(classes, [rel("generalization", "A", "B"), rel("generalization", "B", "A"),
                                     rel("generalization", "C", "D"), rel("generalization", "D", "C")])
    assert [p.split(":")[0] for p in found] == ["relations[0]", "relations[2]"]


def test_multiple_inheritance_and_repeated_lines_are_not_cycles():
    classes = [box("A", 150, 0), box("B", 0, 150), box("C", 300, 150), box("E", 150, 300)]
    d = C.parse({"classes": classes, "relations": [
        rel("generalization", "B", "A"), rel("generalization", "C", "A"), rel("generalization", "E", "B"),
        rel("generalization", "E", "C"), rel("generalization", "B", "A")]})
    assert len(d.relations) == 5 and d.notices == ()


def test_a_wrong_inheritance_is_not_counted_again_in_a_cycle():
    found = class_problems([box("A", 0), box("I", 300, kind="interface")],
                           [rel("generalization", "A", "I"), rel("generalization", "I", "A")])
    assert len(found) == 2 and all("상속의 두 끝 종류가 다르다" in p for p in found)


def test_rule_errors_come_together_with_the_other_input_errors():
    found = class_problems(ROW, [rel("generalization", "A", "B"), rel("generalization", "B", "A"),
                                 rel("dependency", "A", "C", navigable="to")])
    assert [p.split(":")[0] for p in found] == ["relations[2].navigable", "relations[0]"]


# ---------------------------------------------------------------- 실체화 알림


def test_realization_to_a_class_draws_and_passes_with_a_notice():
    r = class_report([box("Circle", 0), box("Shape", 300)], [rel("realization", "Circle", "Shape")])
    assert r.passed
    (n,) = r.notices
    assert n.path == "relations[0]" and n.elements == ("Circle", "Shape")
    assert n.problem == "실체화가 가는 쪽이 인터페이스가 아니다(to 'Shape': 'class')."
    assert n.hint == "상속을 뜻했으면 kind를 'generalization'으로 바꾸고, 인터페이스를 구현하는 것이면 to를 인터페이스로 고친다."
    lines = r.summary().splitlines()
    assert lines[0].startswith("합격")
    assert lines[1:3] == [NOTICE_HEAD.format(1), f"- relations[0]: {n.problem} {n.hint}"]
    assert lines[3].startswith("알림 — 선끼리 엇갈린 곳 0곳")
    data = json.loads(json.dumps(r.to_dict(), ensure_ascii=False))
    assert data["notices"] == [{"path": "relations[0]", "elements": ["Circle", "Shape"], "problem": n.problem,
                                "hint": n.hint}]


def test_realization_between_inheritable_kinds_asks_about_inheritance():
    r = class_report([box("A", 0), box("B", 300, kind="abstract")], [rel("realization", "A", "B")])
    (n,) = r.notices
    assert "(to 'B': 'abstract')" in n.problem and n.hint.startswith("상속을 뜻했으면 kind를 'generalization'으로 바꾸고")


def test_realization_hint_never_leads_to_an_input_error():
    # class -> enum은 상속으로 바꾸면 종류가 다른 상속 오류라, 상속을 권하지 않고 실체화를 긋는 자리를 알린다
    r = class_report([box("A", 0), box("B", 300, kind="enum")], [rel("realization", "A", "B")])
    (n,) = r.notices
    assert n.hint == "실체화는 인터페이스를 구현하는 쪽에서 인터페이스로 긋는다 — 다른 뜻이면 dependency를 쓴다."
    assert "generalization" not in n.hint


def test_realization_made_by_an_interface_has_a_notice_from_its_source():
    same = class_report([box("I", 0, kind="interface"), box("J", 300, kind="interface")], [rel("realization", "I", "J")])
    (n,) = same.notices
    assert n.problem == "실체화를 하는 쪽이 인터페이스다(from 'I': 'interface')."
    assert n.hint == "인터페이스끼리는 kind를 'generalization'으로 바꾼다."
    turned = class_report([box("Shape", 0, kind="interface"), box("Circle", 300)], [rel("realization", "Shape", "Circle")])
    (n,) = turned.notices
    assert n.problem.startswith("실체화를 하는 쪽이 인터페이스다(from 'Shape'")
    assert n.hint.endswith("— 방향이 거꾸로면 from과 to를 바꾼다.")


def test_realization_to_an_interface_has_no_notice():
    r = class_report([box("Circle", 0), box("Shape", 300, kind="interface")], [rel("realization", "Circle", "Shape")])
    assert r.passed and r.notices == () and r.to_dict()["notices"] == []
    assert r.summary().splitlines()[1].startswith("알림 — 선끼리 엇갈린 곳")


def test_notices_come_only_after_the_input_is_right():
    # 오류가 있으면 그리지 않으므로 알림도 없다 — 오류만 돌려준다
    found = class_problems(ROW, [rel("realization", "A", "B"), rel("generalization", "B", "B")])
    assert found == (f"relations[1]: 상속은 자기 자신으로 갈 수 없다 — {SELF_FIX}",)


# ---------------------------------------------------------------- 클래스 관계를 받는 다른 도구


def test_every_tool_that_takes_the_class_relations_checks_their_rules():
    modules = [C, P, CD, D, usecasediagram, statediagram, activitydiagram]
    takers = [m for m in modules if m.SPEC.relations.get("generalization") is C.RELATIONS["generalization"]]
    assert takers == [C, P, CD, D] and all(m.SPEC.rules is C.RULES for m in takers)


@pytest.mark.parametrize("module", [P, D])
@pytest.mark.parametrize("kind", ["component", "artifact", "node"])
def test_inheritance_between_components_artifacts_or_nodes_of_one_kind_reads(module, kind):
    d = module.parse({"elements": [el(kind, "a", 0), el(kind, "b", 400)], "relations": [rel("generalization", "a", "b")]})
    assert len(d.relations) == 1 and d.notices == ()


@pytest.mark.parametrize("source, target", [("class", "component"), ("component", "node"), ("artifact", "class")])
def test_inheritance_across_element_kinds_is_an_input_error(source, target):
    (p,) = problems(P, [el(source, "a", 0), el(target, "b", 400)], [rel("generalization", "a", "b")])
    assert p.startswith(f"relations[0]: 상속의 두 끝 종류가 다르다(from 'a': {source!r}, to 'b': {target!r})")


def test_inheritance_into_a_component_points_to_realization():
    (p,) = problems(CD, [el("class", "Impl", 0, 200), el("component", "Api", 0)], [rel("generalization", "Impl", "Api")])
    assert p.endswith(". 클래스가 컴포넌트를 실현하는 것이면 kind를 'realization'으로 바꾼다")


@pytest.mark.parametrize("source, target, problem", [
    ("lollipop", "class", "실체화를 하는 쪽이 인터페이스다(from 'a': 'lollipop')."),
    ("package", "interface", "패키지('a')는 실체화하지 않는다."),
])
def test_realization_made_by_a_ball_or_a_package_has_a_notice(source, target, problem):
    r = report(CD, [el(source, "a", 0), el(target, "b", 300)], [rel("realization", "a", "b")])
    (n,) = r.notices
    assert n.problem == problem


@pytest.mark.parametrize("source", ["artifact", "node", "enum", "component"])
def test_only_classes_realize_components_quietly(source):
    # 아티팩트는 «manifest» 의존으로 컴포넌트를 구현한다 — 클래스·추상 클래스 밖의 실체화는 알리고, 그 상속 오류도 실체화를 권하지 않는다
    elements = [el(source, "a", 0, 250), el("component", "c", 0)]
    (n,) = report(P, elements, [rel("realization", "a", "c")]).notices
    assert n.problem == "실체화가 가는 쪽이 인터페이스가 아니다(to 'c': 'component')."
    if source != "component":
        (p,) = problems(P, elements, [rel("generalization", "a", "c")])
        assert p.endswith("from·to나 요소의 kind를 고친다")
    assert report(P, [el("abstract", "a", 0, 250), el("component", "c", 0)], [rel("realization", "a", "c")]).notices == ()


def test_inheritance_hint_is_left_out_when_inheriting_would_close_a_cycle():
    # B가 이미 A를 상속하는데 A -> B 실체화를 상속으로 바꾸면 고리 오류가 난다 — 그 말 대신 실체화를 지우라고 한다
    (n,) = class_report([box("A", 0), box("B", 300)], [rel("generalization", "B", "A"),
                                                        rel("realization", "A", "B", via=[[45, -60], [345, -60]])]).notices
    assert n.hint == ("to('B')가 이미 from('A')을 상속해 generalization으로 바꾸면 고리가 된다 — 인터페이스를 구현하는 것이면 to를 "
                      "인터페이스로 고치고, 아니면 이 실체화를 지운다.")
    (n,) = class_report([box("I", 0, kind="interface"), box("J", 300, kind="interface")],
                        [rel("generalization", "J", "I"), rel("realization", "I", "J", via=[[45, -60], [345, -60]])]).notices
    assert n.hint == "to('J')가 이미 from('I')을 상속해 generalization으로 바꾸면 고리가 된다 — 이 실체화를 지운다."


def test_inheritance_hint_is_left_out_when_the_same_inheritance_already_exists():
    # 같은 from·to의 상속이 이미 있으면 실체화를 상속으로 바꾸라고 하지 않는다(두 선이 겹쳐 그려진다)
    (n,) = class_report([box("A", 0), box("B", 300)], [rel("generalization", "A", "B"),
                                                        rel("realization", "A", "B", via=[[45, -60], [345, -60]])]).notices
    assert n.hint.startswith("같은 from·to의 generalization이 이미 있다 — ") and n.hint.endswith("이 실체화를 지운다.")


def test_realization_hint_in_tools_with_components_names_component_realization():
    r = report(D, [el("class", "Impl", 0, 250), el("node", "x", 0)], [rel("realization", "Impl", "x")])
    (n,) = r.notices
    assert n.hint == ("실체화는 인터페이스를 구현하는 쪽에서 인터페이스로, 클래스에서 그 클래스가 실현하는 컴포넌트로 긋는다 — "
                      "다른 뜻이면 dependency를 쓴다.")


@pytest.mark.parametrize("module", [P, CD, D])
@pytest.mark.parametrize("source, target, end", [("package", "package", "a"), ("class", "package", "b"),
                                                 ("package", "class", "a")])
def test_packages_are_never_an_end_of_inheritance(module, source, target, end):
    assert problems(module, [el(source, "a", 0), el(target, "b", 0, 200)], [rel("generalization", "a", "b")]) == (
        f"relations[0]: 패키지({end!r})는 상속의 끝이 될 수 없다 — 패키지가 끝인 관계는 dependency로 긋는다(패키지 사이 "
        "«import» 등은 stereotype으로 단다)",)


@pytest.mark.parametrize("source, target, end", [("lollipop", "lollipop", "a"), ("interface", "lollipop", "b"),
                                                 ("lollipop", "class", "a")])
def test_provided_interface_balls_are_never_an_end_of_inheritance(source, target, end):
    assert problems(CD, [el(source, "a", 0), el(target, "b", 300)], [rel("generalization", "a", "b")]) == (
        f"relations[0]: 제공 인터페이스 원({end!r})은 상속의 끝이 될 수 없다 — 인터페이스 사이 상속은 kind 'interface' 상자끼리 "
        "긋는다",)


@pytest.mark.parametrize("source", ["class", "component"])
def test_inheritance_into_a_ball_points_to_realization_which_then_passes_quietly(source):
    elements = [el(source, "Impl", 250), el("lollipop", "Api", 0)]
    (p,) = problems(CD, elements, [rel("generalization", "Impl", "Api")])
    assert p.endswith("상속의 끝이 될 수 없다 — 인터페이스를 구현하는 것이면 kind를 'realization'으로 바꾼다")
    r = report(CD, elements, [rel("realization", "Impl", "Api")])
    assert r.passed and r.notices == (), r.summary()


def test_a_reversed_class_realization_hint_says_to_swap_the_ends():
    # 컴포넌트 -> 클래스 실체화는 방향만 거꾸로다(클래스가 컴포넌트를 실현) — 의존으로 바꾸라고 하기 전에 방향을 바꾸라고 한다
    (n,) = report(CD, [el("component", "K", 0), el("class", "X", 0, 200)], [rel("realization", "K", "X")]).notices
    assert n.hint.endswith("방향이 거꾸로면 from과 to를 바꾼다.")


@pytest.mark.parametrize("target", ["package", "lollipop", "interface"])
def test_interface_realization_hint_swaps_ends_only_when_the_swap_passes(target):
    # 인터페이스 -> 클래스는 방향만 거꾸로다. 인터페이스 -> 패키지·원·인터페이스는 바꿔도 다시 걸리므로 바꾸라고 하지 않는다
    swapped = report(CD, [el("interface", "I", 0), el("class", "C", 300)], [rel("realization", "I", "C")]).notices[0]
    assert swapped.hint.endswith("방향이 거꾸로면 from과 to를 바꾼다.")
    (n,) = report(CD, [el("lollipop", "I", 0), el(target, "X", 300)], [rel("realization", "I", "X")]).notices
    assert "from과 to를 바꾼다" not in n.hint and n.hint.endswith("다른 뜻이면 dependency를 쓴다.")


@pytest.mark.parametrize("target", ["component", "lollipop", "interface"])
def test_realization_to_a_component_or_an_interface_has_no_notice(target):
    # 클래스가 컴포넌트를 실현하는 것은 컴포넌트도 배치 요령이 권하는 맞는 쓰임이다
    r = report(CD, [el("class", "Impl", 250, 0), el(target, "Api", 0)], [rel("realization", "Impl", "Api")])
    assert r.passed and r.notices == (), r.summary()


@pytest.mark.parametrize("module, target", [(P, "package"), (D, "artifact"), (D, "node")])
def test_realization_to_a_package_artifact_or_node_draws_with_a_notice(module, target):
    r = report(module, [el("class", "Impl", 0, 250), el(target, "x", 0)], [rel("realization", "Impl", "x")])
    (n,) = r.notices
    assert n.problem == f"실체화가 가는 쪽이 인터페이스가 아니다(to 'x': {target!r})."
    assert n.hint.endswith("— 다른 뜻이면 dependency를 쓴다.") and "generalization" not in n.hint
    assert NOTICE_HEAD.format(1) in r.summary()


def test_cycles_are_checked_in_the_other_tools_too():
    (p,) = problems(D, [el("node", "a", 0), el("node", "b", 400)],
                    [rel("generalization", "a", "b"), rel("generalization", "b", "a")])
    assert p.startswith("relations[0]: 상속이 고리를 이룬다('a' → 'b' → 'a')")


def test_self_inheritance_names_the_element_word_of_the_tool():
    assert problems(P, [el("class", "a", 0)], [rel("generalization", "a", "a")]) == (
        "relations[0]: 상속은 자기 자신으로 갈 수 없다 — from과 to를 다른 요소로 고친다",)


# ---------------------------------------------------------------- 도구 설명과 서버


def test_tool_descriptions_state_the_rules_of_the_kinds_the_tool_takes():
    assert ('  - 규칙: 상속은 같은 종류끼리 긋는다("class"·"abstract"끼리, "interface"끼리, "enum"끼리). 클래스가 '
            "인터페이스를 구현하는 것은 realization이다.") in server.CLASS_TOOL
    assert ('  - 알림: 다음 실체화는 그리되 검사 결과에 알림을 준다(불합격이 아니다) — from이 "interface"인 것, to가 '
            '"interface" 밖의 종류인 것. ') in server.CLASS_TOOL
    assert ('"interface"끼리, "enum"끼리, "component"끼리, "artifact"끼리, "node"끼리). 상속의 끝이 될 수 없는 종류: '
            '"package".') in P.TOOL
    assert '상속의 끝이 될 수 없는 종류: "package"·"lollipop".' in CD.TOOL
    assert ('from이 "interface"·"lollipop"·"package" 가운데 하나인 것, to가 "interface"·"lollipop" 밖의 종류인 것(to가 '
            '"component"이고 from이 "class"·"abstract"인 것은 빼고).') in CD.TOOL
    assert ('from이 "interface"·"package" 가운데 하나인 것, to가 "interface" 밖의 종류인 것(to가 "component"이고 from이 '
            '"class"·"abstract"인 것은 빼고).') in D.TOOL
    # 따옴표 친 종류 이름 바로 뒤에 받침에 따라 갈리는 조사를 붙이지 않는다("lollipop"는은 틀린다 — 이고·인 같은 서술은 괜찮다)
    for tool in (server.CLASS_TOOL, P.TOOL, CD.TOOL, D.TOOL):
        rules = "\n".join(line for line in tool.splitlines() if line.startswith(("  - 규칙:", "  - 알림:")))
        assert not re.search(r'"(?:[은는가을를]|이 |으?로)', rules), rules
    # 흐름 안내(서버 안내문·도구 설명)도 표기 규칙 알림이 불합격이 아니라고 적는다
    assert "표기 규칙 알림(관계 규칙이 있는 도구에서 뜻을 확인해 볼 관계)" in server.INSTRUCTIONS
    # 자기 자신 금지는 관계 종류(reflexive)에서 꺾는 점 줄에 적는다
    assert ("자기 자신으로 가는 관계는 꺾는 점이 둘 이상 있어야 한다(상속·실체화는 꺾는 점이 있어도 자기 자신으로 갈 수 "
            "없다).") in server.CLASS_TOOL
    # 유즈케이스도의 일반화는 클래스도 관계가 아니라 이 규칙을 적지 않는다
    assert "  - 규칙:" not in usecasediagram.TOOL and "자기 자신으로 갈 수 없다" not in usecasediagram.TOOL


def call(name, args):
    async def go():
        async with Client(server.mcp) as c:
            return await c.call_tool(name, args)
    return anyio.run(go)


def test_server_returns_rule_errors_as_input_errors_and_notices_with_the_picture(tmp_path):
    bad = call("draw_class_diagram", {"file_name": "loop", "classes": ROW[:2], "out_dir": str(tmp_path),
                                      "relations": [rel("generalization", "A", "B"), rel("generalization", "B", "A")]})
    assert bad.is_error and bad.content[0].text.startswith("입력 오류 — 1건\n- relations[0]: 상속이 고리를 이룬다")
    assert not (tmp_path / "loop.png").exists()
    ok = call("draw_component_diagram", {"file_name": "part", "out_dir": str(tmp_path),
                                         "elements": [el("class", "Impl", 0, 250), el("node", "x", 0)],
                                         "relations": [rel("realization", "Impl", "x")]})
    assert not ok.is_error and (tmp_path / "part.png").exists()
    assert f"{NOTICE_HEAD.format(1)}\n- relations[0]: 실체화가 가는 쪽이 인터페이스가 아니다(to 'x'" in ok.content[0].text
