"""AI가 배치하는 그림의 공용 검사: 그린 결과(boxdiagram.Drawing)를 읽어 합격·불합격과 알림을 낸다.

불합격은 문서에 못 넣는 그림이다 — 선(화살촉·삼각형·마름모 포함)이 요소·글자·다른 선을 가로지르거나 그것들에 붙어 한데
보이는 것, 요소나 글자끼리 겹치는 것이다. 종류는 KINDS에 낸 차례대로 있다. 선끼리 엇갈린 곳과 그림 크기는 알림으로만 준다.
상속·실체화처럼 공유 줄기를 받는 관계에서 자식 여럿의 선이 한 줄기로 부모의 한 삼각형에 모이는 것은 포개짐으로도, 선 끝
모양에 닿는 것으로도 치지 않는다. 공유 줄기처럼 여러 선이 한 자리에 겹쳐 그려진 곳이 걸리면 한 항목으로 묶어 알린다.

요소는 실제 테두리(사각형·타원·볼록 다각형)로 본다. 안에 다른 요소가 없는 요소는 선 위에 그리므로 끝 요소 안으로 들어간
선은 가려 보이지 않고, 요소 안 글자에 닿는 선은 그 요소를 먼저 지난다. 그래서 요소 안 글자를 지나는 선은 "선이 요소를
지난다" 한 항목으로 알린다. 안에 다른 요소를 품은 요소(바깥 요소)는 선보다 먼저 그리고, 선의 끝 요소를 품은 바깥 요소는 그
선이 안을 지나거나 테두리를 건너도 된다 — 다만 테두리를 따라가거나 이름 칸을 지나면 안 된다. 선 글자도 그 안에 놓일 수 있다.
"""
from __future__ import annotations

import math
import operator
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator, Optional, Union

from .boxdiagram import LABEL_CLEAR, NEST_PAD, Drawing, Layout, NameZone, PlacedBox, PlacedRelation, Words, josa
from .canvas import Line, Point, Polygon
from .geom import (Border, Box, alongside, axis_gap, between, clip, crossings, distance, enters, grow, hits, inside,
                   meets, outline, span, touches)
from .report import Finding, fmt_num, fmt_rect, round1
from .report import Report as _Report

# 검사 여유값(논리 좌표 px)
BOX_CLEARANCE = 4  # 요소를 사방으로 이만큼 넓힌 곳에 선이나 다른 요소가 닿으면 지나간·겹친 것으로 본다
TEXT_CLEARANCE = LABEL_CLEAR  # 선 글자 상자를 넓히는 폭. 글자 자리를 고를 때와 같아야 도구가 빈 자리로 고른 글자가 합격한다
OVERLAP_GAP = 2  # 나란한 두 선의 가운데가 이만큼 안이면 한 선으로 보인다
OVERLAP_MIN = 4  # 그렇게 붙어 가는 길이가 이보다 길면 포개진 것으로 본다(선이 제 끝 요소 테두리 BOX_CLEARANCE 안을 가는 길이도)
PARALLEL_SIN = 0.05  # 두 선분 사이 각의 사인이 이 안이면(약 3°) 나란하다고 본다
LINE_EPS = 1e-6  # 점이 선에서 이 안이면 선 위로 본다(엇갈림이 아니라 맞닿음)
HEAD_HIDE = 2  # 선 끝 모양이 제 끝 요소 안으로 이만큼 넘게 들어가면 가려진(들어간) 것으로 본다(살짝 들어가는 건 테두리 밑으로 일부러 넣은 것)
OWN_MARGIN = 0.5  # 선이 제 삼각형·마름모는 그 안쪽으로 이만큼 넘게 들어가야 지난 것으로 본다(테두리에 닿거나 따라가면 이어진 것)
PLACE_EPS = 1e-3  # 여러 선이 걸린 자리가 이 안으로 같으면 한 자리로 묶는다

