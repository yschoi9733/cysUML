"""MCP 서버: UML 그림을 그리는 도구를 stdio로 내놓는다(그림 목록은 README).

도구는 그린 PNG와 그 입력 파일(guide.INPUT_SUFFIX)을 저장하고, 검사 결과 글과 그림을 함께 돌려준다. 입력이 틀렸거나, 그림이
너무 커서 PNG로 못 그리거나, 저장할 폴더에 쓸 수 없으면 저장하지 않고 오류 결과(isError)로 돌려준다 — AI가 읽고 고칠 수 있게 예외
대신 결과로 낸다. 그림은 바꿔 넣었는데 입력 파일에서 멈춘 때만 그림이 바뀐 채 오류가 되고, 오류 글이 그렇다고 알린다.
새 그림의 도구 설명과 인자 설명은 그 그림 모듈이 guide의 공용 조각으로 만든다(처음부터 있던 두 도구의 설명은 여기 있다). 입력에
관한 글은 도구 설명이 아니라 인자 설명에 둔다(guide 머리말). 상자 그림(공용 엔진 boxdiagram이 그리는 그림) 도구는 _box_tool
하나로 등록한다.
"""
from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import secrets
import stat
import threading
import unicodedata
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from types import ModuleType
from typing import Annotated, Any, Callable, Optional, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, ImageContent, TextContent
from PIL import Image
from pydantic import Field, WithJsonSchema

from . import (activitydiagram, boxcheck, boxdiagram, classcheck, classdiagram, componentdiagram, deploymentdiagram,
               packagediagram, sequencecheck, sequencediagram, statediagram, usecasediagram)
from .canvas import MIN_SCALE, SCALE
from .guide import (ARGS_NOTE, COMMON_ARGS, DEFAULT_DIR, IMAGE_RESULT, INPUT_RESULT, INPUT_SUFFIX, MAX_IMAGE_EDGE, MEMBERS,
                    SAVED_INPUT, flow, relation_fields, spacing_tips, trunk_aims)
from .parsing import InputError
from .report import Report, fmt_num, fmt_rect
from .sequencediagram import MAX_FRAMES, MAX_MESSAGES, MAX_NOTES, MAX_PARTICIPANTS, LayoutError

MAX_NAME_BYTES = 200  # 파일 이름(확장자 빼고) UTF-8 길이 상한. 파일 시스템 한도는 보통 255바이트
NAME_FORBIDDEN = set('/\\:*?"<>|')

CLASS_TIPS = f"""클래스도 배치 요령:
- 연결이 가장 많은 클래스를 가운데에 둔다.
- 상속·실체화는 부모를 위에, 자식들을 그 아래 한 줄에 둔다.
- 엇갈림이나 불합격이 나오면 먼저 상자 순서와 자리를 바꾸고, 그래도 안 되면 꺾는 점(via)을 준다.
{spacing_tips(classdiagram.SPEC, "관계 이름·다중도", f"(폭은 {classdiagram.MIN_WIDTH}px 이상)")}"""

# 교류도 배치 버그를 비켜 가는 법
SEQUENCE_WAY_AROUND = "참여자 순서나 메시지 차례, 프레임이 덮는 범위(first·last·칸·before)를 바꾸거나, 글자를 줄이거나, 그림을 나눈다"

SEQUENCE_FLOW = f"""교류도 그리는 흐름:
1. 참여자 차례, 메시지 차례, 프레임이 덮는 메시지 범위를 정하고, 필요하면 노트를 더해 그린다. 좌표는 주지 않는다 — \
생명선 간격, 메시지 높이, 활성 막대는 도구가 정한다.
2. 돌려받은 검사 결과와 그림을 본다. 교류도는 도구가 배치하므로 불합격은 cysUML의 배치 버그다. 그래도 그 그림이 필요하면 \
항목마다 붙은 힌트대로 입력을 바꿔 비켜 간다 — {SEQUENCE_WAY_AROUND}. 배치하지 못했다는 오류가 와도 같다.
3. 고친 입력을 같은 file_name으로 다시 그린다(파일을 덮어쓴다).
그림 크기는 알림이라 불합격이 아니다. 다만 개수 한도 안이어도 그림이 너무 크면 PNG로 그리지 못해 오류가 되니, 메시지가 많아 \
그림이 길면 나눈다."""

