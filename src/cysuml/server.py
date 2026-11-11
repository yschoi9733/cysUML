"""MCP 서버: 클래스도를 그리는 도구를 stdio로 내놓는다.

도구는 그린 PNG를 파일로 저장하고, 검사 결과 글과 그림을 함께 돌려준다. 입력이 틀렸거나, 그림이 너무 커서 PNG로 못
그리거나, 저장할 폴더에 쓸 수 없으면 저장하지 않고 오류 결과(isError)로 돌려준다 — AI가 읽고 고칠 수 있게 예외 대신 결과로 낸다.
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
from typing import Annotated, Any, Optional

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, ImageContent, TextContent
from PIL import Image
from pydantic import Field, WithJsonSchema

from . import classcheck, classdiagram
from .canvas import MIN_SCALE, SCALE

MAX_IMAGE_EDGE = 1568  # 돌려주는 그림의 긴 변 상한(px). Claude는 이보다 큰 그림을 어차피 줄여서 본다
DEFAULT_DIR = "diagrams"
MAX_NAME_BYTES = 200  # 파일 이름(확장자 빼고) UTF-8 길이 상한. 파일 시스템 한도는 보통 255바이트
NAME_FORBIDDEN = set('/\\:*?"<>|')

KIND_NAMES = {  # 불합격 종류(classcheck.KINDS)를 도구 설명에 쓰는 말
    "box_overlap": "상자끼리 겹치거나 붙음",
    "line_through_box": "선이 양 끝이 아닌 상자를 지나감",
    "line_along_own_box": "선이 제 끝 상자 변에 붙어 감",
    "head_near_own_box": "선 끝 모양이 그 선의 다른 끝 상자 변에 붙음",
    "head_under_own_box": "선 끝 모양이 제 상자에 가려짐",
    "line_overlap": "선끼리 포개지거나 선이 왔던 길을 되짚음",
    "line_through_head": "선이 다른 선 끝 모양(삼각형·마름모·화살촉)에 닿음",
    "head_overlap": "선 끝 모양끼리 겹침",
    "line_through_text": "선이 선 글자(관계 이름·다중도)를 지나감",
    "text_on_box": "선 글자가 상자에 겹침",
    "text_overlap": "선 글자끼리 겹침",
}

FLOW = """그리는 흐름 — 검사에 합격할 때까지 되풀이한다:
1. 상자 자리(left·top)와, 필요하면 관계선의 꺾는 점(via)을 정해 그린다.
2. 돌려받은 검사 결과와 그림을 본다. 불합격 항목마다 걸린 요소, 자리(논리 좌표 왼, 위, 폭×높이), 고치는 법이 붙는다. \
고치는 법은 종류마다 다르니(상자를 옮긴다, 꺾는 점을 고친다, 두 상자를 떼어 놓는다 등) 항목에 적힌 대로 고친다.
3. 고친 입력을 같은 file_name으로 다시 그린다(파일을 덮어쓴다).
선끼리 엇갈린 곳과 그림 크기는 알림이라 불합격이 아니다. 다만 엇갈림은 적을수록 읽기 좋다."""

TIPS = """배치 요령:
- 연결이 가장 많은 클래스를 가운데에 둔다.
- 상속·실체화는 부모를 위에, 자식들을 그 아래 한 줄에 둔다.
- 엇갈림이나 불합격이 나오면 먼저 상자 순서와 자리를 바꾸고, 그래도 안 되면 꺾는 점(via)을 준다.
- 상자 사이는 관계 이름·다중도 글자가 들어갈 만큼 띄운다. 가로 80px·세로 60px쯤에서 시작하고, 글자가 길면 더 띄운다.
- 상자 크기는 도구가 글자에 맞춰 늘린다(폭은 90px 이상). 그린 크기는 결과의 "상자 자리"에서 보고 다음 배치에 쓴다."""

INSTRUCTIONS = f"""cysUML은 문서에 바로 넣을 UML 그림을 PNG로 그린다. 배치는 부르는 AI가 하고, cysUML은 받은 좌표대로 그린 뒤 \
선이 상자나 글자를 지나는지 검사해 그림과 함께 돌려준다. 클래스도는 draw_class_diagram으로 그린다.

{FLOW}

{TIPS}"""

CLASS_TOOL = f"""클래스도를 그려 PNG 파일로 저장하고, 검사 결과와 그림을 함께 돌려준다. 상자는 준 왼쪽 위(left·top) 그대로, \
관계선은 준 꺾는 점(via)을 따라 그리고, 상자 크기·선 끝·선 글자 자리만 도구가 정한다. 좌표는 px이고 y는 아래로 커진다.

입력
- classes: 상자 목록(하나 이상).
  - name(필수): 관계가 이 이름으로 상자를 가리키므로 서로 달라야 한다.
  - left·top(필수): 상자 왼쪽 위.
  - kind: "class"(기본)·"abstract"·"interface"·"enum".
  - stereotype: «» 없이 이름만.
  - attributes·operations: 한 줄 문자열(그대로 쓴다)이나 객체. 속성 객체는 name(필수)·type·default·visibility(기본 "-")·static, \
연산 객체는 name(필수)·params(문자열 목록)·returns·visibility(기본 "+")·static. visibility는 "+"·"-"·"#"·"~"·""(안 씀)이고, \
static이 true면 밑줄을 긋는다.
  - literals: 열거 값 목록(kind가 "enum"일 때만).
  - width·height: 최소 크기. 글자가 더 길면 그만큼 늘어난다(폭 기본 90).
