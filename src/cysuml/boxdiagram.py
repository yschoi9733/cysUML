"""AI가 배치하는 그림의 공용 엔진: JSON을 요소·관계 모델로 읽고(parse), 자리를 잡아(layout) 그림판에 그린다(draw).

클래스도·패키지도처럼 요소(모양만 다른 상자)와 요소를 잇는 선, 선 글자(선 위에 얹은 관계 이름, 선 끝 옆 다중도)로 이뤄진 그림이
함께 쓴다. 그림마다 다른 것은
도구 정의(Spec)로 넘긴다 — 받는 요소 종류와 그 모양(Shape), 받는 관계 종류(RelationType), 연관의 기본 방향, 오류 글의 말
(Words), 요소·관계의 짜임 규칙(Rules). 그림 모듈은 모양과 관계 종류를 정의해 Spec에 담기만 하고 이 모듈은 고치지 않는다.

배치는 입력이 정한다 — 요소의 왼쪽 위와 관계선의 꺾는 점은 받은 그대로 쓰고, 여기서는 요소를 글자와 안의 요소에 맞춰
키우고(왼쪽·위는 그대로) 선 끝·선 글자 자리만 계산한다.

틀린 입력은 그리기 전에 InputError로 돌려준다. 문제마다 "classes[0].left: …"처럼 입력 안의 자리를 붙인다. 읽기(parse)의
문제를 한 번에 모두 모아 알리고, 읽기가 통과하면 자리 잡기(layout)에서 선을 그을 수 없는 문제를 한 번에 모두 모아 알린다 —
선 끝은 요소 크기를 알아야 정해지므로 요소가 다 읽혀야 잴 수 있다.
"""
from __future__ import annotations

import math
import numbers
from collections import Counter
from dataclasses import dataclass, field, replace
from functools import cached_property
from typing import Any, Callable, Iterable, Iterator, Mapping, NamedTuple, Optional, Union

from . import text as T
from .canvas import BG_MARGIN, SCALE, Canvas, Line, Point, Polygon, Text
from .geom import Border, RectBorder, Segment, clip, gap, grow, hits, meets, outline, segment_gap, span
from .parsing import InputError, Reader
from .parsing import at as _at
from .parsing import show as _show
from .report import Notice, fmt_num, fmt_rect

NAVIGABLE = ("to", "from", "both", "none")
SIDES = ("bottom", "top", "left", "right")
COORD_LIMIT = 1_000_000

DASH = (5, 4)
TRIANGLE = (18, 9)  # 상속·실체화 빈 삼각형의 길이와 반폭
DIAMOND = 18        # 집합·합성 마름모 길이(그림판 기본값)
ARROW = 10          # 열린 화살촉 길이(그림판 기본값)
# 화살촉 쪽 끝 구간을 꺾을 때 꺾는 점을 끝 요소에서 뗄 거리(입력 오류·relations 인자 설명·고치는 법에 쓴다). 꺾은 앞 구간이 화살촉 갈래 끝에서
# 검사 여유(boxcheck.OVERLAP_GAP 2) 넘게 떨어지려면, 앞 구간이 직각에서 화살촉 쪽으로 β만큼 더 기울 때 끝 구간이
# 10·cos 28° + (2 + 10·sin 28°·sin β) / cos β보다 길어야 한다(직각 10.83, β 30° 13.85, 50° 17.54 — 실측과 맞음). 꺾는 점을 요소
# 가운데 줄에서 비켜 두면 끝 구간이 기울어 β가 생기므로 β 50°까지 덮게 잡는다
ARROW_BEND = 20
# 같은 부모로 공유 줄기 관계 두 종류(split_kinds)가 오면 종류마다 선이 향하는 점을 이만큼 떨어뜨려 가로로 늘어놓는다
# (가운데에서 양쪽으로 반씩). 삼각형 폭 18보다 넉넉해 변에 나란히 놓인 두 삼각형 사이가 12px 남는다
AIM_SPLIT = 30
AIM_EDGE = AIM_SPLIT + 2 * TRIANGLE[1]  # 두 종류의 점을 정하는 가장 좁은 아래·위 변(가운데를 향하는 모양에서). relations 인자 설명이 알린다
# 마지막 꺾는 점(꺾는 점이 없으면 출발 요소의 점)이 종류마다 향하는 점 바로 아래·위인지 볼 때의 여유. 몇 px 셈 실수는 그 점을 쓰려던
# 선으로 받되, 가운데(그 점에서 AIM_SPLIT/2)를 뜻한 선과 헷갈리지 않게 그 한가운데(AIM_SPLIT/4)보다 작게 둔다
AIM_EPS = 5
SIDE_EPS = 1e-6     # 선이 아래·위 변에 닿는지 볼 때의 여유
MAX_LINE = 200_000  # 관계선 하나의 길이 상한 — 그림판 점선 칸 수 상한(MAX_DASHES × 무늬)보다 넉넉히 작게
EDGE_SLACK = 0.5    # 선이 끝 요소 안을 지나는지 볼 때 테두리에서 이만큼 안쪽부터 "안"으로 친다(테두리를 따라 가는 선은 괜찮다)

NAME_GAP = 8        # 이름 글자 상자와 선 사이
LABEL_CLEAR = BG_MARGIN + 1  # 선 글자의 흰 바탕이 선에 닿지 않게 글자 상자를 이만큼 넓혀 선과 견준다
LABEL_LINE = 15     # 여러 줄 선 글자·모양 밖 이름의 줄 간격(줄 상자가 겹치지 않게)
MULT_ANGLES = (math.pi / 8, math.pi / 6, math.pi / 4, math.pi / 3)
MULT_DISTANCES = (20, 25, 30, 35, 40, 50)
MULT_ENOUGH = 20    # 요소와 이만큼 떨어지면 더 멀리 두지 않고 선 끝에 가까운 자리를 고른다
NAME_STEP = 5       # 이름 글자의 가운데 후보가 다 걸릴 때 선을 따라 옮겨 보는 간격
# 선 위에 얹은 이름의 흰 바탕과 선 끝(선 끝 모양이 있으면 그 모양) 사이에 보일 선의 길이 — 점선 무늬 한 주기가 다 보여 점선인지
# 실선인지 가려진다. 짧은 선에 얹으면 선이 흰 바탕 뒤로 거의 다 사라져 관계 종류를 알 수 없다
LINE_SHOW = sum(DASH)
PLACE_EPS = 1e-3    # 여러 선이 걸린 자리가 이 안으로 같으면 한 자리로 묶는다(검사도 이 값으로 묶는다)

NEST_PAD = 20       # 바깥 요소를 늘릴 때 안의 요소 둘레에 두는 여백. 검사도 안의 요소가 칸 테두리에서 이만큼 떨어졌는지 본다
NAME_SEP = 4        # 모양과 모양 밖 이름 사이


# ---------------------------------------------------------------- 그림마다 넘기는 정의


@dataclass(frozen=True)
class Words:
    """오류·검사 글의 말. 클래스도는 상자·변·이름, 새 그림 도구는 요소·테두리·열쇠다. noun 뒤 조사는 글마다 받침 없는 말에 맞춰
    적어 두었으므로(가·를·와·는), noun은 받침 없는 말만 받는다."""

    noun: str
    edge: str
    key: str

    def __post_init__(self):
        last = self.noun[-1:]
        if "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28:
            raise ValueError(f"요소를 부르는 말은 받침 없는 말이어야 한다(검사·오류 글의 조사가 그에 맞춰져 있다): {self.noun!r}")


BOX_WORDS = Words("상자", "변", "이름")
ELEMENT_WORDS = Words("요소", "테두리", "열쇠")


NAME_AREA = "이름 칸"  # NameZone.what의 기본값 — 요소의 글자를 쓰는 자리


def floored(rect: T.Box) -> Point:
    """자리 가운데를 정수로 내린 점. 모양 밖 이름이 모양 자리를 반 픽셀에 놓거나(이름 폭·줄 수가 홀수) 모양 높이·폭이 홀수면 가운데가
    반 픽셀에 걸려, 가운데를 맞춰 놓은 두 요소 사이의 선도 반 픽셀 기울어 계단이 보인다. 선이 향하는 점(Shape.anchor)과 모양을 이
    점에 맞추면, 가운데가 정수인 요소와 잇는 선이 곧다."""
    return math.floor((rect[0] + rect[2]) / 2), math.floor((rect[1] + rect[3]) / 2)


@dataclass(frozen=True)
class NameZone:
    """요소의 글자(이름·스테레오타입 등)를 쓰는 자리. outside면 몸통(선이 닿는 테두리) 밖에 붙은 칸이다(패키지 탭, 모양 밖
    이름) — 그 요소가 끝인 선도 지나가면 안 된다. 몸통 안의 칸은 그 요소를 품은 선만 피하면 된다. 글자를 쓰지 않아도 몸통 밖에
    붙어 선이 지나가면 안 되는 자리(UML 1 표기 컴포넌트의 부품 네모)도 이것으로 넘기고, 검사 글이 그 자리를 부르는 말은 what이다."""

    rect: T.Box
    outside: bool
    what: str = NAME_AREA
    lettered: bool = True  # 글자를 쓰는 칸인지(부품 네모처럼 글자 없이 선만 피하는 자리면 False)


@dataclass(frozen=True)
class Element:
    """요소 하나. key는 관계·중첩이 가리키는 열쇠, name은 이름 줄(이름이 없는 모양은 빈 튜플), parent는 품은 요소의 열쇠,
    data는 모양(Shape.read)이 읽은 필드 값이다. min_width·min_height는 자리(모양 밖 이름까지)의 최소 크기다."""

    key: str
    kind: str
    name: tuple[str, ...]
    stereotype: Optional[str]
    left: float
    top: float
    min_width: float
    min_height: float
    data: Any = None
    parent: Optional[str] = None
    name_side: str = "bottom"


class Shape:
    """요소 모양. 그림 모듈은 이것을 이어받아 겉 테두리·이름 자리·크기·그 모양의 필드 읽기·그리기를 정한다. 기본은 사각형 테두리다.

    rect는 모양 자리(모양 밖 이름은 빼고)다. 모양 밖 이름은 공용 엔진이 쓰고 그 자리를 이름 칸으로 넘긴다."""

    fields: tuple[str, ...] = ()  # 이 모양이 더 받는 필드(공용 필드 밖)
    named: bool = True            # 이름을 받는지(받으면 꼭 준다)
    sized: bool = True            # width·height(자리의 최소 크기)를 받는지
    stereotyped: bool = True      # stereotype을 받는지
    holds: bool = False           # 안에 요소를 둘 수 있는지
    outside_name: bool = False    # 이름을 모양 밖에 쓰는지(쪽은 name_side)
    name_gap: float = NAME_SEP    # 모양 밖 이름을 모양에서 떼는 거리
    aims_aside: bool = False      # 선이 모양 가운데에서 비켜난 점(anchor)을 향하는지 — 결과 글이 그 점을 덧붙인다
    default_width: float = 0      # width를 주지 않았을 때의 최소 폭

    def read(self, r: Reader, o: dict, path: str, kind: Optional[str]) -> Any:
        """이 모양의 필드를 읽는다. 문제는 r.fail로 알린다. kind가 None이면 입력의 kind가 틀렸다(문제만 모으고 값은 쓰지 않는다)."""
        return None

    def keyword(self, e: Element) -> Optional[str]:
        """이름 위 줄에 쓰는 «스테레오타입»."""
        return f"«{e.stereotype}»" if e.stereotype else None

    def size(self, e: Element) -> tuple[float, float]:
        """글자에 맞춘 최소 크기(모양 밖 이름이면 모양만). 안의 요소를 덮는 크기는 엔진이 따로 잰다."""
        return 0.0, 0.0

    def insets(self, e: Element) -> T.Box:
        """안의 요소를 둘 칸이 자리 각 변(왼, 위, 오른, 아래)에서 들어간 폭. holds인 모양만 쓴다."""
        return 0.0, 0.0, 0.0, 0.0

    def border(self, e: Element, rect: T.Box) -> Border:
        """선이 닿는 겉 테두리."""
        return RectBorder(rect)

    def anchor(self, e: Element, rect: T.Box) -> Optional[Point]:
        """선이 향하는 점 — 선 끝은 이 점에서 첫·마지막 꺾는 점(없으면 상대 요소의 이 점)으로 가는 선이 테두리와 만나는 곳이다.
        테두리 안이어야 한다. None(기본)이면 테두리 가운데다. 가운데에서 비켜난 점을 돌려주는 모양은 aims_aside를 켠다 — 결과 글이
        그 점을 덧붙이고 도구 설명이 그것을 알린다(aims_off_center)."""
        return None

    def name_zones(self, e: Element, rect: T.Box) -> tuple[NameZone, ...]:
        """선이 지나가면 안 되는 이름 칸 — 안에 요소를 두는 모양의 이름 칸과, 몸통 밖에 붙은 자리(UML 1 표기 컴포넌트의 부품 네모)."""
        return ()

    def frame(self, e: Element, rect: T.Box) -> tuple[Segment, ...]:
        """안에 요소를 두는 모양의 테두리 선 — 그 안의 요소를 잇는 선이 건너도 되지만 따라가면 안 되고, 선 글자가 겹치면 안 되는 선."""
        return self.border(e, rect).edges()

    def parts(self, e: Element, rect: T.Box) -> tuple[Border, ...]:
        """요소끼리 겹치는지 볼 때 그 요소를 이루는 테두리들. 기본은 자리 사각형 하나이고, 자리 안에 요소가 아닌 빈 곳이 있는
        모양은 실제 모양으로 넘긴다(패키지는 탭과 몸통, 노드는 깎인 모서리를 뺀 육각형). 모양 밖 이름이 있는 요소는 모양과 이름을
        함께 덮는 자리 하나로 본다."""
        return (RectBorder(rect),)

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        raise NotImplementedError


