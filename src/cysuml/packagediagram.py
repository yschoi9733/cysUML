"""패키지도: 패키지와 패키지 사이 의존을 그린다. 패키지 안에 클래스·패키지를 넣고, 컴포넌트·아티팩트·노드도 함께 그린다.

요소 종류는 shapes.SHAPES, 관계는 클래스도 관계 여섯 가지(classdiagram.RELATIONS)이고, 읽기·자리 잡기·그리기는 공용 엔진
(boxdiagram), 검사는 공용 검사(boxcheck)가 한다. 도구 설명(TOOL)과 배치 요령(TIPS)도 여기 둔다.
"""
from __future__ import annotations

from typing import Any

from . import boxdiagram as B
from .boxcheck import KINDS
from .boxdiagram import ELEMENT_WORDS, Diagram, Drawing, Spec
from .canvas import SCALE
from .classdiagram import RELATIONS
from .guide import (COMMON_INPUT, IMAGE_RESULT, NESTING, NEW_INPUT, OUTSIDE_PLACES, PLACED_ELEMENTS, PLACES_RESULT, flow,
                    relation_fields)
from .shapes import SHAPES

SPEC = Spec(SHAPES, RELATIONS, ELEMENT_WORDS, list_field="elements", navigable="to")


def parse(data: Any) -> Diagram:
    return B.parse(SPEC, data)


def render(data: Any, scale: float = SCALE) -> Drawing:
    return B.render(SPEC, data, scale)


TIPS = """패키지도 배치 요령:
- 의존이 위에서 아래로 흐르게 패키지를 층으로 놓는다(쓰는 쪽을 위에, 쓰이는 쪽을 아래에).
- 패키지 안 클래스는 클래스도 요령을 따른다 — 연결이 많은 클래스를 가운데에, 상속은 부모를 위에 자식을 그 아래 한 줄에 둔다.
- 위에서 들어오는 의존선은 탭 오른쪽 몸통 윗변에 닿게 한다. 패키지로 오가는 선은 탭 오른쪽 몸통의 가운데를 향하는데, 그 점은 \
패키지 폭과 이름 길이(탭 폭)에 따라 달라서 위아래로 쌓은 패키지라도 폭이나 이름 길이가 다르면 선이 비스듬히 들어와 아래 패키지 \
탭을 지나기 쉽다. 그러면 아래 패키지 탭 오른쪽 끝에서 20px쯤 오른쪽, 아래 패키지 top에서 30px쯤 위에 꺾는 점(via)을 하나 준다 \
(탭 자리는 불합격 항목의 "이름 칸"에 나온다).
- 요소 사이는 관계 이름·스테레오타입 글자가 들어갈 만큼 띄운다. 가로 80px·세로 60px쯤에서 시작하고, 글자가 길면 더 띄운다.
- 요소 크기는 도구가 글자와 안의 요소에 맞춰 늘린다. 그린 크기는 결과의 "요소 자리"에서 보고 다음 배치에 쓴다."""

TOOL = f"""패키지도를 그려 PNG 파일로 저장하고, 검사 결과와 그림을 함께 돌려준다. 패키지와 패키지 사이 의존을 그리고, 패키지 안에 \
클래스·패키지를 넣는다. 클래스·패키지·컴포넌트·아티팩트·노드를 한 그림에 섞어 그릴 수 있다. 요소는 준 왼쪽 위(left·top) 그대로, \
관계선은 준 꺾는 점(via)을 따라 그리고, 요소 크기·선 끝·선 글자 자리만 도구가 정한다. 좌표는 px이고 y는 아래로 커진다.

입력
{PLACED_ELEMENTS}
{relation_fields(SPEC)}
{COMMON_INPUT}

{NEW_INPUT}

{NESTING}

결과
{PLACES_RESULT}
{OUTSIDE_PLACES}
{IMAGE_RESULT}
- elements·relations·file_name이 틀리면 그리지 않고 틀린 곳을 elements[0].left 꼴 자리와 함께 모두 모아 오류로 돌려준다. \
그림이 너무 커서 PNG로 그릴 수 없거나 저장할 폴더에 쓸 수 없을 때도 오류로 돌려준다.

{flow(KINDS, SPEC.words)}

{TIPS}"""
