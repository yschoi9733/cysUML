"""클래스도 관계 여섯 가지의 표기 규칙(classdiagram.RULES): 상속은 같은 종류끼리, 고리·자기 자신 금지, 인터페이스가 아닌 것으로
가는 실체화는 알림. 이 관계를 받는 패키지도·컴포넌트도·배치도(deployment diagram)도 같은 규칙을 쓴다."""
import json

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
    assert p == ("relations[0]: 상속의 두 끝 종류가 다르다('Circle'는 'class', 'Shape'는 'interface') — 상속은 같은 종류끼리 "
                 "긋는다(class와 abstract는 같은 종류로 친다). 인터페이스를 구현하는 것이면 kind를 'realization'으로 바꾼다")


@pytest.mark.parametrize("source, target", [("interface", "class"), ("class", "enum"), ("enum", "abstract"),
                                            ("interface", "enum")])
def test_inheritance_between_different_kinds_is_an_input_error(source, target):
    (p,) = class_problems([box("A", 0, kind=source), box("B", 300, kind=target)], [rel("generalization", "A", "B")])
    assert p.startswith(f"relations[0]: 상속의 두 끝 종류가 다르다('A'는 {source!r}, 'B'는 {target!r})")
    assert p.endswith("상속은 같은 종류끼리 긋는다(class와 abstract는 같은 종류로 친다). from·to나 요소의 kind를 고친다")


def test_topic_marker_follows_the_last_syllable_of_the_name():
    (p,) = class_problems([box("주문", 0), box("결제", 300, kind="interface")], [rel("generalization", "주문", "결제")])
    assert "('주문'은 'class', '결제'는 'interface')" in p


def test_the_issue_example_now_reports_the_interface_inheriting_a_class():
    # 인터페이스 Shape, 클래스 Circle·Canvas에 Shape -> Circle 상속, Circle -> Shape 실체화, Canvas -> Circle 실체화
    classes = [box("Shape", 150, 0, kind="interface"), box("Circle", 0, 150), box("Canvas", 300, 150)]
    (p,) = class_problems(classes, [rel("generalization", "Shape", "Circle"), rel("realization", "Circle", "Shape"),
                                    rel("realization", "Canvas", "Circle")])
    assert p.startswith("relations[0]: 상속의 두 끝 종류가 다르다('Shape'는 'interface', 'Circle'는 'class')")


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
    assert n.problem == "실체화가 가는 상자 'Shape'는 인터페이스가 아니다(kind 'class')."
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
    assert "(kind 'abstract')" in n.problem and n.hint.startswith("상속을 뜻했으면 kind를 'generalization'으로 바꾸고")


def test_realization_hint_never_leads_to_an_input_error():
    # class -> enum은 상속으로 바꾸면 종류가 다른 상속 오류라, 상속을 권하지 않고 실체화를 긋는 자리를 알린다
    r = class_report([box("A", 0), box("B", 300, kind="enum")], [rel("realization", "A", "B")])
    (n,) = r.notices
    assert n.hint == "실체화는 인터페이스를 구현하는 쪽에서 인터페이스로 긋는다 — 다른 뜻이면 dependency를 쓴다."
    assert "generalization" not in n.hint


def test_realization_made_by_an_interface_has_a_notice_from_its_source():
    same = class_report([box("I", 0, kind="interface"), box("J", 300, kind="interface")], [rel("realization", "I", "J")])
    (n,) = same.notices
    assert n.problem == "실체화를 하는 상자 'I'는 인터페이스다(kind 'interface')."
    assert n.hint == "인터페이스끼리는 kind를 'generalization'으로 바꾼다."
    turned = class_report([box("Shape", 0, kind="interface"), box("Circle", 300)], [rel("realization", "Shape", "Circle")])
    (n,) = turned.notices
    assert n.problem.startswith("실체화를 하는 상자 'Shape'는 인터페이스다")
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
    assert p.startswith(f"relations[0]: 상속의 두 끝 종류가 다르다('a'는 {source!r}, 'b'는 {target!r})")


def test_inheritance_into_a_component_points_to_realization():
    (p,) = problems(CD, [el("class", "Impl", 0, 200), el("component", "Api", 0)], [rel("generalization", "Impl", "Api")])
    assert p.endswith(". 클래스가 컴포넌트를 실현하는 것이면 kind를 'realization'으로 바꾼다")


@pytest.mark.parametrize("source, target, problem", [
    ("lollipop", "class", "실체화를 하는 요소 'a'는 인터페이스다(kind 'lollipop')."),
    ("package", "interface", "패키지('a')는 실체화하지 않는다."),
])
def test_realization_made_by_a_ball_or_a_package_has_a_notice(source, target, problem):
    r = report(CD, [el(source, "a", 0), el(target, "b", 300)], [rel("realization", "a", "b")])
    (n,) = r.notices
    assert n.problem == problem


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
        f"relations[0]: 패키지({end!r})는 상속의 끝이 될 수 없다 — 패키지 사이는 dependency로 잇는다(«import» 등은 "
        "stereotype으로 단다)",)


@pytest.mark.parametrize("source, target, end", [("lollipop", "lollipop", "a"), ("interface", "lollipop", "b")])
def test_provided_interface_balls_are_never_an_end_of_inheritance(source, target, end):
    assert problems(CD, [el(source, "a", 0), el(target, "b", 300)], [rel("generalization", "a", "b")]) == (
        f"relations[0]: 제공 인터페이스 원({end!r})은 상속의 끝이 될 수 없다 — 인터페이스 사이 상속은 kind 'interface' 상자끼리 "
        "긋는다",)


@pytest.mark.parametrize("target", ["component", "lollipop", "interface"])
def test_realization_to_a_component_or_an_interface_has_no_notice(target):
    # 클래스가 컴포넌트를 실현하는 것은 컴포넌트도 배치 요령이 권하는 맞는 쓰임이다
    r = report(CD, [el("class", "Impl", 250, 0), el(target, "Api", 0)], [rel("realization", "Impl", "Api")])
    assert r.passed and r.notices == (), r.summary()


@pytest.mark.parametrize("module, target", [(P, "package"), (D, "artifact"), (D, "node")])
def test_realization_to_a_package_artifact_or_node_draws_with_a_notice(module, target):
    r = report(module, [el("class", "Impl", 0, 250), el(target, "x", 0)], [rel("realization", "Impl", "x")])
    (n,) = r.notices
    assert n.problem == f"실체화가 가는 요소 'x'는 인터페이스가 아니다(kind {target!r})."
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
    assert ('  - 알림: 실체화가 "interface"가 아닌 상자로 가거나 "interface"가 실체화하면 그리되 검사 결과에 알림을 준다'
            in server.CLASS_TOOL)
    assert ('"interface"끼리, "enum"끼리, "component"끼리, "artifact"끼리, "node"끼리). "package"는 상속의 끝이 될 수 없다.'
            in P.TOOL)
    assert '"package"·"lollipop"는 상속의 끝이 될 수 없다.' in CD.TOOL
    assert '실체화가 "interface"·"lollipop"·"component"가 아닌 요소로 가거나 "interface"·"lollipop"·"package"가 실체화하면' in CD.TOOL
    assert '실체화가 "interface"·"component"가 아닌 요소로 가거나 "interface"·"package"가 실체화하면' in D.TOOL
    # 유즈케이스도의 일반화는 클래스도 관계가 아니라 이 규칙을 적지 않는다
    assert "  - 규칙:" not in usecasediagram.TOOL


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
    assert f"{NOTICE_HEAD.format(1)}\n- relations[0]: 실체화가 가는 요소 'x'는" in ok.content[0].text
