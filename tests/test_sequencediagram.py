import copy
from dataclasses import replace

import pytest
from PIL import Image

from cysuml import sequencecheck as SC
from cysuml import sequencediagram as S
from cysuml.canvas import Line, Mask, Polygon, Rect, Text


def life(*names, actor=()):
    return [{"name": n, "kind": "actor" if n in actor else "lifeline"} for n in names]


def call(a, b, name="run()"):
    return {"from": a, "to": b, "name": name}


def reply(a, b, name=None):
    return {"from": a, "to": b, "kind": "reply", **({"name": name} if name else {})}


def bars_of(lay, owner):
    return sorted((b for b in lay.bars if b.owner == owner), key=lambda b: b.top)


def overlap(a, b, pad=0.0):
    return a[0] - pad < b[2] and b[0] < a[2] + pad and a[1] - pad < b[3] and b[1] < a[3] + pad


def problems(data):
    with pytest.raises(S.InputError) as e:
        S.parse(data)
    return e.value.problems


# ---------------------------------------------------------------- 입력 읽기


def test_defaults_and_names():
    d = S.parse({"participants": [{"name": " A "}, {"name": "U", "kind": "actor"}],
                 "messages": [{"from": "U", "to": "A ", "name": "go()"}, {"from": "A", "to": "U", "kind": "reply"}]})
    assert d.participants == (S.Participant("A", "lifeline"), S.Participant("U", "actor"))
    assert d.messages == (S.Message("U", "A", "go()", "call"), S.Message("A", "U", None, "reply"))
    assert d.fragments == () and d.refs == () and d.notes == ()


def test_frames_are_read_by_kind():
    d = S.parse({"participants": life("A", "B"),
                 "messages": [call("A", "B")] * 4,
                 "frames": [{"kind": "alt", "branches": [{"condition": "ok", "first": 2, "last": 2},
                                                         {"condition": "else", "first": 3, "last": 3}]},
                            {"kind": "loop", "first": 0, "last": 1},
                            {"kind": "ref", "name": "Login", "before": 4}]})
    assert [(f.kind, f.first, f.last, f.index) for f in d.fragments] == [("loop", 0, 1, 1), ("alt", 2, 3, 0)]
    assert d.fragments[1].branches == (S.Branch("ok", 2, 2), S.Branch("else", 3, 3))
    assert d.refs == (S.Ref("Login", 4, 2),)


