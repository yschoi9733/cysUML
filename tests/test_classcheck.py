import json

import pytest

from cysuml import classcheck as K
from cysuml import classdiagram as C


def box(name, left, top, **more):
    return {"name": name, "left": left, "top": top, **more}


def rel(kind, source, target, **more):
    return {"kind": kind, "from": source, "to": target, **more}


def report(classes, relations=(), scale=C.SCALE):
    return K.check(C.render({"classes": list(classes), "relations": list(relations)}, scale))


def kinds(r):
    return [f.kind for f in r.failures]


# ---------------------------------------------------------------- 선이 상자를 지난다


def line_past(p_top, **relation):
    """A(0, 0)→B(400, 0)의 가로선(y=24, x 90~400) 아래위로 관계 없는 상자 P(200, p_top, 90×48)를 둔다."""
    return report([box("A", 0, 0), box("B", 400, 0), box("P", 200, p_top)],
                  [rel(relation.pop("kind", "association"), "A", "B", **relation)])


def test_line_through_a_third_box_fails_with_its_rect_and_a_hint():
    r = line_past(0)
    assert not r.passed
    (f,) = r.failures
    assert f.kind == "line_through_box" and f.elements == ("A->B", "P")
    assert f.where == pytest.approx((196, 24, 294, 24))
    assert "상자 P(200, 0, 90×48)" in f.problem and "relations[0]" in f.problem
    assert "꺾는 점(via)을 주어" in f.hint


def test_line_crossing_text_inside_a_third_box_is_one_box_finding():
    # P의 이름 글자 높이(y≈13)로 선이 지나간다 — 상자를 먼저 지나므로 글자는 따로 알리지 않는다
    r = line_past(11)
    assert kinds(r) == ["line_through_box"]


def test_line_with_via_through_a_box_hints_to_fix_the_via():
    r = report([box("A", 0, 0), box("B", 400, 0), box("P", 200, 100)],
               [rel("association", "A", "B", via=[[45, 124], [445, 124]])])
    (f,) = r.failures
    assert f.kind == "line_through_box" and "꺾는 점(via)을 고쳐" in f.hint


@pytest.mark.parametrize("p_top, passed, phrase", [
    (24 + K.BOX_CLEARANCE, False, "4px 안으로 붙어 지나간다"),
    (24 + K.BOX_CLEARANCE + 0.5, True, None),
    (24 - 48 - K.BOX_CLEARANCE, False, "4px 안으로 붙어 지나간다"),
    (24 - 48 - K.BOX_CLEARANCE - 0.5, True, None),
])
def test_line_closer_than_the_clearance_counts_as_passing_the_box(p_top, passed, phrase):
    r = line_past(p_top, navigable="none")
    assert r.passed is passed
    if phrase:
        assert phrase in r.failures[0].problem


def test_moving_the_box_off_the_line_passes():
    assert line_past(200).passed


def test_arrowhead_reaching_a_third_box_fails():
    # B(300, 0) 앞의 열린 화살촉 갈래 끝은 (291.2, 19.3)이다. Q의 아래 변(16.3)은 선(y=24)에서 4px 넘게 떨어졌지만 갈래와는 4px 안이다.
    classes = [box("A", 0, 0), box("B", 300, 0), box("Q", 200, -40, width=95, height=56.3)]
    r = report(classes, [rel("association", "A", "B")])
    (f,) = r.failures
    assert f.kind == "line_through_box" and f.elements == ("A->B", "Q") and "붙어 지나간다" in f.problem
    assert report(classes, [rel("association", "A", "B", navigable="none")]).passed


def test_end_boxes_are_not_third_boxes():
    assert report([box("A", 0, 0), box("B", 300, 0)], [rel("generalization", "A", "B")]).passed
    assert report([box("A", 0, 0)], [rel("association", "A", "A", via=[[45, -40], [140, -40], [140, 24]])]).passed


# ---------------------------------------------------------------- 상자끼리 겹친다


def test_boxes_overlap_after_growing_to_fit_text():
    # A는 왼쪽 위만 받았지만 긴 속성에 맞춰 207로 넓어져 B(150, 0)를 덮는다
    r = report([box("A", 0, 0, attributes=["-aVeryLongAttributeName: String"]), box("B", 150, 0)])
    (f,) = r.failures
    assert f.kind == "box_overlap" and f.elements == ("A", "B")
    assert "상자끼리 겹친다" in f.problem and "상자 A(0, 0, 207×63)" in f.problem
    assert f.where == (150, 0, 207, 48)


