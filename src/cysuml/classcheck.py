"""클래스도 검사: 그린 결과(classdiagram.Drawing)를 읽어 합격·불합격과 알림을 낸다.

불합격은 문서에 못 넣는 그림이다. 관계선(화살촉·삼각형·마름모 포함)이 양 끝이 아닌 상자나 선 글자(관계 이름·다중도)를 지나거나
다른 관계선과 포개질 때, 상자끼리 겹칠 때, 선 글자끼리 또는 선 글자와 상자가 겹칠 때다. 선끼리 엇갈린 곳과 그림 크기는 알림으로만
준다. 상속·실체화에서 자식 여럿의 선이 한 줄기로 부모에게 모이는 것(공유 줄기)은 포개짐으로 치지 않는다.

관계선은 상자 밑에 그리므로 끝 상자 안으로 들어간 부분은 가려 보이지 않고, 상자 안 글자에 닿는 선은 그 상자를 먼저 지난다. 그래서
상자 안 글자를 지나는 선은 "선이 상자를 지난다" 한 항목으로 알린다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Iterator, Optional

from .canvas import PAD, Canvas, Point, Text
from .classdiagram import LABEL_CLEAR, Drawing, PlacedRelation
from .geom import Box, between, clip, grow, hits, meets, outline, span

# 검사 여유값(논리 좌표 px)
BOX_CLEARANCE = 4  # 상자를 사방으로 이만큼 넓힌 곳에 선이나 다른 상자가 닿으면 지나간·겹친 것으로 본다
TEXT_CLEARANCE = LABEL_CLEAR  # 선 글자 상자를 넓히는 폭. 글자 자리를 고를 때와 같아야 도구가 빈 자리로 고른 글자가 합격한다
OVERLAP_GAP = 2  # 나란한 두 선의 가운데가 이만큼 안이면 한 선으로 보인다
OVERLAP_MIN = 4  # 그렇게 붙어 가는 길이가 이보다 길면 포개진 것으로 본다
PARALLEL_SIN = 0.05  # 두 선분 사이 각의 사인이 이 안이면(약 3°) 나란하다고 본다
CROSS_EPS = 1e-9  # 점이 선분이 놓인 직선에서 이 안이면 직선 위로 본다(엇갈림이 아니라 맞닿음)

TRUNK_KINDS = ("generalization", "realization")
ROLES = {"name": "이름", "from_multiplicity": "from 쪽 다중도", "to_multiplicity": "to 쪽 다중도"}
LABEL_HINT = "선 글자 자리는 도구가 선 둘레의 빈 곳에서 고르는데 빈 곳이 없었다 — 상자를 떼어 놓거나, 꺾는 점(via)을 주어 선 둘레를 비운다."

Segment = tuple[Point, Point]


@dataclass(frozen=True)
class Finding:
    """검사 항목 하나. kind는 종류, elements는 걸린 요소의 이름(상자 이름이나 관계 기록의 owner), where는 걸린 자리(논리 좌표
    왼, 위, 오른, 아래 — 엇갈린 곳은 넓이가 없다), problem은 무엇이 걸렸는지, hint는 고치는 법이다.

    불합격 종류: box_overlap(상자끼리) · line_through_box(선이 상자를) · line_overlap(선끼리 포개짐, 한 선의 되짚음) ·
    line_through_text(선이 선 글자를) · text_on_box(선 글자가 상자에) · text_overlap(선 글자끼리). 알림 종류: crossing.
    """

    kind: str
    elements: tuple[str, ...]
    where: Box
    problem: str
    hint: str

    def __str__(self) -> str:
        return f"{self.problem} {self.hint}"

    def to_dict(self) -> dict:
        return {"kind": self.kind, "elements": list(self.elements), "where": [_round(v) for v in self.where],
                "problem": self.problem, "hint": self.hint}


@dataclass(frozen=True)
class Report:
    """failures가 비어 있으면 합격이다. crossings는 선끼리 엇갈린 곳(알림), size는 논리 좌표로 잰 그림 폭·높이(둘레 여백
    포함), png_size는 scale배로 낸 PNG의 픽셀 수다(배율이 너무 커 셀 수 없으면 None)."""

    failures: tuple[Finding, ...]
    crossings: tuple[Finding, ...]
    size: tuple[float, float]
    png_size: Optional[tuple[int, int]]
    scale: float

    @property
    def passed(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict:
        png = self.png_size or (None, None)
        return {"passed": self.passed,
                "failures": [f.to_dict() for f in self.failures],
                "crossings": [f.to_dict() for f in self.crossings],
                "size": {"width": _round(self.size[0]), "height": _round(self.size[1]),
                         "png_width": png[0], "png_height": png[1], "scale": self.scale}}

    def summary(self) -> str:
        out = [f"불합격 — {len(self.failures)}건" if self.failures else "합격 — 선이 상자·글자를 지나거나 겹친 곳이 없다."]
        out += [f"{i}. {f}" for i, f in enumerate(self.failures, 1)]
        out.append(f"알림 — 선끼리 엇갈린 곳 {len(self.crossings)}곳" + (". " + self.crossings[0].hint if self.crossings else ""))
        out += [f"- {f.problem}" for f in self.crossings]
        png = f"PNG {self.png_size[0]}×{self.png_size[1]}px" if self.png_size else "PNG 크기는 셀 수 없음"
        out.append(f"알림 — 그림 크기: 논리 좌표 {_n(self.size[0])}×{_n(self.size[1])}(둘레 여백 포함), {png}(배율 {self.scale:g})")
        return "\n".join(out)


@dataclass(frozen=True)
class _Box:
    name: str
    rect: Box

    @property
    def title(self) -> str:
        return f"상자 {self.name}({_area(self.rect)})"


@dataclass(frozen=True)
class _Relation:
    index: int
    placed: PlacedRelation
    segments: tuple[Segment, ...]  # 선과 선 끝 모양의 테두리
    path: tuple[Segment, ...]  # 선만

    @property
    def owner(self) -> str:
        return self.placed.owner

    @property
    def title(self) -> str:
        return f"선 {self.owner}(relations[{self.index}])"


@dataclass(frozen=True)
class _Label:
    relation: _Relation
    role: str
    text: str
    box: Box

    @property
    def title(self) -> str:
        r = self.relation
        return f"관계 {r.owner}(relations[{r.index}])의 {ROLES[self.role]} '{self.text}'(자리 {_area(self.box)})"


def check(drawing: Drawing) -> Report:
    boxes, relations, labels = _read(drawing)
    failures = [*_box_overlaps(boxes), *_lines_through_boxes(relations, boxes), *_line_overlaps(relations),
                *_lines_through_labels(relations, labels), *_labels_on_boxes(labels, boxes), *_label_overlaps(labels)]
    size, png = _size(drawing.canvas)
    return Report(tuple(failures), tuple(_crossings(relations)), size, png, drawing.canvas.scale)


def _read(drawing: Drawing) -> tuple[list[_Box], list[_Relation], list[_Label]]:
    """상자 자리와 관계선의 점은 자리 잡기 결과에서, 선 끝 모양과 선 글자는 그린 기록에서 읽는다(owner로 묶는다)."""
    records: dict[Optional[str], list] = {}
    for r in drawing.canvas.records:
        records.setdefault(r.owner, []).append(r)
    boxes = [_Box(p.box.name, p.rect) for p in drawing.layout.boxes]
    relations, labels = [], []
    for i, p in enumerate(drawing.layout.relations):
        mine = records.get(p.owner, [])
        rel = _Relation(i, p, tuple(outline(mine)), tuple(zip(p.points, p.points[1:])))
        relations.append(rel)
        texts = [t for t in mine if isinstance(t, Text)]
        labels += [_Label(rel, lab.role, t.text, t.box) for lab, t in zip(p.labels, texts)]
    return boxes, relations, labels


def _parts(segments: Iterable[Segment], rect: Box) -> list[Segment]:
    return [c for p, q in segments if (c := clip(p, q, rect)) is not None]


def _box_overlaps(boxes: list[_Box]) -> Iterator[Finding]:
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if not meets(grow(a.rect, BOX_CLEARANCE), b.rect):
                continue
            dx = max(b.rect[0] - a.rect[2], a.rect[0] - b.rect[2])
            dy = max(b.rect[1] - a.rect[3], a.rect[1] - b.rect[3])
            what = ("상자끼리 겹친다" if dx < 0 and dy < 0 else "상자끼리 맞닿았다" if max(dx, dy) == 0
                    else f"상자끼리 {_n(max(dx, dy))}px밖에 떨어지지 않았다")
            yield Finding("box_overlap", (a.name, b.name), between(a.rect, b.rect), f"{what}: {a.title}, {b.title}.",
                          f"한쪽을 옮겨 가로나 세로로 {BOX_CLEARANCE}px 넘게 띄운다. 상자 크기는 글자에 맞춰 늘어난 값이니 "
                          "위 크기를 보고 옮긴다.")


def _lines_through_boxes(relations: list[_Relation], boxes: list[_Box]) -> Iterator[Finding]:
    for r in relations:
        ends = (r.placed.relation.source, r.placed.relation.target)
        for b in boxes:
            if b.name in ends:
                continue
            parts = _parts(r.segments, grow(b.rect, BOX_CLEARANCE))
            if not parts:
                continue
            what = ("선이 상자를 지난다" if any(hits(p, q, b.rect) for p, q in r.segments)
                    else f"선이 상자에 {BOX_CLEARANCE}px 안으로 붙어 지나간다")
            fix = "꺾는 점(via)을 고쳐" if r.placed.relation.via else "선에 꺾는 점(via)을 주어"
            yield Finding("line_through_box", (r.owner, b.name), span(pt for s in parts for pt in s),
                          f"{what}: {r.title}, {b.title}.", f"그 상자를 옮기거나, {fix} 그 상자를 비켜 가게 한다.")


def _alongside(s: Segment, t: Segment) -> Optional[Segment]:
    """선분 t 가운데 선분 s와 나란히 OVERLAP_GAP 안으로 붙어 가는 부분. 나란하지 않거나 그 길이가 OVERLAP_MIN 이하면 None."""
    (p, q), (r, w) = s, t
    ls, lt = math.dist(p, q), math.dist(r, w)
    if ls == 0 or lt == 0:
        return None
    ux, uy = (q[0] - p[0]) / ls, (q[1] - p[1]) / ls
    if abs(ux * (w[1] - r[1]) - uy * (w[0] - r[0])) / lt > PARALLEL_SIN:
        return None

    def along(v: Point) -> float:
        return (v[0] - p[0]) * ux + (v[1] - p[1]) * uy

    def off(v: Point) -> float:
        return ux * (v[1] - p[1]) - uy * (v[0] - p[0])

    lo, hi = 0.0, 1.0  # t 위의 자리(r에서 0, w에서 1)
    for c, k, low, high in ((along(r), along(w) - along(r), 0.0, ls), (off(r), off(w) - off(r), -OVERLAP_GAP, OVERLAP_GAP)):
        if k == 0:
            if not low <= c <= high:
                return None
            continue
        t1, t2 = sorted(((low - c) / k, (high - c) / k))
        lo, hi = max(lo, t1), min(hi, t2)
    if (hi - lo) * lt <= OVERLAP_MIN:
        return None
    return ((r[0] + (w[0] - r[0]) * lo, r[1] + (w[1] - r[1]) * lo),
            (r[0] + (w[0] - r[0]) * hi, r[1] + (w[1] - r[1]) * hi))


def _trunk(a: _Relation, b: _Relation) -> bool:
    """상속·실체화 트리의 공유 줄기 — 서로 다른 자식이 같은 부모로 가는 같은 종류의 선."""
    x, y = a.placed.relation, b.placed.relation
    return x.kind == y.kind and x.kind in TRUNK_KINDS and x.target == y.target and x.source != y.source


def _line_overlaps(relations: list[_Relation]) -> Iterator[Finding]:
    for i, r in enumerate(relations):
        parts = [c for j, s in enumerate(r.path) for t in r.path[j + 1:] if (c := _alongside(s, t)) is not None]
        if parts:
            where = span(pt for s in parts for pt in s)
            yield Finding("line_overlap", (r.owner,), where, f"선이 왔던 길을 되짚는다: {r.title}, 자리 ({_area(where)}).",
                          "꺾는 점(via)을 고쳐 같은 길로 되돌아가지 않게 한다.")
        for o in relations[i + 1:]:
            if _trunk(r, o):
                continue
            parts = [c for s in r.path for t in o.path if (c := _alongside(s, t)) is not None]
            if parts:
                where = span(pt for s in parts for pt in s)
                yield Finding("line_overlap", (r.owner, o.owner), where,
                              f"선끼리 포개진다: {r.title}, {o.title}, 자리 ({_area(where)}).",
                              "포개진 선은 한 선으로 보여 관계 하나가 사라진다 — 한 선에 꺾는 점(via)을 주거나 고쳐 두 선을 떼어 놓는다.")


def _lines_through_labels(relations: list[_Relation], labels: list[_Label]) -> Iterator[Finding]:
    for r in relations:
        for lab in labels:
            parts = _parts(r.segments, grow(lab.box, TEXT_CLEARANCE))
            if not parts:
                continue
            own = lab.relation is r
            hint = (LABEL_HINT if own else "선 글자 자리는 도구가 제 선 둘레의 빈 곳에서 고른다 — 지나가는 선에 꺾는 점(via)을 "
                    "주어 글자를 비켜 가게 하거나, 상자를 옮겨 두 관계를 떼어 놓는다.")
            yield Finding("line_through_text", (r.owner,) if own else (r.owner, lab.relation.owner),
                          span(pt for s in parts for pt in s), f"선이 글자를 지난다: {r.title}, {lab.title}.", hint)


def _labels_on_boxes(labels: list[_Label], boxes: list[_Box]) -> Iterator[Finding]:
    for lab in labels:
        for b in boxes:
            if not meets(grow(lab.box, TEXT_CLEARANCE), b.rect):
                continue
            what = "선 글자가 상자에 겹친다" if meets(lab.box, b.rect) else f"선 글자가 상자에 {_n(TEXT_CLEARANCE)}px 안으로 붙어 있다"
            yield Finding("text_on_box", (lab.relation.owner, b.name), between(lab.box, b.rect),
                          f"{what}: {lab.title}, {b.title}.", LABEL_HINT)


def _label_overlaps(labels: list[_Label]) -> Iterator[Finding]:
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            if not meets(grow(a.box, TEXT_CLEARANCE), b.box):
                continue
            what = "선 글자끼리 겹친다" if meets(a.box, b.box) else f"선 글자끼리 {_n(TEXT_CLEARANCE)}px 안으로 붙어 있다"
            owners = tuple(dict.fromkeys((a.relation.owner, b.relation.owner)))
            yield Finding("text_overlap", owners, between(a.box, b.box), f"{what}: {a.title}, {b.title}.", LABEL_HINT)


def _side(p: Point, q: Point, v: Point) -> int:
    """v가 p→q 직선의 어느 쪽인지(왼쪽 1, 오른쪽 -1, 직선 위 0)."""
    n = math.dist(p, q)
    d = 0.0 if n == 0 else ((q[0] - p[0]) * (v[1] - p[1]) - (q[1] - p[1]) * (v[0] - p[0])) / n
    return (d > CROSS_EPS) - (d < -CROSS_EPS)


def _cross(s: Segment, t: Segment) -> Optional[Point]:
    """두 선분이 서로 건너가는 점. 맞닿기만 하거나 한 직선 위에 있으면 None."""
    (p, q), (r, w) = s, t
    if _side(p, q, r) * _side(p, q, w) >= 0 or _side(r, w, p) * _side(r, w, q) >= 0:
        return None
    d = (q[0] - p[0]) * (w[1] - r[1]) - (q[1] - p[1]) * (w[0] - r[0])
    k = ((r[0] - p[0]) * (w[1] - r[1]) - (r[1] - p[1]) * (w[0] - r[0])) / d
    return p[0] + (q[0] - p[0]) * k, p[1] + (q[1] - p[1]) * k


def _crossings(relations: list[_Relation]) -> Iterator[Finding]:
    for i, r in enumerate(relations):
        for o in relations[i + 1:]:
            for s in r.path:
                for t in o.path:
                    pt = _cross(s, t)
                    if pt is not None:
                        yield Finding("crossing", (r.owner, o.owner), (*pt, *pt),
                                      f"선끼리 엇갈린다: {r.title}, {o.title}, 자리 ({_n(pt[0])}, {_n(pt[1])}).",
                                      "엇갈림을 줄이려면 상자 순서·자리를 바꾸거나, 꺾는 점(via)을 주어 돌아가게 한다.")


def _size(canvas: Canvas) -> tuple[tuple[float, float], Optional[tuple[int, int]]]:
    """그림판이 PNG로 낼 범위(그린 것 둘레에 PAD)와 그 픽셀 수 — Canvas.frame과 같은 셈이다."""
    b = canvas.bounds()
    assert b is not None  # 상자가 하나 이상이다
    minx, miny = b[0] - PAD, b[1] - PAD
    fw, fh = (b[2] + PAD - minx) * canvas.scale, (b[3] + PAD - miny) * canvas.scale
    png = (max(1, math.ceil(fw)), max(1, math.ceil(fh))) if math.isfinite(fw) and math.isfinite(fh) else None
    return (b[2] + PAD - minx, b[3] + PAD - miny), png


def _round(v: float) -> float:
    return round(v, 1) + 0.0


def _n(v: float) -> str:
    s = f"{_round(v):.1f}"
    return s[:-2] if s.endswith(".0") else s


def _area(rect: Box) -> str:
    return f"{_n(rect[0])}, {_n(rect[1])}, {_n(rect[2] - rect[0])}×{_n(rect[3] - rect[1])}"
