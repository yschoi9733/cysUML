#!/bin/bash
# <스킬 디렉터리>가 든 레포의 본 체크아웃 루트를 낸다. 판정만 한다.
#
# 사용: skill-repo.sh <스킬 디렉터리>
#
# SKILL.md "시작하기 전에"가 <스킬 레포 루트>를 구할 때 쓴다. 스킬 경로 문자열을 잘라 구하면 워크트리를
# .claude/worktrees/ 밖에 두었거나 링크를 거친 경로에서 연결 워크트리 자체가 나오고(.git 이 파일이다),
# same-repo.sh 가 사용법 오류로 멈춰 그 자리에서는 /issue 를 아예 못 쓴다(이전 codex 지적). 그래서 그
# 디렉터리에서 공유 .git 을 git 에 묻는다 — 연결 워크트리 안에서도 본 체크아웃의 .git 하나가 나온다(same-repo.sh
# 머리말과 같은 이유로 --path-format=absolute).
#
# git 을 cwd 가 아니라 <스킬 디렉터리>에서 부른다 — "git 은 전부 cwd 에서 부른다"(lib.sh 머리말)의 예외다.
# 알아내려는 것이 cwd 의 레포가 아니라 이 스킬이 든 레포이고, 그 값은 옮길 자리와 same-repo.sh 의 인자로만
# 쓰여 지우는 명령의 판정에는 들지 않는다.
#
# stdout 첫 줄
#   FOUND        다음 줄이 path <본 체크아웃 루트>. 경로에 셸이 건드리는 문자가 있으면 path-escaped 로 낸다
#   GONE         <스킬 디렉터리>가 없다(지워진 워크트리의 스킬 등)
#   NOT_IN_REPO  <스킬 디렉터리>가 git 레포 안이 아니다(git 이 "레포가 아니다"로 실패했을 때만 — lib.sh git_err_not_repo)
# 종료 코드: 0 판정함 · 2 사용법(인자가 없거나 비었다, <스킬 디렉터리>가 디렉터리가 아니다 — 파일이나 끊긴 링크)
# · 3 환경 실패(<스킬 디렉터리>에 들어가지 못했다, git 이 "레포가 아니다" 밖의 이유로 실패했다 — 지워진 등록을
# 가리키는 .git 파일·소유권 문제 등, 공유 .git 이 <루트>/.git 디렉터리 꼴이 아니다 — bare 레포·서브모듈·
# --separate-git-dir 등)

builtin unset -f -- $(builtin compgen -A function) || { echo "실패: 부른 셸에서 물려받은 함수를 지우지 못했다(lib.sh 머리말)" >&2; exit 3; }
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh" || exit 3
declare -F die_usage die_env rev_parse git_err_not_repo git_err_line lower_ascii norm is_unsafe \
  branch_unsafe ref_unsafe quote_c require_safe_branch head_unreadable has_non_ascii wt_dump wt_load \
  same_path_hits path_in_container print_checked_line print_path_line wt_print >/dev/null ||
  { echo "실패: lib.sh 에 판정 스크립트가 쓰는 함수가 없다 — 이 스크립트와 lib.sh 의 버전이 어긋났다(lib.sh 머리말)" >&2; exit 3; }

if [ $# -ne 1 ] || [ -z "$1" ]; then
  die_usage "skill-repo.sh <스킬 디렉터리>"
fi
# 없는 것만 GONE 이다 — 파일이나 끊긴 링크까지 GONE 으로 내면 SKILL.md 가 앞선 요청의 루트를 다시 쓰라는
# 갈래로 보내 잘못 넘긴 인자를 가린다.
if [ ! -e "$1" ] && [ ! -L "$1" ]; then
  echo GONE
  exit 0
fi
[ -d "$1" ] || die_usage "스킬 디렉터리가 아니다(파일이나 끊긴 링크): $1"
# cd 와 git 을 한 서브셸에서 한 번에 한다 — 따로 두 번 들어가면 그 사이 디렉터리가 바뀌었을 때 들어가지 못한 것을
# 레포 밖으로 잘못 낸다. 들어가지 못한 것(권한 등)은 종료 코드로 가려 따로 멈춘다. CDPATH 를 비우는 것은 상대경로
# 인자에 CDPATH 가 걸리면 cd 가 엉뚱한 자리로 가고 그 자리를 stdout 에 찍어 출력에 섞기 때문이다.
# 레포 밖은 91 로 서브셸 밖에 알린다. rev_parse 가 그 밖의 git 실패로 die_env 하면 서브셸이 그 메시지를 stderr 에
# 내고 3 으로 끝나니 3 은 그대로 넘긴다. 그 밖의 코드(신호 등)는 메시지 없이 끝난 것이라 메시지를 붙여 3 으로 바꾼다
# — 그대로 넘기면 SKILL.md "시작하기 전에"가 127 같은 값을 "스킬 디렉터리가 지워졌다"로 읽는다.
common=$(CDPATH='' cd -- "$1" 2>/dev/null || exit 90
  rev_parse --path-format=absolute --git-common-dir || exit 91
  printf '%s' "$REV_OUT")
rc=$?
case "$rc" in
  0) ;;
  3) exit 3 ;;
  90) die_env "스킬 디렉터리에 들어가지 못했다(권한 등): $1" ;;
  91)
    echo NOT_IN_REPO
    exit 0
    ;;
  *) die_env "스킬 디렉터리에서 git 을 묻다 종료 코드 $rc 로 끝났다: $1" ;;
esac
root=${common%/.git}
if [ "$root" = "$common" ] || [ ! -d "$root/.git" ]; then
  die_env "공유 .git 이 <루트>/.git 디렉터리 꼴이 아니라 본 체크아웃을 구하지 못했다: $common"
fi
echo FOUND
print_path_line path "$root"
exit 0
