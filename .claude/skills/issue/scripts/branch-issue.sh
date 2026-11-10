#!/bin/bash
# cwd 가 이 레포의 이슈 워크트리 안인지 보고, 그 브랜치에 든 이슈 번호를 낸다. 판정만 한다.
#
# 사용: branch-issue.sh <레포 루트> [<이슈번호>]
#   <레포 루트>는 본 체크아웃 루트다 — skill-repo.sh 가 낸 path(SKILL.md "시작하기 전에").
#   <이슈번호>를 주면 브랜치의 번호와 같은지까지 본다.
#
# SKILL.md "이슈 워크트리"("시작하기 전에")가 요청에 레포를 가리킬 수 있는 말이 하나도 없을 때 쓴다. `/issue <번호>` 로 작업을 이어 하는 세션은
# 그 이슈의 워크트리에 서 있고, 번호 없는 "머지했어"를 받는 세션은 방금 PR 을 올린 그 워크트리에 서 있다.
# 대화 기억 대신 서 있는 자리로 가린다 — 대화는 요약되면 사라진다.
#
# 이슈 워크트리로 치는 것은 셋이 모두 맞을 때다.
#   - cwd 가 <레포 루트>의 레포 안이다 — 공유 .git(--git-common-dir)이 <레포 루트>/.git 과 같은 디렉터리다(same-repo.sh
#     와 같은 방법. 비교는 -ef 라 NFC/NFD 표기와 무관하다). 다른 레포에 같은 이름의 브랜치가 있어도 걸리지 않는다.
#   - 연결 워크트리다 — --git-dir 과 --git-common-dir 이 다른 디렉터리다(isolation-check.sh 와 같은 방법). 본 체크아웃이
#     우연히 그 이름의 브랜치에 있으면 이 스킬이 만든 워크트리가 아니다.
#   - 브랜치 이름이 이 스킬의 규약 `<타입>/<번호>-<슬러그>` 다(SKILL.md 1단계 — 슬러그는 영어 소문자·숫자·`-` 만). 옛 이름 꼴 `<타입>+<번호>-<슬러그>`·
#     `worktree-<타입>+<번호>-<슬러그>` 도 친다 — 이어받기가 push 된 옛 이름을 일부러 그대로 두고, 7단계도 그 꼴에서
#     이슈 번호를 뽑는다(references/merge-cleanup.md "대상 브랜치와 이슈 번호를 특정한다"). 타입은 이 레포
#     타입 라벨 다섯 feat·fix·docs·refactor·chore 다 — 1단계가 브랜치의 타입을 이슈의 타입 라벨로 정하고, residue.sh
#     가 옛 타입 폴더로 보는 것도 이 다섯이다. 명령에 넣을 수 없는 이름(lib.sh branch_unsafe)이면 치지 않는다 — 이 이름은 뒤에서 명령의
#     인자로 옮겨진다.
#
# stdout 첫 줄
#   <이슈번호> 없이
#     FOUND      이슈 워크트리 안이다. 다음 줄이 issue <번호>, 그다음이 branch <브랜치>
#     NONE       아니다. 다음 줄이 reason <까닭>
#   <이슈번호>와 함께
#     SAME       이슈 워크트리 안이고 브랜치의 번호가 <이슈번호>와 같다. 다음 줄들은 FOUND 와 같다
#     DIFFERENT  이슈 워크트리 안인데 번호가 다르다. 다음 줄들은 FOUND 와 같다
#     NONE       위와 같다
#   CWD_GONE     작업 디렉터리가 이미 지워졌다
#   reason 은 not-in-repo(레포 밖) · other-repo(다른 레포) · main-checkout(본 체크아웃이나 그 하위) · detached ·
#   not-convention(규약 밖 이름이거나 명령에 넣을 수 없는 이름) · dangling(브랜치 ref 가 지워져 등록과 폴더만 남았다 —
#   앞선 정리가 branch -D 까지 하고 멈춘 자리다. 이슈 작업을 이어 할 자리가 아니라 묻는다) 중 하나다.
# 종료 코드: 0 판정함 · 2 사용법(인자 개수, <레포 루트>/.git 디렉터리가 없다, <이슈번호>가 1 이상의 정수가 아니다)
# · 3 환경 실패(git 이 "레포가 아니다" 밖의 이유로 실패했다 — lib.sh rev_parse)

builtin unset -f -- $(builtin compgen -A function) || { echo "실패: 부른 셸에서 물려받은 함수를 지우지 못했다(lib.sh 머리말)" >&2; exit 3; }
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh" || exit 3
declare -F die_usage die_env rev_parse git_err_not_repo git_err_line lower_ascii norm is_unsafe \
  branch_unsafe ref_unsafe quote_c require_safe_branch head_unreadable has_non_ascii wt_dump wt_load \
  same_path_hits path_in_container print_checked_line print_path_line wt_print >/dev/null ||
  { echo "실패: lib.sh 에 판정 스크립트가 쓰는 함수가 없다 — 이 스크립트와 lib.sh 의 버전이 어긋났다(lib.sh 머리말)" >&2; exit 3; }

