"""상자(왼, 위, 오른, 아래)와 선분의 기하.

선 글자 자리를 고르는 쪽(classdiagram)과 검사(classcheck)가 같은 판정을 쓰게 한곳에 둔다 — 둘이 다르면 도구가 빈 자리로
고른 글자를 검사가 걸러 낸다.
"""
from __future__ import annotations

import math
from typing import Iterable, Optional

from .canvas import Line, Point, Polygon, Record

Box = tuple[float, float, float, float]


def grow(rect: Box, m: float) -> Box:
    return rect[0] - m, rect[1] - m, rect[2] + m, rect[3] + m


def gap(a: Box, b: Box) -> float:
    """두 상자 사이 거리. 겹치거나 맞닿으면 -1."""
    dx = max(b[0] - a[2], a[0] - b[2], 0)
    dy = max(b[1] - a[3], a[1] - b[3], 0)
    return -1 if dx == 0 and dy == 0 else math.hypot(dx, dy)


def meets(a: Box, b: Box) -> bool:
    """두 상자가 겹치거나 맞닿는지."""
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def between(a: Box, b: Box) -> Box:
    """두 상자가 겹친 곳. 떨어져 있으면 둘 사이 빈 곳(가로·세로 가운데 떨어진 쪽은 그 틈, 겹친 쪽은 겹친 폭)."""
    x0, x1 = sorted((max(a[0], b[0]), min(a[2], b[2])))
    y0, y1 = sorted((max(a[1], b[1]), min(a[3], b[3])))
    return x0, y0, x1, y1


def clip(p: Point, q: Point, rect: Box) -> Optional[tuple[Point, Point]]:
    """선분 pq 가운데 상자 rect 안(변 포함)에 든 부분. 닿지 않으면 None."""
    lo, hi = 0.0, 1.0
    for a, d, low, high in ((p[0], q[0] - p[0], rect[0], rect[2]), (p[1], q[1] - p[1], rect[1], rect[3])):
        if d == 0:
            if not low <= a <= high:
                return None
            continue
        t1, t2 = sorted(((low - a) / d, (high - a) / d))
        lo, hi = max(lo, t1), min(hi, t2)
        if lo > hi:
            return None
    return _lerp(p, q, lo), _lerp(p, q, hi)


def hits(p: Point, q: Point, rect: Box) -> bool:
    """선분 pq가 상자 rect를 지나거나 닿는지."""
    return clip(p, q, rect) is not None


def span(points: Iterable[Point]) -> Box:
    """점들을 덮는 가장 작은 상자."""
    xs, ys = zip(*points)
    return min(xs), min(ys), max(xs), max(ys)


def outline(records: Iterable[Record]) -> list[tuple[Point, Point]]:
    """그림판 기록의 선·다각형 테두리를 선분으로."""
    out: list[tuple[Point, Point]] = []
    for r in records:
        if isinstance(r, Line):
            out += zip(r.points, r.points[1:])
        elif isinstance(r, Polygon):
            out += zip(r.points, r.points[1:] + r.points[:1])
    return out


def _lerp(p: Point, q: Point, t: float) -> Point:
    return p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
