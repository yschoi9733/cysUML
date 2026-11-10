"""클래스도: JSON을 상자·관계 모델로 읽고(parse), 자리를 잡아(layout) 그림판에 그린다(draw).

배치는 입력이 정한다 — 상자의 왼쪽 위와 관계선의 꺾는 점은 받은 그대로 쓰고, 여기서는 상자를 글자 폭과 줄 수에 맞춰
키우고(왼쪽·위는 그대로) 선 끝·다중도·이름 글자의 자리만 계산한다. 상자 안 글자 자리, 선 끝, 다중도 자리는 StarUML이
그리는 모양을 따른 기존 규칙이다.

틀린 입력은 그리기 전에 InputError로 돌려준다. 문제마다 "classes[0].left: …"처럼 입력 안의 자리를 붙인다. 읽기(parse)의
문제를 한 번에 모두 모아 알리고, 읽기가 통과하면 자리 잡기(layout)에서 선을 그을 수 없는 문제를 한 번에 모두 모아 알린다 —
선 끝은 상자 크기를 알아야 정해지므로 상자가 다 읽혀야 잴 수 있다.
"""
from __future__ import annotations

import json
import math
import numbers
from dataclasses import dataclass, replace
from typing import Any, Optional

from . import text as T
from .canvas import BG_MARGIN, SCALE, Canvas, Line, Point, Polygon

CLASS_KINDS = ("class", "abstract", "interface", "enum")
RELATION_KINDS = ("association", "aggregation", "composition", "generalization", "realization", "dependency")
ASSOCIATIONS = ("association", "aggregation", "composition")
NAVIGABLE = ("to", "from", "both", "none")
VISIBILITY = ("+", "-", "#", "~", "")

CLASS_FIELDS = ("name", "kind", "stereotype", "attributes", "operations", "literals", "left", "top", "width", "height")
ATTRIBUTE_FIELDS = ("name", "type", "default", "visibility", "static")
OPERATION_FIELDS = ("name", "params", "returns", "visibility", "static")
RELATION_FIELDS = ("kind", "from", "to", "name", "from_multiplicity", "to_multiplicity", "navigable", "via")

COORD_LIMIT = 1_000_000
MIN_WIDTH = 90

# 상자 안 글자 자리
HEAD = 24          # 이름 한 줄짜리 머리 칸 높이
NAME_LINE = 14     # 키워드(«interface» 등)·{abstract} 줄 하나가 머리 칸에 더하는 높이
NAME_PAD = 20      # 머리 칸 글자의 좌우 여백 합
ROW_LEFT = 5
ROW_PAD = 15       # 구획 줄의 왼쪽(ROW_LEFT)·오른쪽 여백 합
ROW = 15           # 구획 줄 간격
STATIC_PAD = 3     # 밑줄 친 줄 뒤는 그만큼 더 띄운다(밑줄이 다음 줄 글자나 구획선에 붙지 않게)
UNDERLINE = 9.5    # 밑줄 높이(글자 가운데 기준) — 글자 아래 끝(+7.3)과 떨어지게
SECTION_PAD = 10   # 구획 하나의 위아래 여백 합(빈 구획은 이 높이만)
BOTTOM = 4

DASH = (5, 4)
TRIANGLE = (18, 9)  # 상속·실체화 빈 삼각형의 길이와 반폭
DIAMOND = 18        # 집합·합성 마름모 길이(그림판 기본값)
ARROW = 10          # 열린 화살촉 길이(그림판 기본값)
MAX_LINE = 200_000  # 관계선 하나의 길이 상한 — 그림판 점선 칸 수 상한(MAX_DASHES × 무늬)보다 넉넉히 작게
EDGE_SLACK = 0.5    # 선이 끝 상자 안을 지나는지 볼 때 변에서 이만큼 안쪽부터 "안"으로 친다(변을 따라 가는 선은 괜찮다)

NAME_GAP = 8        # 이름 글자 상자와 선 사이
LABEL_CLEAR = BG_MARGIN + 1  # 선 글자의 흰 바탕이 선에 닿지 않게 글자 상자를 이만큼 넓혀 선과 견준다
MULT_ANGLES = (math.pi / 8, math.pi / 6, math.pi / 4, math.pi / 3)
MULT_DISTANCES = (20, 25, 30, 35, 40, 50)
MULT_ENOUGH = 20    # 상자와 이만큼 떨어지면 더 멀리 두지 않고 선 끝에 가까운 자리를 고른다


class InputError(ValueError):
    """틀린 입력. problems는 문제마다 한 줄이다."""

    def __init__(self, problems):
        self.problems = tuple(problems)
        super().__init__("\n".join(self.problems))


