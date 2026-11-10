"""글자를 글꼴별 조각으로 나누고, 폭과 자리를 논리 좌표(px)로 잰다.

한글·한자·전각 문자는 Noto Sans KR로, 나머지 글자는 Liberation Sans(Arial과 글자 폭이 같다)로 글자마다 골라 그린다.
폭과 자리는 큰 기준 크기에서 재서 줄인다. 작은 크기에서 재면 힌팅이 글자마다 폭을 반올림해서, 그림 배율과
FreeType 버전에 따라 값이 흔들린다.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

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
_KOREAN_RANGES = (
    (0x1100, 0x11FF),  # 한글 자모
    (0x3000, 0x303F),  # CJK 기호·문장부호
    (0x3130, 0x318F),  # 한글 호환 자모
    (0x3200, 0x33FF),  # 괄호·동그라미 문자, CJK 호환 문자(㈜·㎏)
    (0x3400, 0x4DBF),  # 한자 확장 A
    (0x4E00, 0x9FFF),  # 한자
    (0xA960, 0xA97F),  # 한글 자모 확장 A
    (0xAC00, 0xD7FF),  # 한글 음절, 한글 자모 확장 B
    (0xF900, 0xFAFF),  # 호환 한자
    (0xFF00, 0xFFEF),  # 반각·전각 문자
)

Box = tuple[float, float, float, float]


def is_korean(ch: str) -> bool:
    """Noto Sans KR로 그리는 글자인지."""
    c = ord(ch)
    return any(lo <= c <= hi for lo, hi in _KOREAN_RANGES)


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


@lru_cache(maxsize=4096)
def text_width(s: str, bold: bool = False) -> float:
    return sum(_ref(korean, bold).getlength(part) for part, korean in split_runs(s)) / _REF


@dataclass(frozen=True)
class Placement:
    """한 줄 글자를 놓은 자리(논리 좌표).

    box는 줄 상자다: 폭은 text_width, 높이는 Liberation Sans의 ascent~descent(한글도 이 안에 든다).
    ink는 실제로 칠해지는 곳의 상자이고, 공백뿐이면 None이다.
    """

    box: Box
    baseline: float
    runs: tuple[tuple[float, str, bool], ...]
    ink: Optional[Box]


def place(x: float, y: float, s: str, bold: bool = False, anchor: str = "lm") -> Placement:
    """(x, y)에 s를 놓는다. anchor "lm"이면 x가 왼쪽 끝, "mm"이면 가운데이고, y는 줄 상자의 세로 가운데다."""
    if anchor not in ("lm", "mm"):
        raise ValueError(f"anchor는 lm·mm만 받는다: {anchor!r}")
    if "\n" in s:
        raise ValueError("한 줄 글자만 놓는다")
    width = text_width(s, bold)
    left = x - width / 2 if anchor == "mm" else x
    baseline = y + (ASCENT - DESCENT) / 2
    half = (ASCENT + DESCENT) / 2
    pen = left
    runs = []
    ink: Optional[Box] = None
    for part, korean in split_runs(s):
        f = _ref(korean, bold)
        l, t, r, b = f.getbbox(part, anchor="ls")
        if r > l and b > t:
            run_ink = (pen + l / _REF, baseline + t / _REF, pen + r / _REF, baseline + b / _REF)
            ink = run_ink if ink is None else (
                min(ink[0], run_ink[0]), min(ink[1], run_ink[1]), max(ink[2], run_ink[2]), max(ink[3], run_ink[3]))
        runs.append((pen, part, korean))
        pen += f.getlength(part) / _REF
    return Placement((left, y - half, left + width, y + half), baseline, tuple(runs), ink)
