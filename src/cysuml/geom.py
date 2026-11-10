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


def side(p: Point, q: Point, v: Point, eps: float) -> int:
    """v가 p→q 직선의 왼쪽이면 1, 오른쪽이면 -1, 직선에서 eps 안이면 0."""
    n = math.dist(p, q)
    d = 0.0 if n == 0 else ((q[0] - p[0]) * (v[1] - p[1]) - (q[1] - p[1]) * (v[0] - p[0])) / n
    return (d > eps) - (d < -eps)


def _within(p: Point, q: Point, v: Point, eps: float) -> bool:
    """직선 pq 위의 점 v가 선분 pq 범위(끝 포함)에 드는지."""
    return (min(p[0], q[0]) - eps <= v[0] <= max(p[0], q[0]) + eps
            and min(p[1], q[1]) - eps <= v[1] <= max(p[1], q[1]) + eps)


def touches(s: tuple[Point, Point], t: tuple[Point, Point], eps: float) -> bool:
    """두 선분이 만나는지 — 건너가거나, 닿거나, 한 직선 위에서 겹친다."""
    (p, q), (r, w) = s, t
    d1, d2, d3, d4 = side(p, q, r, eps), side(p, q, w, eps), side(r, w, p, eps), side(r, w, q, eps)
    if d1 * d2 < 0 and d3 * d4 < 0:
        return True
    return ((d1 == 0 and _within(p, q, r, eps)) or (d2 == 0 and _within(p, q, w, eps))
            or (d3 == 0 and _within(r, w, p, eps)) or (d4 == 0 and _within(r, w, q, eps)))


def inside(v: Point, polygon: tuple[Point, ...]) -> bool:
    """점이 다각형 안에 있는지. 변 위의 점은 어느 쪽으로 나올지 정하지 않는다(변은 touches로 따로 본다)."""
    x, y = v
    out = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[-1:] + polygon[:-1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            out = not out
    return out


def crossings(a: tuple[Point, ...], b: Optional[tuple[Point, ...]], eps: float) -> list[Point]:
    """꺾은선 a와 b가 서로 건너가는 점. b가 None이면 a가 제 몸을 건너가는 점이다.

    닿기만 하는 곳과 한 직선 위에서 포개지는 곳은 넣지 않는다. 꺾는 점이 다른 선 위에 딱 놓이면(정수 좌표에서 흔하다) 두 선분
    어느 쪽도 속끼리 건너가지 않으므로, 그 점의 앞뒤 점이 다른 선의 양쪽에 있는지로 건너감을 가린다.
    """
    same = b is None
    if b is None:
        b = a
    sa, sb = list(zip(a, a[1:])), list(zip(b, b[1:]))
    out = []
    for i, (p, q) in enumerate(sa):
        for j, (r, w) in enumerate(sb):
            if same and j <= i + 1:
                continue
            if side(p, q, r, eps) * side(p, q, w, eps) < 0 and side(r, w, p, eps) * side(r, w, q, eps) < 0:
                d = (q[0] - p[0]) * (w[1] - r[1]) - (q[1] - p[1]) * (w[0] - r[0])
                k = ((r[0] - p[0]) * (w[1] - r[1]) - (r[1] - p[1]) * (w[0] - r[0])) / d
                out.append(_lerp(p, q, k))
    out += _vertices_on_segments(a, b, same, eps)
    if not same:
        out += _vertices_on_segments(b, a, same, eps)
    for k in range(1, len(a) - 1):
        for m in range(k + 1 if same else 1, len(b) - 1):
            if math.dist(a[k], b[m]) <= eps and _interleaved(a[k], a[k - 1], a[k + 1], b[m - 1], b[m + 1], eps):
                out.append(a[k])
    return out


def _vertices_on_segments(a: tuple[Point, ...], b: tuple[Point, ...], same: bool, eps: float) -> list[Point]:
    """a의 꺾는 점이 b의 선분 속(끝이 아닌 곳)에 놓이고, 그 앞뒤 점이 그 선분의 양쪽에 있는 곳."""
    out = []
    for k in range(1, len(a) - 1):
        v = a[k]
        for j, (r, w) in enumerate(zip(b, b[1:])):
            if same and j in (k - 1, k):
                continue
            if (side(r, w, v, eps) == 0 and _within(r, w, v, eps) and math.dist(v, r) > eps and math.dist(v, w) > eps
                    and side(r, w, a[k - 1], eps) * side(r, w, a[k + 1], eps) < 0):
                out.append(v)
    return out


def _interleaved(v: Point, a0: Point, a1: Point, b0: Point, b1: Point, eps: float) -> bool:
    """두 꺾은선이 같은 꺾는 점 v를 지날 때 건너가는지 — v에서 a의 두 갈래 사이를 b의 갈래가 하나만 지나면 건너간다.
    갈래 방향이 겹치면(한 직선 위에서 포개진다) 건너가지 않는 것으로 본다."""
    def angle(x: Point) -> float:
        return math.atan2(x[1] - v[1], x[0] - v[0])

    base = angle(a0)
    sweep = (angle(a1) - base) % math.tau
    rel = [(angle(x) - base) % math.tau for x in (b0, b1)]
    tiny = eps / max(math.dist(v, x) for x in (a0, a1, b0, b1))
    if any(min(abs(r), math.tau - abs(r), abs(r - sweep)) <= tiny for r in rel):
        return False
    return (rel[0] < sweep) != (rel[1] < sweep)


def alongside(s: tuple[Point, Point], t: tuple[Point, Point], gap: float, least: float,
              parallel: float) -> Optional[tuple[Point, Point]]:
    """선분 t 가운데 선분 s와 나란히(사이 각의 사인이 parallel 안) gap 안으로 붙어 가는 부분. 나란하지 않거나 그 부분의 길이가
    least 이하면 None."""
    (p, q), (r, w) = s, t
    ls, lt = math.dist(p, q), math.dist(r, w)
    if ls == 0 or lt == 0:
        return None
    ux, uy = (q[0] - p[0]) / ls, (q[1] - p[1]) / ls
    if abs(ux * (w[1] - r[1]) - uy * (w[0] - r[0])) / lt > parallel:
        return None

    def along(v: Point) -> float:
        return (v[0] - p[0]) * ux + (v[1] - p[1]) * uy

    def off(v: Point) -> float:
        return ux * (v[1] - p[1]) - uy * (v[0] - p[0])

    lo, hi = 0.0, 1.0  # t 위의 자리(r에서 0, w에서 1)
    for c, k, low, high in ((along(r), along(w) - along(r), 0.0, ls), (off(r), off(w) - off(r), -gap, gap)):
        if k == 0:
            if not low <= c <= high:
                return None
            continue
        t1, t2 = sorted(((low - c) / k, (high - c) / k))
        lo, hi = max(lo, t1), min(hi, t2)
    if (hi - lo) * lt <= least:
        return None
    return _lerp(r, w, lo), _lerp(r, w, hi)


def _lerp(p: Point, q: Point, t: float) -> Point:
    return p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
