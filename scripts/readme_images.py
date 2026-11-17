"""README 그림을 docs/images/에 다시 그린다. 실행: uv run python scripts/readme_images.py

- README의 JSON 예시 가운데 file_name이 있는 것은 README에서 읽어, 그 예시가 든 절의 "The tool is `draw_…`" 도구로 그린다.
- 맨 위 전후 그림(BEFORE_AFTER)은 docs/images/의 입력 파일(<이름>.cysuml.json)로 다시 그린다.
- 예시는 검사에 합격해야 하고, 전후 그림은 BEFORE_AFTER대로 불합격·합격해야 한다. 어긋나면 docs/images/를 그대로 두고 실패로 끝낸다.

README는 그림을 main의 절대 주소로 가리키고, 앞으로 낼 PyPI 판도 그 주소를 본다. 그림 파일 이름(전후 그림 이름과 README
예시의 file_name)을 바꾸거나 지우면 이미 낸 판의 그림이 깨지므로 바꾸지 않는다.
"""
import json
import re
import shutil
import tempfile
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
            example = json.loads(block)
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
        record = json.loads((IMAGES / f"{name}.cysuml.json").read_text(encoding="utf-8"))
        if record.get("file_name") != name or "tool" not in record:
            raise SystemExit(f"docs/images/{name}.cysuml.json에 tool이 없거나 file_name이 {name}이 아니다")
        found.append((record.pop("tool"), record))
    return found


def main() -> None:
    jobs = [*readme_examples(), *before_after()]
    names = [args["file_name"] for _, args in jobs]
    if len(set(names)) < len(names):  # 한 폴더에 그리므로 겹치면 뒤 그림이 앞 그림을 덮는다
        raise SystemExit(f"README 예시와 전후 그림의 file_name이 겹친다: {sorted({n for n in names if names.count(n) > 1})}")

    async def go(drawn: Path) -> list[str]:
        # 멈출 일은 모아 두었다가 클라이언트를 닫은 뒤 알린다 — 그 안에서 멈추면 anyio가 예외 묶음으로 감싸 메시지가 묻힌다
        problems = []
        async with Client(server.mcp) as c:
            for tool, args in jobs:
                name = args["file_name"]
                result = await c.call_tool(tool, {**args, "out_dir": str(drawn)})
                if result.is_error:
                    problems.append(f"{name}: {result.content[0].text}")
                    continue
                verdict = result.content[0].text.splitlines()[0]
                print(f"{name}: {verdict}")
                if verdict.startswith("합격") != BEFORE_AFTER.get(name, True):
                    problems.append(f"{name}: README 설명과 검사 결과가 다르다")
        return problems

    with tempfile.TemporaryDirectory() as tmp:
        problems = anyio.run(go, Path(tmp))
        if problems:
            raise SystemExit("\n".join([*problems, "docs/images/는 그대로 두었다"]))
        for f in Path(tmp).iterdir():
            shutil.copyfile(f, IMAGES / f.name)


if __name__ == "__main__":
    main()
