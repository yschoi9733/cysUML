#!/bin/bash
# 셀프 리뷰 루프의 셈 기록(SKILL.md 4단계 "셈 기록")을 읽는다. 판정만 한다 — 기록은 SKILL.md 가 시키는 printf 명령으로
# 세션이 쓴다.
#
# 사용: round-count.sh <루프>
#   <루프>는 review(4단계 루프 — scratchpad/issue-rounds) 나 rereview(6단계 재리뷰 루프 — scratchpad/issue-rereview-rounds)
#   다. 이슈 워크트리(연결 워크트리) 안에서 부른다 — 그 워크트리 최상위의 scratchpad/ 를 읽는다.
#
# 기록은 그 파일의 한 줄이고 꼴은 "counted=<센 라운드 수> cap=<상한> streak=<연속 3회 셈>" 이다(끝 줄바꿈은 없어도 되고
# 여럿이어도 뗀다). counted 가 cap 이상인 기록도 그대로 낸다 — 상한에 닿았거나 사람이 알려 준 셈이 상한을 넘은 것이고,
# SKILL.md 4단계 "이어받은 실행의 셈"이 첫 라운드 전에 묻는다. scratchpad/ 는 .gitignore 에 있어 커밋에 섞이지 않고, ignored-check.sh 는 이 두 파일을 지워도 되는 것으로
# 친다 — 워크트리를 지울 때 기록도 함께 지워진다. 그래서 지운 워크트리를 다시 붙이면 기록이 없다(NONE).
# 브랜치 설정(git config branch.<브랜치>.…)에 두지 않는 것은, 워크트리에 격리된 세션에서는 명령 가드가 공유 설정에 쓰는
# git config 를 거부해서다(실측 — --worktree·--file 로 써도 거부했고, Write 도구도 공유 .git 안의 파일은 거부했다).
#
# 본 체크아웃에서 부르면 판정하지 않는다 — 본 체크아웃의 scratchpad/ 는 어느 이슈의 것도 아니다. 연결 워크트리인지는
# --git-dir 과 --git-common-dir 이 다른지로 본다(branch-issue.sh·isolation-check.sh 와 같은 방법).
#
# stdout 첫 줄
#   FOUND   기록이 있고 읽을 수 있다. 다음 줄들이 counted <n>, cap <c>, streak <s>
#   NONE    기록 파일이 없다
#   BROKEN  기록을 읽을 수 없다. 다음 줄이 reason <까닭> — type(기록 파일이 일반 파일이 아니다 — 디렉터리·심볼릭 링크 등,
#           또는 scratchpad/ 가 심볼릭 링크이거나 디렉터리가 아니다) ·
#           format(꼴이 다르다 — 끝 줄바꿈을 뗀 뒤 줄이 둘 이상이거나 빈 파일이거나 NUL 이 들었거나, 숫자가 0 으로
#           시작하거나 네 자리를 넘는다) ·
#           range(cap 이 0 이거나 streak 가 3 을 넘는다)
# 종료 코드: 0 판정함 · 2 사용법(인자 개수, 모르는 <루프>) · 3 환경 실패(레포 밖이나 본 체크아웃에서 불렀다, git 이
# "레포가 아니다" 밖의 이유로 실패했다 — lib.sh rev_parse, 기록 파일을 읽지 못했다)

builtin unset -f -- $(builtin compgen -A function) || { echo "실패: 부른 셸에서 물려받은 함수를 지우지 못했다(lib.sh 머리말)" >&2; exit 3; }
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh" || exit 3
declare -F die_usage die_env rev_parse git_err_not_repo git_err_line lower_ascii norm is_unsafe \
  branch_unsafe ref_unsafe quote_c require_safe_branch head_unreadable has_non_ascii wt_dump wt_load \
  same_path_hits path_in_container print_checked_line print_path_line wt_print >/dev/null ||
  { echo "실패: lib.sh 에 판정 스크립트가 쓰는 함수가 없다 — 이 스크립트와 lib.sh 의 버전이 어긋났다(lib.sh 머리말)" >&2; exit 3; }

