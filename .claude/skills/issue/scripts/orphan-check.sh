#!/bin/bash
# 등록 없는 디렉터리를 rm -rf 해도 되는지 판정한다. 아무것도 지우지 않는다.
# rm -rf 에는 worktree remove 의 미커밋 방벽이 없어서, 이 내용 기준이 유일한 방벽이다.
#
# 사용: orphan-check.sh <디렉터리>
#
# stdout 첫 줄
#   MISSING      그 경로에 아무것도 없다
#   REGISTERED   지금 등록된 워크트리(본 체크아웃 포함)와 같은 디렉터리다 — 지우지 않는다.
#                이름이 아니라 -ef 로 보므로 레포 밖의 같은 이름에 속지 않는다. prunable 로 남은
#                등록 자리에 디렉터리가 되살아난 경우(지운 뒤 도는 프로세스가 그 경로에 파일을 다시 쓴 경우 등)도
#                여기로 오는데, 그때는 셋째 줄에 prunable [이유] 가 붙는다 — git worktree remove 가
#                validation failed 로 못 지우고 git worktree prune 으로만 치울 수 있는 등록이다
#   EMPTY        비어 있거나 맨 위에 .DS_Store 파일 하나뿐이다. 심볼릭 링크는 이름이 .DS_Store 여도 파일로
#                치지 않는다. 하위 디렉터리가 있으면 그 디렉터리부터 다른 파일이다 — .idea/·.venv/ 만 되살아나도
#                OTHER_FILES 로 사람이 본다
#   OTHER_FILES  그 밖의 것이 있다 — 미커밋 작업일 수 있다. other <상대경로> 줄(최대 20줄)
# 둘째 줄: container in|out — <레포 루트>/.claude/worktrees/ 아래인지
# OTHER_FILES 뒤에 other-more 20+ 줄이 붙으면 other 목록이 전부가 아니다 — 21개째에서 세기를 멈췄다. 20개를 보여 준
# 뒤 파일이 늘면 새 파일이 21번째 뒤로 가 other 줄은 그대로이고 이 줄만 붙을 수 있다(실측) — 앞선 출력과 견줄 때는
# 이 줄까지 본다
#
# IDE 가 되살린 흔적은 지워도 되는 것으로 치지 않는다 — JetBrains IDE(PyCharm 등)가 열고 있던 워크트리를 지우면
# .idea/ 를 되살릴 수 있지만, 무엇이 되살아나는지 재 보지 않았으니 흔적으로 치지 않고 OTHER_FILES 로 사람이 본다.
#
# 종료 코드: 0 판정함 · 2 사용법 · 3 환경 실패(디렉터리를 끝까지 읽지 못한 경우 포함 — 권한 등)

builtin unset -f -- $(builtin compgen -A function) || { echo "실패: 부른 셸에서 물려받은 함수를 지우지 못했다(lib.sh 머리말)" >&2; exit 3; }
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh" || exit 3
declare -F die_usage die_env rev_parse git_err_not_repo git_err_line lower_ascii norm is_unsafe \
  branch_unsafe ref_unsafe quote_c require_safe_branch head_unreadable has_non_ascii wt_dump wt_load \
  same_path_hits path_in_container print_checked_line print_path_line wt_print >/dev/null ||
  { echo "실패: lib.sh 에 판정 스크립트가 쓰는 함수가 없다 — 이 스크립트와 lib.sh 의 버전이 어긋났다(lib.sh 머리말)" >&2; exit 3; }

if [ $# -ne 1 ] || [ -z "$1" ]; then
  die_usage "orphan-check.sh <디렉터리>"
fi
d=$1
while [ "$d" != "/" ] && [ "${d%/}" != "$d" ]; do d=${d%/}; done

list=$(mktemp "${TMPDIR:-/tmp}/issue-wt-list.XXXXXX") || die_env "임시 파일을 만들 수 없다"
walk=$(mktemp "${TMPDIR:-/tmp}/issue-orphan-walk.XXXXXX") || { rm -f "$list"; die_env "임시 파일을 만들 수 없다"; }
trap 'rm -f "$list" "$walk"' EXIT
wt_dump "$list"
wt_load "$list"

container_line() {
  if path_in_container "$d"; then echo "container in"; else echo "container out"; fi
}

if [ ! -e "$d" ] && [ ! -L "$d" ]; then
  echo MISSING
  container_line
  exit 0
fi

for ((i = 0; i < WT_N; i++)); do
  if [ "$d" -ef "${WT_PATH[$i]}" ]; then
    echo REGISTERED
    container_line
    if [ "${WT_PRUNABLE[$i]}" = 1 ]; then
      r=${WT_PRUNABLE_REASON[$i]}
      if [ -n "$r" ]; then echo "prunable ${r//$'\n'/ }"; else echo "prunable"; fi
    fi
    exit 0
  fi
done

others=()
if [ -L "$d" ] || [ ! -d "$d" ]; then
  others+=(".")
else
  # find 가 실패하면(읽을 수 없는 디렉터리 등) 판정하지 않는다. 그대로 두면 못 읽은 자리에 미커밋 작업이 있어도
  # 목록이 비어 EMPTY 가 나오는데, 문서는 EMPTY 를 묻지 않고 지워도 되는 판정으로 쓴다. 프로세스 치환으로는
  # /bin/bash(3.2)에서 find 의 종료 코드를 받을 수 없어 파일로 받는다 — 트리 전체를 한 번 훑지만 find 는
  # 수만 개도 금방이고, 느린 것은 아래 반복문인데 그쪽은 여전히 21개째에서 멈춘다.
  find "$d" -mindepth 1 -print0 > "$walk" || die_env "끝까지 읽지 못했다 — 사람이 직접 확인해야 한다: $d"
  while IFS= read -r -d '' e; do
    rel=${e#"$d"/}
    if [ ! -L "$e" ]; then
      case "$rel" in
        .DS_Store)
          [ -f "$e" ] && continue
          ;;
      esac
    fi
    others+=("$rel")
    # 20개를 넘기면 더 세지 않는다 — 판정은 이미 OTHER_FILES 로 정해졌고, 아래 목록도 20개에서 자른다.
    # 남은 전체 체크아웃(소스 + .venv/)에 대고 끝까지 돌면 수만 개를 세느라 멎은 것처럼 보인다.
    [ ${#others[@]} -gt 20 ] && break
  done < "$walk"
fi

if [ ${#others[@]} -eq 0 ]; then
  echo EMPTY
  container_line
  exit 0
fi
echo OTHER_FILES
container_line
for ((k = 0; k < ${#others[@]} && k < 20; k++)); do
  print_path_line other "${others[$k]}"
done
if [ ${#others[@]} -gt 20 ]; then
  echo "other-more 20+"
fi
exit 0