INSTRUCTIONS = f"""cysUML은 문서에 바로 넣을 UML 그림을 PNG로 그리고, 선이 요소나 글자를 지나는지 검사해 그림과 함께 돌려준다.
- 클래스도는 draw_class_diagram으로 그린다. 배치는 부르는 AI가 하고, cysUML은 받은 좌표대로 그린다.
- 패키지도는 draw_package_diagram으로 그린다. 배치는 부르는 AI가 한다. 패키지 안에 클래스·패키지를 넣고, 컴포넌트·아티팩트·노드도 \
함께 그린다.
- 컴포넌트도는 draw_component_diagram으로 그린다. 배치는 부르는 AI가 한다. 컴포넌트와 제공 인터페이스 원, 컴포넌트를 구현하는 \
아티팩트, 컴포넌트를 실현하는 클래스를 그린다. 인터페이스를 쓰는 쪽은 원으로 가는 의존 화살표나 소켓(원을 감싸는 반원)으로 그린다.
- 배치도(deployment diagram)는 draw_deployment_diagram으로 그린다. 요소 자리는 부르는 AI가 잡는다(요령은 도구 설명의 "자리 잡기 \
요령"에 있다). 노드 안에 컴포넌트·아티팩트·노드를 넣고, 노드끼리 통신 경로를, 노드 밖 요소에서 노드로 «deploy»를 긋는다.
- 유즈케이스도는 draw_use_case_diagram으로 그린다. 배치는 부르는 AI가 한다. 시스템 경계 안에 유즈케이스를 넣고, 밖의 액터와는 \
연관으로, 유즈케이스끼리는 «include»·«extend»로, 같은 종류끼리는 일반화로 잇는다.
- 상태도는 draw_state_diagram으로 그린다. 배치는 부르는 AI가 한다. 시작·끝 점, 상태, 선택 마름모를 전이로 잇고, 상태 안에 상태를 넣는다.
- 액티비티도는 draw_activity_diagram으로 그린다. 배치는 부르는 AI가 한다. 시작·끝 점, 행동, 결정·합류 마름모를 흐름으로 잇는다.
- 교류도는 draw_sequence_diagram으로 그린다. 배치는 cysUML이 하고, AI는 참여자·메시지·프레임의 차례를 주고 필요하면 노트를 더한다.
불합격 종류와 그림마다의 배치 요령은 각 도구 설명에 있다.
{SAVED_INPUT}

{flow()}

{SEQUENCE_FLOW}"""

CLASS_TOOL = f"""클래스도를 그려 PNG와 입력 파일로 저장하고, 검사 결과와 그림을 함께 돌려준다. 상자는 준 왼쪽 위(left·top) 그대로, \
관계선은 준 꺾는 점(via)을 따라 그리고, 상자 크기·선 끝·선 글자 자리만 도구가 정한다. 좌표는 px이고 y는 아래로 커진다.

{ARGS_NOTE}

결과
- 글: 검사 결과, 상자마다 그린 자리와 크기, 저장한 그림·입력 파일 경로와 그림 픽셀 크기.
{trunk_aims(classdiagram.SPEC)}
{IMAGE_RESULT}
{INPUT_RESULT}
- classes·relations·file_name이 틀리면 그리지 않고 틀린 곳을 classes[0].left 꼴 자리와 함께 모두 모아 오류로 돌려준다. \
그림이 너무 커서 PNG로 그릴 수 없거나 저장할 폴더에 쓸 수 없을 때도 오류로 돌려준다.

{flow(classcheck.KINDS, classdiagram.SPEC.words)}

{CLASS_TIPS}"""

CLASS_ARGS = {  # 클래스도 도구의 그림 입력 인자 설명(인자 이름 → 글)
    "classes": f"""- classes: 상자 목록(하나 이상).
  - name(필수): 관계가 이 이름으로 상자를 가리키므로 서로 달라야 한다.
  - left·top(필수): 상자 왼쪽 위.
  - kind: "class"(기본)·"abstract"·"interface"·"enum".
  - stereotype: «» 없이 이름만.
  - attributes·operations: {MEMBERS}
  - literals: 열거 값 목록(kind가 "enum"일 때만).
  - width·height: 최소 크기. 글자가 더 길면 그만큼 늘어난다(폭 기본 90).""",
    "relations": relation_fields(classdiagram.SPEC),
}

