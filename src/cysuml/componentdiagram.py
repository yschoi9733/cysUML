"""컴포넌트도: 컴포넌트와 제공 인터페이스 원, 컴포넌트를 구현하는 아티팩트, 컴포넌트를 실현하는 클래스를 그린다.

요소 종류는 shapes.SHAPES(클래스·패키지·컴포넌트·아티팩트·노드와 아이콘 표기 둘)에 제공 인터페이스 원(lollipop)을 더한 것이고, 관계는 클래스도 관계 여섯 가지
(classdiagram.RELATIONS)에 소켓(requires — 쓰는 쪽에서 원으로 가는 실선이 원을 틈을 두고 감싸는 반원에서 끝난다)을 더한 것이다.
연관의 기본 방향은 '없음'이다 — 컴포넌트에서 제공 인터페이스 원으로 가는 막대가 화살촉 없는 실선이라서.
읽기·자리 잡기·그리기는 공용 엔진(boxdiagram), 검사는 공용 검사(boxcheck)가 한다. 소켓의 끝 요소 종류만 여기서 읽은 뒤에 본다.
도구 설명(TOOL)과 배치 요령(TIPS)도 여기 둔다.
"""
from __future__ import annotations

import math
from typing import Any, Union

from . import boxdiagram as B
from .boxcheck import BOX_CLEARANCE, KINDS
from .boxdiagram import ELEMENT_WORDS, Diagram, Drawing, Element, EndShape, PlacedBox, RelationType, Shape, Spec, floored
from .canvas import SCALE, Canvas, Line, Point, Polygon
from .classdiagram import RELATIONS as CLASS_RELATIONS
from .geom import Border, EllipseBorder
from .guide import (COMMON_INPUT, IMAGE_RESULT, NESTING, NEW_INPUT, PLACED_ELEMENTS, flow, places_result,
                    relation_fields)
from .parsing import InputError, at, show
from .shapes import SHAPES
from .text import Box

BALL = 20  # 제공 인터페이스 원의 지름
SOCKET_GAP = 5  # 원 둘레와 소켓 반원 사이 틈
SOCKET = BALL / 2 + SOCKET_GAP  # 소켓 반원의 반지름
# 원과 모양 밖 이름 사이. 소켓 반원은 원 가운데에서 SOCKET 안에 드니, 이름 칸을 검사 여유(BOX_CLEARANCE)보다 1px 더 떼면 원
# 어느 쪽으로 소켓이 와도 반원이 이름 칸에 걸리지 않는다
BALL_NAME_GAP = SOCKET - BALL / 2 + BOX_CLEARANCE + 1
ARC_STEPS = 24  # 소켓 반원을 이 수만큼 나눈 꺾은선으로 그린다


class LollipopShape(Shape):
    """제공 인터페이스 원(lollipop): 작은 원과 모양 밖에 쓰는 이름. 클래스 모양 인터페이스(«interface» 상자)와 다른 종류다. 제공하는
    컴포넌트에서 원으로 연관(막대)을 긋고, 그 인터페이스를 쓰는 쪽은 원으로 점선 의존 화살표를 긋는다. 원은 모양 자리 가운데를
    정수로 내린 점(boxdiagram.floored)에 그리고, 선도 그 점을 향한다 — 정수 좌표에 가운데가 놓인 컴포넌트(기본 폭 90)와 잇는 막대가
    곧다."""

    outside_name = True
    sized = False
    stereotyped = False
    name_gap = BALL_NAME_GAP

    def size(self, e: Element) -> tuple[float, float]:
        return BALL, BALL

    def anchor(self, e: Element, rect: Box) -> Point:
        return floored(rect)

    def border(self, e: Element, rect: Box) -> Border:
        return EllipseBorder(*floored(rect), BALL / 2, BALL / 2)

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        cx, cy = floored(p.shape_rect)
        c.ellipse(cx - BALL / 2, cy - BALL / 2, BALL, BALL, owner=p.key)


LOLLIPOP = LollipopShape()


def _socket(c: Canvas, tip: Point, frm: Point, at_: Point, o: str) -> Union[Line, Polygon]:
    """소켓 반원: 원 가운데(at_ — 원이 선을 향하게 한 점)를 가운데로, 선 끝(tip)을 지나 원을 감싸는 반원. 선 끝은 원 둘레에서
    SOCKET_GAP 앞이라 반지름이 SOCKET이고, 양 끝은 선과 직각인 쪽이다 — 꺾는 점을 준 소켓도 반원 가운데가 원 가운데와 같다."""
    r = math.dist(at_, tip)
    th = math.atan2(tip[1] - at_[1], tip[0] - at_[0])
    return c.line([(at_[0] + r * math.cos(th + a), at_[1] + r * math.sin(th + a))
                   for a in (math.pi * (k / ARC_STEPS - 0.5) for k in range(ARC_STEPS + 1))], owner=o)


