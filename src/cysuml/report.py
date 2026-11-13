"""검사 결과 틀: 그림마다의 검사가 함께 쓰는 항목(Finding)·결과(Report)와 오류·검사 문구의 수 표기(그림 목록은 README).

MCP 도구가 그림마다의 검사 결과를 같은 틀(합격 여부·불합격 항목·크기)로 돌려주도록 한곳에 둔다. 불합격 종류와 요소 이름의 꼴,
합격·불합격 문구와 크기 밖의 알림(AI가 배치하는 그림의 선끼리 엇갈린 곳 등 — to_dict에 그 알림의 열쇠가 더해진다)은 검사마다
(boxcheck·sequencecheck) 정한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .text import Box


def round1(v: float) -> float:
    """오류·검사 결과에 쓰는 수: 소수 한 자리로 반올림(-0은 0으로)."""
    return round(v, 1) + 0.0


def fmt_num(v: float) -> str:
    """round1한 수를 글자로(끝의 .0은 뗀다)."""
    s = f"{round1(v):.1f}"
    return s[:-2] if s.endswith(".0") else s


def fmt_rect(rect: Box) -> str:
    """오류·검사 문구에 쓰는 상자 자리: "왼, 위, 폭×높이"."""
    return f"{fmt_num(rect[0])}, {fmt_num(rect[1])}, {fmt_num(rect[2] - rect[0])}×{fmt_num(rect[3] - rect[1])}"


@dataclass(frozen=True)
class Finding:
    """검사 항목 하나. kind는 종류, elements는 걸린 요소의 이름, where는 걸린 자리(논리 좌표 왼, 위, 오른, 아래 — 넓이가
    없을 수도 있다), problem은 무엇이 걸렸는지, hint는 고치는 법이다."""

    kind: str
    elements: tuple[str, ...]
    where: Box
    problem: str
    hint: str

    def __str__(self) -> str:
        return f"{self.problem} {self.hint}"

    def to_dict(self) -> dict:
        return {"kind": self.kind, "elements": list(self.elements), "where": [round1(v) for v in self.where],
                "problem": self.problem, "hint": self.hint}


@dataclass(frozen=True)
class Report:
    """failures가 비어 있으면 합격이다. size는 그린 것의 범위에 둘레 여백을 둔 논리 좌표 폭·높이, png_size는 scale배로 낼
    PNG의 픽셀 수다 — 그 배율로는 너무 커 PNG를 그릴 수 없으면 None이다(합격과 따로 본다). 둘 다 Canvas.measure 값이다.

    그림마다 바꾸는 것: 합격 문구(PASSED), 불합격 건수 뒤에 붙이는 말(FAILED), PNG로 그리기에 너무 클 때 고치는 법(SHRINK),
    크기 알림 앞에 넣는 알림(_notices)과 그 값(_extra)."""

    failures: tuple[Finding, ...]
    size: tuple[float, float]
    png_size: Optional[tuple[int, int]]
    scale: float

    PASSED = "합격"
    FAILED = ""
    SHRINK = "그림을 줄이거나 배율을 낮춘다"

    @property
    def passed(self) -> bool:
        return not self.failures

    def _extra(self) -> dict:
        return {}

    def _notices(self) -> list[str]:
        return []

    def to_dict(self) -> dict:
        png = self.png_size or (None, None)
        return {"passed": self.passed,
                "failures": [f.to_dict() for f in self.failures],
                **self._extra(),
                "size": {"width": round1(self.size[0]), "height": round1(self.size[1]),
                         "png_width": png[0], "png_height": png[1], "scale": self.scale}}

    def summary(self) -> str:
        out = [f"불합격 — {len(self.failures)}건{self.FAILED}" if self.failures else self.PASSED]
        out += [f"{i}. {f}" for i, f in enumerate(self.failures, 1)]
        out += self._notices()
        png = (f"PNG {self.png_size[0]}×{self.png_size[1]}px(배율 {self.scale:g})" if self.png_size else
               f"배율 {self.scale:g}로는 PNG로 그리기에 너무 크다 — {self.SHRINK}")
        out.append(f"알림 — 그림 크기: 논리 좌표 {fmt_num(self.size[0])}×{fmt_num(self.size[1])}(둘레 여백 포함), {png}")
        return "\n".join(out)