@dataclass(frozen=True)
class Row:
    """구획 안 한 줄(속성·연산·열거 값). static이면 밑줄을 긋는다."""

    text: str
    static: bool = False


@dataclass(frozen=True)
class ClassBox:
    name: str
    kind: str
    stereotype: Optional[str]
    literals: tuple[Row, ...]
    attributes: tuple[Row, ...]
    operations: tuple[Row, ...]
    left: float
    top: float
    min_width: float
    min_height: float

    @property
    def keyword(self) -> Optional[str]:
        words = {"interface": ["interface"], "enum": ["enumeration"]}.get(self.kind, [])
        repeats = {"interface": ("interface",), "enum": ("enumeration", "enum"), "abstract": ("abstract",)}
        if self.stereotype and self.stereotype.casefold() not in repeats.get(self.kind, ()):
            words.append(self.stereotype)
        return f"«{', '.join(words)}»" if words else None

    @property
    def name_lines(self) -> tuple[str, ...]:
        """머리 칸의 이름 줄. 첫 줄(이름)은 굵게 쓴다. 추상 클래스는 기울인 글꼴을 넣지 않았으므로 UML의 다른 표기
        {abstract}를 이름 아래에 쓴다."""
        return (self.name, "{abstract}") if self.kind == "abstract" else (self.name,)

    @property
    def sections(self) -> tuple[tuple[Row, ...], ...]:
        """그리는 구획. 클래스는 비어도 속성·연산 구획을 그리고, 인터페이스·열거형은 빈 구획을 숨긴다(열거 값 구획은 그린다)."""
        if self.kind in ("class", "abstract"):
            return self.attributes, self.operations
        out = [self.literals] if self.kind == "enum" else []
        return tuple(out + [rows for rows in (self.attributes, self.operations) if rows])


@dataclass(frozen=True)
class Relation:
    kind: str
    source: str
    target: str
    name: Optional[str]
    source_multiplicity: Optional[str]
    target_multiplicity: Optional[str]
    navigable: Optional[str]  # 연관·집합·합성만 — 그 밖은 None
    via: tuple[Point, ...]


@dataclass(frozen=True)
class Diagram:
    classes: tuple[ClassBox, ...]
    relations: tuple[Relation, ...]


@dataclass(frozen=True)
class PlacedBox:
    box: ClassBox
    width: float
    height: float

    @property
    def rect(self) -> T.Box:
        b = self.box
        return b.left, b.top, b.left + self.width, b.top + self.height


@dataclass(frozen=True)
class Label:
    """선에 붙는 글자(가운데가 (x, y)). role은 name·from_multiplicity·to_multiplicity다."""

    role: str
    text: str
    x: float
    y: float


@dataclass(frozen=True)
class PlacedRelation:
    """owner는 그 관계를 그린 기록의 owner다 — 보통 "출발->도착"이고, 같은 이름이 앞에 있으면 "#2"·"#3"을 붙인다."""

    relation: Relation
    owner: str
    points: tuple[Point, ...]
    labels: tuple[Label, ...]


@dataclass(frozen=True)
class Layout:
    boxes: tuple[PlacedBox, ...]
    relations: tuple[PlacedRelation, ...]


@dataclass(frozen=True)
class Drawing:
    canvas: Canvas
    layout: Layout


# ---------------------------------------------------------------- 입력 읽기


def _show(v: Any) -> str:
    try:
        s = repr(v)
    except ValueError:  # 파이썬이 글자로 바꾸지 않는 아주 큰 정수(4300자리 넘게)
        return "(아주 큰 정수)"
    return s if len(s) <= 40 else s[:37] + "..."


def _at(path: str, key) -> str:
    return f"{path}[{key}]" if isinstance(key, int) else f"{path}.{key}" if path else str(key)