SOCKET_HEAD = EndShape("소켓 반원", 0, _socket, gap=SOCKET_GAP)
REQUIRES = "requires"
RELATIONS = {**CLASS_RELATIONS, REQUIRES: RelationType("소켓", end=SOCKET_HEAD, role="인터페이스를 쓰는 쪽")}

SPEC = Spec({**SHAPES, "lollipop": LOLLIPOP}, RELATIONS, ELEMENT_WORDS, list_field="elements", navigable="none")


def _socket_problems(d: Diagram) -> list[str]:
    """소켓은 인터페이스를 쓰는 쪽에서 제공 인터페이스 원으로 긋는다. 공용 엔진의 관계 읽기는 끝 요소 종류를 보지 않아 여기서
    본다 — 엔진이 문제 없이 읽었으면 relations 하나가 관계 하나라 차례가 입력 자리와 같다."""
    kind = {e.key: e.kind for e in d.boxes}
    out = []
    for i, r in enumerate(d.relations):
        if r.kind != REQUIRES:
            continue
        path = at("relations", i)
        if kind[r.source] == "lollipop":
            out.append(f"{at(path, 'from')}: 소켓({REQUIRES})의 from은 인터페이스를 쓰는 쪽이다 — from 요소 {show(r.source)}의 종류가 "
                       "'lollipop'이다")
        if kind[r.target] != "lollipop":
            out.append(f"{at(path, 'to')}: 소켓({REQUIRES})은 제공 인터페이스 원(kind \"lollipop\")으로 긋는다 — to 요소 "
                       f"{show(r.target)}의 종류가 {kind[r.target]!r}다")
    return out


def parse(data: Any) -> Diagram:
    d = B.parse(SPEC, data)
    if problems := _socket_problems(d):
        raise InputError(problems)
    return d


def render(data: Any, scale: float = SCALE) -> Drawing:
    return B.draw(parse(data), scale)


LOLLIPOP_INPUT = f"""  - 이 도구는 kind "lollipop"(제공 인터페이스 원)도 받는다. 지름 {BALL}px 원과 그 밖에 쓰는 이름이다. \
클래스 모양 인터페이스(kind "interface"의 «interface» 상자)와 다른 종류이고, 둘 다 쓸 수 있다. name·id·left·top·in·name_side를 \
받고, stereotype·width·height는 받지 않는다. 선은 원 가운데를 향하고 원 둘레에 닿는다. 이름은 원에서 {BALL_NAME_GAP:g}px 떨어진다."""

SOCKET_INPUT = f"""  - 이 도구는 관계 kind "{REQUIRES}"(소켓)도 받는다. 인터페이스를 쓰는 쪽(from)에서 제공 인터페이스 원(to, kind \
"lollipop")으로 긋는 실선인데, 원 둘레에서 {SOCKET_GAP}px 앞에서 멈추고 그 끝에 원을 감싸는 반원(반지름 {SOCKET:g}px — 원과 같은 \
가운데)이 붙는다. 반원은 쓰는 쪽 절반을 감싸고 맞은편이 열려 있다. to가 원이 아니거나 from이 원이면 입력 오류다. name·stereotype·via를 \
받고, from_multiplicity·to_multiplicity·navigable은 받지 않는다. 꺾는 점을 주면 원 쪽 끝 구간이 원 가운데를 향하고 반원도 그 구간 \
쪽에 붙는다."""

