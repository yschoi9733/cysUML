"""글자를 글꼴별 조각으로 나누고, 폭과 자리를 논리 좌표(px)로 잰다.

Liberation Sans(Arial과 글자 폭이 같다)에 있는 글자는 Liberation Sans로, 없는 글자(한글·한자·※·① 등)는
Noto Sans KR로 글자마다 골라 그린다. 폭과 글자 자리는 큰 기준 크기에서 재서 줄인다. 작은 크기에서 재면 힌팅이 글자마다
폭을 반올림해서, 그림 배율과 FreeType 버전에 따라 값이 흔들린다. 그리는 쪽(canvas)도 이 자리에 글자를 하나씩 놓는다.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fontTools.ttLib import TTFont
from PIL import ImageFont

SIZE = 13
FONT_DIR = Path(__file__).parent / "fonts"
_FILES = {
    (False, False): "LiberationSans-Regular.ttf",
    (False, True): "LiberationSans-Bold.ttf",
    (True, False): "NotoSansKR-Regular.otf",
    (True, True): "NotoSansKR-Bold.otf",
}
_REF = 64

Box = tuple[float, float, float, float]


@lru_cache(maxsize=2)
def _codepoints(korean: bool) -> frozenset[int]:
    """그 글꼴에 있는 글자. 보통과 굵게의 글자 목록은 같다(테스트가 확인한다)."""
    with TTFont(str(FONT_DIR / _FILES[korean, False]), lazy=True) as f:
        return frozenset(f.getBestCmap())


def is_korean(ch: str) -> bool:
    """Noto Sans KR로 그리는 글자인지 — Liberation Sans에 없는 글자다."""
    return ord(ch) not in _codepoints(False)


def _check(s: str) -> None:
    for ch in s:
        category = unicodedata.category(ch)
        if category[0] == "C" or category in ("Zl", "Zp"):
            raise ValueError(f"제어·서식 문자나 줄 나눔은 글자에 넣을 수 없다: U+{ord(ch):04X}")
        if ord(ch) not in _codepoints(False) and ord(ch) not in _codepoints(True):
            raise ValueError(f"함께 넣은 글꼴에 없는 글자다: {ch!r} (U+{ord(ch):04X})")


def split_runs(s: str) -> list[tuple[str, bool]]:
    """s를 같은 글꼴로 그리는 조각으로 나눈다. 조각마다 (글자들, Noto Sans KR로 그리는지)."""
    runs: list[tuple[str, bool]] = []
    for ch in s:
        korean = is_korean(ch)
        if runs and runs[-1][1] == korean:
            runs[-1] = (runs[-1][0] + ch, korean)
        else:
            runs.append((ch, korean))
    return runs


@lru_cache(maxsize=32)
def font(korean: bool, bold: bool, size: float) -> ImageFont.FreeTypeFont:
    """함께 넣은 글꼴. 어느 컴퓨터에서든 같게 그리려고 libraqm 대신 Pillow 기본 배치를 쓴다."""
    return ImageFont.truetype(str(FONT_DIR / _FILES[korean, bold]), size, layout_engine=ImageFont.Layout.BASIC)


def _ref(korean: bool, bold: bool) -> ImageFont.FreeTypeFont:
    return font(korean, bold, SIZE * _REF)


_ascent, _descent = _ref(False, False).getmetrics()
ASCENT = _ascent / _REF
DESCENT = _descent / _REF


@dataclass(frozen=True)
class _Layout:
    width: float
    glyphs: tuple[tuple[float, str, bool], ...]
    ink: Optional[Box]


@lru_cache(maxsize=4096)
def _layout(s: str, bold: bool) -> _Layout:
    """왼쪽 끝·기준선을 (0, 0)으로 둔 배치. 두 글자 길이에서 뒤 글자 폭을 빼 다음 글자 자리를 잡아 커닝을 살린다.
    글꼴에 없는 글자나 제어·서식 문자가 있으면 ValueError."""
    _check(s)
    pen = 0.0
    glyphs = []
    ink: Optional[Box] = None
    for part, korean in split_runs(s):
        f = _ref(korean, bold)
        x = pen
        for i, ch in enumerate(part):
            if i:
                x += (f.getlength(part[i - 1] + ch) - f.getlength(ch)) / _REF
            glyphs.append((x, ch, korean))
        l, t, r, b = f.getbbox(part, anchor="ls")
        if r > l and b > t:
            run_ink = (pen + l / _REF, t / _REF, pen + r / _REF, b / _REF)
            ink = run_ink if ink is None else (
                min(ink[0], run_ink[0]), min(ink[1], run_ink[1]), max(ink[2], run_ink[2]), max(ink[3], run_ink[3]))
        pen += f.getlength(part) / _REF
    if ink is not None:  # 공백뿐인 조각은 높이가 없어 빠지므로, 가로는 진행 폭 전체로 넓힌다
        ink = (min(ink[0], 0.0), ink[1], max(ink[2], pen), ink[3])
    return _Layout(pen, tuple(glyphs), ink)


def normalize(s: str) -> str:
    """그리고 잴 글자. 풀어 쓴 한글(NFD — macOS 파일 이름 등에서 옮긴 것)은 자모가 흩어져 그려지므로 NFC로 모은다."""
    if not isinstance(s, str):
        raise ValueError(f"글자는 문자열이어야 한다: {s!r}")
    return unicodedata.normalize("NFC", s)


def _layout_of(s: str, bold: bool) -> _Layout:
    return _layout(normalize(s), bool(bold))


def text_width(s: str, bold: bool = False) -> float:
    return _layout_of(s, bold).width


@dataclass(frozen=True)
class Placement:
    """한 줄 글자를 놓은 자리(논리 좌표).

    box는 줄 상자다: 폭은 text_width, 높이는 Liberation Sans의 ascent~descent(한글도 이 안에 든다)이고, 그 밖으로
    칠해지는 글자(Ǻ·█ 등)가 있으면 거기까지 늘어나 ink를 늘 덮는다. glyphs는 글자마다 (왼쪽 x, 글자, Noto Sans KR로
    그리는지)다. ink는 글자가 칠해지는 곳의 상자이고(가로는 글자 진행 폭 전체를 덮는다), 공백뿐이면 None이다.
    """

    box: Box
    baseline: float
    glyphs: tuple[tuple[float, str, bool], ...]
    ink: Optional[Box]


def place(x: float, y: float, s: str, bold: bool = False, anchor: str = "lm") -> Placement:
    """(x, y)에 한 줄 글자 s를 놓는다(normalize한 글자로). anchor "lm"이면 x가 왼쪽 끝, "mm"이면 가운데이고, y는
    줄 상자의 세로 가운데다."""
    if anchor not in ("lm", "mm"):
        raise ValueError(f"anchor는 lm·mm만 받는다: {anchor!r}")
    lay = _layout_of(s, bold)
    left = x - lay.width / 2 if anchor == "mm" else x
    baseline = y + (ASCENT - DESCENT) / 2
    half = (ASCENT + DESCENT) / 2
    box = (left, y - half, left + lay.width, y + half)
    ink = None
    if lay.ink is not None:
        ink = (left + lay.ink[0], baseline + lay.ink[1], left + lay.ink[2], baseline + lay.ink[3])
        box = (min(box[0], ink[0]), min(box[1], ink[1]), max(box[2], ink[2]), max(box[3], ink[3]))
    return Placement(box, baseline, tuple((left + gx, ch, korean) for gx, ch, korean in lay.glyphs), ink)
