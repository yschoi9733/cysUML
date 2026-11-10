"""그림판: 논리 좌표(px)로 도형과 글자를 받아 기록하고, 그 기록만으로 PNG를 그린다.

그림을 기록에서 그리므로 검사가 읽는 기록(Canvas.records)과 그림이 어긋나지 않는다. 기록은 그림 배율과 상관없이
논리 좌표 그대로이고, owner는 그 도형이 속한 그림 요소의 이름으로 검사 결과에 쓴다. 잘못된 입력은 기록하기 전에
ValueError로 막는다. 그릴 때는 그린 것의 범위에 PAD만큼 여백을 두고(frame), SS배로 그린 뒤 줄여 선을 부드럽게 하고,
결과는 scale배(기본 SCALE) PNG로 낸다.
"""
from __future__ import annotations

import math
import numbers
from dataclasses import dataclass
from typing import Iterable, Optional, Union

from PIL import Image, ImageColor, ImageDraw

from . import text as T

SCALE = 1.6
SS = 4
PAD = 12
BG_MARGIN = 2
MIN_DASH = 0.5
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
    """한 줄 글자. box는 줄 상자(text.Placement.box)다.

    bg는 글자 밑에 흰 바탕을 깔았다는 뜻이고, 그 바탕은 바로 앞의 Mask다. 칠할 글자가 없으면(공백뿐) 깔지 않고 bg도
    False다.
    """

    x: float
    y: float
    text: str
    bold: bool
    anchor: str
    box: Box
    bg: bool = False
    owner: Optional[str] = None


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


def _direction(tip: Point, frm: Point) -> tuple[float, float]:
    """tip에서 frm으로 가는 단위 벡터."""
    tip, frm = _point(tip), _point(frm)
    dx, dy = frm[0] - tip[0], frm[1] - tip[1]
    n = math.hypot(dx, dy)
    if n == 0:
        raise ValueError(f"선 끝 장식의 방향을 정할 수 없다(두 점이 같다): {tip}")
    return dx / n, dy / n


class Canvas:
    def __init__(self, scale: float = SCALE):
        (scale,) = _nums(scale)
        if scale <= 0:
            raise ValueError(f"배율은 0보다 커야 한다: {scale}")
        self.scale = scale
        self.records: list[Record] = []

    def line(self, pts: Iterable[Point], dash: Optional[tuple[float, float]] = None, owner: Optional[str] = None) -> None:
        """dash=(칠할 길이, 비울 길이)이면 점선이다(둘 다 MIN_DASH 이상). 무늬는 꺾는 점마다 새로 시작한다."""
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
        self.records.append(Line(pts, dash, owner))

    def rect(self, left: float, top: float, width: float, height: float, fill: Optional[str] = "white",
             owner: Optional[str] = None) -> None:
        self.records.append(Rect(*_box(left, top, width, height), _fill(fill), owner))

    def ellipse(self, left: float, top: float, width: float, height: float, fill: Optional[str] = "white",
                owner: Optional[str] = None) -> None:
        self.records.append(Ellipse(*_box(left, top, width, height), _fill(fill), owner))

    def poly(self, pts: Iterable[Point], fill: Optional[str] = "white", owner: Optional[str] = None) -> None:
        pts = _points(pts, 3)
        self.records.append(Polygon(pts, _fill(fill), owner))

    def text(self, x: float, y: float, s: str, bold: bool = False, anchor: str = "lm", bg: bool = False,
             owner: Optional[str] = None) -> None:
        """한 줄 글자. anchor와 y의 뜻은 text.place와 같다. bg면 글자가 칠해지는 곳보다 BG_MARGIN 넓게 흰 바탕을 깐다."""
        x, y = _nums(x, y)
        bold = bool(bold)
        placed = T.place(x, y, s, bold, anchor)
        laid = bg and placed.ink is not None
        if laid:
            l, t, r, b = placed.ink
            self.erase(l - BG_MARGIN, t - BG_MARGIN, r + BG_MARGIN, b + BG_MARGIN, owner=owner)
        self.records.append(Text(x, y, s, bold, anchor, placed.box, laid, owner))

    def erase(self, left: float, top: float, right: float, bottom: float, owner: Optional[str] = None) -> None:
        left, top, right, bottom = _nums(left, top, right, bottom)
        _box(left, top, right - left, bottom - top)
        self.records.append(Mask(left, top, right, bottom, owner))

    def open_arrow(self, tip: Point, frm: Point, size: float = 10, spread: float = math.radians(28),
                   owner: Optional[str] = None) -> None:
        """frm에서 tip으로 가는 선 끝의 열린 화살촉(두 갈래 선)."""
        c, s = _direction(tip, frm)
        tip = _point(tip)
        size, spread = _nums(size, spread)
        for turn in (-spread, spread):
            ct, st = math.cos(turn), math.sin(turn)
            self.line([tip, (tip[0] + size * (c * ct - s * st), tip[1] + size * (s * ct + c * st))], owner=owner)

    def closed_arrow(self, tip: Point, frm: Point, filled: bool = True, size: float = 10, half: float = 4.5,
                     owner: Optional[str] = None) -> None:
        """닫힌 삼각형 화살촉. 채우면 호출 메시지, 비우면(크기 18·9) 상속·실체화다."""
        c, s = _direction(tip, frm)
        tip = _point(tip)
        size, half = _nums(size, half)
        base = (tip[0] + c * size, tip[1] + s * size)
        self.poly([tip, (base[0] - s * half, base[1] + c * half), (base[0] + s * half, base[1] - c * half)],
                  fill="black" if filled else "white", owner=owner)

    def diamond(self, tip: Point, frm: Point, filled: bool = True, size: float = 18, half: float = 6,
                owner: Optional[str] = None) -> None:
        """선 끝의 마름모. 채우면 합성, 비우면 집합이다."""
        c, s = _direction(tip, frm)
        tip = _point(tip)
        size, half = _nums(size, half)
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
                ink = T.place(r.x, r.y, r.text, r.bold, r.anchor).ink
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
        return (minx, miny, max(1, math.ceil((b[2] + PAD - minx) * self.scale)),
                max(1, math.ceil((b[3] + PAD - miny) * self.scale)))

    def frame(self) -> Box:
        """결과 PNG가 덮는 논리 좌표 범위: 그린 것의 범위에 PAD만큼 여백을 두고, 오른쪽·아래를 출력 픽셀에 맞춰 늘린다.
        PNG의 픽셀 (px, py)는 논리 좌표 (frame[0] + px / scale, frame[1] + py / scale)다."""
        minx, miny, w, h = self._frame_px()
        return minx, miny, minx + w / self.scale, miny + h / self.scale

    def to_image(self) -> Image.Image:
        minx, miny, w, h = self._frame_px()
        if w * SS * h * SS > MAX_PIXELS:
            raise ValueError(f"그림이 너무 크다: 논리 {w / self.scale:g}×{h / self.scale:g}, 배율 {self.scale:g}")
        img = Image.new("L", (w * SS, h * SS), 255)
        _Painter(img, minx, miny, self.scale * SS).paint(self.records)
        return img.resize((w, h), Image.LANCZOS)

    def save(self, path) -> tuple[int, int]:
        out = self.to_image()
        out.save(path, format="PNG")
        return out.size