ROLES = {"name": "이름", "from_multiplicity": "from 쪽 다중도", "to_multiplicity": "to 쪽 다중도"}
KINDS = (  # 불합격 종류(이 차례로 낸다)
    "box_overlap",  # 요소끼리 겹치거나 붙었다(품고 품긴 사이는 빼고)
    "inner_off_area",  # 안의 요소가 바깥 요소의 칸(안의 요소를 두는 곳) 밖으로 나가거나 테두리·이름 칸에 붙었다
    "line_through_box",  # 선이 양 끝도 아니고 끝을 품지도 않은 요소를 지나거나 붙어 지나간다
    "line_through_name",  # 선이 끝 요소의 몸통 밖 이름 칸이나, 끝을 품은 요소의 이름 칸을 지나거나 붙어 지나간다
    "line_along_container",  # 선이 끝을 품은 요소의 테두리 선을 따라간다
    "line_along_own_box",  # 선이 제 끝 요소에 붙어 간다(그 요소에 닿는 끝 구간은 빼고)
    "head_near_own_box",  # 반대쪽 끝의 선 끝 모양이 제 끝 요소 테두리에 붙는다
    "head_under_own_box",  # 선 끝 모양이 제 끝 요소 안으로 들어간다(선 뒤에 그린 요소면 가려진다)
    "line_overlap",  # 선끼리 포개지거나 한 선이 왔던 길을 되짚는다
    "line_through_head",  # 선이 선 끝 모양에 닿는다
    "head_overlap",  # 선 끝 모양끼리 겹친다
    "line_through_text",  # 선이 선 글자를 지난다
    "text_on_box",  # 선 글자가 요소에 겹친다(끝을 품은 요소면 그 테두리 선·이름 칸에)
    "text_overlap",  # 선 글자끼리 겹친다
)
NESTED_KINDS = ("inner_off_area", "line_through_name", "line_along_container")  # 안에 요소를 두거나 이름 칸이 있는 그림에서만 난다

Segment = tuple[Point, Point]


def label_hint(w: Words) -> str:
    return (f"선 글자 자리는 도구가 선 둘레의 빈 곳에서 고르는데 빈 곳이 없었다 — {w.noun}를 떼어 놓거나, 꺾는 점(via)을 주어 "
            "선 둘레를 비운다.")


def crossing_hint(w: Words) -> str:
    return f"엇갈림을 줄이려면 {w.noun} 순서·자리를 바꾸거나, 꺾는 점(via)을 주어 돌아가게 한다."


@dataclass(frozen=True)
class Report(_Report):
    """report.Report에 선끼리 엇갈린 곳(crossings, 알림)을 더한다. Finding의 elements는 요소 열쇠나 관계 기록의 owner이고,
    불합격 종류는 KINDS, 알림 종류는 crossing이다. words는 합격 문구·고치는 법에 쓰는 말이다."""

    crossings: tuple[Finding, ...] = field(kw_only=True)
    words: Words = field(kw_only=True, repr=False)

    @property  # type: ignore[override]
    def PASSED(self) -> str:
        return f"합격 — 선이 {self.words.noun}·글자를 지나거나 겹친 곳이 없다."

    @property  # type: ignore[override]
    def SHRINK(self) -> str:
        return f"{self.words.noun}를 가까이 모으거나 배율을 낮춘다"

    def _extra(self) -> dict:
        return {"crossings": [f.to_dict() for f in self.crossings]}

    def _notices(self) -> list[str]:
        return ([f"알림 — 선끼리 엇갈린 곳 {len(self.crossings)}곳" + (f". {crossing_hint(self.words)}" if self.crossings else "")]
                + [f"- {f.problem}" for f in self.crossings])


