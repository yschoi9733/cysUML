"""잰 기록(stream.jsonl)을 지금 run_bench.py의 판정 규칙으로 다시 읽어 rescored.csv로 쓴다.

판정 규칙을 고친 뒤 옛 측정의 숫자를 새 규칙으로 맞출 때 쓴다(다시 재지 않으니 돈이 들지 않는다). 비용·시간도 기록에서 다시
읽는다. 도구와 문제는 그 실행의 prompt.txt에서 읽는다 — 문제 파일을 그 뒤에 고치거나 문제 이름을 바꿨을 수 있어서다(없으면
지금 문제 파일). 결과 폴더(results.csv가 있는 곳)마다 같은 폴더에 rescored.csv를 쓰고, 합격 판정이 바뀐 실행을 알린다. 다시
읽을 수 없는 실행(기록이 없거나 망가졌거나, 하네스 오류라 종료 코드·시간이 남지 않은 것)은 원래 줄을 그대로 둔다.

쓰는 법: uv run python bench/rescore.py ~/Documents/cysUML-bench-runs/<태그> [...]
"""
import csv
import json
import sys
from pathlib import Path

from run_bench import (FIELDS, build_row, is_measured, load_problem, run_dir_for, run_tool, spec_from_prompt,
                       tool_from_prompt)


class Kept(Exception):
    """다시 읽지 않고 원래 줄을 둘 까닭."""


def rescore_row(tag_dir: Path, r: dict) -> dict:
    sub = r.get("subtype") or ""
    run_dir = run_dir_for(tag_dir, r["model"], r["effort"], r["problem"], r["run"])
    stream, prompt, run_json = run_dir / "stream.jsonl", run_dir / "prompt.txt", run_dir / "run.json"
    if not stream.exists():
        raise Kept("기록(stream.jsonl)이 없다")
    # run_one이 해석 전에 남긴 종료 코드·시간·시간 초과 여부(이것을 남기기 전의 옛 기록은 CSV 줄을 쓴다)
    meta = r | json.loads(run_json.read_text(encoding="utf-8")) if run_json.exists() else r
    if sub.startswith("harness_error") and not run_json.exists():
        raise Kept("하네스 오류 줄인데 종료 코드·시간(run.json)이 남지 않았다")
    text = prompt.read_text(encoding="utf-8") if prompt.exists() else ""
    tool = tool_from_prompt(text) or run_tool(run_dir, r.get("tool"))
    spec = spec_from_prompt(text) if text else None
    if not tool or spec is None:
        print(f"  {r['model']} {r['effort']} {r['problem']} run{r['run']}: 준 문제를 못 찾아 지금 문제 파일과 견준다")
        now_tool, now_spec = load_problem(r["problem"])
        tool, spec = tool or now_tool, spec or now_spec
    if str(meta.get("timed_out")) in ("True", "False"):
        timed_out = str(meta["timed_out"]) == "True"
    else:  # timed_out을 남기기 전의 옛 기록은 그때 적은 판정 문구로만 가린다
        timed_out = sub == "timeout" or sub.endswith("(timeout)")
    return build_row(meta, stream.read_text(encoding="utf-8").split("\n"), tool, spec, timed_out)


def main() -> None:
    for tag_dir in map(Path, sys.argv[1:]):
        try:
            with (tag_dir / "results.csv").open(encoding="utf-8") as f:
                old_rows = list(csv.DictReader(f))
        except OSError as e:  # 한 태그를 못 읽어도 나머지 태그는 계속한다
            print(f"{tag_dir.name}: results.csv를 읽지 못해 건너뛴다: {e}")
            continue
        new_rows = []
        for r in old_rows:
            name = f"{tag_dir.name}: {r['model']} {r['effort']} {r['problem']} run{r['run']}"
            try:
                row = rescore_row(tag_dir, r)
            except Exception as e:  # 한 실행을 다시 읽지 못해도 나머지는 계속한다
                reason = str(e) if isinstance(e, Kept) else f"{type(e).__name__}: {e}"
                print(f"{name} 원래 줄을 둔다: {reason}")
                new_rows.append(r)
                continue
            new_rows.append(row)
            was, now = is_measured(r.get("subtype")), is_measured(row["subtype"])
            if was != now:  # 표에 드는 실행 수가 바뀐다
                print(f"{name} {'표에 들어옴' if now else '표에서 빠짐'}: {r.get('subtype') or '-'}→{row['subtype'] or '-'}")
            if str(row["passed"]) != r.get("passed") or str(row["first_pass_draw"] or "") != (r.get("first_pass_draw") or ""):
                print(f"{name} 합격 {r.get('passed')}→{row['passed']}, 첫 합격 차례 {r.get('first_pass_draw') or '-'}"
                      f"→{row['first_pass_draw'] or '-'}, 판정 {row['verdicts']}")
        with (tag_dir / "rescored.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(new_rows)
        print(f"{tag_dir.name}: {len(new_rows)}건 → {tag_dir / 'rescored.csv'}")


if __name__ == "__main__":
    main()
