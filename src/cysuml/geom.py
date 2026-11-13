"""상자(왼, 위, 오른, 아래)와 선분, 요소 테두리(사각형·타원·볼록 다각형)의 기하.

선 글자 자리를 고르는 쪽(boxdiagram)과 검사(boxcheck)가 같은 판정을 쓰게 한곳에 둔다 — 둘이 다르면 도구가 빈 자리로
고른 글자를 검사가 걸러 낸다.
"""
from __future__ import annotations

import bisect
import math
from typing import Iterable, Optional

from .canvas import Box, Line, Point, Polygon, Record

Segment = tuple[Point, Point]
ELLIPSE_SIDES = 96  # 타원을 판정할 때 쓰는 다각형의 변 수. 반지름 100px에서 실제 타원과 0.06px 안으로 다르다


def grow(rect: Box, m: float) -> Box:
    return rect[0] - m, rect[1] - m, rect[2] + m, rect[3] + m


def gap(a: Box, b: Box) -> float:
    """두 상자 사이 거리. 겹치거나 맞닿으면 -1."""
    dx = max(b[0] - a[2], a[0] - b[2], 0)
    dy = max(b[1] - a[3], a[1] - b[3], 0)
    return -1 if dx == 0 and dy == 0 else math.hypot(dx, dy)


def axis_gap(a: Box, b: Box) -> float:
    """두 상자가 가로·세로 가운데 더 떨어진 쪽의 틈. 0이면 맞닿고, 음수면 가로·세로 모두 겹친다."""
    return max(b[0] - a[2], a[0] - b[2], b[1] - a[3], a[1] - b[3])


def meets(a: Box, b: Box) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def overlap(a: Box, b: Box, pad: float = 0.0, eps: float = 0.0) -> bool:
    """a를 사방으로 pad만큼 넓히면 b와 겹치는지. 맞닿는 것과 eps 안으로만 걸치는 것은 치지 않는다."""
    return (a[0] - pad < b[2] - eps and b[0] < a[2] + pad - eps
            and a[1] - pad < b[3] - eps and b[1] < a[3] + pad - eps)


def between(a: Box, b: Box) -> Box:
    """두 상자가 겹친 곳. 떨어져 있으면 둘 사이 빈 곳(가로·세로 가운데 떨어진 쪽은 그 틈, 겹친 쪽은 겹친 폭)."""
    x0, x1 = sorted((max(a[0], b[0]), min(a[2], b[2])))
    y0, y1 = sorted((max(a[1], b[1]), min(a[3], b[3])))
    return x0, y0, x1, y1


def _narrow(lo: float, hi: float, c: float, k: float, low: float, high: float) -> Optional[tuple[float, float]]:
    """선분 위 자리 t의 구간 [lo, hi]를, t에 따라 c + k·t로 바뀌는 값이 [low, high] 안인 곳으로 좁힌다. 남는 곳이 없으면 None."""
    if k == 0:
        return (lo, hi) if low <= c <= high else None
    t1, t2 = sorted(((low - c) / k, (high - c) / k))
    lo, hi = max(lo, t1), min(hi, t2)
    return (lo, hi) if lo <= hi else None


def clip(p: Point, q: Point, rect: Box) -> Optional[tuple[Point, Point]]:
    """선분 pq 가운데 상자 rect 안(변 포함)에 든 부분. 닿지 않으면 None."""
    span_t: Optional[tuple[float, float]] = (0.0, 1.0)
    for a, d, low, high in ((p[0], q[0] - p[0], rect[0], rect[2]), (p[1], q[1] - p[1], rect[1], rect[3])):
        span_t = _narrow(*span_t, a, d, low, high)
        if span_t is None:
            return None
    return lerp(p, q, span_t[0]), lerp(p, q, span_t[1])


def hits(p: Point, q: Point, rect: Box) -> bool:
    """선분 pq가 상자 rect를 지나거나 닿는지."""
    return clip(p, q, rect) is not None


def span(points: Iterable[Point]) -> Box:
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


