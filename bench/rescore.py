"""잰 기록(stream.jsonl)을 지금 run_bench.py의 판정 규칙으로 다시 읽어 rescored.csv로 쓴다.

판정 규칙을 고친 뒤 옛 측정의 숫자를 새 규칙으로 맞출 때 쓴다(다시 재지 않으니 돈이 들지 않는다). 비용·시간도 기록에서 다시
읽는다. 도구와 문제는 그 실행의 prompt.txt에서 읽는다 — 문제 파일을 그 뒤에 고치거나 문제 이름을 바꿨을 수 있어서다(없으면
지금 문제 파일). 결과 폴더(results.csv가 있는 곳)마다 같은 폴더에 rescored.csv를 쓰고, 합격 판정이 바뀐 실행을 알린다. 기록이
없는 실행(claude를 띄우기 전에 실패한 것 등)은 원래 줄을 그대로 둔다.

쓰는 법: uv run python bench/rescore.py ~/Documents/cysUML-bench-runs/<태그> [...]
"""
import csv
import sys
from pathlib import Path

from run_bench import FIELDS, finish_row, load_problem, parse_stream, run_dir_for, spec_from_prompt, tool_from_prompt


def given_problem(run_dir: Path, r: dict) -> tuple[str | None, dict | None]:
    prompt = run_dir / "prompt.txt"
    text = prompt.read_text(encoding="utf-8") if prompt.exists() else ""
    tool, spec = r.get("tool") or tool_from_prompt(text), spec_from_prompt(text) if text else None
    if tool is None or spec is None:
        try:
            now_tool, now_spec = load_problem(r["problem"])
        except KeyError:
            return tool, spec
        print(f"  {r['model']} {r['effort']} {r['problem']} run{r['run']}: 준 문제를 못 찾아 지금 문제 파일과 견준다")
        tool, spec = tool or now_tool, spec or now_spec
    return tool, spec


for tag_dir in map(Path, sys.argv[1:]):
    with (tag_dir / "results.csv").open(encoding="utf-8") as f:
        old_rows = list(csv.DictReader(f))
    new_rows = []
    for r in old_rows:
        run_dir = run_dir_for(tag_dir, r["model"], r["effort"], r["problem"], r["run"])
        stream = run_dir / "stream.jsonl"
        tool, spec = given_problem(run_dir, r)
        if not stream.exists() or tool is None or spec is None:
            print(f"{tag_dir.name}: {r['model']} {r['effort']} {r['problem']} run{r['run']} "
                  f"기록이나 문제가 없어 원래 줄을 둔다")
            new_rows.append(r)
            continue
        row = {k: r.get(k) for k in ("model", "effort", "problem", "run", "exit", "wall_s")} | {"tool": tool}
        row.update(parse_stream(stream.read_text(encoding="utf-8").splitlines(), tool, spec))
        finish_row(row, timed_out=r.get("subtype") == "timeout")
        if row["subtype"] == "timeout":  # 끊긴 실행은 시간도 원래 기록을 따른다
            row["duration_s"] = r.get("duration_s")
        new_rows.append(row)
        if str(row["passed"]) != r.get("passed") or str(row["first_pass_draw"] or "") != (r.get("first_pass_draw") or ""):
            print(f"{tag_dir.name}: {r['model']} {r['effort']} {r['problem']} run{r['run']} "
                  f"합격 {r.get('passed')}→{row['passed']}, 첫 합격 차례 {r.get('first_pass_draw') or '-'}"
                  f"→{row['first_pass_draw'] or '-'}, 판정 {row['verdicts']}")
    with (tag_dir / "rescored.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(new_rows)
    print(f"{tag_dir.name}: {len(new_rows)}건 → {tag_dir / 'rescored.csv'}")