@pytest.mark.parametrize("data, expected", [
    ([], "입력: 객체여야 한다"),
    ({}, "입력: 'participants' 필드가 빠졌다"),
    ({"participants": []}, "participants: 참여자가 하나 이상"),
    ({"participants": life("A", "A")}, "participants[1].name: participants[0]와 이름이 같다"),
    ({"participants": [{"name": "A", "kind": "object"}]}, "participants[0].kind: 'lifeline' · 'actor'"),
    ({"participants": life("A"), "lines": []}, "lines: 모르는 필드다"),
    ({"participants": life("A", "B"), "messages": [call("A", "C")]},
     "messages[0].to: 이름이 'C'인 참여자가 없다(있는 참여자: 'A', 'B')"),
    ({"participants": life("A", "B"), "messages": [{"from": "A", "to": "B"}]}, "messages[0]: 호출 메시지는 'name'"),
    ({"participants": life("A", "B"), "messages": [{"from": "A", "to": "B", "name": "x", "kind": "async"}]},
     "messages[0].kind: 'call' · 'reply' · 'create'"),
    ({"participants": life("A", "U", actor=("U",)), "messages": [{"from": "A", "to": "U", "kind": "create"}]},
     "messages[0].to: 액터는 만들 수 없다"),
    ({"participants": life("A", "B"), "messages": [{"from": "A", "to": "B", "kind": "create"}] * 2},
     "messages[1].to: 'B'는 messages[0]에서 이미 만들었다"),
    ({"participants": life("A", "B"), "messages": [call("B", "A"), {"from": "A", "to": "B", "kind": "create"}]},
     "messages[1].to: 'B'는 messages[0]에서 이미 메시지를 주고받았다"),
    ({"participants": life("A", "B"), "messages": [call("A", "B")], "frames": [{"first": 0, "last": 0}]},
     "frames[0]: 'kind' 필드가 빠졌다"),
    ({"participants": life("A", "B"), "messages": [call("A", "B")], "frames": [{"kind": "loop", "first": 0}]},
     "frames[0]: 'last' 필드가 빠졌다"),
    ({"participants": life("A", "B"), "messages": [call("A", "B")] * 2,
      "frames": [{"kind": "loop", "first": 1, "last": 0}]}, "frames[0].last: first(1)보다 앞이다"),
    ({"participants": life("A", "B"), "messages": [call("A", "B")], "frames": [{"kind": "opt", "first": 0, "last": 1}]},
     "frames[0].last: 0~0 사이여야 한다(받은 값 1)"),
    ({"participants": life("A", "B"), "messages": [call("A", "B")],
      "frames": [{"kind": "opt", "first": True, "last": 0.0}]}, "frames[0].first: messages 안의 자리(0부터 센 정수)"),
    ({"participants": life("A"), "frames": [{"kind": "opt", "first": 0, "last": 0}]},
     "frames[0].first: messages가 비어 있어"),
    ({"participants": life("A", "B"), "messages": [call("A", "B")],
      "frames": [{"kind": "opt", "first": 0, "last": 0, "condition": "[x > 0]"}]}, "frames[0].condition: 대괄호 없이"),
    ({"participants": life("A", "B"), "messages": [call("A", "B")],
      "frames": [{"kind": "opt", "first": 0, "last": 0, "condition": " [x] "}]}, "frames[0].condition: 대괄호 없이"),
    ({"participants": life("A", "B"), "messages": [call("A", "B")],
      "frames": [{"kind": "loop", "first": 0, "last": 0, "name": "x"}]}, "frames[0].name: loop 프레임에는 쓰지 않는 필드다"),
    ({"participants": life("A", "B"), "messages": [call("A", "B")],
      "frames": [{"kind": "alt", "branches": [{"condition": "x", "first": 0, "last": 0}]}]},
     "frames[0].branches: alt는 칸이 둘 이상"),
    ({"participants": life("A", "B"), "messages": [call("A", "B")] * 3,
      "frames": [{"kind": "alt", "branches": [{"condition": "x", "first": 0, "last": 0},
                                              {"condition": "y", "first": 2, "last": 2}]}]},
     "frames[0].branches[1].first: 앞 칸이 messages[0]에서 끝나므로 1이어야 한다"),
    ({"participants": life("A", "B"), "messages": [call("A", "B")] * 2,
      "frames": [{"kind": "alt", "branches": [{"first": 0, "last": 0}, {"condition": "y", "first": 1, "last": 1}]}]},
     "frames[0].branches[0]: 'condition' 필드가 빠졌다"),
    ({"participants": life("A", "B"), "messages": [call("A", "B")] * 3,
      "frames": [{"kind": "loop", "first": 0, "last": 1}, {"kind": "opt", "first": 1, "last": 2}]},
     "frames[1]: frames[0]와 덮는 메시지가 겹친다"),
    ({"participants": life("A", "B"), "messages": [call("A", "B")] * 3,
      "frames": [{"kind": "loop", "first": 0, "last": 1}, {"kind": "ref", "name": "R", "before": 1}]},
     "frames[1].before: frames[0](messages[0]~[1]) 안이다"),
    ({"participants": life("A", "B"), "messages": [call("A", "B")], "frames": [{"kind": "ref", "name": "R", "before": 2}]},
     "frames[0].before: 0~1 사이여야 한다"),
    ({"participants": life("A"), "notes": ["ok", 3]}, "notes[1]: 문자열이어야 한다"),
    ({"participants": life("A"), "notes": ["한 줄\n두 줄"]}, "notes[0]: 제어·서식 문자나 줄 나눔"),
    ({"participants": life(*[f"P{i}" for i in range(S.MAX_PARTICIPANTS + 1)])}, "participants: 참여자가 41개다"),
    ({"participants": life("A", "B"), "messages": [call("A", "B")] * (S.MAX_MESSAGES + 1)}, "messages: 메시지가 301개다"),
    ({"participants": life("A"), "frames": [{"kind": "ref", "name": "R", "before": 0}] * (S.MAX_FRAMES + 1)},
     "frames: 프레임이 101개다 — 100개까지 받는다. 그림을 나눈다"),
    ({"participants": life("A"), "notes": ["n"] * (S.MAX_NOTES + 1)}, "notes: 노트가 51개다"),
])
def test_input_problems_point_at_the_field(data, expected):
    assert any(expected in p for p in problems(data)), problems(data)


def test_self_message_is_an_input_error_that_points_to_notes():
    (p,) = problems({"participants": life("A"), "messages": [call("A", "A")]})
    assert p.startswith("messages[0]: 자기 자신('A')에게") and "notes" in p


def test_all_problems_are_reported_together():
    found = problems({"participants": life("A", "B"),
                      "messages": [call("A", "A"), call("A", "Z"), {"from": "A", "to": "B"}],
                      "frames": [{"kind": "ref", "before": 9}], "notes": [""]})
    assert len(found) >= 5


def test_spacing_constants_keep_bar_ends_in_event_order():
    # 막대 밑변을 "몇 번째 일 + 얼마"로 적고 차례만으로 견주는 셈(_after)이 기대는 순서 — 다음 메시지는 앞 일에서 생긴
    # 밑변 후보보다 아래에 놓인다
    assert S.DY >= S.ACT_H >= S.CLEAR
    assert S.FRAME_GAP + S.FRAME_HEAD >= S.ACT_H
    assert S.FRAME_AFTER >= S.EDGE_CLEAR and S.REF_AFTER >= S.EDGE_CLEAR


def test_alt_with_more_branches_than_messages_is_one_problem():
    found = problems({"participants": life("A"), "frames": [{"kind": "alt", "branches": [1] * 1000}]})
    assert list(found) == ["frames[0].branches: 칸이 1000개인데 메시지는 0개다 — 칸마다 메시지가 하나 이상 있어야 한다"]
    found = problems({"participants": life("A", "B"), "messages": [call("A", "B")],
                      "frames": [{"kind": "alt", "branches": [{"condition": "a", "first": 0, "last": 0}] * 2}]})
    assert list(found) == ["frames[0].branches: 칸이 2개인데 메시지는 1개다 — 칸마다 메시지가 하나 이상 있어야 한다"]


