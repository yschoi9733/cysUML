#!/bin/bash
# git worktree remove 가 함께 지울 무시 대상 파일 중 다시 만들 수 없는 것을 찾는다. 아무것도 지우지 않는다.
# remove 는 추적 안 된 파일이 있으면 거부하지만 .gitignore 대상은 묻지 않고 디렉터리째 지운다. 이 레포의
# 무시 대상에는 비밀 값 파일(.env·.env.*)·그림 출력 폴더(diagrams/)·편집기 설정(.vscode/)처럼 다른 곳에 없을 수 있는
# 것이 들어 있다.
#
# 사용: ignored-check.sh <워크트리 경로>
#   다른 스크립트와 달리 cwd 가 아니라 인자로 받은 워크트리 안에서 git 을 부른다 — 보는 것이 그 워크트리의
#   파일이기 때문이다. 레포나 브랜치를 판정하지는 않는다.
#
# stdout 첫 줄
#   MISSING       그 경로에 아무것도 없다 — remove 가 지울 파일이 없다
#   NOT_WORKTREE  그 경로가 워크트리의 최상위가 아니다(.git 없이 되살아난 디렉터리, 심볼릭 링크 등) — 판정하지
#                 않는다
#   CLEAN         무시 대상이 없거나 다시 만들 수 있는 것뿐이다
#   KEEP          그 밖의 무시 대상이 있다. keep <워크트리 기준 상대경로> 줄(최대 20줄), 20개를 넘으면
#                 keep-more 20+ 줄이 붙는다
#
# 다시 만들 수 있는 것으로 치는 것은 /issue 3단계 게이트(uv sync·uv run pytest)와 IDE·하네스가 만드는 자리뿐이다:
#   - 어느 깊이든, 안에 *.pyc 파일만 든 __pycache__ 디렉터리(파이썬이 모듈을 불러올 때 만든다 — scratchpad/ 바로 아래도
#     그렇다. 사람이 거기 둔 도우미 스크립트를 돌려도 생기는 바이트코드 캐시라 아래 scratchpad 규칙의 "사람이 남긴 것"이
#     아니다). *.pyc 밖의 것이 하나라도 들었으면 사람이 본다
#   - 최상위 .venv·.pytest_cache 디렉터리(uv sync·uv run pytest 가 만든다)
#   - .claude/settings.local.json 파일(하네스가 그 워크트리에서 받은 허용 설정을 적는다 — 잃어도 다시 묻는다)
#   - scratchpad/issue-rounds·scratchpad/issue-rereview-rounds 파일(/issue 셀프 리뷰의 셈 기록 — SKILL.md 4단계 "셈 기록",
#     round-count.sh. PR 이 머지될 때까지 남겨 두는 파일이라, 사람이 보게 하면 머지 정리가 매번 멈춘다. 지운 워크트리를
#     다시 붙이면 기록이 없어 SKILL.md 대로 셈을 사람에게 묻는다)
#   - 최상위 .idea 디렉터리와 최상위 *.iml 파일(개발자가 PR 의 코드를 보려고 워크트리를 JetBrains IDE(PyCharm 등)로
#     열면 생긴다 — IDE 가 다시 만든다). 다만 .idea 안에 팀이 남기려고 만드는 폴더(runConfigurations·inspectionProfiles·
#     dictionaries·scopes·fileTemplates·codeStyles — 프로젝트 파일로 저장한 실행 구성·설정)나 사람이 만든 작업이
#     남는 자리(shelf — Shelve Changes 로 치워 둔 변경, dataSources 폴더와 DB 연결 설정 파일 dataSources.xml·
#     dataSources.local.xml)가 하나라도 있으면 사람이 본다.
#     workspace.xml 등 나머지는 IDE 가 사용자마다 따로 두는 로컬 상태다. httpRequests 는 IDE 의 HTTP 클라이언트가 요청을
#     한 번만 돌려도 기록(http-requests-log)을 자동으로 쌓는 자리라 로컬 상태로 친다 — 사람이 보게 하면 머지 정리가
#     매번 멈춘다. codeStyles 는 사람이 프로젝트 코드 스타일을 바꿨을 때만 생기므로 사람이 본다
#   - .DS_Store 파일(링크·디렉터리 제외 — orphan-check.sh 와 같다)
#   - 빈 디렉터리(하네스가 워크트리 안에 빈 .claude/worktrees/ 를 만든다 — 실측)
# 그 밖의 무시 대상은 늘 KEEP 으로 나온다 — 그림 출력 폴더 diagrams/, 편집기 설정 .vscode/, __pycache__ 밖의 *.pyc
# 같은 것이다. 최상위 build/·dist/ 도 사람이 본다 — 패키지를 빌드하면 생기지만 /issue 게이트가 만드는 자리가 아니고,
# .gitignore 에 걸려 사람이 둔 스크립트·메모가 추적 밖에 숨을 수 있다(이전 리뷰에서 나온 기준이다). .ruff_cache 와
# *.egg-info 도 사람이 본다 — ruff 는 게이트에 없고, *.egg-info 는 빌드 백엔드에 따라 생기지 않는다. 게이트가 늘 만든다고
# 실측한 자리만 이 목록에 더한다.
# 이름만으로 넘기지 않는다. 같은 이름이 다른 자리에 있으면 사람이 만든 것일 수 있다 — 깊은 곳의 .venv·.pytest_cache·
# .idea(.gitignore 가 어느 깊이든 무시한다), 최상위가 아닌 *.iml, scratchpad/ 에 남긴 메모(이전 리뷰에서 실측).
# 최상위 scratchpad/ 는 한 줄로만 나오므로 안을 들여다보고 하나씩 가린다(5단계가 거기 둔 PR 본문 파일은 다 쓰면
# 지우므로, 위 셈 기록 두 파일 밖에 남은 것은 사람이 본다).
#
# 종료 코드: 0 판정함 · 2 사용법 · 3 환경 실패(git 이 "레포가 아니다" 밖의 이유로 실패했다 — 소유권 문제 등)