@dataclass(frozen=True, eq=False)
class _Box:
    """검사가 보는 요소. first면 선보다 먼저 그렸다(안에 다른 요소를 품었다)."""

    placed: PlacedBox
    noun: str
    first: bool

    @property
    def name(self) -> str:
        return self.placed.key

    @property
    def rect(self) -> Box:
        return self.placed.rect

    @property
    def border(self) -> Border:
        return self.placed.border

    @property
    def zones(self) -> tuple[NameZone, ...]:
        return self.placed.zones

    @property
    def title(self) -> str:
        return f"{self.noun} {self.name}({fmt_rect(self.rect)})"


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
    trunk: bool  # 공유 줄기를 받는 관계 종류인지
    holders: frozenset[str]  # 끝 요소를 품은 요소들

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
        """제 끝 요소 box에 닿는 끝(points의 처음 0, 마지막 -1)."""
        rel = self.placed.relation
        return [i for i, name in ((0, rel.source), (-1, rel.target)) if name == box]

    def heads_at(self, box: str) -> list[_Head]:
        """제 끝 요소 box에 닿는 끝에 얹힌 선 끝 모양."""
        tips = [self.points[i] for i in self._ends_at(box)]
        return [h for h in self.heads if any(math.dist(h.tip, t) <= LINE_EPS for t in tips)]

    def away_from(self, box: str) -> tuple[tuple[Segment, ...], tuple[Segment, ...]]:
        """제 끝 요소 box에 붙어 가는지 볼 (선 구간, 선 끝 모양 테두리). 그 요소에 닿는 끝 구간과 그 끝에 얹힌 선 끝 모양은 뺀다 —
        끝 구간은 요소 가운데를 향해 나가므로, 넓은 요소 테두리를 비스듬히 나가는 평범한 선도 처음 몇 px는 테두리에 붙어 있다."""
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
    lay = drawing.layout
    w = lay.spec.words
    boxes, relations, labels = _read(drawing)
    pairs = [(r, o) for i, r in enumerate(relations) for o in relations[i + 1:]
             if meets(grow(r.bounds, OVERLAP_GAP), o.bounds)]  # 서로 닿을 수 있는 두 선(앞 선, 뒤 선)
    retraces, overlaps = _line_overlaps(relations, pairs)
    near = _overlap_pieces(overlaps)
    failures = [*_box_overlaps(boxes, lay, w), *_inner_off_area(boxes, lay, w), *_lines_through_boxes(relations, boxes, w),
                *_lines_through_names(relations, boxes, w), *_lines_along_containers(relations, boxes, w),
                *_heads_under_own_box(relations, boxes, w), *retraces, *_merged_overlaps(overlaps),
                *_lines_through_heads(relations, pairs, near, w), *_head_overlaps(relations, pairs, near, w),
                *_lines_through_labels(relations, labels, w), *_labels_on_boxes(labels, boxes, w), *_label_overlaps(labels, w)]
    failures.sort(key=lambda f: KINDS.index(f.kind))
    measured = drawing.canvas.measure()
    if measured is None:
        raise ValueError("그린 것이 없다")
    return Report(tuple(failures), measured.size, measured.png, drawing.canvas.scale,
                  crossings=tuple(_crossings(relations, pairs, w)), words=w)


def _read(drawing: Drawing) -> tuple[list[_Box], list[_Relation], list[_Label]]:
    """요소 자리와 관계선의 점은 자리 잡기 결과에서, 선 끝 모양과 선 글자는 관계마다 그린 기록(Drawing.drawn)에서 읽는다."""
    lay = drawing.layout
    boxes = [_Box(p, lay.spec.words.noun, p.key in lay.parents) for p in lay.boxes]
    relations, labels = [], []
    for i, (p, d) in enumerate(zip(lay.relations, drawing.drawn, strict=True)):
        points = d.line.points
        heads = tuple(_Head.of(h) for h in d.heads)
        path = tuple(zip(points, points[1:]))
        segments = path + tuple(e for h in heads for e in h.edges)
        end = next((h for h in heads if h.closed and math.dist(h.tip, points[-1]) <= LINE_EPS), None)
        rel = _Relation(i, p, points, heads, path, segments, _cover(segments), end, lay.kind_of(p.relation).trunk,
                        lay.holders(p.relation))
        relations.append(rel)
        labels += [_Label(rel, lab.role, " ".join(t.text for t in texts), span(pt for t in texts for pt in (t.box[:2], t.box[2:])))
                   for lab, texts in zip(p.labels, d.labels, strict=True)]
    return boxes, relations, labels