def test_a_broken_message_does_not_count_as_using_a_participant():
    found = problems({"participants": life("A", "B"),
                      "messages": [{"from": "A", "to": "B", "kind": "bogus"}, {"from": "A", "to": "B", "kind": "create"}]})
    assert len(found) == 1 and found[0].startswith("messages[0].kind")


def test_overlapping_frames_are_reported_once_each():
    found = problems({"participants": life("A", "B"), "messages": [call("A", "B")],
                      "frames": [{"kind": "loop", "first": 0, "last": 0}] * 5})
    assert list(found) == [f"frames[{i}]: frames[0]와 덮는 메시지가 겹친다 — 프레임 안에 프레임을 넣지 않는다" for i in range(1, 5)]


def test_too_big_drawing_is_an_input_error_before_drawing():
    with pytest.raises(S.InputError) as e:
        S.render({"participants": life("A", "B"), "messages": [call("A", "B", "x" * 40_000), reply("B", "A", "y")]})
    assert "그림이 너무 크다" in str(e.value)


def test_parse_does_not_change_input():
    data = {"participants": life("A", "B"), "messages": [call(" A", "B")], "notes": ["n"]}
    before = copy.deepcopy(data)
    S.render(data)
    assert data == before


# ---------------------------------------------------------------- 활성 막대


def lay_of(participants, messages, frames=(), notes=()):
    return S.render({"participants": participants, "messages": messages, "frames": list(frames),
                     "notes": list(notes)}).layout


def rule_breaks(lay):
    """교류도 검사(sequencecheck)에 걸린 것을 글로."""
    return [f.problem for f in SC.find(lay)]


def test_bar_lasts_until_that_lifeline_replies():
    lay = lay_of(life("A", "B", "C"), [call("A", "B"), call("B", "C"), reply("C", "B"), reply("B", "A")])
    y = [m.y for m in lay.messages]
    (a,), (b,), (c,) = bars_of(lay, "A"), bars_of(lay, "B"), bars_of(lay, "C")
    assert (b.top, b.bottom) == (y[0], y[3])
    assert c.top == y[1] and c.bottom == max(y[2], y[1] + S.ACT_H)
    assert a.top == y[0] and a.bottom >= y[3]


def test_bar_ends_when_the_caller_sends_the_next_message():
    lay = lay_of(life("A", "B", "C"), [call("A", "B"), call("A", "C")])
    y = [m.y for m in lay.messages]
    (b,) = bars_of(lay, "B")
    assert b.bottom == y[0] + S.ACT_H <= y[1]


def test_call_back_into_a_busy_lifeline_nests_a_bar_to_the_right():
    lay = lay_of(life("A", "B"), [call("A", "B"), call("B", "A", "notify()"), reply("A", "B"), reply("B", "A")])
    outer, inner = bars_of(lay, "A")
    assert (outer.depth, inner.depth) == (0, 1)
    assert inner.x == outer.x + S.NEST
    assert outer.top < inner.top and inner.bottom <= outer.bottom
    m = lay.messages[1]
    assert m.end == inner.x + S.ACT_W / 2  # 왼쪽으로 가는 호출은 안쪽 막대의 오른쪽 변에 닿는다


def test_reply_from_a_lifeline_without_a_bar_keeps_the_receivers_bar():
    lay = lay_of(life("A", "B", "C"), [call("A", "B"), reply("C", "A", "r")])
    (a,) = bars_of(lay, "A")
    assert a.top == lay.messages[0].y and a.bottom >= lay.messages[1].y
    assert lay.messages[1].end == a.rect[2]  # 왼쪽으로 가는 반환이 기다리던 막대의 오른쪽 변에 닿는다


def test_frame_starting_with_a_reply_without_a_bar_does_not_cut_waiting_bars():
    messages = [call("A", "B"), call("B", "C"), reply("D", "C", "r"), reply("C", "B"), reply("B", "A")]
    plain = lay_of(life("A", "B", "C", "D"), messages)
    framed = lay_of(life("A", "B", "C", "D"), messages, frames=[{"kind": "opt", "first": 2, "last": 2}])
    assert [b.owner for b in framed.bars] == [b.owner for b in plain.bars] == ["A", "B", "C"]


def test_deeply_nested_bars_stay_inside_the_frame():
    messages = [m for _ in range(12) for m in (call("A", "B", "f"), call("B", "A", "g"))]
    lay = lay_of(life("A", "B"), messages, frames=[{"kind": "loop", "first": 0, "last": len(messages) - 1}])
    f = lay.frames[0]
    assert max(b.rect[2] for b in lay.bars) < f.right


def test_caller_of_an_actor_lasts_as_long_as_the_actors_bar():
    lay = lay_of(life("U", "A", "V", actor=("U", "V")), [call("U", "A", "go()"), call("A", "V", "ask()"), call("U", "A", "again()")])
    a = bars_of(lay, "A")[0]
    (v,) = bars_of(lay, "V")
    assert a.bottom >= v.bottom


def test_called_actor_answers_from_its_bar():
    lay = lay_of(life("A", "V", actor=("V",)), [call("A", "V", "ask()"), reply("V", "A", "ans")])
    (v,) = bars_of(lay, "V")
    m = lay.messages[1]
    assert v.bottom == m.y and m.start == v.rect[0]