def enters(s: tuple[Point, Point], polygon: tuple[Point, ...], margin: float) -> bool:
    """선분 s가 볼록 다각형 안쪽으로 margin 넘게 들어가는지. 테두리를 따라가거나 꼭짓점에 닿기만 하면 들어간 게 아니다."""
    area = sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(polygon, polygon[1:] + polygon[:1]))
    sign = 1 if area > 0 else -1
    (a, b) = s
    lo, hi = 0.0, 1.0
    for p, q in zip(polygon, polygon[1:] + polygon[:1]):
        ex, ey = q[0] - p[0], q[1] - p[1]
        n = math.hypot(ex, ey)

        def inward(v: Point) -> float:
            return sign * (ex * (v[1] - p[1]) - ey * (v[0] - p[0])) / n

        da, db = inward(a), inward(b)
        if da == db:
            if da <= margin:
                return False
            continue
        t = (margin - da) / (db - da)  # s 위에서 이 변으로부터 안쪽 margin이 되는 자리
        if db > da:
            lo = max(lo, t)
        else:
            hi = min(hi, t)
        if lo >= hi:
            return False
    return True


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
    return lerp(pts[k], pts[k + 1], 0.0 if n == 0 else (s - cum[k]) / n)


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

    span_t: Optional[tuple[float, float]] = (0.0, 1.0)  # t 위의 자리(r에서 0, w에서 1)
    for c, k, low, high in ((along(r), along(w) - along(r), 0.0, ls), (off(r), off(w) - off(r), -width, width)):
        span_t = _narrow(*span_t, c, k, low, high)
        if span_t is None:
            return None
    if (span_t[1] - span_t[0]) * lt <= least:
        return None
    return lerp(r, w, span_t[0]), lerp(r, w, span_t[1])


def lerp(p: Point, q: Point, t: float) -> Point:
    return p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t


def distance(s: tuple[Point, Point], t: tuple[Point, Point], eps: float) -> float:
    """두 선분 사이의 가장 짧은 거리(만나면 0)."""
    if touches(s, t, eps):
        return 0.0
    return min(_to_segment(v, seg) for v, seg in ((s[0], t), (s[1], t), (t[0], s), (t[1], s)))