def aims_off_center(shape: Shape) -> bool:
    """모양이 켠 aims_aside를 돌려준다 — 도구 설명과 결과 글이 이 하나를 본다. 판정은 모양이 한다: anchor를 비켜난 점으로 고친
    모양이 켜고, 가운데를 정수로 내린 점처럼 사실상 가운데면 켜지 않는다(test_server가 모든 모양에서 둘이 맞는지 본다)."""
    return shape.aims_aside


@dataclass(frozen=True)
class EndShape:
    """선 끝 모양. draw(그림판, 끝 점, 선 위 그 앞 점, 끝 요소가 향하게 한 점(anchor), owner)는 그린 기록(칠한 모양은 Polygon,
    열린 모양은 Line)을 돌려준다. gap이면 선 끝을 끝 요소 테두리에서 그만큼 띄운다 — 띄운 틈에는 이 모양만 놓인다(원을 틈을 두고
    감싸는 소켓 반원). 검사는 이 모양의 이름(name)과 선 끝 점을 그린 기록에서 짐작하지 않고 여기서 받는다."""

    name: str
    length: float
    draw: Callable[[Canvas, Point, Point, Point, str], Union[Line, Polygon]]
    gap: float = 0.0


ARROW_HEAD = EndShape("화살촉", ARROW, lambda c, tip, frm, at, o: c.open_arrow(tip, frm, size=ARROW, owner=o))
TRIANGLE_HEAD = EndShape("삼각형", TRIANGLE[0], lambda c, tip, frm, at, o: c.closed_arrow(
    tip, frm, filled=False, size=TRIANGLE[0], half=TRIANGLE[1], owner=o))
OPEN_DIAMOND = EndShape("마름모", DIAMOND, lambda c, tip, frm, at, o: c.diamond(tip, frm, filled=False, size=DIAMOND,
                                                                                 owner=o))
FILLED_DIAMOND = EndShape("마름모", DIAMOND, lambda c, tip, frm, at, o: c.diamond(tip, frm, filled=True, size=DIAMOND,
                                                                                  owner=o))


@dataclass(frozen=True)
class RelationType:
    """관계 종류. start·end는 from·to 쪽 끝에 늘 그리는 모양이다. navigable이면 방향(navigable)을 받아 그 쪽에 화살촉을 그리고,
    multiplicity면 다중도를 받는다. trunk면 자식 여럿의 선이 한 줄기로 모여 한 끝 모양을 함께 쓰는 것(공유 줄기)을 받는다.
    reflexive가 아니면 자기 자신으로 가는 관계를 꺾는 점이 있어도 받지 않는다(상속 등). label(상속 등)과 role(from 쪽이 무엇인지
    — 상속은 자식)은 오류 글과 relations 인자 설명(guide.relation_fields)에 쓴다."""

    label: str
    dash: Optional[tuple[float, float]] = None
    start: Optional[EndShape] = None
    end: Optional[EndShape] = None
    navigable: bool = False
    multiplicity: bool = False
    trunk: bool = False
    role: str = ""
    reflexive: bool = True

    def __post_init__(self):
        if self.navigable and self.end is not None:
            raise ValueError("방향을 받는 관계는 to 쪽 끝 모양을 따로 두지 않는다(화살촉이 겹친다)")
        if self.trunk and self.end is None:
            raise ValueError("공유 줄기를 받는 관계는 자식 선들이 함께 쓸 to 쪽 끝 모양이 있어야 한다")


class Rules:
    """요소·관계의 짜임이 UML 표기에 맞는지 보는 규칙(Spec.rules). 선이 겹치는지와 달리 자리와 상관없어 읽기 끝에 본다. 틀린 짜임은
    r.fail로 다른 입력 오류와 함께 모아 그리지 않고, 그리되 뜻을 확인해 볼 짜임은 알림(Notice)으로 돌려 검사 결과에 싣는다. 그림
    모듈은 이것을 이어받아 그 그림의 규칙을 정한다. 자기 자신으로 가는 관계를 막는 것은 관계 종류(RelationType.reflexive)가 정한다."""

    def check(self, r: Reader, spec: Spec, elements: list[tuple[str, Element]],
              relations: list[tuple[str, Relation]]) -> list[Notice]:
        """읽힌 요소와 관계를 (입력 안의 자리, 값)으로 받아 짜임을 본다. 다른 곳이 틀려 읽히지 않은 요소는 elements에 없으니, 끝 요소를
        찾지 못한 관계는 건너뛴다(그 문제는 이미 알렸다). 자기 자신으로 가는 관계는 그 종류가 받을 때(reflexive)만 relations에 든다."""
        return []

    def guide(self, spec: Spec) -> str:
        """relations 인자 설명의 관계 항목(guide.relation_fields)에 붙이는 규칙 글. 줄마다 들여 쓴 "  - " 항목이다. 없으면 빈 글."""
        return ""

    def nests(self, outer: str, inner: str) -> bool:
        """inner 종류 요소를 안에 요소를 두는 outer 종류 요소 안에 둘 수 있는지. 요소가 겹쳤을 때의 안내(boxcheck)는 둘 수 없으면
        in을 권하지 않는다. 엔진은 이것으로 입력을 막지 않는다 — 막는 것은 그림 모듈이 이어받은 check가 그 그림의 오류 글로 한다. 기본은
        모두 된다."""
        return True


NO_RULES = Rules()  # 짜임을 보지 않는 그림의 규칙(Spec.rules 기본값)


def end_of(side: str, key: str, kind: str) -> str:
    """오류·알림 글에서 관계의 한 끝: from 'Circle': 'class'. 이름 바로 뒤에 조사를 붙이지 않는다(영어 이름은 받침을 알 수 없다)."""
    return f"{side} {_show(key)}: {kind!r}"


def ends_of(rel: Relation, source: str, target: str) -> str:
    """오류·알림 글에서 관계의 두 끝(source·target은 두 끝의 요소 종류): from 'A': 'class', to 'B': 'interface'."""
    return f"{end_of('from', rel.source, source)}, {end_of('to', rel.target, target)}"


def parent_path(parents: dict[str, list[str]], start: str, goal: str) -> Optional[list[str]]:
    """parents(자식 → 부모들)의 상속을 따라 start에서 goal로 가는 가장 짧은 길(양 끝 포함). 없으면 None."""
    came: dict[str, Optional[str]] = {start: None}
    queue = [start]
    for key in queue:
        if key == goal:
            path = [key]
            while (up := came[path[-1]]) is not None:
                path.append(up)
            return path[::-1]
        for parent in parents.get(key, ()):
            if parent not in came:
                came[parent] = key
                queue.append(parent)
    return None


def fail_loops(r: Reader, inherits: list[tuple[str, Relation]], parents: dict[str, list[str]], label: str,
               why: str) -> None:
    """고리를 이루는 상속(label — 상속·일반화 등)을 입력 오류로 알린다. inherits는 오류 없는 상속의 (입력 안의 자리, 관계), parents는
    그 상속(자식 → 부모들)이고, why는 고리가 왜 틀렸는지다. 고치는 법은 고리 안의 하나를 지우라고만 한다 — 뒤집으면 이미 있는
    관계와 같아지거나(두 관계 고리는 늘) 다른 고리가 남을 수 있다. 같은 from·to의 상속이 여럿이면 그것을 모두 지우라고 덧붙인다(하나만
    지우면 고리가 남는다). 고리(그 고리를 이루는 상속들)마다 입력에서 먼저 나온 상속에서 한 번 알린다."""
    count = Counter((rel.source, rel.target) for _, rel in inherits)
    loops: set[frozenset[tuple[str, str]]] = set()
    for path, rel in inherits:
        back = parent_path(parents, rel.target, rel.source)
        if back is None:
            continue
        ring = [rel.source, *back]
        edges = frozenset(zip(ring, ring[1:]))
        if edges in loops:
            continue
        loops.add(edges)
        pairs = list(zip(ring, ring[1:]))
        if all(count[e] == 1 for e in pairs):
            fix = "둘 가운데 하나를 지운다" if len(pairs) == 2 else f"고리 안의 {label} 하나를 지운다"
        elif len(pairs) == 2:  # 같은 from·to가 여럿이면 하나만 지워서는 고리가 남는다 — 방향마다 몇 개인지 적는다
            fix = "한 방향의 관계를 모두 지운다(" + ", ".join(f"{_show(x)} → {_show(y)} {count[(x, y)]}개" for x, y in pairs) + ")"
        else:
            fix = (f"고리 안의 from·to 하나를 골라 그 {label}{josa(label, '을', '를')} 모두 지운다(같은 from·to의 "
                   f"{label}{josa(label, '이', '가')} 여럿 있다)")
        r.fail(path, f"{label}{josa(label, '이', '가')} 고리를 이룬다({' → '.join(_show(k) for k in ring)}) — {why}. {fix}")


@dataclass(frozen=True, eq=False)
class Spec:
    """도구 하나가 받는 것. shapes는 요소 종류 → 모양, relations는 관계 종류 → 정의다. navigable은 방향을 받는 관계(연관·집합·
    합성)의 기본 방향이다. extended면 새 도구 입력(id·in·여러 줄 이름·관계 stereotype·name_side)을 받는다 — 클래스도 도구는
    받지 않는다. 관계 종류가 하나뿐이면 관계의 kind를 빼도 그 종류로 읽는다. rules는 요소·관계의 짜임 규칙이다(기본은 보지 않는
    NO_RULES)."""

    shapes: Mapping[str, Shape]
    relations: Mapping[str, RelationType]
    words: Words = ELEMENT_WORDS
    list_field: str = "elements"
    default_kind: Optional[str] = None
    navigable: str = "to"
    extended: bool = True
    rules: Rules = NO_RULES

    def __post_init__(self):
        if self.navigable not in ("to", "none"):
            raise ValueError(f"연관의 기본 방향은 'to'나 'none'이다: {self.navigable!r}")
        for shape in self.shapes.values():
            if shape.holds and shape.outside_name or shape.outside_name and shape.sized:
                raise ValueError(f"모양 밖 이름을 쓰는 모양은 안에 요소를 두거나 크기를 받지 않는다: {shape!r}")

    @property
    def default_relation(self) -> Optional[str]:
        return next(iter(self.relations)) if len(self.relations) == 1 else None

    def element_fields(self, shape: Optional[Shape]) -> tuple[str, ...]:
        """요소가 받는 필드. 모양을 모르면(kind가 틀렸다) 모든 모양의 필드."""
        shapes = [shape] if shape is not None else list(self.shapes.values())
        out = (("id",) if self.extended else ()) + (("name",) if any(s.named for s in shapes) else ()) + ("kind",)
        out += ("stereotype",) if any(s.stereotyped for s in shapes) else ()
        out += tuple(dict.fromkeys(f for s in shapes for f in s.fields))
        out += ("in",) if self.extended else ()
        out += ("left", "top") + (("width", "height") if any(s.sized for s in shapes) else ())
        out += ("name_side",) if self.extended and any(s.outside_name for s in shapes) else ()
        return out

    def relation_fields(self) -> tuple[str, ...]:
        types = self.relations.values()
        return (("kind", "from", "to", "name") + (("stereotype",) if self.extended else ())
                + (("from_multiplicity", "to_multiplicity") if any(t.multiplicity for t in types) else ())
                + (("navigable",) if any(t.navigable for t in types) else ()) + ("via",))


# ---------------------------------------------------------------- 모델


@dataclass(frozen=True)
class Relation:
    kind: str
    source: str
    target: str
    name: tuple[str, ...]
    stereotype: Optional[str]
    source_multiplicity: Optional[str]
    target_multiplicity: Optional[str]
    navigable: Optional[str]  # 방향을 받는 관계만 — 그 밖은 None
    via: tuple[Point, ...]

    @property
    def label_lines(self) -> tuple[str, ...]:
        """이름 자리에 쓰는 줄: «스테레오타입» 줄 아래에 이름 줄."""
        return ((f"«{self.stereotype}»",) if self.stereotype else ()) + self.name


@dataclass(frozen=True)
class Diagram:
    """notices는 읽기에서 나온 표기 규칙 알림(Spec.rules)이다 — 그린 결과(Drawing)를 거쳐 검사 결과에 실린다."""

    spec: Spec
    boxes: tuple[Element, ...]
    relations: tuple[Relation, ...]
    notices: tuple[Notice, ...] = ()