SEQUENCE_TOOL = f"""교류도를 그려 PNG와 입력 파일로 저장하고, 검사 결과와 그림을 함께 돌려준다. 교류도는 도구가 배치한다 — 좌표는 받지 \
않고, 생명선 간격과 메시지 높이를 글자 폭에 맞춰 정하고 활성 막대를 메시지에서 잇는다.

{ARGS_NOTE}

결과
- 글: 검사 결과, 저장한 그림·입력 파일 경로와 그림 픽셀 크기. 검사 항목은 메시지·프레임·노트를 입력 안의 자리(messages[3]·\
frames[0]·notes[0])로, 참여자를 이름으로 가리킨다.
{IMAGE_RESULT}
{INPUT_RESULT}
- 입력이 틀리면 그리지 않고 틀린 곳을 messages[2].to 꼴 자리와 함께 모두 모아 오류로 돌려준다. 그림이 너무 커서 PNG로 그릴 수 \
없거나, 저장할 폴더에 쓸 수 없거나, 도구가 배치하지 못했을 때도 오류로 돌려준다.

{SEQUENCE_FLOW}"""

SEQUENCE_ARGS = {  # 교류도 도구의 그림 입력 인자 설명(인자 이름 → 글)
    "participants": f"""- participants: 참여자 목록(하나 이상, {MAX_PARTICIPANTS}개까지). 이 차례로 왼쪽부터 놓는다.
  - name(필수): 메시지가 이 이름으로 참여자를 가리키므로 서로 달라야 한다.
  - kind: "lifeline"(기본)·"actor".""",
    "messages": f"""- messages: 메시지 목록(없어도 된다, {MAX_MESSAGES}개까지). 이 차례로 위에서부터 놓는다.
  - from·to(필수): 참여자 이름. 생명선은 자기 자신을 부를 수 있다(from·to가 같은 call — 자기 호출). 자기 호출 막대는 짧게 \
끝나고, 그 뒤 메시지는 자기 호출이 끝난 뒤의 일로 그려진다 — 자기 호출 안에서 하는 일은 어느 호출의 일인지 밝혀 notes에 적는다. \
액터의 자기 호출과 자기 자신에게 보내는 reply·create는 받지 않는다.
  - kind: "call"(기본, 호출)·"reply"(반환, 점선)·"create"(생명선을 만든다 — 그 생명선의 머리가 이 메시지 높이에 놓인다).
  - name: 메시지 글자. call은 꼭 준다(부르는 연산). reply는 돌려주는 값이 있을 때, create는 «create» 밑에 한 줄 더 쓸 때만 준다.
  - 반환(reply)은 나를 부른 쪽으로 보낸다 — A가 B를 불렀으면 B에서 A로. 거꾸로 보내도 그려지지만 뜻이 틀린다.
  - create는 액터에 보내지 못하고, 그 생명선이 주고받는 첫 메시지여야 한다. 같은 생명선을 다시 만드는 것은 같은 alt의 다른 \
칸에서만 한다 — 칸마다 그 높이에 머리를 그리고, 앞 칸에서 만든 생명선은 그 칸과 함께 끝나 다시 만들기 전에는 쓰지 못한다.
  - 활성 막대는 도구가 잇는다. 대개 생명선을 부르면 열리고, 그 생명선이 반환하거나 부른 쪽이 다음 메시지를 보내면 닫힌다\
(액터가 받는 호출, 자기 호출 막대, 프레임 둘레는 규칙이 따로 있다).""",
    "frames": f"""- frames: 프레임 목록(없어도 된다, {MAX_FRAMES}개까지). 메시지는 messages 안의 자리(0부터)로 가리킨다. 프레임은 그림 전체 폭으로 \
그리고, 프레임끼리 덮는 메시지가 겹치면 안 된다(프레임 안에 프레임·ref를 넣지 않는다).
  - kind(필수): "loop"·"opt"·"alt"·"ref".
  - loop·opt: first·last(필수, 덮는 첫 메시지와 끝 메시지), condition(조건).
  - alt: branches(필수, 칸 둘 이상). 칸마다 condition·first·last를 모두 주고, 칸은 빈틈없이 이어 붙인다(다음 칸 first는 앞 칸 \
last+1). 마지막 칸 조건은 흔히 "else"다.
  - ref: name(필수, 상자에 쓸 이름), before(필수, 이 자리 메시지 바로 앞에 놓는다 — 메시지 수와 같으면 맨 뒤).
  - condition은 대괄호 없이 쓴다(도구가 씌운다).""",
    "notes": f"- notes: 노트 글자 목록({MAX_NOTES}개까지). 같은 그림 안 생명선 아래에 차례대로 모은다.",
}