def _to_segment(v: Point, seg: tuple[Point, Point]) -> float:
    (p, q) = seg
    n = (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2
    k = 0.0 if n == 0 else min(max(((v[0] - p[0]) * (q[0] - p[0]) + (v[1] - p[1]) * (q[1] - p[1])) / n, 0.0), 1.0)
    return math.dist(v, lerp(p, q, k))


def segment_gap(box: Box, s: Segment) -> float:
    """선분과 상자 사이 거리. 만나거나 닿으면 -1(gap과 같은 꼴)."""
    if hits(*s, box):
        return -1
    return min(distance(s, e, 0.0) for e in rect_edges(box))


def rect_edges(r: Box) -> tuple[Segment, ...]:
    l, t, rt, b = r
    return ((l, t), (rt, t)), ((rt, t), (rt, b)), ((rt, b), (l, b)), ((l, b), (l, t))


class Border:
    """요소의 볼록한 테두리 — 선이 닿는 곳이고, 선·글자가 그 요소를 지나는지 보는 곳이다. 사각형(RectBorder)·타원
    (EllipseBorder)·볼록 다각형(PolygonBorder)이 있다. 사각형은 클래스도가 쓰던 상자 판정을 그대로 쓴다."""

    @property
    def bounds(self) -> Box:
        raise NotImplementedError

    @property
    def empty(self) -> bool:
        """좁혀서 넓이가 없어졌는지."""
        return False

    def center(self) -> Point:
        raise NotImplementedError

    def exit(self, inside: Point, toward: Point) -> Optional[Point]:
        """테두리 안 inside에서 toward로 가는 선이 테두리와 만나는 점. toward가 안이나 테두리 위면 None."""
        raise NotImplementedError

    def grown(self, m: float) -> Border:
        """사방으로 m만큼 넓힌(음수면 좁힌) 테두리. 다각형 꼭짓점은 변을 늘여 만나는 자리로 간다(사각형을 넓힌 것과 같은 꼴)."""
        raise NotImplementedError

    def clip(self, p: Point, q: Point) -> Optional[Segment]:
        """선분 pq 가운데 테두리 안(테두리 위 포함)에 든 부분. 닿지 않으면 None."""
        raise NotImplementedError

    def hits(self, p: Point, q: Point) -> bool:
        return self.clip(p, q) is not None

    def holds(self, v: Point) -> bool:
        """점이 테두리 안에 있는지(테두리 위는 빼고)."""
        raise NotImplementedError

    def edges(self) -> tuple[Segment, ...]:
        raise NotImplementedError

    def meets(self, box: Box) -> bool:
        """상자와 겹치거나 닿는지."""
        raise NotImplementedError

    def gap(self, box: Box) -> float:
        """상자와 떨어진 거리. 겹치거나 닿으면 -1."""
        raise NotImplementedError


class RectBorder(Border):
    def __init__(self, rect: Box):
        self.rect = rect

    def __repr__(self) -> str:
        return f"RectBorder({self.rect})"

    def __eq__(self, other) -> bool:
        return isinstance(other, RectBorder) and other.rect == self.rect

    def __hash__(self) -> int:
        return hash(self.rect)

    @property
    def bounds(self) -> Box:
        return self.rect

    @property
    def empty(self) -> bool:
        return self.rect[0] >= self.rect[2] or self.rect[1] >= self.rect[3]

    def center(self) -> Point:
        return (self.rect[0] + self.rect[2]) / 2, (self.rect[1] + self.rect[3]) / 2

    def exit(self, inside: Point, toward: Point) -> Optional[Point]:
        (x1, y1), (x2, y2) = inside, toward
        l, t, r, b = self.rect
        ks = []
        if x2 != x1:
            ks.append(((r if x2 > x1 else l) - x1) / (x2 - x1))
        if y2 != y1:
            ks.append(((b if y2 > y1 else t) - y1) / (y2 - y1))
        if not ks or min(ks) >= 1:
            return None
        k = min(ks)
        return x1 + (x2 - x1) * k, y1 + (y2 - y1) * k

    def grown(self, m: float) -> RectBorder:
        return RectBorder(grow(self.rect, m))

    def clip(self, p: Point, q: Point) -> Optional[Segment]:
        return clip(p, q, self.rect)

    def holds(self, v: Point) -> bool:
        l, t, r, b = self.rect
        return l < v[0] < r and t < v[1] < b

    def edges(self) -> tuple[Segment, ...]:
        return rect_edges(self.rect)

    def meets(self, box: Box) -> bool:
        return meets(box, self.rect)

    def gap(self, box: Box) -> float:
        return gap(box, self.rect)


class PolygonBorder(Border):
    """볼록 다각형. 꼭짓점 차례는 어느 쪽으로 돌아도 된다."""

    def __init__(self, points: Iterable[Point], empty: bool = False):
        pts = _distinct(tuple((float(x), float(y)) for x, y in points))
        if len(pts) < 3 or _area(pts) == 0:
            raise ValueError(f"넓이가 있는 볼록 다각형이어야 한다: {pts}")
        self.points = pts
        self._sign = 1 if _area(pts) > 0 else -1
        self._empty = empty
        self._edges = tuple(zip(pts, pts[1:] + pts[:1]))

    def __repr__(self) -> str:
        return f"PolygonBorder({self.points})"

    def __eq__(self, other) -> bool:
        return isinstance(other, PolygonBorder) and other.points == self.points and other._empty == self._empty

    def __hash__(self) -> int:
        return hash((self.points, self._empty))

    @property
    def bounds(self) -> Box:
        return span(self.points)

    @property
    def empty(self) -> bool:
        return self._empty

    def center(self) -> Point:
        """넓이 중심 — 볼록 다각형이면 늘 안에 있다."""
        pts = self.points
        a = cx = cy = 0.0
        for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
            w = x1 * y2 - x2 * y1
            a += w
            cx += (x1 + x2) * w
            cy += (y1 + y2) * w
        return cx / (3 * a), cy / (3 * a)

    def _inward(self, a: Point, b: Point, v: Point) -> float:
        """v가 변 ab에서 안쪽으로 들어간 거리(바깥이면 음수)."""
        ex, ey = b[0] - a[0], b[1] - a[1]
        return self._sign * (ex * (v[1] - a[1]) - ey * (v[0] - a[0])) / math.hypot(ex, ey)

    def _span(self, p: Point, q: Point) -> Optional[tuple[float, float]]:
        """선 p + t(q - p)가 다각형 안(테두리 포함)에 드는 t 구간(0 이상). 없으면 None."""
        t_span: Optional[tuple[float, float]] = (0.0, math.inf)
        for a, b in self.edges():
            fp, fq = self._inward(a, b, p), self._inward(a, b, q)
            t_span = _narrow(*t_span, fp, fq - fp, 0.0, math.inf)
            if t_span is None:
                return None
        return t_span

    def exit(self, inside: Point, toward: Point) -> Optional[Point]:
        if inside == toward:
            return None
        found = self._span(inside, toward)
        if found is None or found[1] >= 1:
            return None
        return lerp(inside, toward, found[1])

    def grown(self, m: float) -> PolygonBorder:
        if self._empty:
            return self
        pts, n = self.points, len(self.points)
        lines = []
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            ex, ey = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(ex, ey)
            nx, ny = self._sign * ey / ln, -self._sign * ex / ln  # 바깥쪽 단위 법선
            lines.append(((a[0] + nx * m, a[1] + ny * m), (ex, ey)))
        out = []
        for i in range(n):
            (p, d), (q, e) = lines[i - 1], lines[i]
            k = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / (d[0] * e[1] - d[1] * e[0])
            out.append((p[0] + d[0] * k, p[1] + d[1] * k))
        # 좁히다 변이 뒤집히면(원래 변과 방향이 반대가 되면) 넓이가 없어진 것이다
        if any((b[0] - a[0]) * d[0] + (b[1] - a[1]) * d[1] <= 0
               for (a, b), (_, d) in zip(zip(out, out[1:] + out[:1]), lines)):
            return PolygonBorder(self.points, empty=True)
        return PolygonBorder(out)

    def clip(self, p: Point, q: Point) -> Optional[Segment]:
        if self._empty:
            return None
        if p == q:
            return (p, q) if all(self._inward(a, b, p) >= 0 for a, b in self.edges()) else None
        found = self._span(p, q)
        if found is None or found[0] > 1:
            return None
        return lerp(p, q, found[0]), lerp(p, q, min(found[1], 1.0))

    def holds(self, v: Point) -> bool:
        return not self._empty and all(self._inward(a, b, v) > 0 for a, b in self.edges())

    def edges(self) -> tuple[Segment, ...]:
        return self._edges

    def meets(self, box: Box) -> bool:
        if self._empty or not meets(self.bounds, box):
            return False
        corners = ((box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3]))
        # 상자 꼭짓점이 모두 한 변 바깥에 있으면 떨어져 있다(볼록 다각형과 상자의 분리 축 — 상자 축은 위 bounds가 본다)
        return all(any(self._inward(a, b, c) >= 0 for c in corners) for a, b in self.edges())

    def gap(self, box: Box) -> float:
        if self.meets(box):
            return -1
        return min(distance(s, e, 0.0) for s in self.edges() for e in rect_edges(box))


