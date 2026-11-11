"""클래스도 검사: 그린 결과(classdiagram.Drawing)를 읽어 합격·불합격과 알림을 낸다.

불합격은 문서에 못 넣는 그림이다. 관계선(화살촉·삼각형·마름모 포함)이 양 끝이 아닌 상자나 선 글자(관계 이름·다중도)를 지날 때,
관계선이 제 끝 상자 변에 붙어 가거나 선 끝 모양이 제 끝 상자에 가려질 때, 관계선이 다른 관계선과 포개지거나 선 끝 모양에 닿을 때, 선 끝 모양끼리 겹칠 때, 상자끼리 겹칠 때, 선 글자끼리 또는 선 글자와
상자가 겹칠 때다. 선끼리 엇갈린 곳과 그림 크기는 알림으로만 준다. 상속·실체화에서 자식 여럿의 선이 한 줄기로 부모의 한 삼각형에
모이는 것(공유 줄기)은 포개짐으로도, 선 끝 모양에 닿는 것으로도 치지 않는다. 공유 줄기처럼 여러 선이 한 자리에 겹쳐 그려진 곳이
걸리면 한 항목으로 묶어 알린다.

관계선은 상자 밑에 그리므로 끝 상자 안으로 들어간 부분은 가려 보이지 않고, 상자 안 글자에 닿는 선은 그 상자를 먼저 지난다. 그래서
상자 안 글자를 지나는 선은 "선이 상자를 지난다" 한 항목으로 알린다.
"""
from __future__ import annotations

import math
import operator
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator, Optional, Union

from .canvas import Line, Point, Polygon
from .classdiagram import LABEL_CLEAR, Drawing, PlacedRelation, fmt_num, fmt_rect, round1
from .geom import (Box, alongside, axis_gap, between, clip, crossings, distance, enters, grow, hits, inside, meets, outline,
                   span, touches)

# 검사 여유값(논리 좌표 px)
BOX_CLEARANCE = 4  # 상자를 사방으로 이만큼 넓힌 곳에 선이나 다른 상자가 닿으면 지나간·겹친 것으로 본다
TEXT_CLEARANCE = LABEL_CLEAR  # 선 글자 상자를 넓히는 폭. 글자 자리를 고를 때와 같아야 도구가 빈 자리로 고른 글자가 합격한다
OVERLAP_GAP = 2  # 나란한 두 선의 가운데가 이만큼 안이면 한 선으로 보인다
OVERLAP_MIN = 4  # 그렇게 붙어 가는 길이가 이보다 길면 포개진 것으로 본다(선이 제 끝 상자 변 BOX_CLEARANCE 안을 가는 길이도)
PARALLEL_SIN = 0.05  # 두 선분 사이 각의 사인이 이 안이면(약 3°) 나란하다고 본다
LINE_EPS = 1e-6  # 점이 선에서 이 안이면 선 위로 본다(엇갈림이 아니라 맞닿음)
HEAD_HIDE = 2  # 선 끝 모양이 제 끝 상자 안으로 이만큼 넘게 들어가면 가려진 것으로 본다(살짝 들어가는 건 상자 변 밑으로 일부러 넣은 것)
OWN_MARGIN = 0.5  # 선이 제 삼각형·마름모는 그 안쪽으로 이만큼 넘게 들어가야 지난 것으로 본다(테두리에 닿거나 따라가면 이어진 것)
PLACE_EPS = 1e-3  # 여러 선이 걸린 자리가 이 안으로 같으면 한 자리로 묶는다

TRUNK_KINDS = ("generalization", "realization")
ROLES = {"name": "이름", "from_multiplicity": "from 쪽 다중도", "to_multiplicity": "to 쪽 다중도"}
LABEL_HINT = "선 글자 자리는 도구가 선 둘레의 빈 곳에서 고르는데 빈 곳이 없었다 — 상자를 떼어 놓거나, 꺾는 점(via)을 주어 선 둘레를 비운다."
CROSSING_HINT = "엇갈림을 줄이려면 상자 순서·자리를 바꾸거나, 꺾는 점(via)을 주어 돌아가게 한다."

Segment = tuple[Point, Point]