def _cover(segments: Iterable[Segment]) -> Box:
    return span(pt for s in segments for pt in s)


def _parts(segments: Iterable[Segment], rect: Box) -> list[Segment]:
    return [c for p, q in segments if (c := clip(p, q, rect)) is not None]


def _clipped(segments: Iterable[Segment], border: Border) -> list[Segment]:
    return [c for p, q in segments if (c := border.clip(p, q)) is not None]


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


def _box_overlaps(boxes: list[_Box], lay: Layout, w: Words) -> Iterator[Finding]:
    """품고 품긴 사이(여러 겹 포함)가 아닌 두 요소가 겹치거나 BOX_CLEARANCE 안으로 붙었다. 자리(모양 밖 이름까지)로 본다."""
    fit = "글자와 안의 요소에" if lay.spec.extended else "글자에"
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if a.name in lay.ancestors(b.name) or b.name in lay.ancestors(a.name):
                continue
            g = axis_gap(a.rect, b.rect)
            if g > BOX_CLEARANCE:
                continue
            what = (f"{w.noun}끼리 겹친다" if g < -LINE_EPS else f"{w.noun}끼리 맞닿았다" if round1(g) == 0
                    else f"{w.noun}끼리 {fmt_num(g)}px밖에 떨어지지 않았다")
            hint = (f"한쪽을 옮겨 가로나 세로로 {BOX_CLEARANCE}px 넘게 띄운다. {w.noun} 크기는 {fit} 맞춰 늘어난 값이니 "
                    "위 크기를 보고 옮긴다.")
            for outer, inner in ((a, b), (b, a)):
                o = outer.rect
                if (lay.spec.extended and outer.placed.shape.holds and o[0] <= inner.rect[0] and o[1] <= inner.rect[1]
                        and inner.rect[2] <= o[2] and inner.rect[3] <= o[3]):
                    hint += f" {inner.name}를 {outer.name} 안에 두려면 {inner.name}의 in에 {outer.name}를 준다."
            yield Finding("box_overlap", (a.name, b.name), between(a.rect, b.rect), f"{what}: {a.title}, {b.title}.", hint)


def _inner_off_area(boxes: list[_Box], lay: Layout, w: Words) -> Iterator[Finding]:
    """안의 요소는 바깥 요소의 칸(안의 요소를 두는 곳)의 테두리에서 NEST_PAD 이상 떨어져야 한다. 바깥 요소는 그 여백을 두고
    오른쪽·아래로 늘어나므로 걸리는 것은 대개 왼쪽·위다."""
    by_key = {b.name: b for b in boxes}
    for b in boxes:
        parent = b.placed.box.parent
        if parent is None:
            continue
        p = by_key[parent]
        area = p.placed.inner
        assert area is not None
        r = b.rect
        room = min(r[0] - area[0], r[1] - area[1], area[2] - r[2], area[3] - r[3])
        if room >= NEST_PAD - LINE_EPS:
            continue
        if any(meets(r, z.rect) for z in p.zones):
            what = f"안의 {w.noun}가 바깥 {w.noun}의 이름 칸에 걸친다"
        elif room < 0:
            what = f"안의 {w.noun}가 바깥 {w.noun}의 칸 밖으로 나간다"
        else:
            what = f"안의 {w.noun}가 바깥 {w.noun}의 칸 테두리에서 {fmt_num(room)}px밖에 떨어지지 않았다"
        yield Finding("inner_off_area", (b.name, p.name), r,
                      f"{what}: {b.title}, {p.title}(안의 {w.noun}를 두는 칸 {fmt_rect(area)}).",
                      f"안의 {w.noun}를 그 칸 테두리에서 {NEST_PAD}px 이상 들여 놓는다 — 바깥 {w.noun}는 안의 {w.noun}에 맞춰 "
                      f"오른쪽·아래로만 늘어나므로, 안의 {w.noun}를 오른쪽·아래로 옮기거나 바깥 {w.noun}의 left·top을 왼쪽·위로 옮긴다.")


