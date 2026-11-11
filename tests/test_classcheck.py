import dataclasses
import json
import unicodedata

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


@pytest.mark.parametrize("via_y, passed", [(-2, False), (-4, False), (-4.5, True), (-10, True)])
def test_line_running_along_its_own_end_box_fails(via_y, passed):
    # A→B가 A 위 변 바로 위(via_y)를 x 10~90 동안 따라간다 — A의 윗테두리가 두 겹으로 보인다
    r = report([box("A", 0, 0), box("B", 300, 0)],
               [rel("association", "A", "B", via=[[10, via_y], [200, via_y], [200, 24]])])
    assert r.passed is passed
    if not passed:
        (f,) = r.failures
        assert f.kind == "line_along_own_box" and f.elements == ("A->B", "A")
        assert "제 끝 상자에 4px 안으로 붙어 간다" in f.problem and "상자 A(0, 0, 90×48)" in f.problem
        assert "테두리가 두 겹" in f.hint


def test_end_segment_leaving_its_box_at_a_shallow_angle_passes():
    # 넓은 A(300×48) 위 변을 9°쯤으로 비스듬히 나가는 끝 구간은 처음 20여 px가 변에 붙어 있지만, 끝 구간이라 보지 않는다
    r = report([box("A", 0, 0, width=300), box("B", 600, -200)],
               [rel("association", "A", "B", via=[[290, -6], [645, -6]])])
    assert r.passed


@pytest.mark.parametrize("b_top, passed", [(58, False), (80, True)])
def test_end_shape_reaching_the_other_end_box_hints_to_space_the_boxes(b_top, passed):
    # A 바로 밑 B로 가는 의존선은 10px뿐이라 B 쪽 화살촉 갈래 끝(y≈49)이 A 아래 변(48)에 붙는다 — 꺾는 점이 없으니 상자를 떼야 한다
    r = report([box("A", 0, 0), box("B", 0, b_top)], [rel("dependency", "A", "B")])
    assert r.passed is passed
    if not passed:
        (f,) = r.failures
        assert f.kind == "head_near_own_box" and f.elements == ("A->B", "A")
        assert "선 끝 모양이 제 끝 상자 변에 4px 안으로 붙는다" in f.problem
        assert f.hint.endswith("두 상자를 더 떼어 놓는다.") and "via" not in f.hint


def test_bend_just_outside_its_own_box_that_leaves_at_once_passes():
    # 꺾는 점 (93, 24)는 A 오른쪽 변에서 3px이지만, 다음 구간이 곧바로 비스듬히 멀어져 변을 따라가지 않는다
    r = report([box("A", 0, 0), box("B", 400, 200)],
               [rel("association", "A", "B", navigable="none", via=[[93, 24], [300, 100]])])
    assert r.passed


@pytest.mark.parametrize("width, b_left, b_top, passed", [(300, 1105, -300, False), (300, 700, -300, True),
                                                         (90, 435, -264, True)])
def test_end_shape_hidden_under_its_own_box(width, b_left, b_top, passed):
    # 넓은 A(300×48) 위 변을 17°로 나가면 마름모 꼭짓점이 A 안으로 3.2px 들어가 가려진다. 27°면 1.3px, 보통 상자(90×48)를
    # 31°로 나가면 0.5px로, 꼭짓점이 상자 테두리에 겹치는 정도라 합격이다
    r = report([box("A", 0, 0, width=width), box("B", b_left, b_top)], [rel("aggregation", "A", "B")])
    assert r.passed is passed
    if not passed:
        (f,) = r.failures
        assert f.kind == "head_under_own_box" and f.elements == ("A->B", "A")
        assert "선 끝 모양이 제 끝 상자에 가려진다" in f.problem and "마름모" in f.problem


