import itertools
import json
import random
from dataclasses import replace

import pytest

from cysuml import classcheck as K
from cysuml import sequencecheck as SC
from cysuml import sequencediagram as S


def life(*names, actor=()):
    return [{"name": n, "kind": "actor" if n in actor else "lifeline"} for n in names]


def call(a, b, name="run()"):
    return {"from": a, "to": b, "name": name}


def reply(a, b, name=None):
    return {"from": a, "to": b, "kind": "reply", **({"name": name} if name else {})}


def kinds(found):
    return [f.kind for f in found]


# ---------------------------------------------------------------- 틀어 둔 배치를 잡는다

BASE = {"participants": life("U", "A", "B", "C", actor=("U",)),
        "messages": [call("U", "A", "order(items)"), call("A", "B", "find(id)"), reply("B", "A", "item"),
                     {"from": "A", "to": "C", "kind": "create", "name": "new"}, reply("A", "U", "ok")],
        "frames": [{"kind": "opt", "first": 1, "last": 2, "condition": "cached"}, {"kind": "ref", "name": "Pay", "before": 4}],
        "notes": ["메모"]}


@pytest.fixture(scope="module")
def base():
    return S.render(BASE).layout


def test_base_drawing_passes_and_has_what_the_cases_change(base):
    assert SC.find(base) == ()
    assert len(base.frames) == 1 and len(base.refs) == 1 and len(base.notes) == 1
    assert base.participants[3].top > 0  # C는 만드는 메시지 높이로 내려온다


def part(lay, name):
    return next(p for p in lay.participants if p.participant.name == name)


def bar(lay, owner):
    return min((b for b in lay.bars if b.owner == owner), key=lambda b: b.top)


def swap(lay, field, old, new):
    return replace(lay, **{field: tuple(new if x is old else x for x in getattr(lay, field))})


def relabel(lay, k, **kw):
    m = lay.messages[k]
    return swap(lay, "messages", m, replace(m, labels=(replace(m.labels[0], **kw),)))


def moved(item, top):
    return replace(item, top=top, bottom=top + item.bottom - item.top)


CASES = {
    "participant_overlap": lambda lay: swap(lay, "participants", part(lay, "B"), replace(part(lay, "B"), x=part(lay, "A").x + 10)),
    "bar_on_participant": lambda lay: swap(lay, "bars", bar(lay, "A"), replace(bar(lay, "A"), top=5)),
    "bar_overlap": lambda lay: replace(lay, bars=lay.bars + (moved(bar(lay, "B"), bar(lay, "B").top + 3),)),
    "bar_off_message": lambda lay: swap(lay, "bars", bar(lay, "B"), replace(bar(lay, "B"), top=bar(lay, "B").top - 2)),
    "message_off_bar": lambda lay: swap(lay, "messages", lay.messages[1], replace(lay.messages[1], end=lay.messages[1].end + 3)),
    "line_at_bar_end": lambda lay: swap(lay, "bars", bar(lay, "B"), replace(bar(lay, "B"), bottom=lay.messages[3].y - 1)),
    "line_overlap": lambda lay: swap(lay, "messages", lay.messages[2], replace(lay.messages[2], y=lay.messages[1].y + 1)),
    "line_through_participant": lambda lay: swap(lay, "participants", part(lay, "B"),
                                          replace(part(lay, "B"), top=lay.messages[3].y - S.HEAD_H / 2)),
    "frame_cuts_bar": lambda lay: swap(lay, "frames", lay.frames[0], replace(lay.frames[0], top=bar(lay, "B").top - 2)),
    "bar_outside_frame": lambda lay: swap(lay, "frames", lay.frames[0], replace(lay.frames[0], right=part(lay, "A").x)),
    "frame_overlap": lambda lay: swap(lay, "refs", lay.refs[0], moved(lay.refs[0], lay.frames[0].bottom - 5)),
    "message_in_ref": lambda lay: swap(lay, "refs", lay.refs[0], moved(lay.refs[0], lay.messages[3].y - 10)),
    "line_on_frame": lambda lay: swap(lay, "frames", lay.frames[0], replace(lay.frames[0], bottom=lay.messages[2].y + 4)),
    "frame_on_participant": lambda lay: swap(lay, "frames", lay.frames[0], replace(lay.frames[0], top=part(lay, "C").top + 10)),
    "tag_on_lifeline": lambda lay: swap(lay, "frames", lay.frames[0], replace(lay.frames[0], left=part(lay, "U").x - 10)),
    "line_through_text": lambda lay: relabel(lay, 1, y=lay.messages[3].y),
    "text_on_bar": lambda lay: relabel(lay, 1, x=part(lay, "A").x),
    "text_on_participant": lambda lay: relabel(lay, 1, x=part(lay, "B").x, y=20),
    "text_on_lifeline": lambda lay: relabel(lay, 1, x=part(lay, "B").x + 10),
    "text_overlap": lambda lay: relabel(lay, 2, x=lay.messages[1].labels[0].x, y=lay.messages[1].labels[0].y + 3),
    "note_covers": lambda lay: swap(lay, "notes", lay.notes[0], replace(lay.notes[0], left=part(lay, "B").x - 20,
                                                                        top=lay.messages[3].y - 10)),
    "text_outside": lambda lay: swap(lay, "notes", lay.notes[0], replace(lay.notes[0], width=20)),
}


