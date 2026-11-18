"""bench/(모델별 배치 측정)는 cysUML 내부(도구별 SPEC·parse)에 기대어 그린 입력을 문제와 견준다. 그 내부를 바꿔도 측정이
조용히 깨지지 않는지 본다."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
import run_bench as bench  # noqa: E402

PROBLEM_IDS = list(bench.PROBLEMS) + list(bench.WRITTEN)


@pytest.mark.parametrize("pid", PROBLEM_IDS)
def test_problem_is_read_and_matches_itself(pid):
    tool, spec = bench.load_problem(pid)
    bench.problem_shape(spec, tool)
    assert bench.faithful(json.loads(json.dumps(spec)), spec, tool)


@pytest.mark.parametrize("pid", list(bench.PROBLEMS))
def test_readme_example_with_layout_matches_its_problem(pid):
    # README 예시 그림의 입력(자리가 든 원본)은 자리를 지운 문제와 같은 그림이어야 한다
    drawn = json.loads((bench.EXAMPLES / f"{bench.PROBLEMS[pid]}.cysuml.json").read_text(encoding="utf-8"))
    tool, spec = bench.load_problem(pid)
    assert bench.faithful(drawn, spec, tool)


def test_changed_diagram_is_not_faithful():
    tool, spec = bench.load_problem("order")
    dropped = json.loads(json.dumps(spec))
    dropped["relations"].pop()
    assert not bench.faithful(dropped, spec, tool)