def test_self_relation_loop_hugging_its_box_fails():
    # 자기 관계의 고리 가운데 구간이 A 위 변 2px 위를 지난다(처음·마지막 구간만 A에 닿는 끝 구간이다)
    hug = report([box("A", 0, 0)], [rel("association", "A", "A", via=[[20, -30], [20, -2], [70, -2], [70, -30], [140, -30], [140, 24]])])
    assert [(f.kind, f.elements) for f in hug.failures] == [("line_along_own_box", ("A->A", "A"))]
    assert report([box("A", 0, 0)], [rel("association", "A", "A", via=[[45, -40], [140, -40], [140, 24]])]).passed


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


def test_boxes_touching_through_float_error_are_called_touching():
    # A의 오른쪽 -89.9 + 90은 실수로 0.09999999999999432라 B의 왼쪽 0.1과 6e-15 떨어진다
    (f,) = report([box("A", -89.9, 0), box("B", 0.1, 0)]).failures
    assert "맞닿았다" in f.problem


def test_boxes_a_hair_apart_are_called_touching():
    # 틈 0.02px는 소수 한 자리로 0이라 "0px밖에 떨어지지 않았다"가 아니라 맞닿았다고 적는다
    (f,) = report([box("A", 0, 0, width=90.03), box("B", 90.05, 0)]).failures
    assert "맞닿았다" in f.problem


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


def test_label_text_given_in_nfd_to_draw_is_matched_to_its_record():
    # parse를 거치지 않고 draw에 바로 준 모델은 풀어 쓴 한글(NFD)일 수 있다 — 그린 기록의 글자는 NFC다
    diagram = C.parse({"classes": [box("A", 0, 0), box("B", 300, 0)], "relations": [rel("association", "A", "B", name="가입")]})
    relation = dataclasses.replace(diagram.relations[0], name=unicodedata.normalize("NFD", "가입"))
    r = K.check(C.draw(dataclasses.replace(diagram, relations=(relation,))))
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


def test_siblings_with_slightly_shifted_triangles_are_not_a_trunk():
    # C1→P는 (243.4, 48), C2→P는 (245, 48)에 닿아 두 삼각형이 1.6px 어긋나 겹치고, 서로의 선이 상대 삼각형을 지난다
    r = report([box("P", 200, 0), box("C1", 105, 200), box("C2", 295, 250)],
               [rel("generalization", "C1", "P", via=[[150, 100], [240, 100]]),
                rel("generalization", "C2", "P", via=[[340, 150], [245, 150]])])
    assert kinds(r) == ["line_through_head", "line_through_head", "head_overlap"]
    assert r.failures[2].elements == ("C1->P", "C2->P")


def test_same_child_twice_is_not_a_trunk():
    r = report([box("P", 150, 0), box("C", 150, 200)], [rel("generalization", "C", "P"), rel("generalization", "C", "P")])
    assert kinds(r) == ["line_overlap"]


# ---------------------------------------------------------------- 선이 다른 관계의 선 끝 모양에 닿는다


def triangle_over(d_top):
    """A→B 가로선(y=24) 위로 C→D 상속선이 내려와 D 위 변(d_top)에 삼각형(길이 18)을 그린다."""
    return report([box("A", 0, 0), box("B", 400, 0), box("C", 200, -200), box("D", 200, d_top)],
                  [rel("association", "A", "B"), rel("generalization", "C", "D")])


def test_line_under_another_relations_triangle_fails():
    # 삼각형(y 12~30)은 흰색으로 칠해져 그 밑을 지나는 A→B 선을 끊는다
    r = triangle_over(30)
    (f,) = r.failures
    assert f.kind == "line_through_head" and f.elements == ("A->B", "C->D")
    assert "관계 C->D(relations[1])의 삼각형" in f.problem
    assert f.where == pytest.approx((236, 12, 254, 30))


def test_moving_the_triangle_off_the_line_passes():
    r = triangle_over(100)
    assert r.passed and len(r.crossings) == 1