class _Painter:
    """기록을 SS배 그림판에 그린다. 테두리와 선은 모두 논리 좌표의 선·변을 가운데로 칠한다."""

    def __init__(self, img: Image.Image, minx: float, miny: float, k: float):
        self.d = ImageDraw.Draw(img)
        self.minx, self.miny, self.k = minx, miny, k
        self.lw = max(1, round(k))

    def _p(self, p: Point) -> Point:
        return (p[0] - self.minx) * self.k, (p[1] - self.miny) * self.k

    def _outlined(self, left: float, top: float, width: float, height: float) -> list[Point]:
        # Pillow는 상자 테두리를 안쪽으로 칠한다. 반 획씩 넓혀 선과 같이 변 가운데로 칠하게 한다.
        (x0, y0), (x1, y1) = self._p((left, top)), self._p((left + width, top + height))
        h = self.lw / 2
        return [(x0 - h, y0 - h), (x1 + h, y1 + h)]

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
                # 테두리는 닫힌 선으로 변 가운데에 칠한다(첫 변을 한 번 더 그어 첫 꼭짓점도 둥글게 잇는다).
                pts = [self._p(p) for p in r.points]
                if r.fill is not None:
                    self.d.polygon(pts, fill=r.fill)
                self.d.line(pts + pts[:2], fill="black", width=self.lw, joint="curve")
            elif isinstance(r, Text):
                self.text(r)
            else:
                self.d.rectangle([self._p((r.left, r.top)), self._p((r.right, r.bottom))], fill="white")

    def line(self, r: Line) -> None:
        if r.dash is None:
            self.d.line([self._p(p) for p in r.points], fill="black", width=self.lw, joint="curve")
            return
        on, off = r.dash
        for (x1, y1), (x2, y2) in zip(r.points, r.points[1:]):
            n = math.hypot(x2 - x1, y2 - y1)
            s = 0.0
            while s < n:
                a, b = s / n, min(s + on, n) / n
                self.d.line([self._p((x1 + (x2 - x1) * a, y1 + (y2 - y1) * a)),
                             self._p((x1 + (x2 - x1) * b, y1 + (y2 - y1) * b))], fill="black", width=self.lw)
                s += on + off

    def text(self, r: Text) -> None:
        # 조각째 그리면 이 크기에서 힌팅으로 반올림된 글자 폭이 쌓여 기록한 상자와 어긋난다. 글자를 잰 자리에 하나씩 놓는다.
        placed = T.place(r.x, r.y, r.text, r.bold, r.anchor)
        for left, ch, korean in placed.glyphs:
            if not ch.isspace():
                self.d.text(self._p((left, placed.baseline)), ch, fill="black",
                            font=T.font(korean, r.bold, T.SIZE * self.k), anchor="ls")
