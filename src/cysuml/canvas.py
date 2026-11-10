"""그림판: 논리 좌표(px)로 도형과 글자를 받아 기록하고, 그 기록만으로 PNG를 그린다.

그림을 기록에서 그리므로 검사가 읽는 기록(Canvas.records)과 그림이 어긋나지 않는다. 기록은 그림 배율과 상관없이
논리 좌표 그대로이고, owner는 그 도형이 속한 그림 요소의 이름으로 검사 결과에 쓴다. 잘못된 입력은 기록하기 전에
ValueError로 막는다. 그릴 때는 그린 것의 범위에 PAD만큼 여백을 두고(frame), SS배로 그린 뒤 줄여 선을 부드럽게 하고,
결과는 scale배(기본 SCALE) PNG로 낸다.
"""
from __future__ import annotations

import bisect
import math
import numbers
from dataclasses import dataclass, field, replace
from typing import Iterable, Optional, Union

from PIL import Image, ImageColor, ImageDraw

from . import text as T

SCALE = 1.6
MIN_SCALE = 0.25  # 이보다 작으면 글자가 FreeType이 그릴 수 있는 크기 밑으로 내려간다
SS = 4
PAD = 12
BG_MARGIN = 2
MIN_DASH = 0.5
MAX_DASHES = 100_000  # 점선 하나의 칸 수 상한(칸마다 그리기 호출이 하나씩 든다)
MAX_PIXELS = 150_000_000  # SS배로 그리는 그림판의 픽셀 수 상한(회색조라 1픽셀 1바이트). 기본 배율에서 논리 약 1900×1900

Point = tuple[float, float]
Box = T.Box


@dataclass(frozen=True)
class Line:
    points: tuple[Point, ...]
    dash: Optional[tuple[float, float]] = None
    owner: Optional[str] = None


@dataclass(frozen=True)
class Rect:
    left: float
    top: float
    width: float
    height: float
    fill: Optional[str] = "white"
    owner: Optional[str] = None


@dataclass(frozen=True)
class Ellipse:
    left: float
    top: float
    width: float
    height: float
    fill: Optional[str] = "white"
    owner: Optional[str] = None


@dataclass(frozen=True)
class Polygon:
    points: tuple[Point, ...]
    fill: Optional[str] = "white"
    owner: Optional[str] = None


@dataclass(frozen=True)
class Text:
    """한 줄 글자. text는 normalize한 글자다.

    bg는 글자 밑에 흰 바탕을 깔았다는 뜻이고, 그 바탕은 바로 앞의 Mask다. 칠할 글자가 없으면(공백뿐) 깔지 않고 bg도
    False다. placement는 글자를 놓은 결과로, 범위 계산과 그리기가 그대로 쓴다(주지 않으면 만들 때 놓는다).
    """

    x: float
    y: float
    text: str
    bold: bool
    anchor: str
    bg: bool = False
    owner: Optional[str] = None
    placement: T.Placement = field(default=None, compare=False, repr=False)  # type: ignore[assignment]

    def __post_init__(self):
        object.__setattr__(self, "text", T.normalize(self.text))
        if self.placement is None:
            object.__setattr__(self, "placement", T.place(self.x, self.y, self.text, self.bold, self.anchor))

    @property
    def box(self) -> Box:
        """줄 상자(text.Placement.box). 칠해지는 곳을 늘 덮는다."""
        return self.placement.box


@dataclass(frozen=True)
class Mask:
    """흰색으로 지운 곳(테두리 없음)."""

    left: float
    top: float
    right: float
    bottom: float
    owner: Optional[str] = None


Record = Union[Line, Rect, Ellipse, Polygon, Text, Mask]


def _nums(*values) -> tuple[float, ...]:
    if not all(isinstance(v, numbers.Real) and not isinstance(v, bool) and math.isfinite(v) for v in values):
        raise ValueError(f"좌표·크기는 유한한 수여야 한다: {values!r}")
    return tuple(float(v) for v in values)


def _point(p) -> Point:
    try:
        x, y = p
    except (TypeError, ValueError):
        raise ValueError(f"점은 (x, y)여야 한다: {p!r}") from None
    return _nums(x, y)