def test_every_kind_has_a_case_and_a_hint():
    assert set(CASES) == set(SC.KINDS) == set(SC.HINTS)


@pytest.mark.parametrize("kind", SC.KINDS)
def test_each_kind_is_caught(base, kind):
    found = SC.find(CASES[kind](base))
    assert kind in kinds(found), [f.problem for f in found]
    assert kinds(found) == sorted(kinds(found), key=SC.KINDS.index)


@pytest.mark.parametrize("change", [
    lambda lay: swap(lay, "refs", lay.refs[0], moved(lay.refs[0], part(lay, "C").top + 5)),  # ref 상자가 머리를 가린다
])
def test_ref_box_over_a_head_is_caught(base, change):
    assert "frame_on_participant" in kinds(SC.find(change(base)))


@pytest.mark.parametrize("change, problem", [
    (lambda lay: swap(lay, "frames", lay.frames[0], replace(lay.frames[0], conditions=(
        replace(lay.frames[0].conditions[0], x=lay.frames[0].right - 5),))), "조건 글자가"),
    (lambda lay: swap(lay, "refs", lay.refs[0], replace(lay.refs[0], name=replace(lay.refs[0].name, x=lay.refs[0].left + 20))),
     "ref 이름이"),
])
def test_condition_and_ref_name_outside_their_box_are_caught(base, change, problem):
    found = [f for f in SC.find(change(base)) if f.kind == "text_outside"]
    assert found and found[0].problem.startswith(problem)


def test_message_end_away_from_its_lifeline_is_caught(base):
    # 반환 A→U는 U에 막대가 없어 생명선에서 끝난다 — 조금 비키면 생명선에서 떨어진 끝이다
    m = base.messages[4]
    found = SC.find(swap(base, "messages", m, replace(m, end=m.end + 3)))
    assert any(f.kind == "message_off_bar" and "생명선" in f.problem for f in found)


def test_bar_ending_just_below_a_message_that_ended_nothing_is_cut(base):
    # A의 막대가 opt 윗변을 건너 messages[1] 선에서 CLEAR 아래에 끝난다 — 그 메시지에서 끝난 막대가 없으니 이유 없이 잘린 막대다
    a = bar(base, "A")
    cut = swap(base, "bars", a, replace(a, bottom=base.messages[1].y + S.CLEAR))
    assert any(f.kind == "frame_cuts_bar" and "윗변만" in f.problem for f in SC.find(cut))


def test_frame_side_through_a_label_or_a_message_is_caught(base):
    f = base.frames[0]
    lab = base.messages[1].labels[0]
    found = SC.find(swap(base, "frames", f, replace(f, right=lab.x)))
    assert any(x.kind == "line_through_text" and "오른쪽 변" in x.problem for x in found)
    assert any(x.kind == "line_on_frame" and "오른쪽 변" in x.problem for x in found)