def test_actor_bar_lasts_until_it_answers_while_the_caller_works():
    lay = lay_of(life("S", "U", "P", actor=("U",)),
                 [call("S", "U", "confirm()"), call("S", "P", "prepare()"), reply("P", "S", "ready"), reply("U", "S", "yes")])
    (u,) = bars_of(lay, "U")
    yes = lay.messages[3]
    assert u.top == lay.messages[0].y and u.bottom == yes.y and yes.start == u.rect[0]
    assert rule_breaks(lay) == []


def test_caller_waiting_for_an_actor_is_not_cut_by_other_lifelines():
    # 막대 없는 C가 보내면 열린 막대를 모두 닫지만, U의 대답을 기다리는 A는 남는다
    lay = lay_of(life("U", "A", "C", "D", actor=("U",)), [call("A", "U", "ask()"), call("C", "D", "tick()"), reply("U", "A", "ok")])
    (a,), (u,) = bars_of(lay, "A"), bars_of(lay, "U")
    ok = lay.messages[2]
    assert a.top == lay.messages[0].y and a.bottom >= ok.y and ok.start == u.rect[2]
    assert rule_breaks(lay) == []


def test_actor_answers_from_its_bar_even_if_the_caller_returned_first():
    lay = lay_of(life("Z", "A", "U", actor=("U",)), [call("Z", "A", "f()"), call("A", "U", "ask()"), reply("A", "Z"), reply("U", "A", "ok")])
    u = bars_of(lay, "U")[0]
    ok = lay.messages[3]
    assert u.bottom == ok.y and ok.start == u.rect[0]
    assert rule_breaks(lay) == []


def test_caller_waiting_for_an_actor_survives_its_own_callers_return():
    lay = lay_of(life("X", "S", "A", "U", actor=("U",)),
                 [call("X", "S", "f()"), call("S", "A", "g()"), call("A", "U", "ask()"), reply("S", "X"), reply("U", "A", "ok")])
    (a,) = bars_of(lay, "A")
    ok = lay.messages[4]
    assert a.bottom >= ok.y and ok.end == a.rect[2]
    assert rule_breaks(lay) == []


def test_actor_answering_someone_else_keeps_the_receiver_and_the_waiting_caller():
    # U는 A가 불렀는데 B에게 대답한다. B 막대는 끊기지 않고, 기다리던 A 막대는 그 대답까지 이어진다
    lay = lay_of(life("A", "U", "B", "C", actor=("U",)),
                 [call("A", "U", "ask()"), call("B", "C", "work()"), reply("C", "B"), reply("U", "B", "ans")])
    ans = lay.messages[3]
    (a,), (b,) = bars_of(lay, "A"), bars_of(lay, "B")
    assert a.bottom >= ans.y and b.top == lay.messages[1].y and b.bottom >= ans.y and ans.end == b.rect[0]
    assert rule_breaks(lay) == []


def test_trailing_refs_do_not_stretch_bars_under_them():
    lay = lay_of(life("A", "B"), [call("A", "B", "f()")],
                 frames=[{"kind": "ref", "name": "R1", "before": 1}, {"kind": "ref", "name": "R2", "before": 1}])
    assert all(b.bottom <= lay.refs[0].top - S.EDGE_CLEAR for b in lay.bars)


def test_frame_or_ref_right_after_a_message_keeps_away_from_its_line():
    lay = lay_of(life("A", "U", actor=("U",)), [call("A", "U", "ask()"), reply("U", "A", "ok")],
                 frames=[{"kind": "ref", "name": "R", "before": 1}])
    assert lay.refs[0].top - lay.messages[0].y >= S.FRAME_BEFORE


def test_actor_call_without_an_answer_keeps_the_short_bar():
    lay = lay_of(life("S", "U", actor=("U",)), [call("S", "U", "show()"), call("S", "U", "show(again)"), call("U", "S", "click()")])
    first, second = bars_of(lay, "U")
    assert first.bottom == first.top + S.ACT_H and second.bottom == second.top + S.ACT_H


@pytest.mark.parametrize("yes_first", [True, False])
def test_actor_called_before_an_alt_answers_alike_in_every_branch(yes_first):
    # 호출과 대답 사이에 프레임 선이 있으면 막대를 대답까지 잇지 않는다 — 어느 칸이 먼저든 두 대답이 같은 모양이다
    answers = [reply("U", "S", "yes"), reply("U", "S", "no")]
    lay = lay_of(life("S", "U", actor=("U",)), [call("S", "U", "confirm()"), *(answers if yes_first else answers[::-1])],
                 frames=[{"kind": "alt", "branches": [{"condition": "a", "first": 1, "last": 1},
                                                      {"condition": "b", "first": 2, "last": 2}]}])
    assert [m.start for m in lay.messages[1:]] == [lay.participants[1].x] * 2
    (u,) = bars_of(lay, "U")
    assert u.bottom == u.top + S.ACT_H
    assert rule_breaks(lay) == []


@pytest.mark.parametrize("ok_first", [True, False])
def test_actor_answer_inside_one_branch_does_not_depend_on_branch_order(ok_first):
    branches = [[reply("U", "C", "ok")], [call("C", "U", "ask()")]]
    first, second = branches if ok_first else branches[::-1]
    lay = lay_of(life("U", "C", actor=("U",)), [call("C", "U", "prompt()"), *first, *second, call("C", "U", "next()")],
                 frames=[{"kind": "alt", "branches": [{"condition": "a", "first": 1, "last": 1},
                                                      {"condition": "b", "first": 2, "last": 2}]}])
    prompt = bars_of(lay, "U")[0]
    assert prompt.bottom == prompt.top + S.ACT_H