@dataclass(frozen=True)
class Finding:
    """검사 항목 하나. kind는 종류, elements는 걸린 요소의 이름(상자 이름이나 관계 기록의 owner), where는 걸린 자리(논리 좌표
    왼, 위, 오른, 아래 — 엇갈린 곳은 넓이가 없다), problem은 무엇이 걸렸는지, hint는 고치는 법이다.

    불합격 종류(이 차례로 낸다): box_overlap(상자끼리) · line_through_box(선이 상자를, 제 끝 상자 변에 붙어, 선 끝 모양이 제 상자에 가려져) · line_overlap(선끼리 포개짐, 한 선의
    되짚음) · line_through_head(선이 선 끝 모양에) · head_overlap(선 끝 모양끼리) · line_through_text(선이 선 글자를) ·
    text_on_box(선 글자가 상자에) · text_overlap(선 글자끼리). 알림 종류: crossing.
    """

    kind: str
    elements: tuple[str, ...]
    where: Box
    problem: str
    hint: str

    def __str__(self) -> str:
        return f"{self.problem} {self.hint}"

    def to_dict(self) -> dict:
        return {"kind": self.kind, "elements": list(self.elements), "where": [round1(v) for v in self.where],
                "problem": self.problem, "hint": self.hint}


@dataclass(frozen=True)
class Report:
    """failures가 비어 있으면 합격이다. crossings는 선끼리 엇갈린 곳(알림), size는 그린 것의 범위에 둘레 여백을 둔 논리 좌표
    폭·높이, png_size는 scale배로 낼 PNG의 픽셀 수다 — 그 배율로는 너무 커 PNG를 그릴 수 없으면 None이다(합격과 따로 본다).
    둘 다 Canvas.measure 값이다."""

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
                "size": {"width": round1(self.size[0]), "height": round1(self.size[1]),
                         "png_width": png[0], "png_height": png[1], "scale": self.scale}}

    def summary(self) -> str:
        out = [f"불합격 — {len(self.failures)}건" if self.failures else "합격 — 선이 상자·글자를 지나거나 겹친 곳이 없다."]
        out += [f"{i}. {f}" for i, f in enumerate(self.failures, 1)]
        out.append(f"알림 — 선끼리 엇갈린 곳 {len(self.crossings)}곳" + (f". {CROSSING_HINT}" if self.crossings else ""))
        out += [f"- {f.problem}" for f in self.crossings]
        png = (f"PNG {self.png_size[0]}×{self.png_size[1]}px(배율 {self.scale:g})" if self.png_size else
               f"배율 {self.scale:g}로는 PNG로 그리기에 너무 크다 — 상자를 가까이 모으거나 배율을 낮춘다")
        out.append(f"알림 — 그림 크기: 논리 좌표 {fmt_num(self.size[0])}×{fmt_num(self.size[1])}(둘레 여백 포함), {png}")
        return "\n".join(out)


@dataclass(frozen=True)
class _Box:
    name: str
    rect: Box

    @property
    def title(self) -> str:
        return f"상자 {self.name}({fmt_rect(self.rect)})"


@dataclass(frozen=True)
class _Head:
    """선 끝 모양 — 삼각형·마름모(흰색이나 검은색으로 칠한 다각형)와 열린 화살촉(갈래 끝 → tip → 갈래 끝의 선). tip은 선 끝에
    닿은 꼭짓점이다."""

    name: str
    points: tuple[Point, ...]
    closed: bool
    tip: Point
    edges: tuple[Segment, ...]

    @classmethod
    def of(cls, record: Union[Line, Polygon]) -> _Head:
        closed = isinstance(record, Polygon)
        pts = record.points
        name = ("삼각형" if len(pts) == 3 else "마름모") if closed else "화살촉"
        return cls(name, pts, closed, pts[0] if closed else pts[1], tuple(outline([record])))

    def holds(self, segments: Iterable[Segment]) -> bool:
        """선분 끝점이 이 모양(삼각형·마름모) 안에 있는지."""
        return self.closed and any(inside(v, self.points) for s in segments for v in s)

    def touches(self, segments: Iterable[Segment]) -> bool:
        """선분들이 이 모양에 닿는지 — 테두리에 닿거나 안에 든다."""
        segments = tuple(segments)
        return any(touches(s, e, LINE_EPS) for s in segments for e in self.edges) or self.holds(segments)

    def near(self, segments: Iterable[Segment]) -> bool:
        """선분들이 이 모양 테두리에서 OVERLAP_GAP 안으로 다가오거나 안에 드는지 — 그만큼 붙으면 모양과 선이 한데 붙어 보인다."""
        segments = tuple(segments)
        return (any(distance(s, e, LINE_EPS) <= OVERLAP_GAP for s in segments for e in self.edges)
                or self.holds(segments))

    def meets(self, other: _Head) -> bool:
        return self.near(other.edges) or other.near(self.edges)


