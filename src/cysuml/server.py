"""MCP 서버: UML 그림을 그리는 도구를 stdio로 내놓는다(그림 목록은 README).

도구는 그린 PNG를 파일로 저장하고, 검사 결과 글과 그림을 함께 돌려준다. 입력이 틀렸거나, 그림이 너무 커서 PNG로 못
그리거나, 저장할 폴더에 쓸 수 없으면 저장하지 않고 오류 결과(isError)로 돌려준다 — AI가 읽고 고칠 수 있게 예외 대신 결과로 낸다.
새 그림의 도구 설명은 그 그림 모듈이 guide의 공용 조각으로 만든다(처음부터 있던 두 도구의 설명은 여기 있다).
"""
from __future__ import annotations

import base64
import contextlib
import io
import os
import secrets
import threading
import unicodedata
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, Any, Callable, Optional, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, ImageContent, TextContent
from PIL import Image
from pydantic import Field, WithJsonSchema

from . import (boxcheck, boxdiagram, classcheck, classdiagram, deploymentdiagram, packagediagram, sequencecheck,
               sequencediagram)
from .canvas import MIN_SCALE, SCALE
from .guide import COMMON_INPUT, DEFAULT_DIR, IMAGE_RESULT, MAX_IMAGE_EDGE, MEMBERS, flow, relation_fields
from .parsing import InputError
from .report import Report, fmt_rect
from .sequencediagram import MAX_FRAMES, MAX_MESSAGES, MAX_NOTES, MAX_PARTICIPANTS, LayoutError

MAX_NAME_BYTES = 200  # 파일 이름(확장자 빼고) UTF-8 길이 상한. 파일 시스템 한도는 보통 255바이트
NAME_FORBIDDEN = set('/\\:*?"<>|')

CLASS_TIPS = """클래스도 배치 요령:
- 연결이 가장 많은 클래스를 가운데에 둔다.
- 상속·실체화는 부모를 위에, 자식들을 그 아래 한 줄에 둔다.
- 엇갈림이나 불합격이 나오면 먼저 상자 순서와 자리를 바꾸고, 그래도 안 되면 꺾는 점(via)을 준다.
- 상자 사이는 관계 이름·다중도 글자가 들어갈 만큼 띄운다. 가로 80px·세로 60px쯤에서 시작하고, 글자가 길면 더 띄운다.
- 상자 크기는 도구가 글자에 맞춰 늘린다(폭은 90px 이상). 그린 크기는 결과의 "상자 자리"에서 보고 다음 배치에 쓴다."""

# 교류도 배치 버그를 비켜 가는 법
SEQUENCE_WAY_AROUND = "참여자 순서나 메시지 차례, 프레임이 덮는 범위(first·last·칸·before)를 바꾸거나, 글자를 줄이거나, 그림을 나눈다"

SEQUENCE_FLOW = f"""교류도 그리는 흐름:
1. 참여자 차례, 메시지 차례, 프레임이 덮는 메시지 범위를 정해 그린다. 좌표는 주지 않는다 — 생명선 간격, 메시지 높이, \
활성 막대는 도구가 정한다.
2. 돌려받은 검사 결과와 그림을 본다. 교류도는 도구가 배치하므로 불합격은 cysUML의 배치 버그다. 그래도 그 그림이 필요하면 \
항목마다 붙은 힌트대로 입력을 바꿔 비켜 간다 — {SEQUENCE_WAY_AROUND}. 배치하지 못했다는 오류가 와도 같다.
3. 고친 입력을 같은 file_name으로 다시 그린다(파일을 덮어쓴다).
그림 크기는 알림이라 불합격이 아니다. 다만 개수 한도 안이어도 그림이 너무 크면 PNG로 그리지 못해 오류가 되니, 메시지가 많아 \
그림이 길면 나눈다."""

INSTRUCTIONS = f"""cysUML은 문서에 바로 넣을 UML 그림을 PNG로 그리고, 선이 요소나 글자를 지나는지 검사해 그림과 함께 돌려준다.
- 클래스도는 draw_class_diagram으로 그린다. 배치는 부르는 AI가 하고, cysUML은 받은 좌표대로 그린다.
- 패키지도는 draw_package_diagram으로 그린다. 배치는 부르는 AI가 한다. 패키지 안에 클래스·패키지를 넣고, 컴포넌트·아티팩트·노드도 \
함께 그린다.
- 배치도(deployment diagram)는 draw_deployment_diagram으로 그린다. 요소 자리는 부르는 AI가 잡는다(요령은 도구 설명의 "자리 잡기 \
요령"에 있다). 노드 안에 컴포넌트·아티팩트·노드를 \
넣고, 노드끼리 통신 경로를, 노드 밖 요소에서 노드로 «deploy»를 긋는다.
- 교류도는 draw_sequence_diagram으로 그린다. 배치는 cysUML이 하고, AI는 참여자·메시지·프레임의 차례만 준다.
불합격 종류와 그림마다의 배치 요령은 각 도구 설명에 있다.

{flow()}

{SEQUENCE_FLOW}"""

