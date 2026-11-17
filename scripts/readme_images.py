"""README 그림을 docs/images/에 다시 그린다. 실행: uv run python scripts/readme_images.py

- README의 JSON 예시 가운데 file_name이 있는 것은 README에서 읽어, 그 예시가 든 절의 "The tool is `draw_…`" 도구로 그린다.
- 맨 위 전후 그림(BEFORE_AFTER)은 docs/images/의 입력 파일(<이름>.cysuml.json)로 다시 그린다.
- 예시는 검사에 합격해야 하고, 전후 그림은 BEFORE_AFTER대로 불합격·합격해야 한다. 어긋나면 docs/images/를 그대로 두고 실패로 끝낸다.
- 첫 배치(first-try·first-try-ko)에서 상품 밑에 가려지는 고객→결제 선에는 곧은 선 위에 꺾는 점을 둔다. 관계 이름은 가장 긴
  토막의 가운데에 앉으므로, 상품 양 변과 안쪽에 점을 둬 고객–상품 사이 보이는 토막을 가장 길게 만든다. 지우면 이름이 상품 상자에
  붙는다. 그래서 그 검사 결과의 고치는 법은 "꺾는 점(via)을 고쳐"로 나온다.

README는 그림을 main의 절대 주소로 가리키고, 앞으로 낼 PyPI 판도 그 주소를 본다. 그림 파일 이름(전후 그림 이름과 README
예시의 file_name)을 바꾸거나 지우면 이미 낸 판의 그림이 깨지므로 바꾸지 않는다.
"""
import json
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path

import anyio
from mcp import Client

from cysuml import server

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
IMAGES = ROOT / "docs" / "images"
BEFORE_AFTER = {"first-try": False, "fixed": True, "first-try-ko": False, "fixed-ko": True}  # 이름 → 검사에 합격하는지


def readme_examples() -> list[tuple[str, dict]]:
    """README 영어 부분의 (도구, 예시) 목록."""
    english = README.read_text(encoding="utf-8").split("\n## 한국어\n", 1)[0]
    found = []
    for section in re.split(r"^##+ ", english, flags=re.M)[1:]:
        for block in re.findall(r"```json\n(.*?)```", section, re.S):
            try:
                example = json.loads(block)
            except ValueError as e:
                raise SystemExit(f"README '{section.splitlines()[0]}' 절의 JSON 예시를 읽지 못했다: {e}")
            if "file_name" not in example:
                continue
            tool = re.search(r"The tool is `(draw_\w+)`", section)
            if tool is None:
                raise SystemExit(f"README '{section.splitlines()[0]}' 절에 \"The tool is `draw_…`\" 문장이 없어 "
                                 f"예시 {example['file_name']}을 그릴 도구를 모른다")
            found.append((tool.group(1), example))
    return found


def before_after() -> list[tuple[str, dict]]:
    """전후 그림의 (도구, 입력) 목록 — 저장된 입력 파일에서 도구 이름을 떼어 낸다."""
    found = []
    for name in BEFORE_AFTER:
        try:
            record = json.loads((IMAGES / f"{name}.cysuml.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise SystemExit(f"docs/images/{name}.cysuml.json을 읽지 못했다: {e}")
        if record.get("file_name") != name or "tool" not in record:
            raise SystemExit(f"docs/images/{name}.cysuml.json에 tool이 없거나 file_name이 {name}이 아니다")
        found.append((record.pop("tool"), record))
    return found


def main() -> None:
    jobs = [*readme_examples(), *before_after()]
    # 한 폴더에 그리므로 겹치면 뒤 그림이 앞 그림을 덮는다. macOS 기본 파일 시스템은 대소문자도 유니코드 정규화(NFC·NFD)도 가리지
    # 않아, 둘을 맞춘 뒤 견준다
    names = [unicodedata.normalize("NFC", args["file_name"]).casefold() for _, args in jobs]
    if len(set(names)) < len(names):
        raise SystemExit(f"README 예시와 전후 그림의 file_name이 겹친다: {sorted({n for n in names if names.count(n) > 1})}")

    async def go(drawn: Path) -> list[str]:
        # 멈출 일은 모아 두었다가 클라이언트를 닫은 뒤 알린다 — 그 안에서 멈추면 anyio가 예외 묶음으로 감싸 메시지가 묻힌다
        problems = []
        async with Client(server.mcp) as c:
            for tool, args in jobs:
                name = args["file_name"]
                try:
                    result = await c.call_tool(tool, {**args, "out_dir": str(drawn)})
                except Exception as e:  # 도구가 오류 결과가 아니라 예외를 내도(인자 검증 등) 모아 두었다가 알린다
                    problems.append(f"{name}: {type(e).__name__}: {e}")
                    continue
                if result.is_error:
                    problems.append(f"{name}: {result.content[0].text}")
                    continue
                verdict = result.content[0].text.splitlines()[0]
                print(f"{name}: {verdict}")
                if name not in BEFORE_AFTER and not verdict.startswith("합격"):
                    problems.append(f"{name}: README 예시가 검사에 불합격했다")
                elif name in BEFORE_AFTER and verdict.startswith("합격") != BEFORE_AFTER[name]:
                    problems.append(f"{name}: 전후 그림이 README 설명과 다르게 {'합격' if verdict.startswith('합격') else '불합격'}했다")
        return problems

    with tempfile.TemporaryDirectory() as tmp:
        problems = anyio.run(go, Path(tmp))
        if problems:
            raise SystemExit("\n".join([*problems, "docs/images/는 그대로 두었다"]))
        for f in Path(tmp).iterdir():
            shutil.copyfile(f, IMAGES / f.name)


if __name__ == "__main__":
    main()