@dataclass(frozen=True, eq=False)
class _Relation:
    index: int
    placed: PlacedRelation
    points: tuple[Point, ...]  # 그린 선의 점
    heads: tuple[_Head, ...]
    path: tuple[Segment, ...]  # 선만(선 끝 모양 빼고)
    segments: tuple[Segment, ...]  # 선과 선 끝 모양의 테두리
    bounds: Box  # segments를 덮는 상자
    end_shape: Optional[_Head]  # to 쪽 끝의 삼각형·마름모

    @property
    def owner(self) -> str:
        return self.placed.owner

    @property
    def via(self) -> bool:
        return bool(self.placed.relation.via)

    @property
    def name(self) -> str:
        return f"{self.owner}(relations[{self.index}])"

    @property
    def title(self) -> str:
        return f"선 {self.name}"

    def _ends_at(self, box: str) -> list[int]:
        """제 끝 상자 box에 닿는 끝(points의 처음 0, 마지막 -1)."""
        rel = self.placed.relation
        return [i for i, name in ((0, rel.source), (-1, rel.target)) if name == box]

    def heads_at(self, box: str) -> list[_Head]:
        """제 끝 상자 box에 닿는 끝에 얹힌 선 끝 모양."""
        tips = [self.points[i] for i in self._ends_at(box)]
        return [h for h in self.heads if any(math.dist(h.tip, t) <= LINE_EPS for t in tips)]

    def away_from(self, box: str) -> tuple[tuple[Segment, ...], tuple[Segment, ...]]:
        """제 끝 상자 box에 붙어 가는지 볼 (선 구간, 선 끝 모양 테두리). 그 상자에 닿는 끝 구간과 그 끝에 얹힌 선 끝 모양은 뺀다 —
        끝 구간은 상자 가운데를 향해 나가므로, 넓은 상자 변을 비스듬히 나가는 평범한 선도 처음 몇 px는 변에 붙어 있다."""
        drop = {0 if i == 0 else len(self.path) - 1 for i in self._ends_at(box)}
        attached = self.heads_at(box)
        return (tuple(s for i, s in enumerate(self.path) if i not in drop),
                tuple(e for h in self.heads if h not in attached for e in h.edges))

    def over_own(self, head: _Head) -> list[Segment]:
        """이 선이 제 선 끝 모양 head를 지나는 구간들. 그 모양이 얹힌 끝 구간은 빼고, 삼각형·마름모는 안쪽으로 OWN_MARGIN 넘게
        들어간 구간만 친다 — 테두리에 닿거나 따라가는 것(끝 구간이 모양 길이와 같은 직교 꺾음, 밑변으로 올라와 붙는 꺾음)은 선이
        모양에 이어진 것이다. 화살촉은 갈래가 끝 구간(화살촉 길이 이상)보다 짧아, 다른 구간이 닿으면 정말 지난 것이다."""
        end = 0 if math.dist(head.tip, self.points[0]) <= LINE_EPS else len(self.path) - 1
        rest = [s for i, s in enumerate(self.path) if i != end]
        if head.closed:
            return [s for s in rest if enters(s, head.points, OWN_MARGIN)]
        return [s for s in rest if head.touches([s])]


@dataclass(frozen=True, eq=False)
class _Label:
    relation: _Relation
    role: str
    text: str
    box: Box

    @property
    def title(self) -> str:
        return f"관계 {self.relation.name}의 {ROLES[self.role]} '{self.text}'(자리 {fmt_rect(self.box)})"


Pairs = list[tuple[_Relation, _Relation]]
Overlap = tuple[_Relation, _Relation, list[Segment]]  # 포개진 두 선과 포개진 조각들