@pytest.mark.parametrize("p_first", [True, False])
def test_ref_right_before_an_alt_does_not_depend_on_branch_order(p_first):
    branches = [[call("B", "C", "p")], [call("A", "B", "q")]]
    first, second = branches if p_first else branches[::-1]
    lay = lay_of(life("A", "B", "C"), [call("A", "B", "m0"), call("B", "C", "m1"), *first, *second, call("A", "B", "after")],
                 frames=[{"kind": "alt", "branches": [{"condition": "a", "first": 2, "last": 2},
                                                      {"condition": "b", "first": 3, "last": 3}]},
                         {"kind": "ref", "name": "R", "before": 2}])
    b0 = bars_of(lay, "B")[0]
    assert b0.bottom > lay.frames[0].bottom  # 어느 칸이 먼저든 B의 첫 막대는 alt를 감싼다
    assert rule_breaks(lay) == []


def test_frames_and_refs_one_after_another_keep_a_gap():
    lay = lay_of(life("A", "B"), [call("A", "B")] * 4,
                 frames=[{"kind": "loop", "first": 0, "last": 1}, {"kind": "opt", "first": 2, "last": 3},
                         {"kind": "ref", "name": "R1", "before": 4}, {"kind": "ref", "name": "R2", "before": 4}])
    loop, opt = lay.frames
    r1, r2 = lay.refs
    assert opt.top - loop.bottom >= S.FRAME_AFTER and r1.top - opt.bottom >= S.FRAME_AFTER
    assert r2.top - r1.bottom >= S.REF_AFTER


def test_actor_called_inside_a_frame_and_answering_after_it_ends_with_the_frame():
    lay = lay_of(life("S", "U", actor=("U",)), [call("S", "U", "confirm()"), reply("U", "S", "yes")],
                 frames=[{"kind": "opt", "first": 0, "last": 0}])
    (u,), f = bars_of(lay, "U"), lay.frames[0]
    assert u.bottom < f.bottom and lay.messages[1].start == lay.participants[1].x
    assert rule_breaks(lay) == []


@pytest.mark.parametrize("frame", [
    {"kind": "loop", "first": 1, "last": 2},
    {"kind": "alt", "branches": [{"condition": "a", "first": 1, "last": 1}, {"condition": "b", "first": 2, "last": 2}]},
])
def test_actor_bar_opened_before_a_frame_ends_before_it(frame):
    lay = lay_of(life("X", "Y", "V", actor=("V",)), [call("X", "V", "ask()"), reply("Y", "V", "a"), reply("Y", "V", "b")],
                 frames=[frame])
    (v,), f = bars_of(lay, "V"), lay.frames[0]
    assert v.bottom <= f.top - S.EDGE_CLEAR
    assert rule_breaks(lay) == []


def test_frame_first_keeps_the_first_message_at_its_usual_height():
    plain = lay_of(life("A", "B"), [call("A", "B", "x")])
    framed = lay_of(life("A", "B"), [call("A", "B", "x")], frames=[{"kind": "loop", "first": 0, "last": 0}])
    assert framed.messages[0].y >= plain.messages[0].y == S.FIRST


def test_actor_gets_a_short_bar_only_when_called():
    lay = lay_of(life("U", "A", actor=("U",)), [call("U", "A"), call("A", "U", "show()"), reply("A", "U")])
    (u,) = bars_of(lay, "U")
    assert (u.top, u.bottom) == (lay.messages[1].y, lay.messages[1].y + S.ACT_H)
    assert lay.messages[0].start == lay.participants[0].x  # 액터는 막대 없이 생명선에서 보낸다


def test_created_lifeline_head_comes_down_to_the_create_message():
    lay = lay_of(life("A", "B"), [{"from": "A", "to": "B", "kind": "create", "name": "B()"}, call("A", "B")])
    m = lay.messages[0]
    b = lay.participants[1]
    assert b.top == m.y - S.HEAD_H / 2 and b.dash_top == m.y + S.HEAD_H / 2
    assert m.end == b.x - b.width / 2
    assert [lab.text for lab in m.labels] == ["«create»", "B()"]
    assert bars_of(lay, "B")[0].top == lay.messages[1].y  # 만드는 메시지는 막대를 열지 않는다


def test_bar_open_when_a_frame_starts_wraps_the_whole_frame():
    lay = lay_of(life("A", "B", "C"), [call("A", "B"), call("B", "C"), reply("C", "B"), call("B", "C"), reply("B", "A")],
                 frames=[{"kind": "loop", "first": 1, "last": 2, "condition": "each"}])
    f = lay.frames[0]
    (b,) = bars_of(lay, "B")
    assert b.top < f.top and b.bottom > f.bottom
    first_c = bars_of(lay, "C")[0]
    assert f.top < first_c.top and first_c.bottom < f.bottom  # 프레임 안에서 연 막대는 안에서 닫는다


def test_bar_open_when_a_frame_starts_ends_where_it_replies_inside():
    lay = lay_of(life("A", "B"), [call("A", "B", "get()"), reply("B", "A"), call("A", "B", "get()"), reply("B", "A")],
                 frames=[{"kind": "loop", "first": 1, "last": 3}])
    first, second = bars_of(lay, "B")
    assert first.bottom == lay.messages[1].y
    assert second.depth == 0 and second.top == lay.messages[2].y  # 다시 부른 것을 겹친 막대로 그리지 않는다