@pytest.mark.parametrize("navigable, passed", [("to", False), ("none", True)])
def test_line_through_another_relations_arrowhead(navigable, passed):
    # B(300, 0) 앞 화살촉의 갈래는 x 291~300에 걸친다. C→D 세로선(x=295)은 B에서 5px 떨어져 상자는 비켜 가지만 갈래를 지난다.
    r = report([box("A", 0, 0), box("B", 300, 0), box("C", 250, -200), box("D", 250, 200)],
               [rel("association", "A", "B", navigable=navigable), rel("association", "C", "D", navigable="none")])
    assert r.passed is passed
    if not passed:
        (f,) = r.failures
        assert f.kind == "line_through_head" and f.elements == ("C->D", "A->B") and "화살촉" in f.problem


def test_line_under_its_own_diamond_fails():
    # 돌아온 세로 구간(x=100)이 제 마름모(x 90~108)를 지난다
    via = [[150, 24], [150, 80], [100, 80], [100, 10], [200, 10], [200, 24]]
    r = report([box("A", 0, 0), box("B", 400, 0)], [rel("aggregation", "A", "B", navigable="none", via=via)])
    (f,) = r.failures
    assert f.kind == "line_through_head" and f.elements == ("A->B",) and "제 선 끝 모양" in f.problem
    assert report([box("A", 0, 0), box("B", 400, 0)], [rel("association", "A", "B", navigable="none", via=via)]).passed


def test_line_coming_back_over_its_own_triangle_fails():
    # 끝 구간 (370, 24)→(400, 24) 바로 앞 구간이 B 앞 빈 삼각형(x 382~400) 위로 되돌아 지나간다
    r = report([box("A", 0, 0), box("B", 400, 0)],
               [rel("generalization", "A", "B", via=[[200, 100], [398, 30], [370, 24]])])
    # 앞 구간이 지나는 꺾는 점 (398, 30)은 B 왼쪽 변에서 2px이라 B 변에 붙어 가는 것도 함께 걸린다
    assert [(f.kind, f.elements) for f in r.failures] == [("line_along_own_box", ("A->B", "B")),
                                                          ("line_through_head", ("A->B",))]


def test_own_end_shape_on_its_own_end_segments_is_fine():
    assert report([box("A", 0, 0), box("B", 300, 0)],
                  [rel("composition", "A", "B", via=[[108, 24], [108, 100], [345, 100]])]).passed


def test_overlap_hides_only_the_end_shapes_it_reaches():
    # C→D가 A→B 가로선의 가운데(x 120~250)에 포개진 뒤, 멀리 B 앞 화살촉(x 391~400)을 세로로 지난다
    r = report([box("A", 0, 0), box("B", 400, 0), box("C", 75, -200), box("D", 350, 100)],
               [rel("association", "A", "B"),
                rel("association", "C", "D", via=[[120, 24], [250, 24], [250, -60], [395, -60]])])
    assert kinds(r) == ["line_overlap", "line_through_head"]
    assert r.failures[1].elements == ("C->D", "A->B")


def test_overlaps_hide_end_shapes_only_near_each_overlapped_piece():
    # C→D는 A→B에 두 군데(위 y=24 x 100~140, 아래 y=124 x 290~342) 포개지고, 두 조각을 함께 덮는 상자 안에 든 B 밑 화살촉
    # (x 340~350, y 48~57)을 두 조각과 떨어진 y=54에서 지난다
    r = report([box("A", 0, 0), box("B", 300, 0), box("C", 55, -200), box("D", 420, 30)],
               [rel("association", "A", "B", via=[[150, 24], [150, 124], [345, 124]]),
                rel("association", "C", "D", navigable="none",
                    via=[[100, 24], [140, 24], [140, -40], [290, -40], [290, 124], [342, 124], [342, 54], [400, 54]])])
    assert kinds(r) == ["line_overlap", "line_through_head"]
    assert r.failures[1].elements == ("C->D", "A->B")


