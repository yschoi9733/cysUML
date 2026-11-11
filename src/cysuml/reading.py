"""클래스도·교류도가 함께 쓰는 입력 읽기: 틀린 입력(InputError)과 읽기 도우미.

읽기는 틀린 곳을 만나도 멈추지 않고 문제를 모은다. 문제마다 "classes[0].left: …"처럼 입력 안의 자리를 붙인다.
그림마다 읽는 모양은 Reader를 이어받아 더한다.
"""
from __future__ import annotations

from typing import Any, Optional

from . import text as T


class InputError(ValueError):
    """틀린 입력. problems는 문제마다 한 줄이다."""

    def __init__(self, problems):
        self.problems = tuple(problems)
        super().__init__("\n".join(self.problems))


def show(v: Any) -> str:
    try:
        s = repr(v)
    except ValueError:  # 파이썬이 글자로 바꾸지 않는 아주 큰 정수(4300자리 넘게)
        return "(아주 큰 정수)"
    return s if len(s) <= 40 else s[:37] + "..."


def at(path: str, key) -> str:
    return f"{path}[{key}]" if isinstance(key, int) else f"{path}.{key}" if path else str(key)


class Reader:
    def __init__(self):
        self.problems: list[str] = []

    def fail(self, path: str, message: str) -> None:
        self.problems.append(f"{path or '입력'}: {message}")

    def obj(self, v, path: str, fields: tuple[str, ...], required: tuple[str, ...] = ()) -> Optional[dict]:
        if not isinstance(v, dict):
            self.fail(path, f"객체여야 한다(받은 값 {show(v)})")
            return None
        for k in v:
            if k not in fields:
                self.fail(at(path, k) if isinstance(k, str) else path,
                          f"모르는 필드다{'' if isinstance(k, str) else f' {show(k)}'}. 쓸 수 있는 필드: {', '.join(fields)}")
        for k in required:
            if k not in v:
                self.fail(path, f"'{k}' 필드가 빠졌다")
        return v

    def items(self, v, path: str) -> list:
        if not isinstance(v, (list, tuple)):
            self.fail(path, f"목록이어야 한다(받은 값 {show(v)})")
            return []
        return list(v)

    def text(self, v, path: str, bold: bool = False, name: bool = False) -> Optional[str]:
        """name이면 상자·참여자를 가리키는 이름이라 앞뒤 공백을 뗀다("A "와 "A"를 같은 것으로)."""
        if not isinstance(v, str):
            self.fail(path, f"문자열이어야 한다(받은 값 {show(v)})")
            return None
        if not v.strip():
            self.fail(path, "비어 있다")
            return None
        try:
            T.text_width(v, bold)
        except ValueError as e:
            self.fail(path, str(e))
            return None
        return T.normalize(v).strip() if name else T.normalize(v)

    def choice(self, v, path: str, options: tuple[str, ...]) -> Optional[str]:
        if not isinstance(v, str) or v not in options:
            self.fail(path, f"{' · '.join(repr(o) for o in options)} 가운데 하나여야 한다(받은 값 {show(v)})")
            return None
        return v