def check(drawing: Drawing) -> Report:
    boxes, relations, labels = _read(drawing)
    pairs = [(r, o) for i, r in enumerate(relations) for o in relations[i + 1:]
             if meets(grow(r.bounds, OVERLAP_GAP), o.bounds)]  # 서로 닿을 수 있는 두 선(앞 선, 뒤 선)
    retraces, overlaps = _line_overlaps(relations, pairs)
    near = _overlap_pieces(overlaps)
    failures = [*_box_overlaps(boxes), *_lines_through_boxes(relations, boxes), *_heads_under_own_box(relations, boxes),
                *retraces, *_merged_overlaps(overlaps),
                *_lines_through_heads(relations, pairs, near), *_head_overlaps(relations, pairs, near),
                *_lines_through_labels(relations, labels), *_labels_on_boxes(labels, boxes), *_label_overlaps(labels)]
    measured = drawing.canvas.measure()
    if measured is None:
        raise ValueError("그린 것이 없다")
    return Report(tuple(failures), tuple(_crossings(relations, pairs)), *measured, drawing.canvas.scale)


def _read(drawing: Drawing) -> tuple[list[_Box], list[_Relation], list[_Label]]:
    """상자 자리와 관계선의 점은 자리 잡기 결과에서, 선 끝 모양과 선 글자는 관계마다 그린 기록(Drawing.drawn)에서 읽는다."""
    boxes = [_Box(p.box.name, p.rect) for p in drawing.layout.boxes]
    relations, labels = [], []
    for i, (p, d) in enumerate(zip(drawing.layout.relations, drawing.drawn, strict=True)):
        points = d.line.points
        heads = tuple(_Head.of(h) for h in d.heads)
        path = tuple(zip(points, points[1:]))
        segments = path + tuple(e for h in heads for e in h.edges)
        end = next((h for h in heads if h.closed and math.dist(h.tip, points[-1]) <= LINE_EPS), None)
        rel = _Relation(i, p, points, heads, path, segments, _cover(segments), end)
        relations.append(rel)
        labels += [_Label(rel, lab.role, t.text, t.box) for lab, t in zip(p.labels, d.labels, strict=True)]
    return boxes, relations, labels


def _cover(segments: Iterable[Segment]) -> Box:
    return span(pt for s in segments for pt in s)


def _parts(segments: Iterable[Segment], rect: Box) -> list[Segment]:
    return [c for p, q in segments if (c := clip(p, q, rect)) is not None]


def _same(a: Any, b: Any) -> bool:
    """두 열쇠가 같은지 — 수는 PLACE_EPS 안이면 같다(계산 차례에 따른 오차나 반올림 경계로 한 자리가 갈리지 않게)."""
    if isinstance(a, tuple) and isinstance(b, tuple):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= PLACE_EPS
    return a == b


class _Places:
    """열쇠가 _same인 항목을 한 자리로 모은다(입력 차례를 지킨다)."""

    def __init__(self) -> None:
        self.items: list[tuple[Any, Any]] = []

    def get(self, key: Any, make: Callable[[], Any]) -> Any:
        for k, v in self.items:
            if _same(k, key):
                return v
        v = make()
        self.items.append((key, v))
        return v

    def values(self) -> list[Any]:
        return [v for _, v in self.items]


_index = operator.attrgetter("index")


def _add(found: list[_Relation], *rels: _Relation) -> None:
    for r in rels:
        if r not in found:
            found.append(r)


def _titles(rels: Iterable[_Relation]) -> str:
    return ", ".join(r.title for r in sorted(rels, key=_index))


def _owners(*groups: Iterable[_Relation]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(r.owner for g in groups for r in sorted(g, key=_index)))


def _box_overlaps(boxes: list[_Box]) -> Iterator[Finding]:
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            g = axis_gap(a.rect, b.rect)
            if g > BOX_CLEARANCE:
                continue
            what = ("상자끼리 겹친다" if g < -LINE_EPS else "상자끼리 맞닿았다" if round1(g) == 0
                    else f"상자끼리 {fmt_num(g)}px밖에 떨어지지 않았다")
            yield Finding("box_overlap", (a.name, b.name), between(a.rect, b.rect), f"{what}: {a.title}, {b.title}.",
                          f"한쪽을 옮겨 가로나 세로로 {BOX_CLEARANCE}px 넘게 띄운다. 상자 크기는 글자에 맞춰 늘어난 값이니 "
                          "위 크기를 보고 옮긴다.")