class _Reader:
    def __init__(self):
        self.problems: list[str] = []

    def fail(self, path: str, message: str) -> None:
        self.problems.append(f"{path or '입력'}: {message}")

    def obj(self, v, path: str, fields: tuple[str, ...], required: tuple[str, ...] = ()) -> Optional[dict]:
        if not isinstance(v, dict):
            self.fail(path, f"객체여야 한다(받은 값 {_show(v)})")
            return None
        for k in v:
            if k not in fields:
                self.fail(_at(path, k) if isinstance(k, str) else path,
                          f"모르는 필드다{'' if isinstance(k, str) else f' {_show(k)}'}. 쓸 수 있는 필드: {', '.join(fields)}")
        for k in required:
            if k not in v:
                self.fail(path, f"'{k}' 필드가 빠졌다")
        return v

    def items(self, v, path: str) -> list:
        if not isinstance(v, (list, tuple)):
            self.fail(path, f"목록이어야 한다(받은 값 {_show(v)})")
            return []
        return list(v)

    def text(self, v, path: str, bold: bool = False, name: bool = False) -> Optional[str]:
        """name이면 상자를 가리키는 이름이라 앞뒤 공백을 뗀다("A "와 "A"를 같은 상자로)."""
        if not isinstance(v, str):
            self.fail(path, f"문자열이어야 한다(받은 값 {_show(v)})")
            return None
        if not v.strip():
            self.fail(path, "비어 있다")
            return None
        try:
            T.text_width(v, bold)
        except ValueError as e:
            self.fail(path, str(e))
            return None
        return T.normalize(v).strip() if name else T.normalize(v)

    def number(self, v, path: str, least: float = -COORD_LIMIT) -> Optional[float]:
        try:
            f = float(v) if isinstance(v, numbers.Real) and not isinstance(v, bool) else math.nan
        except OverflowError:  # float으로 못 바꾸는 큰 정수(JSON 정수는 자릿수 제한이 없다)
            f = math.inf
        if math.isnan(f):
            self.fail(path, f"수여야 한다(받은 값 {_show(v)})")
            return None
        if not least <= f <= COORD_LIMIT:
            self.fail(path, f"{least:.0f}~{COORD_LIMIT:.0f} 사이여야 한다(받은 값 {_show(v)})")
            return None
        return f

    def choice(self, v, path: str, options: tuple[str, ...]) -> Optional[str]:
        if not isinstance(v, str) or v not in options:
            self.fail(path, f"{' · '.join(repr(o) for o in options)} 가운데 하나여야 한다(받은 값 {_show(v)})")
            return None
        return v

    def flag(self, v, path: str) -> bool:
        if not isinstance(v, bool):
            self.fail(path, f"true나 false여야 한다(받은 값 {_show(v)})")
            return False
        return v

    def point(self, v, path: str) -> Optional[Point]:
        if not isinstance(v, (list, tuple)) or len(v) != 2:
            self.fail(path, f"[x, y]여야 한다(받은 값 {_show(v)})")
            return None
        x, y = self.number(v[0], _at(path, 0)), self.number(v[1], _at(path, 1))
        return None if x is None or y is None else (x, y)

    # -------- 상자

    def member(self, v, path: str, operation: bool) -> Optional[Row]:
        """문자열이면 그 글자를 그대로 한 줄로 쓰고, 객체면 보이기(+·-·#·~)·이름·형·기본값·인자를 이어 쓴다."""
        if isinstance(v, str):
            s = self.text(v, path)
            return None if s is None else Row(s)
        before = len(self.problems)
        o = self.obj(v, path, OPERATION_FIELDS if operation else ATTRIBUTE_FIELDS, ("name",))
        if o is None:
            return None

        def part(key: str) -> Optional[str]:
            return self.text(o[key], _at(path, key)) if key in o else None

        name = part("name")
        visibility = self.choice(o["visibility"], _at(path, "visibility"), VISIBILITY) if "visibility" in o else (
            "+" if operation else "-")
        static = self.flag(o["static"], _at(path, "static")) if "static" in o else False
        if operation:
            params = [self.text(p, _at(_at(path, "params"), i))
                      for i, p in enumerate(self.items(o["params"], _at(path, "params")) if "params" in o else [])]
            returns = part("returns")
            if len(self.problems) > before:
                return None
            return Row(f"{visibility}{name}({', '.join(params)})" + (f": {returns}" if returns else ""), static)
        type_, default = part("type"), self.default(o["default"], _at(path, "default")) if "default" in o else None
        if len(self.problems) > before:
            return None
        return Row(f"{visibility}{name}" + (f": {type_}" if type_ else "") + (f" = {default}" if default else ""), static)

    def default(self, v, path: str) -> Optional[str]:
        """속성 기본값. 문자열은 다른 글자처럼 비어 있지 않아야 하고(빈 문자열 값은 "\\"\\""로 쓴다), 수와 참거짓은 JSON
        표기(0·0.5·true)로 쓴다."""
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            if isinstance(v, float) and not math.isfinite(v):
                self.fail(path, f"유한한 수여야 한다(받은 값 {_show(v)})")
                return None
            try:
                return json.dumps(v)
            except ValueError:
                self.fail(path, f"수가 너무 크다(받은 값 {_show(v)})")
                return None
        if not isinstance(v, str):
            self.fail(path, f"문자열이나 수, true·false여야 한다(받은 값 {_show(v)})")
            return None
        return self.text(v, path)

    def rows(self, o: dict, key: str, path: str, operation: bool) -> tuple[Row, ...]:
        out = []
        for i, v in enumerate(self.items(o[key], _at(path, key)) if key in o else []):
            row = self.member(v, _at(_at(path, key), i), operation)
            if row is not None:
                out.append(row)
        return tuple(out)

    def class_box(self, v, path: str) -> tuple[Optional[str], Optional[ClassBox]]:
        """(읽은 이름, 상자). 이름만 맞고 다른 곳이 틀렸으면 상자는 None이다 — 그 이름을 가리키는 관계를 "없는 상자"로
        또 알리지 않으려고 이름을 따로 돌려준다."""
        before = len(self.problems)
        o = self.obj(v, path, CLASS_FIELDS, ("name", "left", "top"))
        if o is None:
            return None, None
        name = self.text(o["name"], _at(path, "name"), bold=True, name=True) if "name" in o else None
        kind = self.choice(o["kind"], _at(path, "kind"), CLASS_KINDS) if "kind" in o else "class"
        stereotype = None
        if "stereotype" in o:
            stereotype = self.text(o["stereotype"], _at(path, "stereotype"), name=True)
            if stereotype and (stereotype[:1] in "«<" or stereotype[-1:] in "»>"):
                self.fail(_at(path, "stereotype"), f"«» 없이 이름만 쓴다(받은 값 {_show(stereotype)})")
        literals = ()
        if "literals" in o and kind == "enum":
            found = [self.text(s, _at(_at(path, "literals"), i))
                     for i, s in enumerate(self.items(o["literals"], _at(path, "literals")))]
            literals = tuple(Row(s) for s in found if s is not None)
        elif "literals" in o and kind is not None:
            self.fail(_at(path, "literals"), f"열거 값은 kind가 'enum'인 상자에만 쓴다(이 상자는 {kind!r})")
        attributes = self.rows(o, "attributes", path, operation=False)
        operations = self.rows(o, "operations", path, operation=True)
        left = self.number(o["left"], _at(path, "left")) if "left" in o else None
        top = self.number(o["top"], _at(path, "top")) if "top" in o else None
        width = self.number(o["width"], _at(path, "width"), least=0) if "width" in o else MIN_WIDTH
        height = self.number(o["height"], _at(path, "height"), least=0) if "height" in o else 0.0
        if len(self.problems) > before:
            return name, None
        return name, ClassBox(name, kind, stereotype, literals, attributes, operations, left, top, width, height)

    # -------- 관계

    def relation(self, v, path: str) -> tuple[Optional[str], Optional[str], Optional[Relation]]:
        """(읽은 from, 읽은 to, 관계). 다른 필드가 틀려 관계가 None이어도 from·to가 없는 상자를 가리키는지는 함께 알리려고
        두 이름을 따로 돌려준다."""
        before = len(self.problems)
        o = self.obj(v, path, RELATION_FIELDS, ("kind", "from", "to"))
        if o is None:
            return None, None, None
        kind = self.choice(o["kind"], _at(path, "kind"), RELATION_KINDS) if "kind" in o else None
        source = self.text(o["from"], _at(path, "from"), name=True) if "from" in o else None
        target = self.text(o["to"], _at(path, "to"), name=True) if "to" in o else None
        name = self.text(o["name"], _at(path, "name")) if "name" in o else None
        association = kind in ASSOCIATIONS
        mults = []
        for key in ("from_multiplicity", "to_multiplicity"):
            if key in o and kind is not None and not association:
                self.fail(_at(path, key), f"다중도는 연관·집합·합성에만 쓴다(이 관계는 {kind!r})")
            mults.append(self.text(o[key], _at(path, key)) if key in o and association else None)
        navigable = None
        if association:
            navigable = self.choice(o["navigable"], _at(path, "navigable"), NAVIGABLE) if "navigable" in o else "to"
            if kind != "association" and navigable in ("from", "both"):
                self.fail(_at(path, "navigable"), "집합·합성은 마름모가 있는 from 쪽에 화살촉을 둘 수 없다 — 'to'나 'none'을 쓴다")
        elif "navigable" in o and kind is not None:
            self.fail(_at(path, "navigable"), f"방향은 연관·집합·합성에만 쓴다(이 관계는 {kind!r} — 화살촉은 늘 to 쪽이다)")
        via = []
        for i, p in enumerate(self.items(o["via"], _at(path, "via")) if "via" in o else []):
            q = self.point(p, _at(_at(path, "via"), i))
            if q is not None and via and q == via[-1]:
                self.fail(_at(_at(path, "via"), i), f"앞 꺾는 점과 같다 {q}")
            via.append(q)
        if source is not None and source == target and len(via) < 2:
            self.fail(path, "자기 자신으로 가는 관계는 꺾는 점(via)이 둘 이상 있어야 고리로 그릴 수 있다")
        if len(self.problems) > before:
            return source, target, None
        return source, target, Relation(kind, source, target, name, mults[0], mults[1], navigable, tuple(via))

    def diagram(self, data) -> Optional[Diagram]:
        o = self.obj(data, "", ("classes", "relations"), ("classes",))
        if o is None:
            return None
        raw_classes = self.items(o["classes"], "classes") if "classes" in o else []
        if "classes" in o and isinstance(o["classes"], (list, tuple)) and not raw_classes:
            self.fail("classes", "상자가 하나 이상 있어야 한다")
        read = [self.class_box(v, _at("classes", i)) for i, v in enumerate(raw_classes)]
        seen: dict[str, int] = {}
        for i, (name, _) in enumerate(read):
            if name is None:
                continue
            if name in seen:
                self.fail(_at(_at("classes", i), "name"),
                          f"classes[{seen[name]}]와 이름이 같다 — 관계가 이름으로 상자를 가리키므로 이름은 달라야 한다")
            else:
                seen[name] = i
        known = ", ".join(_show(n) for n in list(seen)[:20]) + (" …" if len(seen) > 20 else "")
        relations = []
        for i, v in enumerate(self.items(o["relations"], "relations") if "relations" in o else []):
            path = _at("relations", i)
            source, target, r = self.relation(v, path)
            missing = [(key, n) for key, n in (("from", source), ("to", target)) if n is not None and n not in seen]
            for key, n in missing:
                self.fail(_at(path, key), f"이름이 {_show(n)}인 상자가 없다(있는 상자: {known or '없음'})")
            if r is not None and not missing:
                relations.append(r)
        return Diagram(tuple(c for _, c in read if c is not None), tuple(relations))


