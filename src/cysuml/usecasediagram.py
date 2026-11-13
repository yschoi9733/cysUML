"""유즈케이스도: 액터·유즈케이스·시스템 경계와 그 사이의 연관·의존(«include»·«extend»)·일반화를 그린다.

액터는 교류도와 같은 사람 모양(sequencediagram.draw_actor)에 이름을 모양 밖에 쓰고, 유즈케이스는 이름을 안 가운데에 쓴 타원,
시스템 경계는 이름을 위쪽 가운데에 쓰고 안에 유즈케이스를 두는 사각형이다. 읽기·자리 잡기·그리기는 공용 엔진(boxdiagram),
검사는 공용 검사(boxcheck)가 한다. 도구 설명(TOOL)과 배치 요령(TIPS)도 여기 둔다.
"""
from __future__ import annotations

import math
from typing import Any

from . import boxdiagram as B
from . import text as T
from .boxcheck import KINDS
from .boxdiagram import (ELEMENT_WORDS, LABEL_LINE, NEST_PAD, TRIANGLE_HEAD, Diagram, Drawing, Element, NameZone, PlacedBox,
                         RelationType, Shape, Spec, line_ys)
from .canvas import SCALE, Canvas, Point
from .classdiagram import RELATIONS as CLASS_RELATIONS
from .geom import Border, EllipseBorder
from .guide import (COMMON_INPUT, IMAGE_RESULT, NAME_SIDE, NESTING, NEW_INPUT, OUTSIDE_PLACES, PLACES_RESULT, flow,
                    relation_fields)
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
    """액터: 교류도와 같은 사람 모양. 이름은 모양 밖(name_side, 기본 아래)에 쓰고, 선 끝은 사람 모양을 덮는 사각형 테두리에 닿는다."""

    outside_name = True
    sized = False
    stereotyped = False

    def size(self, e: Element) -> tuple[float, float]:
        return ACTOR_FIGURE

    def anchor(self, e: Element, rect: Box) -> Point:
        """사람 모양 가운데보다 반 픽셀 위. 높이가 홀수라 가운데는 반 픽셀에 걸리는데, 그러면 정수 좌표에 놓은 타원과 가로로
        맞춰도 선이 반 픽셀 기울어 계단이 보인다."""
        return (rect[0] + rect[2]) / 2, rect[1] + ACTOR_FIGURE[1] // 2

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        l, t, r, _ = p.shape_rect
        draw_actor(c, (l + r) / 2, t, p.key)


class UseCaseShape(Shape):
    """유즈케이스: 이름을 안 가운데에 쓴 타원. 여백을 더한 이름 글자 상자를 가로·세로 √2배 하면 그 상자의 네 모서리가 타원 위에
    놓이므로, 타원은 그 크기(최소 USE_CASE_MIN)로 이름을 덮는다. 선 끝과 겹침은 타원 테두리로 본다."""

    stereotyped = False

    def size(self, e: Element) -> tuple[float, float]:
        w = _lines_width(e.name) + 2 * USE_CASE_PAD[0]
        h = LABEL_LINE * len(e.name) + 2 * USE_CASE_PAD[1]
        return max(USE_CASE_MIN[0], math.ceil(math.sqrt(2) * w)), max(USE_CASE_MIN[1], math.ceil(math.sqrt(2) * h))

    def border(self, e: Element, rect: Box) -> Border:
        l, t, r, b = rect
        return EllipseBorder((l + r) / 2, (t + b) / 2, (r - l) / 2, (b - t) / 2)

    def parts(self, e: Element, rect: Box) -> tuple[Border, ...]:
        """타원 — 자리 사각형의 네 모서리 쪽은 유즈케이스가 아니다."""
        return (self.border(e, rect),)

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        l, t, r, b = p.rect
        c.ellipse(l, t, r - l, b - t, owner=p.key)
        for s, y in zip(p.box.name, line_ys((t + b) / 2, len(p.box.name))):
            c.text((l + r) / 2, y, s, anchor="mm", owner=p.key)


class SystemShape(Shape):
    """시스템 경계: 이름(굵게)을 위쪽 가운데에 쓴 사각형. 안에 요소를 두는 칸은 이름 줄 아래이고, 이름 칸은 이름 글자 폭만큼이라
    그 옆으로는 선이 윗변을 건널 수 있다."""

    holds = True
    stereotyped = False

    def _name(self, e: Element) -> tuple[float, float]:
        """(이름 칸 폭, 이름 칸 높이)."""
        return (_lines_width(e.name, True) + 2 * SYSTEM_NAME_SIDE,
                LABEL_LINE * len(e.name) + 2 * SYSTEM_NAME_PAD)

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
    "generalization": RelationType("일반화", end=TRIANGLE_HEAD, trunk=True, role="자식"),
}
SPEC = Spec(SHAPES, RELATIONS, ELEMENT_WORDS, list_field="elements", navigable="none")