@dataclass(eq=False)
class _BoxHit:
    """상자 하나에 같은 자리로 걸린 선들. own이면 그 상자가 선들의 끝 상자다. inside는 묶인 선 가운데 하나라도 상자 안을 지나는지,
    along은 (끝 상자일 때) 선 구간이 그 상자 둘레 BOX_CLEARANCE 안을 OVERLAP_MIN 넘게 가는지다 — 아니면 반대쪽 끝의 선 끝 모양만
    그 상자 변에 붙었다."""

    box: _Box
    where: Box
    own: bool
    inside: bool = False
    along: bool = False
    rels: list[_Relation] = field(default_factory=list)


def _length(parts: Iterable[Segment]) -> float:
    return sum(math.dist(p, q) for p, q in parts)


def _lines_through_boxes(relations: list[_Relation], boxes: list[_Box]) -> Iterator[Finding]:
    """선이 양 끝이 아닌 상자를 지나거나, 제 끝 상자에 붙어 간다(변을 따라가면 테두리가 두 겹으로 보인다). 같은 상자를 같은 자리에서
    지나는 선들(공유 줄기)은 한 항목으로 묶는다."""
    found = _Places()
    for b in boxes:
        wide = grow(b.rect, BOX_CLEARANCE)
        for r in relations:
            if not meets(r.bounds, wide):
                continue
            own = b.name in (r.placed.relation.source, r.placed.relation.target)
            if own:
                path, edges = r.away_from(b.name)
                on_path, on_heads = _parts(path, wide), _parts(edges, wide)
                parts = on_path + on_heads
                if _length(parts) <= OVERLAP_MIN:
                    continue  # 제 끝 상자 띠를 잠깐 스치는 꺾음은 변을 따라가는 게 아니다
            else:
                on_path, parts = [], _parts(r.segments, wide)
            if parts:
                where = _cover(parts)
                hit = found.get((b.name, own, where), lambda: _BoxHit(b, where, own))
                hit.inside = hit.inside or (not own and any(hits(p, q, b.rect) for p, q in parts))
                hit.along = hit.along or _length(on_path) > OVERLAP_MIN
                _add(hit.rels, r)
    for hit in found.values():
        b, rels, vias = hit.box, hit.rels, {r.via for r in hit.rels}
        if hit.own and hit.along:
            yield Finding("line_through_box", (*_owners(rels), b.name), hit.where,
                          f"선이 제 끝 상자에 {BOX_CLEARANCE}px 안으로 붙어 간다: {_titles(rels)}, {b.title}.",
                          f"선이 상자 테두리에 붙어 보인다(변을 따라가면 테두리가 두 겹으로 보인다) — 꺾는 점(via)을 고쳐 그 상자에서 "
                          f"{BOX_CLEARANCE}px 넘게 띄운다.")
        elif hit.own:
            fix = ("두 상자를 더 떼어 놓는다" if vias == {False}
                   else "꺾는 점(via)을 고치거나 두 상자를 더 떼어 놓는다")
            yield Finding("line_through_box", (*_owners(rels), b.name), hit.where,
                          f"선 끝 모양이 제 끝 상자 변에 {BOX_CLEARANCE}px 안으로 붙는다: {_titles(rels)}, {b.title}.",
                          f"반대쪽 끝의 화살촉·삼각형·마름모가 이 상자 변에 닿아 보인다 — {fix}.")
        else:
            what = "선이 상자를 지난다" if hit.inside else f"선이 상자에 {BOX_CLEARANCE}px 안으로 붙어 지나간다"
            fix = ("꺾는 점(via)을 고쳐" if vias == {True} else "선에 꺾는 점(via)을 주어" if vias == {False}
                   else "꺾는 점(via)을 주거나 고쳐")
            yield Finding("line_through_box", (*_owners(rels), b.name), hit.where, f"{what}: {_titles(rels)}, {b.title}.",
                          f"그 상자를 옮기거나, {fix} 그 상자를 비켜 가게 한다.")