@pytest.mark.parametrize("via_y, passed", [(216, False), (300, True)])
def test_arrowhead_inside_another_relations_triangle_fails(via_y, passed):
    # 키 큰 B(400, 0, 200×400)의 왼쪽 변에 상속 삼각형(끝 (400, 200))과 의존 화살촉(끝 (400, 208))이 붙는다. 두 선은 닿지 않지만
    # 화살촉 갈래 끝이 흰 삼각형 안에 들어간다
    r = report([box("A", 0, 176), box("Cc", 0, 300), box("B", 400, 0, width=200, height=400)],
               [rel("generalization", "A", "B", via=[[300, 200]]), rel("dependency", "Cc", "B", via=[[300, via_y]])])
    assert r.passed is passed
    if not passed:
        # 의존선도 삼각형 아래 모서리 (382, 209)에서 0.4px 옆을 지나 그 삼각형에 붙는다
        assert kinds(r) == ["line_through_head", "head_overlap"]
        f = r.failures[1]
        assert f.elements == ("A->B", "Cc->B")
        assert "관계 A->B(relations[0])의 삼각형" in f.problem and "관계 Cc->B(relations[1])의 화살촉" in f.problem


def test_diagonal_overlap_hides_only_end_shapes_next_to_it():
    # A→D가 A→C의 대각선 (100, 100)–(300, 300)에 포개진 뒤 x=306 세로로 C 오른쪽 화살촉(x 300~309, y 115~125)을 지난다.
    # 그 화살촉은 대각선을 덮는 상자 안이지만 대각선에서 100px 넘게 떨어져 있다
    r = report([box("A", 0, 0), box("C", 210, 96), box("D", 261, -100)],
               [rel("association", "A", "C", via=[[100, 100], [300, 300], [350, 120]]),
                rel("association", "A", "D", via=[[100, 100], [300, 300], [306, 300]])])
    assert kinds(r) == ["line_overlap", "line_through_head"]
    assert r.failures[1].elements == ("A->D", "A->C") and "화살촉" in r.failures[1].problem


def test_two_end_shapes_of_one_self_relation_overlap():
    # 자기 관계의 두 끝이 A 위 변에서 4.5px 떨어져 마름모와 화살촉이 겹친다
    r = report([box("A", 0, 0)], [rel("aggregation", "A", "A", via=[[40, -40], [40, -60], [52, -60], [52, -40]])])
    (f,) = [f for f in r.failures if f.kind == "head_overlap"]
    assert f.elements == ("A->A",) and "마름모" in f.problem and "화살촉" in f.problem


def test_orthogonal_bend_right_at_the_triangle_base_passes():
    # 끝 구간 (345, 182)→(345, 200)이 삼각형 길이(18)와 같아, 앞 가로 구간이 삼각형 밑변(y=182)을 따라 들어온다
    r = report([box("A", 0, 0), box("P", 300, 200)],
               [rel("generalization", "A", "P", via=[[200, 24], [200, 182], [345, 182]])])
    assert r.passed


@pytest.mark.parametrize("via_x", [140, 136])
def test_line_coming_up_into_its_own_triangle_base_passes(via_x):
    # 선이 아래에서 올라와 삼각형 밑변(y=66, x 136~154)의 가운데에서 5px 옆이나 모서리에 닿은 뒤, 밑변을 따라 줄기(x=145)로 간다
    r = report([box("A", 95, 200), box("P", 100, 0)],
               [rel("generalization", "A", "P", via=[[via_x, 66], [145, 66]])])
    assert r.passed


def test_places_within_the_tolerance_are_one_place():
    assert K._same((("A", True), (1.0, 2.0)), (("A", True), (1.0 + K.PLACE_EPS / 2, 2.0)))
    assert not K._same((1.0, 2.0), (1.0 + K.PLACE_EPS * 2, 2.0))
    assert not K._same(("A", 1.0), ("B", 1.0))