def _version() -> str:
    try:
        return version("cysuml")
    except PackageNotFoundError:  # 설치하지 않은 소스에서 띄웠다
        return ""


mcp = MCPServer(name="cysUML", instructions=INSTRUCTIONS, version=_version())
_drawing = threading.Lock()  # 동기 도구는 스레드에서 돈다. 글꼴 객체를 함께 쓰므로 그리기는 한 번에 하나씩
_saving = threading.Lock()  # 같은 이름을 동시에 저장해도 그림과 입력 파일이 서로 다른 부름의 것으로 짝지어지지 않게


def _error(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=True)


def _file_name(raw: str) -> tuple[Optional[str], Optional[str]]:
    """(쓸 이름, 문제). 끝의 .png나 입력 파일의 끝(입력 파일 이름을 그대로 줬을 때)은 떼고, 경로를 가리키거나 파일 이름으로 못 쓰는
    글자가 들면 문제를 돌려준다."""
    name = unicodedata.normalize("NFC", raw.strip())
    for suffix in (".png", INPUT_SUFFIX):
        if name.lower().endswith(suffix):
            name = name[:-len(suffix)].rstrip()
            break
    if not name:
        return None, "file_name이 비어 있다"
    bad = sorted({c for c in name if c in NAME_FORBIDDEN or unicodedata.category(c).startswith("C")})
    if bad:
        return None, f"file_name에 파일 이름으로 쓸 수 없는 글자가 있다: {', '.join(repr(c) for c in bad)}. 폴더는 out_dir로 준다"
    if name.startswith("."):
        return None, "file_name은 점(.)으로 시작할 수 없다"
    if len(name.encode()) > MAX_NAME_BYTES:
        return None, f"file_name이 너무 길다(UTF-8로 {MAX_NAME_BYTES}바이트까지)"
    return name, None


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _shrink(img: Image.Image) -> Image.Image:
    w, h = img.size
    if max(w, h) <= MAX_IMAGE_EDGE:
        return img
    k = MAX_IMAGE_EDGE / max(w, h)
    return img.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)


def _record(tool: str, name: str, data: dict, scale: float) -> bytes:
    """입력 파일의 내용: 그린 도구, file_name, 그린 입력, scale. 그대로 그 도구에 넣으면 같은 그림이 나온다(tool은 SDK가 모르는
    인자로 버린다). scale은 기본값이어도 넣어 기본값이 바뀌어도 같은 크기로 그린다. out_dir은 넣지 않는다 — 문서와 함께 커밋되는
    파일에 절대 경로가 남지 않고, 폴더를 옮겨도 쓸 수 있게."""
    record = {"tool": tool, "file_name": name, **data, "scale": scale}

    def one(v: Any) -> str:
        return json.dumps(v, ensure_ascii=False)

    def field(key: str, value: Any) -> str:
        # README 예시처럼 목록의 항목 하나를 한 줄에 쓴다 — 읽기 쉽고, 커밋하면 고친 항목만 diff에 나온다
        if not (isinstance(value, list) and value):
            return f"  {one(key)}: {one(value)}"
        items = ",\n".join(f"    {one(item)}" for item in value)
        return f"  {one(key)}: [\n{items}\n  ]"
    text = "{\n" + ",\n".join(field(k, v) for k, v in record.items()) + "\n}\n"
    # 짝 없는 서로게이트는 parsing이 거르지만, 남더라도 \ud800 꼴 JSON 이스케이프로 쓴다
    return text.encode("utf-8", "backslashreplace")


