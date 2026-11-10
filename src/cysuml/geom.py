"""상자(왼, 위, 오른, 아래)와 선분의 기하.

선 글자 자리를 고르는 쪽(classdiagram)과 검사(classcheck)가 같은 판정을 쓰게 한곳에 둔다 — 둘이 다르면 도구가 빈 자리로
고른 글자를 검사가 걸러 낸다.
"""
from __future__ import annotations

import bisect
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

    두 선이 닿은 곳(한 점이든, 한 직선 위를 같이 가는 구간이든)마다 a가 그곳에 들어오기 전과 나간 뒤가 b의 다른 쪽에 있으면
    건너간 것이다. 그래서 꺾는 점이 다른 선 위에 딱 놓이거나(정수 좌표에서 흔하다) 짧게 같이 가다 나가도 건너감으로 센다. 닿기만
    하고 같은 쪽으로 돌아가는 곳과 어느 한 선이 닿은 채 끝나는 곳은 넣지 않는다. 같이 가는 구간은 그 가운데 점으로 낸다.
    """
    same = b is None
    if b is None:
        b = a
    ca, cb = _lengths(a), _lengths(b)
    contacts = []
    for i in range(len(a) - 1):
        for j in range(len(b) - 1):
            if same and j <= i + 1:
                continue
            c = _contact((a[i], a[i + 1]), (b[j], b[j + 1]), eps)
            if c is not None:
                (k0, k1), (m0, m1) = c
                la, lb = ca[i + 1] - ca[i], cb[j + 1] - cb[j]
                contacts.append((_snap(ca, ca[i] + k0 * la, eps), _snap(ca, ca[i] + k1 * la, eps),
                                 _snap(cb, cb[j] + m0 * lb, eps), _snap(cb, cb[j] + m1 * lb, eps)))
    return [_at(a, ca, (sa0 + sa1) / 2) for sa0, sa1, sb0, sb1 in _components(contacts, eps)
            if _crosses(a, ca, b, cb, sa0, sa1, sb0, sb1, eps)]


def _lengths(pts: tuple[Point, ...]) -> list[float]:
    out = [0.0]
    for p, q in zip(pts, pts[1:]):
        out.append(out[-1] + math.dist(p, q))
    return out


def _snap(cum: list[float], s: float, eps: float) -> float:
    """선 위의 자리 s(처음부터의 길이)가 꺾는 점에서 eps 안이면 그 꺾는 점의 자리로."""
    i = bisect.bisect_left(cum, s)
    for k in (i - 1, i):
        if 0 <= k < len(cum) and abs(cum[k] - s) <= eps:
            return cum[k]
    return s


def _at(pts: tuple[Point, ...], cum: list[float], s: float) -> Point:
    k = min(max(bisect.bisect_right(cum, s) - 1, 0), len(pts) - 2)
    n = cum[k + 1] - cum[k]
    return _lerp(pts[k], pts[k + 1], 0.0 if n == 0 else (s - cum[k]) / n)


def _unit(p: Point, q: Point) -> Point:
    n = math.dist(p, q)
    return (q[0] - p[0]) / n, (q[1] - p[1]) / n


def _back(pts: tuple[Point, ...], cum: list[float], s: float) -> Point:
    """자리 s에서 선을 거슬러 가는 방향(s 바로 앞 선분)."""
    k = min(max(bisect.bisect_left(cum, s) - 1, 0), len(pts) - 2)
    return _unit(pts[k + 1], pts[k])


def _ahead(pts: tuple[Point, ...], cum: list[float], s: float) -> Point:
    """자리 s에서 선을 따라가는 방향(s 바로 뒤 선분)."""
    k = min(max(bisect.bisect_right(cum, s) - 1, 0), len(pts) - 2)
    return _unit(pts[k], pts[k + 1])


def _clamp(v: float) -> float:
    return min(max(v, 0.0), 1.0)


def _contact(s: tuple[Point, Point], t: tuple[Point, Point],
             eps: float) -> Optional[tuple[tuple[float, float], tuple[float, float]]]:
    """두 선분이 만나는 부분: s 위의 자리 구간 (k0, k1)과 그 두 점의 t 위 자리 (m0, m1)(모두 0~1). 만나지 않으면 None."""
    if not touches(s, t, eps):
        return None
    (p, q), (r, w) = s, t
    ux, uy, vx, vy = q[0] - p[0], q[1] - p[1], w[0] - r[0], w[1] - r[1]
    if (side(p, q, r, eps) == 0 and side(p, q, w, eps) == 0) or (side(r, w, p, eps) == 0 and side(r, w, q, eps) == 0):
        ll, mm = ux * ux + uy * uy, vx * vx + vy * vy
        kr = ((r[0] - p[0]) * ux + (r[1] - p[1]) * uy) / ll
        kw = ((w[0] - p[0]) * ux + (w[1] - p[1]) * uy) / ll
        k0, k1 = _clamp(min(kr, kw)), _clamp(max(kr, kw))

        def onto_t(k: float) -> float:
            x, y = p[0] + ux * k, p[1] + uy * k
            return _clamp(((x - r[0]) * vx + (y - r[1]) * vy) / mm)

        return (k0, k1), (onto_t(k0), onto_t(k1))
    d = ux * vy - uy * vx
    if d == 0:
        return None
    k = _clamp(((r[0] - p[0]) * vy - (r[1] - p[1]) * vx) / d)
    m = _clamp(((r[0] - p[0]) * uy - (r[1] - p[1]) * ux) / d)
    return (k, k), (m, m)


def _components(contacts: list[tuple[float, float, float, float]], eps: float) -> list[tuple[float, float, float, float]]:
    """닿은 부분들을 a와 b 위에서 함께 이어지는 것끼리 묶는다. 묶음마다 (a 위 처음, a 위 끝, 그 처음의 b 위 자리, 그 끝의
    b 위 자리)다."""
    out: list[tuple[float, float, float, float]] = []
    for c in sorted(contacts):
        for k, (sa0, sa1, sb0, sb1) in enumerate(out):
            if c[0] <= sa1 + eps and abs(c[2] - sb1) <= eps:
                out[k] = (sa0, c[1], sb0, c[3]) if c[1] > sa1 else (sa0, sa1, sb0, sb1)
                break
        else:
            out.append(c)
    return out


def _left(x: Point, start: Point, end: Point) -> Optional[bool]:
    """방향 x가 start에서 end까지 한쪽으로 돌아가는 사이에 드는지. x가 start나 end와 같은 방향이면 None."""
    base = math.atan2(start[1], start[0])
    sweep = (math.atan2(end[1], end[0]) - base) % math.tau
    r = (math.atan2(x[1], x[0]) - base) % math.tau
    if min(r, math.tau - r) <= 1e-9 or abs(r - sweep) <= 1e-9:
        return None
    return r < sweep


def _crosses(a: tuple[Point, ...], ca: list[float], b: tuple[Point, ...], cb: list[float],
             sa0: float, sa1: float, sb0: float, sb1: float, eps: float) -> bool:
    """닿은 묶음에서 a가 b를 건너가는지. b를 P(a가 들어오는 끝)에서 Q(a가 나가는 끝)로 가는 선으로 보고, a가 들어오기 전
    방향이 P에서 b의 어느 쪽인지와 나간 뒤 방향이 Q에서 b의 어느 쪽인지를 견준다."""
    if sa0 <= eps or sa1 >= ca[-1] - eps or min(sb0, sb1) <= eps or max(sb0, sb1) >= cb[-1] - eps:
        return False
    a_in, a_out = _back(a, ca, sa0), _ahead(a, ca, sa1)
    if sa1 - sa0 <= eps:
        b_in, b_out = _back(b, cb, sb0), _ahead(b, cb, sb0)
        sides = _left(a_in, b_out, b_in), _left(a_out, b_out, b_in)
    else:
        run_p, run_q = _ahead(a, ca, sa0), _back(a, ca, sa1)
        bp, bq = (_back(b, cb, sb0), _ahead(b, cb, sb1)) if sb0 <= sb1 else (_ahead(b, cb, sb0), _back(b, cb, sb1))
        sides = _left(a_in, run_p, bp), _left(a_out, bq, run_q)
    return None not in sides and sides[0] != sides[1]


def alongside(s: tuple[Point, Point], t: tuple[Point, Point], width: float, least: float,
              parallel: float) -> Optional[tuple[Point, Point]]:
    """선분 t 가운데 선분 s와 나란히(사이 각의 사인이 parallel 안) width 안으로 붙어 가는 부분. 나란하지 않거나 그 부분의 길이가
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
    for c, k, low, high in ((along(r), along(w) - along(r), 0.0, ls), (off(r), off(w) - off(r), -width, width)):
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