def test_arrowhead_touching_a_head_is_caught(base):
    # B의 머리 밑변을 messages[1] 선 3px 위로 — 선은 머리를 비키지만 화살촉(위아래 ARROW_HALF)이 머리에 닿는다
    b = part(base, "B")
    y = base.messages[1].y
    moved_head = swap(base, "participants", b, replace(b, top=y - 3 - S.HEAD_H, dash_top=y - 3))
    assert any(f.kind == "line_through_participant" and "화살촉" in f.problem for f in SC.find(moved_head))


@pytest.fixture(scope="module")
def callback():
    """C가 B를 되불러 B에 옆으로 비킨 막대(깊이 1)가 생긴다. messages[2]는 그 막대 오른쪽 변에 닿고, messages[3]은 거기서 나간다."""
    return S.render({"participants": life("A", "B", "C"),
                     "messages": [call("A", "B", "f()"), call("B", "C", "g()"), call("C", "B", "cb()"), reply("B", "C"),
                                  reply("C", "B"), reply("B", "A")]}).layout


def test_callback_layout_passes(callback):
    inner = max((b for b in callback.bars if b.owner == "B"), key=lambda b: b.depth)
    assert inner.depth == 1 and callback.messages[2].end == inner.rect[2]
    assert SC.find(callback) == ()


def test_message_end_on_the_far_edge_of_its_bar_is_caught(callback):
    # 오른쪽에서 오는 cb()가 막대를 지나 왼쪽 변에 닿는다 — 선이 막대를 가로지른다
    inner = max((b for b in callback.bars if b.owner == "B"), key=lambda b: b.depth)
    m = callback.messages[2]
    found = SC.find(swap(callback, "messages", m, replace(m, end=inner.rect[0])))
    assert any(f.kind == "message_off_bar" and "맞은편 변" in f.problem for f in found)


def test_message_end_inside_a_deeper_bar_is_caught(callback):
    # B→C 반환을 바깥 막대 오른쪽 변에서 내보내면 그 끝이 위에 그려지는 안쪽 막대 안이다
    outer = min((b for b in callback.bars if b.owner == "B"), key=lambda b: b.depth)
    m = callback.messages[3]
    found = SC.find(swap(callback, "messages", m, replace(m, start=outer.rect[2])))
    assert any(f.kind == "message_off_bar" and "더 옆으로 비킨 막대" in f.problem for f in found)


def test_bar_tail_below_its_last_message_is_caught(base):
    # B의 막대는 반환 item(messages[2])에서 끝난다 — 2px 더 가면 화살표 밑에 꼬리가 남는다
    b = bar(base, "B")
    assert b.bottom == base.messages[2].y
    found = SC.find(swap(base, "bars", b, replace(b, bottom=b.bottom + 2)))
    assert any(f.kind == "bar_off_message" and "꼬리" in f.problem for f in found)


def test_bar_opened_in_an_alt_branch_running_into_the_next_is_caught():
    lay = S.render({"participants": life("A", "B", "C"),
                    "messages": [call("A", "B", "f()"), call("B", "C", "g()"), reply("C", "B"), call("B", "C", "h()"),
                                 reply("C", "B"), reply("B", "A")],
                    "frames": [{"kind": "alt", "branches": [{"condition": "p", "first": 1, "last": 2},
                                                            {"condition": "else", "first": 3, "last": 4}]}]}).layout
    assert SC.find(lay) == ()
    (divider,) = lay.frames[0].dividers
    first = bar(lay, "C")
    assert first.bottom < divider
    found = SC.find(swap(lay, "bars", first, replace(first, bottom=divider + 12)))
    assert any(f.kind == "frame_cuts_bar" and "칸 나눔선" in f.problem for f in found)