def _heads_under_own_box(relations: list[_Relation], boxes: list[_Box]) -> Iterator[Finding]:
    """선 끝 모양이 제 끝 상자 안으로 HEAD_HIDE 넘게 들어가 상자에 가려진다(상자를 선 위에 그린다). 선이 넓은 상자 변을 아주
    비스듬히 나가면 마름모·삼각형 꼭짓점이나 화살촉 갈래가 상자 밑으로 들어간다. 같은 모양(공유 줄기의 삼각형)은 한 항목으로 묶는다."""
    found = _Places()
    for b in boxes:
        inner = grow(b.rect, -HEAD_HIDE)
        if inner[0] >= inner[2] or inner[1] >= inner[3]:
            continue
        for r in relations:
            for h in r.heads_at(b.name):
                corners = h.points if h.closed else (h.points[0], h.points[-1])
                if any(inner[0] < x < inner[2] and inner[1] < y < inner[3] for x, y in corners):
                    _add(found.get((b.name, h.points), lambda: (b, h, []))[2], r)
    for b, h, rels in found.values():
        whose = "·".join(f"관계 {r.name}" for r in sorted(rels, key=_index))
        yield Finding("line_through_box", (*_owners(rels), b.name), span(h.points),
                      f"선 끝 모양이 제 끝 상자에 가려진다: {whose}의 {h.name}(자리 {fmt_rect(span(h.points))}), {b.title}.",
                      "선이 상자 변을 너무 비스듬히 나간다 — 상자를 옮기거나 꺾는 점(via)을 주어 변에서 곧게 나가게 한다.")


def _trunk(a: _Relation, b: _Relation) -> bool:
    """상속·실체화 트리의 공유 줄기 — 서로 다른 자식이 같은 부모로 가는 같은 종류의 선이 한 삼각형을 함께 쓴다(끝 삼각형이 같다).
    그 두 선은 어디서 포개져도 따라가면 같은 삼각형에 닿으므로 관계가 사라지지 않는다(자식 상자에 닿으면 "선이 상자를 지난다"가
    따로 잡는다). 삼각형이 조금이라도 어긋나면 공유 줄기가 아니다 — 두 삼각형이 겹쳐 그려진다."""
    x, y = a.placed.relation, b.placed.relation
    if not (x.kind == y.kind and x.kind in TRUNK_KINDS and x.target == y.target and x.source != y.source):
        return False
    return a.end_shape is not None and b.end_shape is not None and _same(a.end_shape.points, b.end_shape.points)


def _alongside(s: Segment, t: Segment) -> Optional[Segment]:
    return alongside(s, t, OVERLAP_GAP, OVERLAP_MIN, PARALLEL_SIN)


def _line_overlaps(relations: list[_Relation], pairs: Pairs) -> tuple[list[Finding], list[Overlap]]:
    """한 선이 왔던 길을 되짚는 항목과, 두 선이 포개진 짝들."""
    retraces = []
    for r in relations:
        path = r.path
        parts = [c for j, s in enumerate(path) for t in path[j + 1:] if (c := _alongside(s, t)) is not None]
        if parts:
            where = _cover(parts)
            retraces.append(Finding("line_overlap", (r.owner,), where,
                                    f"선이 왔던 길을 되짚는다: {r.title}, 자리 ({fmt_rect(where)}).",
                                    "꺾는 점(via)을 고쳐 같은 길로 되돌아가지 않게 한다."))
    overlaps = []
    for r, o in pairs:
        if not _trunk(r, o):
            parts = [c for s in r.path for t in o.path if (c := _alongside(s, t)) is not None]
            if parts:
                overlaps.append((r, o, parts))
    return retraces, overlaps


def _merged_overlaps(overlaps: list[Overlap]) -> Iterator[Finding]:
    """같은 자리에서 포개진 짝들(공유 줄기에 포개진 선 등)은 한 항목으로 묶는다."""
    found = _Places()
    for r, o, parts in overlaps:
        where = _cover(parts)
        _add(found.get(where, lambda: (where, []))[1], r, o)
    for where, rels in found.values():
        yield Finding("line_overlap", _owners(rels), where, f"선끼리 포개진다: {_titles(rels)}, 자리 ({fmt_rect(where)}).",
                      "포개진 선은 한 선으로 보여 관계 하나가 사라진다 — 한 선에 꺾는 점(via)을 주거나 고쳐 두 선을 떼어 놓는다.")


