#!/bin/bash
# cwd 가 <경로> 자신이거나 그 아래인지 본다. 판정만 한다.
#
# 사용: inside.sh <경로>
#
# cwd 에서 위로 거슬러 올라가며 inode(-ef)로 비교한다 — cwd 하나만 비교하면 하위에 서 있는
# 경우를 놓치고, 문자열로 비교하면 NFC/NFD 표기가 달라 틀린다. 디렉터리 이름이나
# git rev-parse --git-dir 로도 보지 않는다(고아 디렉터리에는 .git 이 없어 git 이 상위 레포를
# 낸다).
#
# stdout
#   INSIDE    cwd 가 <경로>이거나 그 하위다
#   OUTSIDE   아니다 (<경로>가 없어도 여기)
#   CWD_GONE  cwd 가 이미 지워져 판단할 수 없다 — 예전 순회는 이때 무한 루프에 빠졌다
# 종료 코드: 0 판정함 · 2 사용법 · 3 환경 실패(lib.sh 를 불러오는 앞머리에서 멈췄다 — SKILL.md "스크립트를 부르는 법")

builtin unset -f -- $(builtin compgen -A function) || { echo "실패: 부른 셸에서 물려받은 함수를 지우지 못했다(lib.sh 머리말)" >&2; exit 3; }
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh" || exit 3
declare -F die_usage die_env rev_parse git_err_not_repo git_err_line lower_ascii norm is_unsafe \
  branch_unsafe ref_unsafe quote_c require_safe_branch head_unreadable has_non_ascii wt_dump wt_load \
  same_path_hits path_in_container print_checked_line print_path_line wt_print >/dev/null ||
  { echo "실패: lib.sh 에 판정 스크립트가 쓰는 함수가 없다 — 이 스크립트와 lib.sh 의 버전이 어긋났다(lib.sh 머리말)" >&2; exit 3; }

if [ $# -ne 1 ] || [ -z "$1" ]; then
  die_usage "inside.sh <경로>"
fi

D=$(pwd -P 2>/dev/null)
if [ -z "$D" ]; then
  echo CWD_GONE
  exit 0
fi
while [ -n "$D" ] && [ "$D" != "/" ] && [ "$D" != "." ]; do
  if [ "$D" -ef "$1" ]; then
    echo INSIDE
    exit 0
  fi
  D=$(dirname "$D")
done
echo OUTSIDE
exit 0