@pytest.mark.parametrize("b_left, passed, phrase", [
    (90, False, "맞닿았다"),
    (93, False, "3px밖에 떨어지지 않았다"),
    (90 + K.BOX_CLEARANCE, False, "4px밖에"),
    (90 + K.BOX_CLEARANCE + 0.5, True, None),
])
def test_boxes_closer_than_the_clearance_fail(b_left, passed, phrase):
    r = report([box("A", 0, 0), box("B", b_left, 0)])
    assert r.passed is passed
    if phrase:
        assert phrase in r.failures[0].problem


def test_diagonal_boxes_count_the_farther_axis():
    # 가로 3, 세로 10 떨어지면 세로로 4px 넘게 떨어진 것이라 합격
    assert report([box("A", 0, 0), box("B", 93, 58)]).passed
    assert not report([box("A", 0, 0), box("B", 93, 51)]).passed


# ---------------------------------------------------------------- 선이 글자를 지난다


def crossed_multiplicity(x):
    """A→B의 to 쪽 다중도(긴 글자)가 B 앞에 놓이고, C→D 세로 점선이 x에서 그 둘레를 지난다."""
    return report([box("A", 0, 0), box("B", 300, 0), box("C", x - 45, -200), box("D", x - 45, 200)],
                  [rel("association", "A", "B", to_multiplicity="0..* {ordered, unique}"), rel("dependency", "C", "D")])


def test_multiplicity_crossed_by_another_line_fails():
    r = crossed_multiplicity(270)
    (f,) = r.failures
    assert f.kind == "line_through_text" and f.elements == ("C->D", "A->B")
    assert "to 쪽 다중도 '0..* {ordered, unique}'" in f.problem and "relations[1]" in f.problem


def test_moving_the_other_line_away_from_the_multiplicity_passes():
    r = crossed_multiplicity(150)
    assert r.passed and len(r.crossings) == 1


def test_name_crossed_by_another_line_fails():
    # 세로선이 이름 후보 둘(가로선 가운데 위아래)을 다 지나 이름이 선 위에 놓인다
    r = report([box("A", 0, 0), box("B", 300, 0), box("C", 150, -200), box("D", 150, 200)],
               [rel("association", "A", "B", name="places"), rel("association", "C", "D")])
    (f,) = r.failures
    assert f.kind == "line_through_text" and f.elements == ("C->D", "A->B") and "이름 'places'" in f.problem


def test_line_through_its_own_label_names_one_element():
    # 가장 긴 첫 구간 (90, 24)–(400, 24)의 가운데 위아래가 이름 자리인데, 돌아 내려오는 마지막 구간(x=245)이 둘 다 지난다
    r = report([box("A", 0, 0), box("B", 200, 280)],
               [rel("association", "A", "B", name="x", via=[[400, 24], [400, -10], [245, -10]])])
    own = [f for f in r.failures if f.kind == "line_through_text"]
    assert own and all(f.elements == ("A->B",) for f in own)
    assert own[0].hint == K.LABEL_HINT


def test_labels_placed_where_the_layout_found_room_pass():
    r = report([box("A", 0, 0), box("B", 400, 0)],
               [rel("association", "A", "B", name="has", from_multiplicity="1", to_multiplicity="0..*")])
    assert r.passed


def test_text_clearance_matches_label_placement():
    assert K.TEXT_CLEARANCE == C.LABEL_CLEAR


# ---------------------------------------------------------------- 선 글자가 상자에·선 글자끼리 겹친다


def boxed_in_name(c_bottom):
    """A→B 가로선(y=24) 가운데 위아래에 상자 C·D(선에서 5px)를 두어 이름 놓을 자리를 막는다. C의 아래 변은 c_bottom."""
    return report([box("A", 0, 0), box("B", 300, 0), box("C", 120, c_bottom - 59, width=140, height=59),
                   box("D", 120, 29, width=140)],
                  [rel("association", "A", "B", name="has")])


def test_label_with_no_room_lands_on_a_box_and_fails():
    r = boxed_in_name(19)
    (f,) = r.failures
    assert f.kind == "text_on_box" and f.elements == ("A->B", "C")
    assert "이름 'has'" in f.problem and "상자 C(120, -40, 140×59)" in f.problem and f.hint == K.LABEL_HINT


