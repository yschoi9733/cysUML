"""여러 그림이 함께 쓰는 요소 모양: 패키지·컴포넌트·아티팩트·노드, 그리고 그 넷과 클래스를 한 그림에 섞어 받는 종류 목록(SHAPES).

패키지도·컴포넌트도·배치도(deployment diagram)가 같은 모양을 두 번 만들지 않게 여기 둔다. 네 모양 모두 클래스처럼 스테레오타입을 받아 이름 위
줄에 쓰고, 머리 칸 글자는 클래스 머리 칸과 같은 자리 규칙(classdiagram.draw_head)을 쓴다.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from .boxdiagram import NEST_PAD, Element, NameZone, PlacedBox, Shape
from .canvas import Canvas
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

    def _tab(self, e: Element) -> Head:
        """(탭 머리 칸 줄, 탭 폭, 탭 높이)."""
        lines, w, h = self.head(e)
        return lines, max(TAB_MIN, w), h

    def size(self, e: Element) -> tuple[float, float]:
        _, tab_w, tab_h = self._tab(e)
        return max(MIN_WIDTH, tab_w + TAB_STEP), tab_h + PACKAGE_BODY

    def parts(self, e: Element, rect: Box) -> tuple[Box, ...]:
        """탭과 몸통 — 탭 오른쪽 빈 곳은 패키지가 아니다."""
        _, tab_w, tab_h = self._tab(e)
        return (rect[0], rect[1], rect[0] + tab_w, rect[1] + tab_h), (rect[0], rect[1] + tab_h, rect[2], rect[3])

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


class ArtifactShape(_IconBox):
    """아티팩트: 오른쪽 위 귀가 접힌 문서 아이콘을 단 상자. 이름은 흔히 파일 이름이다."""

    def icon(self, c: Canvas, x: float, y: float, owner: str) -> None:
        w, h = self.ICON
        fold = 4
        c.poly([(x, y), (x + w - fold, y), (x + w, y + fold), (x + w, y + h), (x, y + h)], owner=owner)
        c.line([(x + w - fold, y), (x + w - fold, y + fold), (x + w, y + fold)], owner=owner)


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

    def parts(self, e: Element, rect: Box) -> tuple[Box, ...]:
        """앞면과 위·오른쪽 두께 띠 — 왼쪽 위와 오른쪽 아래의 깎인 모서리는 노드가 아니다."""
        l, t, r, b = rect
        return (l, t + DEPTH, r - DEPTH, b), (l + DEPTH, t, r, t + DEPTH), (r - DEPTH, t + DEPTH, r, b - DEPTH)

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
NODE = NodeShape()

# 패키지도·컴포넌트도·배치도(deployment diagram)가 함께 받는 요소 종류
SHAPES = {**CLASS_SHAPES, "package": PACKAGE, "component": COMPONENT, "artifact": ARTIFACT, "node": NODE}
