"""도구 설명과 서버 안내문이 함께 쓰는 조각. 그림 모듈은 제 도구 설명을 만들 때 이 조각을 가져다 쓴다(고치지 않는다).

- flow(가): AI가 배치하는 그림을 그리는 흐름과, 그 도구에서 날 수 있는 불합격 목록.
- NEW_INPUT(나): 새 그림 도구가 모두 받는 입력 규칙(열쇠·여러 줄 이름·관계 스테레오타입).
- PLACED_ELEMENTS(다): 패키지도·컴포넌트도·배치도(deployment diagram)가 함께 받는 요소 종류.
- relation_fields(라): 클래스도 관계 여섯 가지 가운데 받는 것과 연관의 기본 방향으로 만드는 관계 필드.
- NESTING(마): 요소 안에 요소 두기.
- NAME_SIDE(바): 모양 밖 이름의 쪽.
"""
from __future__ import annotations

from typing import Iterable, Optional

from .boxcheck import KINDS
from .boxdiagram import BOX_WORDS, NAVIGABLE, NEST_PAD, SIDES, Words, josa
from .canvas import MIN_SCALE, SCALE

MAX_IMAGE_EDGE = 1568  # 돌려주는 그림의 긴 변 상한(px). Claude는 이보다 큰 그림을 어차피 줄여서 본다
DEFAULT_DIR = "diagrams"

KIND_NAMES = {  # 불합격 종류(boxcheck.KINDS)를 도구 설명에 쓰는 말
    "box_overlap": "요소끼리 겹치거나 붙음",
    "inner_off_area": "안의 요소가 바깥 요소의 칸 밖으로 나가거나 테두리·이름 칸에 붙음",
    "line_through_box": "선이 그 선과 상관없는 요소를 지나감",
    "line_through_name": "선이 끝 요소나 끝을 품은 요소의 이름 칸을 지나감",
    "line_along_container": "선이 끝을 품은 요소의 테두리를 따라감",
    "line_along_own_box": "선이 제 끝 요소 테두리에 붙어 감",
    "head_near_own_box": "선 끝 모양이 그 선의 다른 끝 요소 테두리에 붙음",
    "head_under_own_box": "선 끝 모양이 제 끝 요소 안으로 들어감",
    "line_overlap": "선끼리 포개지거나 선이 왔던 길을 되짚음",
    "line_through_head": "선이 선 끝 모양(화살촉·삼각형·마름모)에 닿음",
    "head_overlap": "선 끝 모양끼리 겹침",
    "line_through_text": "선이 선 글자(관계 이름·다중도 등)를 지나감",
    "text_on_box": "선 글자가 요소에 겹침",
    "text_overlap": "선 글자끼리 겹침",
}
assert tuple(KIND_NAMES) == KINDS

PLACED_FLOW = """AI가 배치하는 그림(클래스도·패키지도 등)을 그리는 흐름 — 검사에 합격할 때까지 되풀이한다:
1. 요소(클래스도에서는 상자)의 자리(left·top)와, 필요하면 관계선의 꺾는 점(via)을 정해 그린다.
2. 돌려받은 검사 결과와 그림을 본다. 불합격 항목마다 걸린 요소, 자리(논리 좌표 왼, 위, 폭×높이), 고치는 법이 붙는다. \
고치는 법은 종류마다 다르니(요소를 옮긴다, 꺾는 점을 고친다, 두 요소를 떼어 놓는다 등) 항목에 적힌 대로 고친다.
3. 고친 입력을 같은 file_name으로 다시 그린다(파일을 덮어쓴다).
선끼리 엇갈린 곳과 그림 크기는 알림이라 불합격이 아니다. 다만 엇갈림은 적을수록 읽기 좋다."""


def flow(kinds: Optional[Iterable[str]] = None) -> str:
    """(가) AI가 배치하는 그림의 그리는 흐름. kinds(그 도구에서 날 수 있는 불합격 종류)를 주면 끝에 불합격 목록을 붙인다 —
    서버 안내문에는 목록 없이 넣는다."""
    if kinds is None:
        return PLACED_FLOW
    kinds = tuple(kinds)
    names = ", ".join(KIND_NAMES[k] for k in kinds)
    return f"{PLACED_FLOW}\n\n불합격(선이 요소나 글자를 지나는 등 문서에 넣을 수 없는 그림) {len(kinds)}가지: {names}."


