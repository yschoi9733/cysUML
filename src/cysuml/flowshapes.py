"""상태도·액티비티도가 함께 쓰는 요소 모양: 시작 점, 끝 점(과녁), 마름모(선택·결정·합류), 둥근 모서리 상자(상태·행동).

그림판에는 둥근 모서리 상자가 없다. 모서리 호를 짧은 선분으로 나눈 다각형으로 그리고, 같은 꼭짓점을 검사용 테두리로 넘긴다 —
그린 것과 검사하는 테두리가 같다. 시작·끝 점과 마름모는 이름이 없어 관계·in이 id로 가리키고, 크기가 정해져 있다.
"""
from __future__ import annotations

import math
from typing import Optional

from . import text as T
from .boxdiagram import LABEL_LINE, Element, NameZone, PlacedBox, Shape, line_ys
from .canvas import Canvas, Point
from .classdiagram import MIN_WIDTH, NAME_PAD, ROW, SECTION_PAD
from .geom import Border, EllipseBorder, PolygonBorder
from .parsing import Reader
from .parsing import at as _at
from .text import Box

START = 20         # 시작 점 지름
FINAL = 24         # 끝 점 바깥 원 지름
FINAL_CORE = 14    # 끝 점 안쪽 칠한 원 지름
DIAMOND_SIZE = 30  # 선택·결정·합류 마름모의 폭·높이
ARC_STEPS = 6      # 둥근 모서리 호 하나를 나누는 선분 수
STATE_RADIUS = 10  # 상태 모서리 반지름
ACTION_RADIUS = 16  # 행동 모서리 반지름(상태보다 둥글다)
NAME_BAND = 25     # 상태·행동 이름 칸에서 이름 줄 밖에 더하는 높이(위아래 반씩) — 이름 한 줄이면 40
ACTION_LEFT = 8    # 상태 동작 줄의 왼쪽 여백(오른쪽도 같게 폭에 더한다) — 둥근 모서리에 글자가 닿지 않게
ACTION_SIDE = 20   # 행동 이름 좌우 여백(둥근 모서리에 글자가 닿지 않게)

_QUARTER = tuple((math.cos(math.pi / 2 * i / ARC_STEPS), math.sin(math.pi / 2 * i / ARC_STEPS)) for i in range(ARC_STEPS + 1))
_QUARTER = ((1.0, 0.0),) + _QUARTER[1:-1] + ((0.0, 1.0),)  # 호 끝은 곧은 변과 정확히 맞물리게


def rounded(rect: Box, radius: float) -> tuple[Point, ...]:
    """둥근 모서리 상자의 꼭짓점(위 변 오른쪽 끝에서 시계 방향). 모서리마다 반지름 radius인 4분원을 ARC_STEPS개 선분으로 나눈다.
    상자가 반지름의 두 배보다 작으면 반지름을 줄인다."""
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


class _Fixed(Shape):
    """이름이 없고 크기가 정해진 모양(시작·끝 점, 마름모). 겹침은 실제 테두리로 본다."""

    named = False
    sized = False
    stereotyped = False
    SIZE = (0.0, 0.0)

    def size(self, e: Element) -> tuple[float, float]:
        return self.SIZE

    def parts(self, e: Element, rect: Box) -> tuple[Border, ...]:
        return (self.border(e, rect),)


def _circle(rect: Box) -> EllipseBorder:
    l, t, r, b = rect
    return EllipseBorder((l + r) / 2, (t + b) / 2, (r - l) / 2, (b - t) / 2)


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
        l, t, r, b = rect
        cx, cy = (l + r) / 2, (t + b) / 2
        return (cx, t), (r, cy), (cx, b), (l, cy)

    def border(self, e: Element, rect: Box) -> Border:
        return PolygonBorder(self.corners(rect))

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        c.poly(self.corners(p.rect), owner=p.key)


class _RoundedShape(Shape):
    """둥근 모서리 상자. 그린 다각형과 검사용 테두리가 같은 꼭짓점(rounded)이다."""

    RADIUS = 0.0
    stereotyped = False

    def border(self, e: Element, rect: Box) -> Border:
        return PolygonBorder(rounded(rect, self.RADIUS))

    def parts(self, e: Element, rect: Box) -> tuple[Border, ...]:
        return (self.border(e, rect),)

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
    상태 안의 요소를 잇는 선이 지나가거나 그 선의 글자가 겹치면 안 된다. 이름 칸 아래에 자리가 남으면(복합 상태) 경계에 선을 긋는다."""

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
        widths = [T.text_width(s, True) + NAME_PAD for s in e.name] + [
            T.text_width(s) + 2 * ACTION_LEFT for s in self._actions(e)]
        return max(MIN_WIDTH, math.ceil(max(widths))), self.zone_height(e)

    def insets(self, e: Element) -> Box:
        return 0.0, self.zone_height(e), 0.0, 0.0

    def name_zones(self, e: Element, rect: Box) -> tuple[NameZone, ...]:
        return (NameZone((rect[0], rect[1], rect[2], rect[1] + self.zone_height(e)), False),)

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        e, o = p.box, p.key
        l, t, r, b = p.rect
        self.outline(c, p)
        band = _band(e)
        _centered(c, p, e.name, t, band, bold=True)
        acts = self._actions(e)
        if acts:
            c.line([(l, t + band), (r, t + band)], owner=o)
            y = t + band + SECTION_PAD / 2 + ROW / 2
            for s in acts:
                c.text(l + ACTION_LEFT, y, s, owner=o)
                y += ROW
        bottom = t + self.zone_height(e)
        if b - bottom > 1e-6:
            c.line([(l, bottom), (r, bottom)], owner=o)


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
