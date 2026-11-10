#!/bin/bash
# <브랜치>에만 있는 커밋에 detached 로 서 있는 워크트리를 찾는다. 누군가 그 안에서 bisect 중일
# 수 있으니, 있으면 브랜치를 지우기 전에 묻는다. 판정만 한다.
#
# 사용: detached-check.sh <브랜치>
#
# "이 브랜치에만 있다" = HEAD 가 그 브랜치의 조상이고 origin/main 의 조상은 아니다.
# 뒤 조건이 없으면 옛 main 커밋에 세워 둔 아무 detached 워크트리나 걸려 머지 정리가 매번 멈춘다.
# 그 브랜치는 refs/heads/<브랜치>와 refs/remotes/origin/<브랜치> 중 있는 것을 전부 본다 — 어느 한쪽에만
# 있는 커밋에 선 체크아웃도 원격 삭제 앞에서 걸리게 한다. 원격에만 남은 브랜치를 git checkout
# origin/<브랜치> 로 열어 둔 경우와, 다른 머신의 push 로 원격이 로컬보다 앞선 커밋에 선 경우가 그렇다.
# detached 워크트리는 branch 줄이 없고 이름도 브랜치에서 안 나와서 find.sh 로는 안 잡힌다.
#
# stdout 첫 줄
#   NO_BRANCH  로컬에도 원격 추적 ref 에도 그 브랜치가 없다
#   NONE       해당 워크트리가 없다
#   FOUND      있다
# 그 뒤 줄 (NO_BRANCH 가 아닐 때)
#   ref <refs/heads/… 또는 refs/remotes/origin/…>  기준으로 본 ref 마다 한 줄, 로컬이 먼저 —
#                      refs/heads/ 줄이 없으면 로컬 브랜치가 없다
#   unreadable <경로>  판정에서 뺀 깨진 등록 — HEAD 를 못 읽거나(0바이트면 branch·detached 줄이 아예 없고,
#                      HEAD 파일이 없으면 detached 가 붙는다 — 실측) HEAD 가 가리키는 커밋이 없다(force-push
#                      뒤 gc). 하나 때문에 판정 전체가 죽으면 그 레포의 머지 정리가 전부 멈추므로 빼고
#                      보고만 한다. 브랜치 ref 만 지워진 등록(branch 줄이 남는다)은 여기 안 들어간다 —
#                      detached 가 아니라 이 확인의 대상이 아니고, 제거 절차가 치우는 정상 경로다
#   FOUND 면 레코드마다 블록(find.sh 와 같은 모양)
#
# 종료 코드: 0 판정함 · 2 사용법(<브랜치>가 명령에 넣을 수 없는 이름일 때 포함 — lib.sh branch_unsafe) ·
#   3 환경 실패(origin/main 이 없음). merge-base --is-ancestor 는
#   "아니다"가 1, 오류가 128 이라 둘을 가를 수 있고, 오류 난 레코드는 unreadable 로 빼고 계속한다.

builtin unset -f -- $(builtin compgen -A function) || { echo "실패: 부른 셸에서 물려받은 함수를 지우지 못했다(lib.sh 머리말)" >&2; exit 3; }
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh" || exit 3
declare -F die_usage die_env rev_parse git_err_not_repo git_err_line lower_ascii norm is_unsafe \
  branch_unsafe ref_unsafe quote_c require_safe_branch head_unreadable has_non_ascii wt_dump wt_load \
  same_path_hits path_in_container print_checked_line print_path_line wt_print >/dev/null ||
  { echo "실패: lib.sh 에 판정 스크립트가 쓰는 함수가 없다 — 이 스크립트와 lib.sh 의 버전이 어긋났다(lib.sh 머리말)" >&2; exit 3; }

if [ $# -ne 1 ] || [ -z "$1" ]; then
  die_usage "detached-check.sh <브랜치>"
fi
b=$1
require_safe_branch "$b"

list=$(mktemp "${TMPDIR:-/tmp}/issue-wt-list.XXXXXX") || die_env "임시 파일을 만들 수 없다"
trap 'rm -f "$list"' EXIT
wt_dump "$list"
wt_load "$list"

refs=()
for r in "refs/heads/$b" "refs/remotes/origin/$b"; do
  if git rev-parse --verify -q "$r" >/dev/null; then refs+=("$r"); fi
done
if [ ${#refs[@]} -eq 0 ]; then
  echo NO_BRANCH
  exit 0
fi
git rev-parse --verify -q refs/remotes/origin/main >/dev/null || die_env "origin/main 이 없다"

# <sha>가 refs 중 하나라도의 조상이면 0, 어느 것의 조상도 아니면 1, merge-base 가 오류(128)면 2.
on_branch() {
  local r rc
  for r in "${refs[@]}"; do
    git merge-base --is-ancestor "$1" "$r" 2>/dev/null
    rc=$?
    case $rc in
      0) return 0 ;;
      1) ;;
      *) return 2 ;;
    esac
  done
  return 1
}

# merge-base 오류의 원인이 "그 커밋이 없다"면 그 레코드만 빼고 계속한다 — 깨진 등록 하나가 판정 전체를
# 멈추면 그 레포의 머지 정리가 전부 막힌다. 그 밖의 오류(객체 DB 손상 등)면 판정을 못 믿으니 멈춘다.
skip_or_die() {
  if git cat-file -e "$1^{commit}" 2>/dev/null; then
    die_env "git merge-base --is-ancestor $1 가 실패했다"
  fi
}

hits=()
unreadable=()
for ((i = 0; i < WT_N; i++)); do
  if [ "${WT_BARE[$i]}" != 1 ] && [ -z "${WT_BRANCH[$i]}" ] && head_unreadable "$i"; then
    unreadable+=("$i")
    continue
  fi
  [ "${WT_DETACHED[$i]}" = 1 ] || continue
  sha=${WT_HEAD[$i]}
  on_branch "$sha"
  rc=$?
  case $rc in
    0) ;;
    1) continue ;;
    *)
      skip_or_die "$sha"
      unreadable+=("$i")
      continue
      ;;
  esac
  git merge-base --is-ancestor "$sha" refs/remotes/origin/main 2>/dev/null
  rc=$?
  case $rc in
    0) continue ;;
    1) hits+=("$i") ;;
    *)
      skip_or_die "$sha"
      unreadable+=("$i")
      ;;
  esac
done

if [ ${#hits[@]} -eq 0 ]; then echo NONE; else echo FOUND; fi
for r in "${refs[@]}"; do echo "ref $r"; done
for i in "${unreadable[@]}"; do print_path_line unreadable "${WT_PATH[$i]}"; done
for i in "${hits[@]}"; do wt_print "$i" detached; done
exit 0