def test_frame_lines_too_close_are_caught(base):
    # 프레임 밑변과 ref 윗변이 0.5px — 겹치지 않아도 한 굵은 선으로 보인다
    found = SC.find(swap(base, "refs", base.refs[0], moved(base.refs[0], base.frames[0].bottom + 0.5)))
    assert any(f.kind == "frame_overlap" and "0.5px로 붙는다" in f.problem for f in found)


def test_bars_of_different_lifelines_overlapping_are_caught(base):
    b, a = bar(base, "B"), bar(base, "A")
    found = SC.find(swap(base, "bars", b, replace(b, x=a.x + 5)))
    assert any(f.kind == "bar_overlap" and "다른 생명선" in f.problem for f in found)


def test_message_line_on_a_frame_line_is_caught_without_bars_nearby():
    # 액터끼리 주고받는 반환에는 막대가 없다 — 프레임 선이 막대 끝에 붙어 우연히 걸리는 일이 없다
    lay = S.render({"participants": life("A", "B", actor=("A", "B")), "messages": [reply("A", "B", "x"), reply("B", "A", "y")],
                    "frames": [{"kind": "opt", "first": 0, "last": 0}]}).layout
    assert lay.bars == () and SC.find(lay) == ()
    moved_frame = swap(lay, "frames", lay.frames[0], replace(lay.frames[0], bottom=lay.messages[1].y))
    assert kinds(SC.find(moved_frame)) == ["line_on_frame"]


def test_white_background_of_a_label_counts_as_covering(base):
    # 줄 상자는 막대에서 2px(TEXT_BAR_GAP 넘게) 떨어졌지만, 그 밑에 깐 흰 바탕(잉크 둘레 BG_MARGIN)이 막대 변을 지운다
    a, lab = bar(base, "A"), base.messages[1].labels[0]
    shifted = relabel(base, 1, x=lab.x + (a.rect[2] + 2 - lab.box[0]))
    box = shifted.messages[1].labels[0].box
    assert not SC._overlap(box, a.rect, SC.TEXT_BAR_GAP)
    assert "text_on_bar" in kinds(SC.find(shifted))


def test_white_background_wiping_another_text_is_caught(base):
    # 조건 글자를 꼬리표에서 1px 떨어뜨리면 줄 상자는 안 겹치지만, 조건 밑에 깐 흰 바탕이 꼬리표 테두리를 지운다
    f = base.frames[0]
    (cond,) = f.conditions
    near = swap(base, "frames", f, replace(f, conditions=(replace(cond, x=cond.x + f.tag[2] + 1 - cond.box[0]),)))
    (found,) = [x for x in SC.find(near) if x.kind == "text_overlap"]
    assert "흰 바탕이 다른 글자를 지운다" in found.problem


def test_note_text_is_checked_with_other_texts(base):
    note = base.notes[0].label
    found = SC.find(relabel(base, 1, x=note.box[0] + 20, y=note.y))
    assert ("messages[1]", "notes[0]") in [f.elements for f in found if f.kind == "text_overlap"]


def test_elements_are_input_places(base):
    (f,) = [f for f in SC.find(CASES["participant_overlap"](base)) if f.kind == "participant_overlap"]
    assert f.elements == ("participants[1]", "participants[2]")
    found = SC.find(CASES["text_on_bar"](base))
    assert ("messages[1]", "participants[1]") in [f.elements for f in found if f.kind == "text_on_bar"]


def test_kind_names_shared_with_the_class_check_mean_the_same():
    # 두 검사 결과를 같은 꼴로 돌려주므로, 이름이 같으면 뜻도 같다(선끼리 포개진다·선이 글자를 지난다·글자끼리 겹친다)
    assert set(SC.KINDS) & set(K.KINDS) == {"line_overlap", "line_through_text", "text_overlap"}


# ---------------------------------------------------------------- 걸지 않는 것