@dataclass(frozen=True)
class PlacedBox:
    """자리를 잡은 요소. rect는 자리(모양 밖 이름까지 덮는다), shape_rect는 모양 자리, inner는 안의 요소를 둘 칸(안에 요소를 둘 수
    없는 모양은 None), zones는 이름 칸, frame은 안에 요소를 두는 모양의 테두리 선, parts는 겹침을 볼 때 그 요소를 이루는 테두리들
    (Shape.parts), anchor는 선이 향하는 점(Shape.anchor — 없으면 테두리 가운데)이다. aims는 split_kinds의 두 종류가 다 올 때
    종류(관계 kind)마다 정한 점이다(_split_aims) — 그 점 바로 아래나 위에서 곧게 들어오는 그 종류의 선만 그 점을 향하고(_aim),
    그 밖의 선은 anchor를 향한다."""

    box: Element
    shape: Shape = field(compare=False, repr=False)
    rect: T.Box
    shape_rect: T.Box
    border: Border
    zones: tuple[NameZone, ...] = ()
    inner: Optional[T.Box] = None
    frame: tuple[Segment, ...] = ()
    name_at: tuple[tuple[float, float], ...] = ()  # 모양 밖 이름 줄마다 가운데
    parts: tuple[Border, ...] = ()
    anchor: Optional[Point] = None
    aims: tuple[tuple[str, Point], ...] = ()

    def __post_init__(self):
        if not self.parts:
            object.__setattr__(self, "parts", (RectBorder(self.rect),))
        if self.anchor is None:
            object.__setattr__(self, "anchor", self.border.center())

    @property
    def key(self) -> str:
        return self.box.key

    def aim_of(self, kind: str) -> Optional[Point]:
        """관계 종류 kind의 향하는 점(aims). 없으면 None."""
        return dict(self.aims).get(kind)

    @property
    def width(self) -> float:
        return self.rect[2] - self.rect[0]

    @property
    def height(self) -> float:
        return self.rect[3] - self.rect[1]


@dataclass(frozen=True)
class Label:
    """선에 붙는 글자(가운데가 (x, y)). role은 name·from_multiplicity·to_multiplicity, lines는 위에서부터 줄이다. segment는 이름을
    그 관계의 선 위에 얹었을 때 얹은 구간의 번호다(선의 점 points[k]에서 points[k+1]로 가는 구간이면 k). 선 옆에 놓은 이름과
    다중도는 None이다."""

    role: str
    lines: tuple[str, ...]
    x: float
    y: float
    segment: Optional[int] = None

    @property
    def text(self) -> str:
        return " ".join(self.lines)


@dataclass(frozen=True)
class PlacedRelation:
    """owner는 그 관계를 그린 기록의 owner다 — 보통 "출발->도착"이고, 같은 이름이 앞에 있으면 "#2"·"#3"을 붙인다. aim은 이 선이
    도착 요소의 anchor 대신 향하는 종류마다의 점이다(_aim — 없으면 None). start는 출발 요소에서 선을 낸 점이다(_from_at — 보통
    출발 요소의 anchor)."""

    relation: Relation
    owner: str
    points: tuple[Point, ...]
    labels: tuple[Label, ...]
    start: Point
    aim: Optional[Point] = None


@dataclass(frozen=True)
class Layout:
    """lines_of는 요소마다 품은 요소들(lineage)이다 — 자리 잡기가 이미 잰 것을 넘기고, 주지 않으면 여기서 잰다."""

    spec: Spec = field(compare=False, repr=False)
    boxes: tuple[PlacedBox, ...]
    relations: tuple[PlacedRelation, ...]
    lines_of: Optional[Mapping[str, tuple[str, ...]]] = field(default=None, compare=False, repr=False)

    def __post_init__(self):
        if self.lines_of is None:
            object.__setattr__(self, "lines_of", lineage({p.key: p.box.parent for p in self.boxes}))

    @cached_property
    def by_key(self) -> dict[str, PlacedBox]:
        return {p.key: p for p in self.boxes}

    @cached_property
    def parents(self) -> frozenset[str]:
        """안에 다른 요소를 품은 요소의 열쇠."""
        return frozenset(p.box.parent for p in self.boxes if p.box.parent is not None)

    def ancestors(self, key: str) -> tuple[str, ...]:
        """key를 품은 요소들(바로 품은 것부터 바깥으로)."""
        assert self.lines_of is not None
        return self.lines_of[key]

    def holders(self, r: Relation) -> frozenset[str]:
        """관계의 끝 요소를 품은 요소들."""
        assert self.lines_of is not None
        return holders(self.lines_of, r)

    def kind_of(self, r: Relation) -> RelationType:
        return self.spec.relations[r.kind]


@dataclass(frozen=True)
class HeadMark:
    """그린 선 끝 모양 하나의 이름(EndShape.name)과 그 모양이 얹힌 선 끝 점."""

    name: str
    tip: Point


@dataclass(frozen=True)
class DrawnRelation:
    """관계 하나를 그린 기록: 선(line), 선 끝 모양(heads — 칠한 모양은 Polygon, 열린 모양은 Line)과 그 이름·끝 점(marks — heads
    차례로), 선 글자(labels — PlacedRelation.labels 차례로, 글자마다 줄마다의 기록)."""

    line: Line
    heads: tuple[Union[Line, Polygon], ...]
    labels: tuple[tuple[Text, ...], ...]
    marks: tuple[HeadMark, ...]


@dataclass(frozen=True)
class Drawing:
    """drawn은 관계마다(layout.relations 차례) 그린 기록이다 — 검사가 그림판 기록을 거꾸로 짚어 찾지 않게 넘긴다. notices는
    읽기에서 나온 표기 규칙 알림(Diagram.notices)이다."""

    canvas: Canvas
    layout: Layout
    drawn: tuple[DrawnRelation, ...]
    notices: tuple[Notice, ...] = ()


# ---------------------------------------------------------------- 입력 읽기


def ancestors(parent_of: Mapping[str, Optional[str]], key: str) -> list[str]:
    """key를 품은 요소들(바로 품은 것부터 바깥으로). parent_of는 열쇠 → 품은 요소의 열쇠다. 모르는 열쇠나 고리(in이 서로를
    가리킨다)에 닿으면 거기서 멈춘다."""
    out: list[str] = []
    up = parent_of.get(key)
    while up is not None and up in parent_of and up != key and up not in out:
        out.append(up)
        up = parent_of[up]
    return out


def lineage(parent_of: Mapping[str, Optional[str]]) -> dict[str, tuple[str, ...]]:
    """요소마다 그 요소를 품은 요소들(ancestors). 읽기·자리 잡기·검사가 모두 이것으로 품은 사이를 본다."""
    return {key: tuple(ancestors(parent_of, key)) for key in parent_of}


def holders(lines: Mapping[str, tuple[str, ...]], r: Relation) -> frozenset[str]:
    """관계의 끝 요소를 품은 요소들(lines는 lineage의 값)."""
    return frozenset(lines.get(r.source, ())) | frozenset(lines.get(r.target, ()))


def josa(word: str, with_final: str, without_final: str) -> str:
    """word 뒤에 붙는 조사(받침이 있으면 with_final). 한글 음절이 아니면 받침 없는 쪽."""
    last = word[-1:]
    return with_final if "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 else without_final


