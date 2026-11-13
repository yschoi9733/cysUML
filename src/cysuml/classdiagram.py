"""클래스도: 클래스 모양(머리 칸과 속성·연산 구획)과 관계 여섯 가지를 정의하고, 공용 엔진(boxdiagram)으로 읽고 그린다.

클래스 모양과 관계 여섯 가지(RELATIONS)는 패키지도처럼 클래스를 함께 그리는 그림도 가져다 쓴다. 상자 안 글자 자리, 선 끝,
다중도 자리는 StarUML이 그리는 모양을 따른 기존 규칙이다.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Optional

from . import boxdiagram as B
from . import text as T
from .boxdiagram import (ARROW, ARROW_HEAD, BOX_WORDS, DASH, DIAMOND, FILLED_DIAMOND, LABEL_CLEAR, MULT_DISTANCES,
                         MULT_ENOUGH, NAME_GAP, OPEN_DIAMOND, TRIANGLE, TRIANGLE_HEAD, Diagram, Drawing, Element, Label,
                         Layout, PlacedBox, RelationType, Shape, Spec, draw, layout, name_spots)
from .canvas import SCALE, Canvas
from .parsing import InputError, Reader
from .parsing import at as _at
from .parsing import show as _show

__all__ = ["ARROW", "CLASS_KINDS", "CLASS_SHAPE", "CLASS_SHAPES", "DIAMOND", "Diagram", "Drawing", "InputError", "LABEL_CLEAR",
           "Label", "Layout", "MIN_WIDTH", "MULT_DISTANCES", "MULT_ENOUGH", "NAME_GAP", "RELATIONS", "SPEC", "TRIANGLE",
           "draw", "layout", "name_spots", "parse", "render"]

CLASS_KINDS = ("class", "abstract", "interface", "enum")
VISIBILITY = ("+", "-", "#", "~", "")
ATTRIBUTE_FIELDS = ("name", "type", "default", "visibility", "static")
OPERATION_FIELDS = ("name", "params", "returns", "visibility", "static")

MIN_WIDTH = 90

# 상자 안 글자 자리(머리 칸은 패키지·노드 등 이름을 머리에 쓰는 모양도 같은 값을 쓴다)
HEAD = 24          # 이름 한 줄짜리 머리 칸 높이
NAME_LINE = 14     # 키워드(«interface» 등)·{abstract}·이름 다음 줄 하나가 머리 칸에 더하는 높이
NAME_PAD = 20      # 머리 칸 글자의 좌우 여백 합
ROW_LEFT = 5
ROW_PAD = 15       # 구획 줄의 왼쪽(ROW_LEFT)·오른쪽 여백 합
ROW = 15           # 구획 줄 간격
STATIC_PAD = 3     # 밑줄 친 줄 뒤는 그만큼 더 띄운다(밑줄이 다음 줄 글자나 구획선에 붙지 않게)
UNDERLINE = 9.5    # 밑줄 높이(글자 가운데 기준) — 글자 아래 끝(+7.3)과 떨어지게
SECTION_PAD = 10   # 구획 하나의 위아래 여백 합(빈 구획은 이 높이만)
BOTTOM = 4


@dataclass(frozen=True)
class Row:
    """구획 안 한 줄(속성·연산·열거 값). static이면 밑줄을 긋는다."""

    text: str
    static: bool = False


@dataclass(frozen=True)
class ClassParts:
    """클래스 모양이 읽는 제 필드."""

    literals: tuple[Row, ...]
    attributes: tuple[Row, ...]
    operations: tuple[Row, ...]


# ---------------------------------------------------------------- 머리 칸(이름을 머리에 쓰는 모양이 함께 쓴다)


def head_lines(keyword: Optional[str], names: tuple[str, ...], more: tuple[str, ...] = ()) -> list[tuple[str, bool]]:
    """머리 칸에 쓰는 (글자, 굵게) 줄: «키워드», 이름 줄(굵게), 그 밖의 줄(more)."""
    return ([(keyword, False)] if keyword else []) + [(s, True) for s in names] + [(s, False) for s in more]


def head_height(lines: list[tuple[str, bool]]) -> float:
    return HEAD + NAME_LINE * (len(lines) - 1)


def head_width(lines: list[tuple[str, bool]]) -> int:
    return math.ceil(max(T.text_width(s, bold) + NAME_PAD for s, bold in lines))


def draw_head(c: Canvas, lines: list[tuple[str, bool]], cx: float, top: float, owner: str) -> None:
    """머리 칸 글자: 첫 줄 가운데가 top + 12(키워드)나 top + 13(이름)이고, 줄마다 NAME_LINE씩 내려간다."""
    y = top + 5
    for i, (s, bold) in enumerate(lines):
        if i:
            y += NAME_LINE
        c.text(cx, y + (8 if bold or i else 7), s, bold=bold, anchor="mm", owner=owner)


# ---------------------------------------------------------------- 클래스 모양


def _member(r: Reader, v, path: str, operation: bool) -> Optional[Row]:
    """문자열이면 그 글자를 그대로 한 줄로 쓰고, 객체면 보이기(+·-·#·~)·이름·형·기본값·인자를 이어 쓴다."""
    if isinstance(v, str):
        s = r.text(v, path)
        return None if s is None else Row(s)
    before = len(r.problems)
    o = r.obj(v, path, OPERATION_FIELDS if operation else ATTRIBUTE_FIELDS, ("name",))
    if o is None:
        return None

    def part(key: str) -> Optional[str]:
        return r.text(o[key], _at(path, key)) if key in o else None

    name = part("name")
    visibility = r.choice(o["visibility"], _at(path, "visibility"), VISIBILITY) if "visibility" in o else (
        "+" if operation else "-")
    static = r.flag(o["static"], _at(path, "static")) if "static" in o else False  # type: ignore[attr-defined]
    if operation:
        params = [r.text(p, _at(_at(path, "params"), i))
                  for i, p in enumerate(r.items(o["params"], _at(path, "params")) if "params" in o else [])]
        returns = part("returns")
        if len(r.problems) > before:
            return None
        return Row(f"{visibility}{name}({', '.join(params)})" + (f": {returns}" if returns else ""), static)  # type: ignore[arg-type]
    type_, default = part("type"), _default(r, o["default"], _at(path, "default")) if "default" in o else None
    if len(r.problems) > before:
        return None
    return Row(f"{visibility}{name}" + (f": {type_}" if type_ else "") + (f" = {default}" if default else ""), static)


def _default(r: Reader, v, path: str) -> Optional[str]:
    """속성 기본값. 문자열은 다른 글자처럼 비어 있지 않아야 하고(빈 문자열 값은 "\\"\\""로 쓴다), 수와 참거짓은 JSON
    표기(0·0.5·true)로 쓴다."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        if isinstance(v, float) and not math.isfinite(v):
            r.fail(path, f"유한한 수여야 한다(받은 값 {_show(v)})")
            return None
        try:
            return json.dumps(v)
        except ValueError:
            r.fail(path, f"수가 너무 크다(받은 값 {_show(v)})")
            return None
    if not isinstance(v, str):
        r.fail(path, f"문자열이나 수, true·false여야 한다(받은 값 {_show(v)})")
        return None
    return r.text(v, path)


def _rows(r: Reader, o: dict, key: str, path: str, operation: bool) -> tuple[Row, ...]:
    out = []
    for i, v in enumerate(r.items(o[key], _at(path, key)) if key in o else []):
        row = _member(r, v, _at(_at(path, key), i), operation)
        if row is not None:
            out.append(row)
    return tuple(out)


def _section_height(rows: tuple[Row, ...]) -> float:
    return SECTION_PAD + sum(_pitch(r) for r in rows)


def _pitch(row: Row) -> float:
    return ROW + (STATIC_PAD if row.static else 0)


class ClassShape(Shape):
    """클래스(class·abstract·interface·enum): 머리 칸(키워드·이름·{abstract})과 속성·연산(열거형은 열거 값) 구획."""

    fields = ("attributes", "operations", "literals")
    default_width = MIN_WIDTH

    def read(self, r: Reader, o: dict, path: str, kind: Optional[str]) -> ClassParts:
        literals: tuple[Row, ...] = ()
        if "literals" in o and kind == "enum":
            found = [r.text(s, _at(_at(path, "literals"), i)) for i, s in enumerate(r.items(o["literals"], _at(path, "literals")))]
            literals = tuple(Row(s) for s in found if s is not None)
        elif "literals" in o and kind is not None:
            r.fail(_at(path, "literals"), f"열거 값은 kind가 'enum'인 상자에만 쓴다(이 상자는 {kind!r})")
        return ClassParts(literals, _rows(r, o, "attributes", path, operation=False),
                          _rows(r, o, "operations", path, operation=True))

    def keyword(self, e: Element) -> Optional[str]:
        words = {"interface": ["interface"], "enum": ["enumeration"]}.get(e.kind, [])
        repeats = {"interface": ("interface",), "enum": ("enumeration", "enum"), "abstract": ("abstract",)}
        if e.stereotype and e.stereotype.casefold() not in repeats.get(e.kind, ()):
            words.append(e.stereotype)
        return f"«{', '.join(words)}»" if words else None

    def head(self, e: Element) -> list[tuple[str, bool]]:
        """추상 클래스는 기울인 글꼴을 넣지 않았으므로 UML의 다른 표기 {abstract}를 이름 아래에 쓴다."""
        return head_lines(self.keyword(e), e.name, ("{abstract}",) if e.kind == "abstract" else ())

    def sections(self, e: Element) -> tuple[tuple[Row, ...], ...]:
        """그리는 구획. 클래스는 비어도 속성·연산 구획을 그리고, 인터페이스·열거형은 빈 구획을 숨긴다(열거 값 구획은 그린다)."""
        d: ClassParts = e.data
        if e.kind in ("class", "abstract"):
            return d.attributes, d.operations
        out = [d.literals] if e.kind == "enum" else []
        return tuple(out + [rows for rows in (d.attributes, d.operations) if rows])

    def size(self, e: Element) -> tuple[float, float]:
        head = self.head(e)
        widths = [head_width(head)] + [math.ceil(T.text_width(r.text) + ROW_PAD) for rows in self.sections(e) for r in rows]
        return max(widths), head_height(head) + sum(_section_height(rows) for rows in self.sections(e)) + BOTTOM

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        e, o = p.box, p.key
        l, t, w = p.rect[0], p.rect[1], p.width
        c.rect(l, t, w, p.height, owner=o)
        head = self.head(e)
        draw_head(c, head, l + w / 2, t, o)
        y = t + head_height(head)
        for rows in self.sections(e):
            c.line([(l, y), (l + w, y)], owner=o)
            ty = y + SECTION_PAD / 2 + ROW / 2
            for row in rows:
                c.text(l + ROW_LEFT, ty, row.text, owner=o)
                width = T.text_width(row.text)
                if row.static and width > 0:
                    c.line([(l + ROW_LEFT, ty + UNDERLINE), (l + ROW_LEFT + width, ty + UNDERLINE)], owner=o)
                ty += _pitch(row)
            y += _section_height(rows)


CLASS_SHAPE = ClassShape()
CLASS_SHAPES = {kind: CLASS_SHAPE for kind in CLASS_KINDS}

RELATIONS = {
    "association": RelationType("연관", navigable=True, multiplicity=True),
    "aggregation": RelationType("집합", start=OPEN_DIAMOND, navigable=True, multiplicity=True),
    "composition": RelationType("합성", start=FILLED_DIAMOND, navigable=True, multiplicity=True),
    "generalization": RelationType("상속", end=TRIANGLE_HEAD, trunk=True),
    "realization": RelationType("실체화", dash=DASH, end=TRIANGLE_HEAD, trunk=True),
    "dependency": RelationType("의존", dash=DASH, end=ARROW_HEAD),
}

SPEC = Spec(CLASS_SHAPES, RELATIONS, BOX_WORDS, list_field="classes", default_kind="class", navigable="to", extended=False)


def parse(data: Any) -> Diagram:
    """JSON(을 읽은 파이썬 값)을 클래스도 모델로 읽는다. 틀린 곳이 있으면 모두 모아 InputError."""
    return B.parse(SPEC, data)


def render(data: Any, scale: float = SCALE) -> Drawing:
    """JSON을 읽어 그린다. PNG는 Drawing.canvas.save(경로)나 to_image()로 얻는다 — 그 배율로 그리기에 그림이 너무 크면
    그 둘이 ValueError를 낸다(canvas.MAX_PIXELS)."""
    return B.render(SPEC, data, scale)