def test_shared_trunk_through_a_box_is_one_finding():
    # 두 자식의 공유 줄기(x=195, y 48~120)와 그 위 삼각형이 상자 Q(190, 60)를 지난다
    r = report([box("P", 150, 0), box("C1", 0, 200), box("C2", 300, 200), box("Q", 190, 60)],
               [rel("generalization", "C1", "P", via=[[45, 120], [195, 120]]),
                rel("generalization", "C2", "P", via=[[345, 120], [195, 120]])])
    (f,) = r.failures
    assert f.kind == "line_through_box" and f.elements == ("C1->P", "C2->P", "Q")
    assert "선 C1->P(relations[0]), 선 C2->P(relations[1]), 상자 Q" in f.problem


def test_drawing_records_must_match_the_layout():
    d = C.render({"classes": [box("A", 0, 0), box("B", 300, 0)], "relations": [rel("association", "A", "B")]})
    with pytest.raises(ValueError):
        K.check(dataclasses.replace(d, drawn=()))


@pytest.mark.parametrize("x, passed", [(281, False), (270, True)])
def test_line_running_just_beside_another_relations_triangle_fails(x, passed):
    # A→B 상속 삼각형의 밑변은 x=282(y 15~33)다. X→Y 세로선이 그 1px 옆을 나란히 가면 밑변과 한 선으로 보인다
    r = report([box("A", 0, 0), box("B", 300, 0), box("X", x - 45, 300), box("Y", x - 45, -300)],
               [rel("generalization", "A", "B"), rel("association", "X", "Y", navigable="none")])
    assert r.passed is passed and len(r.crossings) == 1
    if not passed:
        (f,) = r.failures
        assert f.kind == "line_through_head" and f.elements == ("X->Y", "A->B") and "삼각형" in f.problem


def test_diamond_counts_as_an_end_shape():
    r = report([box("A", 0, 0), box("B", 300, 0), box("C", 50, -200), box("D", 50, 200)],
               [rel("composition", "A", "B", navigable="none"), rel("association", "C", "D", navigable="none")])
    (f,) = r.failures
    assert f.kind == "line_through_head" and "마름모" in f.problem


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


def bent_over(via, d_top):
    """A→B 가로선(y=24, x 90~400)을 C(100, -200)→D(300, d_top)이 꺾는 점 via로 지나간다."""
    return report([box("A", 0, 0), box("B", 400, 0), box("C", 100, -200), box("D", 300, d_top)],
                  [rel("association", "A", "B", navigable="none"), rel("association", "C", "D", navigable="none", via=via)])


def test_bend_point_exactly_on_another_line_counts_when_the_line_goes_across():
    r = bent_over([[150, -100], [245, 24], [300, 150]], 250)
    assert r.passed
    (f,) = r.crossings
    assert f.where == pytest.approx((245, 24, 245, 24)) and f.elements == ("A->B", "C->D")


@pytest.mark.parametrize("leave_y, y_top, crossed", [(21, -200, True), (27, 200, False)])
def test_short_run_along_another_line_counts_by_where_it_leaves(leave_y, y_top, crossed):
    # X→Y가 아래에서 A→B 가로선(y=24)에 올라 3px(포개짐으로 치기엔 짧다)을 같이 가다 위(21)나 아래(27)로 나간다
    r = report([box("A", 0, 0), box("B", 400, 0), box("X", 155, 200), box("Y", 300, y_top)],
               [rel("association", "A", "B", navigable="none"),
                rel("association", "X", "Y", navigable="none", via=[[245, 27], [248, 24], [251, 24], [254, leave_y]])])
    assert r.passed
    assert len(r.crossings) == (1 if crossed else 0)
    if crossed:
        assert r.crossings[0].where == pytest.approx((249.5, 24, 249.5, 24))