class _Reader(Reader):
    def __init__(self, spec: Spec):
        super().__init__()
        self.spec = spec

    def number(self, v, path: str, least: float = -COORD_LIMIT) -> Optional[float]:
        try:
            f = float(v) if isinstance(v, numbers.Real) and not isinstance(v, bool) else math.nan
        except OverflowError:  # float으로 못 바꾸는 큰 정수(JSON 정수는 자릿수 제한이 없다)
            f = math.inf
        if math.isnan(f):
            self.fail(path, f"수여야 한다(받은 값 {_show(v)})")
            return None
        if not least <= f <= COORD_LIMIT:
            self.fail(path, f"{fmt_num(least)}~{fmt_num(COORD_LIMIT)} 사이여야 한다(받은 값 {_show(v)})")
            return None
        return f

    def point(self, v, path: str) -> Optional[Point]:
        if not isinstance(v, (list, tuple)) or len(v) != 2:
            self.fail(path, f"[x, y]여야 한다(받은 값 {_show(v)})")
            return None
        x, y = self.number(v[0], _at(path, 0)), self.number(v[1], _at(path, 1))
        return None if x is None or y is None else (x, y)

    def lines(self, v, path: str, bold: bool = False, name: bool = False) -> Optional[tuple[str, ...]]:
        """글자 한 줄이나, 새 도구면 줄마다 문자열인 목록(여러 줄). 줄 안에 줄바꿈은 넣지 못한다."""
        if self.spec.extended and isinstance(v, (list, tuple)):
            if not v:
                self.fail(path, "비어 있다")
                return None
            got = [self.text(s, _at(path, i), bold, name) for i, s in enumerate(v)]
            return None if None in got else tuple(got)  # type: ignore[arg-type]
        if self.spec.extended and not isinstance(v, str):
            self.fail(path, f"문자열이나 줄마다 문자열인 목록이어야 한다(받은 값 {_show(v)})")
            return None
        s = self.text(v, path, bold, name)
        return None if s is None else (s,)

    def stereotype(self, o: dict, path: str) -> Optional[str]:
        if "stereotype" not in o:
            return None
        s = self.text(o["stereotype"], _at(path, "stereotype"), name=True)
        if s and (s[:1] in "«<" or s[-1:] in "»>"):
            self.fail(_at(path, "stereotype"), f"«» 없이 이름만 쓴다(받은 값 {_show(s)})")
        return s

    # -------- 요소

    def element(self, v, path: str) -> tuple[Optional[str], Optional[str], Optional[Element]]:
        """(읽은 열쇠, 열쇠를 읽은 자리, 요소). 열쇠만 맞고 다른 곳이 틀렸으면 요소는 None이다 — 그 열쇠를 가리키는 관계를 "없는
        요소"로 또 알리지 않으려고 열쇠를 따로 돌려준다."""
        spec = self.spec
        if not isinstance(v, dict):
            self.fail(path, f"객체여야 한다(받은 값 {_show(v)})")
            return None, None, None
        peek = v.get("kind", spec.default_kind)
        shape = spec.shapes.get(peek) if isinstance(peek, str) else None
        fields = spec.element_fields(shape)
        # 모양을 모르면(kind가 없거나 틀렸다) 이름 없는 모양이 하나도 없을 때만 이름이 빠졌다고 함께 알린다
        named = shape.named if shape is not None else all(s.named for s in spec.shapes.values())
        required = ("name",) * named + ("kind",) * (spec.default_kind is None) + ("left", "top")
        before = len(self.problems)
        self.obj(v, path, fields, required)
        o = {k: x for k, x in v.items() if k in fields}  # 모르는 필드는 위에서 알렸다
        name = self.lines(o["name"], _at(path, "name"), bold=True, name=True) if "name" in o else None
        kind = self.choice(o["kind"], _at(path, "kind"), tuple(spec.shapes)) if "kind" in o else spec.default_kind
        shape = spec.shapes.get(kind) if kind is not None else None
        stereotype = self.stereotype(o, path)
        reader = shape
        if reader is None:  # kind가 틀렸어도 받은 필드를 맡는 모양이 하나뿐이면 그 모양으로 읽어 문제를 함께 알린다
            owners = {id(s): s for s in spec.shapes.values() if any(f in o for f in s.fields)}
            reader = next(iter(owners.values())) if len(owners) == 1 else None
        data = reader.read(self, o, path, kind) if reader is not None else None
        parent = self.text(o["in"], _at(path, "in"), name=True) if "in" in o else None
        left = self.number(o["left"], _at(path, "left")) if "left" in o else None
        top = self.number(o["top"], _at(path, "top")) if "top" in o else None
        default_width = shape.default_width if shape is not None else 0.0
        width = self.number(o["width"], _at(path, "width"), least=0) if "width" in o else default_width
        height = self.number(o["height"], _at(path, "height"), least=0) if "height" in o else 0.0
        side = self.choice(o["name_side"], _at(path, "name_side"), SIDES) if "name_side" in o else "bottom"
        key, key_path = None, None
        if "id" in o:
            key, key_path = self.text(o["id"], _at(path, "id"), name=True), _at(path, "id")
            if key is None and name is not None and len(name) == 1:  # 틀린 id는 알렸으니, 이름으로 가리킨 관계를 "없는 요소"로 또 알리지 않는다
                key, key_path = name[0], _at(path, "name")
        elif name is not None and len(name) == 1:
            key, key_path = name[0], _at(path, "name")
        elif name is not None:
            self.fail(path, "'id' 필드가 빠졌다 — 이름이 여러 줄이면 관계·in이 가리킬 열쇠를 id로 준다")
        elif shape is not None and not shape.named:
            self.fail(path, "'id' 필드가 빠졌다 — 이름이 없는 요소는 관계·in이 id로 가리킨다")
        if len(self.problems) > before:
            return key, key_path, None
        assert key is not None and kind is not None and left is not None and top is not None
        return key, key_path, Element(key, kind, name or (), stereotype, left, top, width, height, data, parent, side)

    # -------- 관계

    def relation(self, v, path: str) -> tuple[Optional[str], Optional[str], Optional[Relation]]:
        """(읽은 from, 읽은 to, 관계). 다른 필드가 틀려 관계가 None이어도 from·to가 없는 요소를 가리키는지는 함께 알리려고
        두 열쇠를 따로 돌려준다."""
        spec = self.spec
        before = len(self.problems)
        fields = spec.relation_fields()
        o = self.obj(v, path, fields, (("kind",) if spec.default_relation is None else ()) + ("from", "to"))
        if o is None:
            return None, None, None
        o = {k: x for k, x in o.items() if k in fields}  # 모르는 필드는 위에서 알렸다
        kind = (self.choice(o["kind"], _at(path, "kind"), tuple(spec.relations)) if "kind" in o
                else spec.default_relation)
        t = spec.relations.get(kind) if kind is not None else None
        source = self.text(o["from"], _at(path, "from"), name=True) if "from" in o else None
        target = self.text(o["to"], _at(path, "to"), name=True) if "to" in o else None
        name = self.lines(o["name"], _at(path, "name")) if "name" in o else ()
        stereotype = self.stereotype(o, path)
        types = spec.relations.values()
        mults = []
        for key in ("from_multiplicity", "to_multiplicity"):
            if key in o and t is not None and not t.multiplicity:
                which = "·".join(x.label for x in types if x.multiplicity)
                self.fail(_at(path, key), f"다중도는 {which}에만 쓴다(이 관계는 {kind!r})")
            mults.append(self.text(o[key], _at(path, key)) if key in o and t is not None and t.multiplicity else None)
        navigable = None
        if t is not None and t.navigable:
            navigable = self.choice(o["navigable"], _at(path, "navigable"), NAVIGABLE) if "navigable" in o else spec.navigable
            if t.start is not None and navigable in ("from", "both"):
                kinds = "·".join(x.label for x in types if x.navigable and x.start is not None)
                shape = t.start.name
                self.fail(_at(path, "navigable"), f"{kinds}{josa(kinds, '은', '는')} {shape}{josa(shape, '이', '가')} 있는 "
                                                  "from 쪽에 화살촉을 둘 수 없다 — 'to'나 'none'을 쓴다")
        elif "navigable" in o and t is not None:
            which = "·".join(x.label for x in types if x.navigable)
            tail = " — 화살촉은 늘 to 쪽이다" if t.end is not None else ""
            self.fail(_at(path, "navigable"), f"방향은 {which}에만 쓴다(이 관계는 {kind!r}{tail})")
        via: list[Optional[Point]] = []
        for i, p in enumerate(self.items(o["via"], _at(path, "via")) if "via" in o else []):
            q = self.point(p, _at(_at(path, "via"), i))
            if q is not None and via and q == via[-1]:
                self.fail(_at(_at(path, "via"), i), f"앞 꺾는 점과 같다 {q}")
            via.append(q)
        if source is not None and source == target:
            if t is not None and not t.reflexive:
                self.fail(path, f"{t.label}{josa(t.label, '은', '는')} 자기 자신으로 갈 수 없다 — from과 to를 다른 "
                                f"{spec.words.noun}{josa(spec.words.noun, '으로', '로')} 고친다")
            elif len(via) < 2:
                self.fail(path, "자기 자신으로 가는 관계는 꺾는 점(via)이 둘 이상 있어야 고리로 그릴 수 있다")
        if len(self.problems) > before:
            return source, target, None
        assert kind is not None and source is not None and target is not None and name is not None
        return source, target, Relation(kind, source, target, name, stereotype, mults[0], mults[1], navigable,
                                        tuple(via))  # type: ignore[arg-type]

    # -------- 그림

    def _known(self, seen: dict[str, Any]) -> str:
        return ", ".join(_show(n) for n in list(seen)[:20]) + (" …" if len(seen) > 20 else "")

    def _missing(self, path: str, key: str, seen: dict[str, Any]) -> None:
        w = self.spec.words
        self.fail(path, f"{w.key}{josa(w.key, '이', '가')} {_show(key)}인 {w.noun}{josa(w.noun, '이', '가')} 없다"
                        f"(있는 {w.noun}: {self._known(seen) or '없음'})")

    def _parents(self, read: list[tuple[str, Element]], seen: dict[str, int],
                 parent_of: dict[str, Optional[str]]) -> None:
        """in이 가리키는 요소를 본다."""
        field_ = self.spec.list_field
        by_key = {e.key: e for _, e in read}
        loops: set[frozenset[str]] = set()
        for path, e in read:
            if e.parent is None:
                continue
            where = _at(path, "in")
            if e.parent not in seen:
                self._missing(where, e.parent, seen)
            elif e.parent == e.key:
                self.fail(where, "자기 자신 안에 둘 수 없다")
            elif e.parent not in by_key:
                continue  # 그 요소가 다른 곳이 틀려 읽히지 않았다(그 문제는 이미 알렸다)
            elif not self.spec.shapes[by_key[e.parent].kind].holds:
                holding = " · ".join(repr(k) for k, s in self.spec.shapes.items() if s.holds)
                self.fail(where, f"{field_}[{seen[e.parent]}]({by_key[e.parent].kind!r})는 안에 요소를 둘 수 없다 — 안에 "
                                 f"요소를 두는 종류: {holding or '없음'}")
            else:
                chain = [e.key, *ancestors(parent_of, e.key)]
                # 이 요소로 돌아오는 고리만, 고리마다 입력에서 처음 나온 요소에서 한 번 알린다
                if parent_of.get(chain[-1]) == e.key and frozenset(chain) not in loops:
                    loops.add(frozenset(chain))
                    self.fail(where, f"in이 고리를 이룬다({' → '.join(_show(k) for k in chain + [e.key])})")

    def diagram(self, data) -> Optional[Diagram]:
        spec, w = self.spec, self.spec.words
        field_ = spec.list_field
        o = self.obj(data, "", (field_, "relations"), (field_,))
        if o is None:
            return None
        raw = self.items(o[field_], field_) if field_ in o else []
        if field_ in o and isinstance(o[field_], (list, tuple)) and not raw:
            self.fail(field_, f"{w.noun}{josa(w.noun, '이', '가')} 하나 이상 있어야 한다")
        got = [(_at(field_, i), self.element(v, _at(field_, i))) for i, v in enumerate(raw)]
        seen: dict[str, int] = {}
        for i, (path, (key, key_path, _)) in enumerate(got):
            if key is None:
                continue
            if key in seen:
                if not spec.extended:
                    why = f"관계가 {w.key}으로 {w.noun}를 가리키므로 {w.key}은 달라야 한다"
                elif key_path is not None and key_path.endswith(".id"):
                    why = "관계·in이 열쇠로 요소를 가리키므로 열쇠는 달라야 한다"
                else:
                    why = "id가 없으면 이름이 열쇠다 — 이름이 같은 요소는 id로 가른다"
                what = "이름" if not spec.extended else "열쇠"
                self.fail(key_path or path, f"{field_}[{seen[key]}]와 {what}{josa(what, '이', '가')} 같다 — {why}")
            else:
                seen[key] = i
        read = [(path, e) for path, (_, _, e) in got if e is not None]
        parent_of = {e.key: e.parent for _, e in read}
        self._parents(read, seen, parent_of)
        lines_of = lineage(parent_of)  # in이 틀린 요소가 있어도 맞는 in만으로 잰다(ancestors는 고리·없는 열쇠에서 멈춘다)
        relations: list[tuple[str, Relation]] = []
        for i, v in enumerate(self.items(o["relations"], "relations") if "relations" in o else []):
            path = _at("relations", i)
            source, target, r = self.relation(v, path)
            missing = [(key, n) for key, n in (("from", source), ("to", target)) if n is not None and n not in seen]
            for key, n in missing:
                self._missing(_at(path, key), n, seen)
            if r is None or missing:
                continue
            outer_first = r.source in lines_of.get(r.target, ())
            if outer_first or r.target in lines_of.get(r.source, ()):
                inner, outer = (r.target, r.source) if outer_first else (r.source, r.target)
                self.fail(path, f"한 끝({_show(inner)})이 다른 끝({_show(outer)}) 안에 있다 — 품은 {w.noun}와 그 안의 "
                                f"{w.noun}는 선으로 잇지 않는다")
                continue
            relations.append((path, r))
        notices = spec.rules.check(self, spec, read, relations)
        return Diagram(spec, tuple(e for _, e in read), tuple(r for _, r in relations), tuple(notices))


def parse(spec: Spec, data: Any) -> Diagram:
    """JSON(을 읽은 파이썬 값)을 그 도구의 모델로 읽는다. 틀린 곳이 있으면 모두 모아 InputError."""
    reader = _Reader(spec)
    diagram = reader.diagram(data)
    if reader.problems:
        raise InputError(reader.problems)
    assert diagram is not None
    return diagram


# ---------------------------------------------------------------- 자리 잡기


def lines_box(x: float, y: float, lines: tuple[str, ...], bold: bool = False) -> T.Box:
    """가운데가 (x, y)인 여러 줄 글자(줄 간격 LABEL_LINE)의 줄 상자를 모두 덮는 상자."""
    boxes = [T.place(x, ly, s, bold, "mm").box for s, ly in zip(lines, line_ys(y, len(lines)))]
    return span(pt for b in boxes for pt in (b[:2], b[2:]))


def line_ys(y: float, n: int) -> list[float]:
    """가운데가 y인 n줄 글자의 줄마다 가운데 높이."""
    return [y + (i - (n - 1) / 2) * LABEL_LINE for i in range(n)]


def _segments_by_length(points: tuple[Point, ...]) -> list[int]:
    """구간 번호를 긴 것부터(길이가 같으면 앞 구간부터)."""
    return sorted(range(len(points) - 1), key=lambda j: (-math.dist(points[j], points[j + 1]), j))


def _along(p: Point, q: Point, along: float = 0.0) -> Point:
    ln = math.dist(p, q)
    return (p[0] + q[0]) / 2 + (q[0] - p[0]) / ln * along, (p[1] + q[1]) / 2 + (q[1] - p[1]) / ln * along


def _beside(p: Point, q: Point, box: T.Box, along: float = 0.0) -> list[Point]:
    """구간 pq의 가운데에서 p→q 쪽으로 along만큼 간 점에서, 진행 방향의 왼쪽(오른쪽으로 가는 가로선이면 위)과 오른쪽으로
    글자 상자(box — 가운데가 원점)가 선과 NAME_GAP만큼 떨어지는 두 자리."""
    ln = math.dist(p, q)
    ux, uy = (q[0] - p[0]) / ln, (q[1] - p[1]) / ln
    mx, my = _along(p, q, along)
    out = []
    for nx, ny in ((uy, -ux), (-uy, ux)):
        reach = max(-(cx * nx + cy * ny) for cx in (box[0], box[2]) for cy in (box[1], box[3]))  # 선을 마주 보는 쪽 끝까지
        out.append((mx + nx * (reach + NAME_GAP), my + ny * (reach + NAME_GAP)))
    return out


def name_spots(points: tuple[Point, ...], lines: Union[str, tuple[str, ...]]) -> list[Point]:
    """이름 글자 가운데의 후보: 가장 긴 구간(길이가 같으면 앞 구간)의 가운데에서 선 양옆의 두 자리(_beside). 꺾는 점에서 먼
    곳이라 다른 구간에 덜 걸린다."""
    if isinstance(lines, str):
        lines = (lines,)
    k = _segments_by_length(points)[0]
    return _beside(points[k], points[k + 1], lines_box(0, 0, lines))


def _room(p: Point, q: Point, box: T.Box) -> float:
    """구간 pq(길이가 0이 아니다)의 가운데에 둔 글자 상자(box — 가운데가 원점)를 구간 방향으로 비춘 폭이 구간 안에 들도록 가운데에서
    옮길 수 있는 거리. 음수면 가운데에도 들지 않는다."""
    ln = math.dist(p, q)
    ux, uy = (q[0] - p[0]) / ln, (q[1] - p[1]) / ln
    return ln / 2 - max(abs(cx * ux + cy * uy) for cx in (box[0], box[2]) for cy in (box[1], box[3]))


