"""유즈케이스도: 액터·유즈케이스·시스템 경계와 그 사이의 연관·의존(«include»·«extend»)·일반화를 그린다.

액터는 교류도와 같은 사람 모양(sequencediagram.draw_actor)에 이름을 모양 밖에 쓰고, 유즈케이스는 이름을 안 가운데에 쓴 타원,
시스템 경계는 이름을 위쪽 가운데에 쓰고 안에 유즈케이스를 두는 사각형이다. 읽기·자리 잡기·그리기는 공용 엔진(boxdiagram),
검사는 공용 검사(boxcheck)가 한다. 요소·관계의 짜임이 UML 표기에 맞는지는 표기 규칙(UseCaseRules)이 읽기 끝에 본다. 도구
설명(TOOL)과 배치 요령(TIPS)도 여기 둔다.
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Any, Optional

from . import boxdiagram as B
from . import text as T
from .boxdiagram import (ELEMENT_WORDS, LABEL_LINE, NEST_PAD, TRIANGLE_HEAD, Diagram, Drawing, Element, NameZone, PlacedBox,
                         RelationType, Rules, Shape, Spec, floored, line_ys)
from .canvas import SCALE, Canvas, Point
from .classdiagram import RELATIONS as CLASS_RELATIONS
from .classdiagram import end_of, fail_loops, parent_path
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


def _step(rel: B.Relation) -> bool:
    return rel.stereotype is not None and rel.stereotype.casefold() in STEPS


class UseCaseRules(Rules):
    """유즈케이스도의 표기 규칙. 모두 입력 오류다(그리지 않는다) — 알림은 없다.

    액터는 시스템 밖의 사람이나 외부 시스템이라 시스템 경계 안에 두지 않는다(in). 연관은 액터와 유즈케이스 사이에 긋는다 — 시스템
    경계에 닿는 연관, 액터끼리 잇는 연관(UML 명세 Actor 제약: 액터의 연관은 유즈케이스·컴포넌트·클래스로만 간다), 같은 주체의
    유즈케이스끼리 잇는 연관(UseCase 제약: 같은 주체를 가리키는 유즈케이스끼리는 연관을 맺지 않는다 — 주체는 유즈케이스를 품은
    가장 가까운 시스템 경계이고, 둘 다 경계 밖이면 같은 주체로 친다)은 틀렸다. 일반화는 액터끼리, 유즈케이스끼리 긋고 고리를 이루지
    않는다(자기 자신으로 가는 일반화는 관계 종류가 막는다 — RELATIONS의 reflexive). «include»·«extend»는 유즈케이스 사이의 의존에만
    단다. 관계 하나에는 오류를 하나만 알리고(«include»·«extend»를 먼저 본다), 고치는 법은 그대로 따랐을 때 다시 걸리지 않게 두 끝
    종류와 이미 있는 관계에 맞춘다."""

    def check(self, r: Reader, spec: Spec, elements: list[tuple[str, Element]],
              relations: list[tuple[str, B.Relation]]) -> list[Notice]:
        kinds = {e.key: e.kind for _, e in elements}
        for path, e in elements:
            if e.kind == "actor" and e.parent is not None and kinds.get(e.parent) == "system":
                r.fail(_at(path, "in"), f"액터는 시스템 경계({_show(e.parent)}) 안에 둘 수 없다 — 액터는 시스템 밖의 사람이나 외부 "
                                        "시스템이다. in을 빼고 시스템 경계 밖(왼쪽이나 오른쪽)에 둔다")
        lines = B.lineage({e.key: e.parent for _, e in elements})

        def subject(key: str) -> Optional[str]:
            return next((k for k in lines.get(key, ()) if kinds.get(k) == "system"), None)

        have = {(rel.kind, rel.source, rel.target) for _, rel in relations}
        parents: dict[str, list[str]] = {}  # 오류 없는 일반화(자식 → 부모들)
        inherits: list[tuple[str, B.Relation]] = []
        faults: list[tuple[str, B.Relation, str, str]] = []
        for path, rel in relations:
            s, t = kinds.get(rel.source), kinds.get(rel.target)
            if s is None or t is None:
                continue
            if _step(rel):
                if not (rel.kind == "dependency" and s == t == "use_case"):
                    faults.append((path, rel, s, t))
            elif rel.kind == "generalization":
                if s != t or s == "system":
                    faults.append((path, rel, s, t))
                else:
                    parents.setdefault(rel.source, []).append(rel.target)
                    inherits.append((path, rel))
            elif rel.kind == "association" and ("system" in (s, t) or s == t == "actor"
                                                or s == t == "use_case" and subject(rel.source) == subject(rel.target)):
                faults.append((path, rel, s, t))
        fix = _Fixes(have, parents)
        for path, rel, s, t in faults:  # 고치는 법이 오류 없는 일반화 전부를 보고 고른다
            if _step(rel):
                r.fail(_at(path, "stereotype"), f"«include»·«extend»는 유즈케이스 사이의 dependency에만 단다(이 관계는 "
                                                f"{rel.kind!r}, {_ends(rel, s, t)}) — {fix.step(rel, s, t)}")
            elif rel.kind == "generalization":
                r.fail(path, _generalization(rel, s, t, fix))
            else:
                r.fail(path, _association(rel, s, t, subject(rel.source), fix))
        fail_loops(r, inherits, parents, "일반화", "조상이 다시 자식이 될 수 없다")
        return []

    def guide(self, spec: Spec) -> str:
        """따옴표 친 이름 바로 뒤에는 받침에 따라 갈리는 조사를 붙이지 않는다(classdiagram.ClassRules.guide와 같은 까닭)."""
        return "\n".join([
            "  - 규칙: 연관은 액터와 유즈케이스 사이에 긋는다. 시스템 경계에 닿는 연관, 액터끼리 잇는 연관, 같은 시스템 경계 안이거나 둘 "
            "다 경계 밖인 유즈케이스끼리 잇는 연관은 입력 오류다(서로 다른 시스템 경계의 유즈케이스끼리는 받는다).",
            "  - 규칙: 일반화는 액터끼리, 유즈케이스끼리 긋는다. 종류가 다른 일반화, 시스템 경계가 끝인 일반화, 고리를 이루는 일반화(A의 "
            "부모가 B이고 B의 부모가 다시 A인 것 — 여러 단계도)는 입력 오류다.",
            '  - 규칙: stereotype이 "include"·"extend"인 관계(«include»·«extend»)는 유즈케이스 사이의 dependency여야 한다 — 다른 '
            "관계에 달면 입력 오류다. 다른 스테레오타입은 어느 관계에든 단다."])


def _ends(rel: B.Relation, s: str, t: str) -> str:
    return f"{end_of('from', rel.source, s)}, {end_of('to', rel.target, t)}"


class _Fixes:
    """틀린 관계의 고치는 법. have는 입력의 모든 관계 (kind, from, to), parents는 오류 없는 일반화(자식 → 부모들)다 — 고치는 법을
    따라 바꾼 관계가 이미 있는 관계와 겹치거나 일반화 고리를 만들면 그 관계를 지우라고 한다."""

    def __init__(self, have: set[tuple[str, str, str]], parents: dict[str, list[str]]):
        self.have, self.parents = have, parents

    def joined(self, kind: str, a: str, b: str) -> bool:
        """a와 b를 kind 관계가 어느 방향으로든 잇는지."""
        return (kind, a, b) in self.have or (kind, b, a) in self.have

    def lineage(self, a: str, b: str) -> Optional[list[str]]:
        """a와 b가 일반화로(여러 단계도) 이어져 있으면 자식에서 부모로 가는 길."""
        return parent_path(self.parents, a, b) or parent_path(self.parents, b, a)

    def actors(self, rel: B.Relation, what: str) -> str:
        """액터끼리 잇는 관계(what — 연관·관계)의 고치는 법. 액터끼리는 일반화만 긋는다."""
        if rel.source == rel.target:
            return f"자기 자신과 잇는 {what}{B.josa(what, '은', '는')} 지운다"
        if (ring := self.lineage(rel.source, rel.target)) is not None:
            return f"두 액터는 이미 일반화로 이어져 있다({' → '.join(_show(k) for k in ring)}). 이 {what}{B.josa(what, '을', '를')} 지운다"
        drop = " stereotype을 빼고" if rel.stereotype else ""
        return (f"한 액터가 다른 액터의 한 종류면{drop} kind를 'generalization'으로 바꾸고(from이 자식), 아니면 이 "
                f"{what}{B.josa(what, '을', '를')} 지운다")

    def step(self, rel: B.Relation, s: str, t: str) -> str:
        """«include»·«extend»를 유즈케이스 사이의 의존이 아닌 관계에 달았을 때."""
        if s == t == "use_case":  # 관계 종류만 틀렸다(연관·일반화)
            if ("dependency", rel.source, rel.target) in self.have:
                return "같은 from·to의 dependency가 이미 있다. 이 관계를 지운다"
            if rel.kind == "generalization" and self.lineage(rel.source, rel.target) is None:
                return "포함·확장이면 kind를 'dependency'로 바꾸고, 일반화를 뜻했으면 stereotype을 뺀다"
            return "kind를 'dependency'로 바꾼다"
        if "system" in (s, t):
            return "시스템 경계 쪽 끝을 유즈케이스로 고친다"
        if s == t == "actor":
            if rel.kind != "generalization":
                return f"액터끼리는 일반화만 긋는다. {self.actors(rel, '관계')}"
            if self.lineage(rel.source, rel.target) is None:
                return "액터 사이 일반화를 뜻했으면 stereotype을 뺀다"
            return self.actors(rel, "관계")
        if rel.kind != "association" and self.joined("association", rel.source, rel.target):
            return "두 끝을 잇는 association이 이미 있다. 이 관계를 지운다"
        change = "" if rel.kind == "association" else " kind를 'association'으로 바꾸고"
        return f"액터와 유즈케이스는 stereotype 없는 연관으로 잇는다.{change} stereotype을 뺀다"


def _generalization(rel: B.Relation, s: str, t: str, fix: _Fixes) -> str:
    for key, kind in ((rel.source, s), (rel.target, t)):
        if kind == "system":
            return (f"시스템 경계({_show(key)})는 일반화의 끝이 될 수 없다 — 일반화는 액터끼리, 유즈케이스끼리 긋는다. from·to를 "
                    "액터나 유즈케이스로 고친다")
    how = ("두 끝을 잇는 association이 이미 있다. 이 일반화를 지운다" if fix.joined("association", rel.source, rel.target)
           else "액터가 유즈케이스를 쓰는 것이면 kind를 'association'으로 바꾼다")
    return f"일반화의 두 끝 종류가 다르다({_ends(rel, s, t)}) — 일반화는 액터끼리, 유즈케이스끼리 긋는다. {how}"


def _association(rel: B.Relation, s: str, t: str, subject: Optional[str], fix: _Fixes) -> str:
    """시스템 경계에 닿거나, 액터끼리이거나, 같은 주체(subject — from 쪽 유즈케이스의 주체)의 유즈케이스끼리 잇는 연관."""
    if "system" in (s, t):
        ends = ", ".join(end_of(side, key, kind) for side, key, kind in (("from", rel.source, s), ("to", rel.target, t))
                         if kind == "system")
        other = {"actor": "그 액터가 쓰는 유즈케이스로", "use_case": "그 유즈케이스를 쓰는 액터로"}.get(t if s == "system" else s)
        how = f"시스템 경계 쪽 끝을 {other} 고친다" if other else "from·to를 액터와 유즈케이스로 고친다"
        return f"연관이 시스템 경계에 닿는다({ends}) — 연관은 액터와 유즈케이스 사이에 긋는다. {how}"
    if s == "actor":
        return f"액터끼리 잇는 연관이다({_ends(rel, s, t)}) — 액터는 유즈케이스와 연관으로 잇는다. {fix.actors(rel, '연관')}"
    where = f"같은 시스템 경계({_show(subject)}) 안의" if subject is not None else "시스템 경계 밖의"
    if rel.source == rel.target:
        how = "자기 자신과 잇는 연관은 지운다"
    elif fix.joined("dependency", rel.source, rel.target) or fix.joined("generalization", rel.source, rel.target):
        how = "두 유즈케이스는 이미 다른 관계로 이어져 있다. 이 연관을 지운다"
    else:
        how = "포함·확장이면 kind를 'dependency'로 바꾸고 stereotype 'include'나 'extend'를 단다"
    return (f"{where} 유즈케이스끼리 잇는 연관이다({_ends(rel, s, t)}) — 같은 시스템 경계 안이거나 둘 다 경계 밖인 유즈케이스는 "
            f"연관으로 잇지 않는다. {how}")


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
- 액터는 시스템 경계의 왼쪽과 오른쪽에 두고, 이름은 왼쪽 액터면 왼쪽("left"), 오른쪽 액터면 오른쪽("right")에 쓴다\
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
