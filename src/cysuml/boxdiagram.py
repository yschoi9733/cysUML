"""AI가 배치하는 그림의 공용 엔진: JSON을 요소·관계 모델로 읽고(parse), 자리를 잡아(layout) 그림판에 그린다(draw).

클래스도·패키지도처럼 요소(모양만 다른 상자)와 요소를 잇는 선, 선 위 글자로 이뤄진 그림이 함께 쓴다. 그림마다 다른 것은
도구 정의(Spec)로 넘긴다 — 받는 요소 종류와 그 모양(Shape), 받는 관계 종류(RelationType), 연관의 기본 방향, 오류 글의 말
(Words). 그림 모듈은 모양과 관계 종류를 정의해 Spec에 담기만 하고 이 모듈은 고치지 않는다.

배치는 입력이 정한다 — 요소의 왼쪽 위와 관계선의 꺾는 점은 받은 그대로 쓰고, 여기서는 요소를 글자와 안의 요소에 맞춰
키우고(왼쪽·위는 그대로) 선 끝·선 글자 자리만 계산한다.

틀린 입력은 그리기 전에 InputError로 돌려준다. 문제마다 "classes[0].left: …"처럼 입력 안의 자리를 붙인다. 읽기(parse)의
문제를 한 번에 모두 모아 알리고, 읽기가 통과하면 자리 잡기(layout)에서 선을 그을 수 없는 문제를 한 번에 모두 모아 알린다 —
선 끝은 요소 크기를 알아야 정해지므로 요소가 다 읽혀야 잴 수 있다.
"""
from __future__ import annotations

import math
import numbers
from dataclasses import dataclass, field, replace
from functools import cached_property
from typing import Any, Callable, Mapping, Optional, Union

from . import text as T
from .canvas import BG_MARGIN, SCALE, Canvas, Line, Point, Polygon, Text
from .geom import Border, RectBorder, Segment, gap, grow, hits, meets, outline, segment_gap, span
from .parsing import InputError, Reader
from .parsing import at as _at
from .parsing import show as _show
from .report import fmt_num, fmt_rect

NAVIGABLE = ("to", "from", "both", "none")
SIDES = ("bottom", "top", "left", "right")
COORD_LIMIT = 1_000_000

DASH = (5, 4)
TRIANGLE = (18, 9)  # 상속·실체화 빈 삼각형의 길이와 반폭
DIAMOND = 18        # 집합·합성 마름모 길이(그림판 기본값)
ARROW = 10          # 열린 화살촉 길이(그림판 기본값)
MAX_LINE = 200_000  # 관계선 하나의 길이 상한 — 그림판 점선 칸 수 상한(MAX_DASHES × 무늬)보다 넉넉히 작게
EDGE_SLACK = 0.5    # 선이 끝 요소 안을 지나는지 볼 때 테두리에서 이만큼 안쪽부터 "안"으로 친다(테두리를 따라 가는 선은 괜찮다)

NAME_GAP = 8        # 이름 글자 상자와 선 사이
LABEL_CLEAR = BG_MARGIN + 1  # 선 글자의 흰 바탕이 선에 닿지 않게 글자 상자를 이만큼 넓혀 선과 견준다
LABEL_LINE = 15     # 여러 줄 선 글자·모양 밖 이름의 줄 간격(줄 상자가 겹치지 않게)
MULT_ANGLES = (math.pi / 8, math.pi / 6, math.pi / 4, math.pi / 3)
MULT_DISTANCES = (20, 25, 30, 35, 40, 50)
MULT_ENOUGH = 20    # 요소와 이만큼 떨어지면 더 멀리 두지 않고 선 끝에 가까운 자리를 고른다

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


@dataclass(frozen=True)
class NameZone:
    """요소가 제 글자(이름·스테레오타입 등)를 쓰는 자리. outside면 몸통(선이 닿는 테두리) 밖에 붙은 칸이다(패키지 탭, 모양 밖
    이름) — 그 요소가 끝인 선도 지나가면 안 된다. 몸통 안의 칸은 그 요소를 품은 선만 피하면 된다."""

    rect: T.Box
    outside: bool