def test_label_may_cover_a_lifeline_its_message_crosses():
    # 글자가 A–B·B–C 어느 칸에도 안 들어가 막대 없는 가운데 생명선 B를 건너 놓인다(그 점선은 글자 밑에서 지운다)
    lay = S.render({"participants": life("A", "B", "C"),
                    "messages": [call("A", "C", "processPaymentWithRetry(orderId, amount, currency)")]}).layout
    (lab,) = lay.messages[0].labels
    assert lab.box[0] < part(lay, "B").x < lab.box[2]
    assert SC.find(lay) == ()


def test_condition_may_cover_lifelines():
    # 조건 글자는 꼬리표 오른쪽 같은 줄에 쓰는 자리라 생명선 점선을 지우며 건넌다 — 막대·머리만 비킨다
    lay = S.render({"participants": life("A", "B", "C"), "messages": [reply("A", "B"), reply("B", "C")],
                    "frames": [{"kind": "opt", "first": 0, "last": 1, "condition": "a very long condition for every lifeline"}]}).layout
    (cond,) = lay.frames[0].conditions
    assert all(cond.box[0] < p.x < cond.box[2] for p in lay.participants[1:])
    assert SC.find(lay) == ()


def test_message_line_may_cross_a_bar_in_its_middle():
    # B가 A를 되부른 채 기다리는 동안, 되불린 A가 C를 부르는 선이 B의 막대 가운데를 건넌다
    lay = S.render({"participants": life("A", "B", "C"),
                    "messages": [call("A", "B", "f()"), call("B", "A", "cb()"), call("A", "C", "g()"), reply("C", "A"),
                                 reply("A", "B"), reply("B", "A")]}).layout
    b = bar(lay, "B")
    assert b.top < lay.messages[2].y < b.bottom
    assert SC.find(lay) == ()


# ---------------------------------------------------------------- 결과 형식


def test_passing_report():
    d = S.render(BASE)
    r = SC.check(d)
    assert r.passed and r.failures == ()
    lines = r.summary().splitlines()
    assert lines[0] == SC.Report.PASSED
    assert lines[1].startswith("알림 — 그림 크기: 논리 좌표 ") and len(lines) == 2
    data = json.loads(json.dumps(r.to_dict(), ensure_ascii=False))
    assert set(data) == {"passed", "failures", "size"} and data["passed"] is True


def test_failing_report_says_it_is_a_layout_bug_and_how_to_get_around_it(base):
    canvas = S.render(BASE).canvas
    r = SC.check(S.Drawing(canvas, CASES["text_overlap"](base)))
    lines = r.summary().splitlines()
    assert lines[0].startswith(f"불합격 — {len(r.failures)}건. 교류도는 cysUML이 배치하므로 cysUML의 배치 버그다")
    assert lines[1].startswith("1. ") and lines[1].endswith(SC.HINTS[r.failures[0].kind])
    (f,) = json.loads(json.dumps(r.to_dict(), ensure_ascii=False))["failures"][:1]
    assert set(f) == {"kind", "elements", "where", "problem", "hint"}


@pytest.mark.parametrize("scale", [1.0, S.SCALE, 2.5])
def test_size_is_the_png_the_canvas_draws(scale):
    d = S.render(BASE, scale)
    r = SC.check(d)
    assert r.png_size == d.canvas.to_image().size and r.scale == scale


def test_picture_too_big_for_a_png_has_no_png_size():
    d = S.render(BASE, 1e308)
    r = SC.check(d)
    assert r.png_size is None and r.to_dict()["size"]["png_width"] is None
    assert f"PNG로 그리기에 너무 크다 — {SC.Report.SHRINK}" in r.summary()


# ---------------------------------------------------------------- 조합 테스트: 여러 입력으로 배치 규칙을 시험한다

NAMES = ["A", "Customer", ": Service", ": 주문 서비스", ": VeryLongRepositoryName", "UI", ": Db"]
WORDS = ["get", "save(order)", "find(id)", "check()", "send(phoneNumbers, message)", "조회", "결제 승인(금액)",
         "processPaymentWithRetry(orderId, amount, currency)", "ok", "x", "목록", "ƴƴƴƴƴ", "Ȉ(ƴ)"]  # ƴ·Ȉ는 진행 폭 밖으로 칠해진다