COMMON_INPUT = f"""- file_name: 저장할 파일 이름(확장자 없이). 같은 이름이면 덮어쓴다.
- out_dir: 저장할 폴더. 주지 않으면 서버 작업 폴더 아래 {DEFAULT_DIR}/이고, 상대 경로도 서버 작업 폴더 기준이다.
- scale: 출력 배율(기본 {SCALE:g}, {MIN_SCALE:g} 이상). 보통은 주지 않는다."""

IMAGE_RESULT = f"- 그림: 저장한 PNG. 긴 변이 {MAX_IMAGE_EDGE}px를 넘으면 그 길이로 줄여 돌려준다(저장한 파일은 줄이지 않는다)."

PLACES_RESULT = ("- 글: 검사 결과, 요소마다 그린 자리(열쇠와 왼, 위, 폭×높이 — 모양 밖 이름이 있는 요소는 모양과 이름을 함께 덮는 "
                 "자리와 모양 자리), 저장한 파일 경로와 픽셀 크기. 자리를 그대로 다음 입력에 넣으면 요소가 움직이지 않는다.")

MEMBERS = """속성·연산은 한 줄 문자열(그대로 쓴다)이나 객체다. 속성 객체는 name(필수)·type·default·visibility(기본 "-")·static, \
연산 객체는 name(필수)·params(문자열 목록)·returns·visibility(기본 "+")·static. visibility는 "+"·"-"·"#"·"~"·""(안 씀)이고, \
static이 true면 밑줄을 긋는다."""

NEW_INPUT = """공용 입력(열쇠·이름):
- id: 요소의 열쇠. 관계의 from·to와 in이 이 열쇠로 요소를 가리킨다. 주지 않으면 한 줄 이름이 곧 열쇠다. 이름이 여러 줄이거나 \
이름이 없는 요소, 이름이 같은 요소는 id를 준다. 열쇠는 서로 달라야 한다.
- name: 한 줄이면 문자열, 여러 줄이면 줄마다 문자열인 목록(["주문", "관리"]). 도구는 줄을 나누지 않으니 긴 이름은 목록으로 \
나눈다. 한 줄 안에 줄바꿈 글자는 넣지 못한다. 관계 name도 여러 줄 목록을 받는다.
- 관계의 stereotype: «» 없이 이름만(include·extend·deploy·manifest·use 등). 관계 종류를 새로 만들지 않고 어느 관계에든 단다 \
(«deploy»는 의존에). 관계 이름 위 줄에 쓴다."""

PLACED_ELEMENTS = f"""- elements: 요소 목록(하나 이상). 종류를 섞어 한 그림에 그린다.
  - kind(필수): "class"·"abstract"·"interface"·"enum"(클래스 상자 — 인터페이스는 «interface» 상자다), "package"(탭 달린 \
폴더 — 이름은 탭에 쓰고 안에 요소를 둔다), "component"(오른쪽 위에 부품 아이콘을 단 상자), "artifact"(오른쪽 위에 문서 아이콘을 \
단 상자 — 이름은 흔히 파일 이름), "node"(오른쪽과 위에 두께가 보이는 입체 상자 — 이름은 앞면 위쪽에 쓰고 안에 요소를 둔다).
  - name(필수)·id: "공용 입력(열쇠·이름)" 절.
  - left·top(필수): 자리의 왼쪽 위(패키지는 탭, 노드는 두께 띠까지 덮는 자리).
  - stereotype: «» 없이 이름만. 이름 위 줄에 쓴다(component·subsystem·device·executionEnvironment 등).
  - in: 이 요소를 품은 요소(package·node)의 열쇠. "요소 안에 요소 두기(중첩)" 절.
  - width·height: 자리의 최소 크기. 글자와 안의 요소에 맞춰 더 늘어난다.
  - attributes·operations·literals: 클래스 상자만 쓴다(literals는 kind가 "enum"일 때). {MEMBERS}
  - 선은 패키지 몸통(탭 아래), 노드 겉 테두리, 그 밖은 상자 테두리에 닿는다. 패키지 탭은 그 패키지가 끝인 선도 지나가면 안 되므로, \
패키지로 오가는 선은 몸통 가운데가 아니라 탭 오른쪽 몸통의 가운데를 향한다. 안의 요소를 두는 칸은 패키지는 탭 아래 몸통, 노드는 \
이름 줄 아래 앞면(두께 띠 빼고)이다."""