if [ $# -ne 1 ]; then
  die_usage "round-count.sh <루프(review|rereview)>"
fi
case "$1" in
  review) name=issue-rounds ;;
  rereview) name=issue-rereview-rounds ;;
  *) die_usage "루프는 review 나 rereview 다: $1" ;;
esac

if ! rev_parse --path-format=absolute --git-dir --git-common-dir --show-toplevel; then
  die_env "레포 밖에서 불렀다 — 이슈 워크트리 안에서 부른다"
fi
dirs=$REV_OUT
# 한 번 불러 세 줄로 받는다 — 경로에 개행이 있으면 줄을 갈라 읽을 수 없다.
case "$dirs" in
  *$'\n'*$'\n'*$'\n'*) die_env "git 경로에 개행이 있어 판정하지 못했다" ;;
  *$'\n'*$'\n'*) ;;
  *) die_env "git rev-parse 가 세 줄을 내지 않았다: $dirs" ;;
esac
git_dir=${dirs%%$'\n'*}
rest=${dirs#*$'\n'}
common=${rest%%$'\n'*}
top=${rest#*$'\n'}
if [ "$git_dir" -ef "$common" ]; then
  die_env "본 체크아웃에서 불렀다 — 이슈 워크트리 안에서 부른다"
fi

broken() {
  echo BROKEN
  echo "reason $1"
  exit 0
}

# scratchpad/ 자체가 링크이거나 디렉터리가 아니면 기록 파일이 없어도 type 이다 — 링크면 읽기도 쓰기(리다이렉트)도 그
# 너머로 가고, 파일이면 쓰기가 실패한다.
d=$top/scratchpad
if [ -L "$d" ] || { [ -e "$d" ] && [ ! -d "$d" ]; }; then
  broken type
fi
f=$d/$name
if [ ! -e "$f" ] && [ ! -L "$f" ]; then
  echo NONE
  exit 0
fi
if [ -L "$f" ] || [ ! -f "$f" ]; then
  broken type
fi
[ -r "$f" ] || die_env "기록 파일을 읽을 수 없다: $f"
# 명령 치환은 NUL 을 조용히 버린다(bash 3.2 는 경고도 없다) — 버린 뒤의 값이 꼴에 맞을 수 있으니 NUL 이 든 파일은 먼저
# 꼴이 다른 것으로 친다.
all=$(wc -c < "$f") || die_env "기록 파일을 읽지 못했다: $f"
# pipefail 이 없으면 파이프의 종료 코드가 wc 의 것이라 tr 의 읽기 실패가 format 으로 읽힌다.
nonul=$(set -o pipefail; LC_ALL=C tr -d '\000' < "$f" | wc -c) || die_env "기록 파일을 읽지 못했다: $f"
[ $((all)) -eq $((nonul)) ] || broken format
# 명령 치환은 끝 줄바꿈을 모두 뗀다 — 남은 값에 줄바꿈이 있으면 줄이 둘 이상이다.
v=$(cat "$f") || die_env "기록 파일을 읽지 못했다: $f"
case "$v" in
  *$'\n'*) broken format ;;
esac
re='^counted=(0|[123456789][0123456789]{0,3}) cap=(0|[123456789][0123456789]{0,3}) streak=(0|[123456789][0123456789]{0,3})$'
[[ $v =~ $re ]] || broken format
counted=${BASH_REMATCH[1]}
cap=${BASH_REMATCH[2]}
streak=${BASH_REMATCH[3]}
if [ "$cap" -eq 0 ] || [ "$streak" -gt 3 ]; then
  broken range
fi
echo FOUND
echo "counted $counted"
echo "cap $cap"
echo "streak $streak"
exit 0