def random_frames(rnd, n, word):
    frames, k = [], 0
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
    return frames


def random_diagram(seed):
    """보내는 쪽·받는 쪽·종류를 따로 뽑는 입력 — 실제로는 드문 짜임까지 고루 나온다."""
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
    frames = random_frames(rnd, len(messages), word)
    return {"participants": parts, "messages": messages, "frames": frames,
            "notes": [word() for _ in range(rnd.randint(0, 2))]}


def nested_diagram(seed):
    """실제 교류도처럼, 불린 쪽이 일하는 동안 더 부르고 부른 차례를 거슬러 돌려주는 입력. 맨 앞 참여자는 액터이기 쉽고, 불린
    액터도 대답하기도 한다."""
    rnd = random.Random(seed)
    word = lambda: rnd.choice(WORDS)  # noqa: E731
    n = rnd.randint(2, 6)
    parts = [{"name": f"{rnd.choice(NAMES)}{i}",
              "kind": "actor" if rnd.random() < (0.6 if i == 0 else 0.1) else "lifeline"} for i in range(n)]
    names = [p["name"] for p in parts]
    actors = [p["name"] for p in parts if p["kind"] == "actor"]
    lifelines = [x for x in names if x not in actors]
    later = rnd.sample(lifelines, rnd.randint(0, min(2, len(names) - 2, len(lifelines))))
    alive = [x for x in names if x not in later]
    waiting = []  # (불린 쪽, 부른 쪽) — 대답할 차례대로 쌓인다
    messages = []
    for _ in range(rnd.randint(1, 18)):
        pending = [x for x in later if x not in alive]
        busy = waiting[-1][0] if waiting else None
        r = rnd.random()
        if pending and r < 0.12:
            dst = rnd.choice(pending)
            messages.append({"from": busy or rnd.choice(alive), "to": dst, "kind": "create",
                             **({"name": word()} if rnd.random() < 0.5 else {})})
            alive.append(dst)
        elif waiting and r < 0.5:
            callee, caller = waiting.pop()
            messages.append(reply(callee, caller, word() if rnd.random() < 0.7 else None))
        else:
            src = busy or rnd.choice(alive)
            dst = rnd.choice([x for x in alive if x != src])
            messages.append(call(src, dst, word()))
            if dst not in actors or rnd.random() < 0.5:
                waiting.append((dst, src))
    return {"participants": parts, "messages": messages, "frames": random_frames(rnd, len(messages), word),
            "notes": [word() for _ in range(rnd.randint(0, 1))]}


def frame_variants(n):
    """메시지 n개에 놓을 수 있는 프레임 배치 전부: 없음, ref 자리마다, loop·opt 범위마다, alt 칸 나누기마다(칸 셋까지), 그리고
    프레임·ref가 잇달아 놓이는 것 하나."""
    yield []
    for k in range(n + 1):
        yield [{"kind": "ref", "name": "Sub", "before": k}]
    for a in range(n):
        for b in range(a, n):
            for kind in ("loop", "opt"):
                yield [{"kind": kind, "first": a, "last": b, "condition": "c"}]
            for r in (1, 2):
                for cuts in itertools.combinations(range(a + 1, b + 1), r):
                    starts, ends = [a, *cuts], [c - 1 for c in cuts] + [b]
                    yield [{"kind": "alt", "branches": [{"condition": f"c{i}", "first": s, "last": e}
                                                        for i, (s, e) in enumerate(zip(starts, ends))]}]
    if n >= 2:
        yield [{"kind": "opt", "first": 0, "last": 0}, {"kind": "ref", "name": "R", "before": 1},
               {"kind": "loop", "first": 1, "last": n - 1}]