def parse(data: Any) -> Diagram:
    """JSON(을 읽은 파이썬 값)을 클래스도 모델로 읽는다. 틀린 곳이 있으면 모두 모아 InputError."""
    reader = _Reader()
    diagram = reader.diagram(data)
    if reader.problems:
        raise InputError(reader.problems)
    assert diagram is not None
    return diagram


# ---------------------------------------------------------------- 자리 잡기


def _section_height(rows: tuple[Row, ...]) -> float:
    return SECTION_PAD + sum(_pitch(r) for r in rows)


def _pitch(row: Row) -> float:
    return ROW + (STATIC_PAD if row.static else 0)


def head_height(box: ClassBox) -> float:
    return HEAD + (NAME_LINE if box.keyword else 0) + NAME_LINE * (len(box.name_lines) - 1)


def fit(box: ClassBox) -> tuple[float, float]:
    """상자 크기: 글자가 다 들어가는 크기와 입력의 최소 크기(width·height, 폭은 없으면 MIN_WIDTH) 가운데 큰 쪽."""
    names = box.name_lines
    widths = [T.text_width(names[0], True) + NAME_PAD] + [T.text_width(s) + NAME_PAD for s in names[1:]]
    if box.keyword:
        widths.append(T.text_width(box.keyword) + NAME_PAD)
    widths += [T.text_width(r.text) + ROW_PAD for rows in box.sections for r in rows]
    need_h = head_height(box) + sum(_section_height(rows) for rows in box.sections) + BOTTOM
    return max(box.min_width, math.ceil(max(widths))), max(box.min_height, need_h)


