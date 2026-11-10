"""그림판: 논리 좌표(px)로 도형과 글자를 그리고, 그린 것을 같은 좌표로 기록한다.

SS배로 그린 뒤 줄여 선을 부드럽게 하고, 결과는 SCALE배 PNG로 낸다. 기록(Canvas.records)은 그림 배율과 상관없이
논리 좌표 그대로라 검사가 이것을 읽는다. owner는 그 도형이 속한 그림 요소의 이름으로, 검사 결과에 쓴다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Optional, Union

from PIL import Image, ImageDraw

from . import text as T

SCALE = 1.6
SS = 4
PAD = 12
BG_MARGIN = 2
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
    """글자 하나. box는 줄 상자(text.Placement.box)다.

    bg는 글자 밑에 흰 바탕을 깔았다는 뜻이고, 그 바탕은 바로 앞의 Mask로 남는다. masked는 그리는 쪽이 글자 뒤로
    지나는 선을 따로 지웠다는 표시일 뿐 그리는 것은 같다.
    """

    x: float
    y: float
    text: str
    bold: bool
    anchor: str
    box: Box
    bg: bool = False
    masked: bool = False
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


def _points(pts: Iterable[Point], least: int) -> tuple[Point, ...]:
    out = tuple((float(x), float(y)) for x, y in pts)
    if len(out) < least:
        raise ValueError(f"점이 {least}개 이상 있어야 한다: {out}")
    return out


def _size(width: float, height: float) -> None:
    if width < 0 or height < 0:
        raise ValueError(f"크기가 음수다: {width}×{height}")


def _direction(tip: Point, frm: Point) -> tuple[float, float]:
    """tip에서 frm으로 가는 단위 벡터."""
    dx, dy = frm[0] - tip[0], frm[1] - tip[1]
    n = math.hypot(dx, dy)
    if n == 0:
        raise ValueError(f"선 끝 장식의 방향을 정할 수 없다(두 점이 같다): {tip}")
    return dx / n, dy / n


class Canvas:
    """box(왼, 위, 오른, 아래)는 그릴 논리 좌표 범위다. 결과는 그린 곳 둘레로 잘라 내지만, 그림판은 이 범위 전체를
    SS×scale배로 잡으므로 그린 것에 맞춰 준다(MAX_PIXELS를 넘으면 ValueError)."""

    def __init__(self, box: Box, scale: float = SCALE):
        minx, miny, maxx, maxy = box
        if not (maxx > minx and maxy > miny and scale > 0):
            raise ValueError(f"그림판 범위나 배율이 잘못됐다: {box}, {scale}")
        self.minx, self.miny = minx, miny
        self.scale = scale
        self.k = scale * SS
        size = (math.ceil((maxx - minx) * self.k), math.ceil((maxy - miny) * self.k))
        if size[0] * size[1] > MAX_PIXELS:
            raise ValueError(f"그림이 너무 크다: 논리 {maxx - minx:g}×{maxy - miny:g}, 배율 {scale:g}")
        self.img = Image.new("L", size, 255)
        self.d = ImageDraw.Draw(self.img)
        self.lw = max(1, round(self.k))
        self.records: list[Record] = []

    def _p(self, p: Point) -> Point:
        return (p[0] - self.minx) * self.k, (p[1] - self.miny) * self.k

    def line(self, pts: Iterable[Point], dash: Optional[tuple[float, float]] = None, owner: Optional[str] = None) -> None:
        """dash=(칠할 길이, 비울 길이)이면 점선이다. 무늬는 꺾는 점마다 새로 시작한다."""
        pts = _points(pts, 2)
        if dash is not None:
            dash = (float(dash[0]), float(dash[1]))
            if not (dash[0] > 0 and dash[1] >= 0):
                raise ValueError(f"점선 무늬가 잘못됐다: {dash}")
        self.records.append(Line(pts, dash, owner))
        if dash is None:
            self.d.line([self._p(p) for p in pts], fill="black", width=self.lw, joint="curve")
            return
        on, off = dash
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            n = math.hypot(x2 - x1, y2 - y1)
            s = 0.0
            while s < n:
                a, b = s / n, min(s + on, n) / n
                self.d.line([self._p((x1 + (x2 - x1) * a, y1 + (y2 - y1) * a)),
                             self._p((x1 + (x2 - x1) * b, y1 + (y2 - y1) * b))], fill="black", width=self.lw)
                s += on + off

    def rect(self, left: float, top: float, width: float, height: float, fill: Optional[str] = "white",
             owner: Optional[str] = None) -> None:
        _size(width, height)
        self.records.append(Rect(left, top, width, height, fill, owner))
        self.d.rectangle([self._p((left, top)), self._p((left + width, top + height))], outline="black", width=self.lw,
                         fill=fill)

    def ellipse(self, left: float, top: float, width: float, height: float, fill: Optional[str] = "white",
                owner: Optional[str] = None) -> None:
        _size(width, height)
        self.records.append(Ellipse(left, top, width, height, fill, owner))
        self.d.ellipse([self._p((left, top)), self._p((left + width, top + height))], outline="black", width=self.lw,
                       fill=fill)

    def poly(self, pts: Iterable[Point], fill: Optional[str] = "white", owner: Optional[str] = None) -> None:
        pts = _points(pts, 3)
        self.records.append(Polygon(pts, fill, owner))
        self.d.polygon([self._p(p) for p in pts], fill=fill, outline="black", width=self.lw)

    def text(self, x: float, y: float, s: str, bold: bool = False, anchor: str = "lm", bg: bool = False,
             masked: bool = False, owner: Optional[str] = None) -> None:
        """한 줄 글자. anchor와 y의 뜻은 text.place와 같다. bg면 글자가 칠해지는 곳보다 BG_MARGIN 넓게 흰 바탕을 깐다."""
        placed = T.place(x, y, s, bold, anchor)
        if bg and placed.ink:
            l, t, r, b = placed.ink
            self.erase(l - BG_MARGIN, t - BG_MARGIN, r + BG_MARGIN, b + BG_MARGIN, owner=owner)
        self.records.append(Text(x, y, s, bold, anchor, placed.box, bg, masked, owner))
        # 조각째 그리면 이 크기에서 힌팅으로 반올림된 글자 폭이 쌓여 기록한 상자와 어긋난다. 글자를 잰 자리에 하나씩 놓는다.
        for left, ch, korean in placed.glyphs:
            if not ch.isspace():
                self.d.text(self._p((left, placed.baseline)), ch, fill="black", font=T.font(korean, bold, T.SIZE * self.k),
                            anchor="ls")

    def erase(self, left: float, top: float, right: float, bottom: float, owner: Optional[str] = None) -> None:
        _size(right - left, bottom - top)
        self.records.append(Mask(left, top, right, bottom, owner))
        self.d.rectangle([self._p((left, top)), self._p((right, bottom))], fill="white")

    def open_arrow(self, tip: Point, frm: Point, size: float = 10, spread: float = math.radians(28),
                   owner: Optional[str] = None) -> None:
        """frm에서 tip으로 가는 선 끝의 열린 화살촉(두 갈래 선)."""
        c, s = _direction(tip, frm)
        for turn in (-spread, spread):
            ct, st = math.cos(turn), math.sin(turn)
            self.line([tip, (tip[0] + size * (c * ct - s * st), tip[1] + size * (s * ct + c * st))], owner=owner)

    def closed_arrow(self, tip: Point, frm: Point, filled: bool = True, size: float = 10, half: float = 4.5,
                     owner: Optional[str] = None) -> None:
        """닫힌 삼각형 화살촉. 채우면 호출 메시지, 비우면(크기 18·9) 상속·실체화다."""
        c, s = _direction(tip, frm)
        base = (tip[0] + c * size, tip[1] + s * size)
        self.poly([tip, (base[0] - s * half, base[1] + c * half), (base[0] + s * half, base[1] - c * half)],
                  fill="black" if filled else "white", owner=owner)

    def diamond(self, tip: Point, frm: Point, filled: bool = True, size: float = 18, half: float = 6,
                owner: Optional[str] = None) -> None:
        """선 끝의 마름모. 채우면 합성, 비우면 집합이다."""
        c, s = _direction(tip, frm)
        mid = (tip[0] + c * size / 2, tip[1] + s * size / 2)
        far = (tip[0] + c * size, tip[1] + s * size)
        self.poly([tip, (mid[0] - s * half, mid[1] + c * half), far, (mid[0] + s * half, mid[1] - c * half)],
                  fill="black" if filled else "white", owner=owner)

    def to_image(self) -> Image.Image:
        """SCALE배로 줄이고, 그린 곳 둘레에 PAD만큼 남기고 잘라 낸 그림."""
        out = self.img.resize((max(1, round(self.img.width / SS)), max(1, round(self.img.height / SS))), Image.LANCZOS)
        box = out.point(lambda p: 255 if p < 250 else 0).getbbox()
        if box:
            m = round(PAD * self.scale)
            out = out.crop((max(0, box[0] - m), max(0, box[1] - m), min(out.width, box[2] + m), min(out.height, box[3] + m)))
        return out

    def save(self, path) -> tuple[int, int]:
        out = self.to_image()
        out.save(path, format="PNG")
        return out.size
