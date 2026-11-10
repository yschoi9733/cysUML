#!/bin/bash
# 지금 작업 디렉터리가 어느 레포의 워크트리 안인지 본다. 판정만 한다.
#
# 사용: isolation-check.sh
#
# SKILL.md "시작하기 전에"의 "옮기기"가 cd 해도 되는 세션인지 가릴 때 쓴다. 워크트리 안에 선 세션은 격리돼 있을
# 수 있다 — 명령 가드가 워크트리 밖을 건드리는 git 명령을 거부하고, 하네스가 작업 디렉터리를 그 워크트리로
# 되돌려 옮겼다고 믿고 친 명령이 엉뚱한 곳에서 돈다(references/worktree.md "먼저 알아 둘 것"). 대화 기록으로
# 가리면 요약으로 잘린 기록을 못 보므로 서 있는 자리로 가린다. 둘 중 하나라도 걸리면 ISOLATED 다.
#   - 경로에 /.claude/worktrees/ 가 들어 있다(논리 경로·실제 경로 어느 쪽이든). 하네스는 작업 디렉터리가 그
#     아래면 이미 격리된 세션으로 다룬다 — 등록이 지워진 빈 폴더여도 같다.
#   - 연결 워크트리 안이다 — --git-dir 과 --git-common-dir 이 다른 디렉터리다. 공유 git 디렉터리 이름과 무관해
#     bare 레포·--separate-git-dir 레포의 워크트리와 .claude/worktrees/ 밖에 등록된 워크트리도 걸린다. 또는
#     --git-dir 이 /.git/worktrees/ 아래다 — 연결 워크트리 안의 서브모듈은 git 디렉터리가 곧 공유 디렉터리라 앞의
#     비교로는 안 걸리지만, 그 자리가 워크트리의 git 디렉터리 아래(.git/worktrees/<이름>/modules/…)다.
#
# stdout 첫 줄
#   MOVABLE    어느 레포의 워크트리 안도 아니다(본 체크아웃이거나 그 하위, 또는 레포 밖)
#   ISOLATED   다음 줄이 reason worktree-path(경로) 또는 reason linked-worktree(연결 워크트리)
#   CWD_GONE   작업 디렉터리가 이미 지워졌다
# 종료 코드: 0 판정함 · 2 사용법 · 3 환경 실패(git 이 "레포가 아니다" 밖의 이유로 실패했다 — 지워진 등록을
# 가리키는 .git 파일, safe.directory 등. 그때 MOVABLE 로 내면 막아야 할 자리를 통과시킨다. 판별은 lib.sh
# git_err_not_repo 로 same-repo.sh·skill-repo.sh 와 같다)

builtin unset -f -- $(builtin compgen -A function) || { echo "실패: 부른 셸에서 물려받은 함수를 지우지 못했다(lib.sh 머리말)" >&2; exit 3; }
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh" || exit 3
declare -F die_usage die_env rev_parse git_err_not_repo git_err_line lower_ascii norm is_unsafe \
  branch_unsafe ref_unsafe quote_c require_safe_branch head_unreadable has_non_ascii wt_dump wt_load \
  same_path_hits path_in_container print_checked_line print_path_line wt_print >/dev/null ||
  { echo "실패: lib.sh 에 판정 스크립트가 쓰는 함수가 없다 — 이 스크립트와 lib.sh 의 버전이 어긋났다(lib.sh 머리말)" >&2; exit 3; }

if [ $# -ne 0 ]; then
  die_usage "isolation-check.sh (인자 없음)"
fi
if ! physical=$(pwd -P 2>/dev/null); then
  echo CWD_GONE
  exit 0
fi
# 그 아래에 무엇이 있을 때만 친다 — 컨테이너 폴더(.claude/worktrees) 자체는 워크트리 안이 아니다. 대소문자는
# 지운다 — 이 볼륨은 대소문자만 다른 경로로도 같은 폴더가 열리고, pwd -P 는 친 대소문자를 그대로 낸다(lib.sh
# norm 과 같은 이유).
for p in "$PWD" "$physical"; do
  case "$(lower_ascii "$p")/" in
    */.claude/worktrees/?*)
      echo ISOLATED
      echo "reason worktree-path"
      exit 0
      ;;
  esac
done
# 레포 밖만 MOVABLE 로 친다 — 그 밖의 git 실패는 lib.sh rev_parse 가 종료 코드 3 으로 멈춘다.
if ! rev_parse --path-format=absolute --git-dir --git-common-dir; then
  echo MOVABLE
  exit 0
fi
dirs=$REV_OUT
# 한 번 불러 두 줄로 받는다(--git-dir, --git-common-dir 순서). 따로 두 번 부르면 둘째만 실패하는 갈래가 하나 더
# 생긴다. 줄이 정확히 둘이 아니면(경로에 개행이 있다) 갈라 읽을 수 없으니 멈춘다.
case "$dirs" in
  *$'\n'*$'\n'*) die_env "git 디렉터리 경로에 개행이 있어 판정하지 못했다" ;;
  *$'\n'*) ;;
  *) die_env "git rev-parse 가 두 줄을 내지 않았다: $dirs" ;;
esac
git_dir=${dirs%%$'\n'*}
common=${dirs#*$'\n'}
linked=
[ "$git_dir" -ef "$common" ] || linked=1
case "$git_dir/" in
  */.git/worktrees/?*) linked=1 ;;
esac
if [ -n "$linked" ]; then
  echo ISOLATED
  echo "reason linked-worktree"
  exit 0
fi
echo MOVABLE
exit 0