def test_label_with_room_above_the_line_passes():
    assert boxed_in_name(-10).passed


def test_labels_of_stacked_relations_overlap():
    # 같은 두 상자 사이의 세 관계는 한 선에 포개지고, 이름 자리 둘을 앞의 둘이 쓰고 나면 셋째 이름은 겹친다
    r = report([box("A", 0, 0), box("B", 300, 0)],
               [rel("association", "A", "B", name="a"), rel("dependency", "A", "B", name="b"),
                rel("association", "B", "A", name="c")])
    (f,) = [f for f in r.failures if f.kind == "text_overlap"]
    assert f.elements == ("A->B#2", "B->A") and "이름 'b'" in f.problem and "이름 'c'" in f.problem


# ---------------------------------------------------------------- 선끼리 포개진다


def test_two_relations_on_one_line_fail():
    r = report([box("A", 0, 0), box("B", 300, 0)], [rel("association", "A", "B"), rel("dependency", "B", "A")])
    (f,) = r.failures
    assert f.kind == "line_overlap" and f.elements == ("A->B", "B->A")
    assert f.where == pytest.approx((90, 24, 300, 24)) and "한 선으로 보여" in f.hint


def test_routing_one_relation_apart_passes():
    r = report([box("A", 0, 0), box("B", 300, 0)],
               [rel("association", "A", "B"), rel("dependency", "B", "A", via=[[345, 100], [45, 100]])])
    assert r.passed


def test_lines_run_side_by_side_within_the_gap_fail():
    # 2px 안으로 나란히 가는 선은 한 선으로 보인다
    r = report([box("A", 0, 0, height=60), box("B", 300, 0, height=60)],
               [rel("association", "A", "B", via=[[150, 20], [250, 20]]),
                rel("association", "A", "B", via=[[150, 21.5], [250, 21.5]])])
    assert "line_overlap" in kinds(r)
    r = report([box("A", 0, 0, height=60), box("B", 300, 0, height=60)],
               [rel("association", "A", "B", via=[[150, 20], [250, 20]]),
                rel("association", "A", "B", via=[[150, 40], [250, 40]])])
    assert "line_overlap" not in kinds(r)


def test_line_retracing_its_way_fails():
    r = report([box("A", 0, 0), box("B", 300, 0)], [rel("association", "A", "B", via=[[200, 24], [150, 24]])])
    (f,) = r.failures
    assert f.kind == "line_overlap" and f.elements == ("A->B",) and "되짚는다" in f.problem
    assert f.where == pytest.approx((150, 24, 200, 24))


def test_straight_line_through_a_collinear_bend_is_not_a_retrace():
    assert report([box("A", 0, 0), box("B", 300, 0)], [rel("association", "A", "B", via=[[150, 24]])]).passed


def tree(kind_a, kind_b, target_b="P"):
    """P(150, 0) 아래 C1(0, 200)·C2(300, 200)이 y=120 줄기로 모여 P 가운데 (195)로 올라간다."""
    return report([box("P", 150, 0), box("C1", 0, 200), box("C2", 300, 200)],
                  [rel(kind_a, "C1", "P", via=[[45, 120], [195, 120]]),
                   rel(kind_b, "C2", target_b, via=[[345, 120], [195, 120]])])


@pytest.mark.parametrize("kind", ["generalization", "realization"])
def test_shared_trunk_of_an_inheritance_tree_passes(kind):
    r = tree(kind, kind)
    assert r.passed and r.crossings == ()


@pytest.mark.parametrize("kind_a, kind_b", [("generalization", "realization"), ("association", "association"),
                                            ("generalization", "association")])
def test_shared_trunk_of_other_relations_fails(kind_a, kind_b):
    assert kinds(tree(kind_a, kind_b)) == ["line_overlap"]


def test_same_child_twice_is_not_a_trunk():
    r = report([box("P", 150, 0), box("C", 150, 200)], [rel("generalization", "C", "P"), rel("generalization", "C", "P")])
    assert kinds(r) == ["line_overlap"]


# ---------------------------------------------------------------- 알림