CLASS_TOOL = f"""클래스도를 그려 PNG 파일로 저장하고, 검사 결과와 그림을 함께 돌려준다. 상자는 준 왼쪽 위(left·top) 그대로, \
관계선은 준 꺾는 점(via)을 따라 그리고, 상자 크기·선 끝·선 글자 자리만 도구가 정한다. 좌표는 px이고 y는 아래로 커진다.

입력
- classes: 상자 목록(하나 이상).
  - name(필수): 관계가 이 이름으로 상자를 가리키므로 서로 달라야 한다.
  - left·top(필수): 상자 왼쪽 위.
  - kind: "class"(기본)·"abstract"·"interface"·"enum".
  - stereotype: «» 없이 이름만.
  - attributes·operations: {MEMBERS}
  - literals: 열거 값 목록(kind가 "enum"일 때만).
  - width·height: 최소 크기. 글자가 더 길면 그만큼 늘어난다(폭 기본 90).
{relation_fields(classdiagram.SPEC)}
{COMMON_INPUT}

결과
- 글: 검사 결과, 상자마다 그린 자리와 크기, 저장한 파일 경로와 픽셀 크기.
{IMAGE_RESULT}
- classes·relations·file_name이 틀리면 그리지 않고 틀린 곳을 classes[0].left 꼴 자리와 함께 모두 모아 오류로 돌려준다. \
그림이 너무 커서 PNG로 그릴 수 없거나 저장할 폴더에 쓸 수 없을 때도 오류로 돌려준다.

{flow(classcheck.KINDS, classdiagram.SPEC.words)}

{CLASS_TIPS}"""

SEQUENCE_TOOL = f"""교류도를 그려 PNG 파일로 저장하고, 검사 결과와 그림을 함께 돌려준다. 교류도는 도구가 배치한다 — 좌표는 받지 \
않고, 생명선 간격과 메시지 높이를 글자 폭에 맞춰 정하고 활성 막대를 메시지에서 잇는다.

입력
- participants: 참여자 목록(하나 이상, {MAX_PARTICIPANTS}개까지). 이 차례로 왼쪽부터 놓는다.
  - name(필수): 메시지가 이 이름으로 참여자를 가리키므로 서로 달라야 한다.
  - kind: "lifeline"(기본)·"actor".
- messages: 메시지 목록(없어도 된다, {MAX_MESSAGES}개까지). 이 차례로 위에서부터 놓는다.
  - from·to(필수): 참여자 이름. 자기 자신에게 보내는 메시지는 받지 않는다 — 그 일은 notes에 적는다.
  - kind: "call"(기본, 호출)·"reply"(반환, 점선)·"create"(생명선을 만든다 — 그 생명선의 머리가 이 메시지 높이에 놓인다).
  - name: 메시지 글자. call은 꼭 준다(부르는 연산). reply는 돌려주는 값이 있을 때, create는 «create» 밑에 한 줄 더 쓸 때만 준다.
  - 반환(reply)은 나를 부른 쪽으로 보낸다 — A가 B를 불렀으면 B에서 A로. 거꾸로 보내도 그려지지만 뜻이 틀린다.
  - create는 액터에 보내지 못하고, 그 생명선이 주고받는 첫 메시지여야 한다. 같은 생명선을 다시 만드는 것은 같은 alt의 다른 \
칸에서만 한다 — 칸마다 그 높이에 머리를 그리고, 앞 칸에서 만든 생명선은 그 칸과 함께 끝나 다시 만들기 전에는 쓰지 못한다.
  - 활성 막대는 도구가 잇는다. 대개 생명선을 부르면 열리고, 그 생명선이 반환하거나 부른 쪽이 다음 메시지를 보내면 닫힌다\
(액터가 받는 호출과 프레임 둘레는 규칙이 따로 있다).
- frames: 프레임 목록(없어도 된다, {MAX_FRAMES}개까지). 메시지는 messages 안의 자리(0부터)로 가리킨다. 프레임은 그림 전체 폭으로 \
그리고, 프레임끼리 덮는 메시지가 겹치면 안 된다(프레임 안에 프레임·ref를 넣지 않는다).
  - kind(필수): "loop"·"opt"·"alt"·"ref".
  - loop·opt: first·last(필수, 덮는 첫 메시지와 끝 메시지), condition(조건).
  - alt: branches(필수, 칸 둘 이상). 칸마다 condition·first·last를 모두 주고, 칸은 빈틈없이 이어 붙인다(다음 칸 first는 앞 칸 \
last+1). 마지막 칸 조건은 흔히 "else"다.
  - ref: name(필수, 상자에 쓸 이름), before(필수, 이 자리 메시지 바로 앞에 놓는다 — 메시지 수와 같으면 맨 뒤).
  - condition은 대괄호 없이 쓴다(도구가 씌운다).
- notes: 노트 글자 목록({MAX_NOTES}개까지). 그림 아래에 차례대로 모은다.
{COMMON_INPUT}

결과
- 글: 검사 결과, 저장한 파일 경로와 픽셀 크기. 검사 항목은 메시지·프레임·노트를 입력 안의 자리(messages[3]·frames[0]·notes[0])로, \
참여자를 이름으로 가리킨다.
{IMAGE_RESULT}
- 입력이 틀리면 그리지 않고 틀린 곳을 messages[2].to 꼴 자리와 함께 모두 모아 오류로 돌려준다. 그림이 너무 커서 PNG로 그릴 수 \
없거나, 저장할 폴더에 쓸 수 없거나, 도구가 배치하지 못했을 때도 오류로 돌려준다.

{SEQUENCE_FLOW}"""