@dataclass(frozen=True)
class Element:
    """요소 하나. key는 관계·중첩이 가리키는 열쇠, name은 이름 줄(이름이 없는 모양은 빈 튜플), parent는 품은 요소의 열쇠,
    data는 모양이 제 필드를 읽은 값이다. min_width·min_height는 자리(모양 밖 이름까지)의 최소 크기다."""

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
    """요소 모양. 그림 모듈은 이것을 이어받아 겉 테두리·이름 자리·크기·제 필드 읽기·그리기를 정한다. 기본은 사각형 테두리다.

    rect는 모양 자리(모양 밖 이름은 빼고)다. 모양 밖 이름은 공용 엔진이 쓰고 그 자리를 이름 칸으로 넘긴다."""

    fields: tuple[str, ...] = ()  # 이 모양이 더 받는 필드(공용 필드 밖)
    named: bool = True            # 이름을 받는지(받으면 꼭 준다)
    sized: bool = True            # width·height(자리의 최소 크기)를 받는지
    stereotyped: bool = True      # stereotype을 받는지
    holds: bool = False           # 안에 요소를 둘 수 있는지
    outside_name: bool = False    # 이름을 모양 밖에 쓰는지(쪽은 name_side)
    default_width: float = 0      # width를 주지 않았을 때의 최소 폭

    def read(self, r: Reader, o: dict, path: str, kind: Optional[str]) -> Any:
        """제 필드를 읽는다. 문제는 r.fail로 알린다. kind가 None이면 입력의 kind가 틀렸다(문제만 모으고 값은 쓰지 않는다)."""
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
        테두리 안이어야 한다. None(기본)이면 테두리 가운데다."""
        return None

    def name_zones(self, e: Element, rect: T.Box) -> tuple[NameZone, ...]:
        """이름 칸. 안에 요소를 두는 모양만 쓴다(선이 지나가면 안 되는 자리)."""
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


@dataclass(frozen=True)
class EndShape:
    """선 끝 모양. draw(그림판, 끝 점, 선 위 그 앞 점, owner)는 그린 기록(삼각형·마름모는 Polygon, 화살촉은 Line)을 돌려준다."""

    name: str
    length: float
    draw: Callable[[Canvas, Point, Point, str], Union[Line, Polygon]]


ARROW_HEAD = EndShape("화살촉", ARROW, lambda c, tip, frm, o: c.open_arrow(tip, frm, size=ARROW, owner=o))
TRIANGLE_HEAD = EndShape("삼각형", TRIANGLE[0], lambda c, tip, frm, o: c.closed_arrow(
    tip, frm, filled=False, size=TRIANGLE[0], half=TRIANGLE[1], owner=o))
OPEN_DIAMOND = EndShape("마름모", DIAMOND, lambda c, tip, frm, o: c.diamond(tip, frm, filled=False, size=DIAMOND, owner=o))
FILLED_DIAMOND = EndShape("마름모", DIAMOND, lambda c, tip, frm, o: c.diamond(tip, frm, filled=True, size=DIAMOND, owner=o))


@dataclass(frozen=True)
class RelationType:
    """관계 종류. start·end는 from·to 쪽 끝에 늘 그리는 모양이다. navigable이면 방향(navigable)을 받아 그 쪽에 화살촉을 그리고,
    multiplicity면 다중도를 받는다. trunk면 자식 여럿의 선이 한 줄기로 모여 한 끝 모양을 함께 쓰는 것(공유 줄기)을 받는다.
    label(상속 등)과 role(from 쪽이 무엇인지 — 상속은 자식)은 오류 글과 도구 설명(guide.relation_fields)에 쓴다."""

    label: str
    dash: Optional[tuple[float, float]] = None
    start: Optional[EndShape] = None
    end: Optional[EndShape] = None
    navigable: bool = False
    multiplicity: bool = False
    trunk: bool = False
    role: str = ""

    def __post_init__(self):
        if self.navigable and self.end is not None:
            raise ValueError("방향을 받는 관계는 to 쪽 끝 모양을 따로 두지 않는다(화살촉이 겹친다)")


@dataclass(frozen=True, eq=False)
class Spec:
    """도구 하나가 받는 것. shapes는 요소 종류 → 모양, relations는 관계 종류 → 정의다. navigable은 방향을 받는 관계(연관·집합·
    합성)의 기본 방향이다. extended면 새 도구 입력(id·in·여러 줄 이름·관계 stereotype·name_side)을 받는다 — 클래스도 도구는
    받지 않는다. 관계 종류가 하나뿐이면 관계의 kind를 빼도 그 종류로 읽는다."""

    shapes: Mapping[str, Shape]
    relations: Mapping[str, RelationType]
    words: Words = ELEMENT_WORDS
    list_field: str = "elements"
    default_kind: Optional[str] = None
    navigable: str = "to"
    extended: bool = True

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
    spec: Spec
    boxes: tuple[Element, ...]
    relations: tuple[Relation, ...]


@dataclass(frozen=True)
class PlacedBox:
    """자리를 잡은 요소. rect는 자리(모양 밖 이름까지 덮는다), shape_rect는 모양 자리, inner는 안의 요소를 둘 칸(안에 요소를 둘 수
    없는 모양은 None), zones는 이름 칸, frame은 안에 요소를 두는 모양의 테두리 선, parts는 겹침을 볼 때 그 요소를 이루는 테두리들
    (Shape.parts), anchor는 선이 향하는 점(Shape.anchor — 없으면 테두리 가운데)이다."""

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

    def __post_init__(self):
        if not self.parts:
            object.__setattr__(self, "parts", (RectBorder(self.rect),))
        if self.anchor is None:
            object.__setattr__(self, "anchor", self.border.center())

    @property
    def key(self) -> str:
        return self.box.key

    @property
    def width(self) -> float:
        return self.rect[2] - self.rect[0]

    @property
    def height(self) -> float:
        return self.rect[3] - self.rect[1]


@dataclass(frozen=True)
class Label:
    """선에 붙는 글자(가운데가 (x, y)). role은 name·from_multiplicity·to_multiplicity, lines는 위에서부터 줄이다."""

    role: str
    lines: tuple[str, ...]
    x: float
    y: float

    @property
    def text(self) -> str:
        return " ".join(self.lines)


@dataclass(frozen=True)
class PlacedRelation:
    """owner는 그 관계를 그린 기록의 owner다 — 보통 "출발->도착"이고, 같은 이름이 앞에 있으면 "#2"·"#3"을 붙인다."""

    relation: Relation
    owner: str
    points: tuple[Point, ...]
    labels: tuple[Label, ...]


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
class DrawnRelation:
    """관계 하나를 그린 기록: 선(line), 선 끝 모양(heads — 삼각형·마름모는 Polygon, 화살촉은 Line), 선 글자(labels —
    PlacedRelation.labels 차례로, 글자마다 줄마다의 기록)."""

    line: Line
    heads: tuple[Union[Line, Polygon], ...]
    labels: tuple[tuple[Text, ...], ...]


@dataclass(frozen=True)
class Drawing:
    """drawn은 관계마다(layout.relations 차례) 그린 기록이다 — 검사가 그림판 기록을 거꾸로 짚어 찾지 않게 넘긴다."""

    canvas: Canvas
    layout: Layout
    drawn: tuple[DrawnRelation, ...]


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
        if source is not None and source == target and len(via) < 2:
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
                self.fail(where, "제 자신 안에 둘 수 없다")
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
        relations = []
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
            relations.append(r)
        return Diagram(spec, tuple(e for _, e in read), tuple(relations))


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


def name_spots(points: tuple[Point, ...], lines: Union[str, tuple[str, ...]]) -> list[Point]:
    """이름 글자 가운데의 후보: 가장 긴 구간(길이가 같으면 앞 구간)의 가운데에서, 진행 방향의 왼쪽(오른쪽으로 가는
    가로선이면 위)과 오른쪽으로 글자 상자가 선과 NAME_GAP만큼 떨어지는 자리. 꺾는 점에서 먼 곳이라 다른 구간에 덜 걸린다."""
    if isinstance(lines, str):
        lines = (lines,)
    k = max(range(len(points) - 1), key=lambda j: (math.dist(points[j], points[j + 1]), -j))
    (x1, y1), (x2, y2) = points[k], points[k + 1]
    ln = math.dist(points[k], points[k + 1])
    ux, uy = (x2 - x1) / ln, (y2 - y1) / ln
    b = lines_box(0, 0, lines)
    out = []
    for nx, ny in ((uy, -ux), (-uy, ux)):
        reach = max(-(cx * nx + cy * ny) for cx in (b[0], b[2]) for cy in (b[1], b[3]))  # 선을 마주 보는 쪽 끝까지
        out.append(((x1 + x2) / 2 + nx * (reach + NAME_GAP), (y1 + y2) / 2 + ny * (reach + NAME_GAP)))
    return out


def multiplicity_spots(end: Point, toward: Point) -> list[Point]:
    """다중도 글자 가운데의 후보: 선 끝 end에서 선 방향(end→toward)을 MULT_ANGLES만큼 양쪽으로 돌린 쪽으로
    MULT_DISTANCES만큼 떨어진 자리. 선 끝에 가까운 것부터 늘어놓는다."""
    th = math.atan2(toward[1] - end[1], toward[0] - end[0])
    return [(end[0] + d * math.cos(th - turn), end[1] + d * math.sin(th - turn))
            for d in MULT_DISTANCES for a in MULT_ANGLES for turn in (a, -a)]


@dataclass(frozen=True)
class Obstacles:
    """선 글자가 피할 것: solids는 겹치면 안 되는 테두리(요소, 이름 칸), frames는 닿으면 안 되는 선(끝을 품은 요소의 테두리 선)."""

    solids: tuple[Border, ...]
    frames: tuple[Segment, ...] = ()


def obstacles(boxes: tuple[PlacedBox, ...], holders: frozenset[str] = frozenset()) -> Obstacles:
    """관계 하나의 선 글자가 피할 것. 끝을 품은 요소(holders)는 안에 글자를 둘 수 있지만 테두리 선과 이름 칸은 피한다. 그 밖의
    요소는 통째로 피한다(몸통 밖 이름 칸도)."""
    solids: list[Border] = []
    frames: list[Segment] = []
    for p in boxes:
        if p.key in holders:
            solids += [RectBorder(z.rect) for z in p.zones]
            frames += p.frame
        else:
            solids.append(p.border)
            solids += [RectBorder(z.rect) for z in p.zones if z.outside]
    return Obstacles(tuple(solids), tuple(frames))


class _Spots:
    """선 글자의 자리를 고른다. 글자의 흰 바탕(글자 상자를 LABEL_CLEAR만큼 넓힌 것)이 피할 것(Obstacles)에 겹치지 않는 자리,
    그 가운데 관계선과 선 끝 모양(화살촉·삼각형·마름모)과 앞서 놓은 선 글자에 닿지 않는 자리, 그 가운데 피할 것에서 먼
    (MULT_ENOUGH까지) 자리가 낫고, 같으면 후보 목록의 앞쪽이다."""

    def __init__(self, segments: list[Segment]):
        self.segments = [(p, q, span((p, q))) for p, q in segments]
        self.labels: list[T.Box] = []

    def pick(self, lines: tuple[str, ...], candidates: list[Point], avoid: Obstacles) -> Point:
        boxes = [lines_box(x, y, lines) for x, y in candidates]
        wides = [grow(b, LABEL_CLEAR) for b in boxes]
        region = span(pt for w in wides for pt in (w[:2], w[2:]))
        # 후보들이 닿을 수 있는 것만 먼저 거른다. 피할 것은 MULT_ENOUGH 밖이면 점수가 같아 거리를 잴 필요가 없다.
        reach = grow(region, MULT_ENOUGH)
        near_solids = [b for b in avoid.solids if meets(b.bounds, reach)]
        near_frames = [s for s in avoid.frames if meets(span(s), reach)]
        near_segments = [(p, q) for p, q, bb in self.segments if meets(bb, region)]
        near_labels = [x for x in self.labels if meets(x, region)]
        best = None
        for p, box, wide in zip(candidates, boxes, wides):
            room = min([b.gap(wide) for b in near_solids] + [segment_gap(wide, s) for s in near_frames],
                       default=MULT_ENOUGH)
            clear = not any(hits(a, b, wide) for a, b in near_segments) and all(gap(wide, x) >= 0 for x in near_labels)
            score = (room >= 0, clear, min(room, MULT_ENOUGH))
            if best is None or score > best[0]:
                best = score, p, box
        assert best is not None
        self.labels.append(best[2])
        return best[1]


def shape_lengths(r: Relation, t: RelationType) -> tuple[float, float]:
    """선 처음(from)과 끝(to)에 그리는 모양이 선을 따라 차지하는 길이."""
    start = t.start.length if t.start else ARROW if t.navigable and r.navigable in ("from", "both") else 0
    end = t.end.length if t.end else ARROW if t.navigable and r.navigable in ("to", "both") else 0
    return start, end


def _route(r: Relation, a: PlacedBox, b: PlacedBox, path: str, t: RelationType,
           w: Words) -> tuple[Optional[tuple[Point, ...]], list[str]]:
    """관계선의 점들(선 끝은 요소가 향하게 한 점(anchor — 보통 테두리 가운데)에서 첫·마지막 꺾는 점으로, 꺾는 점이 없으면 다른
    요소의 그 점으로 가는 선이 테두리와 만나는 곳)과, 그렇게 그을 수 없으면 그 까닭들."""
    ca, cb = a.anchor, b.anchor
    assert ca is not None and cb is not None
    if r.via:
        start, end = a.border.exit(ca, r.via[0]), b.border.exit(cb, r.via[-1])
        problems = [f"{_at(_at(path, 'via'), j)}: 꺾는 점 {r.via[j]}이 {key} {w.noun} {_show(p_.key)}({fmt_rect(p_.border.bounds)}) 안이나 "
                    f"{w.edge} 위에 있다 — {w.noun} 밖으로 옮긴다"
                    for p, p_, j, key in ((start, a, 0, "from"), (end, b, len(r.via) - 1, "to")) if p is None]
        if problems:
            return None, problems
    else:
        start, end = a.border.exit(ca, cb), b.border.exit(cb, ca)
        if start is None or end is None or (end[0] - start[0]) * (cb[0] - ca[0]) + (end[1] - start[1]) * (cb[1] - ca[1]) <= 0:
            return None, [f"{path}: {w.noun} {_show(r.source)}와 {_show(r.target)}가 겹치거나 맞닿아 둘 사이에 선을 그을 자리가 "
                          f"없다 — 떼어 놓거나 {w.noun} 밖을 도는 꺾는 점(via)을 준다"]
    assert start is not None and end is not None
    points = (start, *r.via, end)
    if start == end:
        return None, [f"{path}: 선의 두 끝이 같은 점 {start}이다 — 첫·마지막 꺾는 점을 {w.noun}의 다른 쪽으로 옮긴다"]
    problems = []
    # 선 끝은 테두리 위에 있으므로, 테두리에서 EDGE_SLACK 안쪽으로 줄인 것을 지나면 선이 끝 요소 안으로 들어간 것이다.
    # 요소가 선 위에 그려지면 그 부분은 가려지므로 선이 엉뚱한 곳에서 시작하는 것처럼 보인다.
    for key, p_ in (("from", a),) + ((("to", b),) if r.target != r.source else ()):
        inner = p_.border.grown(-EDGE_SLACK)
        if any(inner.hits(p, q) for p, q in zip(points, points[1:])):
            problems.append(f"{path}: 선이 {key} {w.noun} {_show(p_.key)}({fmt_rect(p_.border.bounds)}) 안을 지난다 — 꺾는 점을 그 "
                            f"{w.noun} 밖으로 돌린다")
    lengths = [math.dist(p, q) for p, q in zip(points, points[1:])]
    head, tail = shape_lengths(r, t)
    if len(lengths) == 1 and lengths[0] < head + tail:
        problems.append(f"{path}: 선 길이 {fmt_num(lengths[0])}가 양 끝 모양 길이({fmt_num(head)}+{fmt_num(tail)})보다 짧다 — "
                        f"{w.noun}를 더 떼어 놓는다")
    elif len(lengths) > 1:
        for length, need, key, which in ((lengths[0], head, "from", "첫"), (lengths[-1], tail, "to", "마지막")):
            if length < need:
                problems.append(f"{path}: {key} 쪽 끝 구간 길이 {fmt_num(length)}가 끝 모양 길이({fmt_num(need)})보다 짧다 — "
                                f"{which} 꺾는 점을 {w.noun}에서 더 떼어 놓는다")
    if sum(lengths) > MAX_LINE:
        problems.append(f"{path}: 선 길이 {fmt_num(sum(lengths))}가 {MAX_LINE}을 넘는다 — {w.noun}를 가까이 모은다")
    return (None if problems else points), problems


def _outside_name(e: Element, w: float, h: float) -> tuple[float, float, Point, T.Box]:
    """모양 밖 이름이 있는 요소의 (자리 폭, 자리 높이, 자리 왼쪽 위에서 모양 왼쪽 위까지, 자리 왼쪽 위 기준 이름 칸)."""
    lines = e.name
    tw = math.ceil(max(T.text_width(s) for s in lines))
    th = LABEL_LINE * len(lines)
    if e.name_side in ("bottom", "top"):
        width, height = max(w, tw), h + NAME_SEP + th
        sx, nx = (width - w) / 2, (width - tw) / 2
        sy, ny = (0, h + NAME_SEP) if e.name_side == "bottom" else (th + NAME_SEP, 0)
    else:
        width, height = w + NAME_SEP + tw, max(h, th)
        sy, ny = (height - h) / 2, (height - th) / 2
        sx, nx = (0, w + NAME_SEP) if e.name_side == "right" else (tw + NAME_SEP, 0)
    return width, height, (sx, sy), (nx, ny, nx + tw, ny + th)


def _place(spec: Spec, diagram: Diagram, lines_of: Mapping[str, tuple[str, ...]]) -> tuple[PlacedBox, ...]:
    """요소 크기와 자리. 안의 요소부터 재서 바깥 요소가 안의 요소를 NEST_PAD 여백을 두고 덮도록 오른쪽·아래로 늘린다. 제 이름 칸이
    들어갈 크기는 모양(Shape.size)이 정한다."""
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
            w, h, offset, zone = _outside_name(e, sw, sh)
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


def layout(diagram: Diagram) -> Layout:
    """요소 크기, 선의 점들, 선 글자 자리를 잡는다. 선을 그을 수 없는 배치면(꺾는 점이 요소 안이다, 두 요소가 겹치거나
    맞닿았다, 끝 구간이 끝 모양보다 짧다 등) 모두 모아 InputError. 선 글자는 관계 순서대로 이름 → from 다중도 → to 다중도
    차례로 놓고, 앞서 놓은 글자를 뒤 글자가 피한다."""
    spec = diagram.spec
    lines_of = lineage({e.key: e.parent for e in diagram.boxes})  # 품은 사이는 여기서 한 번 재서 검사(Layout)까지 넘긴다
    placed = _place(spec, diagram, lines_of)
    by_key = {p.key: p for p in placed}
    problems: list[str] = []
    routes = []
    for i, r in enumerate(diagram.relations):
        points, found = _route(r, by_key[r.source], by_key[r.target], _at("relations", i), spec.relations[r.kind],
                               spec.words)
        problems += found
        routes.append(points)
    if problems:
        raise InputError(problems)
    used = set(by_key)
    bare = []
    for r, points in zip(diagram.relations, routes):
        owner = base = f"{r.source}->{r.target}"
        n = 2
        while owner in used:
            owner, n = f"{base}#{n}", n + 1
        used.add(owner)
        bare.append(PlacedRelation(r, owner, points, ()))
    sketch = Canvas()  # 선 끝 모양을 그림판과 똑같이 얻으려고 선만 한 번 그려 본다
    for p in bare:
        _draw_relation(sketch, p, spec.relations[p.relation.kind])
    spots = _Spots(outline(sketch.records))
    avoids: dict[frozenset[str], Obstacles] = {}  # 끝을 품은 요소들마다 한 번만 만든다
    out = []
    for p in bare:
        r, points = p.relation, p.points
        held = holders(lines_of, r)
        if held not in avoids:
            avoids[held] = obstacles(placed, held)
        avoid = avoids[held]
        labels = []
        if r.label_lines:
            lines = r.label_lines
            labels.append(Label("name", lines, *spots.pick(lines, name_spots(points, lines), avoid)))
        for role, text, tip, toward in (("from_multiplicity", r.source_multiplicity, points[0], points[1]),
                                        ("to_multiplicity", r.target_multiplicity, points[-1], points[-2])):
            if text:
                labels.append(Label(role, (text,), *spots.pick((text,), multiplicity_spots(tip, toward), avoid)))
        out.append(replace(p, labels=tuple(labels)))
    return Layout(spec, placed, tuple(out), lines_of)


# ---------------------------------------------------------------- 그리기


def _draw_relation(c: Canvas, r: PlacedRelation, t: RelationType) -> tuple[Line, tuple[Union[Line, Polygon], ...]]:
    """선과 선 끝 모양을 그리고 그 기록을 돌려준다."""
    pts, o = r.points, r.owner
    line = c.line(pts, dash=t.dash, owner=o)
    heads: list[Union[Line, Polygon]] = []
    if t.start is not None:
        heads.append(t.start.draw(c, pts[0], pts[1], o))
    if t.end is not None:
        heads.append(t.end.draw(c, pts[-1], pts[-2], o))
    if t.navigable and r.relation.navigable in ("to", "both"):
        heads.append(ARROW_HEAD.draw(c, pts[-1], pts[-2], o))
    if t.navigable and r.relation.navigable in ("from", "both"):
        heads.append(ARROW_HEAD.draw(c, pts[0], pts[1], o))
    return line, tuple(heads)


def _draw_box(c: Canvas, p: PlacedBox) -> None:
    p.shape.draw(c, p)
    for s, (x, y) in zip(p.box.name, p.name_at):
        c.text(x, y, s, anchor="mm", owner=p.key)


def draw(diagram: Diagram, scale: float = SCALE) -> Drawing:
    """안에 다른 요소를 품은 요소(겉에서 안으로) → 선 → 안에 다른 요소가 없는 요소 → 선 글자 차례로 그린다. 요소를 선 뒤에
    그려 선 끝의 화살촉이 요소 테두리 밑으로 들어가고, 품은 요소는 선 앞에 그려 흰 바탕이 안쪽 선을 덮지 않는다. 선 글자는 흰
    바탕을 깔아 맨 위에 쓴다."""
    lay = layout(diagram)
    c = Canvas(scale)
    depth = {p.key: len(lay.ancestors(p.key)) for p in lay.boxes}
    for p in sorted((p for p in lay.boxes if p.key in lay.parents), key=lambda p: depth[p.key]):
        _draw_box(c, p)
    shapes = [_draw_relation(c, r, lay.kind_of(r.relation)) for r in lay.relations]
    for p in lay.boxes:
        if p.key not in lay.parents:
            _draw_box(c, p)
    drawn = []
    for r, (line, heads) in zip(lay.relations, shapes):
        texts = tuple(tuple(c.text(lab.x, y, s, anchor="mm", bg=True, owner=r.owner)
                            for s, y in zip(lab.lines, line_ys(lab.y, len(lab.lines)))) for lab in r.labels)
        drawn.append(DrawnRelation(line, heads, texts))
    return Drawing(c, lay, tuple(drawn))


def render(spec: Spec, data: Any, scale: float = SCALE) -> Drawing:
    """JSON을 읽어 그린다. PNG는 Drawing.canvas.save(경로)나 to_image()로 얻는다 — 그 배율로 그리기에 그림이 너무 크면
    그 둘이 ValueError를 낸다(canvas.MAX_PIXELS)."""
    return draw(parse(spec, data), scale)