def parse(data: Any) -> Diagram:
    return B.parse(SPEC, data)


def render(data: Any, scale: float = SCALE) -> Drawing:
    return B.render(SPEC, data, scale)


_ONE_LINE = SYSTEM_NAME_PAD * 2 + LABEL_LINE  # 이름 한 줄인 시스템 경계의 이름 칸 높이

ELEMENTS = f"""- elements: 요소 목록(하나 이상).
  - kind(필수): "actor"(사람 모양 — 이름은 모양 밖에 쓴다), "use_case"(이름을 안 가운데에 쓴 타원 — 이름에 맞춰 \
커진다), "system"(시스템 경계 — 이름을 위쪽 가운데에 쓴 사각형, 안에 유즈케이스를 둔다).
  - name(필수)·id: "공용 입력(열쇠·이름)" 절.
  - left·top(필수): 자리의 왼쪽 위(액터는 사람 모양과 이름을 함께 덮는 자리).
  - in: 이 요소를 품은 시스템 경계의 열쇠. "요소 안에 요소 두기(중첩)" 절.
  - width·height: 유즈케이스·시스템 경계 자리의 최소 크기. 글자와 안의 요소에 맞춰 더 늘어난다. 액터는 받지 않는다.
  {NAME_SIDE} 액터만 쓴다.
  - 선은 모양 가운데를 향하고, 선 끝은 액터면 사람 모양(폭 {ACTOR_FIGURE[0]}px·높이 {ACTOR_FIGURE[1]}px — 이름 빼고)을 덮는 \
사각형, 유즈케이스면 타원, 시스템 경계면 사각형 테두리에 닿는다. 시스템 경계의 이름 칸은 위쪽 가운데의 이름 글자 자리이고, 안의 요소를 두는 칸은 그 아래다 — 칸 윗변은 top에서 \
이름 한 줄이면 {_ONE_LINE}px, 줄이 하나 늘 때마다 {LABEL_LINE}px씩 더 아래다(그래서 안의 유즈케이스는 이름 한 줄이면 \
top + {_ONE_LINE + NEST_PAD}부터 둔다)."""

TIPS = """유즈케이스도 배치 요령:
- 시스템 경계 안에 유즈케이스를 세로로 늘어놓는다. 포함(«include»)·확장(«extend»)으로 이어지는 유즈케이스는 그 옆에 둔다.
- 액터는 시스템 경계의 왼쪽과 오른쪽 밖에 두고, 이름은 왼쪽 액터면 왼쪽("left"), 오른쪽 액터면 오른쪽("right")에 쓴다\
(name_side). 이름을 아래(기본)에 두면 아래쪽 유즈케이스로 가는 연관선과, 아래 자식 액터에서 올라오는 일반화 선이 이름을 \
지나 불합격하기 쉽다.
- 액터끼리 일반화는 부모 액터를 위에, 자식 액터를 그 아래에 둔다. 유즈케이스끼리 일반화도 부모를 위에 둔다.
- «include»는 기본 유즈케이스에서 포함되는 유즈케이스로, «extend»는 확장하는 유즈케이스에서 기본 유즈케이스로 긋는다 — 둘 다 \
kind "dependency"에 stereotype을 단다.
- 요소 사이는 관계 이름·스테레오타입 글자가 들어갈 만큼 띄운다. 가로 80px·세로 60px쯤에서 시작하고, 글자가 길면 더 띄운다.
- 요소 크기는 도구가 글자와 안의 요소에 맞춰 늘린다. 그린 크기는 결과의 "요소 자리"에서 보고 다음 배치에 쓴다."""

TOOL = f"""유즈케이스도를 그려 PNG 파일로 저장하고, 검사 결과와 그림을 함께 돌려준다. 액터·유즈케이스·시스템 경계를 그리고, 그 \
사이를 연관·의존(«include»·«extend»)·일반화로 잇는다. 요소는 준 왼쪽 위(left·top) 그대로, 관계선은 준 꺾는 점(via)을 따라 \
그리고, 요소 크기·선 끝·선 글자 자리만 도구가 정한다. 좌표는 px이고 y는 아래로 커진다.

입력
{ELEMENTS}
{relation_fields(SPEC)}
{COMMON_INPUT}

{NEW_INPUT}

{NESTING}

결과
{PLACES_RESULT}
{OUTSIDE_PLACES}
{IMAGE_RESULT}
- elements·relations·file_name이 틀리면 그리지 않고 틀린 곳을 elements[0].left 꼴 자리와 함께 모두 모아 오류로 돌려준다. \
그림이 너무 커서 PNG로 그릴 수 없거나 저장할 폴더에 쓸 수 없을 때도 오류로 돌려준다.

{flow(KINDS, SPEC.words)}

{TIPS}"""
