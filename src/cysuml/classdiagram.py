"""클래스도: 클래스 모양(머리 칸과 속성·연산 구획)과 관계 여섯 가지를 정의하고, 공용 엔진(boxdiagram)으로 읽고 그린다.

클래스 모양과 관계 여섯 가지(RELATIONS)와 그 표기 규칙(RULES — 상속은 같은 종류끼리 등)은 패키지도처럼 클래스를 함께 그리는
그림도 가져다 쓴다. 상자 안 글자 자리, 선 끝, 다중도 자리는 StarUML이 그리는 모양을 따른 기존 규칙이다.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, NamedTuple, Optional

from . import boxdiagram as B
from . import text as T
from .boxdiagram import (ARROW, ARROW_HEAD, BOX_WORDS, DASH, DIAMOND, FILLED_DIAMOND, LABEL_CLEAR, MULT_DISTANCES,
                         MULT_ENOUGH, NAME_GAP, OPEN_DIAMOND, TRIANGLE, TRIANGLE_HEAD, Diagram, Drawing, Element, Label,
                         Layout, PlacedBox, RelationType, Rules, Shape, Spec, draw, layout, name_spots)
from .canvas import SCALE, Canvas
from .parsing import InputError, Reader
from .parsing import at as _at
from .parsing import show as _show
from .report import Notice

__all__ = ["ARROW", "CLASS_KINDS", "CLASS_SHAPE", "CLASS_SHAPES", "DIAMOND", "Diagram", "Drawing", "InputError", "LABEL_CLEAR",
           "Label", "Layout", "MIN_WIDTH", "MULT_DISTANCES", "MULT_ENOUGH", "NAME_GAP", "RELATIONS", "RULES", "SPEC", "TRIANGLE",
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
    static = r.flag(o["static"], _at(path, "static")) if "static" in o else False
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
    "generalization": RelationType("상속", end=TRIANGLE_HEAD, trunk=True, role="자식", reflexive=False),
    "realization": RelationType("실체화", dash=DASH, end=TRIANGLE_HEAD, trunk=True, role="구현하는 쪽", reflexive=False),
    "dependency": RelationType("의존", dash=DASH, end=ARROW_HEAD, role="의존하는 쪽"),
}

# ---------------------------------------------------------------- 관계 규칙(이 관계를 받는 도구가 함께 쓴다)

GENERALIZATION, REALIZATION = "generalization", "realization"
SAME_KIND = {"abstract": "class",  # 상속에서 같은 종류로 치는 요소 종류 → 그 기본 종류
             "component_icon": "component", "artifact_icon": "artifact"}  # 아이콘 표기는 같은 요소를 다르게 그린 것이다
ICONS = ("component_icon", "artifact_icon")
NOT_INHERITED = {  # 상속의 끝이 될 수 없는 요소 종류 → (부르는 말, 고치는 법)
    "package": ("패키지", "패키지가 끝인 관계는 dependency로 긋는다(패키지 사이 «import» 등은 stereotype으로 단다)"),
    "lollipop": ("제공 인터페이스 원", "인터페이스 사이 상속은 kind 'interface' 상자끼리 긋는다"),
}
INTERFACES = ("interface", "lollipop")  # 실체화의 from이 되면 알리는 종류(인터페이스는 다른 것을 구현하지 않는다)


class Realized(NamedTuple):
    """실체화가 가도 알리지 않는 요소 종류의 정의. doers는 그 실체화를 해도 되는 종류다 — None이면 INTERFACES와 NOT_INHERITED(이 둘이
    하는 실체화는 늘 알린다) 밖의 모든 종류. meant는 이 종류로 가는 틀린 상속을 실체화로 고치라고 할 때의 앞말, others는 doers 밖의
    종류가 이 종류를 실체화했을 때의 고치는 법이다."""

    doers: Optional[tuple[str, ...]]
    meant: str
    others: str = ""


REALIZED = {
    "interface": Realized(None, "인터페이스를 구현하는 것이면"),
    "lollipop": Realized(None, "인터페이스를 구현하는 것이면"),
    "component": Realized(("class", "abstract"), "클래스가 컴포넌트를 실현하는 것이면",
                          "컴포넌트를 실현하는 것은 클래스다 — 아티팩트가 컴포넌트를 구현하는 것이면 dependency에 stereotype "
                          "'manifest'를 달고, 다른 뜻이면 dependency를 쓴다."),
}
REALIZED["component_icon"] = REALIZED["component"]  # 아이콘 표기 컴포넌트도 클래스가 실현한다


def _end(side: str, key: str, kind: str) -> str:
    """오류·알림 글에서 관계의 한 끝: from 'Circle': 'class'. 이름 바로 뒤에 조사를 붙이지 않는다(영어 이름은 받침을 알 수 없다)."""
    return f"{side} {_show(key)}: {kind!r}"


def _same_kind(a: str, b: str) -> bool:
    return SAME_KIND.get(a, a) == SAME_KIND.get(b, b)


def _realizable(s: str, t: str) -> bool:
    """s 종류가 t 종류로 가는 실체화가 알림 없이 받아지는지 — 고치는 법이 실체화를 권하거나 방향을 바꾸라고 할 때 그대로 따라도
    다시 걸리지 않는지 본다."""
    if s in INTERFACES or s in NOT_INHERITED or t not in REALIZED:
        return False
    doers = REALIZED[t].doers
    return doers is None or s in doers


def _elsewhere(spec: Spec, s: str, t: str) -> str:
    """실체화를 상속으로 고칠 수 없을 때의 고치는 법: 실체화를 긋는 자리와, 방향을 바꾸면 받아지면 바꾸라는 말(아니면 의존을 쓰라는 말)."""
    where = "실체화는 인터페이스를 구현하는 쪽에서 인터페이스로" + (", 클래스에서 그 클래스가 실현하는 컴포넌트로"
                                                      if "component" in spec.shapes else "") + " 긋는다"
    return f"{where} — " + ("방향이 거꾸로면 from과 to를 바꾼다." if _realizable(t, s) else "다른 뜻이면 dependency를 쓴다.")


def _cycle(parents: dict[str, list[str]], start: str, goal: str) -> Optional[list[str]]:
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


class ClassRules(Rules):
    """클래스도 관계 여섯 가지(RELATIONS)의 표기 규칙. 이 관계를 받는 패키지도·컴포넌트도·배치도(deployment diagram)도 함께
    쓴다.

    입력 오류(그리지 않는다): 두 끝 종류가 다른 상속(class와 abstract는 같은 종류), 패키지·제공 인터페이스 원이 끝인 상속, 고리를
    이루는 상속(여러 단계도). 자기 자신으로 가는 상속·실체화는 관계 종류가 막는다(RELATIONS의 reflexive). 알림(그린다): 인터페이스·
    제공 인터페이스 원·패키지가 하는 실체화와, 인터페이스·제공 인터페이스 원이 아닌 요소로 가는 실체화(클래스·추상 클래스가
    컴포넌트를 실현하는 것은 빼고) — 그 컴포넌트 실현처럼 인터페이스가 아닌 것으로 가는 맞는 쓰임이 있어 막지 않는다. 오류·알림의
    고치는 법은 그대로 따랐을 때 다시 걸리지 않게 두 끝 종류와 이미 있는 상속에 맞춘다."""

    def check(self, r: Reader, spec: Spec, elements: list[tuple[str, Element]],
              relations: list[tuple[str, B.Relation]]) -> list[Notice]:
        kinds = {e.key: e.kind for _, e in elements}
        parents: dict[str, list[str]] = {}  # 오류 없는 상속(자식 → 부모들)
        inherits: list[tuple[str, B.Relation]] = []
        realizations: list[tuple[str, B.Relation, str, str]] = []
        realized = {(rel.source, rel.target) for _, rel in relations if rel.kind == REALIZATION}
        for path, rel in relations:
            s, t = kinds.get(rel.source), kinds.get(rel.target)
            if s is None or t is None or rel.source == rel.target:
                continue
            if rel.kind == GENERALIZATION:
                if self._generalization(r, spec, path, rel, s, t, realized):
                    parents.setdefault(rel.source, []).append(rel.target)
                    inherits.append((path, rel))
            elif rel.kind == REALIZATION:
                realizations.append((path, rel, s, t))
        loops: set[frozenset[tuple[str, str]]] = set()
        for path, rel in inherits:
            back = _cycle(parents, rel.target, rel.source)
            if back is None:
                continue
            ring = [rel.source, *back]
            edges = frozenset(zip(ring, ring[1:]))
            if edges in loops:  # 고리(그 고리를 이루는 상속들)마다 입력에서 먼저 나온 상속에서 한 번 알린다
                continue
            loops.add(edges)
            r.fail(path, f"상속이 고리를 이룬다({' → '.join(_show(k) for k in ring)}) — 조상을 다시 상속할 수 없다. 고리 안의 "
                         "상속 하나를 지우거나 from·to를 바꾼다")
        found = (self._realization(spec, parents, *x) for x in realizations)  # 알림의 고치는 법이 상속 전부를 보고 고른다
        return [n for n in found if n is not None]

    @staticmethod
    def _generalization(r: Reader, spec: Spec, path: str, rel: B.Relation, s: str, t: str,
                        realized: set[tuple[str, str]]) -> bool:
        """상속의 두 끝 종류를 본다. 맞으면 True, 틀렸으면 알리고 False. 실체화를 뜻했을 수 있으면(그 실체화가 알림 없이 받아지면)
        실체화로 고치라고 하되, 그 실체화가 이미 있으면(realized — 실체화의 (from, to)) 선이 겹치니 이 상속을 지우라고 한다."""
        if _realizable(s, t):
            fix = ("같은 from·to의 realization이 이미 있다 — 이 상속을 지운다" if (rel.source, rel.target) in realized
                   else f"{REALIZED[t].meant} kind를 'realization'으로 바꾼다")
        elif _realizable(t, s):  # 인터페이스 -> 클래스처럼 실체화를 거꾸로 적었을 수 있다
            fix = ("거꾸로 가는 realization이 이미 있다 — 이 상속을 지운다" if (rel.target, rel.source) in realized
                   else "방향이 거꾸로인 실체화를 뜻했으면 from과 to를 바꾸고 kind를 'realization'으로 바꾼다")
        else:
            fix = None
        for key, kind in ((rel.source, s), (rel.target, t)):
            if kind in NOT_INHERITED:
                name, default = NOT_INHERITED[kind]
                r.fail(path, f"{name}({_show(key)}){B.josa(name, '은', '는')} 상속의 끝이 될 수 없다 — {fix or default}")
                return False
        if _same_kind(s, t):
            return True
        icons = "·".join(k for k in ICONS if k in spec.shapes)
        same = "class와 abstract는 같은 종류로 친다" + (f", 아이콘 표기({icons})도 기본 표기와 같은 종류로 친다" if icons else "")
        r.fail(path, f"상속의 두 끝 종류가 다르다({_end('from', rel.source, s)}, {_end('to', rel.target, t)}) — 상속은 같은 "
                     f"종류끼리 긋는다({same}). {fix or 'from·to나 요소의 kind를 고친다'}")
        return False

    @staticmethod
    def _realization(spec: Spec, parents: dict[str, list[str]], path: str, rel: B.Relation, s: str,
                     t: str) -> Optional[Notice]:
        """실체화의 두 끝 종류를 본다(from 쪽부터). 알릴 것이 없으면 None. 상속으로 바꾸라는 말은 두 끝이 같은 종류이고, 바꿔도
        고리가 생기지 않을 때만 한다(parents는 오류 없는 상속 — to가 이미 from을 상속하면 고리가 된다)."""
        def blocked() -> Optional[str]:
            """이 실체화를 상속으로 바꾸면 안 되는 까닭 — 같은 상속이 이미 있거나(겹쳐 그린다), to가 이미 from을 상속한다(고리)."""
            if rel.target in parents.get(rel.source, ()):
                return "같은 from·to의 generalization이 이미 있다"
            if _cycle(parents, rel.target, rel.source) is not None:
                return (f"to({_show(rel.target)})가 이미 from({_show(rel.source)})을 상속해 generalization으로 바꾸면 고리가 "
                        "된다")
            return None

        if s in INTERFACES:
            problem = f"실체화를 하는 쪽이 인터페이스다({_end('from', rel.source, s)})."
            if s == t == "interface":
                why = blocked()
                hint = f"{why} — 이 실체화를 지운다." if why else "인터페이스끼리는 kind를 'generalization'으로 바꾼다."
            else:
                hint = _elsewhere(spec, s, t)
        elif s in NOT_INHERITED:
            name, fix = NOT_INHERITED[s]
            problem, hint = f"{name}({_show(rel.source)}){B.josa(name, '은', '는')} 실체화하지 않는다.", f"{fix}."
        elif t in REALIZED and not _realizable(s, t) and not _same_kind(s, t):  # 하는 쪽 종류가 아니다(아티팩트 -> 컴포넌트)
            problem = f"실체화를 하는 쪽이 to를 실현하지 않는 종류다({_end('from', rel.source, s)}, {_end('to', rel.target, t)})."
            hint = REALIZED[t].others or _elsewhere(spec, s, t)
        elif not _realizable(s, t):
            problem = f"실체화가 가는 쪽이 인터페이스가 아니다({_end('to', rel.target, t)})."
            if not _same_kind(s, t):
                hint = _elsewhere(spec, s, t)
            elif why := blocked():
                hint = f"{why} — 인터페이스를 구현하는 것이면 to를 인터페이스로 고치고, 아니면 이 실체화를 지운다."
            else:
                hint = "상속을 뜻했으면 kind를 'generalization'으로 바꾸고, 인터페이스를 구현하는 것이면 to를 인터페이스로 고친다."
        else:
            return None
        return Notice(path, (rel.source, rel.target), problem, hint)

    def guide(self, spec: Spec) -> str:
        """따옴표 친 종류 이름 바로 뒤에는 받침에 따라 갈리는 조사(은·는·이·가·을·를·으로·로)를 붙이지 않는다(_end와 같은 까닭).
        서술하는 '이고'·'인'은 어느 말 뒤에도 쓸 수 있어 괜찮다."""
        def quoted(kinds) -> str:
            return "·".join(f'"{k}"' for k in dict.fromkeys(kinds) if k in spec.shapes)

        families: dict[str, list[str]] = {}  # 같은 종류로 치는 것끼리 — 기본 종류 → 그 종류들(도구가 받는 차례)
        for k in spec.shapes:
            if k not in NOT_INHERITED:
                families.setdefault(SAME_KIND.get(k, k), []).append(k)
        groups = ", ".join(f"{quoted(ks)}끼리" for ks in families.values())
        never = quoted(NOT_INHERITED)
        quiet = quoted(k for k, d in REALIZED.items() if d.doers is None)
        limited: dict[tuple[str, ...], list[str]] = {}  # 하는 쪽이 정해진 대상들 — 하는 쪽 종류 → 대상 종류들
        for k, d in REALIZED.items():
            if d.doers is not None and k in spec.shapes:
                limited.setdefault(d.doers, []).append(k)
        but = "".join(f"(to가 {quoted(ks)}{' 가운데 하나' if len(ks) > 1 else ''}이고 from이 {quoted(by)}인 것은 빼고)"
                      for by, ks in limited.items())
        doers = quoted((*INTERFACES, *NOT_INHERITED))
        doers += " 가운데 하나" if "·" in doers else ""
        return "\n".join([
            f"  - 규칙: 상속은 같은 종류끼리 긋는다({groups})." + (f" 상속의 끝이 될 수 없는 종류: {never}." if never else "")
            + " 클래스가 인터페이스를 구현하는 것은 realization이다. 종류가 다른 상속, 고리를 이루는 상속(A가 B를, B가 다시 A를 "
            "상속하는 것 — 여러 단계도)은 입력 오류다.",
            f"  - 알림: 다음 실체화는 그리되 검사 결과에 알림을 준다(불합격이 아니다) — from이 {doers}인 것, to가 {quiet} 밖의 "
            f"종류인 것{but}. 상속 등 다른 관계를 뜻했는지 확인하고, 뜻한 대로면 그대로 둔다."])


RULES = ClassRules()

SPEC = Spec(CLASS_SHAPES, RELATIONS, BOX_WORDS, list_field="classes", default_kind="class", navigable="to", extended=False,
            rules=RULES)


def parse(data: Any) -> Diagram:
    """JSON(을 읽은 파이썬 값)을 클래스도 모델로 읽는다. 틀린 곳이 있으면 모두 모아 InputError."""
    return B.parse(SPEC, data)


def render(data: Any, scale: float = SCALE) -> Drawing:
    """JSON을 읽어 그린다. PNG는 Drawing.canvas.save(경로)나 to_image()로 얻는다 — 그 배율로 그리기에 그림이 너무 크면
    그 둘이 ValueError를 낸다(canvas.MAX_PIXELS)."""
    return B.render(SPEC, data, scale)
