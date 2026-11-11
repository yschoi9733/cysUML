# cysUML

An MCP server for document-ready UML diagrams: the AI lays them out, cysUML draws and checks them.

[한국어 안내](#한국어)

Auto-layout tools are quick, but lines often run through boxes and labels, and the result is hard to fix by hand.
cysUML takes the other way round: your AI assistant decides where every box goes, cysUML draws exactly that and
checks the drawing. If a line crosses a box or a label, the check fails and says what to move. The assistant fixes
the layout and draws again until the check passes.

- Class diagrams for now. Sequence diagrams are next.
- PNG output. The fonts are bundled, so every machine draws the same picture, Korean text included.

## Install

You need [uv](https://docs.astral.sh/uv/). This one line downloads and starts the server:

```
uvx --from git+https://github.com/yschoi9733/cysUML cysuml
```

It talks MCP over stdin/stdout, so on its own it just waits for a client. Register it with your MCP client instead.

**Claude Code**

```
claude mcp add cysuml -- uvx --from git+https://github.com/yschoi9733/cysUML cysuml
```

**Other clients** (Claude Desktop, Cursor, …) take the same command in their JSON config:

```json
{
  "mcpServers": {
    "cysuml": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/yschoi9733/cysUML", "cysuml"]
    }
  }
}
```

## Use

Ask your assistant for a class diagram, for example "draw a class diagram of the order domain with cysUML".
The server tells the assistant how to place boxes, so you don't have to.

The tool is `draw_class_diagram`. The assistant sends boxes with their top-left corners and relations with
optional bend points:

```json
{
  "file_name": "order",
  "classes": [
    {"name": "Order", "left": 0, "top": 0, "attributes": ["-id: long"]},
    {"name": "Customer", "left": 200, "top": 0}
  ],
  "relations": [
    {"kind": "association", "from": "Order", "to": "Customer", "name": "places", "to_multiplicity": "1"}
  ]
}
```

It gets back the check result, the size and place of every box as drawn, the saved file path, and the picture.

- **Saved to** `out_dir`, or `diagrams/` under the server's working folder when `out_dir` is not given. The same
  `file_name` overwrites the file. Some clients start servers in a folder you can't write to (such as `/`); the tool
  then answers with an error, and the assistant should pass an `out_dir`.
- **Returned picture** is shrunk to 1568 px on its long side when it is bigger. The saved file keeps its full size.
- **Fails** when boxes overlap, a line runs through a box, a label or another line's arrowhead, or labels overlap.
  Crossing lines and the picture size are reported but don't fail.

The full input format is in the tool description, which your client hands to the assistant.

## Develop

```
uv sync
uv run pytest
```

To try your working copy in Claude Code, register it under another name:

```
claude mcp add cysuml-dev -- uv run --directory /path/to/cysUML cysuml
```

The bundled fonts are Liberation Sans and Noto Sans KR, both under the SIL Open Font License
(see [`src/cysuml/fonts`](src/cysuml/fonts)).

---

## 한국어

AI가 배치하고 도구가 그리는, 문서용 UML 그림 MCP 서버다.

자동 배치 도구는 빠르지만 선이 상자나 글자를 가로지르기 쉽고, 손으로 다듬기도 어렵다. cysUML은 반대로 간다. AI 어시스턴트가
상자 자리를 정하면 cysUML은 그대로 그리고 그림을 검사한다. 선이 상자나 글자를 지나면 불합격이고, 무엇을 옮길지 알려 준다.
어시스턴트는 배치를 고쳐 합격할 때까지 다시 그린다.

- 지금은 클래스도를 그린다. 교류도가 다음이다.
- PNG로 낸다. 글꼴을 함께 넣어 어느 컴퓨터에서든 같은 그림이 나오고, 한글도 그린다.

### 설치

[uv](https://docs.astral.sh/uv/)가 있어야 한다. 아래 한 줄이 서버를 받아 띄운다:

```
uvx --from git+https://github.com/yschoi9733/cysUML cysuml
```

표준 입출력으로 MCP를 주고받으므로 혼자 띄우면 클라이언트를 기다리기만 한다. 쓰려면 MCP 클라이언트에 등록한다.

- **Claude Code:** `claude mcp add cysuml -- uvx --from git+https://github.com/yschoi9733/cysUML cysuml`
- **다른 클라이언트:** 위 영어 안내의 JSON 설정에 같은 명령을 넣는다.

### 쓰기

어시스턴트에게 "cysUML로 주문 도메인 클래스도를 그려 줘"처럼 부탁한다. 상자 놓는 요령은 서버가 어시스턴트에게 알려 준다.

- 도구는 `draw_class_diagram`이다. 입력 형식 전체는 도구 설명에 있어 클라이언트가 어시스턴트에게 넘긴다.
- 결과로 검사 결과, 상자마다 그린 자리와 크기, 저장한 파일 경로, 그림을 돌려준다.
- 그림은 `out_dir`에, 없으면 서버 작업 폴더 아래 `diagrams/`에 저장한다. 같은 `file_name`이면 덮어쓴다. 쓸 수 없는 폴더(`/` 등)에서
  서버를 띄우는 클라이언트도 있는데, 그때는 도구가 오류로 알리므로 `out_dir`을 주면 된다.
- 돌려주는 그림은 긴 변이 1568px를 넘으면 그 길이로 줄인다. 저장한 파일은 원래 크기다.
- 상자끼리 겹치거나, 선이 상자·글자·다른 선의 화살촉을 지나거나, 글자끼리 겹치면 불합격이다. 선끼리 엇갈린 곳과 그림 크기는
  알려 주기만 하고 불합격이 아니다.

### 개발

`uv sync`로 준비하고 `uv run pytest`로 시험한다. 작업 중인 코드를 Claude Code에서 써 보려면 다른 이름으로 등록한다:
`claude mcp add cysuml-dev -- uv run --directory /path/to/cysUML cysuml`.
