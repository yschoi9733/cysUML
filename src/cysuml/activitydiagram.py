"""액티비티도: 시작·끝 점, 행동, 결정·합류 마름모를 흐름으로 잇는다.

모양은 상태도와 함께 쓰는 flowshapes에 있고, 읽기·자리 잡기·그리기는 공용 엔진(boxdiagram), 검사는 공용 검사(boxcheck)가 한다.
안에 요소를 두는 모양이 없어 중첩에서만 나는 불합격 종류는 나지 않는다. 도구 설명(TOOL)과 배치 요령(TIPS)도 여기 둔다.
"""
from __future__ import annotations

from typing import Any

from . import boxdiagram as B
from .boxcheck import KINDS as ALL_KINDS
from .boxcheck import NESTED_KINDS
from .boxdiagram import ARROW_HEAD, ELEMENT_WORDS, Diagram, Drawing, RelationType, Spec
from .canvas import SCALE
from .flowshapes import ACTION, DIAMOND, DIAMOND_SIZE, FINAL, FINAL_POINT, START, START_POINT, ends_errors, parse_flow
from .guide import box_tool, spacing_tips

FLOW = RelationType("흐름", end=ARROW_HEAD)
SHAPES = {"initial": START_POINT, "final": FINAL_POINT, "action": ACTION, "decision": DIAMOND, "merge": DIAMOND}
SPEC = Spec(SHAPES, {"flow": FLOW}, ELEMENT_WORDS, list_field="elements")
KINDS = tuple(k for k in ALL_KINDS if k not in NESTED_KINDS)  # 이 도구에서 날 수 있는 불합격 종류


def parse(data: Any) -> Diagram:
    return parse_flow(SPEC, data)


def render(data: Any, scale: float = SCALE) -> Drawing:
    return B.draw(parse(data), scale)


TIPS = f"""액티비티도 배치 요령:
- 시작 점을 위에 두고, 흐름이 위에서 아래로 흐르게 행동을 한 줄로 놓는다.
- 결정 마름모에서 갈라지는 갈래는 행동을 옆으로 벌려 놓고, 합류 마름모를 갈래 아래 가운데에 두어 다시 모은다. 갈래로 가는 흐름은 \
마름모 왼쪽·오른쪽 꼭짓점에서 나가 갈래 행동 위에서 꺾어 내려가게, 갈래에서 합류로 오는 흐름은 갈래 행동 아래에서 꺾어 합류 \
마름모의 왼쪽·오른쪽 꼭짓점으로 들어오게 꺾는 점(via)을 하나씩 준다(가로·세로 선은 마름모 꼭짓점에 닿는다).
- 결정에서 나가는 흐름에는 name에 "[조건]"을 쓴다.
- 되돌아가는 흐름(반복)은 꺾는 점(via)으로 행동들 바깥을 돌게 한다 — 곧게 그으면 가는 흐름과 포개지거나 다른 행동을 지난다.
{spacing_tips(SPEC, "흐름")}"""

INTRO = """액티비티도를 그려 PNG 파일로 저장하고, 검사 결과와 그림을 함께 돌려준다. 시작·끝 점, 행동, 결정·합류 마름모를 흐름으로 \
잇는다. 요소는 준 왼쪽 위(left·top) 그대로, 흐름은 준 꺾는 점(via)을 따라 그리고, 요소 크기·선 끝·흐름 글자 자리만 도구가 정한다. \
좌표는 px이고 y는 아래로 커진다."""

INPUTS = f"""- elements: 요소 목록(하나 이상).
  - kind(필수): "initial"(시작 점 — 검게 칠한 원), "final"(끝 점 — 과녁 모양), "action"(행동 — 둥근 모서리 상자), \
"decision"(결정 — 마름모), "merge"(합류 — 마름모).
  - name·id: "공용 입력(열쇠·이름)" 절. 행동은 name(필수)을 쓴다. 시작·끝 점과 마름모는 이름이 없어 name 대신 id(필수)를 준다.
  - left·top(필수): 자리의 왼쪽 위.
  - width·height: 행동 자리의 최소 크기. 글자가 더 길면 그만큼 늘어난다. 시작 점(지름 {START}px)·끝 점(지름 {FINAL}px)·마름모\
({DIAMOND_SIZE}×{DIAMOND_SIZE}px)는 크기가 정해져 있다.
- relations: 흐름 목록(없어도 된다).
  - kind: "flow". 관계 종류가 하나뿐이라 빼도 된다.
  - from·to(필수): 요소 열쇠. 화살촉은 늘 to 쪽에 붙는다. 시작 점은 from에만, 끝 점은 to에만 쓴다.
  - name: 흐름 글자. 받은 그대로 쓴다 — 결정에서 나가는 흐름의 조건은 "[재고 있음]"처럼 대괄호까지 쓴다(도구가 씌우지 않는다). \
길면 줄마다 문자열인 목록으로 나눈다. stereotype: "공용 입력(열쇠·이름)" 절.
  - via: 꺾는 점 [[x, y], …]. 선은 요소 가운데에서 첫 꺾는 점(없으면 상대 요소 가운데)으로 가는 선이 요소 테두리와 만나는 곳에서 \
시작한다. 같은 요소로 돌아오는 흐름은 꺾는 점이 둘 이상 있어야 한다."""

TOOL = box_tool(INTRO, SPEC, INPUTS, TIPS, kinds=KINDS, errors=ends_errors(SPEC))
