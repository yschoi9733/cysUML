"""컴포넌트도: 컴포넌트와 제공 인터페이스(막대사탕), 컴포넌트를 구현하는 아티팩트, 컴포넌트를 실현하는 클래스를 그린다.

요소 종류는 shapes.SHAPES(클래스·패키지·컴포넌트·아티팩트·노드)에 막대사탕을 더한 것이고, 관계는 클래스도 관계 여섯 가지
(classdiagram.RELATIONS)다. 연관의 기본 방향은 '없음'이다 — 컴포넌트에서 막대사탕 원으로 가는 막대가 화살촉 없는 실선이라서.
읽기·자리 잡기·그리기는 공용 엔진(boxdiagram), 검사는 공용 검사(boxcheck)가 한다. 도구 설명(TOOL)과 배치 요령(TIPS)도 여기 둔다.
"""
from __future__ import annotations

from typing import Any

from . import boxdiagram as B
from .boxcheck import KINDS
from .boxdiagram import ELEMENT_WORDS, Diagram, Drawing, Element, PlacedBox, Shape, Spec
from .canvas import SCALE, Canvas
from .classdiagram import RELATIONS
from .geom import Border, EllipseBorder
from .guide import (COMMON_INPUT, IMAGE_RESULT, NAME_SIDE, NESTING, NEW_INPUT, OUTSIDE_PLACES, PLACED_ELEMENTS, PLACES_RESULT,
                    flow, relation_fields)
from .shapes import SHAPES
from .text import Box

BALL = 20  # 막대사탕 원의 지름


class LollipopShape(Shape):
    """막대사탕(제공 인터페이스): 작은 원과 모양 밖에 쓰는 이름. 클래스 모양 인터페이스(«interface» 상자)와 다른 종류다. 제공하는
    컴포넌트에서 원으로 연관(막대)을 긋고, 그 인터페이스를 쓰는 쪽은 원으로 점선 의존 화살표를 긋는다."""

    outside_name = True
    sized = False
    stereotyped = False

    def size(self, e: Element) -> tuple[float, float]:
        return BALL, BALL

    def border(self, e: Element, rect: Box) -> Border:
        l, t, r, b = rect
        return EllipseBorder((l + r) / 2, (t + b) / 2, (r - l) / 2, (b - t) / 2)

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        l, t, r, b = p.shape_rect
        c.ellipse(l, t, r - l, b - t, owner=p.key)


LOLLIPOP = LollipopShape()

SPEC = Spec({**SHAPES, "lollipop": LOLLIPOP}, RELATIONS, ELEMENT_WORDS, list_field="elements", navigable="none")


def parse(data: Any) -> Diagram:
    return B.parse(SPEC, data)


def render(data: Any, scale: float = SCALE) -> Drawing:
    return B.render(SPEC, data, scale)


LOLLIPOP_INPUT = f"""  - 이 도구는 kind "lollipop"(막대사탕 — 제공 인터페이스)도 받는다. 지름 {BALL}px 원과 그 밖에 쓰는 이름이다. \
클래스 모양 인터페이스(kind "interface"의 «interface» 상자)와 다른 종류이고, 둘 다 쓸 수 있다. name·id·left·top·in·name_side를 \
받고, stereotype·width·height는 받지 않는다. 선은 원 가운데를 향하고 원 둘레에 닿는다.
  {NAME_SIDE}"""

TIPS = """컴포넌트도 배치 요령:
- 제공 인터페이스는 막대사탕으로 그린다 — 제공하는 컴포넌트에서 원으로 association을 긋고(이 도구의 연관 기본 방향은 "none"이라 \
화살촉 없는 막대가 된다), 그 인터페이스를 쓰는 쪽에서 원으로 dependency(점선 화살표)를 긋는다. 한 원을 여럿이 쓸 수 있다.
- 원은 제공하는 컴포넌트 바로 옆, 쓰는 쪽을 향한 쪽에 둔다. 컴포넌트가 패키지 안에 있으면 원도 in으로 그 패키지 안에 넣는다.
- 쓰는 쪽이 여럿이면 원으로 들어오는 화살표가 한 점에 몰리지 않게 원 둘레로 흩어 둔다 — 원 가운데에서 본 쓰는 쪽(꺾는 점을 \
주면 마지막 꺾는 점)의 방향이 서로 40°쯤 넘게 벌어지게 한다. 더 좁으면 화살촉끼리 겹쳐 불합격이다.
- 원 이름은 막대와 들어오는 화살표가 없는 쪽에 쓴다(name_side, 기본은 아래) — 쓰는 쪽이 아래면 이름을 옆에 쓴다.
- 패키지마다 그 안의 컴포넌트를 묶어 둔다. 패키지 안 요소와 밖 요소를 잇는 선의 글자(«manifest» 등)는 선의 가장 긴 구간 가운데에 \
놓이므로, 그 자리에 패키지 테두리가 오지 않게 밖 요소를 넉넉히 떼어 놓는다.
- 아티팩트는 구현하는 컴포넌트 가까이 두고, 아티팩트에서 컴포넌트로 stereotype "manifest"를 단 dependency를 긋는다.
- 컴포넌트를 실현하는 클래스들(패키지 안에 둘 수 있다)은 컴포넌트 아래에 두고, 클래스에서 컴포넌트로 realization을, 또는 \
컴포넌트에서 클래스로 dependency를 긋는다. 클래스 사이 관계는 클래스도와 같고, 연관에 화살촉이 필요하면 navigable을 준다.
- 요소 사이는 관계 이름·스테레오타입 글자가 들어갈 만큼 띄운다. 가로 80px·세로 60px쯤에서 시작하고, 글자가 길면 더 띄운다.
- 요소 크기는 도구가 글자와 안의 요소에 맞춰 늘린다. 그린 크기는 결과의 "요소 자리"에서 보고 다음 배치에 쓴다."""

TOOL = f"""컴포넌트도를 그려 PNG 파일로 저장하고, 검사 결과와 그림을 함께 돌려준다. 컴포넌트와 제공 인터페이스(막대사탕), \
컴포넌트를 구현하는 아티팩트, 컴포넌트를 실현하는 클래스를 그린다. 클래스·패키지·컴포넌트·아티팩트·노드와 막대사탕을 한 그림에 섞어 \
그릴 수 있다. 요소는 준 왼쪽 위(left·top) 그대로, 관계선은 준 꺾는 점(via)을 따라 그리고, 요소 크기·선 끝·선 글자 자리만 도구가 \
정한다. 좌표는 px이고 y는 아래로 커진다.

입력
{PLACED_ELEMENTS}
{LOLLIPOP_INPUT}
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
