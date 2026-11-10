"""`cysuml` 명령. 이름만 잡아 두었고 MCP 서버는 아직 없다."""
import sys


def main() -> int:
    print("cysuml: the MCP server is not implemented yet.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