def small_diagrams(n_messages, kinds_=("call", "reply", "create"), actor_sets=((), ("A",), ("B",)), frames_of=frame_variants):
    """참여자 셋(액터 자리는 actor_sets)에 메시지 n개의 모든 짝(보내는 쪽·받는 쪽·종류)과 frames_of가 내는 프레임 배치. 틀린
    입력(이미 쓴 참여자를 만들기 등)은 건너뛴다."""
    names = ("A", "B", "C")
    options = [(s, t, k) for s in names for t in names if s != t for k in kinds_]
    for actors in actor_sets:
        parts = life(*names, actor=actors)
        for seq in itertools.product(options, repeat=n_messages):
            msgs = [{"from": s, "to": t, "kind": k, **({"name": WORDS[(i * 5) % len(WORDS)]} if k != "reply" or i % 2 else {})}
                    for i, (s, t, k) in enumerate(seq)]
            for frames in frames_of(n_messages):
                data = {"participants": parts, "messages": msgs, "frames": frames}
                try:
                    yield S.parse(data), data
                except S.InputError:
                    continue


def some_frames(n):
    """frame_variants 가운데 메시지 셋에 고른 것: 없음, 가운데 ref, 전체 opt, 뒤 둘 loop, alt 칸 둘·셋."""
    yield from ([], [{"kind": "ref", "name": "Sub", "before": 1}], [{"kind": "opt", "first": 0, "last": n - 1}],
                [{"kind": "loop", "first": 1, "last": n - 1, "condition": "c"}],
                [{"kind": "alt", "branches": [{"condition": "a", "first": 0, "last": 0}, {"condition": "else", "first": 1, "last": n - 1}]}],
                [{"kind": "alt", "branches": [{"condition": f"c{i}", "first": i, "last": i} for i in range(n)]}])


def failing(diagrams):
    out = []
    for diagram, data in diagrams:
        found = SC.find(S.layout(diagram))
        if found:
            out.append((data, [f.problem for f in found]))
    return out


@pytest.mark.parametrize("seed", range(400))
def test_random_inputs_pass(seed):
    r = SC.check(S.render(random_diagram(seed), scale=0.5))
    assert r.passed, r.summary()


@pytest.mark.parametrize("seed", [1422, 2819, 6427])
def test_random_inputs_that_once_broke_the_rules(seed):
    # 400 밖에서 겹친 막대 깊이가 같게 나오던 입력(alt 칸에서 이어 가는 막대·반환으로 연 막대가 겹친다)
    assert SC.find(S.layout(S.parse(random_diagram(seed)))) == ()


@pytest.mark.parametrize("seed", range(400))
def test_nested_inputs_pass(seed):
    r = SC.check(S.render(nested_diagram(seed), scale=0.5))
    assert r.passed, r.summary()


def test_every_two_message_diagram_passes():
    cases = list(small_diagrams(2))
    assert len(cases) > 8000
    assert failing(cases) == []


def test_every_three_message_call_and_reply_passes():
    cases = list(small_diagrams(3, ("call", "reply"), ((), ("A",)), some_frames))
    assert len(cases) > 15_000
    assert failing(cases) == []


def test_generated_inputs_cover_the_interesting_cases():
    seen = set()
    for seed in range(400):
        for make in (random_diagram, nested_diagram):
            lay = S.layout(S.parse(make(seed)))
            seen |= {f.fragment.kind for f in lay.frames} | ({"ref"} if lay.refs else set())
            seen |= {"nested"} if any(b.depth for b in lay.bars) else set()
            seen |= {"create"} if any(m.message.kind == "create" for m in lay.messages) else set()
            seen |= {"crossing"} if any(lab.box[0] < p.x < lab.box[2] for m in lay.messages for lab in m.labels
                                        for p in lay.participants) else set()
            seen |= {"actor answers"} if any(m.message.kind == "reply" and p.participant.kind == "actor"
                                             and p.participant.name == m.message.source
                                             for m in lay.messages for p in lay.participants) else set()
    assert seen >= {"loop", "opt", "alt", "ref", "nested", "create", "crossing", "actor answers"}


@pytest.mark.parametrize("seed", range(0, 400, 40))
def test_random_inputs_draw(seed):
    d = S.render(random_diagram(seed), scale=0.5)
    assert d.canvas.to_image().size[0] > 0