if [ $# -lt 1 ] || [ $# -gt 2 ] || [ -z "$1" ]; then
  die_usage "branch-issue.sh <레포 루트> [<이슈번호>]"
fi
[ -d "$1/.git" ] || die_usage "본 체크아웃 루트가 아니다(.git 디렉터리가 없다): $1"
want=
if [ $# -eq 2 ]; then
  case "$2" in
    '' | 0* | *[!0123456789]*) die_usage "이슈 번호는 1 이상의 정수다: $2" ;;
  esac
  want=$2
fi

none() {
  echo NONE
  echo "reason $1"
  exit 0
}

if ! pwd -P >/dev/null 2>&1; then
  echo CWD_GONE
  exit 0
fi
if ! rev_parse --path-format=absolute --git-dir --git-common-dir; then
  none not-in-repo
fi
dirs=$REV_OUT
# 한 번 불러 두 줄로 받는다(isolation-check.sh 와 같은 이유).
case "$dirs" in
  *$'\n'*$'\n'*) die_env "git 디렉터리 경로에 개행이 있어 판정하지 못했다" ;;
  *$'\n'*) ;;
  *) die_env "git rev-parse 가 두 줄을 내지 않았다: $dirs" ;;
esac
git_dir=${dirs%%$'\n'*}
common=${dirs#*$'\n'}
[ "$common" -ef "$1/.git" ] || none other-repo
[ "$git_dir" -ef "$common" ] && none main-checkout
# symbolic-ref -q 는 detached 면 1, 그 밖의 실패는 128 이다.
ref=$(git symbolic-ref -q HEAD 2>/dev/null)
rc=$?
case "$rc" in
  0) ;;
  1) none detached ;;
  *)
    # rev_parse(lib.sh)와 같은 머리 문구를 붙인다 — SKILL.md 는 이 문구로 "지금 자리의 git 이 깨졌다"를 가린다.
    err=$(LC_ALL=C git symbolic-ref -q HEAD 2>&1 >/dev/null)
    die_env "git 오류(레포 밖이 아니다): git symbolic-ref 가 종료 코드 $rc 로 실패했다 — $(git_err_line "$err")"
    ;;
esac
branch=${ref#refs/heads/}
[ "$branch" != "$ref" ] || none not-convention
branch_unsafe "$branch" && none not-convention
case "$branch" in
  feat/* | fix/* | docs/* | refactor/* | chore/*) rest=${branch#*/} ;;
  feat+* | fix+* | docs+* | refactor+* | chore+*) rest=${branch#*+} ;;
  worktree-feat+* | worktree-fix+* | worktree-docs+* | worktree-refactor+* | worktree-chore+*)
    rest=${branch#*+}
    ;;
  *) none not-convention ;;
esac
num=${rest%%-*}
# 번호 뒤에 - 와 슬러그가 있어야 한다. 0 으로 시작하는 번호는 이 스킬이 만들지 않는다.
case "$num" in
  '' | 0* | *[!0123456789]*) none not-convention ;;
esac
[ "$rest" != "$num" ] && [ -n "${rest#"$num"-}" ] || none not-convention
# 슬러그는 이 스킬이 짓는 꼴만 친다 — / 가 더 든 이름(fix/137-debug/sandbox)이나 대문자·점이 든 이름은 사람이 따로 만든
# 브랜치일 수 있고, 그 자리에서 번호 없는 "머지했어"를 받으면 묻지 않고 그 번호를 정리하게 된다(이전 codex 지적).
case "${rest#"$num"-}" in
  *[!abcdefghijklmnopqrstuvwxyz0123456789-]*) none not-convention ;;
esac
# symbolic-ref 는 HEAD 가 가리키는 이름만 읽어서, 그 ref 가 지워졌어도 이름을 낸다(lib.sh head_unreadable 이 다루는 자리).
# for-each-ref 는 없는 ref 에 빈 출력과 0 을 내고 git 이 깨졌을 때만 실패해, "지워졌다"와 "읽지 못했다"가 갈린다.
refs=$(git for-each-ref --format='%(refname)' "$ref" 2>/dev/null)
rc=$?
if [ "$rc" -ne 0 ]; then
  err=$(LC_ALL=C git for-each-ref --format='%(refname)' "$ref" 2>&1 >/dev/null)
  die_env "git 오류(레포 밖이 아니다): git for-each-ref 가 종료 코드 $rc 로 실패했다 — $(git_err_line "$err")"
fi
# 패턴은 그 아래 ref 도 잡으므로(refs/heads/docs/137-x/… ) 같은 이름이 있는지 줄로 본다.
case $'\n'"$refs"$'\n' in
  *$'\n'"$ref"$'\n'*) ;;
  *) none dangling ;;
esac
if [ -z "$want" ]; then
  echo FOUND
elif [ "$num" = "$want" ]; then
  echo SAME
else
  echo DIFFERENT
fi
echo "issue $num"
echo "branch $branch"
exit 0