def _points(pts: Iterable[Point], least: int) -> tuple[Point, ...]:
    try:
        out = tuple(_point(p) for p in pts)
    except TypeError:
        raise ValueError(f"점 목록이 아니다: {pts!r}") from None
    if len(out) < least:
        raise ValueError(f"점이 {least}개 이상 있어야 한다: {out}")
    return out


def _line(pts: Iterable[Point], dash, owner: Optional[str]) -> Line:
    pts = _points(pts, 2)
    if all(a == b for a, b in zip(pts, pts[1:])):
        raise ValueError(f"길이가 0인 선이다: {pts}")
    if dash is not None:
        try:
            on, off = dash
        except (TypeError, ValueError):
            raise ValueError(f"점선 무늬는 (칠할 길이, 비울 길이)여야 한다: {dash!r}") from None
        dash = _nums(on, off)
        if min(dash) < MIN_DASH:
            raise ValueError(f"점선 무늬가 너무 짧다(최소 {MIN_DASH}): {dash}")
        if sum(math.dist(p, q) for p, q in zip(pts, pts[1:])) / sum(dash) > MAX_DASHES:
            raise ValueError(f"점선 칸이 너무 많다(최대 {MAX_DASHES}): 무늬 {dash}")
    return Line(pts, dash, owner)


def _box(left, top, width, height) -> tuple[float, float, float, float]:
    out = _nums(left, top, width, height)
    if out[2] < 0 or out[3] < 0:
        raise ValueError(f"크기가 음수다: {out[2]}×{out[3]}")
    return out


def _fill(fill: Optional[str]) -> Optional[str]:
    if fill is not None:
        if not isinstance(fill, str):
            raise ValueError(f"색은 이름이나 #RRGGBB 문자열이어야 한다: {fill!r}")
        ImageColor.getcolor(fill, "L")
    return fill


def _head(tip: Point, frm: Point, *sizes) -> tuple[Point, float, float, tuple[float, ...]]:
    """선 끝 장식의 자리: 확인한 tip, tip에서 frm으로 가는 단위 벡터, 확인한 크기들(모두 0보다 커야 한다)."""
    tip, frm = _point(tip), _point(frm)
    sizes = _nums(*sizes)
    if min(sizes) <= 0:
        raise ValueError(f"선 끝 장식의 크기는 0보다 커야 한다: {sizes}")
    dx, dy = frm[0] - tip[0], frm[1] - tip[1]
    n = math.hypot(dx, dy)
    if n == 0:
        raise ValueError(f"선 끝 장식의 방향을 정할 수 없다(두 점이 같다): {tip}")
    return tip, dx / n, dy / n, sizes


def _collinear(pts: tuple[Point, ...]) -> bool:
    (x0, y0), others = pts[0], pts[1:]
    far = next((p for p in others if p != pts[0]), None)
    if far is None:
        return True
    return all((far[0] - x0) * (y - y0) == (far[1] - y0) * (x - x0) for x, y in others)


