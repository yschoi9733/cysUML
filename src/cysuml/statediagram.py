"""상태도: 시작·끝 점, 상태(안에 상태를 넣은 복합 상태 포함), 선택 마름모를 전이로 잇는다.

모양은 액티비티도와 함께 쓰는 flowshapes에 있고, 읽기·자리 잡기·그리기는 공용 엔진(boxdiagram), 검사는 공용 검사(boxcheck)가
한다. 도구 설명(TOOL)과 배치 요령(TIPS)도 여기 둔다.
"""
from __future__ import annotations

from typing import Any

from . import boxdiagram as B
from .boxcheck import KINDS
from .boxdiagram import ARROW_HEAD, ELEMENT_WORDS, LABEL_LINE, NEST_PAD, Diagram, Drawing, RelationType, Spec
from .canvas import SCALE
from .classdiagram import ROW, SECTION_PAD
from .flowshapes import DIAMOND, DIAMOND_SIZE, FINAL, FINAL_POINT, NAME_BAND, START, START_POINT, STATE
from .guide import COMMON_INPUT, IMAGE_RESULT, NESTING, NEW_INPUT, PLACES_RESULT, flow

TRANSITION = RelationType("전이", end=ARROW_HEAD)
SHAPES = {"initial": START_POINT, "final": FINAL_POINT, "state": STATE, "choice": DIAMOND}
SPEC = Spec(SHAPES, {"transition": TRANSITION}, ELEMENT_WORDS, list_field="elements")


def parse(data: Any) -> Diagram:
    return B.parse(SPEC, data)


def render(data: Any, scale: float = SCALE) -> Drawing:
    return B.render(SPEC, data, scale)


_ZONE = NAME_BAND + LABEL_LINE  # 이름 한 줄·동작 없는 상태의 이름 칸 높이

TIPS = f"""상태도 배치 요령:
- 시작 점을 위나 왼쪽에 두고, 전이가 한 방향(위에서 아래나 왼쪽에서 오른쪽)으로 흐르게 상태를 차례로 놓는다.
- 되돌아가는 전이는 꺾는 점(via)으로 상태들 바깥을 돌게 한다 — 곧게 그으면 가는 전이와 포개지거나 다른 상태를 지난다.
- 같은 상태로 돌아오는 전이(자기 전이)는 상태 오른쪽 변 25px 밖에 꺾는 점 둘(상태 윗변 높이와 아랫변 높이)을 준다 — 선이 오른쪽 \
변에서 비스듬히 나갔다 들어오는 고리가 된다. 윗변 가운데와 오른쪽 변 가운데로 드나드는 다른 전이가 없으면 꺾는 점 셋(상태 가운데 x로 \
윗변 30px 위, 그 높이로 오른쪽 변 25px 밖, 그 x로 상태 가운데 높이)으로 오른쪽 위 모서리를 도는 네모 고리로 그려도 된다.
- 선택 마름모로 가는 전이와 거기서 갈라지는 전이는 마름모 꼭짓점으로 곧게 들고 나게 둔다(가로·세로 선은 꼭짓점에 닿는다).
- 복합 상태 안의 요소는 이름 칸 아래에 둔다. 복합 상태 안의 상태와 밖의 상태를 잇는 전이는 이름 칸을 지나면 불합격이니, 복합 상태의 \
왼쪽·오른쪽·아래 테두리로 건너게 둔다.
- 요소 사이는 전이 글자가 들어갈 만큼 띄운다. 가로 80px·세로 60px쯤에서 시작하고, 글자가 길면 더 띄운다.
- 요소 크기는 도구가 글자와 안의 요소에 맞춰 늘린다. 그린 크기는 결과의 "요소 자리"에서 보고 다음 배치에 쓴다."""

TOOL = f"""상태도를 그려 PNG 파일로 저장하고, 검사 결과와 그림을 함께 돌려준다. 시작·끝 점, 상태, 선택 마름모를 전이로 잇고, 상태 안에 \
상태를 넣는다(복합 상태). 요소는 준 왼쪽 위(left·top) 그대로, 전이는 준 꺾는 점(via)을 따라 그리고, 요소 크기·선 끝·전이 글자 \
자리만 도구가 정한다. 좌표는 px이고 y는 아래로 커진다.

입력
- elements: 요소 목록(하나 이상).
  - kind(필수): "initial"(시작 점 — 검게 칠한 원), "final"(끝 점 — 과녁 모양), "state"(상태 — 둥근 모서리 상자), "choice"\
(선택 — 마름모).
  - name·id: "공용 입력(열쇠·이름)" 절. 상태는 name(필수)을 쓴다. 시작·끝 점과 선택은 이름이 없어 name 대신 id(필수)를 준다.
  - left·top(필수): 자리의 왼쪽 위.
  - actions: 상태의 동작 칸 줄 목록. 이름 아래 칸에 받은 그대로 쓴다 — "entry / 초기화"·"do / 감시"·"exit / 정리"처럼 앞말도 쓴다.
  - in: 이 요소를 품은 상태(복합 상태)의 열쇠. "요소 안에 요소 두기(중첩)" 절.
  - width·height: 상태 자리의 최소 크기. 글자와 안의 요소에 맞춰 더 늘어난다. 시작 점(지름 {START}px)·끝 점(지름 {FINAL}px)·선택 \
마름모({DIAMOND_SIZE}×{DIAMOND_SIZE}px)는 크기가 정해져 있다.
  - 상태의 이름 칸은 위쪽에 이름 줄과 동작 칸을 함께 덮는다. 높이는 이름 한 줄이면 {_ZONE}px이고, 이름 줄이 하나 늘 때마다 \
{LABEL_LINE}px, 동작 칸이 있으면 {SECTION_PAD}px에 동작 줄마다 {ROW}px를 더한다. 복합 상태 안의 요소는 이 칸 아래에 둔다(이름 한 \
줄·동작 없는 상태면 top + {_ZONE + NEST_PAD}부터).
- relations: 전이 목록(없어도 된다).
  - kind: "transition". 관계 종류가 하나뿐이라 빼도 된다.
  - from·to(필수): 요소 열쇠. 화살촉은 늘 to 쪽에 붙는다.
  - name: 전이 글자. "사건 [조건] / 동작" 꼴을 받은 그대로 쓴다 — 대괄호·빗금도 쓴다(도구가 씌우지 않는다). 길면 줄마다 문자열인 \
목록으로 나눈다. stereotype: "공용 입력(열쇠·이름)" 절.
  - via: 꺾는 점 [[x, y], …]. 선은 요소 가운데에서 첫 꺾는 점(없으면 상대 요소 가운데)으로 가는 선이 요소 테두리와 만나는 곳에서 \
시작한다. 같은 상태로 돌아오는 전이(자기 전이)는 꺾는 점이 둘 이상 있어야 한다.
{COMMON_INPUT}

{NEW_INPUT}

{NESTING}

결과
{PLACES_RESULT}
{IMAGE_RESULT}
- elements·relations·file_name이 틀리면 그리지 않고 틀린 곳을 elements[0].left 꼴 자리와 함께 모두 모아 오류로 돌려준다. \
그림이 너무 커서 PNG로 그릴 수 없거나 저장할 폴더에 쓸 수 없을 때도 오류로 돌려준다.

{flow(KINDS, SPEC.words)}

{TIPS}"""
