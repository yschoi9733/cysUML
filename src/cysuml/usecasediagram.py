"""유즈케이스도: 액터·유즈케이스·시스템 경계와 그 사이의 연관·의존(«include»·«extend»)·일반화를 그린다.

액터는 교류도와 같은 사람 모양(sequencediagram.draw_actor)에 이름을 모양 밖에 쓰고, 유즈케이스는 이름을 안 가운데에 쓴 타원,
시스템 경계는 이름을 위쪽 가운데에 쓰고 안에 유즈케이스를 두는 사각형이다. 읽기·자리 잡기·그리기는 공용 엔진(boxdiagram),
검사는 공용 검사(boxcheck)가 한다. 요소·관계의 짜임이 UML 표기에 맞는지는 표기 규칙(UseCaseRules)이 읽기 끝에 본다. 도구
설명(TOOL)과 배치 요령(TIPS)도 여기 둔다.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache
from typing import Any, Callable, Optional

from . import boxdiagram as B
from . import text as T
from .boxdiagram import (ELEMENT_WORDS, LABEL_LINE, NEST_PAD, TRIANGLE_HEAD, Diagram, Drawing, Element, NameZone, PlacedBox,
                         RelationType, Rules, Shape, Spec, end_of, ends_of, fail_loops, floored, line_ys,
                         parent_path)
from .canvas import SCALE, Canvas, Point
from .classdiagram import RELATIONS as CLASS_RELATIONS
from .geom import Border, EllipseBorder
from .guide import NAME_SIDE, box_tool, relation_fields, spacing_tips
from .parsing import Reader
from .parsing import at as _at
from .parsing import show as _show
from .report import Notice
from .sequencediagram import ACTOR_FIGURE, draw_actor
from .text import Box

USE_CASE_MIN = (120, 50)  # 유즈케이스 타원의 최소 폭·높이
USE_CASE_PAD = (10, 6)    # 이름 글자 둘레 여백(가로, 세로). 타원은 여백을 더한 글자 상자를 가로·세로 √2배로 덮는다
SYSTEM_NAME_PAD = 5       # 시스템 경계 이름 줄 위아래 여백
SYSTEM_NAME_SIDE = 6      # 시스템 경계 이름 칸이 이름 글자 좌우로 더 차지하는 폭
SYSTEM_BODY = 40          # 비어 있는 시스템 경계에서 이름 칸 밖에 더하는 높이


def _lines_width(lines: tuple[str, ...], bold: bool = False) -> float:
    return math.ceil(max(T.text_width(s, bold) for s in lines))


class ActorShape(Shape):
    """액터: 교류도와 같은 사람 모양. 이름은 모양 밖(name_side, 기본 아래)에 쓰고, 선 끝은 사람 모양을 덮는 사각형 테두리에 닿는다.
    선이 향하는 점은 가운데를 정수로 내린 점이고(boxdiagram.floored — 사람 모양 높이가 홀수거나 사람이 준 폭이 홀수·좌표가 소수여도
    가운데를 맞춘 두 요소의 선이 곧다), 사람 모양도 그 x에 그려 곧게 내려오는 선이 몸 한가운데에 닿는다."""

    outside_name = True
    sized = False
    stereotyped = False

    def size(self, e: Element) -> tuple[float, float]:
        return ACTOR_FIGURE

    def anchor(self, e: Element, rect: Box) -> Point:
        return floored(rect)

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        draw_actor(c, floored(p.shape_rect)[0], p.shape_rect[1], p.key)


def _even(v: float) -> int:
    """v 이상인 가장 작은 짝수."""
    return 2 * math.ceil(v / 2)


@lru_cache(maxsize=4096)
def _ellipse(rect: Box) -> EllipseBorder:
    """자리 사각형에 꼭 맞는 타원 — 테두리와 겹침 조각이 같은 타원(꼭짓점 많은 다각형)을 한 번만 만들게."""
    l, t, r, b = rect
    return EllipseBorder((l + r) / 2, (t + b) / 2, (r - l) / 2, (b - t) / 2)


class UseCaseShape(Shape):
    """유즈케이스: 이름을 안 가운데에 쓴 타원. 여백을 더한 이름 글자 상자를 가로·세로 √2배 하면 그 상자의 네 모서리가 타원 위에
    놓이므로, 타원은 그 크기(최소 USE_CASE_MIN)로 이름을 덮는다. 폭·높이는 짝수로 올려, 정수 좌표에 놓으면 선이 향하는 점
    (boxdiagram.floored)이 타원 가운데와 같다. 선 끝과 겹침은 타원 테두리로 본다."""

    stereotyped = False

    def size(self, e: Element) -> tuple[float, float]:
        w = _lines_width(e.name) + 2 * USE_CASE_PAD[0]
        h = LABEL_LINE * len(e.name) + 2 * USE_CASE_PAD[1]
        return max(USE_CASE_MIN[0], _even(math.sqrt(2) * w)), max(USE_CASE_MIN[1], _even(math.sqrt(2) * h))

    def border(self, e: Element, rect: Box) -> Border:
        return _ellipse(rect)

    def anchor(self, e: Element, rect: Box) -> Point:
        return floored(rect)

    def parts(self, e: Element, rect: Box) -> tuple[Border, ...]:
        """타원 — 자리 사각형의 네 모서리 쪽은 유즈케이스가 아니다."""
        return (_ellipse(rect),)

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        l, t, r, b = p.rect
        c.ellipse(l, t, r - l, b - t, owner=p.key)
        for s, y in zip(p.box.name, line_ys((t + b) / 2, len(p.box.name))):
            c.text((l + r) / 2, y, s, anchor="mm", owner=p.key)


def _system_name_height(lines: int) -> float:
    """이름이 lines줄인 시스템 경계의 이름 칸 높이."""
    return LABEL_LINE * lines + 2 * SYSTEM_NAME_PAD


@lru_cache(maxsize=1024)
def _system_name(name: tuple[str, ...]) -> tuple[float, float]:
    """(이름 칸 폭, 이름 칸 높이). 모양의 메서드마다 쓰므로 글자 폭은 한 번만 잰다."""
    return _lines_width(name, True) + 2 * SYSTEM_NAME_SIDE, _system_name_height(len(name))


class SystemShape(Shape):
    """시스템 경계: 이름(굵게)을 위쪽 가운데에 쓴 사각형. 안에 요소를 두는 칸은 이름 줄 아래이고, 이름 칸은 이름 글자 폭만큼이라
    그 옆으로는 선이 윗변을 건널 수 있다."""

    holds = True
    stereotyped = False

    def _name(self, e: Element) -> tuple[float, float]:
        return _system_name(e.name)

    def size(self, e: Element) -> tuple[float, float]:
        w, h = self._name(e)
        return w + 2 * NEST_PAD, h + SYSTEM_BODY

    def insets(self, e: Element) -> Box:
        return 0.0, self._name(e)[1], 0.0, 0.0

    def name_zones(self, e: Element, rect: Box) -> tuple[NameZone, ...]:
        w, h = self._name(e)
        cx = (rect[0] + rect[2]) / 2
        return (NameZone((cx - w / 2, rect[1], cx + w / 2, rect[1] + h), False),)

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        l, t, r, b = p.rect
        c.rect(l, t, r - l, b - t, owner=p.key)
        h = self._name(p.box)[1]
        for s, y in zip(p.box.name, line_ys(t + h / 2, len(p.box.name))):
            c.text((l + r) / 2, y, s, bold=True, anchor="mm", owner=p.key)


ACTOR = ActorShape()
USE_CASE = UseCaseShape()
SYSTEM = SystemShape()

SHAPES = {"actor": ACTOR, "use_case": USE_CASE, "system": SYSTEM}
RELATIONS = {
    "association": CLASS_RELATIONS["association"],
    "dependency": CLASS_RELATIONS["dependency"],
    "generalization": RelationType("일반화", end=TRIANGLE_HEAD, trunk=True, role="자식", reflexive=False),
}

# ---------------------------------------------------------------- 표기 규칙

STEPS = ("include", "extend")  # 유즈케이스 사이의 의존에만 다는 스테레오타입(대소문자는 가리지 않는다)
KIND_JOSA = {"association": "이", "generalization": "이", "dependency": "가"}  # 관계 종류 이름 뒤 주격 조사(읽는 소리대로)

Edge = tuple[str, str, str, Optional[str]]  # (kind, from, to, 소문자로 맞춘 stereotype)


def _stereo(rel: B.Relation) -> Optional[str]:
    return rel.stereotype.casefold() if rel.stereotype is not None else None


def _step(rel: B.Relation) -> bool:
    return _stereo(rel) in STEPS


def _other(s: str, t: str) -> Optional[str]:
    """시스템 경계가 한 끝인 관계에서 다른 끝의 종류. 두 끝이 다 시스템 경계면 None."""
    return t if s == "system" and t != "system" else s if t == "system" and s != "system" else None


class UseCaseRules(Rules):
    """유즈케이스도의 표기 규칙. 모두 입력 오류다(그리지 않는다) — 알림은 없다.

    액터는 시스템 밖의 사람이나 외부 시스템이라 시스템 경계 안에 두지 않는다(in). 연관은 액터와 유즈케이스 사이에 긋는다 — 시스템
    경계에 닿는 연관, 액터끼리 잇는 연관(UML 명세 Actor 제약: 액터의 연관은 유즈케이스·컴포넌트·클래스로만 간다), 같은 주체의
    유즈케이스끼리 잇는 연관(UseCase 제약: 같은 주체를 가리키는 유즈케이스끼리는 연관을 맺지 않는다 — 주체는 유즈케이스를 품은
    가장 가까운 시스템 경계이고, 둘 다 경계 밖이면 같은 주체로 친다)은 틀렸다. 일반화는 액터끼리, 유즈케이스끼리 긋고 고리를 이루지
    않는다(자기 자신으로 가는 일반화는 관계 종류가 막는다 — RELATIONS의 reflexive). «include»·«extend»는 유즈케이스 사이의 의존에만
    단다. 유즈케이스는 자기 자신을 포함·확장하지 않고, «include»는 고리를 이루지 않는다(UseCase 제약: 저를 바로나 거쳐서 포함하는
    유즈케이스를 포함할 수 없다). «extend»의 고리는 막지 않는다 — 명세에 그런 제약이 없다. 관계 하나에는 오류를 하나만
    알린다(«include»·«extend»를 먼저 본다). 고치는 법은 _Plan이 고른다."""

    def check(self, r: Reader, spec: Spec, elements: list[tuple[str, Element]],
              relations: list[tuple[str, B.Relation]]) -> list[Notice]:
        out, r = r, _InOrder()  # 규칙 오류는 모아 두었다가 입력 차례로 넘긴다
        kinds = {e.key: e.kind for _, e in elements}

        def holds(key: str) -> bool:
            """key가 읽힌 요소이고 안에 요소를 두는 종류인지 — 아니면 그 in은 엔진이 이미 알렸다."""
            return key in kinds and spec.shapes[kinds[key]].holds

        for path, e in elements:
            if e.parent is not None and holds(e.parent) and not self.nests(kinds[e.parent], e.kind):
                r.fail(_at(path, "in"), f"액터는 시스템 경계({_show(e.parent)}) 안에 둘 수 없다 — 액터는 시스템 밖의 사람이나 외부 "
                                        "시스템이다. in을 빼고 시스템 경계 밖(왼쪽이나 오른쪽)에 둔다")
        parent_of = {e.key: e.parent for _, e in elements}

        def subject(key: str) -> tuple[bool, Optional[str]]:
            """(주체를 알 수 있는지, 주체 — 품은 가장 가까운 시스템 경계, 경계 밖이면 None). 품은 쪽의 in이 틀렸으면(읽히지 않은
            요소·품을 수 없는 요소·고리 — 엔진이 이미 알렸다) 알 수 없다."""
            chain = B.ancestors(parent_of, key)
            if parent_of.get(chain[-1] if chain else key) is not None or not all(holds(k) for k in chain):
                return False, None
            return True, next((k for k in chain if kinds[k] == "system"), None)

        plan = _Plan()
        inherits: list[tuple[str, B.Relation]] = []
        includes: list[tuple[str, B.Relation]] = []
        faults: list[tuple[str, str, B.Relation, str, str]] = []
        for path, rel in relations:
            s, t = kinds.get(rel.source), kinds.get(rel.target)
            if s is None or t is None:
                continue
            if (fault := _fault(rel, s, t, subject)) is not None:
                faults.append((fault, path, rel, s, t))
                continue
            plan.add((rel.kind, rel.source, rel.target, _stereo(rel)))
            if rel.kind == "generalization":
                inherits.append((path, rel))
            elif _stereo(rel) == "include":
                includes.append((path, rel))
        parents = {k: list(v) for k, v in plan.graphs["generalization"].items()}  # 입력의 일반화·«include»(고치는 법을 더하기 전)
        included = {k: list(v) for k, v in plan.graphs["include"].items()}
        for fault, path, rel, s, t in faults:  # 앞 오류의 고치는 법이 만들 관계까지 보고 고른다
            r.fail(*_explain(plan, fault, path, rel, s, t, subject(rel.source)[1]))
        fail_loops(r, inherits, parents, "일반화", "조상이 다시 자식이 될 수 없다")
        fail_loops(r, includes, included, "«include»", "유즈케이스는 저를 포함하는 유즈케이스를 다시 포함할 수 없다")
        r.flush(out)
        return []

    def nests(self, outer: str, inner: str) -> bool:
        """액터는 시스템 경계 안에 두지 않는다 — 읽기 끝의 검사와 겹침 안내(boxcheck)가 함께 본다."""
        return inner != "actor"

    def guide(self, spec: Spec) -> str:
        """따옴표 친 이름 바로 뒤에는 받침에 따라 갈리는 조사를 붙이지 않는다(classdiagram.ClassRules.guide와 같은 까닭)."""
        return "\n".join([
            "  - 규칙: 연관은 액터와 유즈케이스 사이에 긋는다. 시스템 경계에 닿는 연관, 액터끼리 잇는 연관, 같은 시스템 경계 안이거나 둘 "
            "다 경계 밖인 유즈케이스끼리 잇는 연관은 입력 오류다(서로 다른 시스템 경계의 유즈케이스끼리는 받는다).",
            "  - 규칙: 일반화는 액터끼리, 유즈케이스끼리 긋는다. 종류가 다른 일반화, 시스템 경계가 끝인 일반화, 고리를 이루는 일반화(A의 "
            "부모가 B이고 B의 부모가 다시 A인 것 — 여러 단계도)는 입력 오류다.",
            '  - 규칙: stereotype이 "include"·"extend"인 관계(«include»·«extend»)는 유즈케이스 사이의 dependency여야 한다 — 다른 '
            "관계에 달면 입력 오류다. 다른 스테레오타입은 어느 관계에든 단다. 자기 자신을 포함하거나 확장하는 관계와 고리를 이루는 "
            "«include»(A가 B를, B가 다시 A를 포함하는 것 — 여러 단계도)도 입력 오류다(«extend»의 고리는 받는다)."])


def _fault(rel: B.Relation, s: str, t: str, subject: Callable[[str], tuple[bool, Optional[str]]]) -> Optional[str]:
    """관계가 어긋난 규칙의 이름(_explain이 이 이름으로 오류 글을 고른다). 어긋나지 않았으면 None — 일반화·«include» 고리는 따로
    본다. 주체를 알 수 없는 유즈케이스끼리의 연관은 보지 않는다(품은 요소의 문제는 이미 알렸다)."""
    if _step(rel):
        if rel.kind == "dependency" and s == t == "use_case":
            return "self_step" if rel.source == rel.target else None
        return "step"
    if rel.kind == "generalization":
        return "system_generalization" if "system" in (s, t) else "mixed_generalization" if s != t else None
    if rel.kind != "association":
        return None
    if "system" in (s, t):
        return "system_association"
    if s == t == "actor":
        return "actor_association"
    if s == t == "use_case":
        (known, here), (sure, there) = subject(rel.source), subject(rel.target)
        if known and sure and here == there:
            return "use_case_association"
    return None


def _graph(edge: Edge) -> Optional[str]:
    """고리를 보는 관계면 그 그래프 이름(일반화·«include»)."""
    kind, _, _, stereotype = edge
    if kind == "generalization":
        return kind
    return "include" if kind == "dependency" and stereotype == "include" else None


def _same(edge: Edge) -> tuple:
    """같은 관계로 치는 열쇠 — 연관은 방향이 없고, 의존은 stereotype이 다르면 다른 관계다."""
    kind, a, b, stereotype = edge
    if kind == "association":
        return kind, frozenset((a, b))
    return (kind, a, b, stereotype) if kind == "dependency" else (kind, a, b)


class _Plan:
    """고치는 법을 모두 따랐을 때 남을 관계. 오류 없는 관계에서 시작해, 오류마다 입력 차례대로 고치는 법이 권하는 관계를 더한다.
    권하는 관계와 같은 관계가 이미 있거나(권한 것 포함) 권하는 관계가 일반화·«include» 고리를 만들면 권하지 않고 지우라고 한다.
    같은 관계와 고리는 관계가 있어야 생기는 문제라, 권한 관계를 다 더한 집합에 문제가 없으면 어느 것을 고르거나 지워도 문제가 생기지
    않는다. 종류가 다른 관계가 같은 두 끝을 이어 선이 포개지는 것은 검사가 알리고 꺾는 점(via)으로 푼다."""

    def __init__(self) -> None:
        self.edges: dict[tuple, Optional[str]] = {}  # 같은 관계 열쇠(_same) → 그 관계를 권한 오류의 자리(입력에 있으면 None)
        self.graphs: dict[str, dict[str, list[str]]] = {"generalization": {}, "include": {}}  # 자식 → 부모들, 포함하는 쪽 → 포함되는 쪽들

    def add(self, edge: Edge, origin: Optional[str] = None) -> None:
        _, a, b, _ = edge
        self.edges.setdefault(_same(edge), origin)
        if (graph := _graph(edge)) is not None and a != b:
            self.graphs[graph].setdefault(a, []).append(b)

    def clash(self, edge: Edge) -> Optional[str]:
        """edge를 더하면 생기는 문제의 글. 없으면 None."""
        kind, a, b, _ = edge
        if (key := _same(edge)) in self.edges:
            what = "두 끝을 잇는" if kind == "association" else "같은 from·to의"
            origin = self.edges[key]
            return f"{what} {kind}{KIND_JOSA[kind]} {'이미 있다' if origin is None else f'생긴다({origin}의 고치는 법)'}"
        graph = _graph(edge)
        if graph is not None and (back := parent_path(self.graphs[graph], b, a)) is not None:
            label = "일반화" if graph == "generalization" else "«include»"
            keys = [("generalization", x, y) if graph == "generalization" else ("dependency", x, y, "include")
                    for x, y in zip(back, back[1:])]
            # 고리의 관계 가운데 다른 오류의 고치는 법이 만들 것이 있으면 밝힌다 — 입력에 있는 고리로 읽히지 않게
            origins = list(dict.fromkeys(o for key in keys if (o := self.edges.get(key)) is not None))
            how = f" — {'·'.join(origins)}의 고치는 법을 따르면" if origins else ""
            return f"{label}로 두면 고리가 된다({' → '.join(_show(k) for k in [a, *back])}{how})"
        return None

    def offer(self, path: str, what: str, options: list[tuple[str, str, Edge, str]], maybe: bool) -> str:
        """options는 (뒤에 말이 이어지는 꼴, 끝맺는 꼴, 그 말대로 바꾼 관계, 그 바꿈을 부르는 말 — 의존·일반화 등) — 다른 뜻의
        바꿈이다. 문제가 없는 것만 권하고 그 관계를 계획에 더한다. 막힌 바꿈은 까닭을 적는다 — 적지 않으면 그 바꿈도 된다고 읽힌다.
        maybe면 권하는 말이 뜻에 따른 것이라(…이면 바꾼다) 끝에 아니면 지우라는 말을 붙인다. what은 이 관계를 부르는
        말(관계·연관·일반화)이다."""
        drop = f"이 {what}{B.josa(what, '을', '를')} 지운다"
        problems = [self.clash(o[2]) for o in options]
        good = [o for o, p in zip(options, problems) if p is None]
        for o in good:
            self.add(o[2], path)
        if not good:
            return f"{'. '.join(dict.fromkeys(p for p in problems if p))}. {drop}"
        # 막힌 바꿈은 앞에 따로 적는다 — 권하는 말 뒤에 붙이면 그 말의 조건처럼 읽힌다
        blocked = "".join(f"{o[3]}{B.josa(o[3], '은', '는')} 안 된다 — {p}. " for o, p in zip(options, problems) if p)
        said = [o[0] for o in good[:-1]]
        said.append(f"{good[-1][0]}, 아니면 {drop}" if maybe else good[-1][1])
        return blocked + ", ".join(said)


class _InOrder(Reader):
    """규칙 오류를 모아 두는 읽기. 입력 차례(요소 다음 관계, 그 안에서는 입력의 자리, 같은 자리면 알린 차례)로 다른 읽기에 넘긴다 —
    규칙마다 따로 보느라 알린 차례가 입력 차례와 다르다."""

    def __init__(self) -> None:
        super().__init__()
        self.found: list[tuple[str, str]] = []

    def fail(self, path: str, message: str) -> None:
        self.found.append((path, message))

    def flush(self, r: Reader) -> None:
        def order(path: str) -> tuple[bool, int]:
            m = re.match(r"(\w+)\[(\d+)\]", path)
            return (False, 0) if m is None else (m.group(1) == "relations", int(m.group(2)))

        for path, message in sorted(self.found, key=lambda found: order(found[0])):
            r.fail(path, message)


PICK = "(자기 자신으로 가거나, 고리를 이루거나, 이미 있는 관계와 같아지지 않게 고른다)"  # 사람이 고르는 끝을 권할 때 — 고를 요소를 몰라 계획으로 볼 수 없다


def _explain(plan: _Plan, fault: str, path: str, rel: B.Relation, s: str, t: str,
             subject: Optional[str]) -> tuple[str, str]:
    """틀린 관계(fault — _fault가 낸 규칙 이름)의 (오류 자리, 오류 글). subject는 from 쪽 유즈케이스의 주체(시스템 경계)다."""
    a, b, ends = rel.source, rel.target, ends_of(rel, s, t)
    if fault == "self_step":
        what = "포함" if _stereo(rel) == "include" else "확장"
        return path, f"유즈케이스는 자기 자신을 {what}할 수 없다(«{_stereo(rel)}») — 이 관계를 지운다"
    if fault == "step":
        return _at(path, "stereotype"), (f"«include»·«extend»는 유즈케이스 사이의 dependency에만 단다(이 관계는 {rel.kind!r}, "
                                         f"{ends}) — {_step_fix(plan, path, rel, s, t)}")
    if fault == "system_generalization":
        keys = ", ".join(_show(k) for k, kind in ((a, s), (b, t)) if kind == "system")
        other = _other(s, t)
        how = (f"시스템 경계 쪽 끝을 {'액터' if other == 'actor' else '유즈케이스'}로 고치고{PICK}" if other
               else f"from·to를 둘 다 액터나 둘 다 유즈케이스로 고치고{PICK}")
        return path, (f"시스템 경계({keys})는 일반화의 끝이 될 수 없다 — 일반화는 액터끼리, 유즈케이스끼리 긋는다. {how}, 아니면 "
                      "이 일반화를 지운다")
    if fault == "mixed_generalization":
        how = plan.offer(path, "일반화", [("액터가 유즈케이스를 쓰는 것이면 kind를 'association'으로 바꾸고", "",
                                         ("association", a, b, None), "연관")], maybe=True)
        return path, f"일반화의 두 끝 종류가 다르다({ends}) — 일반화는 액터끼리, 유즈케이스끼리 긋는다. {how}"
    if fault == "system_association":
        systems = ", ".join(end_of(side, key, kind) for side, key, kind in (("from", a, s), ("to", b, t)) if kind == "system")
        other = {"actor": "그 액터가 쓰는 유즈케이스로", "use_case": "그 유즈케이스를 쓰는 액터로"}.get(_other(s, t) or "")
        how = f"시스템 경계 쪽 끝을 {other} 고치고" if other else "from·to를 액터와 유즈케이스로 고치고"
        return path, (f"연관이 시스템 경계에 닿는다({systems}) — 연관은 액터와 유즈케이스 사이에 긋는다. {how}{PICK}, 아니면 이 연관을 "
                      "지운다")
    if fault == "actor_association":
        return path, f"액터끼리 잇는 연관이다({ends}) — 액터는 유즈케이스와 연관으로 잇는다. {_actors_fix(plan, path, rel, '연관')}"
    assert fault == "use_case_association", fault
    where = f"같은 시스템 경계({_show(subject)}) 안의" if subject is not None else "시스템 경계 밖의"
    problem = (f"{where} 유즈케이스끼리 잇는 연관이다({ends}) — 같은 시스템 경계 안이거나 둘 다 경계 밖인 유즈케이스는 연관으로 "
               "잇지 않는다")
    if a == b:
        return path, f"{problem}. 자기 자신과 잇는 연관은 지운다"
    inc, ext = ("dependency", a, b, "include"), ("dependency", a, b, "extend")
    no_inc, no_ext = plan.clash(inc), plan.clash(ext)
    for edge, why in ((inc, no_inc), (ext, no_ext)):
        if why is None:
            plan.add(edge, path)
    change = "kind를 'dependency'로 바꾸고 stereotype을"
    if no_inc is None and no_ext is None:
        how = f"포함·확장이면 {change} 'include'나 'extend'로 하고"
    elif no_inc is None:
        how = f"포함이면 {change} 'include'로 하고(«extend»는 안 된다 — {no_ext})"
    elif no_ext is None:
        how = f"확장이면 {change} 'extend'로 하고(«include»는 안 된다 — {no_inc})"
    elif no_inc == no_ext:
        return path, f"{problem}. {no_ext}. 이 연관을 지운다"
    else:
        return path, f"{problem}. «include»는 안 된다 — {no_inc}. «extend»도 안 된다 — {no_ext}. 이 연관을 지운다"
    return path, f"{problem}. {how}, 아니면 이 연관을 지운다"


def _actors_fix(plan: _Plan, path: str, rel: B.Relation, what: str) -> str:
    """액터끼리 잇는 관계(what — 연관·관계)의 고치는 법. 액터끼리는 일반화만 긋는다."""
    if rel.source == rel.target:
        return f"자기 자신과 잇는 {what}{B.josa(what, '은', '는')} 지운다"
    if rel.kind == "generalization":  # «include»·«extend»를 단 일반화
        options = [("액터 사이 일반화를 뜻했으면 stereotype을 빼고", "", ("generalization", rel.source, rel.target, None),
                    "일반화")]
    else:
        drop = " stereotype을 빼고" if rel.stereotype else ""
        options = [(f"한 액터가 다른 액터의 한 종류면{drop} kind를 'generalization'으로 바꾸고(from이 자식)", "",
                    ("generalization", rel.source, rel.target, None), "일반화")]
    return plan.offer(path, what, options, maybe=True)


def _step_fix(plan: _Plan, path: str, rel: B.Relation, s: str, t: str) -> str:
    """«include»·«extend»를 유즈케이스 사이의 의존이 아닌 관계에 달았을 때의 고치는 법."""
    a, b, stereotype = rel.source, rel.target, _stereo(rel)
    if a == b and s == t:  # 유즈케이스가 자기 자신을 포함·확장하는 의존은 _explain이 본다
        if rel.kind == "dependency":  # 액터·시스템 경계의 자기 의존은 받는다
            return plan.offer(path, "관계", [("의존을 뜻했으면 stereotype을 빼고", "", ("dependency", a, a, None), "의존")],
                              maybe=True)
        return "자기 자신과 잇는 관계는 지운다"
    if s == t == "use_case":  # 관계 종류만 틀렸다(연관·일반화)
        dependency = ("dependency", a, b, stereotype)
        if rel.kind == "generalization":
            meant = "포함이면" if stereotype == "include" else "확장이면"
            return plan.offer(path, "관계", [(f"{meant} kind를 'dependency'로 바꾸고", "", dependency, "의존"),
                                            ("일반화를 뜻했으면 stereotype을 빼고", "", ("generalization", a, b, None), "일반화")],
                              maybe=True)
        return plan.offer(path, "관계", [("", "kind를 'dependency'로 바꾼다", dependency, "의존")], maybe=False)
    if "system" in (s, t):
        other = _other(s, t)
        if other == "actor":
            change = "" if rel.kind == "association" else " kind를 'association'으로 바꾸고"
            return (f"액터와 유즈케이스는 stereotype 없는 연관으로 잇는다. 시스템 경계 쪽 끝을 그 액터가 쓰는 유즈케이스로 "
                    f"고치고{PICK}{change} stereotype을 빼고, 아니면 이 관계를 지운다")
        where = "시스템 경계 쪽 끝을 유즈케이스로" if other == "use_case" else "from·to를 유즈케이스로"
        change = "" if rel.kind == "dependency" else " kind를 'dependency'로 바꾸고"
        return f"{where} 고치고{PICK}{change}, 아니면 이 관계를 지운다"
    if s == t == "actor":
        if rel.kind == "dependency":  # 액터 사이 의존은 받는다 — stereotype만 빼도 된다
            return plan.offer(path, "관계", [("의존을 뜻했으면 stereotype을 빼고", "", ("dependency", a, b, None), "의존"),
                                            ("한 액터가 다른 액터의 한 종류면 stereotype을 빼고 kind를 'generalization'으로 "
                                             "바꾸고(from이 자식)", "", ("generalization", a, b, None), "일반화")], maybe=True)
        return _actors_fix(plan, path, rel, "관계")  # 일반화(stereotype만 틀렸다)나 연관(액터끼리 연관도 틀렸다)
    change = "stereotype을 뺀다" if rel.kind == "association" else "kind를 'association'으로 바꾸고 stereotype을 뺀다"
    how = plan.offer(path, "관계", [("", change, ("association", a, b, None), "연관")], maybe=False)
    return f"액터와 유즈케이스는 stereotype 없는 연관으로 잇는다. {how}"


RULES = UseCaseRules()
SPEC = Spec(SHAPES, RELATIONS, ELEMENT_WORDS, list_field="elements", navigable="none", rules=RULES)


def parse(data: Any) -> Diagram:
    return B.parse(SPEC, data)


def render(data: Any, scale: float = SCALE) -> Drawing:
    return B.render(SPEC, data, scale)


_ONE_LINE = _system_name_height(1)

ELEMENTS = f"""- elements: 요소 목록(하나 이상).
  - kind(필수): "actor"(사람 모양 — 이름은 모양 밖에 쓴다), "use_case"(이름을 안 가운데에 쓴 타원 — 이름에 맞춰 \
커진다), "system"(시스템 경계 — 이름을 위쪽 가운데에 쓴 사각형, 안에 유즈케이스를 둔다).
  - name(필수)·id: "공용 입력(열쇠·이름)" 절.
  - left·top(필수): 자리의 왼쪽 위(액터는 사람 모양과 이름을 함께 덮는 자리).
  - in: 이 요소를 품은 시스템 경계의 열쇠. "요소 안에 요소 두기(중첩)" 절. 규칙: 액터는 시스템 밖의 사람이나 외부 시스템이라 \