@dataclass(eq=False)
class _BoxHit:
    """요소 하나에 같은 자리로 걸린 선들. own이면 그 요소가 선들의 끝 요소다. inside는 묶인 선 가운데 하나라도 요소 안을 지나는지,
    along은 (끝 요소일 때) 선 구간이 그 요소 둘레 BOX_CLEARANCE 안을 OVERLAP_MIN 넘게 가는지다 — 아니면 반대쪽 끝의 선 끝 모양만
    그 요소 테두리에 붙었다."""

    box: _Box
    where: Box
    own: bool
    inside: bool = False
    along: bool = False
    rels: list[_Relation] = field(default_factory=list)


def _length(parts: Iterable[Segment]) -> float:
    return sum(math.dist(p, q) for p, q in parts)


def _lines_through_boxes(relations: list[_Relation], boxes: list[_Box], w: Words) -> Iterator[Finding]:
    """선이 양 끝도 아니고 끝을 품지도 않은 요소(몸통 밖 이름 칸까지)를 지나거나, 제 끝 요소에 붙어 간다(테두리를 따라가면 두
    겹으로 보인다). 같은 요소를 같은 자리에서 지나는 선들(공유 줄기)은 한 항목으로 묶는다. 끝을 품은 요소는 따로 본다."""
    found = _Places()
    for b in boxes:
        wide = b.border.grown(BOX_CLEARANCE)
        names = [grow(z.rect, BOX_CLEARANCE) for z in b.zones if z.outside]
        reach = span(pt for r in (wide.bounds, *names) for pt in (r[:2], r[2:]))
        for r in relations:
            if not meets(r.bounds, reach) or b.name in r.holders:
                continue
            own = b.name in (r.placed.relation.source, r.placed.relation.target)
            if own:
                path, edges = r.away_from(b.name)
                on_path, on_heads = _clipped(path, wide), _clipped(edges, wide)
                parts = on_path + on_heads
                if _length(parts) <= OVERLAP_MIN:
                    continue  # 제 끝 요소 띠를 잠깐 스치는 꺾음은 테두리를 따라가는 게 아니다
            else:
                on_path, parts = [], _clipped(r.segments, wide) + [c for n in names for c in _parts(r.segments, n)]
            if parts:
                where = _cover(parts)
                along = own and _length(on_path) > OVERLAP_MIN
                hit = found.get((b.name, own, along, where), lambda: _BoxHit(b, where, own, along=along))
                hit.inside = hit.inside or (not own and any(
                    b.border.hits(p, q) or any(hits(p, q, z.rect) for z in b.zones if z.outside) for p, q in parts))
                _add(hit.rels, r)
    for hit in found.values():
        b, rels, vias = hit.box, hit.rels, {r.via for r in hit.rels}
        if hit.own and hit.along:
            yield Finding("line_along_own_box", (*_owners(rels), b.name), hit.where,
                          f"선이 제 끝 {w.noun}에 {BOX_CLEARANCE}px 안으로 붙어 간다: {_titles(rels)}, {b.title}.",
                          f"선이 {w.noun} 테두리에 붙어 보인다({w.edge}{josa(w.edge, '을', '를')} 따라가면 테두리가 두 겹으로 "
                          f"보인다) — 꺾는 점(via)을 고쳐 그 {w.noun}에서 {BOX_CLEARANCE}px 넘게 띄운다.")
        elif hit.own:
            fix = (f"두 {w.noun}를 더 떼어 놓는다" if vias == {False}
                   else f"꺾는 점(via)을 고치거나 두 {w.noun}를 더 떼어 놓는다")
            yield Finding("head_near_own_box", (*_owners(rels), b.name), hit.where,
                          f"선 끝 모양이 제 끝 {w.noun} {w.edge}에 {BOX_CLEARANCE}px 안으로 붙는다: {_titles(rels)}, {b.title}.",
                          f"반대쪽 끝의 화살촉·삼각형·마름모가 이 {w.noun} {w.edge}에 닿아 보인다 — {fix}.")
        else:
            what = (f"선이 {w.noun}를 지난다" if hit.inside
                    else f"선이 {w.noun}에 {BOX_CLEARANCE}px 안으로 붙어 지나간다")
            fix = ("꺾는 점(via)을 고쳐" if vias == {True} else "선에 꺾는 점(via)을 주어" if vias == {False}
                   else "꺾는 점(via)을 주거나 고쳐")
            yield Finding("line_through_box", (*_owners(rels), b.name), hit.where, f"{what}: {_titles(rels)}, {b.title}.",
                          f"그 {w.noun}를 옮기거나, {fix} 그 {w.noun}를 비켜 가게 한다.")


