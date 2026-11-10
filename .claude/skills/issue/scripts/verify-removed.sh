#!/bin/bash
# remove 가 의도한 워크트리를 지웠는지, remove 직전 스냅숏과 지금 목록을 견줘 확인한다.
# remove 는 무엇을 지웠는지 알려주지 않으므로 이것이 비가역 명령에 대한 유일한 사후 방어다.
#
# 사용: verify-removed.sh <스냅숏 파일> <경로>
#   <스냅숏 파일>은 remove 직전에 find.sh 가 뜬 것, <경로>는 지우려던 레코드의 경로다.
#   remove 가 exit 0 으로 끝났을 때만 부른다 — 실패한 remove 뒤에 부르면 줄이 남아 있는 게
#   정상인데 STILL_PRESENT 가 나와 없는 사고로 읽힌다.
#
# stdout 첫 줄
#   REMOVED        그 레코드가 지금 목록에 없다. 다른 레코드도 사라졌으면 also-gone <경로> 줄
#                  (다른 세션이 지운 것일 수 있다 — 사고가 아니라 보고 거리다)
#   STILL_PRESENT  그 레코드가 그대로 있다. 사라진 레코드는 gone 줄 — gone 줄이 있으면 remove 가 다른 것을
#                  지웠다. 없으면 지운 직후 같은 경로가 같은 바이트로 다시 등록됐거나 prune 이 아무것도 안
#                  지운 것이다. 스냅숏과 지금 목록만으로는 이 셋을 가를 수 없어 한 키워드로 내고, 어느 쪽이든
#                  멈춘다(references/worktree.md 제거 절차 3번 "사후 확인")
#   REREGISTERED   같은 경로가 다른 바이트로 다시 등록돼 있다(누가 지웠다 다시 만들었다).
#                  사라진 레코드는 gone 줄
#
# 종료 코드: 0 판정함 · 2 사용법 · 3 환경 실패 — 스냅숏에서 <경로>가 정확히 하나로 안 잡히면
#   그 파일은 이 remove 의 기준선이 아니므로 여기로 온다

builtin unset -f -- $(builtin compgen -A function) || { echo "실패: 부른 셸에서 물려받은 함수를 지우지 못했다(lib.sh 머리말)" >&2; exit 3; }
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh" || exit 3
declare -F die_usage die_env rev_parse git_err_not_repo git_err_line lower_ascii norm is_unsafe \
  branch_unsafe ref_unsafe quote_c require_safe_branch head_unreadable has_non_ascii wt_dump wt_load \
  same_path_hits path_in_container print_checked_line print_path_line wt_print >/dev/null ||
  { echo "실패: lib.sh 에 판정 스크립트가 쓰는 함수가 없다 — 이 스크립트와 lib.sh 의 버전이 어긋났다(lib.sh 머리말)" >&2; exit 3; }

if [ $# -ne 2 ] || [ -z "$1" ] || [ -z "$2" ]; then
  die_usage "verify-removed.sh <스냅숏 파일> <경로>"
fi
[ -s "$1" ] || die_env "스냅숏 파일이 없거나 비었다: $1"

wt_load "$1"
same_path_hits "$2"
if [ ${#SAME_HITS[@]} -ne 1 ]; then
  die_env "스냅숏에서 경로가 ${#SAME_HITS[@]}개 레코드로 잡힌다(1개여야 한다) — remove 직전 스냅숏이 아니다"
fi
target=${WT_PATH[${SAME_HITS[0]}]}
target_norm=${WT_NORM[${SAME_HITS[0]}]}
B_PATH=("${WT_PATH[@]}")
B_N=$WT_N

live=$(mktemp "${TMPDIR:-/tmp}/issue-wt-live.XXXXXX") || die_env "임시 파일을 만들 수 없다"
trap 'rm -f "$live"' EXIT
wt_dump "$live"
wt_load "$live"

in_live() {
  local i
  for ((i = 0; i < WT_N; i++)); do
    [ "${WT_PATH[$i]}" = "$1" ] && return 0
  done
  return 1
}

state=REMOVED
if in_live "$target"; then
  state=STILL_PRESENT
else
  for ((i = 0; i < WT_N; i++)); do
    [ "${WT_NORM[$i]}" = "$target_norm" ] && state=REREGISTERED
  done
fi
echo "$state"

for ((j = 0; j < B_N; j++)); do
  p=${B_PATH[$j]}
  in_live "$p" && continue
  if [ "$state" = REMOVED ]; then
    [ "$p" = "$target" ] && continue
    print_path_line also-gone "$p"
  else
    print_path_line gone "$p"
  fi
done
exit 0