def _overlap_pieces(overlaps: list[Overlap]) -> dict[frozenset[str], list[Segment]]:
    out: dict[frozenset[str], list[Segment]] = {}
    for r, o, parts in overlaps:
        out.setdefault(frozenset((r.owner, o.owner)), []).extend(parts)
    return out


def _by_overlap(near: dict[frozenset[str], list[Segment]], a: _Relation, b: _Relation, head: _Head) -> bool:
    """포개진 두 선 a·b는 포개진 조각 끝의 선 끝 모양에도 닿기 마련이다 — 그 조각에 붙은(OVERLAP_GAP 안) 선 끝 모양은 포개짐으로
    이미 알린 것으로 본다."""
    pieces = near.get(frozenset((a.owner, b.owner)), ())
    return any(distance(s, e, LINE_EPS) <= OVERLAP_GAP for s in pieces for e in head.edges) or head.holds(pieces)


def _lines_through_heads(relations: list[_Relation], pairs: Pairs,
                         near: dict[frozenset[str], list[Segment]]) -> Iterator[Finding]:
    """삼각형·마름모는 칠한 다각형이라 밑을 지나는 선을 가리고, 화살촉에 다른 선이 닿으면 어느 선의 것인지 헷갈린다. 같은 모양을
    같은 구간으로 지나는 선들(공유 줄기)과, 같은 자리에 같은 모양을 그린 관계들(공유 줄기의 삼각형)은 한 항목으로 묶는다."""
    found = _Places()

    def note(passer: _Relation, owner: _Relation, head: _Head, hit: list[Segment]) -> None:
        entry = found.get((passer is owner, head.points, tuple(hit)), lambda: (passer is owner, head, [], []))
        _add(entry[2], passer)
        _add(entry[3], owner)

    for r in relations:
        for h in r.heads:
            if hit := r.over_own(h):
                note(r, r, h, hit)
    for a, b in pairs:
        if _trunk(a, b):
            continue
        for r, o in ((a, b), (b, a)):
            for h in o.heads:
                if (hit := [s for s in r.path if h.near([s])]) and not _by_overlap(near, r, o, h):
                    note(r, o, h, hit)
    for own, h, passers, owners in found.values():
        where = span(h.points)
        if own:
            problem = f"선이 제 선 끝 모양에 닿는다: {_titles(passers)}, {h.name}(자리 {fmt_rect(where)})."
            hint = "꺾는 점(via)을 고쳐 선이 제 선 끝 모양을 비켜 가게 한다."
        else:
            whose = "·".join(f"관계 {o.name}" for o in sorted(owners, key=_index))
            problem = f"선이 다른 관계의 선 끝 모양에 닿는다: {_titles(passers)}, {whose}의 {h.name}(자리 {fmt_rect(where)})."
            hint = "닿은 선 끝 모양이 어느 선의 것인지 헷갈린다 — 그 선에 꺾는 점(via)을 주어 비켜 가게 하거나 상자를 옮긴다."
        yield Finding("line_through_head", _owners(passers, owners), where, problem, hint)


def _head_overlaps(relations: list[_Relation], pairs: Pairs,
                   near: dict[frozenset[str], list[Segment]]) -> Iterator[Finding]:
    """선 끝 모양끼리 겹친다 — 두 선은 닿지 않아도 화살촉이 다른 관계의 삼각형에 들어가거나, 한 관계의 두 끝(자기 관계)이 붙어 두
    모양이 겹치는 등. 같은 자리에 같은 모양을 그린 관계(공유 줄기의 삼각형)는 한 모양으로 묶는다."""
    found: list[_Places] = []  # 겹친 두 모양마다 {모양 열쇠: (모양, 그 모양을 그린 관계들)}

    def note(r: _Relation, a: _Head, o: _Relation, b: _Head) -> None:
        entry = next((e for e in found if all(any(_same(k, h.points) for k, _ in e.items) for h in (a, b))), None)
        if entry is None:
            entry = _Places()
            found.append(entry)
        for h, rel in ((a, r), (b, o)):
            _add(entry.get(h.points, lambda: (h, []))[1], rel)

    for r in relations:
        for i, a in enumerate(r.heads):
            for b in r.heads[i + 1:]:
                if a.meets(b):
                    note(r, a, r, b)
    for r, o in pairs:
        if _trunk(r, o):
            continue
        for a in r.heads:
            for b in o.heads:
                if a.meets(b) and not (_by_overlap(near, r, o, a) or _by_overlap(near, r, o, b)):
                    note(r, a, o, b)
    for entry in found:
        shapes = [(h, sorted(rels, key=_index)) for h, rels in entry.values()]
        parts = [f"{'·'.join(f'관계 {x.name}' for x in rels)}의 {h.name}(자리 {fmt_rect(span(h.points))})" for h, rels in shapes]
        yield Finding("head_overlap", _owners(*(rels for _, rels in shapes)), span(pt for h, _ in shapes for pt in h.points),
                      f"선 끝 모양끼리 겹친다: {', '.join(parts)}.",
                      "겹친 모양은 어느 선의 것인지 헷갈린다 — 꺾는 점(via)을 주어 한 선이 상자의 다른 곳에 닿게 하거나 상자를 옮긴다.")