def test_each_alt_branch_starts_from_the_bars_open_at_the_frame():
    # B는 두 칸에서 각각 반환한다 — 첫 칸 반환에서 끝나고, 둘째 칸은 칸 나눔선 아래에서 이어 가는 막대에서 반환한다.
    # C는 첫 칸에서만 반환한다 — 둘째 칸 갈래에서는 아직 일하므로 그 칸에서도 막대가 있다
    lay = lay_of(life("A", "B", "C"), [call("A", "B"), call("B", "C"), reply("C", "B", "ok"), reply("B", "A", "x"),
                                       reply("B", "A", "y")],
                 frames=[{"kind": "alt", "branches": [{"condition": "ok", "first": 2, "last": 3},
                                                      {"condition": "else", "first": 4, "last": 4}]}])
    (divider,) = lay.frames[0].dividers
    b1, b2 = bars_of(lay, "B")
    assert b1.bottom == lay.messages[3].y
    assert b2.top == divider + S.EDGE_CLEAR and b2.bottom == lay.messages[4].y and lay.messages[4].start == b2.rect[0]
    c1, c2 = bars_of(lay, "C")
    assert c1.bottom == lay.messages[2].y and c2.top == divider + S.EDGE_CLEAR
    assert rule_breaks(lay) == []


def test_nested_bars_going_on_in_the_next_branch_stay_nested():
    # A에 겹친 막대가 둘 열린 채 alt가 열리고 첫 칸에서 둘 다 반환한다 — 둘째 칸에서 이어 가는 두 막대도 겹친 채다
    lay = lay_of(life("A", "B"), [call("A", "B"), call("B", "A", "cb()"), reply("A", "B"), reply("A", "B"), reply("A", "B")],
                 frames=[{"kind": "alt", "branches": [{"condition": "x", "first": 2, "last": 3},
                                                      {"condition": "else", "first": 4, "last": 4}]}])
    (divider,) = lay.frames[0].dividers
    going_on = [b for b in bars_of(lay, "A") if b.top == divider + S.EDGE_CLEAR]
    assert sorted(b.depth for b in going_on) == [0, 1]
    assert rule_breaks(lay) == []


def test_reply_after_returning_in_a_branch_leaves_from_the_bare_lifeline():
    lay = lay_of(life("A", "B", "C"), [call("A", "B"), reply("B", "A"), reply("B", "C"), call("B", "C")],
                 frames=[{"kind": "alt", "branches": [{"condition": "x", "first": 1, "last": 2},
                                                      {"condition": "else", "first": 3, "last": 3}]}])
    m = lay.messages[2]
    assert m.start == lay.participants[1].x
    assert not any(b.owner == "B" and b.top <= m.y <= b.bottom for b in lay.bars)
    assert rule_breaks(lay) == []


def test_bar_returned_in_one_branch_goes_on_through_the_others_and_ends_with_the_alt():
    lay = lay_of(life("A", "B", "C"), [call("A", "B"), reply("B", "A", "ok"), call("A", "C", "log()"), reply("B", "A", "late")],
                 frames=[{"kind": "alt", "branches": [{"condition": "x", "first": 1, "last": 1},
                                                      {"condition": "else", "first": 2, "last": 2}]}])
    f, late = lay.frames[0], lay.messages[3]
    b1, b2 = bars_of(lay, "B")
    assert b1.bottom == lay.messages[1].y
    assert b2.top == f.dividers[0] + S.EDGE_CLEAR and b2.bottom == f.bottom - S.EDGE_CLEAR  # 첫 칸에서 반환해 alt와 함께 끝난다
    assert late.start == lay.participants[1].x
    assert rule_breaks(lay) == []


def test_bar_opened_by_a_reply_hands_its_end_only_to_its_caller():
    # D는 반환을 받아 막대를 연다(부른 막대가 없다). 그 막대가 닫힐 때 스택 아래의 B를 늘리지 않는다
    lay = lay_of(life("A", "B", "C", "D", "E"),
                 [call("A", "B", "f"), reply("C", "D", "r"), call("D", "E", "f"), call("D", "E", "f"), call("D", "E", "f"),
                  call("A", "B", "f")])
    first_b = bars_of(lay, "B")[0]
    assert first_b.bottom == lay.messages[0].y + S.ACT_H


def test_callee_kept_by_a_frame_ends_when_its_caller_returns():
    messages = [call("U", "A", "f"), call("A", "B", "f"), call("B", "C", "f"), reply("C", "B"), reply("A", "U")]
    lay = lay_of(life("U", "A", "B", "C", actor=("U",)), messages, frames=[{"kind": "loop", "first": 2, "last": 4}])
    (a,), (b,) = bars_of(lay, "A"), bars_of(lay, "B")
    assert a.bottom == lay.messages[4].y and b.bottom <= lay.messages[4].y + S.CLEAR
    assert rule_breaks(lay) == []