- relations: 관계 목록(없어도 된다).
  - kind(필수): "association"·"aggregation"·"composition"·"generalization"·"realization"·"dependency".
  - from·to(필수): 상자 이름. 상속·실체화·의존은 from이 자식·구현하는 쪽·의존하는 쪽이고 삼각형·화살촉이 to 쪽에 붙는다. \
집합·합성의 마름모는 from 쪽에 붙는다.
  - name: 관계 이름.
  - from_multiplicity·to_multiplicity·navigable: 연관·집합·합성만 쓴다. navigable은 화살촉을 둘 쪽 "to"(기본)·"from"·"both"·"none"이다\
(집합·합성은 "to"·"none"만).
  - via: 꺾는 점 [[x, y], …]. 선은 상자 가운데에서 첫 꺾는 점(없으면 상대 상자 가운데)으로 가는 선이 상자 변과 만나는 곳에서 \
시작한다. 자기 자신으로 가는 관계는 꺾는 점이 둘 이상 있어야 한다.
- file_name: 저장할 파일 이름(확장자 없이). 같은 이름이면 덮어쓴다.
- out_dir: 저장할 폴더. 주지 않으면 서버 작업 폴더 아래 {DEFAULT_DIR}/이고, 상대 경로도 서버 작업 폴더 기준이다.
- scale: 출력 배율(기본 {SCALE:g}, {MIN_SCALE:g} 이상). 보통은 주지 않는다.

결과
- 글: 검사 결과, 상자마다 그린 자리와 크기, 저장한 파일 경로와 픽셀 크기.
- 그림: 저장한 PNG. 긴 변이 {MAX_IMAGE_EDGE}px를 넘으면 그 길이로 줄여 돌려준다(저장한 파일은 줄이지 않는다).
- classes·relations·file_name이 틀리면 그리지 않고 틀린 곳을 classes[0].left 꼴 자리와 함께 모두 모아 오류로 돌려준다. \
그림이 너무 커서 PNG로 그릴 수 없거나 저장할 폴더에 쓸 수 없을 때도 오류로 돌려준다.

불합격(선이 상자나 글자를 지나는 등 문서에 넣을 수 없는 그림) {len(KIND_NAMES)}가지: {", ".join(KIND_NAMES.values())}.

{FLOW}

{TIPS}"""

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


def _boxes(drawing: classdiagram.Drawing) -> str:
    return "상자 자리(왼, 위, 폭×높이): " + ", ".join(f"{p.box.name}({classdiagram.fmt_rect(p.rect)})"
                                               for p in drawing.layout.boxes)


@mcp.tool(name="draw_class_diagram", description=CLASS_TOOL)
def draw_class_diagram(
        file_name: Annotated[str, Field(description="저장할 파일 이름(확장자 없이). 같은 이름이면 덮어쓴다.")],
        classes: Annotated[Any, WithJsonSchema(
            {"type": "array", "items": {"type": "object"}, "description": "상자 목록(하나 이상). 필드는 도구 설명에 있다."})],
        relations: Annotated[Any, WithJsonSchema(
            {"type": "array", "items": {"type": "object"}, "description": "관계 목록. 필드는 도구 설명에 있다."})] = None,
        out_dir: Annotated[Optional[str], Field(
            description=f"저장할 폴더. 주지 않으면 서버 작업 폴더 아래 {DEFAULT_DIR}/.")] = None,
        scale: Annotated[float, Field(ge=MIN_SCALE, allow_inf_nan=False,
                                      description=f"출력 배율(기본 {SCALE:g}). 보통은 주지 않는다.")] = SCALE,
) -> CallToolResult:
    # classes·relations는 모양을 검사하지 않고 받는다 — 파서가 자리 붙은 오류를 한 번에 모아 알린다
    name, problem = _file_name(file_name)
    problems = [problem] if problem else []
    data = {"classes": classes} if relations is None else {"classes": classes, "relations": relations}
    with _drawing:
        try:
            drawing = classdiagram.render(data, scale)
        except classdiagram.InputError as e:
            problems += e.problems
        if problems:
            return _error(f"입력 오류 — {len(problems)}건\n" + "\n".join(f"- {p}" for p in problems))
        report = classcheck.check(drawing)
        if report.png_size is None:
            return _error("그림이 너무 커서 PNG를 그리지 않았다(파일도 저장하지 않았다).\n"
                          + report.summary() + "\n" + _boxes(drawing))
        img = drawing.canvas.to_image()
    full = _png(img)
    path, problem = _save(full, out_dir, name)
    if problem:
        return _error(problem + "\n\n" + report.summary() + "\n" + _boxes(drawing))
    shown = _shrink(img)
    lines = [report.summary(), _boxes(drawing), f"저장한 파일: {path} ({img.width}×{img.height}px)"]
    if shown is not img:
        lines.append(f"돌려준 그림은 긴 변을 {MAX_IMAGE_EDGE}px로 줄였다({shown.width}×{shown.height}px). "
                     "원래 크기는 저장한 파일에 있다.")
    data_b64 = base64.b64encode(full if shown is img else _png(shown)).decode("ascii")
    return CallToolResult(content=[
        TextContent(type="text", text="\n".join(lines)),
        ImageContent(type="image", data=data_b64, mime_type="image/png"),
    ])
