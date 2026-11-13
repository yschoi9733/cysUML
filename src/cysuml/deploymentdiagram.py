"""배치도(deployment diagram): 소프트웨어(컴포넌트·아티팩트)가 어느 컴퓨터(노드)에 놓여 도는지 그린다. 노드 안에 컴포넌트·아티팩트·
노드를 넣고, 노드끼리는 통신 경로(연관)로, 노드 밖 요소에서 노드로는 «deploy»(스테레오타입을 단 의존)로 잇는다.

요소 종류·관계 종류·읽기·자리 잡기·그리기·검사는 패키지도와 같은 공용 엔진(boxdiagram)·공용 검사(boxcheck)를 쓰고, 연관의 기본
방향만 '없음'으로 둔다(통신 경로는 화살촉 없는 실선). 도구 설명(TOOL)과 자리 잡기 요령(TIPS)도 여기 둔다.
"""
from __future__ import annotations

from typing import Any

from . import boxdiagram as B
from .boxcheck import KINDS
from .boxdiagram import ELEMENT_WORDS, LABEL_LINE, NEST_PAD, Diagram, Drawing, Spec
from .canvas import SCALE
from .classdiagram import HEAD, NAME_LINE, RELATIONS
from .guide import COMMON_INPUT, IMAGE_RESULT, NESTING, NEW_INPUT, PLACED_ELEMENTS, flow, places_result, relation_fields
from .shapes import DEPTH, SHAPES

SPEC = Spec(SHAPES, RELATIONS, ELEMENT_WORDS, list_field="elements", navigable="none")


def parse(data: Any) -> Diagram:
    return B.parse(SPEC, data)


def render(data: Any, scale: float = SCALE) -> Drawing:
    return B.render(SPEC, data, scale)


NOTATION = """배치도(deployment diagram) 표기:
- 노드 안에 두기: 노드에서 도는 컴포넌트·아티팩트, 노드 안의 노드(서버 안의 실행 환경 등)는 in으로 그 노드 안에 둔다.
- 통신 경로: 노드끼리 kind "association"으로 잇는다. 이 도구의 연관은 navigable 기본이 "none"이라 화살촉 없는 실선이다(클래스끼리 \
이은 연관·집합·합성도 같으니, 화살촉이 필요하면 navigable을 준다). 선 위에 프로토콜 같은 이름(name — "HTTPS"·"JDBC" 등)이나 \
stereotype을 쓴다.
- «deploy»: 노드 밖에 둔 컴포넌트·아티팩트에서 노드로 kind "dependency", stereotype "deploy"를 긋는다(점선 화살표). 한 그림에서 \
어떤 요소는 노드 안에 두고 어떤 요소는 «deploy»로 이어도 된다. 다만 노드 안에 둔 요소에서 그 노드(나 그 노드를 품은 노드)로는 \
긋지 않는다 — 품은 요소와 그 안의 요소를 잇는 선은 입력 오류다.
- «manifest»: 아티팩트에서 그 아티팩트가 담은 컴포넌트로 kind "dependency", stereotype "manifest"를 긋는다. UML 2의 정석은 \
아티팩트를 노드에 두고(안에 두거나 «deploy»로) 컴포넌트는 그 아티팩트에서 «manifest»로 잇는 것이고, 컴포넌트를 노드 안에 바로 두는 \
간단한 표기도 흔히 쓴다. 한 문서 안에서는 한 가지로 맞춘다.
- 노드 종류: 노드의 stereotype에 "device"·"executionEnvironment" 등을 주면 이름 위 줄에 쓴다. 모양은 같은 입체 상자다."""

INNER_TOP = DEPTH + HEAD + NEST_PAD  # 이름 한 줄 노드에서 안의 요소를 둘 수 있는 가장 위(노드 top에서)

