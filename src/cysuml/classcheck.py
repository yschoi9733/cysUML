"""클래스도 검사: 그린 결과(classdiagram.Drawing)를 읽어 합격·불합격과 알림을 낸다.

불합격은 문서에 못 넣는 그림이다. 관계선(화살촉·삼각형·마름모 포함)이 양 끝이 아닌 상자나 선 글자(관계 이름·다중도)를 지날 때,
관계선이 다른 관계선과 포개지거나 선 끝 모양에 닿을 때, 선 끝 모양끼리 겹칠 때, 상자끼리 겹칠 때, 선 글자끼리 또는 선 글자와
상자가 겹칠 때다. 선끼리 엇갈린 곳과 그림 크기는 알림으로만 준다. 상속·실체화에서 자식 여럿의 선이 한 줄기로 부모의 한 삼각형에
모이는 것(공유 줄기)은 포개짐으로도, 선 끝 모양에 닿는 것으로도 치지 않는다.

관계선은 상자 밑에 그리므로 끝 상자 안으로 들어간 부분은 가려 보이지 않고, 상자 안 글자에 닿는 선은 그 상자를 먼저 지난다. 그래서
상자 안 글자를 지나는 선은 "선이 상자를 지난다" 한 항목으로 알린다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Iterator, Optional, Union

from .canvas import PAD, Canvas, Line, Point, Polygon
from .classdiagram import LABEL_CLEAR, Drawing, PlacedRelation, fmt_num, fmt_rect
from .geom import (Box, alongside, between, clip, crossings, distance, grow, hits, inside, lerp, meets, outline, span,
                   touches)

# 검사 여유값(논리 좌표 px)
BOX_CLEARANCE = 4  # 상자를 사방으로 이만큼 넓힌 곳에 선이나 다른 상자가 닿으면 지나간·겹친 것으로 본다
TEXT_CLEARANCE = LABEL_CLEAR  # 선 글자 상자를 넓히는 폭. 글자 자리를 고를 때와 같아야 도구가 빈 자리로 고른 글자가 합격한다
OVERLAP_GAP = 2  # 나란한 두 선의 가운데가 이만큼 안이면 한 선으로 보인다
OVERLAP_MIN = 4  # 그렇게 붙어 가는 길이가 이보다 길면 포개진 것으로 본다
PARALLEL_SIN = 0.05  # 두 선분 사이 각의 사인이 이 안이면(약 3°) 나란하다고 본다
LINE_EPS = 1e-6  # 점이 선에서 이 안이면 선 위로 본다(엇갈림이 아니라 맞닿음)
OWN_TRIM = 0.01  # 제 선 끝 모양이 얹힌 끝 구간과 이웃 구간이 만나는 꺾는 점에서, 이웃 구간을 이만큼 앞에서 끊고 본다

TRUNK_KINDS = ("generalization", "realization")
ROLES = {"name": "이름", "from_multiplicity": "from 쪽 다중도", "to_multiplicity": "to 쪽 다중도"}
LABEL_HINT = "선 글자 자리는 도구가 선 둘레의 빈 곳에서 고르는데 빈 곳이 없었다 — 상자를 떼어 놓거나, 꺾는 점(via)을 주어 선 둘레를 비운다."
CROSSING_HINT = "엇갈림을 줄이려면 상자 순서·자리를 바꾸거나, 꺾는 점(via)을 주어 돌아가게 한다."

Segment = tuple[Point, Point]


@dataclass(frozen=True)
class Finding:
    """검사 항목 하나. kind는 종류, elements는 걸린 요소의 이름(상자 이름이나 관계 기록의 owner), where는 걸린 자리(논리 좌표
    왼, 위, 오른, 아래 — 엇갈린 곳은 넓이가 없다), problem은 무엇이 걸렸는지, hint는 고치는 법이다.

    불합격 종류(이 차례로 낸다): box_overlap(상자끼리) · line_through_box(선이 상자를) · line_overlap(선끼리 포개짐, 한 선의
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
        return {"kind": self.kind, "elements": list(self.elements), "where": [_round(v) for v in self.where],
                "problem": self.problem, "hint": self.hint}


@dataclass(frozen=True)
class Report:
    """failures가 비어 있으면 합격이다. crossings는 선끼리 엇갈린 곳(알림), size는 논리 좌표로 잰 그림 폭·높이(둘레 여백
    포함), png_size는 scale배로 낼 PNG의 픽셀 수다 — 그 배율로는 너무 커 PNG를 그릴 수 없으면 None이다(합격과 따로 본다)."""

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
    닿은 꼭짓점, key는 같은 모양인지 견주는 열쇠다."""

    name: str
    points: tuple[Point, ...]
    closed: bool
    tip: Point
    edges: tuple[Segment, ...]
    key: tuple[float, ...]

    @classmethod
    def of(cls, record: Union[Line, Polygon]) -> _Head:
        closed = isinstance(record, Polygon)
        pts = record.points
        name = ("삼각형" if len(pts) == 3 else "마름모") if closed else "화살촉"
        return cls(name, pts, closed, pts[0] if closed else pts[1], tuple(outline([record])),
                   _key(v for p in pts for v in p))

    def meets(self, other: _Head) -> bool:
        if any(touches(e, f, LINE_EPS) for e in self.edges for f in other.edges):
            return True
        return ((other.closed and any(inside(v, other.points) for v in self.points))
                or (self.closed and any(inside(v, self.points) for v in other.points)))


@dataclass(frozen=True, eq=False)
class _Relation:
    """eq=False — 같은 객체끼리만 같다."""

    index: int
    placed: PlacedRelation
    heads: tuple[_Head, ...]
    path: tuple[Segment, ...]  # 선만(선 끝 모양 빼고)
    segments: tuple[Segment, ...]  # 선과 선 끝 모양의 테두리
    bounds: Box  # segments를 덮는 상자
    end_shape: Optional[_Head]  # to 쪽 끝의 삼각형·마름모

    @property
    def owner(self) -> str:
        return self.placed.owner

    @property
    def points(self) -> tuple[Point, ...]:
        return self.placed.points

    def around(self, head: _Head) -> tuple[Segment, ...]:
        """제 선 끝 모양 head에 닿는지 볼 구간들. 그 모양이 얹힌 끝 구간은 빼고, 바로 이웃 구간은 둘이 만나는 꺾는 점 OWN_TRIM
        앞에서 끊는다 — 끝 구간이 모양 길이와 같으면 그 꺾는 점이 모양 끝에 닿는데, 그건 선이 이어진 것이지 모양을 지난 게 아니다."""
        path = list(self.path)
        if math.dist(head.tip, self.points[0]) <= LINE_EPS:
            path = path[1:]
            if path:
                q, w = path[0]
                path[0] = (_toward(q, w, OWN_TRIM), w)
        elif math.dist(head.tip, self.points[-1]) <= LINE_EPS:
            path = path[:-1]
            if path:
                q, w = path[-1]
                path[-1] = (q, _toward(w, q, OWN_TRIM))
        return tuple(path)

    @property
    def name(self) -> str:
        return f"{self.owner}(relations[{self.index}])"

    @property
    def title(self) -> str:
        return f"선 {self.name}"


@dataclass(frozen=True)
class _Label:
    relation: _Relation
    role: str
    text: str
    box: Box

    @property
    def title(self) -> str:
        return f"관계 {self.relation.name}의 {ROLES[self.role]} '{self.text}'(자리 {fmt_rect(self.box)})"


Overlap = tuple[_Relation, _Relation, list[Segment]]  # 포개진 두 선과 포개진 조각들


def check(drawing: Drawing) -> Report:
    boxes, relations, labels = _read(drawing)
    retraces, overlaps = _line_overlaps(relations)
    near = _overlap_pieces(overlaps)
    failures = [*_box_overlaps(boxes), *_lines_through_boxes(relations, boxes), *retraces, *_merged_overlaps(overlaps),
                *_lines_through_heads(relations, near), *_head_overlaps(relations, near),
                *_lines_through_labels(relations, labels), *_labels_on_boxes(labels, boxes), *_label_overlaps(labels)]
    return Report(tuple(failures), tuple(_crossings(relations)), _size(drawing.canvas), drawing.canvas.png_size(),
                  drawing.canvas.scale)


def _read(drawing: Drawing) -> tuple[list[_Box], list[_Relation], list[_Label]]:
    """상자 자리와 관계선의 점은 자리 잡기 결과에서, 선 끝 모양과 선 글자는 관계마다 그린 기록(Drawing.drawn)에서 읽는다."""
    boxes = [_Box(p.box.name, p.rect) for p in drawing.layout.boxes]
    relations, labels = [], []
    for i, (p, d) in enumerate(zip(drawing.layout.relations, drawing.drawn)):
        heads = tuple(_Head.of(h) for h in d.heads)
        path = tuple(zip(p.points, p.points[1:]))
        segments = path + tuple(e for h in heads for e in h.edges)
        end = next((h for h in heads if h.closed and math.dist(h.tip, p.points[-1]) <= LINE_EPS), None)
        rel = _Relation(i, p, heads, path, segments, _cover(segments), end)
        relations.append(rel)
        labels += [_Label(rel, lab.role, t.text, t.box) for lab, t in zip(p.labels, d.labels)]
    return boxes, relations, labels


def _cover(segments: Iterable[Segment]) -> Box:
    return span(pt for s in segments for pt in s)


def _parts(segments: Iterable[Segment], rect: Box) -> list[Segment]:
    return [c for p, q in segments if (c := clip(p, q, rect)) is not None]


def _box_overlaps(boxes: list[_Box]) -> Iterator[Finding]:
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if not meets(grow(a.rect, BOX_CLEARANCE), b.rect):
                continue
            dx = max(b.rect[0] - a.rect[2], a.rect[0] - b.rect[2])
            dy = max(b.rect[1] - a.rect[3], a.rect[1] - b.rect[3])
            g = max(dx, dy)  # 가로·세로 가운데 더 떨어진 쪽. 음수면 둘 다 겹친다
            what = ("상자끼리 겹친다" if g < -LINE_EPS else "상자끼리 맞닿았다" if g <= LINE_EPS
                    else f"상자끼리 {fmt_num(g)}px밖에 떨어지지 않았다")
            yield Finding("box_overlap", (a.name, b.name), between(a.rect, b.rect), f"{what}: {a.title}, {b.title}.",
                          f"한쪽을 옮겨 가로나 세로로 {BOX_CLEARANCE}px 넘게 띄운다. 상자 크기는 글자에 맞춰 늘어난 값이니 "
                          "위 크기를 보고 옮긴다.")


def _lines_through_boxes(relations: list[_Relation], boxes: list[_Box]) -> Iterator[Finding]:
    for r in relations:
        ends = (r.placed.relation.source, r.placed.relation.target)
        for b in boxes:
            wide = grow(b.rect, BOX_CLEARANCE)
            if b.name in ends or not meets(r.bounds, wide):
                continue
            parts = _parts(r.segments, wide)
            if not parts:
                continue
            what = ("선이 상자를 지난다" if any(hits(p, q, b.rect) for p, q in parts)
                    else f"선이 상자에 {BOX_CLEARANCE}px 안으로 붙어 지나간다")
            fix = "꺾는 점(via)을 고쳐" if r.placed.relation.via else "선에 꺾는 점(via)을 주어"
            yield Finding("line_through_box", (r.owner, b.name), _cover(parts),
                          f"{what}: {r.title}, {b.title}.", f"그 상자를 옮기거나, {fix} 그 상자를 비켜 가게 한다.")


def _trunk(a: _Relation, b: _Relation) -> bool:
    """상속·실체화 트리의 공유 줄기 — 서로 다른 자식이 같은 부모로 가는 같은 종류의 선이 한 삼각형을 함께 쓴다(끝 삼각형이 같다).
    그 두 선은 어디서 포개져도 따라가면 같은 삼각형에 닿으므로 관계가 사라지지 않는다(자식 상자에 닿으면 "선이 상자를 지난다"가
    따로 잡는다). 삼각형이 조금이라도 어긋나면 공유 줄기가 아니다 — 두 삼각형이 겹쳐 그려진다."""
    x, y = a.placed.relation, b.placed.relation
    if not (x.kind == y.kind and x.kind in TRUNK_KINDS and x.target == y.target and x.source != y.source):
        return False
    return a.end_shape is not None and b.end_shape is not None and a.end_shape.key == b.end_shape.key


def _alongside(s: Segment, t: Segment) -> Optional[Segment]:
    return alongside(s, t, OVERLAP_GAP, OVERLAP_MIN, PARALLEL_SIN)


def _line_overlaps(relations: list[_Relation]) -> tuple[list[Finding], list[Overlap]]:
    """한 선이 왔던 길을 되짚는 항목과, 두 선이 포개진 짝들."""
    retraces, pairs = [], []
    for i, r in enumerate(relations):
        path = r.path
        parts = [c for j, s in enumerate(path) for t in path[j + 1:] if (c := _alongside(s, t)) is not None]
        if parts:
            where = _cover(parts)
            retraces.append(Finding("line_overlap", (r.owner,), where,
                                    f"선이 왔던 길을 되짚는다: {r.title}, 자리 ({fmt_rect(where)}).",
                                    "꺾는 점(via)을 고쳐 같은 길로 되돌아가지 않게 한다."))
        for o in relations[i + 1:]:
            if not meets(grow(r.bounds, OVERLAP_GAP), o.bounds) or _trunk(r, o):
                continue
            parts = [c for s in path for t in o.path if (c := _alongside(s, t)) is not None]
            if parts:
                pairs.append((r, o, parts))
    return retraces, pairs


def _key(values: Iterable[float]) -> tuple[float, ...]:
    """같은 자리인지 견주는 열쇠(계산 오차는 버린다)."""
    return tuple(round(v, 4) for v in values)


def _group(items: Iterable[tuple[tuple, Box, Iterable[_Relation]]]) -> list[tuple[tuple, Box, list[_Relation]]]:
    """같은 열쇠의 항목을 한데 묶어 (열쇠, 자리, 걸린 관계들 — 입력 차례)로. 공유 줄기처럼 여러 선이 한 자리에 겹쳐 그려진
    곳은 한 번만 알린다."""
    out: dict[tuple, tuple[Box, list[_Relation]]] = {}
    for key, where, rels in items:
        found = out.setdefault(key, (where, []))[1]
        for r in rels:
            if r not in found:
                found.append(r)
    return [(key, where, sorted(rels, key=_index)) for key, (where, rels) in out.items()]


def _merged_overlaps(pairs: list[Overlap]) -> Iterator[Finding]:
    spans = [(r, o, _cover(parts)) for r, o, parts in pairs]
    for _, where, rels in _group((_key(w), w, (r, o)) for r, o, w in spans):
        yield Finding("line_overlap", tuple(r.owner for r in rels), where,
                      f"선끼리 포개진다: {', '.join(r.title for r in rels)}, 자리 ({fmt_rect(where)}).",
                      "포개진 선은 한 선으로 보여 관계 하나가 사라진다 — 한 선에 꺾는 점(via)을 주거나 고쳐 두 선을 떼어 놓는다.")


def _overlap_pieces(pairs: list[Overlap]) -> dict[frozenset[str], list[Segment]]:
    out: dict[frozenset[str], list[Segment]] = {}
    for r, o, parts in pairs:
        out.setdefault(frozenset((r.owner, o.owner)), []).extend(parts)
    return out


def _by_overlap(near: dict[frozenset[str], list[Segment]], a: _Relation, b: _Relation, head: _Head) -> bool:
    """포개진 두 선 a·b는 포개진 조각 끝의 선 끝 모양에도 닿기 마련이다 — 그 조각에 붙은(OVERLAP_GAP 안) 선 끝 모양은 포개짐으로
    이미 알린 것으로 본다."""
    pieces = near.get(frozenset((a.owner, b.owner)), ())
    return any(distance(s, e, LINE_EPS) <= OVERLAP_GAP for s in pieces for e in head.edges) or (
        head.closed and any(inside(v, head.points) for s in pieces for v in s))


def _meets_head(path: Iterable[Segment], head: _Head) -> bool:
    path = tuple(path)
    if any(touches(s, e, LINE_EPS) for s in path for e in head.edges):
        return True
    return head.closed and any(inside(v, head.points) for s in path for v in s)


def _lines_through_heads(relations: list[_Relation], near: dict[frozenset[str], list[Segment]]) -> Iterator[Finding]:
    """삼각형·마름모는 칠한 다각형이라 밑을 지나는 선을 가리고, 화살촉에 다른 선이 닿으면 어느 선의 것인지 헷갈린다."""
    found = []
    for r in relations:
        for o in relations:
            if o is not r and (_trunk(r, o) or not meets(r.bounds, o.bounds)):
                continue
            for h in o.heads:
                if o is not r and _by_overlap(near, r, o, h):
                    continue
                if _meets_head(r.around(h) if o is r else r.path, h):
                    found.append(((r.owner, o is r, h.name, *h.key), span(h.points), (r, o)))
    for (owner, own, shape, *_), where, rels in _group(found):
        # 열쇠에 지나는 선의 owner가 들어 있어 묶음마다 그 선은 하나이고, 나머지는 같은 자리에 같은 모양을 그린 관계들이다
        r = next(x for x in rels if x.owner == owner)
        others = [x for x in rels if x is not r]
        if own:
            problem = f"선이 제 선 끝 모양에 닿는다: {r.title}, {shape}(자리 {fmt_rect(where)})."
            hint = "꺾는 점(via)을 고쳐 선이 제 선 끝 모양을 비켜 가게 한다."
        else:
            whose = "·".join(f"관계 {o.name}" for o in others)
            problem = f"선이 다른 관계의 선 끝 모양에 닿는다: {r.title}, {whose}의 {shape}(자리 {fmt_rect(where)})."
            hint = "닿은 선 끝 모양이 어느 선의 것인지 헷갈린다 — 그 선에 꺾는 점(via)을 주어 비켜 가게 하거나 상자를 옮긴다."
        yield Finding("line_through_head", (r.owner, *(o.owner for o in others)), where, problem, hint)


def _head_overlaps(relations: list[_Relation], near: dict[frozenset[str], list[Segment]]) -> Iterator[Finding]:
    """선 끝 모양끼리 겹친다 — 두 선은 닿지 않아도 화살촉이 다른 관계의 삼각형에 들어가는 등. 같은 자리에 같은 모양을 그린
    관계(공유 줄기의 삼각형)는 한 모양으로 묶는다."""
    found: dict[frozenset, dict[tuple, tuple[_Head, list[_Relation]]]] = {}
    for i, r in enumerate(relations):
        for o in relations[i + 1:]:
            if _trunk(r, o) or not meets(r.bounds, o.bounds):
                continue
            for a in r.heads:
                for b in o.heads:
                    if a.meets(b) and not (_by_overlap(near, r, o, a) or _by_overlap(near, r, o, b)):
                        entry = found.setdefault(frozenset((a.key, b.key)), {})
                        for h, rel in ((a, r), (b, o)):
                            rels = entry.setdefault(h.key, (h, []))[1]
                            if rel not in rels:
                                rels.append(rel)
    for entry in found.values():
        shapes = [(h, sorted(rels, key=_index)) for h, rels in entry.values()]
        parts = [f"{'·'.join(f'관계 {x.name}' for x in rels)}의 {h.name}(자리 {fmt_rect(span(h.points))})" for h, rels in shapes]
        owners = tuple(dict.fromkeys(x.owner for _, rels in shapes for x in rels))
        yield Finding("head_overlap", owners, span(pt for h, _ in shapes for pt in h.points),
                      f"선 끝 모양끼리 겹친다: {', '.join(parts)}.",
                      "겹친 모양은 어느 선의 것인지 헷갈린다 — 꺾는 점(via)을 주어 한 선이 상자의 다른 곳에 닿게 하거나 상자를 옮긴다.")


def _lines_through_labels(relations: list[_Relation], labels: list[_Label]) -> Iterator[Finding]:
    for r in relations:
        for lab in labels:
            wide = grow(lab.box, TEXT_CLEARANCE)
            if not meets(r.bounds, wide):
                continue
            parts = _parts(r.segments, wide)
            if not parts:
                continue
            own = lab.relation is r
            hint = (LABEL_HINT if own else "선 글자 자리는 도구가 제 선 둘레의 빈 곳에서 고른다 — 지나가는 선에 꺾는 점(via)을 "
                    "주어 글자를 비켜 가게 하거나, 상자를 옮겨 두 관계를 떼어 놓는다.")
            yield Finding("line_through_text", (r.owner,) if own else (r.owner, lab.relation.owner),
                          _cover(parts), f"선이 글자를 지난다: {r.title}, {lab.title}.", hint)


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
            owners = tuple(dict.fromkeys((a.relation.owner, b.relation.owner)))
            yield Finding("text_overlap", owners, between(a.box, b.box), f"{what}: {a.title}, {b.title}.", LABEL_HINT)


def _crossings(relations: list[_Relation]) -> Iterator[Finding]:
    """선끼리(한 선이 제 선을 건너가는 것도) 엇갈린 곳. 여러 선이 한 자리에서 엇갈리면(공유 줄기를 건너는 선 등) 한 곳으로 센다."""
    found = []
    for i, r in enumerate(relations):
        for o in relations[i:]:
            if o is not r and not meets(r.bounds, o.bounds):
                continue
            for x, y in crossings(r.points, None if o is r else o.points, LINE_EPS):
                found.append((_key((x, y)), (x, y, x, y), (r, o)))
    for _, where, rels in _group(found):
        x, y = where[0], where[1]
        who = (f"선이 제 선을 엇갈린다: {rels[0].title}" if len(rels) == 1
               else f"선끼리 엇갈린다: {', '.join(r.title for r in rels)}")
        yield Finding("crossing", tuple(r.owner for r in rels), where,
                      f"{who}, 자리 ({fmt_num(x)}, {fmt_num(y)}).", CROSSING_HINT)


def _index(r: _Relation) -> int:
    return r.index


def _toward(p: Point, q: Point, d: float) -> Point:
    """p에서 q 쪽으로 d만큼(선분 길이의 절반을 넘지 않게) 옮긴 점."""
    n = math.dist(p, q)
    return lerp(p, q, min(d, n / 2) / n)


def _size(canvas: Canvas) -> tuple[float, float]:
    b = canvas.bounds()
    assert b is not None  # 상자가 하나 이상이다
    return b[2] - b[0] + 2 * PAD, b[3] - b[1] + 2 * PAD


def _round(v: float) -> float:
    return round(v, 1) + 0.0