class Canvas:
    def __init__(self, scale: float = SCALE):
        (scale,) = _nums(scale)
        if scale < MIN_SCALE:
            raise ValueError(f"배율은 {MIN_SCALE} 이상이어야 한다: {scale}")
        self.scale = scale
        self.records: list[Record] = []

    def line(self, pts: Iterable[Point], dash: Optional[tuple[float, float]] = None, owner: Optional[str] = None) -> None:
        """dash=(칠할 길이, 비울 길이)이면 점선이다(둘 다 MIN_DASH 이상). 무늬는 꺾는 점을 지나도 이어진다."""
        self.records.append(_line(pts, dash, owner))

    def rect(self, left: float, top: float, width: float, height: float, fill: Optional[str] = "white",
             owner: Optional[str] = None) -> None:
        self.records.append(Rect(*_box(left, top, width, height), _fill(fill), owner))

    def ellipse(self, left: float, top: float, width: float, height: float, fill: Optional[str] = "white",
                owner: Optional[str] = None) -> None:
        self.records.append(Ellipse(*_box(left, top, width, height), _fill(fill), owner))

    def poly(self, pts: Iterable[Point], fill: Optional[str] = "white", owner: Optional[str] = None) -> None:
        pts = _points(pts, 3)
        if _collinear(pts):
            raise ValueError(f"모든 점이 한 줄 위에 있어 넓이가 없는 다각형이다: {pts}")
        self.records.append(Polygon(pts, _fill(fill), owner))

    def text(self, x: float, y: float, s: str, bold: bool = False, anchor: str = "lm", bg: bool = False,
             owner: Optional[str] = None) -> None:
        """한 줄 글자. anchor와 y의 뜻은 text.place와 같다. bg면 글자가 칠해지는 곳보다 BG_MARGIN 넓게 흰 바탕을 깐다."""
        x, y = _nums(x, y)
        record = Text(x, y, s, bool(bold), anchor, False, owner)
        ink = record.placement.ink
        if bg and ink is not None:
            self.erase(ink[0] - BG_MARGIN, ink[1] - BG_MARGIN, ink[2] + BG_MARGIN, ink[3] + BG_MARGIN, owner=owner)
            record = replace(record, bg=True)
        self.records.append(record)

    def erase(self, left: float, top: float, right: float, bottom: float, owner: Optional[str] = None) -> None:
        left, top, right, bottom = _nums(left, top, right, bottom)
        if right < left or bottom < top:
            raise ValueError(f"지울 곳의 오른쪽·아래가 왼쪽·위보다 앞이다: {(left, top, right, bottom)}")
        self.records.append(Mask(left, top, right, bottom, owner))

    def open_arrow(self, tip: Point, frm: Point, size: float = 10, spread: float = math.radians(28),
                   owner: Optional[str] = None) -> None:
        """frm에서 tip으로 가는 선 끝의 열린 화살촉. 갈래 끝 → tip → 갈래 끝의 꺾은선 하나로 기록해 tip을 둥글게 잇는다.
        spread는 선과 갈래 사이 각(라디안, 직각 미만)이다."""
        tip, c, s, (size,) = _head(tip, frm, size)
        (spread,) = _nums(spread)
        if not 0 < spread < math.pi / 2:
            raise ValueError(f"화살촉 갈래 각은 0보다 크고 직각보다 작아야 한다: {spread}")
        ends = []
        for turn in (-spread, spread):
            ct, st = math.cos(turn), math.sin(turn)
            ends.append((tip[0] + size * (c * ct - s * st), tip[1] + size * (s * ct + c * st)))
        if tip in ends:
            raise ValueError(f"화살촉 갈래 길이가 0이다: {size}")
        self.records.append(_line([ends[0], tip, ends[1]], None, owner))

    def closed_arrow(self, tip: Point, frm: Point, filled: bool = True, size: float = 10, half: float = 4.5,
                     owner: Optional[str] = None) -> None:
        """닫힌 삼각형 화살촉. 기본값은 호출 메시지의 채운 화살촉이고, 상속·실체화의 빈 삼각형은 filled=False, size=18,
        half=9로 부른다."""
        tip, c, s, (size, half) = _head(tip, frm, size, half)
        base = (tip[0] + c * size, tip[1] + s * size)
        self.poly([tip, (base[0] - s * half, base[1] + c * half), (base[0] + s * half, base[1] - c * half)],
                  fill="black" if filled else "white", owner=owner)

    def diamond(self, tip: Point, frm: Point, filled: bool = True, size: float = 18, half: float = 6,
                owner: Optional[str] = None) -> None:
        """선 끝의 마름모. 채우면 합성, 비우면 집합이다."""
        tip, c, s, (size, half) = _head(tip, frm, size, half)
        mid = (tip[0] + c * size / 2, tip[1] + s * size / 2)
        far = (tip[0] + c * size, tip[1] + s * size)
        self.poly([tip, (mid[0] - s * half, mid[1] + c * half), far, (mid[0] + s * half, mid[1] - c * half)],
                  fill="black" if filled else "white", owner=owner)

    def bounds(self) -> Optional[Box]:
        """그린 것이 차지하는 논리 좌표 범위(왼, 위, 오른, 아래). 지운 곳과 공백뿐인 글자는 넣지 않고, 없으면 None."""
        xs: list[float] = []
        ys: list[float] = []
        for r in self.records:
            if isinstance(r, (Line, Polygon)):
                pts: Iterable[Point] = r.points
            elif isinstance(r, (Rect, Ellipse)):
                pts = ((r.left, r.top), (r.left + r.width, r.top + r.height))
            elif isinstance(r, Text):
                ink = r.placement.ink
                if ink is None:
                    continue
                pts = ((ink[0], ink[1]), (ink[2], ink[3]))
            else:
                continue
            for x, y in pts:
                xs.append(x)
                ys.append(y)
        return (min(xs), min(ys), max(xs), max(ys)) if xs else None

    def _frame_px(self) -> tuple[float, float, int, int]:
        b = self.bounds()
        if b is None:
            raise ValueError("그린 것이 없다")
        minx, miny = b[0] - PAD, b[1] - PAD
        fw, fh = (b[2] + PAD - minx) * self.scale, (b[3] + PAD - miny) * self.scale
        too_big = ValueError(f"그림이 너무 크다: 논리 {b[2] - b[0]:g}×{b[3] - b[1]:g}, 배율 {self.scale:g}")
        if not (math.isfinite(fw) and math.isfinite(fh)):
            raise too_big
        w, h = max(1, math.ceil(fw)), max(1, math.ceil(fh))
        if w * SS * h * SS > MAX_PIXELS:
            raise too_big
        return minx, miny, w, h

    def frame(self) -> Box:
        """결과 PNG가 덮는 논리 좌표 범위: 그린 것의 범위에 PAD만큼 여백을 두고, 오른쪽·아래를 출력 픽셀에 맞춰 늘린다.
        PNG의 픽셀 (px, py)는 논리 좌표 (frame[0] + px / scale, frame[1] + py / scale)다. 그린 것이 없거나 그림이
        MAX_PIXELS를 넘으면 ValueError."""
        minx, miny, w, h = self._frame_px()
        return minx, miny, minx + w / self.scale, miny + h / self.scale

    def to_image(self) -> Image.Image:
        minx, miny, w, h = self._frame_px()
        img = Image.new("L", (w * SS, h * SS), 255)
        _Painter(img, minx, miny, self.scale * SS).paint(self.records)
        return img.resize((w, h), Image.LANCZOS)

    def save(self, path) -> tuple[int, int]:
        out = self.to_image()
        out.save(path, format="PNG")
        return out.size


