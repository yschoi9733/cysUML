"""상태도·액티비티도가 함께 쓰는 요소 모양: 시작 점, 끝 점(과녁), 마름모(선택·결정·합류), 둥근 모서리 상자(상태·행동).

그림판에는 둥근 모서리 상자가 없다. 모서리 호를 짧은 선분으로 나눈 다각형으로 그리고, 같은 꼭짓점을 검사용 테두리로 넘긴다 —
그린 것과 검사하는 테두리가 같다. 시작·끝 점과 마름모는 이름이 없어 관계·in이 id로 가리키고, 크기가 정해져 있다. 두 그림의
읽기(parse_flow)는 공용 엔진의 읽기에 시작·끝 점의 선 방향 규칙을 더한다.
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Any, Optional

from . import boxdiagram as B
from . import text as T
from .boxdiagram import LABEL_LINE, Diagram, Element, NameZone, PlacedBox, Shape, Spec, josa, line_ys
from .canvas import Canvas, Point
from .classdiagram import MIN_WIDTH, ROW, SECTION_PAD, head_lines, head_width
from .geom import Border, EllipseBorder, PolygonBorder
from .parsing import InputError, Reader
from .parsing import at as _at
from .parsing import show as _show
from .text import Box

START = 20         # 시작 점 지름
FINAL = 24         # 끝 점 바깥 원 지름
FINAL_CORE = 14    # 끝 점 안쪽 칠한 원 지름
DIAMOND_SIZE = 30  # 선택·결정·합류 마름모의 폭·높이
ARC_STEPS = 6      # 둥근 모서리 호 하나를 나누는 선분 수
STATE_RADIUS = 10  # 상태 모서리 반지름
ACTION_RADIUS = 16  # 행동 모서리 반지름(상태보다 둥글다)
NAME_BAND = 25     # 상태·행동 이름 칸에서 이름 줄 밖에 더하는 높이(위아래 반씩) — 이름 한 줄이면 40
STATE_ROW_LEFT = 8  # 상태 동작 칸 줄의 왼쪽 여백(오른쪽도 같게 폭에 더한다) — 둥근 모서리에 글자가 닿지 않게
ACTION_SIDE = 20   # 행동 이름 좌우 여백(둥근 모서리에 글자가 닿지 않게)

# 4분원 위의 점(0°에서 90°까지). 호 끝은 곧은 변과 정확히 맞물리게 (1, 0)·(0, 1) 그대로 둔다
_QUARTER = ((1.0, 0.0), *((math.cos(math.pi / 2 * i / ARC_STEPS), math.sin(math.pi / 2 * i / ARC_STEPS))
                          for i in range(1, ARC_STEPS)), (0.0, 1.0))


@lru_cache(maxsize=1024)
def rounded(rect: Box, radius: float) -> tuple[Point, ...]:
    """둥근 모서리 상자의 꼭짓점(위 변 오른쪽 끝에서 시계 방향). 모서리마다 반지름 radius인 4분원을 ARC_STEPS개 선분으로 나눈다.
    상자가 반지름의 두 배보다 작으면 반지름을 줄인다. 자리 잡기(테두리·겹침 조각·테두리 선)와 그리기가 같은 자리로 여러 번 부르므로
    한 번만 잰다."""
    l, t, r, b = rect
    k = min(radius, (r - l) / 2, (b - t) / 2)
    corners = (((r - k, t + k), lambda x, y: (y, -x)), ((r - k, b - k), lambda x, y: (x, y)),
               ((l + k, b - k), lambda x, y: (-y, x)), ((l + k, t + k), lambda x, y: (-x, -y)))
    out: list[Point] = []
    for (cx, cy), turn in corners:
        for x, y in _QUARTER:
            dx, dy = turn(x, y)
            p = (cx + k * dx, cy + k * dy)
            if not out or p != out[-1]:
                out.append(p)
    return tuple(out) if out[0] != out[-1] else tuple(out[:-1])


@lru_cache(maxsize=1024)
def _rounded_border(rect: Box, radius: float) -> PolygonBorder:
    return PolygonBorder(rounded(rect, radius))


@lru_cache(maxsize=1024)
def _circle(rect: Box) -> EllipseBorder:
    l, t, r, b = rect
    return EllipseBorder((l + r) / 2, (t + b) / 2, (r - l) / 2, (b - t) / 2)


@lru_cache(maxsize=1024)
def _diamond(rect: Box) -> PolygonBorder:
    l, t, r, b = rect
    cx, cy = (l + r) / 2, (t + b) / 2
    return PolygonBorder(((cx, t), (r, cy), (cx, b), (l, cy)))


class _Solid(Shape):
    """사각형이 아닌 모양. 요소끼리 겹치는지도 자리 사각형이 아니라 실제 테두리로 본다. 요소 스테레오타입은 받지 않는다."""

    stereotyped = False

    def parts(self, e: Element, rect: Box) -> tuple[Border, ...]:
        return (self.border(e, rect),)


class _Fixed(_Solid):
    """이름이 없고 크기가 정해진 모양(시작·끝 점, 마름모)."""

    named = False
    sized = False
    SIZE = (0.0, 0.0)

    def size(self, e: Element) -> tuple[float, float]:
        return self.SIZE


class StartShape(_Fixed):
    """시작 점: 검게 칠한 원."""

    SIZE = (START, START)

    def border(self, e: Element, rect: Box) -> Border:
        return _circle(rect)

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        l, t, r, b = p.rect
        c.ellipse(l, t, r - l, b - t, fill="black", owner=p.key)


class FinalShape(_Fixed):
    """끝 점: 흰 바탕의 큰 원 안에 검게 칠한 작은 원을 둔 과녁. 선은 큰 원에 닿는다."""

    SIZE = (FINAL, FINAL)

    def border(self, e: Element, rect: Box) -> Border:
        return _circle(rect)

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        l, t, r, b = p.rect
        c.ellipse(l, t, r - l, b - t, owner=p.key)
        inset = (FINAL - FINAL_CORE) / 2
        c.ellipse(l + inset, t + inset, FINAL_CORE, FINAL_CORE, fill="black", owner=p.key)


class DiamondShape(_Fixed):
    """마름모(선택·결정·합류). 선은 네 변에 닿고, 가운데를 향하는 가로·세로 선은 꼭짓점에 닿는다."""

    SIZE = (DIAMOND_SIZE, DIAMOND_SIZE)

    def corners(self, rect: Box) -> tuple[Point, ...]:
        return _diamond(rect).points

    def border(self, e: Element, rect: Box) -> Border:
        return _diamond(rect)

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        c.poly(self.corners(p.rect), owner=p.key)


class _RoundedShape(_Solid):
    """둥근 모서리 상자. 그린 다각형과 검사용 테두리가 같은 꼭짓점(rounded)이다."""

    RADIUS = 0.0

    def border(self, e: Element, rect: Box) -> Border:
        return _rounded_border(rect, self.RADIUS)

    def outline(self, c: Canvas, p: PlacedBox) -> None:
        c.poly(rounded(p.rect, self.RADIUS), owner=p.key)


def _centered(c: Canvas, p: PlacedBox, lines: tuple[str, ...], top: float, height: float, bold: bool) -> None:
    cx = (p.rect[0] + p.rect[2]) / 2
    for s, y in zip(lines, line_ys(top + height / 2, len(lines))):
        c.text(cx, y, s, bold=bold, anchor="mm", owner=p.key)


def _band(e: Element) -> float:
    """이름 줄을 쓰는 띠의 높이."""
    return NAME_BAND + LABEL_LINE * len(e.name)


class StateShape(_RoundedShape):
    """상태: 둥근 모서리 상자. 위쪽 이름 칸에 이름(굵게)을 쓰고, 동작 칸(actions)이 있으면 그 아래에 선을 긋고 받은 줄을 그대로
    쓴다. 안에 상태를 둘 수 있고(복합 상태), 안의 요소를 두는 칸은 이름 칸 아래다. 이름 칸은 이름 줄과 동작 칸을 함께 덮어, 그
    상태 안의 요소를 잇는 선이 지나가거나 그 선의 글자가 겹치면 안 된다. 이름 칸과 안의 요소 사이에는 선을 긋지 않는다 — 모양은
    안에 요소가 있는지 모르고(그리기는 요소 하나만 받는다), 자리 크기로 짐작하면 height를 준 단순 상태가 빈 복합 상태처럼 그려진다."""

    RADIUS = STATE_RADIUS
    holds = True
    fields = ("actions",)

    def read(self, r: Reader, o: dict, path: str, kind: Optional[str]) -> tuple[str, ...]:
        if "actions" not in o:
            return ()
        where = _at(path, "actions")
        got = [r.text(s, _at(where, i)) for i, s in enumerate(r.items(o["actions"], where))]
        return tuple(s for s in got if s is not None)

    def _actions(self, e: Element) -> tuple[str, ...]:
        return e.data or ()

    def zone_height(self, e: Element) -> float:
        """이름 칸 높이: 이름 띠와, 동작 칸이 있으면 그 칸."""
        acts = self._actions(e)
        return _band(e) + (SECTION_PAD + ROW * len(acts) if acts else 0)

    def size(self, e: Element) -> tuple[float, float]:
        rows = [math.ceil(T.text_width(s) + 2 * STATE_ROW_LEFT) for s in self._actions(e)]
        return max(MIN_WIDTH, head_width(head_lines(None, e.name)), *rows), self.zone_height(e)

    def insets(self, e: Element) -> Box:
        return 0.0, self.zone_height(e), 0.0, 0.0

    def name_zones(self, e: Element, rect: Box) -> tuple[NameZone, ...]:
        return (NameZone((rect[0], rect[1], rect[2], rect[1] + self.zone_height(e)), False),)

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        e, o = p.box, p.key
        l, t, r, _ = p.rect
        self.outline(c, p)
        band = _band(e)
        _centered(c, p, e.name, t, band, bold=True)
        acts = self._actions(e)
        if acts:  # 동작 칸이 있으면 자리는 이름 띠 아래로 SECTION_PAD + ROW 넘게 남아, 이 선은 모서리 호 밖에 닿지 않는다
            c.line([(l, t + band), (r, t + band)], owner=o)
            y = t + band + SECTION_PAD / 2 + ROW / 2
            for s in acts:
                c.text(l + STATE_ROW_LEFT, y, s, owner=o)
                y += ROW


class ActionShape(_RoundedShape):
    """행동: 상태보다 둥근 모서리 상자 가운데에 이름을 쓴다. 이름은 흔히 문장이라 굵게 쓰지 않는다."""

    RADIUS = ACTION_RADIUS

    def size(self, e: Element) -> tuple[float, float]:
        width = max(T.text_width(s) for s in e.name) + 2 * ACTION_SIDE
        return max(MIN_WIDTH, math.ceil(width)), _band(e)

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        self.outline(c, p)
        _centered(c, p, p.box.name, p.rect[1], p.height, bold=False)


START_POINT = StartShape()
FINAL_POINT = FinalShape()
DIAMOND = DiamondShape()
STATE = StateShape()
ACTION = ActionShape()


def parse_flow(spec: Spec, data: Any) -> Diagram:
    """공용 엔진으로 읽고, 시작 점으로 들어오는 선과 끝 점에서 나가는 선도 입력 오류로 알린다 — 시작 점은 나가기만, 끝 점은
    들어오기만 한다(from·to를 바꿔 쓴 입력이 합격한 그림으로 문서에 들어가지 않게). 이 규칙은 요소 종류를 알아야 볼 수 있어, 공용
    엔진이 읽기 문제와 자리 잡기 문제를 단계마다 모아 알리듯 읽기가 통과한 뒤 한 단계로 모아 알린다."""
    diagram = B.parse(spec, data)
    shape_of = {e.key: spec.shapes[e.kind] for e in diagram.boxes}
    problems = []
    for i, r in enumerate(diagram.relations):  # 읽기가 통과했으면 관계는 입력 차례 그대로 다 있다
        path, label = _at("relations", i), spec.relations[r.kind].label
        said = f"{label}{josa(label, '은', '는')}"
        if isinstance(shape_of[r.target], StartShape):
            problems.append(f"{_at(path, 'to')}: 시작 점({_show(r.target)})으로 들어오는 {said} 그릴 수 없다 — 시작 점은 "
                            "from에만 쓴다")
        if isinstance(shape_of[r.source], FinalShape):
            problems.append(f"{_at(path, 'from')}: 끝 점({_show(r.source)})에서 나가는 {said} 그릴 수 없다 — 끝 점은 to에만 쓴다")
    if problems:
        raise InputError(problems)
    return diagram


def ends_errors(spec: Spec) -> str:
    """parse_flow가 따로 모아 알리는 오류를 도구 설명 결과 절에 적는 문장. 두 그림 모두 관계 종류가 하나(전이·흐름)다."""
    (relation,) = spec.relations.values()
    said = f"{relation.label}{josa(relation.label, '은', '는')}"
    return f"시작 점으로 들어오거나 끝 점에서 나가는 {said} 그 밖의 입력이 맞을 때 따로 모아 알린다."