시스템 경계 안에 두면(in) 입력 오류다.
  - width·height: 유즈케이스·시스템 경계 자리의 최소 크기. 글자와 안의 요소에 맞춰 더 늘어난다. 액터는 받지 않는다.
  {NAME_SIDE} 액터만 쓴다.
  - 선은 모양 가운데를 향하고, 선 끝은 액터면 사람 모양(폭 {ACTOR_FIGURE[0]}px·높이 {ACTOR_FIGURE[1]}px — 이름 빼고)을 덮는 \
사각형, 유즈케이스면 타원, 시스템 경계면 사각형 테두리에 닿는다. 시스템 경계의 이름 칸은 위쪽 가운데의 이름 글자 자리이고, 안의 요소를 두는 칸은 그 아래다 — 칸 윗변은 top에서 \
이름 한 줄이면 {_ONE_LINE}px, 줄이 하나 늘 때마다 {LABEL_LINE}px씩 더 아래다(그래서 안의 유즈케이스는 이름 한 줄이면 \
top + {_ONE_LINE + NEST_PAD}부터 둔다)."""

TIPS = f"""유즈케이스도 배치 요령:
- 시스템 경계 안에 유즈케이스를 세로로 늘어놓는다. 포함(«include»)·확장(«extend»)으로 이어지는 유즈케이스는 그 옆에 둔다.
- 액터는 시스템 경계의 왼쪽과 오른쪽 밖에 두고, 이름은 왼쪽 액터면 왼쪽("left"), 오른쪽 액터면 오른쪽("right")에 쓴다\
(name_side). 이름을 아래(기본)에 두면 아래쪽 유즈케이스로 가는 연관선과, 아래 자식 액터에서 올라오는 일반화 선이 이름을 \
지나 불합격하기 쉽다.
- 액터끼리 일반화는 부모 액터를 위에, 자식 액터를 그 아래에 둔다. 유즈케이스끼리 일반화도 부모를 위에 둔다.
- «include»는 기본 유즈케이스에서 포함되는 유즈케이스로, «extend»는 확장하는 유즈케이스에서 기본 유즈케이스로 긋는다 — 둘 다 \
kind "dependency"에 stereotype을 단다.
{spacing_tips(SPEC, "관계 이름·스테레오타입")}"""

INTRO = """유즈케이스도를 그려 PNG 파일로 저장하고, 검사 결과와 그림을 함께 돌려준다. 액터·유즈케이스·시스템 경계를 그리고, 그 \
사이를 연관·의존(«include»·«extend»)·일반화로 잇는다. 요소는 준 왼쪽 위(left·top) 그대로, 관계선은 준 꺾는 점(via)을 따라 \
그리고, 요소 크기·선 끝·선 글자 자리만 도구가 정한다. 좌표는 px이고 y는 아래로 커진다."""

TOOL = box_tool(INTRO, SPEC, f"{ELEMENTS}\n{relation_fields(SPEC)}", TIPS)
