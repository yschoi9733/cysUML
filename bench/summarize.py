"""run_bench.py의 results.csv(여러 개 가능)를 모델·effort별 표와 문제별 표(마크다운)로 묶는다.

쓰는 법: uv run python bench/summarize.py ~/Documents/cysUML-bench-runs/<태그>/results.csv [...] [--drop 태그:문제 ...]
--drop은 결과 폴더 이름이 그 태그인 results.csv에서 그 문제의 줄을 뺀다(문제를 고치기 전에 잰 결과를 뺄 때).
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean

from run_bench import MAX_DRAWS, NOT_MEASURED, counts_as_pass


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def first_pass(r) -> int | None:
    n = num(r.get("first_pass_draw"))
    return int(n) if n is not None and counts_as_pass(int(n)) else None


def avg(values, fmt: str) -> str:
    vals = [v for v in values if v is not None]
    if not vals:
        return "-"
    return fmt.format(mean(vals)) + (f"({len(vals)}번)" if len(vals) < len(values) else "")


ap = argparse.ArgumentParser()
ap.add_argument("paths", nargs="+", type=Path)
ap.add_argument("--drop", action="append", default=[], metavar="태그:문제")
args = ap.parse_args()
drops = []
for d in args.drop:
    tag, sep, problem = d.partition(":")
    if not sep:
        ap.error(f"--drop은 태그:문제 꼴이다: {d}")
    drops.append((tag, problem))

rows, used = [], set()
for path in args.paths:
    tag = path.resolve().parent.name
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (tag, r["problem"]) in drops:
                used.add((tag, r["problem"]))
            else:
                rows.append(r)
for tag, problem in sorted(set(drops) - used):
    print(f"- 알림: --drop {tag}:{problem}에 맞는 줄이 없었다(태그나 문제 이름을 확인한다)")
# 모델을 잰 것이 아닌 실행(MCP 서버가 안 붙음, claude가 시작하지 못함, 하네스 오류)은 표에서 빼고 아래에 따로 적는다
def measured(r) -> bool:
    return not (r.get("subtype") or "").startswith(NOT_MEASURED)


skipped = [r for r in rows if not measured(r)]
rows = [r for r in rows if measured(r)]

groups = defaultdict(list)
for r in rows:
    groups[(r["model"], r["effort"])].append(r)

print("| 모델 | effort | 실행 | 합격 | 첫 그림 합격 | 합격까지 평균 그림 수 | 평균 비용 | 평균 시간 | 합계 비용 |")
print("|---|---|---|---|---|---|---|---|---|")
for (model, effort), rs in sorted(groups.items()):
    passes = [p for p in (first_pass(r) for r in rs) if p is not None]
    costs = [num(r.get("cost_usd")) for r in rs]
    times = [num(r.get("duration_s")) for r in rs]
    print(f"| {model} | {effort} | {len(rs)} | {len(passes)}/{len(rs)} | {passes.count(1)}/{len(rs)} | "
          f"{avg(passes, '{:.1f}')} | {avg(costs, '${:.3f}')} | {avg(times, '{:.0f}초')} | "
          f"${sum(c for c in costs if c is not None):.2f} |")

print()
problems = sorted({r["problem"] for r in rows})
models = sorted(groups)
print("| 문제 | " + " | ".join(f"{m.replace('claude-', '')} {e}" for m, e in models) + " |")
print("|---|" + "---|" * len(models))
for p in problems:
    cells = []
    for key in models:
        rs = [r for r in groups[key] if r["problem"] == p]
        cells.append(", ".join(f"✅{first_pass(r)}" if first_pass(r) else f"❌({r.get('draws') or 0})" for r in rs))
    print(f"| {p} | " + " | ".join(cells) + " |")
print()
def cost(rs) -> float:
    return sum(num(r.get("cost_usd")) or 0 for r in rs)


print(f"전체 {len(rows)}건, 합계 ${cost(rows):.2f}"
      + (f"(표에서 뺀 {len(skipped)}건까지 쓴 돈은 ${cost(rows + skipped):.2f})" if skipped else ""))
no_cost = sum(1 for r in rows if num(r.get("cost_usd")) is None)
no_time = sum(1 for r in rows if num(r.get("duration_s")) is None)
if no_cost:
    print(f"- 비용이 빈 실행 {no_cost}건은 비용 평균과 합계에서 뺐다(칸에 몇 번으로 낸 평균인지 붙였다)")
if no_time:
    print(f"- 시간이 빈 실행 {no_time}건은 시간 평균에서 뺐다")
for r in skipped:
    print(f"- 모델을 잰 것이 아니라 표에서 뺐다: {r['model']} {r['effort']} {r['problem']} run{r.get('run')} → {r.get('subtype')}")
for r in rows:
    if "other" in (r.get("verdicts") or "").split():  # cysUML 검사 결과 문구가 바뀌면 여기서 드러난다
        print(f"- 확인 필요: 검사 결과 첫 줄을 읽지 못한 그림이 있다: {r['model']} {r['effort']} {r['problem']} "
              f"run{r.get('run')} → {r.get('verdicts')}")
    if r.get("subtype") != "success" or str(r.get("is_error")) == "True":  # 오류로 끝났는데 subtype이 success인 것도
        error = f" ({r['error']})" if r.get("error") else ""
        print(f"- 확인 필요: {r['model']} {r['effort']} {r['problem']} run{r.get('run')} → {r.get('subtype')}{error}")
    if num(r.get("first_pass_draw")) is not None and first_pass(r) is None:
        print(f"- {MAX_DRAWS}번을 넘겨 합격해 불합격으로 셌다: {r['model']} {r['effort']} {r['problem']} run{r.get('run')}")