def _lines_through_names(relations: list[_Relation], boxes: list[_Box], w: Words) -> Iterator[Finding]:
    """선이 끝 요소의 몸통 밖 이름 칸(패키지 탭·모양 밖 이름)이나, 끝을 품은 요소의 이름 칸을 지나거나 BOX_CLEARANCE 안으로
    붙는다. 끝 요소의 몸통 안 이름 칸은 보지 않는다 — 선 끝과 끝 모양은 그 칸 쪽 테두리에 닿아도 되고, 칸 안으로 들어가는 선은
    입력 오류(선이 끝 요소 안을 지난다)나 선 끝 모양이 그 요소 안으로 들어간 것으로 따로 걸린다."""
    found = _Places()
    for b in boxes:
        for r in relations:
            holder = b.name in r.holders
            if not holder and b.name not in (r.placed.relation.source, r.placed.relation.target):
                continue
            for z in b.zones:
                if not (holder or z.outside):
                    continue
                wide = grow(z.rect, BOX_CLEARANCE)
                if meets(r.bounds, wide) and (parts := _parts(r.segments, wide)):
                    where = _cover(parts)
                    _add(found.get((b.name, z.rect, where), lambda: (b, z, where, []))[3], r)
    for b, z, where, rels in found.values():
        yield Finding("line_through_name", (*_owners(rels), b.name), where,
                      f"선이 {w.noun}의 이름 칸을 지나거나 {BOX_CLEARANCE}px 안으로 붙는다: {_titles(rels)}, {b.title}의 이름 칸"
                      f"({fmt_rect(z.rect)}).",
                      f"이름 칸은 그 {w.noun}가 끝인 선(몸통 밖 이름 칸일 때)이나 그 {w.noun} 안의 {w.noun}를 잇는 선도 지나가면 "
                      f"안 된다 — 꺾는 점(via)을 주거나 고쳐 이름 칸에서 {BOX_CLEARANCE}px 넘게 비켜 가게 한다.")


def _lines_along_containers(relations: list[_Relation], boxes: list[_Box], w: Words) -> Iterator[Finding]:
    """선이 끝을 품은 요소의 테두리 선을 BOX_CLEARANCE 안으로 OVERLAP_MIN 넘게 나란히 따라간다 — 건너는 것은 괜찮다."""
    found = _Places()
    for b in boxes:
        for r in relations:
            if b.name not in r.holders:
                continue
            parts = [c for e in b.placed.frame for s in r.path
                     if (c := alongside(e, s, BOX_CLEARANCE, OVERLAP_MIN, PARALLEL_SIN)) is not None]
            if parts:
                where = _cover(parts)
                _add(found.get((b.name, where), lambda: (b, where, []))[2], r)
    for b, where, rels in found.values():
        yield Finding("line_along_container", (*_owners(rels), b.name), where,
                      f"선이 끝을 품은 {w.noun}의 테두리를 {BOX_CLEARANCE}px 안으로 따라간다: {_titles(rels)}, {b.title}, "
                      f"자리 ({fmt_rect(where)}).",
                      f"그 {w.noun} 안의 {w.noun}를 잇는 선은 테두리를 건너도 되지만, 따라가면 테두리와 한 선으로 보인다 — 꺾는 "
                      f"점(via)을 고쳐 테두리에서 {BOX_CLEARANCE}px 넘게 띄우거나 곧게 건너게 한다.")