def test_bars_after_an_alt_do_not_depend_on_the_branch_order():
    # B는 한 칸에서만 반환한다 — 어느 칸이 먼저든 B 막대는 alt 안에서 끝나고 그 뒤 B의 호출은 새 막대에서 나간다
    def bars(first, second):
        lay = lay_of(life("A", "B", "C"), [call("A", "B"), first, second, call("B", "C", "g")],
                     frames=[{"kind": "alt", "branches": [{"condition": "x", "first": 1, "last": 1},
                                                          {"condition": "else", "first": 2, "last": 2}]}])
        assert rule_breaks(lay) == []
        f = lay.frames[0]
        return lay, [b for b in bars_of(lay, "B") if b.top < f.bottom], f

    for first, second in ((reply("B", "A"), reply("C", "A")), (reply("C", "A"), reply("B", "A"))):
        lay, inside, f = bars(first, second)
        assert all(b.bottom < f.bottom for b in inside)
        assert bars_of(lay, "B")[-1].top == lay.messages[3].y


@pytest.mark.parametrize("approve_first", [True, False])
def test_alt_branch_order_does_not_change_who_answers_from_a_bar(approve_first):
    # 게이트웨이는 승인 칸에서만 반환한다. 승인이 먼저든 거절이 먼저든 그 반환은 게이트웨이 막대에서 나간다
    approve = [reply("G", "O", "approved"), reply("O", "C", "order")]
    decline = [reply("O", "C", "error")]
    first, second = (approve, decline) if approve_first else (decline, approve)
    lay = lay_of(life("C", "O", "G"), [call("C", "O", "checkout()"), call("O", "G", "charge()"), *first, *second],
                 frames=[{"kind": "alt", "branches": [{"condition": "a", "first": 2, "last": 1 + len(first)},
                                                      {"condition": "b", "first": 2 + len(first), "last": 4}]}])
    m = next(m for m in lay.messages if m.labels and m.labels[0].text == "approved")
    assert any(b.owner == "G" and b.top <= m.y <= b.bottom and m.start == b.rect[0] for b in lay.bars)
    assert rule_breaks(lay) == []


def test_bar_closed_by_the_message_after_a_ref_ends_before_the_ref():
    lay = lay_of(life("A", "B", "C"), [call("A", "B"), call("A", "C")], frames=[{"kind": "ref", "name": "R", "before": 1}])
    (b,), r = bars_of(lay, "B"), lay.refs[0]
    assert b.bottom <= r.top - S.EDGE_CLEAR


def test_brackets_inside_a_condition_are_kept():
    d = S.parse({"participants": life("A", "B"), "messages": [call("A", "B")],
                 "frames": [{"kind": "opt", "first": 0, "last": 0, "condition": "[x] or [y]"}]})
    assert d.fragments[0].branches[0].condition == "[x] or [y]"


def test_reply_to_a_lifeline_without_a_bar_keeps_other_bars():
    lay = lay_of(life("A", "B", "C", "D"), [call("A", "B"), call("B", "C"), reply("C", "D", "r"), reply("B", "A")])
    (a,), (b,) = bars_of(lay, "A"), bars_of(lay, "B")
    assert a.bottom >= lay.messages[3].y and b.bottom == lay.messages[3].y
    assert len(bars_of(lay, "D")) == 1


def test_bar_opened_in_a_frame_is_closed_before_the_frame_ends():
    lay = lay_of(life("A", "B", "C"), [call("A", "B"), call("B", "C")],
                 frames=[{"kind": "opt", "first": 0, "last": 0}])
    f = lay.frames[0]
    first_b = bars_of(lay, "B")[0]
    assert first_b.bottom <= f.bottom - S.EDGE_CLEAR


def test_bars_open_at_a_ref_run_under_it():
    lay = lay_of(life("A", "B"), [call("A", "B"), reply("B", "A")], frames=[{"kind": "ref", "name": "Check", "before": 1}])
    r = lay.refs[0]
    (b,) = bars_of(lay, "B")
    assert b.top < r.top and b.bottom > r.bottom


# ---------------------------------------------------------------- 배치와 그림


def test_long_label_widens_the_gap_and_fits_between_bars():
    name = "processPaymentWithRetry(orderId, amount, currency)"
    lay = lay_of(life("A", "B"), [call("A", "B", name)])
    m = lay.messages[0]
    (box,) = [lab.box for lab in m.labels]
    a_bar, b_bar = bars_of(lay, "A")[0], bars_of(lay, "B")[0]
    assert box[0] >= a_bar.rect[2] + S.LABEL_GAP - 1e-6
    assert box[2] <= b_bar.rect[0] - S.LABEL_GAP - S.TIP_ROOM + 1e-6


def test_label_crossing_a_lifeline_wipes_only_under_itself():
    lay_data = {"participants": life("A", "B", "C"), "messages": [call("A", "C", "a(x)")]}
    d = S.render(lay_data)
    texts = [r for r in d.canvas.records if isinstance(r, Text) and r.owner == "messages[0]"]
    assert texts and all(t.bg for t in texts)
    recs = d.canvas.records
    i = next(k for k, r in enumerate(recs) if isinstance(r, Text) and r.owner == "messages[0]")
    assert isinstance(recs[i - 1], Mask)


def test_label_with_ink_past_its_advance_still_fits_beside_bars():
    # ƴ는 진행 폭보다 오른쪽으로 더 칠해진다 — 칸을 진행 폭으로 재면 B의 끝나지 않은 막대에 글자 상자가 닿았다
    lay = lay_of(life("A", "B", "C"), [call("B", "A", "f"), call("A", "C", "ƴƴƴƴƴ"), reply("C", "A")])
    assert rule_breaks(lay) == []