def _is_dir(path: Path) -> bool:
    """path 자리 자체가 폴더인지(링크는 따라가지 않는다 — 바꿔 넣으면 링크가 바뀐다). 없으면 False, 폴더를 탐색하지 못하는 등의 오류는
    올린다 — Path.is_dir은 파이썬 버전마다 오류를 삼키는 범위가 달라 쓰지 않는다(3.14는 모두 삼킨다)."""
    try:
        return stat.S_ISDIR(os.lstat(path).st_mode)
    except FileNotFoundError:
        return False


def _stage(path: Path, data: bytes) -> Path:
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    try:
        with open(tmp, "xb") as f:
            f.write(data)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    return tmp


def _save(png: bytes, record: bytes, out_dir: Optional[str], name: str) -> tuple[Optional[tuple[Path, Path]], Optional[str]]:
    """((저장한 그림 경로, 입력 파일 경로), 문제). 비었거나 공백뿐인 out_dir은 주지 않은 것으로 본다. 두 파일을 임시 파일에 다 쓴
    뒤 바꿔 넣는다 — 쓰다 실패하거나 같은 이름으로 동시에 써도 깨진 파일이 남지 않는다. 그림을 먼저 바꿔 넣는다: 흔한 실패(Windows
    에서 뷰어가 PNG를 잡고 있다)에는 둘 다 그대로 두고, 그림만 바뀐 채 멈추면 옛 입력 파일을 지워 다음에 그 파일을 이 그림의 입력으로
    읽어 고치는 일을 막는다."""
    given = (out_dir or "").strip()
    if given.startswith("~") and os.path.expanduser(given).startswith("~"):
        return None, f"out_dir {given!r}의 '~'를 홈 폴더로 풀 수 없다. 저장하지 않았다 — out_dir을 절대 경로로 준다."
    try:
        folder = Path(os.path.abspath(os.path.expanduser(given or DEFAULT_DIR)))
    except OSError as e:  # 서버 작업 폴더가 지워졌다
        return None, f"서버 작업 폴더를 알 수 없어 저장할 곳을 정하지 못했다({e.strerror or e}). out_dir에 절대 경로를 준다."
    image, kept = folder / f"{name}.png", folder / f"{name}{INPUT_SUFFIX}"
    files = ((image, png), (kept, record))
    where = f"out_dir {folder}" if given else f"기본 폴더 {folder}(서버 작업 폴더 아래 {DEFAULT_DIR}/)"
    staged: list[tuple[Path, Path]] = []
    done: list[Path] = []
    at = image  # 실패하면 오류 글에 쓸 자리 — 실패할 수 있는 단계마다 그 단계가 다루는 파일로 바꿔 둔다
    left = ""  # 그림만 바뀐 채 멈췄을 때 옛 입력 파일이 어떻게 됐는지
    try:
        with _saving:
            folder.mkdir(parents=True, exist_ok=True)
            for path, _ in files:  # 한쪽만 바꿔 넣은 채 멈추지 않게 먼저 본다
                at = path
                if _is_dir(path):  # 폴더는 쓸 수 있으니 다른 폴더가 아니라 그 자리를 비우라고 한다
                    return None, (f"그림을 저장하지 못했다 — {where}의 {path.name} 자리에 폴더가 있다. 그 폴더를 옮기거나 다른 "
                                  "file_name을 준다.")
            for path, data in files:
                at = path
                staged.append((_stage(path, data), path))
            for tmp, path in staged:
                at = path
                try:
                    os.replace(tmp, path)
                except OSError:
                    if done:  # 잠금 안에서 지운다 — 밖이면 그 사이 다른 부름이 저장한 새 입력 파일을 지울 수 있다
                        try:
                            kept.unlink()
                            left = f"앞서 저장한 {kept.name}은 이 그림과 맞지 않아 지웠다"
                        except FileNotFoundError:
                            left = f"{kept.name}은 없다"
                        except OSError:
                            left = f"앞서 저장한 {kept.name}이 남아 이 그림과 맞지 않는다(지우지도 못했다)"
                    raise
                done.append(path)
    except (OSError, ValueError) as e:  # ValueError: 경로에 NUL 글자
        reason = e.strerror if isinstance(e, OSError) and e.strerror else e
        if done:
            return None, (f"입력 파일을 저장하지 못했다 — {where}에 그림 {image.name}은(는) 새로 썼지만 {kept.name}을(를) 쓸 수 "
                          f"없다({reason}). {left}. 막은 것을 풀고 같은 입력으로 다시 그린다.")
        return None, (f"그림을 저장하지 못했다 — {where}에 {at.name}을(를) 쓸 수 없다({reason}). 다른 프로그램(그림 뷰어 등)이 "
                      "그 파일을 잡고 있으면 닫고 같은 입력으로 다시 그리고, 폴더에 쓸 수 없으면 쓸 수 있는 폴더를 out_dir에 절대 "
                      "경로로 준다.")
    finally:
        for tmp, path in staged:
            if path not in done:
                with contextlib.suppress(OSError):
                    tmp.unlink()
    return (image, kept), None