def _version() -> str:
    try:
        return version("cysuml")
    except PackageNotFoundError:  # 설치하지 않은 소스에서 띄웠다
        return ""


mcp = MCPServer(name="cysUML", instructions=INSTRUCTIONS, version=_version())
_drawing = threading.Lock()  # 동기 도구는 스레드에서 돈다. 글꼴 객체를 함께 쓰므로 그리기는 한 번에 하나씩


def _error(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=True)


def _file_name(raw: str) -> tuple[Optional[str], Optional[str]]:
    """(쓸 이름, 문제). 끝의 .png는 떼고, 경로를 가리키거나 파일 이름으로 못 쓰는 글자가 들면 문제를 돌려준다."""
    name = unicodedata.normalize("NFC", raw.strip())
    if name.lower().endswith(".png"):
        name = name[:-4].rstrip()
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


def _write(path: Path, data: bytes) -> None:
    """같은 폴더의 임시 파일에 다 쓴 뒤 바꿔 넣는다 — 쓰다 실패하거나 같은 이름으로 동시에 써도 깨진 파일이 남지 않는다."""
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    try:
        with open(tmp, "xb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def _save(png: bytes, out_dir: Optional[str], name: str) -> tuple[Optional[Path], Optional[str]]:
    """(저장한 경로, 문제). 비었거나 공백뿐인 out_dir은 주지 않은 것으로 본다."""
    given = (out_dir or "").strip()
    if given.startswith("~") and os.path.expanduser(given).startswith("~"):
        return None, f"out_dir {given!r}의 '~'를 홈 폴더로 풀 수 없다. 저장하지 않았다 — out_dir을 절대 경로로 준다."
    try:
        folder = Path(os.path.abspath(os.path.expanduser(given or DEFAULT_DIR)))
    except OSError as e:  # 서버 작업 폴더가 지워졌다
        return None, f"서버 작업 폴더를 알 수 없어 저장할 곳을 정하지 못했다({e.strerror or e}). out_dir에 절대 경로를 준다."
    path = folder / f"{name}.png"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        _write(path, png)
    except (OSError, ValueError) as e:  # ValueError: 경로에 NUL 글자
        reason = e.strerror if isinstance(e, OSError) and e.strerror else e
        where = f"out_dir {folder}" if given else f"기본 폴더 {folder}(서버 작업 폴더 아래 {DEFAULT_DIR}/)"
        return None, (f"그림을 저장하지 못했다 — {where}에 {path.name}을(를) 쓸 수 없다({reason}). "
                      "쓸 수 있는 폴더를 out_dir에 절대 경로로 준다.")
    return path, None


def _places(drawing: boxdiagram.Drawing) -> list[str]:
    """AI가 배치하는 그림의 요소마다 그린 자리(클래스도는 "상자 자리"). 모양 밖 이름이 있는 요소는 모양 자리를 함께 적는다."""
    def one(p: boxdiagram.PlacedBox) -> str:
        shape = f", 모양 {fmt_rect(p.shape_rect)}" if p.shape_rect != p.rect else ""
        return f"{p.key}({fmt_rect(p.rect)}{shape})"
    noun = drawing.layout.spec.words.noun
    return [f"{noun} 자리(왼, 위, 폭×높이): " + ", ".join(one(p) for p in drawing.layout.boxes)]


D = TypeVar("D", boxdiagram.Drawing, sequencediagram.Drawing)


def _draw(file_name: str, render: Callable[[], D], check: Callable[[D], Report], out_dir: Optional[str],
          extra_lines: Optional[Callable[[D], list[str]]] = None) -> CallToolResult:
    """render()로 그려 check로 검사하고 저장해 돌려준다. extra_lines(그린 것)는 검사 결과 뒤에 붙이는 줄이다. file_name
    문제는 그림 입력 오류와 함께 모아 알린다."""
    name, problem = _file_name(file_name)
    problems = [problem] if problem else []
    with _drawing:
        try:
            drawing = render()
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
    path, problem = _save(full, out_dir, name)
    if problem:
        return _error("\n".join([problem, "", report.summary(), *extra]))
    shown = _shrink(img)
    lines = [report.summary(), *extra, f"저장한 파일: {path} ({img.width}×{img.height}px)"]
    if shown is not img:
        lines.append(f"돌려준 그림은 긴 변을 {MAX_IMAGE_EDGE}px로 줄였다({shown.width}×{shown.height}px). "
                     "원래 크기는 저장한 파일에 있다.")
    data_b64 = base64.b64encode(full if shown is img else _png(shown)).decode("ascii")
    return CallToolResult(content=[
        TextContent(type="text", text="\n".join(lines)),
        ImageContent(type="image", data=data_b64, mime_type="image/png"),
    ])


# 그림 입력(classes·messages 등)은 모양을 검사하지 않고 받는다 — 파서가 자리 붙은 오류를 한 번에 모아 알린다
def _listed(description: str, item: str = "object") -> WithJsonSchema:
    return WithJsonSchema({"type": "array", "items": {"type": item}, "description": description})


FileName = Annotated[str, Field(description="저장할 파일 이름(확장자 없이). 같은 이름이면 덮어쓴다.")]
OutDir = Annotated[Optional[str], Field(description=f"저장할 폴더. 주지 않으면 서버 작업 폴더 아래 {DEFAULT_DIR}/.")]
Scale = Annotated[float, Field(ge=MIN_SCALE, allow_inf_nan=False, description=f"출력 배율(기본 {SCALE:g}). 보통은 주지 않는다.")]


@mcp.tool(name="draw_class_diagram", description=CLASS_TOOL)
def draw_class_diagram(
        file_name: FileName,
        classes: Annotated[Any, _listed("상자 목록(하나 이상). 필드는 도구 설명에 있다.")],
        relations: Annotated[Any, _listed("관계 목록. 필드는 도구 설명에 있다.")] = None,
        out_dir: OutDir = None,
        scale: Scale = SCALE,
) -> CallToolResult:
    data = {"classes": classes} if relations is None else {"classes": classes, "relations": relations}
    return _draw(file_name, lambda: classdiagram.render(data, scale), classcheck.check, out_dir, _places)


@mcp.tool(name="draw_package_diagram", description=packagediagram.TOOL)
def draw_package_diagram(
        file_name: FileName,
        elements: Annotated[Any, _listed("요소 목록(하나 이상). 필드는 도구 설명에 있다.")],
        relations: Annotated[Any, _listed("관계 목록. 필드는 도구 설명에 있다.")] = None,
        out_dir: OutDir = None,
        scale: Scale = SCALE,
) -> CallToolResult:
    data = {"elements": elements} if relations is None else {"elements": elements, "relations": relations}
    return _draw(file_name, lambda: packagediagram.render(data, scale), boxcheck.check, out_dir, _places)


@mcp.tool(name="draw_deployment_diagram", description=deploymentdiagram.TOOL)
def draw_deployment_diagram(
        file_name: FileName,
        elements: Annotated[Any, _listed("요소 목록(하나 이상). 필드는 도구 설명에 있다.")],
        relations: Annotated[Any, _listed("관계 목록. 필드는 도구 설명에 있다.")] = None,
        out_dir: OutDir = None,
        scale: Scale = SCALE,
) -> CallToolResult:
    data = {"elements": elements} if relations is None else {"elements": elements, "relations": relations}
    return _draw(file_name, lambda: deploymentdiagram.render(data, scale), boxcheck.check, out_dir, _places)


@mcp.tool(name="draw_sequence_diagram", description=SEQUENCE_TOOL)
def draw_sequence_diagram(
        file_name: FileName,
        participants: Annotated[Any, _listed("참여자 목록(하나 이상). 필드는 도구 설명에 있다.")],
        messages: Annotated[Any, _listed("메시지 목록. 필드는 도구 설명에 있다.")] = None,
        frames: Annotated[Any, _listed("프레임 목록. 필드는 도구 설명에 있다.")] = None,
        notes: Annotated[Any, _listed("노트 글자 목록. 그림 아래에 모은다.", "string")] = None,
        out_dir: OutDir = None,
        scale: Scale = SCALE,
) -> CallToolResult:
    given = {"messages": messages, "frames": frames, "notes": notes}
    data = {"participants": participants, **{k: v for k, v in given.items() if v is not None}}
    return _draw(file_name, lambda: sequencediagram.render(data, scale), sequencecheck.check, out_dir)