class _Painter:
    """기록을 SS배 그림판에 그린다. 테두리와 선은 모두 논리 좌표의 선·변을 가운데로 칠하고, 꺾는 점은 둥글게 잇는다."""

    def __init__(self, img: Image.Image, minx: float, miny: float, k: float):
        self.d = ImageDraw.Draw(img)
        self.minx, self.miny, self.k = minx, miny, k
        self.lw = max(1, round(k))

    def _p(self, p: Point) -> Point:
        return (p[0] - self.minx) * self.k, (p[1] - self.miny) * self.k

    @staticmethod
    def _pixels(x0: float, y0: float, x1: float, y1: float) -> Optional[list[tuple[int, int]]]:
        # Pillow 상자는 좌표를 정수로 자르고 오른쪽·아래 끝 픽셀을 포함한다. [x0, x1) 범위를 칠하게 반올림해 넘기고, 칠할
        # 픽셀이 없으면 None이다(round()는 .5를 짝수로 보내 앞뒤가 뒤집힐 수 있어 늘 올림 쪽으로 반올림한다).
        l, t, r, b = (math.floor(v + 0.5) for v in (x0, y0, x1, y1))
        return [(l, t), (r - 1, b - 1)] if r > l and b > t else None

    def _outlined(self, left: float, top: float, width: float, height: float) -> list[tuple[int, int]]:
        # Pillow는 상자 테두리를 안쪽으로 칠한다. 반 획씩 넓혀 선과 같이 변 가운데로 칠하게 한다(넓힌 폭이 1픽셀 이상이라
        # 비지 않는다).
        (x0, y0), (x1, y1) = self._p((left, top)), self._p((left + width, top + height))
        h = self.lw / 2
        return self._pixels(x0 - h, y0 - h, x1 + h, y1 + h)

    def _snap(self, p: Point) -> tuple[int, int]:
        # Pillow 선은 좌표를 정수로 자르고 짝수 굵기를 아래·오른쪽으로 치우쳐 칠한다. 칠할 첫 픽셀을 상자(_pixels)와 같은
        # 반올림으로 정하고, Pillow가 그 픽셀부터 칠하게 되는 정수 좌표로 넘긴다(가로·세로 선에서 굵기 1~12로 재 맞춘 식).
        o = (self.lw - 1) // 2
        return math.floor(p[0] - self.lw / 2 + 0.5) + o, math.floor(p[1] - self.lw / 2 + 0.5) + o

    def _stroke(self, pts: list[Point], closed: bool = False) -> None:
        # Pillow의 joint="curve"는 굵기 4px 이하에서 꺼진다. 이음은 꺾는 점마다 획 굵기의 점을 찍어 직접 둥글게 한다.
        path = [self._snap(p) for p in pts]
        self.d.line(path + path[:1] if closed else path, fill="black", width=self.lw)
        r = self.lw / 2
        for x, y in pts if closed else pts[1:-1]:
            self.d.ellipse(self._pixels(x - r, y - r, x + r, y + r), fill="black")

    def paint(self, records: Iterable[Record]) -> None:
        for r in records:
            if isinstance(r, Line):
                self.line(r)
            elif isinstance(r, Rect):
                self.d.rectangle(self._outlined(r.left, r.top, r.width, r.height), outline="black", width=self.lw,
                                 fill=r.fill)
            elif isinstance(r, Ellipse):
                self.d.ellipse(self._outlined(r.left, r.top, r.width, r.height), outline="black", width=self.lw,
                               fill=r.fill)
            elif isinstance(r, Polygon):
                # Pillow polygon은 테두리를 안쪽으로 칠하고, 그러려고 그림판 크기의 마스크를 새로 잡는다. 채우기만 맡기고
                # 테두리는 닫힌 선으로 변 가운데에 칠한다.
                pts = [self._p(p) for p in r.points]
                if r.fill is not None:
                    self.d.polygon(pts, fill=r.fill)
                self._stroke(pts, closed=True)
            elif isinstance(r, Text):
                self.text(r)
            elif isinstance(r, Mask):
                box = self._pixels(*self._p((r.left, r.top)), *self._p((r.right, r.bottom)))
                if box:
                    self.d.rectangle(box, fill="white")
            else:
                raise TypeError(f"그릴 줄 모르는 기록이다: {r!r}")

    def line(self, r: Line) -> None:
        if r.dash is None:
            self._stroke([self._p(p) for p in r.points])
            return
        # 점선 k번째 칸은 선 처음부터의 길이로 [k·주기, k·주기 + 칠할 길이]이고, 그 안의 꺾는 점을 지나는 꺾은선으로 그린다.
        on, off = r.dash
        period = on + off
        done = [0.0]
        for p, q in zip(r.points, r.points[1:]):
            done.append(done[-1] + math.dist(p, q))
        total = done[-1]

        def at(length: float) -> Point:
            i = min(bisect.bisect_right(done, length) - 1, len(done) - 2)
            n = done[i + 1] - done[i]
            t = 0.0 if n == 0 else (length - done[i]) / n
            (x1, y1), (x2, y2) = r.points[i], r.points[i + 1]
            return x1 + (x2 - x1) * t, y1 + (y2 - y1) * t

        k, j = 0, 1  # j: 아직 지나지 않은 첫 꺾는 점. 칸이 앞으로만 가므로 되돌아가 훑지 않는다.
        while k * period < total:
            a, b = k * period, min(k * period + on, total)
            while j < len(done) - 1 and done[j] <= a:
                j += 1
            bends, i = [], j
            while i < len(done) - 1 and done[i] < b:
                bends.append(r.points[i])
                i += 1
            self._stroke([self._p(p) for p in [at(a), *bends, at(b)]])
            k += 1

    def text(self, r: Text) -> None:
        # 조각째 그리면 이 크기에서 힌팅으로 반올림된 글자 폭이 쌓여 기록한 상자와 어긋난다. 글자를 잰 자리에 하나씩 놓는다.
        placed = r.placement
        for left, ch, korean in placed.glyphs:
            if not ch.isspace():
                self.d.text(self._p((left, placed.baseline)), ch, fill="black",
                            font=T.font(korean, r.bold, T.SIZE * self.k), anchor="ls")
