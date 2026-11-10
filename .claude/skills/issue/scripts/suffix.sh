#!/bin/bash
# git worktree remove 에 넣을, 그 레코드 하나로만 풀리는 가장 짧은 ASCII 접미사를 낸다.
# 절대경로 remove 가 "is not a working tree" 로 실패했을 때(NFD 로 등록된 워크트리) 쓴다.
# 판정만 하고 아무것도 바꾸지 않는다.
#
# 사용: suffix.sh <스냅숏 파일> <경로>
#   목록을 새로 뜨지 않는다 — 바로 앞에서 find.sh 가 뜬 스냅숏을 읽는다.
#
# git 의 규칙: 인자를 먼저 등록 경로의 접미사(/ 경계에서 시작, 대소문자 무시)로 맞춰 보고,
# 맞는 것이 정확히 하나가 아니면(0개든 2개 이상이든) cwd 기준 경로로 다시 풀어 그 자리에
# 등록된 워크트리를 잡는다 — 무엇을 잡았는지 알려주지 않는다. 그래서 1 이 아니면 절대 내지
# 않는다. 비교는 늘 대소문자를 무시한다(core.ignorecase=false 인 곳에서는 더 길게 잡힐 뿐
# 안전하다).
#
# stdout 첫 줄
#   SUFFIX <접미사>    remove 인자로 그대로 쓴다
#   GONE               스냅숏에 그 경로의 레코드가 없다
#   AMBIGUOUS          그 경로로 레코드가 둘 이상이다
#   MAIN               본 체크아웃이다
#   UNSAFE             경로에 셸이 건드리는 문자가 있다
#   NON_ASCII          유일해지기 전에 ASCII 밖 조각에 닿았다 (정규화가 어긋나면 git 이 못 맞춘다)
#   NO_UNIQUE_SUFFIX   맨 앞 조각까지 붙여도 유일해지지 않는다
#
# 종료 코드: 0 판정함 · 2 사용법 · 3 환경 실패

builtin unset -f -- $(builtin compgen -A function) || { echo "실패: 부른 셸에서 물려받은 함수를 지우지 못했다(lib.sh 머리말)" >&2; exit 3; }
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh" || exit 3
declare -F die_usage die_env rev_parse git_err_not_repo git_err_line lower_ascii norm is_unsafe \
  branch_unsafe ref_unsafe quote_c require_safe_branch head_unreadable has_non_ascii wt_dump wt_load \
  same_path_hits path_in_container print_checked_line print_path_line wt_print >/dev/null ||
  { echo "실패: lib.sh 에 판정 스크립트가 쓰는 함수가 없다 — 이 스크립트와 lib.sh 의 버전이 어긋났다(lib.sh 머리말)" >&2; exit 3; }

if [ $# -ne 2 ] || [ -z "$1" ] || [ -z "$2" ]; then
  die_usage "suffix.sh <스냅숏 파일> <경로>"
fi
[ -s "$1" ] || die_env "스냅숏 파일이 없거나 비었다: $1"

wt_load "$1"
same_path_hits "$2"
case ${#SAME_HITS[@]} in
  0) echo GONE; exit 0 ;;
  1) t=${SAME_HITS[0]} ;;
  *) echo AMBIGUOUS; exit 0 ;;
esac
if [ "$t" -eq 0 ]; then echo MAIN; exit 0; fi

p=${WT_PATH[$t]}
if is_unsafe "$p"; then echo UNSAFE; exit 0; fi

count_suffix() {
  local ls i n=0
  ls=$(lower_ascii "$1")
  for ((i = 0; i < WT_N; i++)); do
    case "${WT_LOWER[$i]}" in
      "$ls" | */"$ls") n=$((n + 1)) ;;
    esac
  done
  echo "$n"
}

rest=$p
s=
while :; do
  comp=${rest##*/}
  case "$rest" in
    */*) rest=${rest%/*} ;;
    *) rest= ;;
  esac
  if [ -z "$comp" ]; then echo NO_UNIQUE_SUFFIX; exit 0; fi
  if has_non_ascii "$comp"; then echo NON_ASCII; exit 0; fi
  if [ -z "$s" ]; then s=$comp; else s="$comp/$s"; fi
  if [ "$(count_suffix "$s")" -eq 1 ]; then
    echo "SUFFIX $s"
    exit 0
  fi
  if [ -z "$rest" ]; then echo NO_UNIQUE_SUFFIX; exit 0; fi
done