def _heads_under_own_box(relations: list[_Relation], boxes: list[_Box], w: Words) -> Iterator[Finding]:
    """선 끝 모양이 제 끝 요소 안으로 HEAD_HIDE 넘게 들어간다. 선 뒤에 그린 요소는 그 모양을 가리고, 선 앞에 그린 요소(바깥 요소)는
    안의 것과 겹쳐 보인다. 선이 넓은 테두리를 아주 비스듬히 나가면 마름모·삼각형 꼭짓점이나 화살촉 갈래가 요소 안으로 들어간다.
    같은 모양(공유 줄기의 삼각형)은 한 항목으로 묶는다."""
    found = _Places()
    for b in boxes:
        inner = b.border.grown(-HEAD_HIDE)
        if inner.empty:
            continue
        for r in relations:
            for h in r.heads_at(b.name):
                corners = h.points if h.closed else (h.points[0], h.points[-1])
                if any(inner.holds(c) for c in corners):
                    _add(found.get((b.name, h.points), lambda: (b, h, []))[2], r)
    for b, h, rels in found.values():
        whose = "·".join(f"관계 {r.name}" for r in sorted(rels, key=_index))
        at = f"{whose}의 {h.name}(자리 {fmt_rect(span(h.points))}), {b.title}."
        if b.first:
            yield Finding("head_under_own_box", (*_owners(rels), b.name), span(h.points),
                          f"선 끝 모양이 그 {w.noun} 안으로 들어간다: {at}",
                          f"선이 {w.noun} {w.edge}에 너무 비스듬히 들어온다 — {w.noun}를 옮기거나 꺾는 점(via)을 주어 "
                          f"{w.edge}에 곧게 닿게 한다.")
        else:
            yield Finding("head_under_own_box", (*_owners(rels), b.name), span(h.points),
                          f"선 끝 모양이 제 끝 {w.noun}에 가려진다: {at}",
                          f"선이 {w.noun} {w.edge}{josa(w.edge, '을', '를')} 너무 비스듬히 나간다 — {w.noun}를 옮기거나 꺾는 "
                          f"점(via)을 주어 {w.edge}에서 곧게 나가게 한다.")


def _trunk(a: _Relation, b: _Relation) -> bool:
    """상속·실체화 트리의 공유 줄기 — 서로 다른 자식이 같은 부모로 가는 같은 종류의 선이 한 삼각형을 함께 쓴다(끝 삼각형이 같다).
    그 두 선은 어디서 포개져도 따라가면 같은 삼각형에 닿으므로 관계가 사라지지 않는다(자식 요소에 닿으면 "선이 요소를 지난다"가
    따로 잡는다). 삼각형이 조금이라도 어긋나면 공유 줄기가 아니다 — 두 삼각형이 겹쳐 그려진다."""
    x, y = a.placed.relation, b.placed.relation
    if not (x.kind == y.kind and a.trunk and x.target == y.target and x.source != y.source):
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


def _lines_through_heads(relations: list[_Relation], pairs: Pairs, near: dict[frozenset[str], list[Segment]],
                         w: Words) -> Iterator[Finding]:
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
            hint = f"닿은 선 끝 모양이 어느 선의 것인지 헷갈린다 — 그 선에 꺾는 점(via)을 주어 비켜 가게 하거나 {w.noun}를 옮긴다."
        yield Finding("line_through_head", _owners(passers, owners), where, problem, hint)


def _head_overlaps(relations: list[_Relation], pairs: Pairs, near: dict[frozenset[str], list[Segment]],
                   w: Words) -> Iterator[Finding]:
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
                      f"겹친 모양은 어느 선의 것인지 헷갈린다 — 꺾는 점(via)을 주어 한 선이 {w.noun}의 다른 곳에 닿게 하거나 "
                      f"{w.noun}를 옮긴다.")


