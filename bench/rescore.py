"""잰 기록(stream.jsonl)을 지금 run_bench.py의 판정 규칙으로 다시 읽어 rescored.csv로 쓴다.

판정 규칙을 고친 뒤 옛 측정의 숫자를 새 규칙으로 맞출 때 쓴다(다시 재지 않으니 돈이 들지 않는다). 비용·시간도 기록에서 다시
읽는다. 결과 폴더(results.csv가 있는 곳)마다 같은 폴더에 rescored.csv를 쓰고, 합격 판정이 바뀐 실행을 알린다.

쓰는 법: uv run python bench/rescore.py ~/Documents/cysUML-bench-runs/<태그> [...]
"""
import csv
import sys
from pathlib import Path

from run_bench import FIELDS, load_problem, parse_stream

for tag_dir in map(Path, sys.argv[1:]):
    with (tag_dir / "results.csv").open(encoding="utf-8") as f:
        old_rows = list(csv.DictReader(f))
    new_rows = []
    for r in old_rows:
        run_dir = tag_dir / f"{r['model']}_{r['effort']}" / r["problem"] / f"run{r['run']}"
        tool, spec = load_problem(r["problem"])
        row = {k: r.get(k) for k in ("model", "effort", "problem", "run", "exit", "wall_s")} | {"tool": tool}
        row.update(parse_stream((run_dir / "stream.jsonl").read_text(encoding="utf-8").splitlines(), tool, spec))
        if r.get("subtype") == "timeout":  # 끊긴 실행은 끝의 결과가 없어 원래 기록을 따른다
            row["subtype"], row["duration_s"] = "timeout", r.get("duration_s")
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
