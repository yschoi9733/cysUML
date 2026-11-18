"""run_bench.py의 results.csv(여러 개 가능)를 모델·effort별 표와 문제별 표(마크다운)로 묶는다.

쓰는 법: uv run python bench/summarize.py ~/Documents/cysUML-bench-runs/r1-high/results.csv [...] [--drop 태그:문제 ...]
--drop은 경로에 그 태그가 든 결과 파일에서 그 문제의 줄을 뺀다(문제를 고치기 전에 잰 결과를 뺄 때).
"""
import csv
import sys
from collections import defaultdict
from statistics import mean


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


args = sys.argv[1:]
drops = [args[i + 1].split(":", 1) for i, a in enumerate(args) if a == "--drop"]
paths = [a for i, a in enumerate(args) if a != "--drop" and (i == 0 or args[i - 1] != "--drop")]
rows = []
for path in paths:
    with open(path, encoding="utf-8") as f:
        rows += [r for r in csv.DictReader(f) if not any(tag in path and r["problem"] == p for tag, p in drops)]

groups = defaultdict(list)
for r in rows:
    groups[(r["model"], r["effort"])].append(r)

print("| 모델 | effort | 실행 | 합격 | 첫 그림 합격 | 합격까지 평균 그림 수 | 평균 비용 | 평균 시간 | 합계 비용 |")
print("|---|---|---|---|---|---|---|---|---|")
for (model, effort), rs in sorted(groups.items()):
    passed = [r for r in rs if r.get("passed") == "True"]
    first = [r for r in passed if r.get("first_pass_draw") == "1"]
    draws = [num(r["first_pass_draw"]) for r in passed]
    costs = [num(r.get("cost_usd")) or 0 for r in rs]
    times = [num(r.get("duration_s")) or 0 for r in rs]
    print(f"| {model} | {effort} | {len(rs)} | {len(passed)}/{len(rs)} | {len(first)}/{len(rs)} | "
          f"{mean(draws):.1f} | ${mean(costs):.3f} | {mean(times):.0f}초 | ${sum(costs):.2f} |"
          if draws else
          f"| {model} | {effort} | {len(rs)} | 0/{len(rs)} | 0/{len(rs)} | - | ${mean(costs):.3f} | "
          f"{mean(times):.0f}초 | ${sum(costs):.2f} |")

print()
problems = sorted({r["problem"] for r in rows})
models = sorted(groups)
print("| 문제 | " + " | ".join(f"{m.replace('claude-', '')} {e}" for m, e in models) + " |")
print("|---|" + "---|" * len(models))
for p in problems:
    cells = []
    for key in models:
        rs = [r for r in groups[key] if r["problem"] == p]
        if not rs:
            cells.append("")
            continue
        cells.append(", ".join(
            (f"✅{r['first_pass_draw']}" if r.get("passed") == "True" else f"❌({r.get('draws') or 0})") for r in rs))
    print(f"| {p} | " + " | ".join(cells) + " |")
print()
print(f"전체 {len(rows)}건, 합계 ${sum(num(r.get('cost_usd')) or 0 for r in rows):.2f}")
odd = [r for r in rows if r.get("subtype") not in ("success",)]
for r in odd:
    print(f"- 확인 필요: {r['model']} {r['effort']} {r['problem']} run{r.get('run')} → {r.get('subtype')}")