def _steps(points: tuple[Point, ...], box: T.Box) -> Iterator[tuple[int, int, list[float]]]:
    """이름 글자를 선을 따라 옮길 구간을 길이 차례로 (차례, 구간 번호, 가운데에서 옮길 거리들)로 낸다. 거리는 NAME_STEP씩이고, 글자
    상자(box — 가운데가 원점)가 구간 안에 드는 것만이다(_room). 가운데에도 글자가 들지 않는 구간은 내지 않는다."""
    for n, k in enumerate(_segments_by_length(points)):
        p, q = points[k], points[k + 1]
        if p == q:
            continue
        room = _room(p, q, box)
        if room >= 0:
            yield n, k, [i * NAME_STEP for i in range(1, int(room // NAME_STEP) + 1)]


def _far(box: T.Box) -> float:
    return max(math.hypot(cx, cy) for cx in (box[0], box[2]) for cy in (box[1], box[3]))


def slide_spots(points: tuple[Point, ...], lines: tuple[str, ...]) -> Iterator[tuple[T.Box, list[list[Point]]]]:
    """이름 글자를 선 옆에서 선을 따라 옮길 때(옮기는 조건은 _Spots.pick_name) 더 볼 자리를 구간마다 (띠, 묶음들)로 낸다. 묶음은
    가운데에서 가까운 것부터다 — 가장 긴 구간은 가운데에서 양쪽으로 NAME_STEP씩 옮긴 자리마다 선 양옆 둘(진행 방향 앞쪽·뒤쪽 차례로
    네 자리가 한 묶음), 그다음 구간도 길이 차례로 그 가운데(두 자리)부터 같게 낸다. 구간마다 낸 자리의 글자는 그 구간 옆을 벗어나지
    않는다(_steps). 띠는 그 구간 묶음들의 흰 바탕을 다 덮는 상자다."""
    box = lines_box(0, 0, lines)
    # 글자 가운데는 선에서 (원점에서 가장 먼 모서리까지) + NAME_GAP 안이고, 흰 바탕은 그 가운데에서 다시 그만큼 + LABEL_CLEAR 안이다
    far = _far(box)
    for n, k, steps in _steps(points, box):
        p, q = points[k], points[k + 1]
        rings = ([_beside(p, q, box)] if n else []) + [_beside(p, q, box, d) + _beside(p, q, box, -d) for d in steps]
        if rings:
            yield grow(span((p, q)), 2 * far + NAME_GAP + LABEL_CLEAR), rings


def on_spots(points: tuple[Point, ...], lines: tuple[str, ...]) -> Iterator[tuple[int, T.Box, list[list[Point]]]]:
    """이름 글자를 그 관계의 선 위에 얹은 채 선을 따라 옮길 때(_Spots.pick_on_line) 더 볼 자리를 구간마다 (구간 번호, 띠, 묶음들)로
    낸다. 글자 가운데는 선 위다. 묶음은 가운데에서 가까운 것부터다 — 가장 긴 구간은 가운데에서 NAME_STEP씩 진행 방향(from→to)
    앞쪽·뒤쪽으로 옮긴 두 자리가 한 묶음, 그다음 구간도 길이 차례로 그 가운데(한 자리)부터 같게 낸다. 구간마다 낸 자리의 글자는 그
    구간을 벗어나지 않는다(_steps). 띠는 그 구간 묶음들의 글자 상자를 NAME_GAP만큼 넓혀 다 덮는 상자다."""
    box = lines_box(0, 0, lines)
    far = _far(box)
    for n, k, steps in _steps(points, box):
        p, q = points[k], points[k + 1]
        rings = ([[_along(p, q)]] if n else []) + [[_along(p, q, d), _along(p, q, -d)] for d in steps]
        if rings:
            yield k, grow(span((p, q)), far + NAME_GAP), rings


def multiplicity_spots(end: Point, toward: Point) -> list[Point]:
    """다중도 글자 가운데의 후보: 선 끝 end에서 선 방향(end→toward)을 MULT_ANGLES만큼 양쪽으로 돌린 쪽으로
    MULT_DISTANCES만큼 떨어진 자리. 선 끝에 가까운 것부터 늘어놓는다."""
    th = math.atan2(toward[1] - end[1], toward[0] - end[0])
    return [(end[0] + d * math.cos(th - turn), end[1] + d * math.sin(th - turn))
            for d in MULT_DISTANCES for a in MULT_ANGLES for turn in (a, -a)]


@dataclass(frozen=True)
class Obstacles:
    """선 글자가 피할 것: solids는 겹치면 안 되는 테두리(요소, 이름 칸), frames는 닿으면 안 되는 선(끝을 품은 요소의 테두리 선).
    solid_keys·frame_keys는 하나하나가 어느 요소의 것인지다 — 걸린 것을 요소마다 셀 때 쓰고, 비면 하나하나 다른 요소로 친다."""

    solids: tuple[Border, ...]
    frames: tuple[Segment, ...] = ()
    solid_keys: tuple[str, ...] = ()
    frame_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for things, keys in ((self.solids, self.solid_keys), (self.frames, self.frame_keys)):
            if keys and len(keys) != len(things):
                raise ValueError("요소 열쇠는 피할 것마다 하나씩이거나 없어야 한다")

    @cached_property
    def keyed(self) -> tuple[list[tuple[Border, object]], list[tuple[Segment, object]]]:
        """(피할 것, 요소 열쇠)·(테두리 선, 요소 열쇠) 짝. 열쇠가 없으면 하나하나 다른 열쇠다."""
        return (list(zip(self.solids, self.solid_keys or [("solid", i) for i in range(len(self.solids))])),
                list(zip(self.frames, self.frame_keys or [("frame", i) for i in range(len(self.frames))])))


def obstacles(boxes: tuple[PlacedBox, ...], holders: frozenset[str] = frozenset()) -> Obstacles:
    """관계 하나의 선 글자가 피할 것. 끝을 품은 요소(holders)는 안에 글자를 둘 수 있지만 테두리 선과 이름 칸은 피한다. 그 밖의
    요소는 통째로 피한다(몸통 밖 이름 칸도)."""
    solids: list[Border] = []
    frames: list[Segment] = []
    solid_keys: list[str] = []
    frame_keys: list[str] = []
    for p in boxes:
        if p.key in holders:
            mine = [RectBorder(z.rect) for z in p.zones]
            frames += p.frame
            frame_keys += [p.key] * len(p.frame)
        else:
            mine = [p.border] + [RectBorder(z.rect) for z in p.zones if z.outside]
        solids += mine
        solid_keys += [p.key] * len(mine)
    return Obstacles(tuple(solids), tuple(frames), tuple(solid_keys), tuple(frame_keys))


_Seg = tuple[Point, Point, T.Box, object, Optional[int]]  # _Spots.segments: 선분, 그 상자, 그린 관계, 그 관계 선의 구간 번호
_Pool = tuple[list[tuple[Border, object]], list[tuple[Segment, object]], list[_Seg],
              list[T.Box]]  # _Spots._pool: (피할 것, 요소 열쇠)·(테두리 선, 요소 열쇠)·선분·앞서 놓은 글자


class _Best(NamedTuple):
    """후보 가운데 가장 나은 것. score는 견주는 점수(피할 것을 비켰다, 빈 자리다, 피할 것에서 떨어진 거리 — MULT_ENOUGH까지)이고,
    faults는 걸린 것의 수다(_Spots)."""

    score: tuple[bool, bool, float]
    spot: Point
    box: T.Box
    faults: int

    @property
    def off(self) -> bool:
        """피할 것을 비켰다."""
        return self.score[0]

    @property
    def free(self) -> bool:
        """빈 자리다(피할 것·선·앞서 놓은 글자에 다 안 닿는다)."""
        return self.score[0] and self.score[1]

    @property
    def roomy(self) -> bool:
        """여유 있는 빈 자리다 — 흰 바탕이 피할 것과 NAME_GAP - LABEL_CLEAR 이상 떨어져, 변을 마주 보는 피할 것과 글자 상자 사이가
        NAME_GAP 이상이다(모서리 쪽에서는 그보다 조금 더 떨어져야 한다)."""
        return self.free and self.score[2] >= NAME_GAP - LABEL_CLEAR


def _places(boxes: Iterable[T.Box]) -> int:
    """자리 수 — PLACE_EPS 안으로 같은 상자는 한 자리로 친다(검사가 같은 자리를 지나는 선들을 한 항목으로 묶는 것과 같다)."""
    seen: list[T.Box] = []
    for b in boxes:
        if not any(all(abs(u - v) <= PLACE_EPS for u, v in zip(b, s)) for s in seen):
            seen.append(b)
    return len(seen)


class _Spots:
    """선 글자의 자리를 고른다. 글자의 흰 바탕(글자 상자를 LABEL_CLEAR만큼 넓힌 것)이 피할 것(Obstacles)에 겹치지 않는 자리,
    그 가운데 관계선과 선 끝 모양(화살촉·삼각형·마름모)과 앞서 놓은 선 글자에 닿지 않는 자리, 그 가운데 피할 것에서 먼
    (MULT_ENOUGH까지) 자리가 낫고, 같으면 후보 목록의 앞쪽이다. 놓은 글자마다 걸린 것의 수도 적어 둔다(misses) — 검사가 알리는
    단위대로, 피할 것은 요소마다, 선은 글자를 지나는 자리마다(같은 자리를 지나는 관계들은 하나), 앞서 놓은 글자는 하나하나 센다.

    이름을 그 관계의 선 위에 얹을 때(pick_on_line)는 얹은 구간을 빼고 보고, 다른 관계의 선분·선 끝 모양과는 글자 상자를
    NAME_GAP만큼 넓혀 본다 — 선 옆 이름이 그 관계의 선과 두는 만큼 얹은 이름도 다른 선과 떨어져, 엇갈리는 곳에서도 어느 선의
    이름인지 분명하다. 걸린 것의 수는 검사와 같이 LABEL_CLEAR로 세고, 얹은 구간은 세지 않는다.

    segments는 그린 선분(관계선과 선 끝 모양 테두리), owners는 선분마다 그린 관계, paths는 선분마다 그 관계 선의 구간 번호다(선
    끝 모양은 None). roomy면 선을 따라 옮기는 이름을 여유 있는 빈 자리에 먼저 둔다(_slid)."""

    def __init__(self, segments: list[Segment], owners: Optional[list[str]] = None,
                 paths: Optional[list[Optional[int]]] = None, roomy: bool = True):
        self.segments: list[_Seg] = [(p, q, span((p, q)), owners[i] if owners else i, paths[i] if paths else None)
                                     for i, (p, q) in enumerate(segments)]
        self.labels: list[T.Box] = []
        self.marks: list[tuple[int, int]] = []  # 글자마다 (걸린 것의 수, 피할 것에 걸렸다)
        self.roomy = roomy
        self.passed = False  # 여유 있는 빈 자리를 고르느라 앞선 빈 자리를 지나친 적이 있다

    def _slid(self, tries: Iterable[tuple[_Best, Optional[int]]]) -> Optional[tuple[_Best, Optional[int]]]:
        """선을 따라 본 묶음들(on_spots·slide_spots가 낸 차례 — 가장 긴 구간의 가운데에서 바깥쪽으로, 그다음 구간들)마다의 (가장 나은
        자리, 얹은 구간 번호) 가운데 옮겨 갈 것. roomy면 여유 있는 빈 자리(_Best.roomy)가 처음 나온 것, 그런 자리가 없으면 빈 자리가
        처음 나온 것이다 — 요소에 막혀 옮긴 글자가 그 요소를 막 비킨 자리에 붙지 않게 한다. roomy가 아니면 빈 자리가 처음 나온 것이다."""
        first = None
        for best, extra in tries:
            if best.roomy or (best.free and not self.roomy):
                self.passed |= first is not None
                return best, extra
            if first is None and best.free:
                first = best, extra
        return first

    def _keep(self, best: _Best) -> Point:
        self.labels.append(best.box)
        self.marks.append((best.faults, int(not best.off)))
        return best.spot

    def cut(self, start: int) -> tuple[list[T.Box], list[tuple[int, int]]]:
        """start번째부터 놓은 글자를 들어내 돌려준다(put으로 도로 놓는다)."""
        tail = self.labels[start:], self.marks[start:]
        del self.labels[start:], self.marks[start:]
        return tail

    def put(self, tail: tuple[list[T.Box], list[tuple[int, int]]]) -> None:
        self.labels += tail[0]
        self.marks += tail[1]

    def misses(self, start: int) -> tuple[int, int]:
        """start번째부터 놓은 글자들이 (걸린 것을 모두 센 수, 피할 것에 걸린 글자 수). 작을수록 낫고, 앞의 수가 검사 불합격 수에
        가깝다."""
        return sum(f for f, _ in self.marks[start:]), sum(b for _, b in self.marks[start:])

    def _pool(self, region: T.Box, avoid: Obstacles, within: Optional[_Pool] = None) -> _Pool:
        """흰 바탕이 region 안인 후보들이 닿을 수 있는 피할 것·선·앞서 놓은 글자(within이 있으면 그 가운데서 거른다). 피할 것은
        MULT_ENOUGH 밖이면 점수가 같아 거리를 잴 필요가 없다."""
        if within is None:
            within = (*avoid.keyed, self.segments, self.labels)
        solids, frames, segments, labels = within
        reach = grow(region, MULT_ENOUGH)
        return ([b for b in solids if meets(b[0].bounds, reach)], [f for f in frames if meets(span(f[0]), reach)],
                [s for s in segments if meets(s[2], region)], [x for x in labels if meets(x, region)])

    def _best(self, lines: tuple[str, ...], candidates: list[Point], avoid: Obstacles,
              pool: Optional[_Pool] = None, on: Optional[tuple[object, int]] = None) -> _Best:
        """후보 가운데 가장 나은 것. pool은 이 후보들을 덮는 더 넓은 곳에서 미리 거른 것이다(_pool). on은 이름을 선 위에 얹을 때
        그 관계와 얹은 구간 번호다 — 그 구간은 빼고, 다른 관계의 선분과는 NAME_GAP으로 본다."""
        boxes = [lines_box(x, y, lines) for x, y in candidates]
        wides = [grow(b, LABEL_CLEAR) for b in boxes]
        region = span(pt for b in boxes for pt in (b[:2], b[2:]))
        near_solids, near_frames, near_segments, near_labels = self._pool(
            grow(region, LABEL_CLEAR if on is None else NAME_GAP), avoid, pool)
        if on is not None:
            near_segments = [s for s in near_segments if (s[3], s[4]) != on]
        others = [on is not None and s[3] != on[0] for s in near_segments]  # 선 위에 얹은 이름이 NAME_GAP으로 볼 선분
        best: Optional[_Best] = None
        for p, box, wide in zip(candidates, boxes, wides):
            solid_gaps = [b.gap(wide) for b, _ in near_solids]
            frame_gaps = [segment_gap(wide, s) for s, _ in near_frames]
            room = min(solid_gaps + frame_gaps, default=MULT_ENOUGH)
            apart = grow(box, NAME_GAP) if on is not None else wide
            clear = (not any(hits(a, b, apart if other else wide) for (a, b, *_), other in zip(near_segments, others))
                     and all(gap(wide, x) >= 0 for x in near_labels))
            score = (room >= 0, clear, min(room, MULT_ENOUGH))
            if best is None or score > best.score:  # 걸린 것은 고른 후보만 센다
                hit = ({k for (_, k), g in zip(near_solids, solid_gaps) if g < 0}
                       | {k for (_, k), g in zip(near_frames, frame_gaps) if g < 0})
                parts: dict[object, list[Point]] = {}  # 그린 관계마다 글자의 흰 바탕 안에 든 선의 점들
                for a, b, _, owner, _ in near_segments:
                    if (c := clip(a, b, wide)) is not None:
                        parts.setdefault(owner, []).extend(c)
                on_labels = sum(gap(wide, x) < 0 for x in near_labels)
                best = _Best(score, p, box, len(hit) + _places(span(pts) for pts in parts.values()) + on_labels)
        assert best is not None
        return best

    def pick(self, lines: tuple[str, ...], candidates: list[Point], avoid: Obstacles) -> Point:
        return self._keep(self._best(lines, candidates, avoid))

    def pick_name(self, lines: tuple[str, ...], points: tuple[Point, ...], avoid: Obstacles,
                  slide: bool = True, wide: bool = True) -> tuple[Point, bool, bool]:
        """이름 글자 자리와, 선을 따라 옮겼는지와, 좁은 조건이라면 옮기지 않았을 이름인지. 가운데 후보 둘이 다 빈 자리가 아니면(wide가
        아니면 둘 다 피할 것에 걸리면 — 좁은 조건) slide일 때 선을 따라 더 본 자리(slide_spots)를 구간마다 묶음 차례로 보아 _slid가
        고른 묶음(roomy면 여유 있는 빈 자리가 처음 나온 묶음, 없으면 빈 자리가 처음 나온 묶음)의 가장 나은 자리로 옮기고, 빈 자리가
        없으면 가운데 후보에 둔다. 피할 것만 비키고 선에 닿는 자리로는 옮기지 않는다 — 선 여러 개에 닿아 불합격이 늘 수 있다."""
        best = self._best(lines, name_spots(points, lines), avoid)
        if slide and not (best.free if wide else best.off):
            def tries() -> Iterator[tuple[_Best, Optional[int]]]:
                for band, rings in slide_spots(points, lines):
                    pool = self._pool(band, avoid)  # 구간마다 한 번만 거른다
                    for ring in rings:
                        yield self._best(lines, ring, avoid, pool), None

            if (got := self._slid(tries())) is not None:
                return self._keep(got[0]), True, best.off
        return self._keep(best), False, False

    def pick_on_line(self, lines: tuple[str, ...], points: tuple[Point, ...], avoid: Obstacles, owner: object,
                     slide: bool = True, show: tuple[float, float] = (0.0, 0.0)) -> Optional[tuple[Point, int, bool]]:
        """이름 글자를 그 관계(owner)의 선 위에 얹을 자리와, 얹은 구간 번호와, 선을 따라 옮겼는지. 선 위 가운데 자리(가장 긴 구간의
        가운데)가 빈 자리가 아니면 slide일 때 선을 따라 더 본 자리(on_spots)를 구간마다 묶음 차례로 보아 _slid가 고른 묶음(roomy면
        여유 있는 빈 자리가 처음 나온 묶음, 없으면 빈 자리가 처음 나온 묶음)의 가장 나은 자리로 옮기고, 빈 자리가 끝내 없으면 놓지 않고 None을
        돌려준다(그 이름은 선 옆에 놓는다). slide가 아니면 빈 자리가 아니어도 선 위 가운데 자리에 둔다 — 다만 글자 상자를
        LABEL_CLEAR만큼 넓힌 것을 구간 방향으로 비춘 폭이 가장 긴 구간 안에 들지 않으면(_room) None이다. 구간을 넘친 글자의 흰
        바탕(BG_MARGIN)이 구간 끝의 꺾인 곳을 지울 수 있어서다.

        slide일 때는 들지 않아도 가운데를 그대로 본다. 빈 자리일 때만 쓰니 흰 바탕이 꺾인 곳에 닿지 않고(빈 자리면 구간 끝의
        요소·이웃 구간·선 끝 모양에서 LABEL_CLEAR 넘게 떨어져 있다), 비스듬한 구간에서는 비춘 폭이 글자가 선 위에서 실제로 차지하는
        길이보다 길어 들지 않는다고 쳐도 빈 자리일 수 있다.

        show는 선의 처음(from)·끝(to)에서 흰 바탕까지 보여야 할 선의 길이다(_shows). 첫 구간과 마지막 구간에서는 흰 바탕 앞뒤로 그
        길이만큼 선이 보이는 자리만 보고, 선 위 가운데 자리가 그렇지 않으면 그 자리가 없는 것으로 친다."""
        last = len(points) - 2

        def shown(j: int, spot: Point) -> bool:
            need = (show[0] if j == 0 else 0.0, show[1] if j == last else 0.0)
            if need == (0.0, 0.0):
                return True
            c = clip(points[j], points[j + 1], grow(lines_box(*spot, lines), BG_MARGIN))
            return c is None or (math.dist(points[j], c[0]) >= need[0] and math.dist(c[1], points[j + 1]) >= need[1])

        k = _segments_by_length(points)[0]
        p, q = points[k], points[k + 1]
        middle = _along(p, q)
        if shown(k, middle) and (slide or _room(p, q, grow(lines_box(0, 0, lines), LABEL_CLEAR)) >= 0):
            best = self._best(lines, [middle], avoid, on=(owner, k))
            if best.free or not slide:
                return self._keep(best), k, False
        elif not slide:
            return None

        def tries() -> Iterator[tuple[_Best, Optional[int]]]:
            for j, band, rings in on_spots(points, lines):
                pool = self._pool(band, avoid)  # 구간마다 한 번만 거른다
                for ring in rings:
                    if ring := [spot for spot in ring if shown(j, spot)]:
                        yield self._best(lines, ring, avoid, pool, on=(owner, j)), j

        if (got := self._slid(tries())) is None:
            return None
        found, j = got
        assert j is not None
        return self._keep(found), j, True


def _shows(heads: tuple[Union[Line, Polygon], ...], marks: tuple[HeadMark, ...], points: tuple[Point, ...]
           ) -> tuple[float, float]:
    """선의 처음·끝에서 선 위에 얹은 이름의 흰 바탕까지 보여야 할 선의 길이: LINE_SHOW에 그 끝의 선 끝 모양이 선을 따라 차지하는
    길이(모양의 점을 끝 구간 방향으로 비춘 가장 먼 거리 — 소켓 반원처럼 선 밖으로 휘는 모양은 0)를 더한다."""
    out = []
    for tip, toward in ((points[0], points[1]), (points[-1], points[-2])):
        ln = math.dist(tip, toward)
        ux, uy = (toward[0] - tip[0]) / ln, (toward[1] - tip[1]) / ln
        reach = max((max((x - tip[0]) * ux + (y - tip[1]) * uy for x, y in h.points) for h, m in zip(heads, marks)
                     if m.tip == tip), default=0.0)
        out.append(LINE_SHOW + max(reach, 0.0))
    return out[0], out[1]


def _end_shape(r: Relation, t: RelationType, key: str) -> Optional[EndShape]:
    """선 처음(from)이나 끝(to)에 그리는 모양. 고정 모양이 있는 종류는 그 쪽 방향(navigable)을 읽기에서 받지 않으므로 둘 중
    하나다."""
    fixed = t.start if key == "from" else t.end
    return fixed or (ARROW_HEAD if t.navigable and r.navigable in (key, "both") else None)


def _route(r: Relation, a: PlacedBox, b: PlacedBox, path: str, t: RelationType, w: Words,
           aim: Optional[Point] = None) -> tuple[Optional[tuple[Point, ...]], list[str], Point]:
    """관계선의 점들(선 끝은 요소가 향하게 한 점(anchor — 보통 테두리 가운데. 도착 요소에서 종류마다 정한 점(aim, _aim이 고른다)을
    향하는 선은 그 점)에서 첫·마지막 꺾는 점으로, 꺾는 점이 없으면 다른 요소의 그 점으로 가는 선이 테두리와 만나는 곳)과, 그렇게 그을
    수 없으면 그 까닭들, 그리고 출발 요소에서 선을 낸 점(_from_at — from 쪽 끝 모양도 이 점을 받는다). aim을 향하는 선은 끝 꺾는
    점들의 x를 aim의 x로 맞춘다(_snap)."""
    cb = aim or b.anchor
    assert cb is not None
    via = r.via if aim is None else _snap(r.via, aim)
    ca = _from_at(a, via, aim)

    def given(j: int, q: Point) -> str:
        """입력의 꺾는 점 j. 종류 점의 x로 맞춘 점(q)이 다르면 맞춘 자리도 적는다 — 테두리와 견준 것은 맞춘 자리다."""
        moved = (f"({t.label} 향하는 점의 x에 맞추면 ({fmt_num(q[0])}, {fmt_num(q[1])}))"
                 if tuple(r.via[j]) != tuple(q) else "")
        return f"{r.via[j]}{moved}"

    if via:
        start, end = a.border.exit(ca, via[0]), b.border.exit(cb, via[-1])
        problems = [f"{_at(_at(path, 'via'), j)}: 꺾는 점 {given(j, q)}이 {key} {w.noun} {_show(p_.key)}"
                    f"({fmt_rect(p_.border.bounds)}) 안이나 {w.edge} 위에 있다 — {w.noun} 밖으로 옮긴다"
                    for p, p_, j, q, key in ((start, a, 0, via[0], "from"), (end, b, len(r.via) - 1, via[-1], "to"))
                    if p is None]
        if problems:
            return None, problems, ca
    else:
        start, end = a.border.exit(ca, cb), b.border.exit(cb, ca)
        if start is None or end is None or (end[0] - start[0]) * (cb[0] - ca[0]) + (end[1] - start[1]) * (cb[1] - ca[1]) <= 0:
            return None, [f"{path}: {w.noun} {_show(r.source)}와 {_show(r.target)}가 겹치거나 맞닿아 둘 사이에 선을 그을 자리가 "
                          f"없다 — 떼어 놓거나 {w.noun} 밖을 도는 꺾는 점(via)을 준다"], ca
    assert start is not None and end is not None
    points = (start, *via, end)
    if start == end:
        return None, [f"{path}: 선의 두 끝이 같은 점 {start}이다 — 첫·마지막 꺾는 점을 {w.noun}의 다른 쪽으로 옮긴다"], ca
    problems = []
    # 선 끝은 테두리 위에 있으므로, 테두리에서 EDGE_SLACK 안쪽으로 줄인 것을 지나면 선이 끝 요소 안으로 들어간 것이다.
    # 요소가 선 위에 그려지면 그 부분은 가려지므로 선이 엉뚱한 곳에서 시작하는 것처럼 보인다.
    for key, p_ in (("from", a),) + ((("to", b),) if r.target != r.source else ()):
        inner = p_.border.grown(-EDGE_SLACK)
        if any(inner.hits(p, q) for p, q in zip(points, points[1:])):
            problems.append(f"{path}: 선이 {key} {w.noun} {_show(p_.key)}({fmt_rect(p_.border.bounds)}) 안을 지난다 — 꺾는 점을 그 "
                            f"{w.noun} 밖으로 돌린다")
    lengths = [math.dist(p, q) for p, q in zip(points, points[1:])]
    shapes = (_end_shape(r, t, "from"), _end_shape(r, t, "to"))  # 끝 모양 길이와 띄운 거리
    gaps = tuple(s.gap if s else 0.0 for s in shapes)
    head, tail = ((s.length if s else 0) + g for s, g in zip(shapes, gaps))

    def short(length: float, needs: tuple[float, ...], gap: bool) -> Optional[str]:
        """구간이 모자라면 그 글. needs는 그 구간이 품어야 할 끝마다의 길이(끝 모양 길이와 띄운 거리)다. 선 끝을 띄우는 끝이 있으면
        그 길이를 다 쓰고도 길이가 남아야 한다 — 같으면 당긴 선 끝이 앞 점에 겹쳐 길이 0인 선이 된다."""
        need, shown = sum(needs), "+".join(fmt_num(n) for n in needs)
        if gap:
            if len(needs) == 2:  # 끝마다 더한 수가 무엇인지 헷갈리지 않게 쪽을 붙인다
                shown = f"from 쪽 {fmt_num(needs[0])}, to 쪽 {fmt_num(needs[1])}"
            return f"끝 모양 길이와 띄운 거리를 더한 길이({shown})보다 길지 않다" if length <= need else None
        return f"끝 모양 길이({shown})보다 짧다" if length < need else None

    if len(lengths) == 1:
        if (why := short(lengths[0], (head, tail), any(gaps))) is not None:
            problems.append(f"{path}: 선 길이 {fmt_num(lengths[0])}가 양 {why} — {w.noun}를 더 떼어 놓는다")
    else:
        for length, need, gap, key, which, shape in ((lengths[0], head, gaps[0], "from", "첫", shapes[0]),
                                                     (lengths[-1], tail, gaps[1], "to", "마지막", shapes[1])):
            if (why := short(length, (need,), bool(gap))) is not None:
                # 화살촉은 끝 모양 길이만큼만 떼면 꺾은 앞 구간이 갈래 끝에 붙어 검사에 걸리므로 그만큼 떼라고 한다
                far = f"{ARROW_BEND}px 이상" if shape is ARROW_HEAD else "더"
                problems.append(f"{path}: {key} 쪽 끝 구간 길이 {fmt_num(length)}가 {why} — {which} 꺾는 점을 {w.noun}에서 {far} "
                                "떼어 놓는다")
    if sum(lengths) > MAX_LINE:
        problems.append(f"{path}: 선 길이 {fmt_num(sum(lengths))}가 {MAX_LINE}을 넘는다 — {w.noun}를 가까이 모은다")
    return (None if problems else _shorten(points, *gaps)), problems, ca


def _snap(via: tuple[Point, ...], aim: Point) -> tuple[Point, ...]:
    """종류마다 정한 점(aim)으로 올라가는 끝 세로 줄을 그 점의 x로 맞춘다 — x가 AIM_EPS 안인 꺾는 점은 몇 px 셈 실수까지 그 점을
    뜻한 것으로 보고, 맞춰야 세로 줄이 곧게 서고 같은 종류의 선들이 삼각형 하나를 함께 쓴다. 세로 줄은 마지막 꺾는 점에서 거슬러
    가며 그 점에서 멀어지는 쪽으로만 이어진 점들이다 — 가로로 이어지거나 위아래가 뒤집히면(지그재그) 멈춰, 받은 선이 되짚어 가는
    선으로 바뀌지 않게 한다."""
    pts, i = list(via), len(via) - 1
    away = via[-1][1] - aim[1] if via else 0.0  # 마지막 꺾는 점이 그 점에서 떨어진 쪽(아래면 양수)
    while i >= 0 and abs(pts[i][0] - aim[0]) <= AIM_EPS and (i == len(via) - 1 or (via[i][1] - via[i + 1][1]) * away > 0):
        pts[i], i = (aim[0], pts[i][1]), i - 1
    return tuple(p for j, p in enumerate(pts) if j == 0 or p != pts[j - 1])


def _from_at(a: PlacedBox, via: tuple[Point, ...], aim: Optional[Point]) -> Point:
    """출발 요소 a에서 선이 나가는 점. 종류 점(aim)을 따르는 선이 꺾는 점 없이, 또는 첫 꺾는 점이 그 x에 맞춰져(_snap) 올라가고 a의
    anchor가 그 x에서 AIM_EPS 안이면 그 x의 점이다 — 자식에서부터 곧게 올라가 끝 삼각형이 그 점에 정확히 앉아 같은 종류 선들과
    하나로 모인다. 그 밖이면 anchor다(첫 꺾는 점만 그 x이고 a가 멀면 선을 옮기지 않는다)."""
    ca = a.anchor
    assert ca is not None
    if aim is not None and (not via or via[0][0] == aim[0]):
        straight = (aim[0], ca[1])
        if abs(ca[0] - aim[0]) <= AIM_EPS and a.border.holds(straight):
            return straight
    return ca


def _shorten(points: tuple[Point, ...], start_gap: float, end_gap: float) -> tuple[Point, ...]:
    """선 처음·끝을 다음(앞) 점 쪽으로 gap만큼 당긴다 — 선 끝을 끝 요소 테두리에서 띄우는 끝 모양(EndShape.gap). 끝 구간이 끝 모양
    길이와 띄운 거리보다 긴지는 _route가 먼저 본다."""
    pts = list(points)
    for i, j, g in ((0, 1, start_gap), (-1, -2, end_gap)):
        if g:
            (x, y), (nx, ny) = pts[i], pts[j]
            k = g / math.dist(pts[i], pts[j])
            pts[i] = (x + (nx - x) * k, y + (ny - y) * k)
    return tuple(pts)


def _outside_name(e: Element, w: float, h: float, gap: float) -> tuple[float, float, Point, T.Box]:
    """모양 밖 이름이 있는 요소의 (자리 폭, 자리 높이, 자리 왼쪽 위에서 모양 왼쪽 위까지, 자리 왼쪽 위 기준 이름 칸). gap은 모양과
    이름 사이(Shape.name_gap)다."""
    lines = e.name
    tw = math.ceil(max(T.text_width(s) for s in lines))
    th = LABEL_LINE * len(lines)
    if e.name_side in ("bottom", "top"):
        width, height = max(w, tw), h + gap + th
        sx, nx = (width - w) / 2, (width - tw) / 2
        sy, ny = (0, h + gap) if e.name_side == "bottom" else (th + gap, 0)
    else:
        width, height = w + gap + tw, max(h, th)
        sy, ny = (height - h) / 2, (height - th) / 2
        sx, nx = (0, w + gap) if e.name_side == "right" else (tw + gap, 0)
    return width, height, (sx, sy), (nx, ny, nx + tw, ny + th)


def _place(spec: Spec, diagram: Diagram, lines_of: Mapping[str, tuple[str, ...]]) -> tuple[PlacedBox, ...]:
    """요소 크기와 자리. 안의 요소부터 재서 바깥 요소가 안의 요소를 NEST_PAD 여백을 두고 덮도록 오른쪽·아래로 늘린다. 요소마다
    이름 칸이 들어갈 크기는 그 요소의 모양(Shape.size)이 정한다."""
    children: dict[str, list[Element]] = {}
    for e in diagram.boxes:
        if e.parent is not None:
            children.setdefault(e.parent, []).append(e)
    done: dict[str, PlacedBox] = {}
    for e in sorted(diagram.boxes, key=lambda e: len(lines_of[e.key]), reverse=True):
        shape = spec.shapes[e.kind]
        w, h = shape.size(e)
        offset: Point = (0.0, 0.0)
        zone = None
        if shape.outside_name and e.name:
            sw, sh = w, h
            w, h, offset, zone = _outside_name(e, sw, sh, shape.name_gap)
        insets = shape.insets(e) if shape.holds else (0.0, 0.0, 0.0, 0.0)
        for c in children.get(e.key, []):
            cr = done[c.key].rect
            w = max(w, cr[2] + NEST_PAD + insets[2] - e.left)
            h = max(h, cr[3] + NEST_PAD + insets[3] - e.top)
        if zone is None:  # 모양 밖 이름이 있는 모양은 크기를 받지 않는다(모양과 이름 자리를 위에서 이미 정했다)
            w, h = max(e.min_width, w), max(e.min_height, h)
        rect = (e.left, e.top, e.left + w, e.top + h)
        if zone is not None:
            sx, sy = e.left + offset[0], e.top + offset[1]
            shape_rect = (sx, sy, sx + sw, sy + sh)
            name_rect = (e.left + zone[0], e.top + zone[1], e.left + zone[2], e.top + zone[3])
            cx = (name_rect[0] + name_rect[2]) / 2
            ys = line_ys((name_rect[1] + name_rect[3]) / 2, len(e.name))
            done[e.key] = PlacedBox(e, shape, rect, shape_rect, shape.border(e, shape_rect),
                                    (NameZone(name_rect, True),), None, (), tuple((cx, y) for y in ys),
                                    anchor=shape.anchor(e, shape_rect))
            continue
        inner = None
        frame: tuple[Segment, ...] = ()
        if shape.holds:
            inner = (rect[0] + insets[0], rect[1] + insets[1], rect[2] - insets[2], rect[3] - insets[3])
            frame = tuple(shape.frame(e, rect))
        done[e.key] = PlacedBox(e, shape, rect, rect, shape.border(e, rect), tuple(shape.name_zones(e, rect)), inner, frame,
                                parts=tuple(shape.parts(e, rect)), anchor=shape.anchor(e, rect))
    return tuple(done[e.key] for e in diagram.boxes)


def _flat(p: PlacedBox, x: float, side: int) -> bool:
    """세로 줄 x의 끝 삼각형이 아래 변(side 1)·위 변(-1)의 곧은 부분에 바로 앉는지 — 삼각형 밑변 양 끝 아래가 그 변에 닿는다(변
    끝(모서리)까지 와도 된다)."""
    assert p.anchor is not None
    _, top, _, bottom = p.border.bounds
    edge, reach = (bottom if side > 0 else top), TRIANGLE[1] - SIDE_EPS
    for at in (x - reach, x + reach):
        inside = (at, p.anchor[1])
        end = p.border.exit(inside, (at, edge + side)) if p.border.holds(inside) else None
        if end is None or abs(end[1] - edge) > SIDE_EPS:
            return False
    return True


def trunk_kinds(spec: Spec) -> tuple[str, ...]:
    """공유 줄기를 받는 관계 종류(도구가 받는 차례)."""
    return tuple(k for k, t in spec.relations.items() if t.trunk)


def split_kinds(spec: Spec) -> tuple[str, ...]:
    """종류마다 향하는 점을 나눌 공유 줄기 관계 종류 둘(도구가 받는 차례 — 이 차례로 왼쪽부터 점을 둔다). 공유 줄기 종류를 둘 받고
    둘 다 끝 모양이 삼각형인 도구만 나누고, 그 밖이면 빈 튜플이다 — 셋 이상의 요령은 relations 인자 설명에 쓰지 않았고, 좁은 모양 판정
    (AIM_EDGE·_flat)은 삼각형 크기로 셈한다."""
    kinds = trunk_kinds(spec)
    return kinds if len(kinds) == 2 and all(spec.relations[k].end is TRIANGLE_HEAD for k in kinds) else ()


def _split_aims(spec: Spec, diagram: Diagram, placed: tuple[PlacedBox, ...]) -> tuple[PlacedBox, ...]:
    """같은 부모로 split_kinds의 두 종류가 다 오면 종류마다 향하는 점(PlacedBox.aims)을 정한다. 위·아래 변을 함께 보는 것은 정한
    점을 어느 쪽에서 오는 선이든 쓸 수 있게 하려는 것이다."""
    split = split_kinds(spec)
    if not split:
        return placed
    kinds: dict[str, set[str]] = {}
    for r in diagram.relations:
        if r.kind in split and r.source != r.target:
            kinds.setdefault(r.target, set()).add(r.kind)
    out = []
    for p in placed:
        if kinds.get(p.key) == set(split):
            assert p.anchor is not None
            x, y = p.anchor
            points = tuple((k, (x + d * AIM_SPLIT / 2, y)) for k, d in zip(split, (-1, 1)))
            if all(_flat(p, ax, side) for _, (ax, _) in points for side in (1, -1)):
                p = replace(p, aims=points)
        out.append(p)
    return tuple(out)


def _aim(r: Relation, a: PlacedBox, b: PlacedBox) -> Optional[Point]:
    """도착 요소 b에서 선 r이 향하는 종류마다의 점(PlacedBox.aims). 없으면 None(anchor를 향한다). 마지막 꺾는 점(꺾는 점이 없으면
    출발 요소 a의 점)이 그 점 바로 아래·위인 선만 따라, 이미 그린 선이나 옆 변으로 들어오는 선을 기울이지 않는다."""
    point = b.aim_of(r.kind)
    toward = r.via[-1] if r.via else a.anchor
    if point is None or toward is None or r.source == r.target or abs(toward[0] - point[0]) > AIM_EPS:
        return None
    return point


def kind_aim(label: str, x: str, y: str) -> str:
    """결과 글의 자리 뒤에 덧붙는 종류마다 향하는 점 하나("상속 향하는 점 x, y")."""
    return f"{label} 향하는 점 {x}, {y}"


def layout(diagram: Diagram) -> Layout:
    """요소 크기, 선의 점들, 선 글자 자리를 잡는다. 선을 그을 수 없는 배치면(꺾는 점이 요소 안이다, 두 요소가 겹치거나
    맞닿았다, 끝 구간이 끝 모양보다 짧다 등) 모두 모아 InputError. 선 글자는 관계 순서대로 이름 → from 다중도 → to 다중도
    차례로 놓고, 앞서 놓은 글자를 뒤 글자가 피한다(_labels). 이름은 그 관계의 선 위에 얹는다(선 위 배치) — 선 위에 빈 자리가 없는
    이름과 같은 요소로 돌아오는 고리 선의 이름은 선 옆에 놓는다. 선 위 배치에 걸린 것이 있으면 이름을 모두 선 옆에 놓은 배치(선 옆
    배치, _beside_layout)로도 놓아 보고, 그림 전체의 (걸린 것의 수, 피할 것에 걸린 글자 수)가 선 위 배치 쪽이 더 크면 선 옆 배치를
    쓴다(둘 다 같으면 선 위 배치) — 얹은 이름이 뒤 관계의 글자가 쓸 자리를 차지해 뒤 글자가 밀리면 선 위에 얹어 더 나빠질 수 있다.
    선을 따라 옮기는 이름은 여유 있는 빈 자리에 먼저 두는데(_Spots._slid), 그렇게 놓은 배치에 걸린 것이 있으면 처음 빈 자리로 옮기는
    배치로도 놓아 보고 같은 두 수가 더 작을 때만 그쪽을 쓴다(_label_layout)."""
    spec = diagram.spec
    lines_of = lineage({e.key: e.parent for e in diagram.boxes})  # 품은 사이는 여기서 한 번 재서 검사(Layout)까지 넘긴다
    placed = _split_aims(spec, diagram, _place(spec, diagram, lines_of))
    by_key = {p.key: p for p in placed}
    problems: list[str] = []
    routes = []
    aims = [_aim(r, by_key[r.source], by_key[r.target]) for r in diagram.relations]
    for i, (r, aim) in enumerate(zip(diagram.relations, aims)):
        points, found, origin = _route(r, by_key[r.source], by_key[r.target], _at("relations", i), spec.relations[r.kind],
                                       spec.words, aim)
        problems += found
        routes.append((points, origin))
    if problems:
        raise InputError(problems)
    used = set(by_key)
    bare = []
    for r, (points, origin), aim in zip(diagram.relations, routes, aims):
        owner = base = f"{r.source}->{r.target}"
        n = 2
        while owner in used:
            owner, n = f"{base}#{n}", n + 1
        used.add(owner)
        bare.append(PlacedRelation(r, owner, points, (), origin, aim))
    sketch = Canvas()  # 선 끝 모양을 그림판과 똑같이 얻으려고 선만 한 번 그려 본다
    segments: list[Segment] = []
    owners: list[str] = []
    paths: list[Optional[int]] = []  # 선분마다 그 관계 선의 구간 번호(선 끝 모양은 None)
    shows: dict[str, tuple[float, float]] = {}
    for p in bare:
        drawn = len(sketch.records)
        line, heads, marks = _draw_relation(sketch, p, spec.relations[p.relation.kind], by_key)
        shows[p.owner] = _shows(heads, marks, p.points)
        for rec in sketch.records[drawn:]:
            for j, s in enumerate(outline([rec])):
                segments.append(s)
                owners.append(p.owner)
                paths.append(j if rec is line else None)
    avoids: dict[frozenset[str], Obstacles] = {}  # 끝을 품은 요소들마다 한 번만 만든다
    out, missed, passed = _label_layout(segments, owners, paths, bare, placed, lines_of, avoids, shows, roomy=True)
    # 여유 있는 빈 자리로 더 멀리 옮긴 이름이 뒤 글자가 쓸 자리를 차지해 걸린 것이 늘 수 있다. 앞선 빈 자리를 지나쳐 옮긴 이름이
    # 없으면 처음 빈 자리로 옮겨도 같은 배치다
    if missed != (0, 0) and passed:
        first, first_missed, _ = _label_layout(segments, owners, paths, bare, placed, lines_of, avoids, shows, roomy=False)
        if missed > first_missed:
            out = first
    return Layout(spec, placed, tuple(out), lines_of)


def _label_layout(segments: list[Segment], owners: list[str], paths: list[Optional[int]], bare: list[PlacedRelation],
                  placed: tuple[PlacedBox, ...], lines_of: Mapping[str, tuple[str, ...]],
                  avoids: dict[frozenset[str], Obstacles], shows: Mapping[str, tuple[float, float]], roomy: bool
                  ) -> tuple[list[PlacedRelation], tuple[int, int], bool]:
    """선 위 배치와, 걸린 것이 있으면 선 옆 배치(_beside_layout)로도 놓아 본 가운데 나은 쪽(layout)과 그 그림 전체의 (걸린 것의 수,
    피할 것에 걸린 글자 수), 놓아 본 배치에서 여유 있는 빈 자리를 고르느라 앞선 빈 자리를 지나친 이름이 있었는지. roomy는
    _Spots의 것이다."""
    spots = _Spots(segments, owners, paths, roomy)
    out, widened = _labels(spots, bare, placed, lines_of, avoids, shows, wide=True, on=True)
    missed, passed = spots.misses(0), spots.passed
    # 걸린 것이 없으면 선 옆 배치가 더 나을 수 없다. 선 위에 얹은 이름이 없으면 이 배치가 곧 넓힌 조건의 선 옆 배치라, 넓혀서 옮긴
    # 이름이 없을 때도 선 옆 배치가 같게 나온다
    if missed != (0, 0) and (widened or any(lab.segment is not None for p in out for lab in p.labels)):
        beside, beside_missed, beside_passed = _beside_layout(segments, owners, bare, placed, lines_of, avoids, roomy)
        passed |= beside_passed
        if missed > beside_missed:
            out, missed = beside, beside_missed
    return out, missed, passed


def _beside_layout(segments: list[Segment], owners: list[str], bare: list[PlacedRelation], placed: tuple[PlacedBox, ...],
                   lines_of: Mapping[str, tuple[str, ...]], avoids: dict[frozenset[str], Obstacles], roomy: bool = True
                   ) -> tuple[list[PlacedRelation], tuple[int, int], bool]:
    """이름을 모두 선 옆에 놓은 배치(선 옆 배치)와 그 그림 전체의 (걸린 것의 수, 피할 것에 걸린 글자 수), 놓아 본 배치에서 여유 있는
    빈 자리를 고르느라 앞선 빈 자리를 지나친 이름이 있었는지(roomy는 _Spots의 것). 이름은 가운데 후보 둘이 다 빈 자리가 아니면
    선을 따라 옮기는데, 좁은 조건(둘 다 피할 것에 걸릴 때만 옮긴다)이라면 옮기지 않았을 이름이 남으면 좁은 조건으로도 놓아 보고,
    그림 전체의 두 수가 더 작은 쪽을 쓴다(둘 다 같으면 넓힌 쪽) — 옮긴 이름이 뒤 관계의 글자가 쓸 자리를 차지해 뒤 글자가 밀리면
    넓혀서 더 나빠질 수 있다."""
    spots = _Spots(segments, owners, roomy=roomy)
    out, widened = _labels(spots, bare, placed, lines_of, avoids, {}, wide=True, on=False)
    if widened and spots.misses(0) != (0, 0):  # 걸린 것이 없으면 좁은 조건이 더 나을 수 없다
        narrow = _Spots(segments, owners, roomy=roomy)
        kept, _ = _labels(narrow, bare, placed, lines_of, avoids, {}, wide=False, on=False)
        passed = spots.passed or narrow.passed
        if spots.misses(0) > narrow.misses(0):
            return kept, narrow.misses(0), passed
        return out, spots.misses(0), passed
    return out, spots.misses(0), spots.passed


def _labels(spots: _Spots, bare: list[PlacedRelation], placed: tuple[PlacedBox, ...], lines_of: Mapping[str, tuple[str, ...]],
            avoids: dict[frozenset[str], Obstacles], shows: Mapping[str, tuple[float, float]], wide: bool, on: bool
            ) -> tuple[list[PlacedRelation], bool]:
    """관계마다 선 글자를 놓은 관계들과, 좁은 조건이라면 옮기지 않았을 이름이 남았는지(pick_name의 wide). 남지 않았으면 좁은 조건으로
    놓은 것과 같다 — 그런 이름이 없는 관계는 앞 글자가 같으면 같게 놓이므로. on이면 이름을 선 위에 얹는다(_relation_labels —
    shows는 관계마다 선의 처음·끝에서 흰 바탕까지 보여야 할 선의 길이, _shows).
    avoids는 끝을 품은 요소들마다의 피할 것을 모아 둔다."""
    out = []
    widened = False
    for p in bare:
        r, points = p.relation, p.points
        held = holders(lines_of, r)
        if held not in avoids:
            avoids[held] = obstacles(placed, held)
        avoid = avoids[held]
        start = len(spots.labels)
        show = shows.get(p.owner, (0.0, 0.0))
        labels, moved, wider = _relation_labels(spots, r, p.owner, points, avoid, show, slide=True, wide=wide, on=on)
        if moved and (missed := spots.misses(start)) != (0, 0):
            # 옮긴 이름(빈 자리다) 때문에 같은 관계의 다중도가 빈 자리를 못 찾았을 수 있다. 이름을 가운데(선 위에 얹은 이름이면 선 위
            # 가운데 자리 — 글자가 가장 긴 구간에 들지 않아 그 자리가 없으면 선 옆 가운데 후보, 선 옆 이름이면 가운데 후보)에 둔 것과
            # 견주어 걸린 것이 더 적을 때(같으면 피할 것에 걸린 글자가 더 적을 때)만 옮긴 쪽을 쓰고, 둘 다 같으면 가운데에 둔다
            slid, tail = labels, spots.cut(start)
            labels, _, _ = _relation_labels(spots, r, p.owner, points, avoid, show, slide=False, wide=wide,
                                            on=slid[0].segment is not None)
            if spots.misses(start) > missed:
                spots.cut(start)
                spots.put(tail)
                labels = slid
            else:
                wider = False
        widened |= wider
        out.append(replace(p, labels=tuple(labels)))
    return out, widened


def _relation_labels(spots: _Spots, r: Relation, owner: str, points: tuple[Point, ...], avoid: Obstacles,
                     show: tuple[float, float], slide: bool, wide: bool, on: bool) -> tuple[list[Label], bool, bool]:
    """관계 하나의 선 글자를 이름 → from 다중도 → to 다중도 차례로 놓는다. 이름을 선을 따라 옮겼는지와, 좁은 조건이라면 옮기지 않았을
    이름인지도 돌려준다(pick_name). on이면 이름을 그 관계의 선 위에 얹고(pick_on_line), 얹을 빈 자리가 없으면 선 옆에 놓는다. 같은
    요소로 돌아오는 고리 선의 이름은 늘 선 옆에 놓는다 — 고리는 짧은 구간 셋 이상이라 얹으면 고리 모양을 가린다."""
    labels = []
    moved = wider = False
    if r.label_lines:
        lines = r.label_lines
        got = spots.pick_on_line(lines, points, avoid, owner, slide, show) if on and r.source != r.target else None
        if got is not None:
            (x, y), k, moved = got
            labels.append(Label("name", lines, x, y, k))
        else:
            (x, y), moved, wider = spots.pick_name(lines, points, avoid, slide, wide)
            labels.append(Label("name", lines, x, y))
    for role, text, tip, toward in (("from_multiplicity", r.source_multiplicity, points[0], points[1]),
                                    ("to_multiplicity", r.target_multiplicity, points[-1], points[-2])):
        if text:
            labels.append(Label(role, (text,), *spots.pick((text,), multiplicity_spots(tip, toward), avoid)))
    return labels, moved, wider


# ---------------------------------------------------------------- 그리기


def _draw_relation(c: Canvas, r: PlacedRelation, t: RelationType, by_key: Mapping[str, PlacedBox]
                   ) -> tuple[Line, tuple[Union[Line, Polygon], ...], tuple[HeadMark, ...]]:
    """선과 선 끝 모양(from 쪽, to 쪽 차례)을 그리고 그 기록과 끝 모양마다의 이름·끝 점을 돌려준다. 끝 모양은 끝 요소가 향하게 한
    점(_route가 선 끝을 낸 점)도 받는다."""
    pts, o, rel = r.points, r.owner, r.relation
    first, last = r.start, r.aim or by_key[rel.target].anchor
    assert last is not None
    line = c.line(pts, dash=t.dash, owner=o)
    ends = [(s, tip, frm, at) for key, tip, frm, at in (("from", pts[0], pts[1], first), ("to", pts[-1], pts[-2], last))
            if (s := _end_shape(rel, t, key)) is not None]  # (모양, 끝 점, 그 앞 점, 끝 요소의 점)
    heads = tuple(s.draw(c, tip, frm, at, o) for s, tip, frm, at in ends)
    return line, heads, tuple(HeadMark(s.name, tip) for s, tip, _, _ in ends)


def _draw_box(c: Canvas, p: PlacedBox) -> None:
    p.shape.draw(c, p)
    for s, (x, y) in zip(p.box.name, p.name_at):
        c.text(x, y, s, anchor="mm", owner=p.key)


def _draw_label(c: Canvas, lab: Label, owner: str) -> tuple[Text, ...]:
    """선 글자를 흰 바탕 위에 줄마다 쓴다. 선 옆 글자는 줄마다 흰 바탕을 깔고, 선 위에 얹은 이름은 글자 덩어리 전체(모든 줄의 줄
    상자)를 덮는 흰 바탕 하나를 둘레 BG_MARGIN만큼 넓혀 깐다 — 줄마다 깔면 두 줄 이름을 얹은 선이 줄 사이 틈으로 보이고, 잉크만
    덮으면 잉크가 줄 가운데를 지나지 않는 이름("..." 등)에서 선이 끊기지 않는다."""
    ys = line_ys(lab.y, len(lab.lines))
    if lab.segment is None:
        return tuple(c.text(lab.x, y, s, anchor="mm", bg=True, owner=owner) for s, y in zip(lab.lines, ys))
    c.erase(*grow(lines_box(lab.x, lab.y, lab.lines), BG_MARGIN), owner=owner)
    return tuple(c.text(lab.x, y, s, anchor="mm", owner=owner) for s, y in zip(lab.lines, ys))


def draw(diagram: Diagram, scale: float = SCALE) -> Drawing:
    """안에 다른 요소를 품은 요소(겉에서 안으로) → 선 → 안에 다른 요소가 없는 요소 → 선 글자 차례로 그린다. 요소를 선 뒤에
    그려 선 끝의 화살촉이 요소 테두리 밑으로 들어가고, 품은 요소는 선 앞에 그려 흰 바탕이 안쪽 선을 덮지 않는다. 선 글자는 흰
    바탕을 깔아 맨 위에 쓴다(_draw_label) — 선 위에 얹은 이름은 그 바탕 뒤로 선이 끊긴다."""
    lay = layout(diagram)
    c = Canvas(scale)
    depth = {p.key: len(lay.ancestors(p.key)) for p in lay.boxes}
    for p in sorted((p for p in lay.boxes if p.key in lay.parents), key=lambda p: depth[p.key]):
        _draw_box(c, p)
    shapes = [_draw_relation(c, r, lay.kind_of(r.relation), lay.by_key) for r in lay.relations]
    for p in lay.boxes:
        if p.key not in lay.parents:
            _draw_box(c, p)
    drawn = []
    for r, (line, heads, marks) in zip(lay.relations, shapes):
        texts = tuple(_draw_label(c, lab, r.owner) for lab in r.labels)
        drawn.append(DrawnRelation(line, heads, texts, marks))
    return Drawing(c, lay, tuple(drawn), diagram.notices)


def render(spec: Spec, data: Any, scale: float = SCALE) -> Drawing:
    """JSON을 읽어 그린다. PNG는 Drawing.canvas.save(경로)나 to_image()로 얻는다 — 그 배율로 그리기에 그림이 너무 크면
    그 둘이 ValueError를 낸다(canvas.MAX_PIXELS)."""
    return draw(parse(spec, data), scale)