def _places(drawing: boxdiagram.Drawing) -> list[str]:
    """AI가 배치하는 그림의 요소마다 그린 자리(클래스도는 "상자 자리"). 모양 밖 이름이 있는 요소는 모양 자리를, 선이 모양
    가운데에서 비켜난 점을 향하는 요소(aims_aside를 켠 모양)는 그 점을, 공유 줄기를 받는 관계 종류마다 향하는 점이 나뉜 요소
    (PlacedBox.aims)는 "상속 향하는 점 x, y"처럼 종류마다의 점을 함께 적는다."""
    relations = drawing.layout.spec.relations

    def one(p: boxdiagram.PlacedBox) -> str:
        assert p.anchor is not None
        shape = f", 모양 {fmt_rect(p.shape_rect)}" if p.shape_rect != p.rect else ""
        aim = f", 향하는 점 {fmt_num(p.anchor[0])}, {fmt_num(p.anchor[1])}" if boxdiagram.aims_off_center(p.shape) else ""
        aim += "".join(f", {boxdiagram.kind_aim(relations[k].label, fmt_num(x), fmt_num(y))}" for k, (x, y) in p.aims)
        return f"{p.key}({fmt_rect(p.rect)}{shape}{aim})"
    noun = drawing.layout.spec.words.noun
    return [f"{noun} 자리(왼, 위, 폭×높이): " + ", ".join(one(p) for p in drawing.layout.boxes)]


D = TypeVar("D", boxdiagram.Drawing, sequencediagram.Drawing)


def _draw(tool: str, file_name: str, data: dict, scale: float, render: Callable[[dict, float], D],
          check: Callable[[D], Report], out_dir: Optional[str],
          extra_lines: Optional[Callable[[D], list[str]]] = None) -> CallToolResult:
    """render(data, scale)로 그려 check로 검사하고, 그림과 입력 파일(그린 도구 tool과 data)을 저장해 돌려준다. extra_lines(그린
    것)는 검사 결과 뒤에 붙이는 줄이다. file_name 문제는 그림 입력 오류와 함께 모아 알린다."""
    name, problem = _file_name(file_name)
    problems = [problem] if problem else []
    with _drawing:
        try:
            drawing = render(data, scale)
        except InputError as e:
            problems += e.problems
        except LayoutError as e:  # file_name 문제가 함께 있으면 그것부터 알린다
            if not problems:
                return _error(f"교류도를 배치하지 못했다 — {e}. 파일은 저장하지 않았다. 입력은 맞는데 cysUML이 자리를 찾지 "
                              f"못한 것이라, 비켜 가려면 {SEQUENCE_WAY_AROUND}.")
        if problems:
            return _error(f"입력 오류 — {len(problems)}건\n" + "\n".join(f"- {p}" for p in problems))
        report = check(drawing)
        extra = extra_lines(drawing) if extra_lines else []
        if report.png_size is None:
            return _error("\n".join(["그림이 너무 커서 PNG를 그리지 않았다(파일도 저장하지 않았다).", report.summary(), *extra]))
        img = drawing.canvas.to_image()
    full = _png(img)
    saved, problem = _save(full, _record(tool, name, data, scale), out_dir, name)
    if problem:
        return _error("\n".join([problem, "", report.summary(), *extra]))
    image_path, input_path = saved
    shown = _shrink(img)
    lines = [report.summary(), *extra, f"저장한 파일: {image_path} ({img.width}×{img.height}px), 입력 {input_path}"]
    if shown is not img:
        lines.append(f"돌려준 그림은 긴 변을 {MAX_IMAGE_EDGE}px로 줄였다({shown.width}×{shown.height}px). "
                     "원래 크기는 저장한 그림에 있다.")
    data_b64 = base64.b64encode(full if shown is img else _png(shown)).decode("ascii")
    return CallToolResult(content=[
        TextContent(type="text", text="\n".join(lines)),
        ImageContent(type="image", data=data_b64, mime_type="image/png"),
    ])


