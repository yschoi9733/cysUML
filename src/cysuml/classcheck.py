"""클래스도 검사: AI가 배치하는 그림의 공용 검사(boxcheck)를 클래스도에 쓴다.

검사 규칙은 boxcheck에 있다. 여기에는 클래스도에서 날 수 있는 불합격 종류(KINDS — 안에 요소를 두거나 이름 칸이 있는 그림에서만
나는 종류는 뺀다)와 클래스도 글의 고치는 법(LABEL_HINT)을 둔다.
"""
from __future__ import annotations

from .boxcheck import BOX_CLEARANCE, NESTED_KINDS, PLACE_EPS, TEXT_CLEARANCE, Report, check, label_hint
from .boxcheck import KINDS as ALL_KINDS
from .boxdiagram import BOX_WORDS

__all__ = ["BOX_CLEARANCE", "KINDS", "LABEL_HINT", "PLACE_EPS", "TEXT_CLEARANCE", "Report", "check"]

KINDS = tuple(k for k in ALL_KINDS if k not in NESTED_KINDS)
LABEL_HINT = label_hint(BOX_WORDS)