def test_crossing_lines_are_a_notice_not_a_failure():
    r = report([box("A", 0, 0), box("B", 300, 200), box("C", 300, 0), box("D", 0, 200)],
               [rel("association", "A", "B"), rel("association", "C", "D")])
    assert r.passed
    (f,) = r.crossings
    assert f.kind == "crossing" and f.elements == ("A->B", "C->D")
    assert f.where == pytest.approx((195, 124, 195, 124)) and "(195, 124)" in f.problem


def test_lines_meeting_at_a_point_are_not_counted_as_crossing():
    # C2의 줄기가 C1의 세로 줄기 끝 (195, 120)에서 만나기만 한다
    assert tree("generalization", "generalization").crossings == ()


@pytest.mark.parametrize("scale", [1.0, C.SCALE, 2.5])
def test_size_is_the_png_the_canvas_draws(scale):
    d = C.render({"classes": [box("A", 0, 0), box("B", 300, 50)], "relations": [rel("association", "A", "B", name="x")]},
                 scale)
    r = K.check(d)
    assert r.png_size == d.canvas.to_image().size
    frame = d.canvas.frame()
    assert r.size == pytest.approx((frame[2] - frame[0], frame[3] - frame[1]), abs=1 / scale)
    assert r.scale == scale


def test_size_of_a_huge_scale_is_not_counted():
    d = C.render({"classes": [box("A", 0, 0)]}, 1e308)
    r = K.check(d)
    assert r.png_size is None and r.passed
    assert "PNG 크기는 셀 수 없음" in r.summary()


# ---------------------------------------------------------------- 결과 형식


def test_report_turns_into_json():
    r = line_past(0)
    data = json.loads(json.dumps(r.to_dict(), ensure_ascii=False))
    assert data["passed"] is False
    (f,) = data["failures"]
    assert f["kind"] == "line_through_box" and f["elements"] == ["A->B", "P"]
    assert f["where"] == [196.0, 24.0, 294.0, 24.0]
    assert set(f) == {"kind", "elements", "where", "problem", "hint"}
    assert data["crossings"] == []
    assert data["size"] == {"width": 514.0, "height": 72.0, "png_width": 823, "png_height": 116, "scale": C.SCALE}


def test_summary_lists_failures_then_notices():
    lines = line_past(0).summary().splitlines()
    assert lines[0] == "불합격 — 1건"
    assert lines[1].startswith("1. 선이 상자를 지난다: 선 A->B(relations[0]), 상자 P(200, 0, 90×48).")
    assert lines[2] == "알림 — 선끼리 엇갈린 곳 0곳"
    assert lines[3] == "알림 — 그림 크기: 논리 좌표 514×72(둘레 여백 포함), PNG 823×116px(배율 1.6)"
    assert line_past(200).summary().startswith("합격")


def test_findings_come_boxes_first_then_lines_then_labels():
    r = report([box("A", 0, 0), box("B", 300, 0), box("P", 150, 0), box("Q", 160, 10)],
               [rel("association", "A", "B", name="n"), rel("dependency", "B", "A")])
    order = ["box_overlap", "line_through_box", "line_overlap", "line_through_text", "text_on_box", "text_overlap"]
    found = kinds(r)
    assert found == sorted(found, key=order.index)
    assert {"box_overlap", "line_through_box", "line_overlap"} <= set(found)


def test_typical_diagram_passes():
    r = report(
        [box("Customer", 0, 0, attributes=[{"name": "name", "type": "String"}],
             operations=[{"name": "placeOrder", "params": ["items: List"], "returns": "Order"}]),
         box("Order", 300, 0, attributes=[{"name": "id", "type": "long"}, {"name": "status", "type": "Status"}]),
         box("OrderLine", 600, 0, attributes=[{"name": "qty", "type": "int"}]),
         box("Payment", 300, 200, kind="abstract", attributes=[{"name": "amount", "type": "Money"}]),
         box("CardPayment", 150, 400), box("CashPayment", 450, 400)],
        [rel("association", "Customer", "Order", name="places", from_multiplicity="1", to_multiplicity="0..*"),
         rel("composition", "Order", "OrderLine", from_multiplicity="1", to_multiplicity="1..*"),
         rel("association", "Order", "Payment", to_multiplicity="0..1"),
         rel("generalization", "CardPayment", "Payment", via=[[205, 340], [365, 340]]),
         rel("generalization", "CashPayment", "Payment", via=[[505, 340], [365, 340]])])
    assert r.passed and r.crossings == ()
