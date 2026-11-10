#!/bin/bash
# cwd 가 <레포 루트>의 레포 안인지 본다 — 본 체크아웃이든 연결 워크트리든, 그 하위든.
# 판정만 한다.
#
# 사용: same-repo.sh <레포 루트>
#   <레포 루트>는 본 체크아웃 루트다 — git worktree list --porcelain 첫 레코드의 경로, 또는 skill-repo.sh 가
#   낸 path(SKILL.md "시작하기 전에").
#
# --show-toplevel 로 보지 않는다 — 워크트리 안에서는 그 워크트리를 내므로 본 체크아웃과 늘
# 다르다. --git-common-dir 은 워크트리 안에서도 공유 .git 하나를 낸다. 하위 디렉터리에서는
# 상대경로(../.git)로 나오므로 --path-format=absolute 를 붙인다. 비교는 -ef(inode)라
# NFC/NFD 표기와 무관하다.
#
# <레포 루트>를 같은 cwd 에서 구했다면 이 확인이 잡는 것은 "cwd 가 그 사이 레포 밖으로 나갔는가" 하나다 —
# 처음부터 다른 레포에서 시작한 세션은 여기를 통과한다. skill-repo.sh 가 스킬 경로에서 구한 루트를 넘기면
# 처음부터 다른 레포에 선 세션도 OTHER_REPO 로, 레포 밖에서 연 세션(홈 디렉터리 등)은 NOT_IN_REPO 로 잡는다.
#
# stdout: SAME_REPO | OTHER_REPO | NOT_IN_REPO | CWD_GONE
#   NOT_IN_REPO 는 git 이 "레포가 아니다"로 실패했을 때만 낸다(lib.sh git_err_not_repo).
# 종료 코드: 0 판정함 · 2 사용법(<레포 루트>/.git 디렉터리가 없다) · 3 환경 실패(git 이 "레포가 아니다" 밖의 이유로
# 실패했다 — 지워진 등록을 가리키는 .git 파일, 소유권 문제(safe.directory) 등)

builtin unset -f -- $(builtin compgen -A function) || { echo "실패: 부른 셸에서 물려받은 함수를 지우지 못했다(lib.sh 머리말)" >&2; exit 3; }
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh" || exit 3
declare -F die_usage die_env rev_parse git_err_not_repo git_err_line lower_ascii norm is_unsafe \
  branch_unsafe ref_unsafe quote_c require_safe_branch head_unreadable has_non_ascii wt_dump wt_load \
  same_path_hits path_in_container print_checked_line print_path_line wt_print >/dev/null ||
  { echo "실패: lib.sh 에 판정 스크립트가 쓰는 함수가 없다 — 이 스크립트와 lib.sh 의 버전이 어긋났다(lib.sh 머리말)" >&2; exit 3; }

if [ $# -ne 1 ] || [ -z "$1" ]; then
  die_usage "same-repo.sh <레포 루트>"
fi
[ -d "$1/.git" ] || die_usage "본 체크아웃 루트가 아니다(.git 디렉터리가 없다): $1"

if ! pwd -P >/dev/null 2>&1; then
  echo CWD_GONE
  exit 0
fi
if ! rev_parse --path-format=absolute --git-common-dir; then
  echo NOT_IN_REPO
  exit 0
fi
common=$REV_OUT
if [ "$common" -ef "$1/.git" ]; then
  echo SAME_REPO
else
  echo OTHER_REPO
fi
exit 0