# 그림 입력(classes·messages 등)은 모양을 검사하지 않고 받는다 — 파서가 자리 붙은 오류를 한 번에 모아 알린다
def _listed(description: str, item: str = "object") -> WithJsonSchema:
    return WithJsonSchema({"type": "array", "items": {"type": item}, "description": description})


def _list_arg(description: str, item: str = "object") -> Any:
    return Annotated[Any, _listed(description, item)]


FileName = Annotated[str, Field(description=COMMON_ARGS["file_name"])]
OutDir = Annotated[Optional[str], Field(description=COMMON_ARGS["out_dir"])]
Scale = Annotated[float, Field(ge=MIN_SCALE, allow_inf_nan=False, description=COMMON_ARGS["scale"])]


CLASS_NAME = "draw_class_diagram"


@mcp.tool(name=CLASS_NAME, description=CLASS_TOOL)
def draw_class_diagram(
        file_name: FileName,
        classes: _list_arg(CLASS_ARGS["classes"]),
        relations: _list_arg(CLASS_ARGS["relations"]) = None,
        out_dir: OutDir = None,
        scale: Scale = SCALE,
) -> CallToolResult:
    data = {"classes": classes} if relations is None else {"classes": classes, "relations": relations}
    return _draw(CLASS_NAME, file_name, data, scale, classdiagram.render, classcheck.check, out_dir, _places)


def _box_tool(name: str, diagram: ModuleType) -> None:
    """상자 그림 도구 하나를 등록한다. 그림 모듈(diagram)의 render·TOOL·ARGS(elements·relations 인자 설명)를 쓰고, 인자는
    file_name·elements·relations·out_dir·scale이다."""
    def tool(file_name, elements, relations=None, out_dir=None, scale=SCALE):
        data = {"elements": elements} if relations is None else {"elements": elements, "relations": relations}
        return _draw(name, file_name, data, scale, diagram.render, boxcheck.check, out_dir, _places)

    # SDK는 함수 이름으로 입력 스키마 이름(<이름>Arguments)을 짓고, 글자로 남은 주석을 그 함수의 모듈에서 풀어 인자 설명을
    # 도구마다 바꿀 수 없다 — 이름은 도구 이름으로, 주석은 글자가 아닌 타입으로 준다
    tool.__name__ = tool.__qualname__ = name
    tool.__annotations__ = {"file_name": FileName, "elements": _list_arg(diagram.ARGS["elements"]),
                            "relations": _list_arg(diagram.ARGS["relations"]), "out_dir": OutDir, "scale": Scale,
                            "return": CallToolResult}
    mcp.add_tool(tool, name=name, description=diagram.TOOL)


_box_tool("draw_package_diagram", packagediagram)
_box_tool("draw_component_diagram", componentdiagram)
_box_tool("draw_deployment_diagram", deploymentdiagram)
_box_tool("draw_use_case_diagram", usecasediagram)
_box_tool("draw_state_diagram", statediagram)
_box_tool("draw_activity_diagram", activitydiagram)


SEQUENCE_NAME = "draw_sequence_diagram"


@mcp.tool(name=SEQUENCE_NAME, description=SEQUENCE_TOOL)
def draw_sequence_diagram(
        file_name: FileName,
        participants: _list_arg(SEQUENCE_ARGS["participants"]),
        messages: _list_arg(SEQUENCE_ARGS["messages"]) = None,
        frames: _list_arg(SEQUENCE_ARGS["frames"]) = None,
        notes: _list_arg(SEQUENCE_ARGS["notes"], "string") = None,
        out_dir: OutDir = None,
        scale: Scale = SCALE,
) -> CallToolResult:
    given = {"messages": messages, "frames": frames, "notes": notes}
    data = {"participants": participants, **{k: v for k, v in given.items() if v is not None}}
    return _draw(SEQUENCE_NAME, file_name, data, scale, sequencediagram.render, sequencecheck.check, out_dir)
