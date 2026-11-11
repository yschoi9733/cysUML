import os
import subprocess
import sys
from pathlib import Path

import pytest

from cysuml import classdiagram as C
from cysuml import reading as R
from cysuml import sequencediagram as S


def test_both_diagrams_raise_the_shared_input_error():
    assert C.InputError is R.InputError and S.InputError is R.InputError


def test_sequence_diagram_does_not_load_class_diagram():
    # 하위 프로세스가 이 테스트가 불러온 것과 같은 cysuml을 불러오게 그 자리를 넘긴다(설치 방식과 상관없이)
    src = str(Path(R.__file__).resolve().parents[1])
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [src, os.environ.get("PYTHONPATH")]))}
    code = "import sys, cysuml.sequencediagram; print('cysuml.classdiagram' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, env=env).stdout
    assert out.strip() == "False"


@pytest.mark.parametrize("read, expected, problems", [
    (lambda r: r.obj([1], "", ("a",)), None, ["입력: 객체여야 한다(받은 값 [1])"]),
    (lambda r: r.obj({"a": 1, "b": 2}, "x", ("a",)), {"a": 1, "b": 2}, ["x.b: 모르는 필드다. 쓸 수 있는 필드: a"]),
    (lambda r: r.obj({1: 2}, "x", ("a",)), {1: 2}, ["x: 모르는 필드다 1. 쓸 수 있는 필드: a"]),
    (lambda r: r.obj({}, "x", ("a", "b"), ("a", "b")), {}, ["x: 'a' 필드가 빠졌다", "x: 'b' 필드가 빠졌다"]),
    (lambda r: r.items((1, 2), "x"), [1, 2], []),
    (lambda r: r.items("ab", "x"), [], ["x: 목록이어야 한다(받은 값 'ab')"]),
    (lambda r: r.text(" A ", "x", name=True), "A", []),
    (lambda r: r.text(" A ", "x"), " A ", []),
    (lambda r: r.text(3, "x"), None, ["x: 문자열이어야 한다(받은 값 3)"]),
    (lambda r: r.text(" ", "x"), None, ["x: 비어 있다"]),
    (lambda r: r.choice("c", "x", ("a", "b")), None, ["x: 'a' · 'b' 가운데 하나여야 한다(받은 값 'c')"]),
    (lambda r: r.choice("a", "x", ("a", "b")), "a", []),
])
def test_reader_collects_problems_with_their_place(read, expected, problems):
    reader = R.Reader()
    assert read(reader) == expected and reader.problems == problems


def test_place_and_value_notation():
    assert [R.at("", "classes"), R.at("classes", 0), R.at("classes[0]", "name")] == ["classes", "classes[0]", "classes[0].name"]
    assert R.show("a" * 50) == repr("a" * 50)[:37] + "..." and R.show(10 ** 5000) == "(아주 큰 정수)"