TIPS = f"""컴포넌트도 배치 요령:
- 제공 인터페이스는 원(lollipop)으로 그린다 — 제공하는 컴포넌트에서 원으로 association을 긋고(이 도구의 연관 기본 방향은 "none"이라 \
화살촉 없는 막대가 된다), 그 인터페이스를 쓰는 쪽에서 원으로 dependency(점선 화살표)나 {REQUIRES}(소켓)를 긋는다. 한 원을 여럿이 쓸 수 \
있다.
- 원은 제공하는 컴포넌트 바로 옆, 쓰는 쪽을 향한 쪽에 둔다. 컴포넌트가 패키지 안에 있으면 원도 in으로 그 패키지 안에 넣는다.
- 원으로 들어오는 화살표는 한 점에 몰리지 않게 원 둘레로 흩어 둔다 — 원 가운데에서 본 쓰는 쪽(꺾는 점을 주면 마지막 꺾는 점)의 \
방향이 다른 쓰는 쪽과도, 막대(제공하는 컴포넌트 쪽)와도 40°쯤 넘게 벌어지게 한다. 더 좁으면 화살촉끼리 겹치거나 화살촉이 막대에 \
닿아 불합격이다.
- 소켓은 한 원에 하나다 — 반원 둘은 겹쳐 불합격이다. 그 원을 쓰는 나머지 쪽은 dependency 화살표로 긋거나, 같은 인터페이스의 원을 \
하나 더 그린다. 반원이 원의 쓰는 쪽 절반을 감싸므로 막대와 화살표는 열린 쪽에서 들어온다 — 원 가운데에서 본 소켓 쪽(꺾는 점을 주면 \
마지막 꺾는 점)과 막대는 100°, 화살표는 110° 넘게 벌린다. 막대를 소켓 맞은편에 두어 막대·원·소켓을 일직선으로 그으면 가장 넉넉하다.
- 원 이름은 막대와 들어오는 화살표·소켓이 없는 쪽에 쓴다(name_side, 기본은 아래) — 쓰는 쪽이 아래면 이름을 옆에 쓰고, 막대·원·소켓이 \
가로 일직선이면 위나 아래에 쓴다.
- 컴포넌트·아티팩트를 아이콘 표기(component_icon·artifact_icon)로 그려도 요령은 같다. 문서 아이콘 아티팩트에서 그 아티팩트가 구현하는 \
컴포넌트로는 stereotype(예: "manifest")을 단 dependency를 긋고, 아티팩트 이름은 그 선이 없는 쪽(name_side)에 쓴다. UML 1 표기 \
컴포넌트에는 왼쪽 변의 부품 네모 사이로 가로선 하나만 들어오므로, 그 컴포넌트와 잇는 나머지 원·아티팩트·요소는 위·아래·오른쪽에 둔다.
- 패키지마다 그 안의 컴포넌트를 묶어 둔다. 패키지 안 요소와 밖 요소를 잇는 선의 글자(«manifest» 등)는 선의 가장 긴 구간 가운데에 \
놓이므로, 그 자리에 패키지 테두리가 오지 않게 밖 요소를 넉넉히 떼어 놓는다.
- 아티팩트는 구현하는 컴포넌트 가까이 두고, 아티팩트에서 컴포넌트로 stereotype "manifest"를 단 dependency를 긋는다.
- 컴포넌트를 실현하는 클래스들(패키지 안에 둘 수 있다)은 컴포넌트 아래에 두고, 클래스에서 컴포넌트로 realization을, 또는 \
컴포넌트에서 클래스로 dependency를 긋는다. 클래스 사이 관계 종류는 클래스도와 같다. 다만 연관·집합·합성의 기본 방향이 클래스도 \
("to")와 달리 "none"이라 화살촉이 없으니, 화살촉이 필요하면 navigable을 준다.
- 요소 사이는 관계 이름·스테레오타입 글자가 들어갈 만큼 띄운다. 가로 80px·세로 60px쯤에서 시작하고, 글자가 길면 더 띄운다.
- 요소 크기는 도구가 글자와 안의 요소에 맞춰 늘린다. 그린 크기는 결과의 "요소 자리"에서 보고 다음 배치에 쓴다."""

TOOL = f"""컴포넌트도를 그려 PNG 파일로 저장하고, 검사 결과와 그림을 함께 돌려준다. 컴포넌트와 제공 인터페이스 원, \
컴포넌트를 구현하는 아티팩트, 컴포넌트를 실현하는 클래스를 그린다. 클래스·패키지·컴포넌트·아티팩트·노드와 제공 인터페이스 원을 한 그림에 섞어 \
그릴 수 있고, 컴포넌트·아티팩트는 아이콘 표기로도 그린다. 요소는 준 왼쪽 위(left·top) 그대로, 관계선은 준 꺾는 점(via)을 따라 그리고, 요소 크기·선 끝·선 글자 자리만 도구가 \
정한다. 좌표는 px이고 y는 아래로 커진다.

입력
{PLACED_ELEMENTS}
{LOLLIPOP_INPUT}
{relation_fields(SPEC)}
{SOCKET_INPUT}
{COMMON_INPUT}

{NEW_INPUT}

{NESTING}

결과
{places_result(SPEC)}
{IMAGE_RESULT}
- elements·relations·file_name이 틀리면 그리지 않고 틀린 곳을 elements[0].left 꼴 자리와 함께 모두 모아 오류로 돌려준다. \
그림이 너무 커서 PNG로 그릴 수 없거나 저장할 폴더에 쓸 수 없을 때도 오류로 돌려준다.

{flow(KINDS, SPEC.words)}

{TIPS}"""
