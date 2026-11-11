"""`cysuml` 명령: MCP 서버를 stdio로 띄운다."""
import sys

from cysuml.server import mcp


def main() -> int:
    mcp.run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
