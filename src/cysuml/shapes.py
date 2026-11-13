"""여러 그림이 함께 쓰는 요소 모양: 패키지·컴포넌트·아티팩트·노드와 컴포넌트·아티팩트의 아이콘 표기, 그리고 이것들과 클래스를 한
그림에 섞어 받는 종류 목록(SHAPES).

패키지도·컴포넌트도·배치도(deployment diagram)가 같은 모양을 두 번 만들지 않게 여기 둔다. 문서 아이콘 아티팩트 밖의 모양은 클래스처럼
스테레오타입을 받아 이름 위 줄에 쓰고, 머리 칸 글자는 클래스 머리 칸과 같은 자리 규칙(classdiagram.draw_head)을 쓴다.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from .boxdiagram import NEST_PAD, Element, NameZone, PlacedBox, Shape, floored
from .canvas import Canvas, Point
from .classdiagram import CLASS_SHAPES, MIN_WIDTH, draw_head, head_height, head_lines, head_width
from .geom import Border, PolygonBorder, RectBorder, Segment
from .text import Box

TAB_MIN = 50       # 패키지 탭의 최소 폭
# 패키지 몸통은 탭보다 적어도 이만큼 넓다. 패키지로 오가는 선은 탭 오른쪽 몸통의 가운데(탭 오른쪽 끝에서 TAB_STEP/2 이상)를
# 향하므로, 위에서 곧게 내려오는 선의 끝 모양(삼각형 반폭 9)이 탭 둘레 검사 여유(4px)에 닿지 않는다
TAB_STEP = 40
PACKAGE_BODY = 40  # 비어 있는 패키지 몸통의 높이
BOX_BODY = 24      # 컴포넌트·아티팩트에서 머리 칸 밖에 더하는 높이(이름 한 줄이면 클래스 기본 높이 48)
ICON_ROOM = 16     # 컴포넌트·아티팩트 아이콘이 이름과 겹치지 않게 머리 칸 좌우에 더하는 폭
ICON_MARGIN = 6    # 아이콘과 상자 오른쪽·위 변 사이
DEPTH = 8          # 노드 두께 띠의 폭. BOX_CLEARANCE의 두 배 안이라 띠 안을 따라가는 선은 늘 띠 한쪽 변에 붙어 걸린다
NODE_BODY = 24     # 노드 앞면에서 이름 줄 밖에 더하는 높이
PART = (16, 6)     # UML 1 표기 컴포넌트의 부품 네모 폭·높이. 폭의 반이 상자 왼쪽 변 밖으로 튀어나온다
# 부품 네모와 선이 향하는 점 높이 사이(두 네모 사이 24px — UML 1 아이콘처럼 네모가 상자 위아래 4분의 1쯤에 놓인다). 왼쪽에서
# 가로로 곧게 들어오는 선 끝 모양은 네모가 있는 x 범위에서 반폭 6을 넘지 않아(삼각형은 끝 쪽이 좁고, 마름모는 가운데가 반폭 6)
# 네모 둘레 검사 여유(4px)에서 2px 더 떨어진다 — 10이면 마름모·삼각형이 걸린다(실측). 상자가 가장 낮을 때(48)도 네모가 위아래
# 변에서 6px 안쪽에 든다
PART_OFF = 12
PAGE = (30, 38)    # 문서 아이콘 아티팩트의 문서 폭·높이
FOLD = 10          # 문서 아이콘의 접힌 귀


Head = tuple[tuple[tuple[str, bool], ...], float, float]  # (머리 칸 줄, 폭, 높이)


@lru_cache(maxsize=1024)
def _head_of(keyword: Optional[str], names: tuple[str, ...]) -> Head:
    head = head_lines(keyword, names)
    return tuple(head), head_width(head), head_height(head)


class _HeadShape(Shape):
    """이름을 클래스 머리 칸처럼 쓰는 모양: «스테레오타입» 줄 아래에 이름 줄(굵게). 머리 칸은 모양의 메서드마다 쓰므로 글자 폭은
    한 번만 잰다."""

    def head(self, e: Element) -> Head:
        return _head_of(self.keyword(e), e.name)


class PackageShape(_HeadShape):
    """패키지: 이름(과 스테레오타입)을 쓴 탭이 몸통 왼쪽 위에 붙은 폴더. 안에 요소를 두는 칸은 몸통이고, 선은 몸통 테두리에 닿는다.
    탭은 몸통 밖에 붙은 이름 칸이라 그 패키지가 끝인 선도 지나가면 안 된다 — 그래서 선은 몸통 가운데가 아니라 탭 오른쪽 몸통의
    가운데를 향한다. 탭 오른쪽 빈 곳은 패키지가 아니다."""

    holds = True
    aims_aside = True

    def _tab(self, e: Element) -> Head:
        """(탭 머리 칸 줄, 탭 폭, 탭 높이)."""
        lines, w, h = self.head(e)
        return lines, max(TAB_MIN, w), h

    def size(self, e: Element) -> tuple[float, float]:
        _, tab_w, tab_h = self._tab(e)
        return max(MIN_WIDTH, tab_w + TAB_STEP), tab_h + PACKAGE_BODY

    def parts(self, e: Element, rect: Box) -> tuple[Border, ...]:
        """탭과 몸통 — 탭 오른쪽 빈 곳은 패키지가 아니다."""
        _, tab_w, tab_h = self._tab(e)
        return (RectBorder((rect[0], rect[1], rect[0] + tab_w, rect[1] + tab_h)),
                RectBorder((rect[0], rect[1] + tab_h, rect[2], rect[3])))

    def anchor(self, e: Element, rect: Box) -> tuple[float, float]:
        _, tab_w, tab_h = self._tab(e)
        return (rect[0] + tab_w + rect[2]) / 2, (rect[1] + tab_h + rect[3]) / 2

    def insets(self, e: Element) -> Box:
        return 0.0, self._tab(e)[2], 0.0, 0.0

    def border(self, e: Element, rect: Box) -> Border:
        return RectBorder((rect[0], rect[1] + self._tab(e)[2], rect[2], rect[3]))

    def name_zones(self, e: Element, rect: Box) -> tuple[NameZone, ...]:
        _, tab_w, tab_h = self._tab(e)
        return (NameZone((rect[0], rect[1], rect[0] + tab_w, rect[1] + tab_h), True),)

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        head, tab_w, tab_h = self._tab(p.box)
        l, t, r, b = p.rect
        c.rect(l, t, tab_w, tab_h, owner=p.key)
        c.rect(l, t + tab_h, r - l, b - t - tab_h, owner=p.key)
        draw_head(c, list(head), l + tab_w / 2, t, p.key)


class _IconBox(_HeadShape):
    """머리 칸 오른쪽 위에 아이콘을 단 상자(컴포넌트·아티팩트). 이름은 상자 세로 가운데에 쓴다."""

    ICON = (12, 15)  # 아이콘 폭·높이

    def size(self, e: Element) -> tuple[float, float]:
        _, w, h = self.head(e)
        return max(MIN_WIDTH, w + 2 * ICON_ROOM), h + BOX_BODY

    def icon(self, c: Canvas, x: float, y: float, owner: str) -> None:
        raise NotImplementedError

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        l, t, r, b = p.rect
        c.rect(l, t, r - l, b - t, owner=p.key)
        self.icon(c, r - ICON_MARGIN - self.ICON[0], t + ICON_MARGIN, p.key)
        lines, _, h = self.head(p.box)
        draw_head(c, list(lines), (l + r) / 2, (t + b - h) / 2, p.key)


class ComponentShape(_IconBox):
    """컴포넌트: 부품 아이콘(작은 상자 왼쪽 변에 작은 네모 둘)을 단 상자. stereotype에 component를 주면 «component»도 쓴다."""

    def icon(self, c: Canvas, x: float, y: float, owner: str) -> None:
        w, h = self.ICON
        c.rect(x, y, w, h, owner=owner)
        for dy in (3, 9):
            c.rect(x - 3, y + dy, 6, 3, owner=owner)


def _page_corners(l: float, t: float, w: float, h: float, fold: float) -> tuple[Point, ...]:
    """왼쪽 위가 (l, t)이고 오른쪽 위 귀가 fold만큼 접힌 문서의 꼭짓점(볼록 오각형)."""
    return (l, t), (l + w - fold, t), (l + w, t + fold), (l + w, t + h), (l, t + h)


def _draw_page(c: Canvas, l: float, t: float, w: float, h: float, fold: float, owner: str) -> None:
    """귀가 접힌 문서: 오각형과 접힌 귀 선. 아티팩트 상자의 아이콘과 문서 아이콘 표기 아티팩트가 함께 쓴다."""
    c.poly(_page_corners(l, t, w, h, fold), owner=owner)
    c.line([(l + w - fold, t), (l + w - fold, t + fold), (l + w, t + fold)], owner=owner)


class ArtifactShape(_IconBox):
    """아티팩트: 오른쪽 위 귀가 접힌 문서 아이콘을 단 상자. 이름은 흔히 파일 이름이다."""

    def icon(self, c: Canvas, x: float, y: float, owner: str) -> None:
        _draw_page(c, x, y, *self.ICON, 4, owner)


class ComponentIconShape(_HeadShape):
    """UML 1 표기 컴포넌트: 상자 왼쪽 변에 부품 네모 둘이 반쯤 걸쳐 튀어나온다. 자리는 튀어나온 네모까지 덮고, 선이 닿는 테두리는
    네모를 뺀 상자(_body)다. 부품 네모는 몸통 밖에 붙은 자리라 그 컴포넌트가 끝인 선도 지나가면 안 된다 — 이름 칸 길(NameZone)로
    넘기되 검사 글은 "부품 네모"라고 부른다. 네모는 상자 세로 가운데에서 위아래로 PART_OFF 떨어져 있어, 왼쪽에서 가로로 곧게 들어오는
    선은 두 네모 사이로 닿는다. 이름과 스테레오타입은 상자 가운데에 쓴다."""

    aims_aside = True  # 선은 자리(부품 네모까지 덮는다) 가운데가 아니라 상자 가운데를 향한다 — 결과 글이 그 점을 덧붙인다

    def size(self, e: Element) -> tuple[float, float]:
        _, w, h = self.head(e)
        return max(MIN_WIDTH, w + PART[0]) + PART[0] / 2, h + BOX_BODY

    def _body(self, rect: Box) -> Box:
        return rect[0] + PART[0] / 2, rect[1], rect[2], rect[3]

    def _parts(self, rect: Box) -> tuple[Box, Box]:
        """부품 네모 둘 — 선이 향하는 점(상자 가운데를 정수로 내린 점)의 높이에서 위아래로 같게 떨어뜨린다."""
        l, cy = rect[0], floored(self._body(rect))[1]
        w, h = PART
        return (l, cy - PART_OFF - h, l + w, cy - PART_OFF), (l, cy + PART_OFF, l + w, cy + PART_OFF + h)

    def border(self, e: Element, rect: Box) -> Border:
        return RectBorder(self._body(rect))

    def anchor(self, e: Element, rect: Box) -> Point:
        """선이 향하는 점: 상자 가운데를 정수로 내린 점(boxdiagram.floored) — 상자 폭은 글자에 맞춰 홀수가 되기 쉽다."""
        return floored(self._body(rect))

    def name_zones(self, e: Element, rect: Box) -> tuple[NameZone, ...]:
        return tuple(NameZone(part, True, "부품 네모", lettered=False) for part in self._parts(rect))

    def parts(self, e: Element, rect: Box) -> tuple[Border, ...]:
        """상자와 부품 네모 둘 — 네모 위아래의 빈 곳은 컴포넌트가 아니다."""
        return (RectBorder(self._body(rect)), *(RectBorder(part) for part in self._parts(rect)))

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        l, t, r, b = self._body(p.rect)
        c.rect(l, t, r - l, b - t, owner=p.key)
        for pl, pt, pr, pb in self._parts(p.rect):
            c.rect(pl, pt, pr - pl, pb - pt, owner=p.key)
        lines, _, h = self.head(p.box)
        draw_head(c, list(lines), (l + r) / 2, (t + b - h) / 2, p.key)


class ArtifactIconShape(Shape):
    """문서 아이콘 표기 아티팩트: 귀가 접힌 문서 아이콘을 정해진 크기(PAGE)로 그리고, 이름(흔히 파일 이름)은 모양 밖(name_side, 기본
    아래)에 쓴다. 문서는 모양 자리(결과의 "모양")를 그대로 채우고, 선 끝은 문서 테두리(볼록 오각형)에 닿는다. 선은 문서 사각형
    가운데를 정수로 내린 점을 향한다. 볼록 다각형의 기본 중심(넓이 중심)은 귀 반대쪽으로 쏠리고, 모양 밖 이름은 모양 자리를 반 픽셀에
    놓기도 해서다 — 그대로면 가운데를 맞춘 컴포넌트와 잇는 세로 선이 계단처럼 보인다."""

    outside_name = True
    sized = False
    stereotyped = False

    def size(self, e: Element) -> tuple[float, float]:
        return PAGE

    def anchor(self, e: Element, rect: Box) -> Point:
        return floored(rect)

    def border(self, e: Element, rect: Box) -> Border:
        return PolygonBorder(_page_corners(rect[0], rect[1], *PAGE, FOLD))

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        _draw_page(c, p.shape_rect[0], p.shape_rect[1], *PAGE, FOLD, p.key)


class NodeShape(_HeadShape):
    """노드: 오른쪽과 위에 두께(DEPTH)가 보이는 입체 상자. 선 끝은 겉 테두리(육각형)에 닿는다. 이름은 앞면 위쪽 가운데에 쓰고(이름
    칸 좌우로 NEST_PAD 이상 앞면이 남는다 — 안의 요소를 잇는 선이 이름 옆으로 앞면 윗변을 건널 자리), 안에 요소를 두는 칸은 이름 줄
    아래 앞면이다. 두께 띠와 앞면 윗변·오른변은 테두리 선이다."""

    holds = True

    def size(self, e: Element) -> tuple[float, float]:
        _, w, h = self.head(e)
        return max(MIN_WIDTH, w + 2 * NEST_PAD) + DEPTH, h + NODE_BODY + DEPTH

    def insets(self, e: Element) -> Box:
        return 0.0, DEPTH + self.head(e)[2], DEPTH, 0.0

    def _corners(self, rect: Box) -> tuple[tuple[float, float], ...]:
        l, t, r, b = rect
        return (l, t + DEPTH), (l + DEPTH, t), (r, t), (r, b - DEPTH), (r - DEPTH, b), (l, b)

    def border(self, e: Element, rect: Box) -> Border:
        return PolygonBorder(self._corners(rect))

    def parts(self, e: Element, rect: Box) -> tuple[Border, ...]:
        """겉 테두리(육각형) — 왼쪽 위와 오른쪽 아래의 깎인 모서리는 노드가 아니다."""
        return (self.border(e, rect),)

    def name_zones(self, e: Element, rect: Box) -> tuple[NameZone, ...]:
        _, w, h = self.head(e)
        cx, top = (rect[0] + rect[2] - DEPTH) / 2, rect[1] + DEPTH
        return (NameZone((cx - w / 2, top, cx + w / 2, top + h), False),)

    def frame(self, e: Element, rect: Box) -> tuple[Segment, ...]:
        l, t, r, b = rect
        front = (r - DEPTH, t + DEPTH)
        return self.border(e, rect).edges() + (((l, t + DEPTH), front), (front, (r - DEPTH, b)), (front, (r, t)))

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        l, t, r, b = p.rect
        c.poly(self._corners(p.rect), owner=p.key)
        front = (r - DEPTH, t + DEPTH)
        c.line([(l, t + DEPTH), front, (r - DEPTH, b)], owner=p.key)
        c.line([front, (r, t)], owner=p.key)
        draw_head(c, list(self.head(p.box)[0]), (l + r - DEPTH) / 2, t + DEPTH, p.key)


PACKAGE = PackageShape()
COMPONENT = ComponentShape()
ARTIFACT = ArtifactShape()
COMPONENT_ICON = ComponentIconShape()
ARTIFACT_ICON = ArtifactIconShape()
NODE = NodeShape()

# 패키지도·컴포넌트도·배치도(deployment diagram)가 함께 받는 요소 종류
SHAPES = {**CLASS_SHAPES, "package": PACKAGE, "component": COMPONENT, "artifact": ARTIFACT, "component_icon": COMPONENT_ICON,
          "artifact_icon": ARTIFACT_ICON, "node": NODE}