def _lines_through_labels(relations: list[_Relation], labels: list[_Label]) -> Iterator[Finding]:
    """같은 글자를 같은 자리에서 지나는 선들(공유 줄기)은 한 항목으로 묶는다."""
    found = _Places()
    for k, lab in enumerate(labels):
        wide = grow(lab.box, TEXT_CLEARANCE)
        for r in relations:
            if meets(r.bounds, wide) and (parts := _parts(r.segments, wide)):
                where = _cover(parts)
                _add(found.get((k, where), lambda: (lab, where, []))[2], r)
    for lab, where, rels in found.values():
        own = rels == [lab.relation]
        hint = (LABEL_HINT if own else "선 글자 자리는 도구가 제 선 둘레의 빈 곳에서 고른다 — 지나가는 선에 꺾는 점(via)을 "
                "주어 글자를 비켜 가게 하거나, 상자를 옮겨 두 관계를 떼어 놓는다.")
        yield Finding("line_through_text", _owners(rels, [lab.relation]), where,
                      f"선이 글자를 지난다: {_titles(rels)}, {lab.title}.", hint)


def _labels_on_boxes(labels: list[_Label], boxes: list[_Box]) -> Iterator[Finding]:
    for lab in labels:
        for b in boxes:
            if not meets(grow(lab.box, TEXT_CLEARANCE), b.rect):
                continue
            what = ("선 글자가 상자에 겹친다" if meets(lab.box, b.rect)
                    else f"선 글자가 상자에 {fmt_num(TEXT_CLEARANCE)}px 안으로 붙어 있다")
            yield Finding("text_on_box", (lab.relation.owner, b.name), between(lab.box, b.rect),
                          f"{what}: {lab.title}, {b.title}.", LABEL_HINT)


def _label_overlaps(labels: list[_Label]) -> Iterator[Finding]:
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            if not meets(grow(a.box, TEXT_CLEARANCE), b.box):
                continue
            what = ("선 글자끼리 겹친다" if meets(a.box, b.box)
                    else f"선 글자끼리 {fmt_num(TEXT_CLEARANCE)}px 안으로 붙어 있다")
            yield Finding("text_overlap", _owners([a.relation, b.relation]), between(a.box, b.box),
                          f"{what}: {a.title}, {b.title}.", LABEL_HINT)


def _crossings(relations: list[_Relation], pairs: Pairs) -> Iterator[Finding]:
    """선끼리(한 선이 제 선을 건너가는 것도) 엇갈린 곳. 여러 선이 한 자리에서 엇갈리면(공유 줄기를 건너는 선 등) 한 곳으로 센다."""
    found = _Places()
    for r, o in [(r, r) for r in relations] + pairs:
        for x, y in crossings(r.points, None if o is r else o.points, LINE_EPS):
            _add(found.get((x, y), lambda: ((x, y, x, y), []))[1], r, o)
    for where, rels in found.values():
        who = (f"선이 제 선을 엇갈린다: {rels[0].title}" if len(rels) == 1 else f"선끼리 엇갈린다: {_titles(rels)}")
        yield Finding("crossing", _owners(rels), where, f"{who}, 자리 ({fmt_num(where[0])}, {fmt_num(where[1])}).",
                      CROSSING_HINT)

