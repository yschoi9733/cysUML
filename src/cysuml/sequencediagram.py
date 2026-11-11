"""교류도: JSON을 참여자·메시지·프레임 모델로 읽고(parse), 자리를 잡아(layout) 그림판에 그린다(draw).

교류도는 도구가 배치한다. 입력은 참여자 순서, 메시지 순서, 프레임이 덮는 메시지 범위만 주고 좌표는 주지 않는다.
자리 잡기는 세 단계다.

1. 활성 막대(_Activations): 메시지를 차례대로 넣어 막대를 잇는다. 막대는 그 생명선이 반환하거나, 부른 쪽이 다음 메시지를
   보낼 때까지 이어진다. 밑변은 "몇 번째 일의 높이 + 얼마"들 가운데 가장 낮은 곳으로 적어 두어, 높이를 정하기 전에도 어느
   막대가 어느 메시지 옆을 지나는지 안다. 프레임이 열릴 때 열려 있던 막대는 프레임을 위아래로 감싸고, 프레임(alt는 칸) 안에서
   연 막대는 그 안에서 닫는다 — 프레임 선이 막대를 자르지 않게.
2. 가로(_columns): 이웃 생명선 사이를 그 사이를 지나는 메시지 글자가 들어갈 만큼 띄운다.
3. 세로(_Placer): 메시지·프레임·ref를 차례대로 놓되, 앞서 놓은 글자·선·머리·막대에 걸리면 걸리지 않는 곳까지 내린다.

틀린 입력은 그리기 전에 클래스도와 같은 InputError로 돌려준다. 문제마다 "messages[2].to: …"처럼 입력 안의 자리를 붙이고,
한 번에 모두 모아 알린다.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from . import text as T
from .canvas import SCALE, Canvas
from .classdiagram import InputError, _at, _Reader, _show

__all__ = ["InputError", "parse", "layout", "draw", "render"]

PARTICIPANT_KINDS = ("lifeline", "actor")
MESSAGE_KINDS = ("call", "reply", "create")
FRAME_KINDS = ("loop", "opt", "alt", "ref")

DIAGRAM_FIELDS = ("participants", "messages", "frames", "notes")
PARTICIPANT_FIELDS = ("name", "kind")
MESSAGE_FIELDS = ("from", "to", "name", "kind")
FRAME_FIELDS = {
    "loop": ("kind", "first", "last", "condition"),
    "opt": ("kind", "first", "last", "condition"),
    "alt": ("kind", "branches"),
    "ref": ("kind", "name", "before"),
}
FRAME_REQUIRED = {"loop": ("first", "last"), "opt": ("first", "last"), "alt": ("branches",), "ref": ("name", "before")}
ALL_FRAME_FIELDS = tuple(dict.fromkeys(k for fields in FRAME_FIELDS.values() for k in fields))
BRANCH_FIELDS = ("condition", "first", "last")

LIMITS = (("participants", "참여자가", 40), ("messages", "메시지가", 300), ("frames", "프레임이", 100), ("notes", "노트가", 50))
MAX_PARTICIPANTS, MAX_MESSAGES, MAX_FRAMES, MAX_NOTES = (n for _, _, n in LIMITS)
MAX_EXTENT = 200_000  # 그림 한 변의 논리 길이 상한 — 그림판 점선 칸 수 상한(MAX_DASHES × 무늬)보다 넉넉히 작게

# 머리
LEFT = 20
SLOT_GAP = 20      # 이웃 머리 사이 최소 간격
LIFE_W = 80        # 생명선 머리 최소 폭
HEAD_PAD = 24      # 생명선 머리 글자의 좌우 여백 합
HEAD_H = 40
HEAD_NAME = 13     # 머리 윗변에서 이름 가운데까지
ACTOR_W = 90       # 액터 자리 최소 폭
ACTOR_PAD = 10
ACTOR_NAME = 51    # 액터 그림 윗끝에서 이름 가운데까지
ACTOR_H = 63       # 액터 그림 윗끝에서 점선 시작까지
LIFE_DASH = (3, 3)
LIFE_TAIL = 20     # 가장 아래 그린 것 밑으로 점선을 더 긋는 길이

# 활성 막대
ACT_W = 14
ACT_H = 28         # 막대 최소 높이
NEST = 7           # 같은 생명선에 겹친 막대를 오른쪽으로 비키는 길이

# 메시지
FIRST = 80         # 첫 메시지 높이(머리 윗변 0 기준)
DY = 28            # 메시지 사이 최소 간격 — ACT_H 이상이어야 한다(막대 밑변 셈이 이것에 기댄다)
DY_FACING = 40     # 앞 글자가 선 아래, 이번 글자가 선 위에 있어 마주 볼 때
LABEL_DY = 10      # 선에서 글자 가운데까지
CREATE_DY = 25     # 만드는 메시지의 두 줄 가운데 선에서 먼 줄(두 줄 상자가 겹치지 않게 LABEL_DY에서 15)
LABEL_GAP = 4      # 글자와 막대(생명선) 사이
TIP_ROOM = 12      # 화살촉 쪽은 화살촉 길이만큼 더 띄운다
ACTOR_ROOM = 10    # 액터 쪽 끝은 더 띄운다
ARROW = 10
ARROW_HALF = 5
REPLY_DASH = (4, 3)
CREATE_LABEL = "«create»"

# 간격 규칙
PAD = 3            # 새로 놓는 것과 앞서 놓은 글자·선·머리 사이(흰 바탕 BG_MARGIN보다 넓게)
CLEAR = 4          # 메시지 선과, 그 선이 건너는 막대의 윗변·밑변 사이
BAR_GAP = 4        # 한 생명선의 앞 막대 밑변과 다음 막대 윗변 사이
EDGE_CLEAR = 6     # 프레임·ref의 가로 선과 막대 끝 사이
EPS = 1e-6
MAX_PUSH = 10_000

# 프레임
FRAME_INSET = 10   # 프레임 왼쪽 변에서 첫 머리까지
FRAME_RIGHT = 15   # 마지막 머리에서 프레임 오른쪽 변까지
FRAME_GAP = 6      # 앞서 그린 것과 프레임·칸·ref 가로 선 사이
FRAME_BEFORE = 20  # 앞 메시지 선에서 프레임·칸·ref 가로 선까지 최소
FRAME_HEAD = 32    # 프레임·칸 윗변에서 첫 메시지까지 최소
FRAME_FOOT = 34    # 마지막 메시지에서 프레임 밑변까지 최소
FRAME_AFTER = 18   # 프레임 밑변에서 다음 메시지까지 최소
TAG_H = 23
TAG_MIN_W = 46
TAG_PAD = 25
TAG_CUT = 10       # 꼬리표 오른쪽 아래 모서리를 깎는 길이
TAG_SIDE = 13
TAG_TEXT = (5, 11)
COND_GAP = 6       # 꼬리표와 조건 글자 사이, 조건 글자와 프레임 오른쪽 변 사이
COND_LEFT = 8      # 칸 나눔 선 아래 조건 글자의 왼쪽 여백
COND_Y = 11
DIVIDER_DASH = (5, 4)
REF_H = 34
REF_AFTER = 18

# 노트
NOTE_GAP = 10
NOTE_H = 26
NOTE_STEP = 30
NOTE_MIN_W = 200
NOTE_PAD = 48
NOTE_TEXT_X = 5
NOTE_FOLD = 10

INF = math.inf
Box = T.Box


@dataclass(frozen=True)
class Participant:
    name: str
    kind: str


@dataclass(frozen=True)
class Message:
    source: str
    target: str
    name: Optional[str]
    kind: str


@dataclass(frozen=True)
class Branch:
    """프레임의 칸. first·last는 messages 안의 자리(0부터)다."""

    condition: Optional[str]
    first: int
    last: int


@dataclass(frozen=True)
class Fragment:
    """loop·opt·alt 프레임. loop·opt는 칸이 하나다. index는 입력 frames 안의 자리다."""

    kind: str
    branches: tuple[Branch, ...]
    index: int

    @property
    def first(self) -> int:
        return self.branches[0].first

    @property
    def last(self) -> int:
        return self.branches[-1].last


@dataclass(frozen=True)
class Ref:
    """messages[before] 바로 앞에 놓는 ref(before가 메시지 수면 맨 뒤). index는 입력 frames 안의 자리다."""

    name: str
    before: int
    index: int


@dataclass(frozen=True)
class Diagram:
    participants: tuple[Participant, ...]
    messages: tuple[Message, ...]
    fragments: tuple[Fragment, ...]
    refs: tuple[Ref, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class Label:
    """한 줄 글자. anchor "mm"이면 (x, y)가 가운데, "lm"이면 x가 왼쪽 끝이다."""

    text: str
    x: float
    y: float
    anchor: str = "mm"

    @property
    def box(self) -> Box:
        return T.place(self.x, self.y, self.text, False, self.anchor).box


@dataclass(frozen=True)
class PlacedParticipant:
    """top은 머리 윗변(만들어지는 생명선은 만드는 메시지 높이로 내려온다), dash_top·bottom은 점선의 위아래 끝이다."""

    participant: Participant
    x: float
    width: float
    top: float
    dash_top: float
    bottom: float

    @property
    def head(self) -> Box:
        return _head_box(self.participant, self.x, self.width, self.top)


def _head_box(p: Participant, x: float, width: float, top: float) -> Box:
    """머리가 차지하는 상자(액터는 그림과 이름)."""
    if p.kind == "actor":
        name = T.place(x, top + ACTOR_NAME, p.name, True, "mm").box
        return min(x - 9, name[0]), top, max(x + 9, name[2]), name[3]
    return x - width / 2, top, x + width / 2, top + HEAD_H


def _extent(lines: list[str]) -> tuple[float, float]:
    """가운데에 놓은 글자 줄들의 상자가 가운데에서 왼쪽·오른쪽으로 닿는 곳(왼쪽은 음수). 진행 폭이 아니라 상자로 잰다 —
    진행 폭 밖으로 칠해지는 글자(ƴ 등)가 있으면 상자가 그만큼 넓다."""
    boxes = [T.place(0, 0, s, False, "mm").box for s in lines]
    return min(b[0] for b in boxes), max(b[2] for b in boxes)


@dataclass(frozen=True)
class PlacedBar:
    """활성 막대. x는 가운데이고, depth는 같은 생명선에서 이 막대를 감싼 막대 수다(그만큼 오른쪽으로 비킨다)."""

    owner: str
    x: float
    top: float
    bottom: float
    depth: int

    @property
    def rect(self) -> Box:
        return self.x - ACT_W / 2, self.top, self.x + ACT_W / 2, self.bottom


@dataclass(frozen=True)
class PlacedMessage:
    """start는 선이 시작하는 x, end는 화살촉 끝 x다. 막대가 있으면 막대 변, 만드는 메시지는 만들어지는 머리의 변이다."""

    message: Message
    owner: str
    y: float
    start: float
    end: float
    labels: tuple[Label, ...]


@dataclass(frozen=True)
class PlacedFrame:
    """loop·opt·alt 프레임. dividers는 alt 칸을 나누는 점선 높이, conditions는 칸마다의 조건 글자다(조건이 없는 칸은 없다)."""

    fragment: Fragment
    owner: str
    left: float
    top: float
    right: float
    bottom: float
    dividers: tuple[float, ...]
    conditions: tuple[Label, ...]


@dataclass(frozen=True)
class PlacedRef:
    ref: Ref
    owner: str
    left: float
    top: float
    right: float
    bottom: float
    name: Label


@dataclass(frozen=True)
class PlacedNote:
    text: str
    owner: str
    left: float
    top: float
    width: float
    height: float


@dataclass(frozen=True)
class Layout:
    participants: tuple[PlacedParticipant, ...]
    bars: tuple[PlacedBar, ...]
    messages: tuple[PlacedMessage, ...]
    frames: tuple[PlacedFrame, ...]
    refs: tuple[PlacedRef, ...]
    notes: tuple[PlacedNote, ...]


@dataclass(frozen=True)
class Drawing:
    canvas: Canvas
    layout: Layout


# ---------------------------------------------------------------- 입력 읽기


def _wrapped(s: str) -> bool:
    """s 전체가 대괄호 한 쌍에 싸였는지(첫 "["의 짝이 마지막 글자인지)."""
    if s[:1] != "[" or s[-1:] != "]":
        return False
    depth = 0
    for i, ch in enumerate(s):
        depth += {"[": 1, "]": -1}.get(ch, 0)
        if depth == 0:
            return i == len(s) - 1
    return False


class _SeqReader(_Reader):
    def position(self, v, path: str, upper: int) -> Optional[int]:
        """messages 안의 자리(0~upper의 정수)."""
        if not isinstance(v, int) or isinstance(v, bool):
            self.fail(path, f"messages 안의 자리(0부터 센 정수)여야 한다(받은 값 {_show(v)})")
            return None
        if upper < 0:
            self.fail(path, "messages가 비어 있어 가리킬 메시지가 없다")
            return None
        if not 0 <= v <= upper:
            self.fail(path, f"0~{upper} 사이여야 한다(받은 값 {_show(v)})")
            return None
        return v

    def condition(self, v, path: str) -> Optional[str]:
        """조건 글자. 도구가 대괄호를 씌우므로, 전체를 감싼 대괄호는 받지 않는다(안쪽 대괄호 "[x] or [y]"는 받는다)."""
        s = self.text(v, path)
        if s is not None and _wrapped(s.strip()):
            self.fail(path, f"대괄호 없이 조건만 쓴다(받은 값 {_show(s)})")
            return None
        return s

    def participant(self, v, path: str) -> tuple[Optional[str], Optional[Participant]]:
        before = len(self.problems)
        o = self.obj(v, path, PARTICIPANT_FIELDS, ("name",))
        if o is None:
            return None, None
        name = self.text(o["name"], _at(path, "name"), bold=True, name=True) if "name" in o else None
        kind = self.choice(o["kind"], _at(path, "kind"), PARTICIPANT_KINDS) if "kind" in o else "lifeline"
        if len(self.problems) > before:
            return name, None
        return name, Participant(name, kind)

    def message(self, v, path: str) -> tuple[Optional[str], Optional[str], Optional[Message]]:
        """(읽은 from, 읽은 to, 메시지). 다른 필드가 틀려도 from·to가 없는 참여자를 가리키는지 함께 알리려고 따로 돌려준다."""
        before = len(self.problems)
        o = self.obj(v, path, MESSAGE_FIELDS, ("from", "to"))
        if o is None:
            return None, None, None
        kind = self.choice(o["kind"], _at(path, "kind"), MESSAGE_KINDS) if "kind" in o else "call"
        source = self.text(o["from"], _at(path, "from"), bold=True, name=True) if "from" in o else None
        target = self.text(o["to"], _at(path, "to"), bold=True, name=True) if "to" in o else None
        name = self.text(o["name"], _at(path, "name")) if "name" in o else None
        if kind == "call" and "name" not in o:
            self.fail(path, "호출 메시지는 'name'(부르는 연산)이 있어야 한다")
        if source is not None and source == target:
            self.fail(path, f"자기 자신({_show(source)})에게 보내는 메시지는 그리지 않는다 — 그 일은 'notes'에 노트로 적는다")
        if len(self.problems) > before:
            return source, target, None
        return source, target, Message(source, target, name, kind)

    def span(self, o: dict, path: str, n: int, condition: Optional[str]) -> Optional[Branch]:
        first = self.position(o["first"], _at(path, "first"), n - 1) if "first" in o else None
        last = self.position(o["last"], _at(path, "last"), n - 1) if "last" in o else None
        if first is not None and last is not None and last < first:
            self.fail(_at(path, "last"), f"first({first})보다 앞이다")
            return None
        return None if first is None or last is None else Branch(condition, first, last)

    def frame(self, v, path: str, n: int, index: int):
        before = len(self.problems)
        o = self.obj(v, path, ALL_FRAME_FIELDS, ("kind",))
        if o is None or "kind" not in o:
            return None
        kind = self.choice(o["kind"], _at(path, "kind"), FRAME_KINDS)
        if kind is None:
            return None
        allowed = FRAME_FIELDS[kind]
        for k in o:
            if k in ALL_FRAME_FIELDS and k not in allowed:
                self.fail(_at(path, k), f"{kind} 프레임에는 쓰지 않는 필드다. 쓸 수 있는 필드: {', '.join(allowed)}")
        for k in FRAME_REQUIRED[kind]:
            if k not in o:
                self.fail(path, f"'{k}' 필드가 빠졌다")
        if kind == "ref":
            name = self.text(o["name"], _at(path, "name")) if "name" in o else None
            at = self.position(o["before"], _at(path, "before"), n) if "before" in o else None
            if len(self.problems) > before:
                return None
            return Ref(name, at, index)
        if kind == "alt":
            raw = self.items(o["branches"], _at(path, "branches")) if "branches" in o else []
            if "branches" in o and isinstance(o["branches"], (list, tuple)) and len(raw) < 2:
                self.fail(_at(path, "branches"), "alt는 칸이 둘 이상이어야 한다 — 칸이 하나면 opt를 쓴다")
            elif len(raw) > n:
                self.fail(_at(path, "branches"), f"칸이 {len(raw)}개인데 메시지는 {n}개다 — 칸마다 메시지가 하나 이상 있어야 한다")
                return None
            branches = []
            for j, b in enumerate(raw):
                bp = _at(_at(path, "branches"), j)
                bo = self.obj(b, bp, BRANCH_FIELDS, BRANCH_FIELDS)
                if bo is None:
                    branches.append(None)
                    continue
                cond = self.condition(bo["condition"], _at(bp, "condition")) if "condition" in bo else None
                branches.append(self.span(bo, bp, n, cond))
            for j in range(1, len(branches)):
                a, b = branches[j - 1], branches[j]
                if a is not None and b is not None and b.first != a.last + 1:
                    self.fail(_at(_at(_at(path, "branches"), j), "first"),
                              f"앞 칸이 messages[{a.last}]에서 끝나므로 {a.last + 1}이어야 한다 — 칸은 빈틈없이 이어 붙인다")
        else:
            cond = self.condition(o["condition"], _at(path, "condition")) if "condition" in o else None
            branches = [self.span(o, path, n, cond)]
        if len(self.problems) > before:
            return None
        return Fragment(kind, tuple(branches), index)

    def diagram(self, data) -> Optional[Diagram]:
        o = self.obj(data, "", DIAGRAM_FIELDS, ("participants",))
        if o is None:
            return None
        lists = {key: self.items(o[key], key) if key in o else [] for key in DIAGRAM_FIELDS}
        too_many = [(key, noun, limit) for key, noun, limit in LIMITS if len(lists[key]) > limit]
        for key, noun, limit in too_many:
            self.fail(key, f"{noun} {len(lists[key])}개다 — {limit}개까지 받는다. 그림을 나눈다")
        if too_many:
            return None
        raw_p = lists["participants"]
        if "participants" in o and isinstance(o["participants"], (list, tuple)) and not raw_p:
            self.fail("participants", "참여자가 하나 이상 있어야 한다")
        read = [self.participant(v, _at("participants", i)) for i, v in enumerate(raw_p)]
        seen: dict[str, int] = {}
        kinds: dict[str, str] = {}
        for i, (name, p) in enumerate(read):
            if name is None:
                continue
            if name in seen:
                self.fail(_at(_at("participants", i), "name"),
                          f"participants[{seen[name]}]와 이름이 같다 — 메시지가 이름으로 참여자를 가리키므로 이름은 달라야 한다")
                continue
            seen[name] = i
            if p is not None:
                kinds[name] = p.kind
        known = ", ".join(_show(n) for n in list(seen)[:20]) + (" …" if len(seen) > 20 else "")

        raw_m = lists["messages"]
        n = len(raw_m)
        messages = []
        created: dict[str, int] = {}
        used: dict[str, int] = {}
        for i, v in enumerate(raw_m):
            path = _at("messages", i)
            source, target, m = self.message(v, path)
            missing = [(key, who) for key, who in (("from", source), ("to", target)) if who is not None and who not in seen]
            for key, who in missing:
                self.fail(_at(path, key), f"이름이 {_show(who)}인 참여자가 없다(있는 참여자: {known or '없음'})")
            if m is not None and not missing:
                if m.kind == "create":
                    if kinds.get(target) == "actor":
                        self.fail(_at(path, "to"), "액터는 만들 수 없다 — 만드는 메시지는 생명선(kind 'lifeline')에 보낸다")
                    elif target in created:
                        self.fail(_at(path, "to"), f"{_show(target)}는 messages[{created[target]}]에서 이미 만들었다")
                    elif target in used:
                        self.fail(_at(path, "to"), f"{_show(target)}는 messages[{used[target]}]에서 이미 메시지를 주고받았다 — "
                                                   "만드는 메시지를 그보다 앞에 둔다")
                    else:
                        created[target] = i
                messages.append(m)
                used.setdefault(source, i)
                used.setdefault(target, i)

        frames = [self.frame(v, _at("frames", i), n, i) for i, v in enumerate(lists["frames"])]
        fragments = sorted((f for f in frames if isinstance(f, Fragment)), key=lambda f: (f.first, f.index))
        refs = [f for f in frames if isinstance(f, Ref)]
        reach: Optional[Fragment] = None  # 앞선 프레임 가운데 가장 아래까지 덮는 것
        for f in fragments:
            if reach is not None and f.first <= reach.last:
                self.fail(_at("frames", f.index), f"frames[{reach.index}]와 덮는 메시지가 겹친다 — 프레임 안에 프레임을 넣지 않는다")
            if reach is None or f.last > reach.last:
                reach = f
        for r in refs:
            f = next((f for f in fragments if f.first < r.before <= f.last), None)
            if f is not None:
                self.fail(_at(_at("frames", r.index), "before"),
                          f"frames[{f.index}](messages[{f.first}]~[{f.last}]) 안이다 — 프레임 안에 ref를 넣지 않는다")
        notes = [self.text(v, _at("notes", i)) for i, v in enumerate(lists["notes"])]
        return Diagram(tuple(p for _, p in read if p is not None), tuple(messages), tuple(fragments), tuple(refs),
                       tuple(s for s in notes if s is not None))


def parse(data: Any) -> Diagram:
    """JSON(을 읽은 파이썬 값)을 교류도 모델로 읽는다. 틀린 곳이 있으면 모두 모아 InputError."""
    reader = _SeqReader()
    diagram = reader.diagram(data)
    if reader.problems:
        raise InputError(reader.problems)
    assert diagram is not None
    return diagram


# ---------------------------------------------------------------- 1. 활성 막대


@dataclass(eq=False)
class _Bar:
    """terms는 밑변의 후보 (일의 차례, 그 높이에 더할 길이)이고, 밑변은 그 가운데 가장 낮은 곳이다."""

    life: int
    top: int
    terms: set = field(default_factory=set)
    protected: bool = False
    sticky: bool = False  # 대답을 기다리는 액터 막대 — 다른 생명선이 보내는 메시지로는 닫히지 않는다
    top_off: float = 0.0  # 윗변 = top번째 일의 높이 + top_off(alt 칸 나눔선 아래에서 이어지는 막대만 0이 아니다)
    parent: Optional[_Bar] = None  # 이 막대를 연 호출을 보낸 막대 — 닫을 때 밑변을 넘겨받는다
    depth: int = 0
    last: int = 0  # terms 가운데 가장 늦은 일의 차례(다 놓인 뒤에야 밑변이 정해진다)


def _after(term: tuple[int, float], e: int) -> bool:
    """밑변 후보가 e번째 일의 높이보다 아래인지. 다음 메시지는 앞 일에서 생기는 후보보다 아래에 놓이므로(DY ≥ ACT_H,
    프레임·ref 뒤 간격 ≥ EDGE_CLEAR — 테스트가 상수 순서를 확인한다) 차례만으로 가려진다."""
    j, off = term
    return j > e or (j == e and off > 0)


def _ends_after(bar: _Bar, e: int) -> bool:
    return any(_after(t, e) for t in bar.terms)


class _Activations:
    """막대를 잇는 규칙.

    - 액터가 아닌 생명선을 부르면 그 생명선에 막대를 연다. 열린 막대는 부른 순서대로 쌓인다.
    - 보내는 생명선에 열린 막대가 있으면 그 위에 쌓인 막대(그가 부른 쪽)를 닫는다. 액터가 보내거나, 열린 막대가 없는
      생명선이 보내면 열린 막대를 모두 닫는다(열린 막대가 없는 생명선은 그 자리에서 막대를 연다). 반환은 막대 없이 보내도
      다른 막대를 닫지 않는다 — 받는 쪽이 기다리던 막대가 끊기지 않게.
    - 반환은 보내는 막대(와 그 위에 남은 막대)를 그 높이에서 닫는다. 받는 생명선에 열린 막대가 있으면 그 위를 닫고 잇고,
      없으면 그 자리에서 연다(다른 막대는 닫지 않는다).
    - 액터가 받는 호출은, 그 액터가 다음에 보내는 메시지가 반환(대답)이고 그 사이에 프레임 선이 없으면 대답할 때까지
      잇는다(대답을 기다리는 막대 — 그 막대와 그 막대를 부른 막대들은 다른 생명선이 메시지를 보내도 닫히지 않고, 부른
      쪽이 먼저 반환해도 그 막대는 대답까지 남는다). 아니면 높이 ACT_H로 그리고 쌓지 않는다.
      액터는 대답할 때 그 막대에서, 그 밖에는 막대 없이 생명선에서 보낸다. 만드는 메시지는 막대를 만들지 않는다.
    닫는 막대의 밑변은 "윗변 + ACT_H"와 그 막대가 마지막으로 주고받은 높이 가운데 아래쪽이고, 그 막대가 부른 막대보다는
    아래다. 부른 막대가 메시지 높이에서 끝났으면 그보다 CLEAR만큼 더 잇는다 — 그 메시지 선이 이 막대 생명선을 지날 때 선이
    막대 밑변을 따라가지 않게(그 밑변은 메시지 높이와 같이 움직여 메시지를 내려서는 못 비킨다).

    프레임 규칙: 칸마다 첫 메시지가 모두 닫을 막대는 프레임 앞에서 닫는다. 그때 남아 열려 있던 막대는 부른 쪽이 메시지를 보내도
    프레임 안에서 닫지 않고(protected) 프레임 밑변 아래까지 잇는다 — 그런 막대의 밑변은 막대 높이로만 정해져 프레임 윗변
    바로 밑에서 끝날 수 있어서다. 다만 그 생명선이 반환하면 그 높이에서 끝난다(프레임 윗변에서 FRAME_HEAD 넘게 아래다).
    프레임 안에서 연 막대는 칸이 끝날 때 닫는다. alt의 칸은 서로 대신하는 갈래라 칸마다 프레임이 열릴 때의 막대에서 시작한다
    — 앞 칸에서 반환한 그런 막대는 거기서 끝나고, 다음 칸에서는 칸 나눔선 EDGE_CLEAR 아래에서 이어지는 막대를 새로 연다.
    어느 한 칸에서라도 반환한 막대는 alt와 함께 끝나고(이어 가던 막대는 밑변 EDGE_CLEAR 위에서 닫는다), 모든 칸에서 계속
    일한 막대만 프레임 밖으로 이어진다 — 칸 차례에 따라 그 뒤 그림이 달라지지 않게.
    ref는 그때 열린 막대를 ref 아래까지 잇는다(바로 다음 메시지가 닫을 막대는 ref 앞에서 닫는다).
    """

    def __init__(self):
        self.stack: list[_Bar] = []
        self.bars: list[_Bar] = []
        self.kept: list[_Bar] = []    # 지금 프레임이 열릴 때 열려 있던 막대(쌓인 차례대로, alt는 지금 칸에서 잇는 막대)
        self.ended: list[bool] = []   # kept 자리마다, 앞 칸에서 반환한 적이 있는지

    def open(self, life: int, e: int, fixed: bool = False, parent: Optional[_Bar] = None, sticky: bool = False) -> _Bar:
        """막대를 연다. fixed(액터가 받는 호출)면 높이 ACT_H로 끝나 쌓지 않고, 부른 막대를 그만큼 잇는다(부른 쪽이 먼저
        끝나지 않게). 다만 sticky(액터가 대답할 호출)면 쌓아 두고 대답할 때 닫는다."""
        b = _Bar(life, e, {(e, ACT_H)}, parent=parent, sticky=sticky)
        self.bars.append(b)
        if not fixed or sticky:
            self.stack.append(b)
        elif parent is not None:
            parent.terms.add((e, ACT_H))
        return b

    def find(self, life: int) -> Optional[_Bar]:
        return next((b for b in reversed(self.stack) if b.life == life), None)

    def _close(self, b: _Bar) -> None:
        self.stack.remove(b)
        if b.parent is not None and b.parent in self.stack:
            b.parent.terms |= {(j, off or CLEAR) for j, off in b.terms}

    def _held(self) -> set[int]:
        """다른 생명선이 보내는 메시지로는 닫지 않는 막대(id): 대답을 기다리는 액터 막대와, 그 막대를 부른 막대들 — 부른
        쪽이 대답을 기다리는 동안 끊기지 않게."""
        held: set[int] = set()
        for x in self.stack:
            p: Optional[_Bar] = x if x.sticky else None
            while p is not None and p in self.stack and id(p) not in held:
                held.add(id(p))
                p = p.parent
        return held

    def _closing(self, above: list[_Bar], keep_sticky: bool = True) -> list[_Bar]:
        """above 가운데 닫을 막대(아래부터). 지킨 막대와, keep_sticky면 대답을 기다리는 막대와 그 부른 막대들은 뺀다."""
        held = self._held() if keep_sticky else set()
        return [x for x in above if not x.protected and id(x) not in held]

    def close_above(self, b: _Bar) -> None:
        for x in reversed(self._closing(self.stack[self.stack.index(b) + 1:])):
            self._close(x)

    def close_all(self, keep_sticky: bool = True) -> None:
        """지킨 막대 밖의 열린 막대를 모두 닫는다. 대답을 기다리는 막대와 그 부른 막대들은 keep_sticky일 때 남긴다(메시지가
        닫을 때) — 프레임·칸이 끝날 때와 그림 끝에서는 닫는다."""
        for x in reversed(self._closing(list(self.stack), keep_sticky)):
            self._close(x)

    def message(self, src: int, dst: int, kind: str, e: int, src_actor: bool, dst_actor: bool, sticky: bool = False
                ) -> tuple[Optional[_Bar], Optional[_Bar]]:
        """메시지 하나를 넣고 (선이 시작하는 막대, 화살촉이 닿는 막대)를 돌려준다. 막대가 없는 끝은 None이다. sticky는
        액터를 부르는 호출에 그 액터가 다음에 대답하는지다."""
        s = self.send_from(src, kind, src_actor)
        if s is None and not src_actor and kind != "reply":
            s = self.open(src, e)
        d = None
        if kind == "reply":
            if s is not None and s.sticky:
                # 액터의 대답: 그 위 막대는 액터가 부른 것이 아니라 두고, 대답 높이는 기다리던 부른 막대에 넘긴다
                s.terms.add((e, 0))
                self._close(s)
            elif s is not None:
                # 위에 남은 것은 프레임이 지키던 막대와 대답을 기다리는 막대(와 그 부른 막대)뿐이다(나머지는 send_from이
                # 닫았다). 부른 쪽이 반환하면 함께 끝나고, 이 반환 선이 그 생명선을 지날 수 있어 선 아래로 CLEAR만큼 잇는다.
                # 이 반환을 받는 생명선의 막대는 남겨 아래에서 반환에 잇고, 대답을 기다리는 액터 막대와 그 부른 막대들은
                # 남겨 그 대답이 막대에서 나가 기다리던 막대에 닿게 한다
                held = self._held()
                for x in reversed(self.stack[self.stack.index(s) + 1:]):
                    if x.life != dst and id(x) not in held:
                        self._close(x)
                        x.terms.add((e, CLEAR))
                self._close(s)  # 반환 높이는 부모에게 넘기지 않는다 — 건너뛰는 반환이 사이 막대 끝을 선 위에 두지 않게
                s.terms.add((e, 0))
            d = self.find(dst)
            if d is not None:
                self.close_above(d)
                d.terms.add((e, 0))
            elif not dst_actor:
                d = self.open(dst, e)
        else:
            if s is not None:
                s.terms.add((e, 0))
            if kind == "call":
                d = self.open(dst, e, fixed=dst_actor, parent=s, sticky=dst_actor and sticky)
        return s, d

    def _source(self, src: int, kind: str, src_actor: bool) -> Optional[_Bar]:
        """메시지가 시작하는 막대. 액터는 대답(반환)할 때만 대답을 기다리던 막대에서 보낸다."""
        return self.find(src) if not src_actor or kind == "reply" else None

    def _send_closing(self, s: Optional[_Bar], kind: str) -> list[_Bar]:
        """보내는 쪽 규칙이 닫을 막대: 보내는 막대 s가 있으면 그 위, 없으면 반환이 아닌 한 모두(_closing이 뺄 것은 빼고).
        대답을 기다리던 액터 막대 위에 쌓인 막대는 그 액터가 부른 것이 아니라 닫지 않는다."""
        if s is not None:
            return [] if s.sticky else self._closing(self.stack[self.stack.index(s) + 1:])
        return self._closing(list(self.stack)) if kind != "reply" else []

    def send_from(self, src: int, kind: str, src_actor: bool) -> Optional[_Bar]:
        """보내는 쪽 규칙: 보내는 막대를 찾아 그 위를 닫는다. 없으면 반환이 아닌 한 열린 막대를 모두 닫는다. 찾은 막대를
        돌려준다."""
        s = self._source(src, kind, src_actor)
        for x in reversed(self._send_closing(s, kind)):
            self._close(x)
        return s

    def _would_close(self, src: int, kind: str, src_actor: bool) -> set[int]:
        """send_from이 닫을 막대(id). 아무것도 바꾸지 않는다."""
        return {id(x) for x in self._send_closing(self._source(src, kind, src_actor), kind)}

    def preclose(self, firsts: list[tuple[int, str, bool]]) -> None:
        """다음에 올 메시지들(보내는 쪽, 종류, 액터인지 — alt면 칸마다 첫 메시지)이 모두 닫을 막대를 지금 닫는다. 프레임·ref
        앞에서 쓴다. 한 칸의 첫 메시지만 보면 alt 칸 순서에 따라 그림이 달라진다."""
        closing = set.intersection(*(self._would_close(*f) for f in firsts))
        for x in reversed(list(self.stack)):
            if id(x) in closing:
                self._close(x)

    def frame_start(self, firsts: list[tuple[int, str, bool]]) -> None:
        """칸마다 첫 메시지가 모두 닫을 막대는 프레임 앞에서 닫고, 남은 막대를 프레임 끝까지 지킨다."""
        self.preclose(firsts)
        for b in self.stack:
            b.protected = True
        self.kept = list(self.stack)
        self.ended = [False] * len(self.kept)

    def branch(self, e: int) -> None:
        """alt 칸 나눔: 앞 칸에서 연 막대를 닫고, 프레임이 열릴 때의 막대로 돌아간다. 앞 칸에서 반환해 끝난 막대는 이 칸에서
        이어 가는 막대를 새로 연다. (대답을 기다리는 액터 막대는 프레임 선을 넘지 않으므로 여기 오지 않는다.)"""
        self.close_all(keep_sticky=False)  # 남는 것은 지킨 막대뿐이고, 쌓인 차례는 kept와 같다
        now: dict[int, _Bar] = {}  # 바꾼 막대 → 이 칸에서 잇는 막대
        for i, b in enumerate(self.kept):
            if b not in self.stack:
                self.ended[i] = True
                parent = now.get(id(b.parent), b.parent) if b.parent is not None else None
                self.kept[i] = _Bar(b.life, e, {(e, EDGE_CLEAR)}, protected=True, top_off=EDGE_CLEAR, parent=parent)
                self.bars.append(self.kept[i])
                now[id(b)] = self.kept[i]
        self.stack = list(self.kept)

    def frame_end(self, e: int) -> None:
        self.close_all(keep_sticky=False)
        for i in reversed(range(len(self.kept))):
            b = self.kept[i]
            b.protected = False
            if b not in self.stack:  # 마지막 칸에서 반환해 이미 끝났다
                continue
            if self.ended[i]:  # 앞 칸에서 반환했다 — 이어 가던 막대를 프레임 밑변 위에서 닫는다
                b.terms.add((e, -EDGE_CLEAR))
                self._close(b)
            else:
                b.terms.add((e, EDGE_CLEAR))
        self.kept, self.ended = [], []

    def ref(self, e: int) -> None:
        for b in self.stack:
            b.terms.add((e, REF_H + EDGE_CLEAR))


@dataclass(frozen=True)
class _Event:
    """그림 위에서 아래로 놓는 일. kind는 message·ref·start(프레임 윗변)·branch(alt 칸 나눔)·end(프레임 밑변)이고, item은
    message면 메시지 자리, ref면 refs 안의 자리, 나머지는 fragments 안의 자리다."""

    kind: str
    item: int
    branch: int = 0


@dataclass
class _Plan:
    index: dict[str, int]                                  # 참여자 이름 → 자리(왼쪽부터)
    actor: tuple[bool, ...]
    events: list[_Event]
    bars: list[_Bar]
    attach: list[tuple[Optional[_Bar], Optional[_Bar]]]  # 메시지마다 (선이 시작하는 막대, 화살촉이 닿는 막대)
    at: list[int]                                          # 메시지마다 그 일의 차례
    created: dict[int, int]                                # 만들어지는 참여자 → 만드는 메시지 자리
    spanning: list[tuple[int, ...]]                        # 메시지마다, 사이 생명선 가운데 막대가 그 높이를 지나는 것


def _events(d: Diagram) -> list[_Event]:
    starts = {f.first: i for i, f in enumerate(d.fragments)}
    ends = {f.last: i for i, f in enumerate(d.fragments)}
    branches = {b.first: (i, j) for i, f in enumerate(d.fragments) for j, b in enumerate(f.branches) if j}
    refs_at = defaultdict(list)
    for i, r in enumerate(d.refs):
        refs_at[r.before].append(i)
    out = []
    for k in range(len(d.messages) + 1):
        out += [_Event("ref", i) for i in refs_at[k]]
        if k == len(d.messages):
            break
        if k in starts:
            out.append(_Event("start", starts[k]))
        if k in branches:
            out.append(_Event("branch", *branches[k]))
        out.append(_Event("message", k))
        if k in ends:
            out.append(_Event("end", ends[k]))
    return out


def _plan(d: Diagram) -> _Plan:
    index = {p.name: i for i, p in enumerate(d.participants)}
    actor = tuple(p.kind == "actor" for p in d.participants)
    events = _events(d)
    acts = _Activations()
    attach: list = [(None, None)] * len(d.messages)
    at = [0] * len(d.messages)
    msg_event = {ev.item: e for e, ev in enumerate(events) if ev.kind == "message"}

    def answered(k: int) -> bool:
        """액터를 부르는 호출에, 그 액터가 다음에 보내는 메시지가 반환(대답)이고 그 사이에 프레임 선(프레임·칸의 시작과
        끝)이 없는지 — 그러면 막대를 대답까지 잇는다. 프레임 선을 넘으면 alt 칸 순서에 따라 대답이 달라지므로 잇지 않는다.
        그 사이 그 액터를 다시 부르면 대답은 나중 호출이 받으므로 아니다."""
        m = d.messages[k]
        if m.kind != "call" or not actor[index[m.target]]:
            return False
        for ev in events[msg_event[k] + 1:]:
            if ev.kind in ("start", "branch", "end"):
                return False
            if ev.kind == "message":
                n = d.messages[ev.item]
                if n.source == m.target:
                    return n.kind == "reply"
                if n.target == m.target and n.kind == "call":
                    return False
        return False

    def firsts_at(k: int) -> list[tuple[int, str, bool]]:
        """messages[k]부터 시작하는 다음 메시지들 — 그 자리에서 프레임이 열리면 칸마다 첫 메시지다."""
        frame = next((f for f in d.fragments if f.first == k), None)
        msgs = [d.messages[b.first] for b in frame.branches] if frame else [d.messages[k]]
        return [(index[m.source], m.kind, actor[index[m.source]]) for m in msgs]

    for e, ev in enumerate(events):
        if ev.kind == "message":
            m = d.messages[ev.item]
            s, t = index[m.source], index[m.target]
            attach[ev.item] = acts.message(s, t, m.kind, e, actor[s], actor[t], answered(ev.item))
            at[ev.item] = e
        elif ev.kind == "start":
            acts.frame_start(firsts_at(d.fragments[ev.item].first))
        elif ev.kind == "branch":
            acts.branch(e)
        elif ev.kind == "end":
            acts.frame_end(e)
        else:
            before = d.refs[ev.item].before
            # 바로 다음 메시지가 닫을 막대는 ref 앞에서 닫는다 — ref 밑에 짧은 조각이 남지 않게. 맨 끝 ref면 다음 메시지가
            # 없으니 열린 막대를 모두 닫는다
            if before < len(d.messages):
                acts.preclose(firsts_at(before))
            else:
                acts.close_all(keep_sticky=False)
            acts.ref(e)
    acts.close_all(keep_sticky=False)
    bars = acts.bars
    # 깊이는 이 막대가 시작할 때 아직 열려 있는 같은 생명선 막대 가운데 가장 깊은 것 + 1이다 — 시간이 겹치는 막대끼리 깊이가
    # 늘 달라 옆으로 비켜 그려진다. 같은 칸 나눔에서 함께 이어 가는 막대는 높이가 같아, 먼저 연(아래에 쌓인) 막대를 앞으로 친다
    order = {id(b): i for i, b in enumerate(bars)}
    for b in bars:
        b.last = max(j for j, _ in b.terms)
    for b in sorted(bars, key=lambda b: (b.top, order[id(b)])):
        b.depth = max((o.depth + 1 for o in bars if o.life == b.life and (o.top, order[id(o)]) < (b.top, order[id(b)])
                       and _ends_after(o, b.top)), default=0)
    created = {index[m.target]: k for k, m in enumerate(d.messages) if m.kind == "create"}
    spanning = []
    for k, m in enumerate(d.messages):
        lo, hi = sorted((index[m.source], index[m.target]))
        spanning.append(tuple(sorted({b.life for b in bars if lo < b.life < hi and b.top < at[k] and _ends_after(b, at[k])})))
    return _Plan(index, actor, events, bars, attach, at, created, spanning)


# ---------------------------------------------------------------- 2. 가로


@dataclass(frozen=True)
class _Columns:
    """생명선 열. 막대 왼쪽 끝은 늘 가운데에서 ACT_W / 2이고, 오른쪽 끝은 겹친 막대만큼 더 나간다."""

    x: tuple[float, ...]          # 생명선 가운데
    width: tuple[float, ...]      # 머리 폭(액터는 자리 폭)
    right_ext: tuple[float, ...]  # 생명선 가운데에서 가장 깊이 겹친 막대 오른쪽 끝까지
    actor: tuple[bool, ...]


def _tag_width(op: str) -> float:
    return max(TAG_MIN_W, T.text_width(op, True) + TAG_PAD)


def _label_lines(m: Message) -> list[str]:
    if m.kind == "create":
        return [CREATE_LABEL] + ([m.name] if m.name else [])
    return [m.name] if m.name else []


def _label_below(m: Message, rightward: bool) -> bool:
    """오른쪽으로 가는 호출·만드는 메시지는 글자를 선 위에, 왼쪽으로 가는 메시지와 반환은 선 아래에 쓴다."""
    return m.kind == "reply" or not rightward


def _margin(m: Message, s: int, t: int, z: int, toward_right: bool, cols: _Columns) -> float:
    """메시지 글자가 칸 경계 생명선 z에서 떨어져야 하는 거리(z 가운데부터). toward_right면 칸이 z의 오른쪽에 있다."""
    if z == t and m.kind == "create":
        base = cols.width[z] / 2
    else:
        base = cols.right_ext[z] if toward_right else ACT_W / 2
    out = base + LABEL_GAP
    if z == t:
        out += TIP_ROOM
    if z in (s, t) and cols.actor[z]:
        out += ACTOR_ROOM
    return out


def _columns(d: Diagram, plan: _Plan) -> _Columns:
    """이웃 생명선 간격 = 머리가 닿지 않고, 막대가 이웃 머리에 닿지 않고, 그 사이를 지나는 메시지마다 글자가 들어가는 칸이
    하나는 있을 만큼. 칸은 그 메시지 높이를 막대가 지나는 사이 생명선으로 나눈다(막대가 없는 생명선은 글자가 건너고 그 밑
    점선은 지운다). 여러 칸을 건너는 메시지는 가장 덜 모자란 칸을 넓히고, 모자란 만큼 그 칸의 간격에 나눈다."""
    ps, index = d.participants, plan.index
    width = tuple(float(max(ACTOR_W, math.ceil(T.text_width(p.name, True) + ACTOR_PAD))) if p.kind == "actor"
                  else float(max(LIFE_W, math.ceil(T.text_width(p.name, True) + HEAD_PAD))) for p in ps)
    depth = [0] * len(ps)
    for b in plan.bars:
        depth[b.life] = max(depth[b.life], b.depth)
    right_ext = tuple(ACT_W / 2 + NEST * dp for dp in depth)
    shape = _Columns((), width, right_ext, plan.actor)  # 간격을 정하는 동안 쓰는 열(가운데 x는 아직 없다)
    gaps = [max(float(SLOT_GAP), right_ext[i] + LABEL_GAP - width[i] / 2) for i in range(len(ps) - 1)]

    def offsets() -> list[float]:
        out = [0.0]
        for i, g in enumerate(gaps):
            out.append(out[-1] + width[i] / 2 + g + width[i + 1] / 2)
        return out

    order = sorted(range(len(d.messages)),
                   key=lambda k: (abs(index[d.messages[k].source] - index[d.messages[k].target]), k))
    for k in order:
        m = d.messages[k]
        lines = _label_lines(m)
        if not lines:
            continue
        left_off, right_off = _extent(lines)
        w = right_off - left_off
        s, t = index[m.source], index[m.target]
        lo, hi = sorted((s, t))
        bounds = [lo, *plan.spanning[k], hi]
        xs = offsets()
        best = None
        for p, q in zip(bounds, bounds[1:]):
            need = w + _margin(m, s, t, p, True, shape) + _margin(m, s, t, q, False, shape)
            lack = need - (xs[q] - xs[p])
            if best is None or lack < best[0]:
                best = lack, p, q
        lack, p, q = best
        if lack > 0:
            for g in range(p, q):
                gaps[g] += lack / (q - p)
    if d.fragments or d.refs:
        tag = max(_tag_width(op) for op in {f.kind for f in d.fragments} | ({"ref"} if d.refs else set()))
        x0 = max(LEFT + FRAME_INSET + width[0] / 2, LEFT + tag + COND_GAP + ACT_W / 2)
    else:
        x0 = LEFT + width[0] / 2
    return _Columns(tuple(x0 + o for o in offsets()), width, right_ext, plan.actor)


# ---------------------------------------------------------------- 3. 세로


def _overlap(a: Box, b: Box, pad: float) -> bool:
    return a[0] - pad < b[2] and b[0] < a[2] + pad and a[1] - pad < b[3] and b[1] < a[3] + pad


@dataclass
class _FrameParts:
    """놓는 동안 모으는 loop·opt·alt 프레임의 높이와 조건 글자."""

    top: float
    conditions: list[Label]
    dividers: list[float] = field(default_factory=list)
    bottom: float = 0.0


class _Placer:
    """일을 위에서 아래로 차례대로 놓는다. obstacles는 앞서 놓은 글자·선·머리·화살촉·꼬리표·ref 상자이고, 막대는 계획(_Plan)
    에서 그때그때 상자를 얻는다(밑변이 아직 안 정해진 막대는 끝없이 이어지는 것으로 본다)."""

    def __init__(self, d: Diagram, plan: _Plan, cols: _Columns):
        self.d, self.plan, self.cols = d, plan, cols
        self.index = plan.index
        self.ys: list[float] = []
        self.obstacles: list[Box] = []
        self.floor = 0.0
        self.bottoms: dict[int, float] = {}
        self.heads: dict[int, float] = {}   # 만들어진 참여자 → 머리 윗변
        self.messages: list[PlacedMessage] = []
        self.frames: dict[int, _FrameParts] = {}
        self.refs: list[tuple[Ref, float]] = []
        for i in range(len(d.participants)):
            if i not in plan.created:
                self._add(self._head_box(i, 0.0))

    # -------- 도우미

    def _add(self, box: Box) -> None:
        self.obstacles.append(box)
        self.floor = max(self.floor, box[3])

    def _head_box(self, i: int, top: float) -> Box:
        return _head_box(self.d.participants[i], self.cols.x[i], self.cols.width[i], top)

    def _bar_x(self, b: _Bar) -> float:
        return self.cols.x[b.life] + NEST * b.depth

    def _bottom(self, b: _Bar, e: int) -> float:
        """e번째 일을 놓을 때 막대 밑변. 아직 안 놓인 일에 달렸으면 INF."""
        if b.last >= e:
            return INF
        key = id(b)
        if key not in self.bottoms:
            self.bottoms[key] = max(self.ys[j] + off for j, off in b.terms)
        return self.bottoms[key]

    def _bar_boxes(self, e: int) -> list[tuple[_Bar, Box]]:
        out = []
        for b in self.plan.bars:
            if b.top < e:
                x = self._bar_x(b)
                out.append((b, (x - ACT_W / 2, self.ys[b.top] + b.top_off, x + ACT_W / 2, self._bottom(b, e))))
        return out

    def _closed_bottom(self, e: int) -> float:
        return max((self._bottom(b, e) for b in self.plan.bars if b.top < e and b.last < e), default=-INF)

    def _free_x(self, e: int, start: float, w: float, row: tuple[float, float]) -> float:
        """row 높이를 지나는 막대를 LABEL_GAP 넘게 비켜, start에서 오른쪽으로 가장 가까운 폭 w 상자의 왼쪽 끝."""
        blocks = sorted((bx[0] - LABEL_GAP, bx[2] + LABEL_GAP) for _, bx in self._bar_boxes(e + 1)  # 이 칸에서 막 연 막대까지
                        if bx[1] < row[1] and bx[3] > row[0])
        x = start
        for a, b in blocks:
            if x + w > a and x < b:
                x = b
        return x

    def _condition(self, e: int, y: float, start: float, text: str) -> Label:
        s = f"[{text}]"
        rel = T.place(0, y + COND_Y, s, False, "lm").box
        left = self._free_x(e, start, rel[2] - rel[0], (rel[1] - PAD, rel[3] + PAD))
        label = Label(s, left - rel[0], y + COND_Y, "lm")
        self._add(label.box)
        return label

    def _settle(self, e: int, base: float, pieces: list[tuple[Box, bool]], new_bars: list[_Bar],
                span: tuple[float, float], attached: tuple) -> float:
        """pieces(높이 0 기준 상자, 막대를 피해야 하는지)와 새 막대가 앞서 놓은 것에 걸리지 않고, 선(높이 0, 가로 span)이
        건너는 막대의 끝에서 CLEAR 넘게 떨어지는 가장 위 높이(base 이상)."""
        # y는 base 아래로만 움직이므로, 가장 위로 뻗는 조각보다 PAD 넘게 위에서 끝난 것은 걸릴 수 없다
        reach = base + min([0.0] + [p[0][1] for p in pieces]) - max(PAD, CLEAR, BAR_GAP)
        near = [o for o in self.obstacles if o[3] > reach]
        bars = [(b, bx) for b, bx in self._bar_boxes(e) if bx[3] > reach]
        y = base
        for _ in range(MAX_PUSH):
            need = -INF
            for (x0, dy0, x1, dy1), avoid_bars in pieces:
                box = (x0, y + dy0, x1, y + dy1)
                for o in near:
                    if _overlap(box, o, PAD):
                        need = max(need, o[3] + PAD - dy0 + EPS)
                if avoid_bars:
                    for b, bx in bars:
                        if b not in attached and _overlap(box, bx, PAD):
                            if bx[3] == INF:
                                raise RuntimeError(f"배치 버그: 끝나지 않은 막대에 걸려 내릴 수 없다({box} / {bx})")
                            need = max(need, bx[3] + PAD - dy0 + EPS)
            for b, bx in bars:
                if b in attached or not (bx[0] < span[1] and span[0] < bx[2]):
                    continue
                for end in (bx[1], bx[3]):
                    if end != INF and abs(y - end) < CLEAR:
                        need = max(need, end + CLEAR + EPS)
            for nb in new_bars:
                x = self._bar_x(nb)
                box = (x - ACT_W / 2, y, x + ACT_W / 2, y + ACT_H)
                for o in near:
                    if _overlap(box, o, PAD):
                        need = max(need, o[3] + PAD + EPS)
                for b, bx in bars:
                    if b.life == nb.life and b.depth == nb.depth and bx[3] != INF and bx[3] > y - BAR_GAP:
                        need = max(need, bx[3] + BAR_GAP + EPS)
            if need == -INF:
                return y
            y = max(need, y + EPS)
        raise RuntimeError("배치 버그: 걸리지 않는 높이를 찾지 못했다")

    # -------- 일 놓기

    def _base(self, e: int, below: Optional[bool]) -> float:
        if not e:
            return FIRST
        prev, py = self.plan.events[e - 1], self.ys[e - 1]
        if prev.kind == "message":
            pm = self.d.messages[prev.item]
            prev_below = _label_below(pm, self.index[pm.target] > self.index[pm.source]) if _label_lines(pm) else None
            return max(FIRST, py + (DY_FACING if prev_below is True and below is False else DY))
        if prev.kind in ("start", "branch"):
            return py + FRAME_HEAD
        if prev.kind == "end":
            return py + FRAME_AFTER
        return py + REF_H + REF_AFTER

    def _label_x(self, k: int, lines: list[str], mid: float) -> float:
        """글자 가운데 x. 사이 생명선(아직 만들어지지 않은 것은 빼고)으로 나눈 칸 가운데 글자 상자가 들어가는 칸에, 없으면
        막대가 지나는 사이 생명선으로만 나눈 칸에(지나는 점선은 흰 바탕으로 지운다) 선 가운데에 가장 가깝게 놓는다."""
        left_off, right_off = _extent(lines)
        m = self.d.messages[k]
        s, t = self.index[m.source], self.index[m.target]
        lo, hi = sorted((s, t))
        c = self.cols
        existing = [z for z in range(lo + 1, hi) if self.plan.created.get(z, -1) < k]
        for inner in (existing, list(self.plan.spanning[k])):
            bounds = [lo, *inner, hi]
            best = None
            for p, q in zip(bounds, bounds[1:]):
                left = c.x[p] + _margin(m, s, t, p, True, c)
                right = c.x[q] - _margin(m, s, t, q, False, c)
                if right - left >= right_off - left_off - EPS:
                    x = min(max(mid, left - left_off), right - right_off)
                    if best is None or abs(x - mid) < abs(best - mid):
                        best = x
            if best is not None:
                return best
        raise RuntimeError(f"배치 버그: messages[{k}] 글자가 들어갈 칸이 없다")

    def message(self, e: int, k: int) -> None:
        m = self.d.messages[k]
        s, t = self.index[m.source], self.index[m.target]
        sb, db = self.plan.attach[k]
        c = self.cols
        right = t > s  # 생명선은 참여자 순서대로 왼쪽에서 오른쪽이다
        sign = 1 if right else -1
        x1 = self._bar_x(sb) + sign * ACT_W / 2 if sb is not None else c.x[s]
        if m.kind == "create":
            x2 = c.x[t] - sign * c.width[t] / 2
        elif db is not None:
            x2 = self._bar_x(db) - sign * ACT_W / 2
        else:
            x2 = c.x[t]
        lines = _label_lines(m)
        below = _label_below(m, right) if lines else None
        pieces: list[tuple[Box, bool]] = [((min(x1, x2), 0.0, max(x1, x2), 0.0), False),
                                          ((min(x2, x2 - sign * ARROW), -ARROW_HALF, max(x2, x2 - sign * ARROW), ARROW_HALF),
                                           False)]
        labels_rel = []
        if lines:
            x = self._label_x(k, lines, (c.x[s] + x2) / 2 if m.kind == "create" else (c.x[s] + c.x[t]) / 2)
            dys = ([LABEL_DY] if len(lines) == 1 else [LABEL_DY, CREATE_DY]) if below else \
                ([-LABEL_DY] if len(lines) == 1 else [-CREATE_DY, -LABEL_DY])
            for text, dy in zip(lines, dys):
                labels_rel.append((text, x, dy))
                pieces.append((T.place(x, dy, text, False, "mm").box, True))
        if m.kind == "create":
            head = self._head_box(t, -HEAD_H / 2)
            pieces.append((head, True))
        new_bars = [b for b in (sb, db) if b is not None and b.top == e]
        y = self._settle(e, self._base(e, below), pieces, new_bars, (min(x1, x2), max(x1, x2)), (sb, db))
        self.ys.append(y)
        for (x0, dy0, x1_, dy1), _ in pieces:
            self._add((x0, y + dy0, x1_, y + dy1))
        if m.kind == "create":
            self.heads[t] = y - HEAD_H / 2
        self.messages.append(PlacedMessage(m, f"messages[{k}]", y, x1, x2,
                                           tuple(Label(text, x, y + dy) for text, x, dy in labels_rel)))

    def _edge(self, e: int) -> float:
        """프레임·칸·ref의 가로 선 높이. 맨 처음 일이어도 그 안 첫 메시지가 FIRST보다 위로 가지 않게 한다."""
        return max(self.floor + FRAME_GAP, self._closed_bottom(e) + EDGE_CLEAR, FIRST - FRAME_HEAD)

    def _box_top(self, e: int) -> float:
        """프레임·칸·ref 가로 선 높이. 바로 앞이 메시지면 그 선에서 FRAME_BEFORE, 프레임 밑변이나 ref면 메시지처럼 띄운다
        — 화살촉에 붙거나 두 상자가 붙어 하나로 읽히지 않게."""
        prev = self.plan.events[e - 1] if e else None
        gap = {"message": FRAME_BEFORE, "end": FRAME_AFTER, "ref": REF_H + REF_AFTER}.get(prev.kind) if prev else None
        return max(self._edge(e), self.ys[e - 1] + gap if gap is not None else -INF)

    def start(self, e: int, f: Fragment) -> None:
        y = self._box_top(e)
        self.ys.append(y)
        self._add((LEFT, y, INF, y))
        tag = _tag_width(f.kind)
        self._add((LEFT, y, LEFT + tag, y + TAG_H))
        cond = f.branches[0].condition
        self.frames[f.index] = _FrameParts(y, [self._condition(e, y, LEFT + tag + COND_GAP, cond)] if cond else [])

    def branch(self, e: int, f: Fragment, j: int) -> None:
        y = self._box_top(e)
        self.ys.append(y)
        self._add((LEFT, y, INF, y))
        part = self.frames[f.index]
        part.dividers.append(y)
        part.conditions.append(self._condition(e, y, LEFT + COND_LEFT, f.branches[j].condition))  # alt 칸은 조건이 늘 있다

    def end(self, e: int, f: Fragment) -> None:
        y = max(self._edge(e), self.ys[self.plan.at[f.last]] + FRAME_FOOT)
        self.ys.append(y)
        self._add((LEFT, y, INF, y))
        self.frames[f.index].bottom = y

    def ref(self, e: int, r: Ref) -> None:
        y = self._box_top(e)
        self.ys.append(y)
        self._add((LEFT, y, INF, y + REF_H))
        self.refs.append((r, y))

    def run(self) -> Layout:
        for e, ev in enumerate(self.plan.events):
            if ev.kind == "message":
                self.message(e, ev.item)
            elif ev.kind == "start":
                self.start(e, self.d.fragments[ev.item])
            elif ev.kind == "branch":
                self.branch(e, self.d.fragments[ev.item], ev.branch)
            elif ev.kind == "end":
                self.end(e, self.d.fragments[ev.item])
            else:
                self.ref(e, self.d.refs[ev.item])
        return self._finish()

    def _finish(self) -> Layout:
        d, c, done = self.d, self.cols, len(self.plan.events)
        bars = []
        for b in self.plan.bars:
            bars.append(PlacedBar(d.participants[b.life].name, self._bar_x(b), self.ys[b.top] + b.top_off,
                                  self._bottom(b, done), b.depth))
        life_end = max([self.floor] + [b.bottom for b in bars]) + LIFE_TAIL
        participants = []
        for i, p in enumerate(d.participants):
            top = self.heads.get(i, 0.0)
            dash_top = top + (ACTOR_H if p.kind == "actor" else HEAD_H)
            participants.append(PlacedParticipant(p, c.x[i], c.width[i], top, dash_top, life_end))
        right = max(c.x[i] + max(c.width[i] / 2, c.right_ext[i]) for i in range(len(c.x))) + FRAME_RIGHT
        for part in self.frames.values():
            for cond in part.conditions:
                right = max(right, cond.box[2] + COND_GAP)
        name_left = LEFT + _tag_width("ref") + COND_GAP  # ref 이름 상자가 꼬리표에서 떨어지는 곳
        for r, _ in self.refs:
            left_off, right_off = _extent([r.name])
            right = max(right, name_left + right_off - left_off + COND_GAP)
        frames = tuple(PlacedFrame(f, f"frames[{f.index}]", LEFT, p.top, right, p.bottom, tuple(p.dividers), tuple(p.conditions))
                       for f in d.fragments for p in (self.frames[f.index],))
        refs = []
        for r, top in self.refs:
            left_off, _ = _extent([r.name])
            x = max((LEFT + right) / 2, name_left - left_off)
            refs.append(PlacedRef(r, f"frames[{r.index}]", LEFT, top, right, top + REF_H, Label(r.name, x, top + REF_H / 2)))
        notes = tuple(PlacedNote(s, f"notes[{j}]", LEFT, life_end + NOTE_GAP + NOTE_STEP * j,
                                 max(NOTE_MIN_W, math.ceil(T.text_width(s) + NOTE_PAD)), NOTE_H)
                      for j, s in enumerate(d.notes))
        width = max([right] + [n.left + n.width for n in notes])
        height = notes[-1].top + NOTE_H if notes else life_end
        if max(width, height) > MAX_EXTENT:
            raise InputError([f"그림이 너무 크다(논리 {width:.0f}×{height:.0f}, 한 변 {MAX_EXTENT}까지) — 글자를 줄이거나 "
                              "그림을 나눈다"])
        return Layout(tuple(participants), tuple(bars), tuple(self.messages), frames, tuple(refs), notes)


def layout(diagram: Diagram) -> Layout:
    """막대를 잇고, 생명선 간격과 메시지·프레임 높이를 정한다. 프레임은 모두 같은 폭(그림 전체 폭)이다. 그림 한 변이
    MAX_EXTENT를 넘으면 InputError."""
    plan = _plan(diagram)
    return _Placer(diagram, plan, _columns(diagram, plan)).run()


# ---------------------------------------------------------------- 그리기


def _draw_tag(c: Canvas, left: float, top: float, op: str, owner: str) -> None:
    w = _tag_width(op)
    c.poly([(left, top), (left + w, top), (left + w, top + TAG_SIDE), (left + w - TAG_CUT, top + TAG_H), (left, top + TAG_H)],
           owner=owner)
    c.text(left + TAG_TEXT[0], top + TAG_TEXT[1], op, bold=True, owner=owner)


def _draw_participant(c: Canvas, p: PlacedParticipant) -> None:
    x, top, name, o = p.x, p.top, p.participant.name, p.participant.name
    if p.participant.kind == "actor":
        c.ellipse(x - 6, top, 12, 12, owner=o)
        c.line([(x, top + 12), (x, top + 24)], owner=o)
        c.line([(x - 9, top + 16), (x + 9, top + 16)], owner=o)
        c.line([(x, top + 24), (x - 9, top + 37)], owner=o)
        c.line([(x, top + 24), (x + 9, top + 37)], owner=o)
        c.text(x, top + ACTOR_NAME, name, bold=True, anchor="mm", owner=o)
    else:
        c.rect(x - p.width / 2, top, p.width, HEAD_H, owner=o)
        c.text(x, top + HEAD_NAME, name, bold=True, anchor="mm", owner=o)
    c.line([(x, p.dash_top), (x, p.bottom)], dash=LIFE_DASH, owner=o)


def _draw_message(c: Canvas, m: PlacedMessage) -> None:
    y, o = m.y, m.owner
    if m.message.kind == "call":
        c.line([(m.start, y), (m.end, y)], owner=o)
        c.closed_arrow((m.end, y), (m.start, y), owner=o)
    else:
        c.line([(m.start, y), (m.end, y)], dash=REPLY_DASH, owner=o)
        c.open_arrow((m.end, y), (m.start, y), size=ARROW, owner=o)
    for lab in m.labels:
        c.text(lab.x, lab.y, lab.text, anchor="mm", bg=True, owner=o)


def _draw_note(c: Canvas, n: PlacedNote) -> None:
    l, t, w, h, f = n.left, n.top, n.width, n.height, NOTE_FOLD
    c.poly([(l, t), (l + w - f, t), (l + w, t + f), (l + w, t + h), (l, t + h)], owner=n.owner)
    c.line([(l + w - f, t), (l + w - f, t + f), (l + w, t + f)], owner=n.owner)
    c.text(l + NOTE_TEXT_X, t + h / 2, n.text, owner=n.owner)


def draw(diagram: Diagram, scale: float = SCALE) -> Drawing:
    """프레임 테두리 → 생명선 → 막대 → ref 상자 → 프레임 꼬리표·조건 → 메시지 → 노트 순서로 그린다. ref 상자는 흰 바탕이라
    그 안을 지나는 점선·막대를 덮는다. 메시지 글자와 조건 글자는 흰 바탕을 깔아, 건너는 생명선 점선을 지운다."""
    lay = layout(diagram)
    c = Canvas(scale)
    for f in lay.frames:
        c.rect(f.left, f.top, f.right - f.left, f.bottom - f.top, fill=None, owner=f.owner)
        for y in f.dividers:
            c.line([(f.left, y), (f.right, y)], dash=DIVIDER_DASH, owner=f.owner)
    for p in lay.participants:
        _draw_participant(c, p)
    for b in sorted(lay.bars, key=lambda b: (b.depth, b.top)):
        c.rect(b.x - ACT_W / 2, b.top, ACT_W, b.bottom - b.top, owner=b.owner)
    for r in lay.refs:
        c.rect(r.left, r.top, r.right - r.left, r.bottom - r.top, owner=r.owner)
        _draw_tag(c, r.left, r.top, "ref", r.owner)
        c.text(r.name.x, r.name.y, r.name.text, anchor="mm", owner=r.owner)
    for f in lay.frames:
        _draw_tag(c, f.left, f.top, f.fragment.kind, f.owner)
        for lab in f.conditions:
            c.text(lab.x, lab.y, lab.text, anchor="lm", bg=True, owner=f.owner)
    for m in lay.messages:
        _draw_message(c, m)
    for n in lay.notes:
        _draw_note(c, n)
    return Drawing(c, lay)


def render(data: Any, scale: float = SCALE) -> Drawing:
    """JSON을 읽어 그린다. PNG는 Drawing.canvas.save(경로)나 to_image()로 얻는다 — 그 배율로 그리기에 그림이 너무 크면
    그 둘이 ValueError를 낸다(canvas.MAX_PIXELS)."""
    return draw(parse(data), scale)
