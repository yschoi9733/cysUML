import copy
import random

import pytest
from PIL import Image

from cysuml import sequencediagram as S
from cysuml import text as T
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
     "frames: 프레임이 101개다 — 100개까지 그린다. 그림을 나눈다"),
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


def test_alt_branches_are_alternatives_for_bars_kept_from_before():
    # B는 두 칸에서 각각 반환한다 — 앞 칸 반환에서 끊기지 않고 뒤 칸 반환까지 잇는다. C는 첫 칸에서만 반환해 거기서 끝난다
    lay = lay_of(life("A", "B", "C"), [call("A", "B"), call("B", "C"), reply("C", "B", "ok"), reply("B", "A", "x"),
                                       reply("B", "A", "y")],
                 frames=[{"kind": "alt", "branches": [{"condition": "ok", "first": 2, "last": 3},
                                                      {"condition": "else", "first": 4, "last": 4}]}])
    (b,), (c,) = bars_of(lay, "B"), bars_of(lay, "C")
    assert b.bottom == lay.messages[4].y and lay.messages[4].start == b.rect[0]
    assert c.bottom == lay.messages[2].y


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


# ---------------------------------------------------------------- 여러 입력으로 배치 규칙 확인

NAMES = ["A", "Customer", ": Service", ": 주문 서비스", ": VeryLongRepositoryName", "UI", ": Db"]
WORDS = ["get", "save(order)", "find(id)", "check()", "send(phoneNumbers, message)", "조회", "결제 승인(금액)",
         "processPaymentWithRetry(orderId, amount, currency)", "ok", "x", "목록", "ƴƴƴƴƴ", "Ȉ(ƴ)"]  # ƴ·Ȉ는 진행 폭 밖으로 칠해진다


def random_diagram(seed):
    rnd = random.Random(seed)
    word = lambda: rnd.choice(WORDS)  # noqa: E731
    parts = []
    for i in range(rnd.randint(1, 6)):
        parts.append({"name": f"{rnd.choice(NAMES)}{i}", "kind": "actor" if rnd.random() < 0.2 else "lifeline"})
    lifelines = [p["name"] for p in parts if p["kind"] == "lifeline"]
    later = set(rnd.sample(lifelines, min(len(lifelines), rnd.randint(0, 2))))
    alive = [p["name"] for p in parts if p["name"] not in later]
    messages = []
    for _ in range(rnd.randint(0, 16)):
        pending = [n for n in lifelines if n in later and n not in alive]
        if alive and pending and (len(alive) < 2 or rnd.random() < 0.2):
            dst = rnd.choice(pending)
            messages.append({"from": rnd.choice(alive), "to": dst, "kind": "create",
                             **({"name": word()} if rnd.random() < 0.6 else {})})
            alive.append(dst)
            continue
        if len(alive) < 2:
            break
        src, dst = rnd.sample(alive, 2)
        if rnd.random() < 0.4:
            messages.append({"from": src, "to": dst, "kind": "reply", **({"name": word()} if rnd.random() < 0.8 else {})})
        else:
            messages.append(call(src, dst, word()))
    frames, k, n = [], 0, len(messages)
    while k < n:
        if rnd.random() < 0.35:
            length = rnd.randint(1, min(5, n - k))
            kind = rnd.choice(["loop", "opt", "alt"] if length >= 2 else ["loop", "opt"])
            if kind == "alt":
                cuts = sorted(rnd.sample(range(k + 1, k + length), min(length - 1, rnd.randint(1, 2))))
                starts = [k, *cuts]
                ends = [c - 1 for c in cuts] + [k + length - 1]
                branches = [{"condition": word(), "first": a, "last": b} for a, b in zip(starts, ends)]
                if rnd.random() < 0.5:
                    branches[-1]["condition"] = "else"
                frames.append({"kind": "alt", "branches": branches})
            else:
                frames.append({"kind": kind, "first": k, "last": k + length - 1,
                               **({"condition": word()} if rnd.random() < 0.7 else {})})
            k += length
        else:
            if rnd.random() < 0.15:
                frames.append({"kind": "ref", "name": word(), "before": k})
            k += 1
    if rnd.random() < 0.2:
        frames.append({"kind": "ref", "name": word(), "before": n})
    rnd.shuffle(frames)
    return {"participants": parts, "messages": messages, "frames": frames,
            "notes": [word() for _ in range(rnd.randint(0, 2))]}


