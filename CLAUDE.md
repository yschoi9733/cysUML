# CLAUDE.md

## 프로젝트

- **cysUML** — AI가 배치하고 도구가 그리는, 문서에 바로 넣을 UML 그림을 뽑는 MCP 서버. 설계 정본은 이슈 #1.
- Python 3.10 이상 · uv · MCP 공식 Python SDK · Pillow. 첫 버전은 클래스도·교류도를 PNG로 그린다.
- 레포·화면 이름은 `cysUML`, 파이썬 패키지·실행 명령은 소문자 `cysuml`.

## 코딩 규칙

- 주석·문서는 한국어로 쓰고, 주석은 최소화한다 — 코드를 읽으면 알 수 있는 건 안 쓴다.
- 그림에는 레포에 함께 넣은 글꼴만 쓴다. 운영체제 글꼴 경로에 기대지 않는다.
- 공개 레포다. 다른 프로젝트·팀·학교 이름, 개인 정보, 비밀 값을 커밋하지 않는다.
- StarUML 앱에서 꺼낸 파일(메타모델 정의 등)을 넣지 않는다.

## 빌드 / 테스트

- 준비는 `uv sync`, 테스트는 `uv run pytest`.
- AI 기본 게이트: 파이썬 코드·`pyproject.toml`·`uv.lock`·글꼴을 고쳤으면 `uv run pytest`, `.claude/skills/`·`.gitignore`를 고쳤으면 `bash .claude/skills/issue/tests/run.sh`를 통과시킨다(스킬 테스트가 `.gitignore`도 검사한다).

## Git / 협업 규칙

- `main` 직접 push 금지. 흐름: **이슈 먼저** → 최신 `main`에서 `<타입>/<기능>` 브랜치 → PR 본문 첫 줄에 `Closes #<이슈번호>`.
- 기능 작업은 `/issue <번호> cysUML`로 한다(`.claude/skills/issue`).
- **Squash 머지 전용**(merge commit·rebase 비활성, 머지하면 브랜치 자동 삭제) — PR 제목이 곧 `main`의 커밋 메시지이므로 PR 제목은 커밋 컨벤션(`feat: ...`)을 따른다.
- 커밋 메시지·이슈·PR은 한국어로 쓴다. 커밋·PR 어디에도 AI 관여 표기(Co-Authored-By, Generated with 등)를 넣지 않는다.
- PR 본문에 머지 조건·머지 담당 문장을 넣지 않는다.
- 스테이징은 파일을 지정해서 한다 — `git add -A` 금지.
- 이슈를 새로 만들기 전에 기존 이슈와 중복되는지 확인한다. 이슈·PR 본문은 올리기 전에 처음 읽는 사람 기준으로 가독성을 점검한다.

## 타입 / 영역 라벨

커밋·브랜치·PR·라벨에 **같은 타입 어휘**를 쓴다.

- 타입: `feat` · `fix` · `refactor` · `docs` · `chore` — 라벨은 이 5개. 커밋에는 필요하면 `build` · `ci` · `style` · `test` · `perf`도 쓴다.
- 영역: `area: class`(클래스도 입력·그리기·검사) · `area: sequence`(교류도 배치·그리기·검사) · `area: server`(MCP 서버·도구 설명·설치)
- 이슈·PR에는 **타입 라벨 1개**를 붙이고, 작업이 한 영역에 분명히 속하면 그 **영역 라벨 1개**를 더 붙인다. 여러 영역에 걸치거나 공통 코드(그림판·글꼴·검사 틀)·빌드 설정·문서·스킬 작업은 영역 라벨 없이 둔다.
- 상태·메타 라벨: 위 타입·영역이 아닌 라벨(GitHub 기본 `bug`·`enhancement`·`question` 등).
