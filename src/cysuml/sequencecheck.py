"""교류도 검사: 그린 결과(sequencediagram.Drawing)를 읽어 합격·불합격과 알림을 낸다.

교류도는 도구가 배치하므로 불합격은 cysUML의 배치 버그다. 그래도 그 그림을 쓸 수 있게, 항목마다 입력에서 무엇을 바꾸면 비켜
가는지(참여자 순서, 글자 줄이기, 그림 나누기)를 힌트로 준다 — 교류도는 좌표를 받지 않으므로 "어디로 옮겨라"가 아니다.

그리기(draw)는 배치 결과를 그대로 옮겨 그리므로 배치 결과(Drawing.layout)로 본다. 불합격 종류는 KINDS에 낸 차례대로 있고,
그림 크기는 알림으로만 준다. 종류 이름은 뜻이 다르면 클래스도 검사(classcheck.KINDS)와 겹치지 않게 짓는다.

글자는 줄 상자와, 흰 바탕을 까는 글자(메시지 글자·조건)면 그 바탕이 지우는 곳(잉크 둘레 BG_MARGIN)까지 차지한 것으로 본다. 메시지
선이 사이 생명선의 점선을 건너는 것은 UML 그대로라 걸지 않는다. 메시지 글자도 그 메시지가 건너는 생명선은 가려도 되고(글자 밑 점선을
지운다), 그 밖의 생명선을 가리면 건다. 프레임 조건 글자는 프레임 윗변·칸 나눔선 바로 밑, 꼬리표 오른쪽에 쓰는 자리라 생명선 점선을
지우며 건너도 된다 — 막대·머리만 비킨다.

"프레임이 막대를 자르지 않는다"는 막대 끝이 프레임 가로 선에 붙지 않는다는 것과, 막대가 프레임 윗변·밑변 가운데 하나만 건너 프레임
안에서 끝나거나 시작하지 않는다는 것으로 본다. 다만 프레임 안 메시지 높이(에서 CLEAR 아래까지)에서 끝나는 막대는 윗변만 건너도
된다 — 그 생명선이나 부른 쪽이 반환해 끝난 것이다.

요소 이름(Finding.elements)은 입력 안의 자리다 — participants[i]·messages[k]·frames[i]·notes[j]. 막대는 그 생명선의 참여자로
가리킨다.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterator, Union

from . import text as T
from .canvas import BG_MARGIN
from .geom import Box, between, grow
from .report import Finding, fmt_num, fmt_rect
from .report import Report as _Report
from .sequencediagram import (ARROW_HALF, BAR_GAP, CLEAR, EDGE_CLEAR, NOTE_FOLD, PAD, Drawing, Label, Layout, PlacedBar,
                              PlacedFrame, PlacedMessage, PlacedParticipant, PlacedRef)

EPS = 1e-6
TEXT_BAR_GAP = 1  # 글자가 차지한 곳과 막대 사이가 이만큼 안이면 글자가 막대를 가린 것으로 본다
END_SNAP = 0.6    # 메시지 선 끝이 막대 변에서 이만큼 안이면 그 막대에 닿으려던 끝으로 본다(변에 딱 맞아야 한다)
FRAME_LINE_CLEAR = ARROW_HALF + PAD  # 메시지 선과 프레임 가로 선 사이 — 화살촉도 프레임 선에서 PAD 넘게 떨어진다

KINDS = (  # 불합격 종류(이 차례로 낸다)
    "participant_overlap",       # 머리끼리 겹친다
    "bar_on_participant",        # 막대가 머리에 걸친다
    "bar_overlap",               # 한 생명선의 막대끼리 겹치거나 붙는다
    "message_off_bar",           # 메시지 선 끝이 막대 변(그 높이에 막대가 없으면 생명선)에 닿지 않는다
    "line_at_bar_end",           # 메시지 선이 건너는 막대의 윗변·밑변에 붙는다
    "line_through_participant",  # 메시지 선이 머리를 지난다
    "frame_cuts_bar",            # 프레임이 막대를 자른다
    "bar_outside_frame",         # 막대가 프레임 옆 변 밖으로 나간다
    "frame_overlap",             # 프레임·ref끼리 겹치거나 붙는다
    "message_in_ref",            # 메시지가 ref 상자 안에 있거나 테두리에 붙는다
    "line_on_frame",             # 메시지 선·화살촉이 프레임 가로 선에 붙는다
    "frame_on_participant",      # 프레임 가로 선이 머리를 지나거나 ref 상자가 머리를 가린다
    "tag_on_lifeline",           # 프레임 꼬리표가 생명선을 가린다
    "line_through_text",         # 메시지 선·화살촉·프레임 가로 선이 글자를 지난다
    "text_on_bar",               # 글자가 막대를 가린다
    "text_on_participant",       # 글자가 머리에 겹친다
    "text_on_lifeline",          # 메시지 글자가 그 메시지가 건너지 않는 생명선을 가린다
    "text_overlap",              # 글자끼리 겹치거나 한 글자의 흰 바탕이 다른 글자를 지운다
    "text_outside",              # 조건·ref 이름·노트 글자가 제 프레임·상자·노트 밖으로 나간다
)

FRAME_HINT = "프레임이 덮는 메시지 범위(first·last·칸)를 바꾸거나, 프레임을 빼고 그림을 나눈다."
TEXT_HINT = "그 글자를 줄이거나 참여자 순서를 바꾼다."
HINTS = {
    "participant_overlap": "참여자 이름을 줄인다.",
    "bar_on_participant": "참여자 순서를 바꾸거나, 만드는 메시지(create)의 차례를 바꾼다.",
    "bar_overlap": "그 생명선을 부르는 메시지의 차례를 바꾸거나 그림을 나눈다.",
    "message_off_bar": "메시지 차례를 바꾸거나 그림을 나눈다.",
    "line_at_bar_end": "참여자 순서를 바꿔 이 메시지가 건너는 생명선을 줄이거나, 메시지 차례를 바꾼다.",
    "line_through_participant": "참여자 순서를 바꿔 이 메시지가 건너는 생명선을 줄인다.",
    "frame_cuts_bar": FRAME_HINT,
    "bar_outside_frame": FRAME_HINT,
    "frame_overlap": FRAME_HINT,
    "message_in_ref": "ref 자리(before)를 바꾸거나 그림을 나눈다.",
    "line_on_frame": FRAME_HINT,
    "frame_on_participant": "만드는 메시지(create)를 프레임·ref 밖으로 옮기거나 프레임 범위를 바꾼다.",
    "tag_on_lifeline": "프레임을 빼고 그림을 나눈다.",
    "line_through_text": TEXT_HINT,
    "text_on_bar": TEXT_HINT,
    "text_on_participant": TEXT_HINT,
    "text_on_lifeline": TEXT_HINT,
    "text_overlap": TEXT_HINT,
    "text_outside": "그 글자를 줄인다(노트는 둘로 나눠도 된다).",
}


@dataclass(frozen=True)
class Report(_Report):
    """report.Report 그대로다. 교류도에는 크기 밖의 알림이 없다."""

    PASSED = "합격 — 선·글자·막대·프레임이 서로 가리거나 겹친 곳이 없다."
    FAILED = (". 교류도는 cysUML이 배치하므로 cysUML의 배치 버그다 — 항목마다 끝의 힌트대로 입력을 바꾸면 비켜 갈 수 있다.")
    SHRINK = "참여자 이름·메시지 글자를 줄이거나, 그림을 나누거나, 배율을 낮춘다"


@dataclass(frozen=True)
class _Text:
    """한 줄 글자나 꼬리표. element는 입력 안의 자리, box는 줄 상자(꼬리표는 그 다각형을 덮는 상자), ink는 칠한 곳(없으면 box),
    area는 이 글자가 차지한 곳 — 흰 바탕을 깐 글자는 잉크 둘레 BG_MARGIN까지 지우므로 그만큼 넓다. over_bars는 막대·머리 위에
    놓이는지다(ref 이름·꼬리표는 흰 ref 상자가 그 밑을 덮으므로 아니다). message는 메시지 글자면 그 메시지 자리다."""

    element: str
    title: str
    box: Box
    ink: Box
    area: Box
    over_bars: bool
    message: int = -1


Framed = Union[PlacedFrame, PlacedRef]


def check(drawing: Drawing) -> Report:
    measured = drawing.canvas.measure()
    if measured is None:
        raise ValueError("그린 것이 없다")
    return Report(find(drawing.layout), measured.size, measured.png, drawing.canvas.scale)


def find(layout: Layout) -> tuple[Finding, ...]:
    """배치 결과에서 불합격 항목을 KINDS 차례로 찾는다(check가 쓴다)."""
    scene = _Scene(layout)
    failures = [f for rule in scene.RULES for f in rule(scene)]
    failures.sort(key=lambda f: KINDS.index(f.kind))
    return tuple(failures)


def _overlap(a: Box, b: Box, pad: float = 0.0) -> bool:
    """두 상자가 pad만큼 넓혀 겹치는지(맞닿는 것은 치지 않는다)."""
    return (a[0] - pad < b[2] - EPS and b[0] < a[2] + pad - EPS
            and a[1] - pad < b[3] - EPS and b[1] < a[3] + pad - EPS)


def _crosses(y: float, x0: float, x1: float, box: Box) -> bool:
    """가로 선분이 상자 안을 지나는지(변에 닿는 것은 치지 않는다)."""
    return box[1] + EPS < y < box[3] - EPS and x0 < box[2] - EPS and box[0] + EPS < x1


def _hull(a: Box, b: Box) -> Box:
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


def _on(x: float, v: float) -> bool:
    return abs(x - v) <= EPS


def _holds(b: PlacedBar, y: float) -> bool:
    return b.top - EPS <= y <= b.bottom + EPS


def _attached(m: PlacedMessage, b: PlacedBar) -> bool:
    """메시지 선 끝이 그 막대 변에 닿는지."""
    return _holds(b, m.y) and any(_on(x, b.rect[0]) or _on(x, b.rect[2]) for x in (m.start, m.end))


def _message(m: PlacedMessage) -> str:
    return f"메시지 {m.owner}" + (f" '{m.message.name}'" if m.message.name else "")


def _frame(f: Framed) -> str:
    return f"ref {f.owner}" if isinstance(f, PlacedRef) else f"프레임 {f.owner}({f.fragment.kind})"


def _label(element: str, what: str, lab: Label, bg: bool, over_bars: bool, message: int = -1) -> _Text:
    """bg면 Canvas.text처럼 잉크 둘레 BG_MARGIN을 흰 바탕으로 지운 글자다."""
    p = T.place(lab.x, lab.y, lab.text, False, lab.anchor)
    ink = p.ink or p.box
    area = _hull(p.box, grow(p.ink, BG_MARGIN)) if bg and p.ink else p.box
    return _Text(element, f"{what} '{lab.text}'(자리 {fmt_rect(p.box)})", p.box, ink, area, over_bars, message)


def _tag(f: Framed, over_bars: bool) -> _Text:
    return _Text(f.owner, f"{_frame(f)}의 꼬리표(자리 {fmt_rect(f.tag)})", f.tag, f.tag, f.tag, over_bars)


class _Scene:
    def __init__(self, lay: Layout):
        self.lay = lay
        self.parts = lay.participants
        self.index = {p.participant.name: i for i, p in enumerate(self.parts)}
        self.framed: list[Framed] = sorted([*lay.frames, *lay.refs], key=lambda f: f.top)
        texts = []
        for k, m in enumerate(lay.messages):
            texts += [_label(m.owner, f"{_message(m)}의 글자", lab, True, True, k) for lab in m.labels]
        for f in lay.frames:
            texts.append(_tag(f, True))
            texts += [_label(f.owner, f"{_frame(f)}의 조건", lab, True, True) for lab in f.conditions]
        for r in lay.refs:
            texts += [_tag(r, False), _label(r.owner, f"{_frame(r)}의 이름", r.name, False, False)]
        texts += [_label(n.owner, f"노트 {n.owner}의 글자", n.label, False, True) for n in lay.notes]
        self.texts = texts

    # -------- 이름

    def who(self, name: str) -> str:
        return f"participants[{self.index[name]}]"

    def head(self, p: PlacedParticipant) -> str:
        return f"참여자 '{p.participant.name}'의 머리(자리 {fmt_rect(p.head)})"

    @staticmethod
    def bar(b: PlacedBar) -> str:
        return f"참여자 '{b.owner}'의 막대(자리 {fmt_rect(b.rect)})"

    @staticmethod
    def found(kind: str, elements, where: Box, problem: str) -> Finding:
        return Finding(kind, tuple(dict.fromkeys(elements)), where, problem, HINTS[kind])

    # -------- 머리·막대

    def participant_overlaps(self) -> Iterator[Finding]:
        for i, a in enumerate(self.parts):
            for j in range(i + 1, len(self.parts)):
                b = self.parts[j]
                if _overlap(a.head, b.head):
                    yield self.found("participant_overlap", (f"participants[{i}]", f"participants[{j}]"),
                                     between(a.head, b.head), f"머리끼리 겹친다: {self.head(a)}, {self.head(b)}.")

    def bars_on_participants(self) -> Iterator[Finding]:
        for b in self.lay.bars:
            for i, p in enumerate(self.parts):
                if _overlap(b.rect, p.head):
                    yield self.found("bar_on_participant", (self.who(b.owner), f"participants[{i}]"), between(b.rect, p.head),
                                     f"막대가 머리에 걸친다: {self.bar(b)}, {self.head(p)}.")

    def bar_overlaps(self) -> Iterator[Finding]:
        groups: dict[tuple[str, int], list[PlacedBar]] = defaultdict(list)
        for b in self.lay.bars:
            groups[(b.owner, b.depth)].append(b)
        for (owner, _), bars in groups.items():
            bars.sort(key=lambda b: b.top)
            for i, a in enumerate(bars):
                for b in bars[i + 1:]:
                    if b.top < a.bottom + BAR_GAP - EPS:
                        what = ("겹친다" if b.top < a.bottom - EPS else "맞닿았다" if b.top <= a.bottom + EPS
                                else f"{fmt_num(b.top - a.bottom)}px밖에 떨어지지 않았다")
                        yield self.found("bar_overlap", (self.who(owner),), between(a.rect, b.rect),
                                         f"한 생명선의 막대끼리 {what}(같은 깊이는 {BAR_GAP}px 넘게 떨어져야 한다): "
                                         f"{self.bar(a)}, {self.bar(b)}.")

    # -------- 메시지 선

    def message_ends(self) -> Iterator[Finding]:
        """선 끝은 그 높이에 그 생명선의 막대가 있으면 그 막대 변에, 없으면 생명선에 닿는다. 만드는 메시지의 화살촉은 만들어지는
        머리 변에 닿는다. 그 밖에 어느 막대 안이나 변 바로 앞에서 멈추는 끝도 건다."""
        for m in self.lay.messages:
            for which, x, name in (("시작", m.start, m.message.source), ("끝", m.end, m.message.target)):
                p = self.parts[self.index[name]]
                at = f"{_message(m)}의 선 {which}(x {fmt_num(x)}, y {fmt_num(m.y)})"
                elements = (m.owner, self.who(name))
                where = (x, m.y, x, m.y)
                if which == "끝" and m.message.kind == "create":
                    h = p.head
                    if not (h[1] <= m.y <= h[3] and (_on(x, h[0]) or _on(x, h[2]))):
                        yield self.found("message_off_bar", elements, where, f"{at}이 만들어지는 머리 변에 닿지 않는다: "
                                                                            f"{self.head(p)}.")
                    continue
                if not p.dash_top - EPS <= m.y <= p.bottom + EPS:
                    yield self.found("message_off_bar", elements, where,
                                     f"{at}이 참여자 '{name}'의 생명선 밖에 있다(생명선은 y {fmt_num(p.dash_top)}~"
                                     f"{fmt_num(p.bottom)}).")
                    continue
                own = [b for b in self.lay.bars if b.owner == name and _holds(b, m.y)]
                if own and not any(_on(x, b.rect[0]) or _on(x, b.rect[2]) for b in own):
                    yield self.found("message_off_bar", elements, where,
                                     f"{at}이 그 높이의 막대 변에 닿지 않는다: {', '.join(self.bar(b) for b in own)}.")
                elif not own and not _on(x, p.x):
                    yield self.found("message_off_bar", elements, where,
                                     f"{at}이 생명선(x {fmt_num(p.x)})에서 떨어져 있다 — 그 높이에 막대가 없다.")
                near = [b for b in self.lay.bars if b.owner != name and _holds(b, m.y)
                        and b.rect[0] - END_SNAP <= x <= b.rect[2] + END_SNAP]
                if near:
                    yield self.found("message_off_bar", (*elements, *(self.who(b.owner) for b in near)), where,
                                     f"{at}이 다른 생명선의 막대 안이나 변 바로 앞에서 멈춘다: "
                                     f"{', '.join(self.bar(b) for b in near)}.")

    def lines_at_bar_ends(self) -> Iterator[Finding]:
        for m in self.lay.messages:
            x0, x1 = sorted((m.start, m.end))
            for b in self.lay.bars:
                if _attached(m, b) or not (b.rect[0] < x1 - EPS and x0 + EPS < b.rect[2]):
                    continue
                for end, edge in ((b.top, "윗변"), (b.bottom, "밑변")):
                    if abs(m.y - end) < CLEAR - EPS:
                        yield self.found("line_at_bar_end", (m.owner, self.who(b.owner)),
                                         (b.rect[0], min(m.y, end), b.rect[2], max(m.y, end)),
                                         f"{_message(m)}의 선(y {fmt_num(m.y)})이 건너는 막대의 {edge}에 "
                                         f"{fmt_num(abs(m.y - end))}px로 붙는다({CLEAR}px 넘게 떨어져야 한다): {self.bar(b)}.")

    def lines_through_participants(self) -> Iterator[Finding]:
        for m in self.lay.messages:
            x0, x1 = sorted((m.start, m.end))
            for i, p in enumerate(self.parts):
                if _crosses(m.y, x0, x1, p.head):
                    yield self.found("line_through_participant", (m.owner, f"participants[{i}]"),
                                     (max(x0, p.head[0]), m.y, min(x1, p.head[2]), m.y),
                                     f"{_message(m)}의 선이 머리를 지난다: {self.head(p)}.")

    # -------- 프레임·ref

    @staticmethod
    def edges(f: Framed) -> list[tuple[float, str]]:
        dividers = f.dividers if isinstance(f, PlacedFrame) else ()
        return [(f.top, "윗변"), (f.bottom, "밑변"), *((y, "칸 나눔선") for y in dividers)]

    def returns_in(self, f: Framed, b: PlacedBar) -> bool:
        """막대가 프레임 안 메시지 높이(에서 CLEAR 아래까지)에서 끝나는지."""
        return any(f.top < m.y < f.bottom and -EPS <= b.bottom - m.y <= CLEAR + EPS for m in self.lay.messages)

    def frames_cutting_bars(self) -> Iterator[Finding]:
        for f in self.framed:
            for b in self.lay.bars:
                elements = (f.owner, self.who(b.owner))
                for y, edge in self.edges(f):
                    for end, side in ((b.top, "윗변"), (b.bottom, "밑변")):
                        if abs(y - end) < EDGE_CLEAR - EPS:
                            yield self.found("frame_cuts_bar", elements, (b.rect[0], min(y, end), b.rect[2], max(y, end)),
                                             f"{_frame(f)}의 {edge}(y {fmt_num(y)})이 막대 {side}에 붙는다({EDGE_CLEAR}px 넘게 "
                                             f"떨어져야 한다): {self.bar(b)}.")
                over_top = b.top + EPS < f.top < b.bottom - EPS
                over_bottom = b.top + EPS < f.bottom < b.bottom - EPS
                if over_top and not over_bottom and not self.returns_in(f, b):
                    yield self.found("frame_cuts_bar", elements, between(b.rect, (f.left, f.top, f.right, f.bottom)),
                                     f"막대가 {_frame(f)}의 윗변만 건너 그 안에서 메시지 없이 끝난다(잘린 것처럼 보인다): "
                                     f"{self.bar(b)}.")
                if over_bottom and not over_top:
                    yield self.found("frame_cuts_bar", elements, between(b.rect, (f.left, f.top, f.right, f.bottom)),
                                     f"막대가 {_frame(f)} 안에서 시작해 밑변을 건넌다(잘린 것처럼 보인다): {self.bar(b)}.")

    def bars_outside_frames(self) -> Iterator[Finding]:
        for f in self.framed:
            for b in self.lay.bars:
                if b.top < f.bottom and f.top < b.bottom and not (f.left < b.rect[0] and b.rect[2] < f.right):
                    yield self.found("bar_outside_frame", (f.owner, self.who(b.owner)), b.rect,
                                     f"막대가 {_frame(f)}(x {fmt_num(f.left)}~{fmt_num(f.right)})의 옆 변 밖으로 나간다: "
                                     f"{self.bar(b)}.")

    def frame_overlaps(self) -> Iterator[Finding]:
        for i, a in enumerate(self.framed):
            for b in self.framed[i + 1:]:
                if b.top <= a.bottom + EPS:
                    yield self.found("frame_overlap", (a.owner, b.owner), between((a.left, a.top, a.right, a.bottom),
                                                                                  (b.left, b.top, b.right, b.bottom)),
                                     f"프레임끼리 겹치거나 붙는다: {_frame(a)}(y {fmt_num(a.top)}~{fmt_num(a.bottom)}), "
                                     f"{_frame(b)}(y {fmt_num(b.top)}~{fmt_num(b.bottom)}).")

    def messages_in_refs(self) -> Iterator[Finding]:
        for r in self.lay.refs:
            for m in self.lay.messages:
                if r.top - PAD < m.y < r.bottom + PAD:
                    yield self.found("message_in_ref", (m.owner, r.owner), (min(m.start, m.end), m.y, max(m.start, m.end), m.y),
                                     f"{_message(m)}(y {fmt_num(m.y)})이 {_frame(r)}(y {fmt_num(r.top)}~{fmt_num(r.bottom)}) "
                                     f"상자 안에 있거나 {PAD}px 안으로 붙는다.")

    def lines_on_frames(self) -> Iterator[Finding]:
        """프레임·ref 가로 선은 그림 전체 폭이라 모든 메시지 선과 나란하다 — 가까우면 두 선이 한 선으로 보이거나 화살촉이 닿는다."""
        for f in self.framed:
            for y, edge in self.edges(f):
                for m in self.lay.messages:
                    if abs(m.y - y) < FRAME_LINE_CLEAR - EPS:
                        yield self.found("line_on_frame", (m.owner, f.owner), (min(m.start, m.end), min(y, m.y),
                                                                              max(m.start, m.end), max(y, m.y)),
                                         f"{_message(m)}의 선(y {fmt_num(m.y)})이 {_frame(f)}의 {edge}(y {fmt_num(y)})에 "
                                         f"{fmt_num(abs(m.y - y))}px로 붙는다({FRAME_LINE_CLEAR}px 넘게 떨어져야 한다).")

    def frames_on_participants(self) -> Iterator[Finding]:
        for f in self.framed:
            for i, p in enumerate(self.parts):
                elements = (f.owner, f"participants[{i}]")
                if isinstance(f, PlacedRef):
                    box = (f.left, f.top, f.right, f.bottom)
                    if _overlap(box, p.head):
                        yield self.found("frame_on_participant", elements, between(box, p.head),
                                         f"{_frame(f)} 상자가 머리를 가린다: {self.head(p)}.")
                    continue
                for y, edge in self.edges(f):
                    if _crosses(y, -math.inf, math.inf, p.head):
                        yield self.found("frame_on_participant", elements, (p.head[0], y, p.head[2], y),
                                         f"{_frame(f)}의 {edge}(y {fmt_num(y)})이 머리를 지난다: {self.head(p)}.")

    def tags_on_lifelines(self) -> Iterator[Finding]:
        for f in self.framed:
            tag = f.tag
            for i, p in enumerate(self.parts):
                if tag[0] - EPS <= p.x <= tag[2] + EPS and p.top < tag[3] and tag[1] < p.bottom:
                    yield self.found("tag_on_lifeline", (f.owner, f"participants[{i}]"), (p.x, tag[1], p.x, tag[3]),
                                     f"{_frame(f)}의 꼬리표(자리 {fmt_rect(tag)})가 참여자 '{p.participant.name}'의 "
                                     f"생명선(x {fmt_num(p.x)})을 가린다.")

    # -------- 글자

    def lines_through_texts(self) -> Iterator[Finding]:
        for m in self.lay.messages:
            x0, x1 = sorted((m.start, m.end))
            arrow = m.arrow
            for t in self.texts:
                a = t.area
                if _crosses(m.y, x0, x1, a):
                    yield self.found("line_through_text", (m.owner, t.element), (max(x0, a[0]), m.y, min(x1, a[2]), m.y),
                                     f"{_message(m)}의 선이 글자를 지난다: {t.title}.")
                elif _overlap(arrow, a):
                    yield self.found("line_through_text", (m.owner, t.element), between(arrow, a),
                                     f"{_message(m)}의 화살촉이 글자에 닿는다: {t.title}.")
        for f in self.framed:
            for y, edge in self.edges(f):
                for t in self.texts:
                    if _crosses(y, -math.inf, math.inf, t.area):
                        yield self.found("line_through_text", (f.owner, t.element), (t.area[0], y, t.area[2], y),
                                         f"{_frame(f)}의 {edge}(y {fmt_num(y)})이 글자를 지난다: {t.title}.")

    def texts_on_bars_and_participants(self) -> Iterator[Finding]:
        for t in self.texts:
            if not t.over_bars:
                continue
            for b in self.lay.bars:
                if _overlap(t.area, b.rect, TEXT_BAR_GAP):
                    yield self.found("text_on_bar", (t.element, self.who(b.owner)), between(t.area, b.rect),
                                     f"글자가 막대를 가린다(막대와 {TEXT_BAR_GAP}px 넘게 떨어져야 한다): {t.title}, {self.bar(b)}.")
            for i, p in enumerate(self.parts):
                if _overlap(t.area, p.head):
                    yield self.found("text_on_participant", (t.element, f"participants[{i}]"), between(t.area, p.head),
                                     f"글자가 머리에 겹친다: {t.title}, {self.head(p)}.")

    def texts_on_lifelines(self) -> Iterator[Finding]:
        """메시지 글자가 그 메시지가 건너는 사이 생명선 밖의 생명선(보내고 받는 생명선 포함)을 가린다."""
        for t in self.texts:
            if t.message < 0:
                continue
            m = self.lay.messages[t.message].message
            lo, hi = sorted((self.index[m.source], self.index[m.target]))
            a = t.area
            for i, p in enumerate(self.parts):
                if lo < i < hi:
                    continue
                if a[0] + EPS < p.x < a[2] - EPS and a[1] < p.bottom and p.dash_top < a[3]:
                    yield self.found("text_on_lifeline", (t.element, f"participants[{i}]"), (p.x, a[1], p.x, a[3]),
                                     f"글자가 그 메시지가 건너지 않는 생명선을 가린다: {t.title}, 참여자 "
                                     f"'{p.participant.name}'의 생명선(x {fmt_num(p.x)}).")

    def text_overlaps(self) -> Iterator[Finding]:
        for i, a in enumerate(self.texts):
            for b in self.texts[i + 1:]:
                if _overlap(a.box, b.box):
                    what, where = "글자끼리 겹친다", between(a.box, b.box)
                elif _overlap(a.area, b.ink) or _overlap(b.area, a.ink):
                    what, where = "한 글자 밑에 깐 흰 바탕이 다른 글자를 지운다", between(a.area, b.area)
                else:
                    continue
                yield self.found("text_overlap", (a.element, b.element), where, f"{what}: {a.title}, {b.title}.")

    def texts_outside(self) -> Iterator[Finding]:
        for f in self.lay.frames:
            for lab in f.conditions:
                box = lab.box
                if not (f.left < box[0] and box[2] < f.right and f.top < box[1] and box[3] < f.bottom):
                    yield self.found("text_outside", (f.owner,), box,
                                     f"조건 글자가 {_frame(f)}(자리 {fmt_rect((f.left, f.top, f.right, f.bottom))}) 밖으로 나간다: "
                                     f"'{lab.text}'(자리 {fmt_rect(box)}).")
        for r in self.lay.refs:
            box = r.name.box
            if not (r.tag[2] < box[0] and box[2] < r.right and r.top < box[1] and box[3] < r.bottom):
                yield self.found("text_outside", (r.owner,), box,
                                 f"ref 이름이 {_frame(r)} 상자 밖으로 나가거나 꼬리표에 닿는다: '{r.name.text}'(자리 {fmt_rect(box)}), "
                                 f"상자 {fmt_rect((r.left, r.top, r.right, r.bottom))}.")
        for n in self.lay.notes:
            box = n.label.box
            if not (n.left < box[0] and box[2] < n.left + n.width - NOTE_FOLD and n.top < box[1] and box[3] < n.top + n.height):
                yield self.found("text_outside", (n.owner,), box,
                                 f"노트 글자가 노트 {n.owner}(자리 {fmt_rect((n.left, n.top, n.left + n.width, n.top + n.height))}) "
                                 f"밖으로 나가거나 접힌 귀에 닿는다: '{n.text}'(자리 {fmt_rect(box)}).")

    RULES = (participant_overlaps, bars_on_participants, bar_overlaps, message_ends, lines_at_bar_ends,
             lines_through_participants, frames_cutting_bars, bars_outside_frames, frame_overlaps, messages_in_refs,
             lines_on_frames, frames_on_participants, tags_on_lifelines, lines_through_texts, texts_on_bars_and_participants,
             texts_on_lifelines, text_overlaps, texts_outside)
