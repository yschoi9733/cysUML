"""여러 그림이 함께 쓰는 요소 모양: 패키지·컴포넌트·아티팩트·노드, 그리고 그 넷과 클래스를 한 그림에 섞어 받는 종류 목록(SHAPES).

패키지도·컴포넌트도·배치도(deployment diagram)가 같은 모양을 두 번 만들지 않게 여기 둔다. 네 모양 모두 클래스처럼 스테레오타입을 받아 이름 위
줄에 쓰고, 머리 칸 글자는 클래스 머리 칸과 같은 자리 규칙(classdiagram.draw_head)을 쓴다.
"""
from __future__ import annotations

from .boxdiagram import Element, NameZone, PlacedBox, Shape
from .canvas import Canvas
from .classdiagram import CLASS_SHAPES, MIN_WIDTH, draw_head, head_height, head_lines, head_width
from .geom import Border, PolygonBorder, RectBorder, Segment
from .text import Box

TAB_MIN = 50       # 패키지 탭의 최소 폭
# 패키지 몸통은 탭 폭의 두 배보다 적어도 이만큼 넓다 — 선이 향하는 몸통 가운데가 탭 오른쪽 끝에서 TAB_STEP/2 오른쪽에 와서
# (검사 여유 4px보다 넓다) 위에 같은 폭으로 쌓은 패키지에서 곧게 내려오는 선이 탭을 지나지 않는다
TAB_STEP = 20
PACKAGE_BODY = 40  # 비어 있는 패키지 몸통의 높이
BOX_BODY = 24      # 컴포넌트·아티팩트에서 머리 칸 밖에 더하는 높이(이름 한 줄이면 클래스 기본 높이 48)
ICON_ROOM = 16     # 컴포넌트·아티팩트 아이콘이 이름과 겹치지 않게 머리 칸 좌우에 더하는 폭
ICON_MARGIN = 6    # 아이콘과 상자 오른쪽·위 변 사이
DEPTH = 8          # 노드 두께 띠의 폭. BOX_CLEARANCE의 두 배 안이라 띠 안을 따라가는 선은 늘 띠 한쪽 변에 붙어 걸린다
NODE_BODY = 24     # 노드 앞면에서 이름 줄 밖에 더하는 높이


class PackageShape(Shape):
    """패키지: 이름(과 스테레오타입)을 쓴 탭이 몸통 왼쪽 위에 붙은 폴더. 안에 요소를 두는 칸은 몸통이고, 선은 몸통 테두리에 닿는다.
    탭은 몸통 밖에 붙은 이름 칸이라 그 패키지가 끝인 선도 지나가면 안 된다. 탭 오른쪽 빈 곳은 패키지가 아니다."""

    holds = True

    def _tab(self, e: Element) -> tuple[list[tuple[str, bool]], float, float]:
        head = head_lines(self.keyword(e), e.name)
        return head, max(TAB_MIN, head_width(head)), head_height(head)

    def size(self, e: Element) -> tuple[float, float]:
        _, tab_w, tab_h = self._tab(e)
        return max(MIN_WIDTH, 2 * tab_w + TAB_STEP), tab_h + PACKAGE_BODY

    def parts(self, e: Element, rect: Box) -> tuple[Box, ...]:
        """탭과 몸통 — 탭 오른쪽 빈 곳은 패키지가 아니다."""
        _, tab_w, tab_h = self._tab(e)
        return (rect[0], rect[1], rect[0] + tab_w, rect[1] + tab_h), (rect[0], rect[1] + tab_h, rect[2], rect[3])

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
        draw_head(c, head, l + tab_w / 2, t, p.key)


class _IconBox(Shape):
    """머리 칸 오른쪽 위에 아이콘을 단 상자(컴포넌트·아티팩트). 이름은 상자 세로 가운데에 쓴다."""

    ICON = (12, 15)  # 아이콘 폭·높이

    def head(self, e: Element) -> list[tuple[str, bool]]:
        return head_lines(self.keyword(e), e.name)

    def size(self, e: Element) -> tuple[float, float]:
        head = self.head(e)
        return max(MIN_WIDTH, head_width(head) + 2 * ICON_ROOM), head_height(head) + BOX_BODY

    def icon(self, c: Canvas, x: float, y: float, owner: str) -> None:
        raise NotImplementedError

    def draw(self, c: Canvas, p: PlacedBox) -> None:
        l, t, r, b = p.rect
        c.rect(l, t, r - l, b - t, owner=p.key)
        self.icon(c, r - ICON_MARGIN - self.ICON[0], t + ICON_MARGIN, p.key)
        head = self.head(p.box)
        draw_head(c, head, (l + r) / 2, (t + b - head_height(head)) / 2, p.key)


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


class NodeShape(Shape):
    """노드: 오른쪽과 위에 두께(DEPTH)가 보이는 입체 상자. 선 끝은 겉 테두리(육각형)에 닿는다. 이름은 앞면 위쪽 가운데에 쓰고, 안에
    요소를 두는 칸은 이름 줄 아래 앞면이다. 두께 띠와 앞면 윗변·오른변은 테두리 선이다."""

    holds = True

    def head(self, e: Element) -> list[tuple[str, bool]]:
        return head_lines(self.keyword(e), e.name)

    def size(self, e: Element) -> tuple[float, float]:
        head = self.head(e)
        return max(MIN_WIDTH, head_width(head)) + DEPTH, head_height(head) + NODE_BODY + DEPTH

    def insets(self, e: Element) -> Box:
        return 0.0, DEPTH + head_height(self.head(e)), DEPTH, 0.0

    def _corners(self, rect: Box) -> tuple[tuple[float, float], ...]:
        l, t, r, b = rect
        return (l, t + DEPTH), (l + DEPTH, t), (r, t), (r, b - DEPTH), (r - DEPTH, b), (l, b)

    def border(self, e: Element, rect: Box) -> Border:
        return PolygonBorder(self._corners(rect))

    def name_zones(self, e: Element, rect: Box) -> tuple[NameZone, ...]:
        head = self.head(e)
        cx, top, w = (rect[0] + rect[2] - DEPTH) / 2, rect[1] + DEPTH, head_width(head)
        return (NameZone((cx - w / 2, top, cx + w / 2, top + head_height(head)), False),)

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
        draw_head(c, self.head(p.box), (l + r - DEPTH) / 2, t + DEPTH, p.key)


PACKAGE = PackageShape()
COMPONENT = ComponentShape()
ARTIFACT = ArtifactShape()
NODE = NodeShape()

# 패키지도·컴포넌트도·배치도(deployment diagram)가 함께 받는 요소 종류
SHAPES = {**CLASS_SHAPES, "package": PACKAGE, "component": COMPONENT, "artifact": ARTIFACT, "node": NODE}