def trunk_with(third):
    """P(150, 0)의 두 자식 C1·C2가 y=120 줄기로 모여 x=195로 올라가는 트리에 관계 하나(third)와 그 상자들을 더한다."""
    classes, relation = third
    return report([box("P", 150, 0), box("C1", 0, 200), box("C2", 300, 200), *classes],
                  [rel("generalization", "C1", "P", via=[[45, 120], [195, 120]]),
                   rel("generalization", "C2", "P", via=[[345, 120], [195, 120]]), relation])


def test_line_across_a_shared_trunk_is_one_crossing():
    r = trunk_with(([box("X", -200, 76), box("Y", 500, 76)], rel("association", "X", "Y", navigable="none")))
    assert r.passed
    (f,) = r.crossings
    assert f.elements == ("C1->P", "C2->P", "X->Y") and f.where == pytest.approx((195, 100, 195, 100))


def test_line_along_a_shared_trunk_is_one_overlap():
    r = trunk_with(([box("Z", 150, 300)], rel("dependency", "Z", "P")))
    (f,) = r.failures
    assert f.kind == "line_overlap" and f.elements == ("C1->P", "C2->P", "Z->P")
    assert f.where == pytest.approx((195, 48, 195, 120))


def test_bend_point_touching_another_line_from_one_side_is_not_a_crossing():
    assert bent_over([[150, -100], [245, 24], [340, -100]], -350).crossings == ()


def test_lines_sharing_a_bend_point_count_when_they_cross_there():
    # 두 선이 같은 꺾는 점 (200, 24)를 지나며 가로·세로로 건너간다
    r = report([box("A", 0, 0), box("B", 400, 0), box("C", 155, -200), box("D", 155, 200)],
               [rel("association", "A", "B", navigable="none", via=[[200, 24]]),
                rel("association", "C", "D", navigable="none", via=[[200, 24]])])
    assert [f.where for f in r.crossings] == [(200, 24, 200, 24)]


def test_lines_sharing_a_bend_point_without_crossing_are_not_counted():
    # 두 선 다 (200, 24)에서 위로 꺾어 나가 서로 건너가지 않는다
    r = report([box("A", 0, 0), box("B", 400, -300), box("C", 0, 100), box("D", 400, -150)],
               [rel("association", "A", "B", navigable="none", via=[[200, 24], [150, -276]]),
                rel("association", "C", "D", navigable="none", via=[[200, 24], [250, -126]])])
    assert r.crossings == ()


def test_line_crossing_itself_is_a_crossing():
    r = report([box("A", 0, 0), box("B", 400, 0)],
               [rel("association", "A", "B", via=[[200, 24], [200, 100], [150, 100], [150, -20], [250, -20]])])
    (f,) = r.crossings
    assert f.elements == ("A->B",) and f.where == (150, 24, 150, 24) and "제 선을 엇갈린다" in f.problem


@pytest.mark.parametrize("scale", [1.0, C.SCALE, 2.5])
def test_size_is_the_png_the_canvas_draws(scale):
    d = C.render({"classes": [box("A", 0, 0), box("B", 300, 50)], "relations": [rel("association", "A", "B", name="x")]},
                 scale)
    r = K.check(d)
    assert r.png_size == d.canvas.to_image().size
    frame = d.canvas.frame()
    assert r.size == pytest.approx((frame[2] - frame[0], frame[3] - frame[1]), abs=1 / scale)
    assert r.scale == scale


@pytest.mark.parametrize("classes, scale", [([box("A", 0, 0)], 1e308), ([box("A", 0, 0), box("B", 1800, 1800)], 2)])
def test_picture_too_big_for_a_png_has_no_png_size(classes, scale):
    d = C.render({"classes": classes}, scale)
    with pytest.raises(ValueError, match="너무 크다"):
        d.canvas.to_image()
    r = K.check(d)
    assert r.png_size is None and r.to_dict()["size"]["png_width"] is None
    assert f"배율 {scale:g}로는 PNG로 그리기에 너무 크다" in r.summary()


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
    found = kinds(r)
    assert found == sorted(found, key=K.KINDS.index)
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