def _lines_through_labels(relations: list[_Relation], labels: list[_Label], w: Words) -> Iterator[Finding]:
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
        hint = (label_hint(w) if own else "선 글자 자리는 도구가 제 선 둘레의 빈 곳에서 고른다 — 지나가는 선에 꺾는 점(via)을 "
                f"주어 글자를 비켜 가게 하거나, {w.noun}를 옮겨 두 관계를 떼어 놓는다.")
        yield Finding("line_through_text", _owners(rels, [lab.relation]), where,
                      f"선이 글자를 지난다: {_titles(rels)}, {lab.title}.", hint)


def _labels_on_boxes(labels: list[_Label], boxes: list[_Box], w: Words) -> Iterator[Finding]:
    """선 글자가 요소(몸통 밖 이름 칸까지)에 겹치거나 TEXT_CLEARANCE 안으로 붙는다. 끝을 품은 요소는 안에 글자를 둘 수 있으므로
    그 테두리 선과 이름 칸만 본다."""
    for lab in labels:
        wide = grow(lab.box, TEXT_CLEARANCE)
        for b in boxes:
            if b.name in lab.relation.holders:
                zone = next((z for z in b.zones if meets(wide, z.rect)), None)
                if zone is not None:
                    what, where = f"선 글자가 끝을 품은 {w.noun}의 이름 칸에 겹친다", between(lab.box, zone.rect)
                elif edges := [(p, q) for p, q in b.placed.frame if hits(p, q, wide)]:
                    what, where = f"선 글자가 끝을 품은 {w.noun}의 테두리 선에 겹친다", _cover(edges)
                else:
                    continue
            else:
                names = [z.rect for z in b.zones if z.outside]
                if not (b.border.meets(wide) or any(meets(wide, n) for n in names)):
                    continue
                touching = b.border.meets(lab.box) or any(meets(lab.box, n) for n in names)
                what = (f"선 글자가 {w.noun}에 겹친다" if touching
                        else f"선 글자가 {w.noun}에 {fmt_num(TEXT_CLEARANCE)}px 안으로 붙어 있다")
                where = between(lab.box, b.rect)
            yield Finding("text_on_box", (lab.relation.owner, b.name), where, f"{what}: {lab.title}, {b.title}.", label_hint(w))


def _label_overlaps(labels: list[_Label], w: Words) -> Iterator[Finding]:
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            if not meets(grow(a.box, TEXT_CLEARANCE), b.box):
                continue
            what = ("선 글자끼리 겹친다" if meets(a.box, b.box)
                    else f"선 글자끼리 {fmt_num(TEXT_CLEARANCE)}px 안으로 붙어 있다")
            yield Finding("text_overlap", _owners([a.relation, b.relation]), between(a.box, b.box),
                          f"{what}: {a.title}, {b.title}.", label_hint(w))


def _crossings(relations: list[_Relation], pairs: Pairs, w: Words) -> Iterator[Finding]:
    """선끼리(한 선이 제 선을 건너가는 것도) 엇갈린 곳. 여러 선이 한 자리에서 엇갈리면(공유 줄기를 건너는 선 등) 한 곳으로 센다."""
    found = _Places()
    for r, o in [(r, r) for r in relations] + pairs:
        for x, y in crossings(r.points, None if o is r else o.points, LINE_EPS):
            _add(found.get((x, y), lambda: ((x, y, x, y), []))[1], r, o)
    for where, rels in found.values():
        who = (f"선이 제 선을 엇갈린다: {rels[0].title}" if len(rels) == 1 else f"선끼리 엇갈린다: {_titles(rels)}")
        yield Finding("crossing", _owners(rels), where, f"{who}, 자리 ({fmt_num(where[0])}, {fmt_num(where[1])}).",
                      crossing_hint(w))