NESTING = f"""요소 안에 요소 두기(중첩):
- 안의 요소에 in으로 품은 요소의 열쇠를 준다. 여러 겹도 된다. 좌표는 늘 그림 전체 기준이다.
- 바깥 요소는 준 왼쪽 위에서 시작해, 안의 요소와 제 이름 칸을 여백 {NEST_PAD}px를 두고 덮도록 오른쪽·아래로 늘어난다. 그래서 \
안의 요소는 바깥 요소의 칸(안의 요소를 두는 곳) 왼쪽·위 테두리에서 {NEST_PAD}px 이상 들여 놓는다.
- 선의 끝 요소를 품은 바깥 요소는 그 선이 안을 지나거나 테두리를 건너도 된다. 다만 테두리를 따라가거나 이름 칸을 지나면 \
불합격이다. 그 선의 글자도 바깥 요소 안에 놓일 수 있다. 그 밖의 요소는 선이 지나가면 불합격이다.
- 품은 요소와 그 안의 요소는 선으로 잇지 않는다."""

NAME_SIDE = f"""- name_side: 이름을 모양 밖에 쓰는 요소의 이름 쪽 {"·".join(f'"{s}"' for s in SIDES)}(첫째가 기본). 요소 자리는 모양과 \
이름을 함께 덮고, left·top은 그 자리의 왼쪽 위다. 선 끝은 모양 테두리에 닿고, 어떤 선이든 이름을 지나가면 불합격이다."""

_ENDS = {"generalization": ("상속", "자식", "삼각형"), "realization": ("실체화", "구현하는 쪽", "삼각형"),
         "dependency": ("의존", "의존하는 쪽", "화살촉")}
_LABELS = {"association": "연관", "aggregation": "집합", "composition": "합성"}


def relation_fields(kinds: Iterable[str], navigable: str = "to", words: Words = BOX_WORDS) -> str:
    """(라) 관계 필드. kinds는 클래스도 관계 여섯 가지 가운데 그 도구가 받는 것(차례대로), navigable은 연관·집합·합성의 기본
    방향이다. words가 클래스도 말(BOX_WORDS)이면 from·to를 상자 이름으로, 아니면 요소 열쇠로 적는다."""
    kinds = tuple(kinds)
    box = words is BOX_WORDS
    quoted = "·".join(f'"{k}"' for k in kinds)
    lines = ["- relations: 관계 목록(없어도 된다).", f"  - kind(필수): {quoted}."]
    meaning = []
    ends = [_ENDS[k] for k in kinds if k in _ENDS]
    if ends:
        who = "·".join(e[0] for e in ends)
        heads = "·".join(dict.fromkeys(e[2] for e in ends))
        meaning.append(f"{who}{josa(who, '은', '는')} from이 {'·'.join(e[1] for e in ends)}이고 {heads}{josa(heads, '이', '가')} "
                       "to 쪽에 붙는다.")
    diamonds = [_LABELS[k] for k in kinds if k in ("aggregation", "composition")]
    if diamonds:
        meaning.append(f"{'·'.join(diamonds)}의 마름모는 from 쪽에 붙는다.")
    lines.append(f"  - from·to(필수): {'상자 이름' if box else '요소 열쇠'}." + "".join(f" {m}" for m in meaning))
    lines.append("  - name: 관계 이름." + ("" if box else ' stereotype: "공용 입력(열쇠·이름)" 절.'))
    assoc = [_LABELS[k] for k in kinds if k in _LABELS]
    if assoc:
        options = "·".join(f'"{n}"' + ("(기본)" if n == navigable else "") for n in NAVIGABLE)
        tail = f"({'·'.join(diamonds)}은 \"to\"·\"none\"만)" if diamonds else ""
        lines.append(f"  - from_multiplicity·to_multiplicity·navigable: {'·'.join(assoc)}만 쓴다. navigable은 화살촉을 둘 쪽 "
                     f"{options}이다{tail}.")
    noun, edge = words.noun, words.edge
    middle, other = ((f"{noun} 가운데", f"상대 {noun} 가운데") if box
                     else (f"{noun} 가운데(요소 종류에 따로 적은 모양은 그 점)", f"상대 {noun}의 그 점"))
    lines.append(f"  - via: 꺾는 점 [[x, y], …]. 선은 {middle}에서 첫 꺾는 점(없으면 {other})으로 가는 선이 "
                 f"{noun} {edge}{josa(edge, '과', '와')} 만나는 곳에서 시작한다. 자기 자신으로 가는 관계는 꺾는 점이 둘 이상 있어야 한다.")
    return "\n".join(lines)