builtin unset -f -- $(builtin compgen -A function) || { echo "실패: 부른 셸에서 물려받은 함수를 지우지 못했다(lib.sh 머리말)" >&2; exit 3; }
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh" || exit 3
declare -F die_usage die_env rev_parse git_err_not_repo git_err_line lower_ascii norm is_unsafe \
  branch_unsafe ref_unsafe quote_c require_safe_branch head_unreadable has_non_ascii wt_dump wt_load \
  same_path_hits path_in_container print_checked_line print_path_line wt_print >/dev/null ||
  { echo "실패: lib.sh 에 판정 스크립트가 쓰는 함수가 없다 — 이 스크립트와 lib.sh 의 버전이 어긋났다(lib.sh 머리말)" >&2; exit 3; }

if [ $# -ne 1 ] || [ -z "$1" ]; then
  die_usage "ignored-check.sh <워크트리 경로>"
fi
d=$1
while [ "$d" != "/" ] && [ "${d%/}" != "$d" ]; do d=${d%/}; done

if [ ! -e "$d" ] && [ ! -L "$d" ]; then
  echo MISSING
  exit 0
fi
if [ -L "$d" ] || [ ! -d "$d" ]; then
  echo NOT_WORKTREE
  exit 0
fi
cd "$d" || die_env "들어갈 수 없다: $d"
# .git 이 없는 디렉터리에서는 git 이 상위 레포(본 체크아웃)로 올라가 그쪽 파일을 본다 — 최상위가 이 경로일 때만
# 판정한다. git 이 "레포가 아니다"로 실패했을 때만 NOT_WORKTREE 로 내고, 소유권 문제 같은 그 밖의 실패는 rev_parse 가
# 종료 코드 3 으로 멈춘다 — NOT_WORKTREE 로 내면 원인이 stderr 에 남지 않는다.
if ! rev_parse --show-toplevel || ! [ "$REV_OUT" -ef . ]; then
  echo NOT_WORKTREE
  exit 0
fi

tmpd=$(mktemp -d "${TMPDIR:-/tmp}/issue-ignored.XXXXXX") || die_env "임시 디렉터리를 만들 수 없다"
trap 'rm -rf "$tmpd"' EXIT
out=$tmpd/status
kids=$tmpd/kids
probe=$tmpd/probe
# --ignored=matching 은 패턴에 걸린 자리를 그대로 낸다 — 디렉터리 패턴이면 그 디렉터리 한 줄, 파일 패턴이면
# 파일마다 한 줄. 경로는 워크트리 최상위 기준이다(실측). -unormal 을 박아 둔다 — 사용자 설정이
# status.showUntrackedFiles=no 면 --ignored=matching 과 함께 쓸 수 없다며 rc 128 로 죽는다(실측).
# --no-optional-locks 는 status 가 인덱스를 새로 쓰며 index.lock 을 잡지 않게 한다 — 판정만 하는 스크립트가 그
# 워크트리에서 커밋 중인 다른 세션과 잠금을 다투면 안 된다.
git --no-optional-locks status --porcelain=v1 -z -unormal --ignored=matching > "$out" || die_env "git status 실패: $d"

# 링크가 아닌 일반 파일·디렉터리일 때만 참 — 링크는 이름이 맞아도 다시 만들 수 있는 것으로 치지 않는다.
plain_file() { [ -f "$1" ] && [ ! -L "$1" ]; }
plain_dir() { [ -d "$1" ] && [ ! -L "$1" ]; }

# .idea 안에 사람이 남기려고 만드는 폴더가 없으면 참.
ide_local_only() {
  local kept
  for kept in runConfigurations inspectionProfiles dictionaries scopes fileTemplates codeStyles shelf dataSources \
    dataSources.xml dataSources.local.xml; do
    if [ -e "$1/$kept" ] || [ -L "$1/$kept" ]; then return 1; fi
  done
  return 0
}

# 이름만 보고 넘기지 않는다.
only_pyc() {
  find "$1" -mindepth 1 \( ! -type f -o ! -name '*.pyc' \) -print -quit > "$probe" 2>/dev/null || return 1
  [ ! -s "$probe" ]
}

# $1 슬래시를 뗀 상대경로. 다시 만들 수 있는 자리면 참 — 파일·디렉터리 구분은 git 이 낸 모양이 아니라 plain_file·
# plain_dir 가 디스크에서 본다.
regenerable() {
  local q=$1
  case "${q##*/}" in
    .DS_Store)
      plain_file "$q"
      return
      ;;
    __pycache__)
      plain_dir "$q" && only_pyc "$q"
      return
      ;;
  esac
  case "$q" in
    .venv | .pytest_cache)
      plain_dir "$q"
      return
      ;;
    .idea)
      plain_dir "$q" && ide_local_only "$q"
      return
      ;;
    .claude/settings.local.json | scratchpad/issue-rounds | scratchpad/issue-rereview-rounds)
      plain_file "$q"
      return
      ;;
  esac
  # *.iml 은 최상위만 — case 의 * 는 / 도 넘으므로 / 가 든 자리를 먼저 뺀다.
  case "$q" in
    */*) return 1 ;;
    *.iml)
      plain_file "$q"
      return
      ;;
  esac
  return 1
}

# 비었는지 확실히 알 때만 참 — 읽을 수 없으면 비었다고 보지 않는다. ls 출력을 명령 치환으로 받지 않는다 — 이름이
# 줄바꿈뿐인 파일이 있으면 출력이 줄바꿈뿐이라 치환이 떼어 내 '비었다'가 된다(이전 codex 지적). find 의 NUL 구분
# 출력을 파일로 받아 크기로 본다.
empty_dir() {
  [ -d "$1" ] && [ ! -L "$1" ] || return 1
  find "$1" -mindepth 1 -maxdepth 1 -print0 > "$probe" 2>/dev/null || return 1
  [ ! -s "$probe" ]
}

keep=()
judge() {
  regenerable "$1" && return
  if [ "${2%/}" != "$2" ] && empty_dir "$1"; then return; fi
  keep+=("$2")
}

while IFS= read -r -d '' e; do
  case "$e" in
    '!! '*) ;;
    *) continue ;;
  esac
  p=${e#'!! '}
  q=${p%/}
  if [ "$q" = scratchpad ] && [ "$p" != "$q" ]; then
    find scratchpad -mindepth 1 -maxdepth 1 -print0 > "$kids" || die_env "끝까지 읽지 못했다: $d/scratchpad"
    while IFS= read -r -d '' k; do
      if [ -d "$k" ] && [ ! -L "$k" ]; then judge "$k" "$k/"; else judge "$k" "$k"; fi
      [ ${#keep[@]} -gt 20 ] && break
    done < "$kids"
  else
    judge "$q" "$p"
  fi
  [ ${#keep[@]} -gt 20 ] && break
done < "$out"

if [ ${#keep[@]} -eq 0 ]; then
  echo CLEAN
  exit 0
fi
echo KEEP
for ((k = 0; k < ${#keep[@]} && k < 20; k++)); do
  print_path_line keep "${keep[$k]}"
done
if [ ${#keep[@]} -gt 20 ]; then
  echo "keep-more 20+"
fi
exit 0