TIPS = f"""배치도(deployment diagram) 자리 잡기 요령:
- 사용자 쪽 노드(PC·휴대폰 등)를 한쪽 끝에, 서버·데이터베이스 노드를 다른 쪽으로 차례로 놓아 통신 경로가 엇갈리지 않게 한다.
- 통신 경로는 두 노드의 가운데를 잇는다. 가로 한 줄에 놓은 노드는 top과 height를, 세로 한 단에 쌓은 노드는 left와 width를 같게 \
주면 경로가 곧다. 노드는 안의 요소에 맞춰 늘어나니, 결과의 "요소 자리"에서 그 줄(단)의 가장 높은(넓은) 노드 크기를 다른 노드의 \
height(width)로 준다. 안의 요소를 바꿔 노드가 다시 늘면 다시 맞춘다.
- 노드 안의 요소는 이름 한 줄 노드면 노드 top + {INNER_TOP:g}부터 두고, 스테레오타입(«device» 등)이나 이름 줄이 하나 늘 때마다 \
{NAME_LINE:g}px씩 더 아래부터 둔다(«device» 노드면 top + {INNER_TOP + NAME_LINE:g}, 이름이 두 줄인 «device» 노드면 \
top + {INNER_TOP + 2 * NAME_LINE:g}).
- 노드 밖에서 노드 안의 요소(노드 안의 노드 포함 — 아래에서 "끝 요소")로 가는 선이 끝 요소를 품은 노드들의 이름(앞면 위 가운데)을 \
지나면 불합격이다. 선을 보내는 요소는 가장 바깥 노드의 옆에 끝 요소와 같은 높이로(보내는 요소의 top을 끝 요소의 윗변과 아랫변 \
사이에) 두거나, 아래에 끝 요소와 같은 가로 자리로(보내는 요소의 left를 끝 요소의 왼변과 오른변 사이에) 둔다. 왼쪽·오른쪽·아래 \
가운데 노드 테두리에서 끝 요소까지 가는 길에 다른 요소가 없는 쪽을 고른다. 그 선의 글자\
(«deploy»·프로토콜 이름)는 선 가운데쯤에 놓여 노드 테두리에 걸리기 쉬우니, 요소 사이 기본 간격("요소 사이는" 항목)보다 더 띄운다 \
— 옆이면 가장 바깥 노드와의 간격을 그 노드 테두리에서 끝 요소까지의 거리 + 선 글자 폭(가장 긴 줄) + 20px 이상, 아래면 그 노드 \
아랫변에서 끝 요소 아랫변까지의 거리 + 40px 이상으로 한다. 선 글자 폭은 영문·숫자·ASCII 기호 한 글자 11px(W·@·%는 14px), 한글 \
12px, 그 밖의 글자 14px로 어림하고, 불합격 항목에 글자 자리(폭×높이)가 나오면 그 폭으로 고친다. 선 글자가 여러 줄(스테레오타입과 \
이름 등)이면 보내는 요소가 아래나 위일 때 간격에 한 줄마다 {LABEL_LINE:g}px를 더한다.
- 끝 요소가 가장 바깥 노드 바로 안의 노드이면 선을 보내는 요소를 위에 둘 수도 있다. 이름 칸 바로 위는 피하고, 바깥 노드 윗변에서 \
80px 이상 떼어(선 글자가 여러 줄이면 한 줄마다 {LABEL_LINE:g}px 더), 이름 칸에서 보내는 요소 쪽으로 40px쯤 바깥, 이름 칸 아랫변에서 10px \
아래에 꺾는 점(via)을 하나 준다(이름 칸 옆 앞면이 40px보다 좁아 꺾는 점이 앞면 밖(두께 띠나 노드 밖)에 놓여도 된다. 이름 칸 \
자리는 불합격 항목의 "이름 칸"에 나온다). 보내는 요소가 바깥 노드 오른쪽 위 모서리 근처라 꺾는 점까지 가는 선이 그 모서리의 \
비스듬한 두께 띠 선을 따라가 불합격하면, 보내는 요소를 옆으로 20px쯤 옮긴다. 끝 요소가 더 깊으면 위에 두지 않는다 — 이 꺾는 점으로는 안쪽 노드의 이름을 비키지 못한다.
- 요소 사이는 관계 이름·스테레오타입 글자가 들어갈 만큼 띄운다. 가로 80px·세로 60px쯤에서 시작하고, 글자가 길면 더 띄운다.
- 요소 크기는 도구가 글자와 안의 요소에 맞춰 늘린다. 그린 크기는 결과의 "요소 자리"에서 보고 다음 입력에 쓴다."""

TOOL = f"""배치도(deployment diagram)를 그려 PNG 파일로 저장하고, 검사 결과와 그림을 함께 돌려준다. 소프트웨어(컴포넌트·아티팩트)가 \
어느 컴퓨터(노드)에 놓여 도는지 보인다. 노드 안에 컴포넌트·아티팩트·노드를 넣고, 노드끼리 통신 경로를, 노드 밖 요소에서 노드로 \
«deploy»를 긋는다. 컴포넌트·아티팩트는 아이콘 표기로도 그리고, 클래스·패키지 요소도 한 그림에 섞어 그릴 수 있다. 요소는 준 왼쪽 위(left·top) 그대로, 관계선은 준 꺾는 점(via)을 \
따라 그리고, 요소 크기·선 끝·선 글자 자리만 도구가 정한다. 좌표는 px이고 y는 아래로 커진다.

입력
{PLACED_ELEMENTS}
{relation_fields(SPEC)}
{COMMON_INPUT}

{NEW_INPUT}

{NESTING}

{NOTATION}

결과
{places_result(SPEC)}
{IMAGE_RESULT}
- elements·relations·file_name이 틀리면 그리지 않고 틀린 곳을 elements[0].left 꼴 자리와 함께 모두 모아 오류로 돌려준다. \
그림이 너무 커서 PNG로 그릴 수 없거나 저장할 폴더에 쓸 수 없을 때도 오류로 돌려준다.

{flow(KINDS, SPEC.words)}

{TIPS}"""
