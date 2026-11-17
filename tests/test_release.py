import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))


def project_field(key):
    # tomllib(Python 3.11부터)으로 읽지 않는다 — publish 워크플로가 3.10에서도 테스트를 돌린다
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    table = re.search(r"^\[project\][ \t]*\n(.*?)(?=^\[|\Z)", text, re.M | re.S)
    found = table and re.search(rf"""^{key}\s*=\s*["']([^"']+)["']""", table.group(1), re.M)
    assert found, f"pyproject.toml의 [project]에서 {key} 값을 읽지 못했다 — 이 테스트의 읽는 법을 고친다"
    return found.group(1)


def test_server_json_versions_follow_pyproject():
    version = project_field("version")
    assert SERVER["version"] == version, "server.json의 version을 pyproject.toml 버전과 같게 올린다"
    assert [p["version"] for p in SERVER["packages"]] == [version], "server.json packages의 version도 같게 올린다"


def test_server_json_names_the_pypi_package():
    assert [(p["registryType"], p["identifier"]) for p in SERVER["packages"]] == [("pypi", project_field("name"))]


def test_server_json_description_fits_the_registry_limit():
    # server.json 스키마(2025-12-11)의 description 최대 길이 — 여기서 못 잡으면 태그를 단 뒤 build job의 레지스트리 검사에서야 걸린다
    assert len(SERVER["description"]) <= 100


def test_readme_carries_the_registry_name():
    # 레지스트리는 올리는 버전의 PyPI README에서 이 줄을 찾는다. 서버 이름 바로 뒤는 공백·줄바꿈·주석 닫기여야 한다
    pattern = rf"mcp-name: {re.escape(SERVER['name'])}(?=\s|-->|<|$)"
    assert re.search(pattern, (ROOT / "README.md").read_text(encoding="utf-8")), \
        f"README에 mcp-name: {SERVER['name']} 줄이 있어야 MCP 레지스트리에 올릴 수 있다"
