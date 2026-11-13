# cysUML

An MCP server for document-ready UML diagrams: the AI lays them out, cysUML draws and checks them.

[한국어 안내](#한국어)

Auto-layout tools are quick, but lines often run through boxes and labels, and the result is hard to fix by hand.
cysUML takes the other way round: your AI assistant decides where every box goes, cysUML draws exactly that and
checks the drawing. If a line crosses a box or a label, the check fails and says what to move. The assistant fixes
the layout and draws again until the check passes.

- Several kinds of UML diagram; the list is under [Use](#use). Sequence diagrams are laid out by cysUML from the order
  of participants and messages, and checked the same way.
- PNG output. The fonts are bundled, so every machine draws the same picture, Korean text included.

## Install

You need [uv](https://docs.astral.sh/uv/). This one line downloads cysUML from [PyPI](https://pypi.org/project/cysuml/)
and starts the server:

```
uvx cysuml
```

It talks MCP over stdin/stdout, so on its own it just waits for a client. Register it with your MCP client instead.

**Claude Code**

```
claude mcp add cysuml -- uvx cysuml
```

**Other clients** (Claude Desktop, Cursor, …) take the same command in their JSON config:

```json
{
  "mcpServers": {
    "cysuml": {
      "command": "uvx",
      "args": ["cysuml"]
    }
  }
}
```

**Versions.** `uvx cysuml` runs the newest release: each time the client starts the server, uv asks PyPI and reuses
the answer for up to ten minutes. If you installed it with `uv tool install cysuml`, uvx runs that copy instead;
update it with `uv tool upgrade cysuml`. To stay on one version, put it after the name: `uvx cysuml@0.1.0` (in JSON,
`"args": ["cysuml@0.1.0"]`). The releases are listed in the [release history](https://pypi.org/project/cysuml/#history).

## Use

Ask your assistant for a diagram, for example "draw a class diagram of the order domain with cysUML" or "draw the
checkout flow as a sequence diagram with cysUML". The server tells the assistant how to lay it out, so you don't
have to.

### Class diagrams

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
The check **fails** when boxes overlap, a line runs through a box, a label or another line's arrowhead, or labels
overlap. Crossing lines and the picture size are reported but don't fail. Inheritance lines from several children to
one parent may join into one trunk that shares a single triangle (realization lines too, but not mixed with
inheritance); the tool description tells the assistant how to give the bend points for it.

### Package diagrams

The tool is `draw_package_diagram`. It draws packages and the dependencies between them, with classes and packages
inside packages, and takes components, artifacts and nodes in the same picture. Every element has a `kind`. An element
names the one it sits in with `in`, and the outer element grows right and down to cover it:

```json
{
  "file_name": "packages",
  "elements": [
    {"kind": "package", "name": "web", "left": 0, "top": 0},
    {"kind": "class", "name": "OrderController", "in": "web", "left": 20, "top": 44},
    {"kind": "package", "name": "domain", "left": 0, "top": 180},
    {"kind": "class", "name": "Order", "in": "domain", "left": 20, "top": 224},
    {"kind": "class", "name": "Customer", "in": "domain", "left": 200, "top": 224}
  ],
  "relations": [
    {"kind": "dependency", "from": "web", "to": "domain", "stereotype": "use"},
    {"kind": "association", "from": "Order", "to": "Customer", "name": "places", "to_multiplicity": "1"}
  ]
}
```

It gets back the same things as the class diagram tool, with the place of every element (and, for a package, the
point its lines aim at, since that is not the middle of the package). Besides the class diagram
checks, the check fails when an element inside another sits too close to its edge or name tab, or a line runs along
the edge of a package it starts or ends in, or through a package's name tab.

### Component diagrams

The tool is `draw_component_diagram`. It draws components with the interfaces they provide, the artifacts that
implement them, and the classes that realize them. It takes every element of the package diagram tool, plus
`lollipop`: a provided interface drawn as a small circle with its name outside (`name_side` puts the name below,
above, left or right of the circle). The providing component joins the circle with an `association`, drawn without
an arrowhead in this tool unless `navigable` is given, and each user points at the circle with a `dependency`:

```json
{
  "file_name": "components",
  "elements": [
    {"kind": "package", "name": "web", "left": 0, "top": 0},
    {"kind": "component", "name": "OrderController", "in": "web", "left": 20, "top": 44},
    {"kind": "component", "name": "AdminController", "in": "web", "left": 220, "top": 44},
    {"kind": "package", "name": "service", "left": 0, "top": 220},
    {"kind": "component", "name": "OrderService", "in": "service", "left": 110, "top": 324},
    {"kind": "lollipop", "name": "OrderApi", "in": "service", "left": 70, "top": 264, "name_side": "left"},
    {"kind": "artifact", "name": "order-service.jar", "left": 400, "top": 324}
  ],
  "relations": [
    {"kind": "association", "from": "OrderService", "to": "OrderApi"},
    {"kind": "dependency", "from": "OrderController", "to": "OrderApi"},
    {"kind": "dependency", "from": "AdminController", "to": "OrderApi"},
    {"kind": "dependency", "from": "order-service.jar", "to": "OrderService", "stereotype": "manifest"}
  ]
}
```

It gets back the same things as the package diagram tool, and for each circle the place of the circle alone next to
the place of the circle with its name. The checks are the same: a line through a circle or its name fails.

### Deployment diagrams

The tool is `draw_deployment_diagram`. It shows which computers (nodes) the software runs on: components and
artifacts sit inside nodes with `in`, and a node can sit inside another node. It takes the same elements as the package
diagram tool. A communication path between nodes is an `association` with the protocol as its `name`. This tool draws
every association without an arrowhead (between classes too) unless `navigable` says otherwise. A «deploy» arrow from
an element outside a node is a `dependency` with `"stereotype": "deploy"`:

```json
{
  "file_name": "deployment",
  "elements": [
    {"kind": "node", "name": "PC", "stereotype": "device", "left": 0, "top": 0, "height": 220},
    {"kind": "component", "name": "Browser", "in": "PC", "left": 20, "top": 66},
    {"kind": "node", "name": "App Server", "stereotype": "device", "left": 240, "top": 0, "height": 220},
    {"kind": "node", "name": "Tomcat", "stereotype": "executionEnvironment", "in": "App Server", "left": 260, "top": 66},
    {"kind": "component", "name": "OrderService", "in": "Tomcat", "left": 280, "top": 132},
    {"kind": "node", "name": "DB Server", "stereotype": "device", "left": 620, "top": 0, "height": 220},
    {"kind": "artifact", "name": "orders.db", "in": "DB Server", "left": 640, "top": 66},
    {"kind": "artifact", "name": "order.war", "left": 310, "top": 280}
  ],
  "relations": [
    {"kind": "association", "from": "PC", "to": "App Server", "name": "HTTPS"},
    {"kind": "association", "from": "App Server", "to": "DB Server", "name": "JDBC"},
    {"kind": "dependency", "from": "order.war", "to": "Tomcat", "stereotype": "deploy"}
  ]
}
```

It gets back the same things as the package diagram tool, and the check fails in the same cases, such as a
communication path running through a node it does not connect or through an element inside one.

### Use case diagrams

The tool is `draw_use_case_diagram`. It draws actors, use cases and the system boundary, joined by associations,
«include» and «extend» dependencies, and generalizations. Use cases sit inside the system boundary with `in`. Actors
stand outside it and write their name beside the figure, on the side `name_side` gives:

```json
{
  "file_name": "use-cases",
  "elements": [
    {"kind": "system", "id": "shop", "name": "Online shop", "left": 160, "top": 0},
    {"kind": "use_case", "name": "Browse items", "in": "shop", "left": 200, "top": 50},
    {"kind": "use_case", "name": "Place order", "in": "shop", "left": 200, "top": 150},
    {"kind": "use_case", "name": "Pay", "in": "shop", "left": 420, "top": 150},
    {"kind": "actor", "name": "Customer", "left": 0, "top": 130, "name_side": "left"},
    {"kind": "actor", "name": "Bank", "left": 660, "top": 157, "name_side": "right"}
  ],
  "relations": [
    {"kind": "association", "from": "Customer", "to": "Browse items"},
    {"kind": "association", "from": "Customer", "to": "Place order"},
    {"kind": "dependency", "from": "Place order", "to": "Pay", "stereotype": "include"},
    {"kind": "association", "from": "Pay", "to": "Bank"}
  ]
}
```

It gets back the same things as the package diagram tool. An actor's place covers the figure and its name, and the
figure's own place comes after it. The check is the same as for package diagrams, and it also fails when a line runs
through an actor's name or the name at the top of the system boundary. Generalization lines to one parent may share
one trunk, as inheritance lines do in class diagrams.

### State diagrams

The tool is `draw_state_diagram`. It draws start and end points, states and choice diamonds joined by transitions. A
state lists its `entry /`, `do /` and `exit /` lines in `actions`, written as given, and can hold other states with
`in`. Start and end points and choices have no name, so they get an `id` for transitions to point to. The transition
`name` is written as given too, brackets and slash included:

```json
{
  "file_name": "order-states",
  "elements": [
    {"kind": "initial", "id": "start", "left": 85, "top": 0},
    {"kind": "state", "name": "Waiting", "left": 25, "top": 60, "width": 140},
    {"kind": "state", "name": "Checking", "left": 25, "top": 180, "width": 140,
     "actions": ["entry / reserve stock", "do / wait for payment"]},
    {"kind": "final", "id": "end", "left": 83, "top": 340}
  ],
  "relations": [
    {"from": "start", "to": "Waiting"},
    {"from": "Waiting", "to": "Checking", "name": "order [in stock] / accept"},
    {"from": "Waiting", "to": "Waiting", "name": "tick", "via": [[190, 68], [190, 92]]},
    {"from": "Checking", "to": "end", "name": "paid"}
  ]
}
```

It gets back the same things as the package diagram tool. The check also fails when a line runs through the name and
actions of a state it starts or ends in, or a label sits on them.

### Activity diagrams

The tool is `draw_activity_diagram`. It draws start and end points, actions, and decision and merge diamonds joined
by flows. The guard of a flow out of a decision goes in its `name`, brackets included:

```json
{
  "file_name": "order-flow",
  "elements": [
    {"kind": "initial", "id": "start", "left": 140, "top": 0},
    {"kind": "action", "name": "Take order", "left": 95, "top": 60, "width": 110},
    {"kind": "decision", "id": "stock?", "left": 135, "top": 150},
    {"kind": "action", "name": "Ship", "left": 0, "top": 230},
    {"kind": "action", "name": "Restock", "left": 200, "top": 230},
    {"kind": "merge", "id": "done?", "left": 135, "top": 320},
    {"kind": "final", "id": "end", "left": 138, "top": 400}
  ],
  "relations": [
    {"from": "start", "to": "Take order"},
    {"from": "Take order", "to": "stock?"},
    {"from": "stock?", "to": "Ship", "name": "[in stock]", "via": [[45, 165]]},
    {"from": "stock?", "to": "Restock", "name": "[out of stock]", "via": [[245, 165]]},
    {"from": "Ship", "to": "done?", "via": [[45, 335]]},
    {"from": "Restock", "to": "done?", "via": [[245, 335]]},
    {"from": "done?", "to": "end"}
  ]
}
```

It gets back the same things as the package diagram tool, and checks the same way.

### Sequence diagrams

The tool is `draw_sequence_diagram`. The assistant sends no coordinates: only the participants, the messages in
order, frames (`loop`, `opt`, `alt`) that cover a range of messages, and `ref` boxes placed before a message.
cysUML spaces the lifelines to fit the text and draws the activation bars:

```json
{
  "file_name": "checkout",
  "participants": [{"name": "Customer", "kind": "actor"}, {"name": "Shop"}, {"name": "Payment"}],
  "messages": [
    {"from": "Customer", "to": "Shop", "name": "order()"},
    {"from": "Shop", "to": "Payment", "name": "pay(amount)"},
    {"from": "Payment", "to": "Shop", "kind": "reply", "name": "receipt"},
    {"from": "Shop", "to": "Customer", "kind": "reply"}
  ],
  "frames": [{"kind": "opt", "first": 1, "last": 2, "condition": "paid by card"}]
}
```

It gets back the check result, the saved file path, and the picture. As cysUML does the layout, a failed check is a
cysUML bug. Each finding still says what to change in the input to get around it: the order of participants or
messages, the messages a frame covers, shorter text, or splitting the diagram.

### All tools

- **Saved to** `out_dir`, or `diagrams/` under the server's working folder when `out_dir` is not given. The same
  `file_name` overwrites the file. Some clients start servers in a folder you can't write to (such as `/`); the tool
  then answers with an error, and the assistant should pass an `out_dir`.
- **Returned picture** is shrunk to 1568 px on its long side when it is bigger. The saved file keeps its full size.

The full input format is in the tool descriptions, which your client hands to the assistant.

## Develop

```
uv sync
uv run pytest
```

To try your working copy in Claude Code, register it under another name:

```
claude mcp add cysuml-dev -- uv run --directory /path/to/cysUML cysuml
```

To try the latest `main` before it is released, use `uvx --from git+https://github.com/yschoi9733/cysUML cysuml`.

## License

cysUML is under the [MIT License](https://github.com/yschoi9733/cysUML/blob/main/LICENSE). The bundled fonts are
Liberation Sans and Noto Sans KR, both under the SIL Open Font License 1.1 (see
[`LiberationSans-LICENSE.txt`](https://github.com/yschoi9733/cysUML/blob/main/src/cysuml/fonts/LiberationSans-LICENSE.txt)
and [`NotoSansKR-LICENSE.txt`](https://github.com/yschoi9733/cysUML/blob/main/src/cysuml/fonts/NotoSansKR-LICENSE.txt)).

---

## 한국어

AI가 배치하고 도구가 그리는, 문서용 UML 그림 MCP 서버다.

자동 배치 도구는 빠르지만 선이 상자나 글자를 가로지르기 쉽고, 손으로 다듬기도 어렵다. cysUML은 반대로 간다. AI 어시스턴트가
상자 자리를 정하면 cysUML은 그대로 그리고 그림을 검사한다. 선이 상자나 글자를 지나면 불합격이고, 무엇을 옮길지 알려 준다.
어시스턴트는 배치를 고쳐 합격할 때까지 다시 그린다.

- 여러 UML 그림을 그린다(목록은 아래 [쓰기](#쓰기)). 교류도는 참여자·메시지 차례를 받아 cysUML이 배치하고, 똑같이 검사한다.
- PNG로 낸다. 글꼴을 함께 넣어 어느 컴퓨터에서든 같은 그림이 나오고, 한글도 그린다.

### 설치

[uv](https://docs.astral.sh/uv/)가 있어야 한다. 아래 한 줄이 [PyPI](https://pypi.org/project/cysuml/)에서 cysUML을 받아
서버를 띄운다:

```
uvx cysuml
```

표준 입출력으로 MCP를 주고받으므로 혼자 띄우면 클라이언트를 기다리기만 한다. 쓰려면 MCP 클라이언트에 등록한다.

- **Claude Code:** `claude mcp add cysuml -- uvx cysuml`
- **다른 클라이언트:** 위 영어 안내의 JSON 설정에 같은 명령을 넣는다.
- **버전:** `uvx cysuml`은 가장 새 버전을 띄운다. 클라이언트가 서버를 띄울 때마다 uv가 PyPI에 묻고, 받은 답은 10분까지 다시
  쓴다. `uv tool install cysuml`로 설치해 두었으면 uvx는 그 설치본을 띄우니 `uv tool upgrade cysuml`로 올린다. 한 버전에
  머물려면 이름 뒤에 버전을 붙인다 — `uvx cysuml@0.1.0`(JSON에서는 `"args": ["cysuml@0.1.0"]`). 나온 버전은
  [PyPI 릴리스 기록](https://pypi.org/project/cysuml/#history)에 있다.

### 쓰기

어시스턴트에게 "cysUML로 주문 도메인 클래스도를 그려 줘"나 "결제 흐름을 cysUML 교류도로 그려 줘"처럼 부탁한다. 배치 요령은
서버가 어시스턴트에게 알려 준다.

- **클래스도**는 `draw_class_diagram`으로 그린다. 어시스턴트가 상자의 왼쪽 위 자리와, 필요하면 관계선의 꺾는 점을 준다. 결과로
  검사 결과, 상자마다 그린 자리와 크기, 저장한 파일 경로, 그림을 돌려준다. 상자끼리 겹치거나, 선이 상자·글자·다른 선의 화살촉을
  지나거나, 글자끼리 겹치면 불합격이다. 선끼리 엇갈린 곳과 그림 크기는 알려 주기만 하고 불합격이 아니다. 같은 부모로 가는
  상속끼리, 실체화끼리는 여러 선을 한 줄기로 모아 삼각형 하나를 함께 써도 된다(꺾는 점을 주는 법은 도구 설명에 있다).
- **패키지도**는 `draw_package_diagram`으로 그린다. 패키지와 패키지 사이 의존을 그리고, 패키지 안에 클래스·패키지를 넣는다.
  컴포넌트·아티팩트·노드도 한 그림에 함께 그린다. 요소마다 `kind`를 주고, 다른 요소 안에 둘 요소는 `in`으로 품은 요소를
  가리킨다 — 바깥 요소는 안의 요소를 덮도록 오른쪽·아래로 늘어난다. 결과는 클래스도와 같고 요소마다 그린 자리를 돌려준다(패키지는
  선이 가운데가 아니라 탭 오른쪽 몸통의 가운데를 향하므로 그 점도 함께).
  클래스도 검사에 더해, 안의 요소가 바깥 요소의 테두리·이름 탭에 붙거나, 선이 그 끝을 품은 패키지의 테두리를 따라가거나 패키지
  탭을 지나면 불합격이다.
- **컴포넌트도**는 `draw_component_diagram`으로 그린다. 컴포넌트와 제공 인터페이스, 컴포넌트를 구현하는 아티팩트, 컴포넌트를
  실현하는 클래스를 그린다. 패키지도 도구가 받는 요소에 더해 `lollipop`(제공 인터페이스 원 — 작은 원과 그 밖에 쓰는
  이름으로 그린다. 이름 쪽은 `name_side`)을 받는다. 제공하는 컴포넌트는 원과 `association`으로 잇고(이 도구에서는 `navigable`을
  주지 않으면 화살촉이 없다), 쓰는 쪽은 원으로 `dependency`를 긋는다. 결과는 패키지도와 같고, 원마다 원만의 자리도 함께
  돌려준다. 검사도 같고, 선이 원이나 그 이름을 지나면 불합격이다.
- **배치도**(deployment diagram)는 `draw_deployment_diagram`으로 그린다. 소프트웨어(컴포넌트·아티팩트)가 어느 컴퓨터(노드)에서
  도는지 보인다. 노드 안에 컴포넌트·아티팩트·노드를 `in`으로 넣고, 노드끼리는 통신 경로(`association` — `name`에 HTTPS 같은
  프로토콜)로 잇고, 노드 밖 요소에서 노드로 «deploy»(`stereotype`이 `deploy`인 `dependency`)를 긋는다. 이 도구는 클래스끼리
  이은 것까지 모든 연관을 화살촉 없는 실선으로 그린다(필요하면 `navigable`을 준다). 받는 요소·결과·검사는 패키지도와 같다.
- **유즈케이스도**는 `draw_use_case_diagram`으로 그린다. 액터·유즈케이스·시스템 경계를 그리고, 연관·의존(«include»·«extend»)·
  일반화로 잇는다. 유즈케이스는 `in`으로 시스템 경계 안에 넣고, 액터는 경계 밖에 두어 이름을 사람 모양 옆(`name_side`가 정한
  쪽)에 쓴다. 결과는 패키지도와 같고, 액터는 이름까지 덮는 자리 뒤에 사람 모양 자리를 함께 돌려준다. 검사는 패키지도와 같고,
  선이 액터 이름이나 시스템 경계 이름을 지나도 불합격이다. 같은 부모로 가는 일반화 선은 클래스도의 상속처럼 한 줄기로 모아도 된다.
- **상태도**는 `draw_state_diagram`으로 그린다. 시작·끝 점, 상태, 선택 마름모를 전이로 잇는다. 상태의 `entry /`·`do /`·`exit /`
  줄은 `actions`에 주면 받은 그대로 쓰고, 상태 안에 상태를 넣을 때는 `in`으로 품은 상태를 가리킨다. 이름이 없는 시작·끝 점과
  선택은 `id`를 주어 전이가 가리키게 한다. 전이 글자(`name`)도 대괄호·빗금까지 받은 그대로 쓴다. 결과는 패키지도와 같다. 선이 그
  끝을 품은 상태의 이름·동작 칸을 지나거나 전이 글자가 그 칸에 겹쳐도 불합격이다.
- **액티비티도**는 `draw_activity_diagram`으로 그린다. 시작·끝 점, 행동, 결정·합류 마름모를 흐름으로 잇는다. 결정에서 나가는
  흐름의 조건은 `name`에 대괄호까지 쓴다. 결과와 검사는 패키지도와 같다.
- **교류도**는 `draw_sequence_diagram`으로 그린다. 어시스턴트는 좌표 없이 참여자, 메시지 차례, 메시지 범위를 덮는
  프레임(`loop`·`opt`·`alt`), 메시지 앞에 놓는 `ref`만 준다. cysUML이 글자에 맞춰 생명선을 띄우고 활성 막대를 그린다. 결과로 검사 결과, 저장한
  파일 경로, 그림을 돌려준다. 배치를 cysUML이 하므로 불합격은 cysUML의 버그다. 그래도 항목마다 입력에서 무엇을 바꾸면
  비켜 가는지(참여자·메시지 차례, 프레임이 덮는 범위, 글자 줄이기, 그림 나누기) 알려 준다.
- 입력 형식 전체는 도구 설명에 있어 클라이언트가 어시스턴트에게 넘긴다.
- 그림은 `out_dir`에, 없으면 서버 작업 폴더 아래 `diagrams/`에 저장한다. 같은 `file_name`이면 덮어쓴다. 쓸 수 없는 폴더(`/` 등)에서
  서버를 띄우는 클라이언트도 있는데, 그때는 도구가 오류로 알리므로 `out_dir`을 주면 된다.
- 돌려주는 그림은 긴 변이 1568px를 넘으면 그 길이로 줄인다. 저장한 파일은 원래 크기다.

### 개발

`uv sync`로 준비하고 `uv run pytest`로 시험한다. 작업 중인 코드를 Claude Code에서 써 보려면 다른 이름으로 등록한다:
`claude mcp add cysuml-dev -- uv run --directory /path/to/cysUML cysuml`. 아직 배포하지 않은 `main`의 최신 코드를 써 보려면
`uvx --from git+https://github.com/yschoi9733/cysUML cysuml`로 띄운다.

### 라이선스

cysUML은 [MIT 라이선스](https://github.com/yschoi9733/cysUML/blob/main/LICENSE)를 따른다. 함께 넣은 글꼴 Liberation Sans와
Noto Sans KR은 SIL Open Font License 1.1을 따른다([`src/cysuml/fonts`](https://github.com/yschoi9733/cysUML/tree/main/src/cysuml/fonts)).