def _exit(rect: T.Box, inside: Point, toward: Point) -> Optional[Point]:
    """상자 안 inside에서 toward로 가는 선이 상자 변과 만나는 점. toward가 상자 안이나 변 위면 None."""
    (x1, y1), (x2, y2) = inside, toward
    l, t, r, b = rect
    ks = []
    if x2 != x1:
        ks.append(((r if x2 > x1 else l) - x1) / (x2 - x1))
    if y2 != y1:
        ks.append(((b if y2 > y1 else t) - y1) / (y2 - y1))
    if not ks or min(ks) >= 1:
        return None
    k = min(ks)
    return x1 + (x2 - x1) * k, y1 + (y2 - y1) * k


def _center(rect: T.Box) -> Point:
    return (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2


def name_spots(points: tuple[Point, ...], text: str) -> list[Point]:
    """이름 글자 가운데의 후보: 가장 긴 구간(길이가 같으면 앞 구간)의 가운데에서, 진행 방향의 왼쪽(오른쪽으로 가는
    가로선이면 위)과 오른쪽으로 글자 상자가 선과 NAME_GAP만큼 떨어지는 자리. 꺾는 점에서 먼 곳이라 다른 구간에 덜 걸린다."""
    k = max(range(len(points) - 1), key=lambda j: (math.dist(points[j], points[j + 1]), -j))
    (x1, y1), (x2, y2) = points[k], points[k + 1]
    ln = math.dist(points[k], points[k + 1])
    ux, uy = (x2 - x1) / ln, (y2 - y1) / ln
    b = T.place(0, 0, text, False, "mm").box
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


def _gap(a: T.Box, b: T.Box) -> float:
    """두 상자 사이 거리. 겹치거나 맞닿으면 -1."""
    dx = max(b[0] - a[2], a[0] - b[2], 0)
    dy = max(b[1] - a[3], a[1] - b[3], 0)
    return -1 if dx == 0 and dy == 0 else math.hypot(dx, dy)


def _grow(rect: T.Box, m: float) -> T.Box:
    return rect[0] - m, rect[1] - m, rect[2] + m, rect[3] + m


def _hits(p: Point, q: Point, rect: T.Box) -> bool:
    """선분 pq가 상자 rect를 지나거나 닿는지."""
    lo, hi = 0.0, 1.0
    for a, d, low, high in ((p[0], q[0] - p[0], rect[0], rect[2]), (p[1], q[1] - p[1], rect[1], rect[3])):
        if d == 0:
            if not low <= a <= high:
                return False
            continue
        t1, t2 = sorted(((low - a) / d, (high - a) / d))
        lo, hi = max(lo, t1), min(hi, t2)
        if lo > hi:
            return False
    return True


def _meets(a: T.Box, b: T.Box) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _outline_segments(records) -> list[tuple[Point, Point]]:
    """그림판 기록의 선·다각형 테두리를 선분으로."""
    out: list[tuple[Point, Point]] = []
    for r in records:
        if isinstance(r, Line):
            out += zip(r.points, r.points[1:])
        elif isinstance(r, Polygon):
            out += zip(r.points, r.points[1:] + r.points[:1])
    return out


class _Spots:
    """선 글자의 자리를 고른다. 글자의 흰 바탕(글자 상자를 LABEL_CLEAR만큼 넓힌 것)이 상자에 겹치지 않는 자리, 그 가운데
    관계선과 선 끝 모양(화살촉·삼각형·마름모)과 앞서 놓은 선 글자에 닿지 않는 자리, 그 가운데 상자에서 먼(MULT_ENOUGH까지)
    자리가 낫고, 같으면 후보 목록의 앞쪽이다."""

    def __init__(self, boxes: list[T.Box], segments: list[tuple[Point, Point]]):
        self.boxes = boxes
        self.segments = [(p, q, (min(p[0], q[0]), min(p[1], q[1]), max(p[0], q[0]), max(p[1], q[1])))
                         for p, q in segments]
        self.labels: list[T.Box] = []

    def pick(self, text: str, candidates: list[Point]) -> Point:
        boxes = [T.place(x, y, text, False, "mm").box for x, y in candidates]
        wides = [_grow(b, LABEL_CLEAR) for b in boxes]
        region = (min(w[0] for w in wides), min(w[1] for w in wides), max(w[2] for w in wides), max(w[3] for w in wides))
        # 후보들이 닿을 수 있는 것만 먼저 거른다. 상자는 MULT_ENOUGH 밖이면 점수가 같아 거리를 잴 필요가 없다.
        near_boxes = [b for b in self.boxes if _meets(b, _grow(region, MULT_ENOUGH))]
        near_segments = [(p, q) for p, q, bb in self.segments if _meets(bb, region)]
        near_labels = [x for x in self.labels if _meets(x, region)]
        best = None
        for p, box, wide in zip(candidates, boxes, wides):
            gap = min((_gap(wide, b) for b in near_boxes), default=MULT_ENOUGH)
            clear = not any(_hits(a, b, wide) for a, b in near_segments) and all(_gap(wide, x) >= 0 for x in near_labels)
            score = (gap >= 0, clear, min(gap, MULT_ENOUGH))
            if best is None or score > best[0]:
                best = score, p, box
        assert best is not None
        self.labels.append(best[2])
        return best[1]


def shape_lengths(r: Relation) -> tuple[float, float]:
    """선 처음(from)과 끝(to)에 그리는 모양이 선을 따라 차지하는 길이."""
    if r.kind in ("generalization", "realization"):
        return 0, TRIANGLE[0]
    if r.kind == "dependency":
        return 0, ARROW
    start = DIAMOND if r.kind != "association" else ARROW if r.navigable in ("from", "both") else 0
    return start, ARROW if r.navigable in ("to", "both") else 0


def _route(r: Relation, a: T.Box, b: T.Box, path: str) -> tuple[Optional[tuple[Point, ...]], list[str]]:
    """관계선의 점들(선 끝은 상자 가운데에서 첫·마지막 꺾는 점으로, 꺾는 점이 없으면 다른 상자 가운데로 가는 선이 상자
    변과 만나는 곳)과, 그렇게 그을 수 없으면 그 까닭들."""
    ca, cb = _center(a), _center(b)
    if r.via:
        start, end = _exit(a, ca, r.via[0]), _exit(b, cb, r.via[-1])
        problems = [f"{_at(_at(path, 'via'), j)}: 꺾는 점 {r.via[j]}이 {key} 상자 {_show(name)}({_fmt_rect(rect)}) 안이나 "
                    "변 위에 있다 — 상자 밖으로 옮긴다"
                    for p, rect, name, j, key in ((start, a, r.source, 0, "from"), (end, b, r.target, len(r.via) - 1, "to"))
                    if p is None]
        if problems:
            return None, problems
    else:
        start, end = _exit(a, ca, cb), _exit(b, cb, ca)
        if start is None or end is None or (end[0] - start[0]) * (cb[0] - ca[0]) + (end[1] - start[1]) * (cb[1] - ca[1]) <= 0:
            return None, [f"{path}: 상자 {_show(r.source)}와 {_show(r.target)}가 겹치거나 맞닿아 둘 사이에 선을 그을 자리가 없다 — "
                          "떼어 놓거나 상자 밖을 도는 꺾는 점(via)을 준다"]
    assert start is not None and end is not None
    points = (start, *r.via, end)
    if start == end:
        return None, [f"{path}: 선의 두 끝이 같은 점 {start}이다 — 첫·마지막 꺾는 점을 상자의 다른 쪽으로 옮긴다"]
    problems = []
    # 선 끝은 상자 변 위에 있으므로, 변에서 EDGE_SLACK 안쪽으로 줄인 상자를 지나면 선이 끝 상자 안으로 들어간 것이다.
    # 상자가 선 위에 그려져 그 부분은 가려지므로 선이 엉뚱한 변에서 시작하는 것처럼 보인다.
    for key, rect, name in (("from", a, r.source),) + ((("to", b, r.target),) if r.target != r.source else ()):
        inner = _grow(rect, -EDGE_SLACK)
        if any(_hits(p, q, inner) for p, q in zip(points, points[1:])):
            problems.append(f"{path}: 선이 {key} 상자 {_show(name)}({_fmt_rect(rect)}) 안을 지난다 — 꺾는 점을 그 상자 밖으로 "
                            "돌린다")
    lengths = [math.dist(p, q) for p, q in zip(points, points[1:])]
    head, tail = shape_lengths(r)
    if len(lengths) == 1 and lengths[0] < head + tail:
        problems.append(f"{path}: 선 길이 {lengths[0]:.1f}가 양 끝 모양 길이({head:g}+{tail:g})보다 짧다 — 상자를 더 떼어 놓는다")
    elif len(lengths) > 1:
        for length, need, key, which in ((lengths[0], head, "from", "첫"), (lengths[-1], tail, "to", "마지막")):
            if length < need:
                problems.append(f"{path}: {key} 쪽 끝 구간 길이 {length:.1f}가 끝 모양 길이({need:g})보다 짧다 — "
                                f"{which} 꺾는 점을 상자에서 더 떼어 놓는다")
    if sum(lengths) > MAX_LINE:
        problems.append(f"{path}: 선 길이 {sum(lengths):.0f}가 {MAX_LINE}을 넘는다 — 상자를 가까이 모은다")
    return (None if problems else points), problems


def layout(diagram: Diagram) -> Layout:
    """상자 크기, 선의 점들, 선 글자 자리를 잡는다. 선을 그을 수 없는 배치면(꺾는 점이 상자 안이다, 두 상자가 겹치거나
    맞닿았다, 끝 구간이 끝 모양보다 짧다 등) 모두 모아 InputError. 선 글자는 관계 순서대로 이름 → from 다중도 → to 다중도
    차례로 놓고, 앞서 놓은 글자를 뒤 글자가 피한다."""
    placed = tuple(PlacedBox(b, *fit(b)) for b in diagram.classes)
    by_name = {p.box.name: p for p in placed}
    problems: list[str] = []
    routes = []
    for i, r in enumerate(diagram.relations):
        points, found = _route(r, by_name[r.source].rect, by_name[r.target].rect, _at("relations", i))
        problems += found
        routes.append(points)
    if problems:
        raise InputError(problems)
    used = set(by_name)
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
        _draw_relation(sketch, p)
    spots = _Spots([p.rect for p in placed], _outline_segments(sketch.records))
    out = []
    for p in bare:
        r, points = p.relation, p.points
        labels = []
        if r.name:
            labels.append(Label("name", r.name, *spots.pick(r.name, name_spots(points, r.name))))
        for role, text, tip, toward in (("from_multiplicity", r.source_multiplicity, points[0], points[1]),
                                        ("to_multiplicity", r.target_multiplicity, points[-1], points[-2])):
            if text:
                labels.append(Label(role, text, *spots.pick(text, multiplicity_spots(tip, toward))))
        out.append(replace(p, labels=tuple(labels)))
    return Layout(placed, tuple(out))


def _fmt_rect(rect: T.Box) -> str:
    return f"{rect[0]:g}, {rect[1]:g}, {rect[2] - rect[0]:g}×{rect[3] - rect[1]:g}"


# ---------------------------------------------------------------- 그리기


def _draw_relation(c: Canvas, r: PlacedRelation) -> None:
    pts, kind, o = r.points, r.relation.kind, r.owner
    c.line(pts, dash=DASH if kind in ("realization", "dependency") else None, owner=o)
    if kind in ("generalization", "realization"):
        c.closed_arrow(pts[-1], pts[-2], filled=False, size=TRIANGLE[0], half=TRIANGLE[1], owner=o)
    elif kind == "dependency":
        c.open_arrow(pts[-1], pts[-2], size=ARROW, owner=o)
    else:
        if kind != "association":
            c.diamond(pts[0], pts[1], filled=kind == "composition", size=DIAMOND, owner=o)
        if r.relation.navigable in ("to", "both"):
            c.open_arrow(pts[-1], pts[-2], size=ARROW, owner=o)
        if r.relation.navigable in ("from", "both"):
            c.open_arrow(pts[0], pts[1], size=ARROW, owner=o)


def _draw_box(c: Canvas, p: PlacedBox) -> None:
    b, o = p.box, p.box.name
    l, t, w = b.left, b.top, p.width
    c.rect(l, t, w, p.height, owner=o)
    y = t + 5
    if b.keyword:
        c.text(l + w / 2, y + 7, b.keyword, anchor="mm", owner=o)
        y += NAME_LINE
    names = b.name_lines
    c.text(l + w / 2, y + 8, names[0], bold=True, anchor="mm", owner=o)
    for s in names[1:]:
        y += NAME_LINE
        c.text(l + w / 2, y + 8, s, anchor="mm", owner=o)
    y = t + head_height(b)
    for rows in b.sections:
        c.line([(l, y), (l + w, y)], owner=o)
        ty = y + SECTION_PAD / 2 + ROW / 2
        for row in rows:
            c.text(l + ROW_LEFT, ty, row.text, owner=o)
            width = T.text_width(row.text)
            if row.static and width > 0:
                c.line([(l + ROW_LEFT, ty + UNDERLINE), (l + ROW_LEFT + width, ty + UNDERLINE)], owner=o)
            ty += _pitch(row)
        y += _section_height(rows)


def draw(diagram: Diagram, scale: float = SCALE) -> Drawing:
    """선 → 상자 → 선 글자 순서로 그린다. 상자를 선 뒤에 그려 선 끝의 화살촉이 상자 변 밑으로 들어가고, 선 글자는 흰
    바탕을 깔아 맨 위에 쓴다."""
    lay = layout(diagram)
    c = Canvas(scale)
    for r in lay.relations:
        _draw_relation(c, r)
    for p in lay.boxes:
        _draw_box(c, p)
    for r in lay.relations:
        for lab in r.labels:
            c.text(lab.x, lab.y, lab.text, anchor="mm", bg=True, owner=r.owner)
    return Drawing(c, lay)


def render(data: Any, scale: float = SCALE) -> Drawing:
    """JSON을 읽어 그린다. PNG는 Drawing.canvas.save(경로)나 to_image()로 얻는다 — 그 배율로 그리기에 그림이 너무 크면
    그 둘이 ValueError를 낸다(canvas.MAX_PIXELS)."""
    return draw(parse(data), scale)