def arrow_box(m):
    sign = 1 if m.end > m.start else -1
    return min(m.end, m.end - sign * S.ARROW), m.y - S.ARROW_HALF, max(m.end, m.end - sign * S.ARROW), m.y + S.ARROW_HALF


def crosses(y0, y1, x0, x1, box):
    """가로 선분이 상자 안을 지나는지(변에 닿는 것은 치지 않는다)."""
    return box[1] < y0 < box[3] and x0 < box[2] and box[0] < x1


def attached(m, b, x):
    return abs(x - b.rect[0]) < 1e-6 or abs(x - b.rect[2]) < 1e-6


def rule_breaks(lay):
    """기존 코드의 배치 테스트(그린 기록을 읽어 보던 규칙)를 배치 결과로 본다. 걸린 것을 글로 돌려준다."""
    out = []
    labels = [(m.owner, lab.box) for m in lay.messages for lab in m.labels]
    conds = [(f.owner, lab.box) for f in lay.frames for lab in f.conditions]
    texts = labels + conds + [(r.owner, r.name.box) for r in lay.refs]
    heads = [(p.participant.name, p.head) for p in lay.participants]
    edges = [(f.owner, y) for f in lay.frames for y in (f.top, f.bottom, *f.dividers)] + \
        [(r.owner, y) for r in lay.refs for y in (r.top, r.bottom)]
    right = max([f.right for f in lay.frames] + [r.right for r in lay.refs], default=None)
    for o, box in labels + conds:
        out += [f"{o} 글자가 {b.owner} 막대에 닿는다" for b in lay.bars if overlap(box, b.rect, 1)]
        out += [f"{o} 글자가 {h} 머리에 닿는다" for h, hb in heads if overlap(box, hb)]
    for i, (o, a) in enumerate(texts):
        out += [f"{o}·{p} 글자가 겹친다" for p, b in texts[i + 1:] if overlap(a, b)]
    for m in lay.messages:
        x0, x1 = sorted((m.start, m.end))
        out += [f"{m.owner} 선이 {o} 글자를 지난다" for o, box in texts if crosses(m.y, m.y, x0, x1, box)]
        out += [f"{m.owner} 선이 {h} 머리를 지난다" for h, hb in heads if crosses(m.y, m.y, x0, x1, hb)]
        out += [f"{m.owner} 화살촉이 {o} 글자에 닿는다" for o, box in labels if o != m.owner and overlap(arrow_box(m), box)]
        for b in lay.bars:
            if b.rect[0] < x1 and x0 < b.rect[2] and not (b.top <= m.y <= b.bottom and attached(m, b, m.start)) \
                    and not (b.top <= m.y <= b.bottom and attached(m, b, m.end)):
                out += [f"{m.owner} 선이 {b.owner} 막대 끝을 지난다" for end in (b.top, b.bottom) if abs(m.y - end) < S.CLEAR - 1e-6]
        for x in (m.start, m.end):
            inside = [b for b in lay.bars if b.top <= m.y <= b.bottom and b.rect[0] - 0.6 <= x <= b.rect[2] + 0.6]
            if inside and not any(attached(m, b, x) for b in inside):
                out.append(f"{m.owner} 선 끝 {x}가 막대 변에 닿지 않는다")
    for o, y in edges:
        out += [f"{o} 가로 선이 글자 {t}를 지난다" for t, box in texts if t != o and crosses(y, y, -1e9, 1e9, box)]
        out += [f"{o} 가로 선이 {h} 머리를 지난다" for h, hb in heads if crosses(y, y, -1e9, 1e9, hb)]
        for b in lay.bars:
            out += [f"{o} 가로 선이 {b.owner} 막대 끝에 붙었다" for end in (b.top, b.bottom) if abs(y - end) < S.EDGE_CLEAR - 1e-6]
    for f in [*lay.frames, *lay.refs]:
        for b in lay.bars:
            over_top, over_bottom = b.top < f.top < b.bottom, b.top < f.bottom < b.bottom
            returns = any(m.message.kind == "reply" and m.y == b.bottom and attached(m, b, m.start) for m in lay.messages)
            if over_bottom and not over_top or over_top and not over_bottom and not returns:
                out.append(f"{f.owner}가 {b.owner} 막대를 자른다")
            if not (f.left < b.rect[0] and b.rect[2] < f.right):
                out.append(f"{b.owner} 막대가 {f.owner} 옆 변 밖으로 나간다")
        tag = S._tag_width(f.fragment.kind if isinstance(f, S.PlacedFrame) else "ref")
        out += [f"{f.owner} 꼬리표 밑으로 {p.participant.name} 생명선이 지난다"
                for p in lay.participants if f.left <= p.x <= f.left + tag]
    for r in lay.refs:
        out += [f"{m.owner}가 {r.owner} 상자 안에 있다" for m in lay.messages if r.top - S.PAD < m.y < r.bottom + S.PAD]
        box = r.name.box
        if not (r.left + S._tag_width("ref") < box[0] and box[2] < r.right and r.top < box[1] and box[3] < r.bottom):
            out.append(f"{r.owner} 이름이 상자 밖이나 꼬리표에 닿는다")
    for o, box in conds:
        if right is not None and box[2] > right:
            out.append(f"{o} 조건 글자가 프레임 밖으로 나간다")
    for n in lay.notes:
        box = T.place(n.left + S.NOTE_TEXT_X, n.top + n.height / 2, n.text).box
        if box[2] > n.left + n.width - S.NOTE_FOLD or box[1] < n.top or box[3] > n.top + n.height:
            out.append(f"{n.owner} 글자가 노트 밖으로 나간다")
    by_life = {}
    for b in lay.bars:
        by_life.setdefault((b.owner, b.depth), []).append(b)
    for (owner, _), bs in by_life.items():
        bs.sort(key=lambda b: b.top)
        out += [f"{owner} 막대가 붙거나 겹친다" for a, b in zip(bs, bs[1:]) if b.top < a.bottom + S.BAR_GAP - 1e-6]
    for i, (h, a) in enumerate(heads):
        out += [f"{h}·{g} 머리가 겹친다" for g, b in heads[i + 1:] if overlap(a, b)]
    return out


@pytest.mark.parametrize("seed", range(400))
def test_random_inputs_keep_the_layout_rules(seed):
    data = random_diagram(seed)
    lay = S.layout(S.parse(data))
    assert rule_breaks(lay) == [], data


def test_random_inputs_cover_the_interesting_cases():
    seen = set()
    for seed in range(400):
        lay = S.layout(S.parse(random_diagram(seed)))
        seen |= {f.fragment.kind for f in lay.frames} | ({"ref"} if lay.refs else set())
        seen |= {"nested"} if any(b.depth for b in lay.bars) else set()
        seen |= {"create"} if any(m.message.kind == "create" for m in lay.messages) else set()
        seen |= {"crossing"} if any(lab.text for m in lay.messages for lab in m.labels
                                    for p in lay.participants if lab.box[0] < p.x < lab.box[2]) else set()
    assert seen >= {"loop", "opt", "alt", "ref", "nested", "create", "crossing"}


@pytest.mark.parametrize("seed", range(0, 400, 40))
def test_random_inputs_draw(seed):
    d = S.render(random_diagram(seed), scale=0.5)
    assert d.canvas.to_image().size[0] > 0