def test_label_keeps_out_of_a_bar_on_a_lifeline_it_passes():
    # B가 C를 부른 채 A가 C에 반환하면 사이 생명선 B의 막대가 그 높이를 지난다 — 글자는 B를 건너지 않는 칸에 놓는다
    lay = lay_of(life("A", "B", "C"), [call("A", "B"), call("B", "C"), reply("C", "A", "veryLongResultName")])
    m = lay.messages[2]
    (box,) = [lab.box for lab in m.labels]
    for b in lay.bars:
        assert not overlap(box, b.rect, 1), b


def test_frames_share_the_full_width_and_alt_is_split_with_else():
    lay = lay_of(life("A", "B", "C"), [call("A", "B"), call("B", "C"), reply("C", "B"), reply("B", "A")],
                 frames=[{"kind": "opt", "first": 0, "last": 0, "condition": "x"},
                         {"kind": "alt", "branches": [{"condition": "ok", "first": 1, "last": 2},
                                                      {"condition": "else", "first": 3, "last": 3}]},
                         {"kind": "ref", "name": "Done", "before": 4}])
    edges = {(f.left, f.right) for f in lay.frames} | {(r.left, r.right) for r in lay.refs}
    assert len(edges) == 1
    alt = next(f for f in lay.frames if f.fragment.kind == "alt")
    assert len(alt.dividers) == 1 and alt.top < alt.dividers[0] < alt.bottom
    assert [c.text for c in alt.conditions] == ["[ok]", "[else]"]
    assert alt.conditions[1].y == alt.dividers[0] + S.COND_Y


def test_notes_are_collected_below_the_lifelines():
    lay = lay_of(life("A", "B"), [call("A", "B")], notes=["첫째", "둘째"])
    bottom = max(p.bottom for p in lay.participants)
    assert [n.top for n in lay.notes] == [bottom + S.NOTE_GAP, bottom + S.NOTE_GAP + S.NOTE_STEP]
    assert all(n.left == S.LEFT for n in lay.notes)


def test_measured_boxes_follow_a_replaced_layout():
    # 꼬리표·글자·머리·화살촉은 처음 읽을 때 한 번 재 두고, replace로 옮긴 것은 새로 잰다(검사 테스트가 이렇게 옮긴다)
    lay = lay_of(life("U", "A", actor=("U",)), [call("U", "A")],
                 [{"kind": "loop", "first": 0, "last": 0, "condition": "c"}, {"kind": "ref", "name": "R", "before": 1}], ["n"])
    (f,), (r,), (n,), (m,), u = lay.frames, lay.refs, lay.notes, lay.messages, lay.participants[0]
    assert f.tag is f.tag and f.conditions[0].placed is f.conditions[0].placed and n.label is n.label
    assert (f.kind, r.kind, f.covers, r.covers, r.dividers) == ("loop", "ref", False, True, ())
    shift = lambda box: (box[0] + 5, box[1] + 7, box[2] + 5, box[3] + 7)  # noqa: E731
    assert replace(f, left=f.left + 5, top=f.top + 7).tag == shift(f.tag)
    assert replace(r, left=r.left + 5, top=r.top + 7).tag == shift(r.tag)
    assert replace(r.name, x=r.name.x + 5, y=r.name.y + 7).box == shift(r.name.box)
    assert replace(n, left=n.left + 5, top=n.top + 7).label.box == shift(n.label.box)
    assert replace(u, x=u.x + 5, top=u.top + 7).head == shift(u.head)
    assert replace(m, end=m.end + 5, y=m.y + 7).arrow == (m.arrow[0] + 5, m.arrow[1] + 7, m.arrow[2] + 5, m.arrow[3] + 7)


def test_reply_without_name_has_no_label():
    lay = lay_of(life("A", "B"), [call("A", "B"), reply("B", "A")])
    assert lay.messages[1].labels == ()


def test_drawing_kinds_and_order():
    d = S.render({"participants": life("U", "A", "B", actor=("U",)),
                  "messages": [call("U", "A"), {"from": "A", "to": "B", "kind": "create"}, reply("A", "U", "ok")],
                  "frames": [{"kind": "ref", "name": "R", "before": 3}], "notes": ["n"]})
    recs = d.canvas.records
    first = {o: next(i for i, r in enumerate(recs) if r.owner == o) for o in ("A", "frames[0]", "messages[0]", "notes[0]")}
    assert first["A"] < first["frames[0]"] < first["messages[0]"] < first["notes[0]"]
    (ref_box,) = [r for r in recs if isinstance(r, Rect) and r.owner == "frames[0]"]
    assert ref_box.fill == "white"  # ref 상자는 지나는 점선·막대를 덮는다
    call_line, reply_line = (next(r for r in recs if isinstance(r, Line) and r.owner == o) for o in ("messages[0]", "messages[2]"))
    assert call_line.dash is None and reply_line.dash == S.REPLY_DASH
    assert any(isinstance(r, Polygon) and r.owner == "messages[0]" and r.fill == "black" for r in recs)


def test_png_comes_out():
    d = S.render({"participants": life("A", "가나다 서비스"), "messages": [call("A", "가나다 서비스", "조회(아이디)")]})
    img = d.canvas.to_image()
    assert isinstance(img, Image.Image) and img.size[0] > 100 and img.size[1] > 100