class EllipseBorder(Border):
    """타원. 선 끝은 실제 타원 위에 두고, 그 밖의 판정은 꼭짓점이 타원 위에 있는 ELLIPSE_SIDES각형으로 한다."""

    def __init__(self, cx: float, cy: float, rx: float, ry: float):
        if not (rx > 0 and ry > 0):
            raise ValueError(f"타원 반지름은 0보다 커야 한다: {rx}, {ry}")
        self.cx, self.cy, self.rx, self.ry = cx, cy, rx, ry
        self.polygon = PolygonBorder((cx + rx * math.cos(2 * math.pi * k / ELLIPSE_SIDES),
                                      cy + ry * math.sin(2 * math.pi * k / ELLIPSE_SIDES)) for k in range(ELLIPSE_SIDES))

    def __repr__(self) -> str:
        return f"EllipseBorder({self.cx}, {self.cy}, {self.rx}, {self.ry})"

    def __eq__(self, other) -> bool:
        return isinstance(other, EllipseBorder) and (other.cx, other.cy, other.rx, other.ry) == (
            self.cx, self.cy, self.rx, self.ry)

    def __hash__(self) -> int:
        return hash((self.cx, self.cy, self.rx, self.ry))

    @property
    def bounds(self) -> Box:
        return self.cx - self.rx, self.cy - self.ry, self.cx + self.rx, self.cy + self.ry

    def center(self) -> Point:
        return self.cx, self.cy

    def exit(self, inside: Point, toward: Point) -> Optional[Point]:
        ux, uy = (inside[0] - self.cx) / self.rx, (inside[1] - self.cy) / self.ry
        dx, dy = (toward[0] - inside[0]) / self.rx, (toward[1] - inside[1]) / self.ry
        a = dx * dx + dy * dy
        if a == 0:
            return None
        b, c = 2 * (ux * dx + uy * dy), ux * ux + uy * uy - 1
        disc = b * b - 4 * a * c
        if disc < 0:
            return None
        k = (-b + math.sqrt(disc)) / (2 * a)
        if not 0 < k < 1:
            return None
        return lerp(inside, toward, k)

    def grown(self, m: float) -> PolygonBorder:
        return self.polygon.grown(m)

    def clip(self, p: Point, q: Point) -> Optional[Segment]:
        return self.polygon.clip(p, q)

    def holds(self, v: Point) -> bool:
        return self.polygon.holds(v)

    def edges(self) -> tuple[Segment, ...]:
        return self.polygon.edges()

    def meets(self, box: Box) -> bool:
        return self.polygon.meets(box)

    def gap(self, box: Box) -> float:
        return self.polygon.gap(box)


def _area(pts: tuple[Point, ...]) -> float:
    return sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(pts, pts[1:] + pts[:1])) / 2


def _distinct(pts: tuple[Point, ...]) -> tuple[Point, ...]:
    """이웃한 같은 꼭짓점과 한 줄 위에 놓인 꼭짓점을 뺀다(변을 늘일 때 나란한 두 변이 만나는 자리를 못 구한다)."""
    out = [p for i, p in enumerate(pts) if p != pts[i - 1]]
    changed = True
    while changed and len(out) >= 3:
        changed = False
        for i in range(len(out)):
            a, b, c = out[i - 1], out[i], out[(i + 1) % len(out)]
            if (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]) == 0:
                del out[i]
                changed = True
                break
    return tuple(out)
