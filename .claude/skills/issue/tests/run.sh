#!/bin/bash
# /issue 판정 스크립트(scripts/) 테스트. 임시 디렉터리에 레포와 워크트리를 여러 모양으로
# 만들어 각 스크립트를 돌리고 기대값과 맞춘다. 끝나면 임시 디렉터리를 지운다.
#
# 사용: bash .claude/skills/issue/tests/run.sh
# 실패가 하나라도 있으면 종료 코드 1.

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
S=$(cd "$HERE/../scripts" && pwd -P)
T=$(mktemp -d "${TMPDIR:-/tmp}/issue-skill-test.XXXXXX") || exit 1
T=$(cd "$T" && pwd -P)
# 권한 테스트가 도중에 끊겨 000 으로 남은 디렉터리도 지울 수 있게 권한부터 되돌린다.
trap 'chmod -R u+rwx "$T" 2>/dev/null; rm -rf "$T"' EXIT

# 사용자 전역 설정(기본 브랜치·훅·서명 등)이 끼어들지 않게 한다.
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t

pass=0
fail=0
ok() { pass=$((pass + 1)); }
bad() { fail=$((fail + 1)); printf 'FAIL %s\n%s\n---\n' "$1" "$2"; }

# <cwd>에서 스크립트를 돌려 stdout+stderr 를 OUT, 종료 코드를 RC 에 담는다.
run() {
  local cwd=$1
  shift
  OUT=$(cd "$cwd" && bash "$@" 2>&1)
  RC=$?
}
# 삭제된 cwd 에서 돌린다.
run_in_deleted_cwd() {
  local dir=$1
  shift
  mkdir -p "$dir"
  OUT=$(cd "$dir" && rmdir "$dir" && bash "$@" 2>/dev/null)
  RC=$?
}
check() {
  if [ "$RC" -eq 0 ] && [ "${OUT%%$'\n'*}" = "$2" ]; then
    ok
  else
    bad "$1" "기대 첫 줄 [$2], rc=$RC, 출력:
$OUT"
  fi
}
check_rc() {
  if [ "$RC" -eq "$2" ]; then ok; else bad "$1" "기대 rc $2, rc=$RC, 출력:
$OUT"; fi
}
has() {
  if printf '%s\n' "$OUT" | LC_ALL=C grep -Fxq -- "$2"; then ok; else bad "$1" "없는 줄 [$2], 출력:
$OUT"; fi
}
hasnt() {
  if printf '%s\n' "$OUT" | LC_ALL=C grep -Fxq -- "$2"; then bad "$1" "있으면 안 되는 줄 [$2], 출력:
$OUT"; else ok; fi
}
has_prefix() {
  if printf '%s\n' "$OUT" | LC_ALL=C grep -q -- "^$2"; then ok; else bad "$1" "[$2] 로 시작하는 줄이 없다, 출력:
$OUT"; fi
}
count_lines() {
  local n
  n=$(printf '%s\n' "$OUT" | LC_ALL=C grep -Fxc -- "$2")
  if [ "$n" -eq "$3" ]; then ok; else bad "$1" "[$2] 줄이 ${n}개(기대 $3), 출력:
$OUT"; fi
}

setup_fail() { echo "준비 실패: $*" >&2; exit 1; }
g() { git -C "$R" "$@" >/dev/null 2>&1 || setup_fail "git $*"; }
add() { g worktree add -q --no-track "$1" -b "$2" origin/main; }

# ---------------------------------------------------------------- 준비
# 한글 디렉터리가 NFD 로 저장된 상태를 만든다(클론 자리가 한글 폴더 아래일 수 있다). 같은 디렉터리를 NFC 로도 부른다.
NFD_GUT=$(printf '\xe1\x84\x80\xe1\x85\xae\xe1\x86\xba')
NFC_GUT=$(printf '\xea\xb5\xbf')
R="$T/p-$NFD_GUT/repo"
RC_="$T/p-$NFC_GUT/repo"
C="$R/.claude/worktrees"
CC="$RC_/.claude/worktrees"
SNAP="$T/snap/wt.z"

git init -q --bare "$T/origin.git" || setup_fail "origin"
mkdir -p "$R" "$C"
g init -q -b main
g commit -q --allow-empty -m init
g remote add origin "$T/origin.git"
g push -q origin main
g fetch -q origin

add "$CC/fix+5-unique" fix/5-unique
mkdir -p "$CC/fix+5-unique/sub"
add "$CC/fix+1-a" fix/1-a
mkdir -p "$T/elsewhere/.claude/worktrees" "$T/upper"
add "$T/elsewhere/.claude/worktrees/fix+1-a" other/1-a
add "$T/upper/FIX+1-A" other/1-upper
git -C "$R" -c core.precomposeunicode=false worktree add -q --no-track "$C/fix+2-nfd" -b fix/2-nfd origin/main \
  >/dev/null 2>&1 || setup_fail "NFD 워크트리"
add "$CC/fix+3-detached" fix/3-detached
git -C "$CC/fix+3-detached" commit -q --allow-empty -m wip || setup_fail "wip 커밋"
git -C "$CC/fix+3-detached" checkout -q --detach || setup_fail "detach"
add "$CC/exp-4-other" fix/4-real
add "$CC/fix+6-locked" fix/6-locked
g worktree lock --reason "in use" "$CC/fix+6-locked"
add "$CC/fix+7-prunable" fix/7-prunable
rm -rf "$CC/fix+7-prunable"
add "$CC/fix+8-switched" fix/8-switched
git -C "$CC/fix+8-switched" switch -q -c fix/8-elsewhere || setup_fail "switch"
mkdir -p "$C/fix+9-orphan"
touch "$C/fix+9-orphan/.DS_Store"
mkdir -p "$C/fix+10-work"
touch "$C/fix+10-work/draft.py"
mkdir -p "$C/fix/11-nested/app"
mkdir -p "$C/unrelated-dir"
add "$CC/wip-\$USER-old" fix/12-unsafe
add "$T/k1-$NFC_GUT/same/dupname" k/1
add "$T/k2-$NFC_GUT/same/dupname" k/2
add "$CC/fix+24-ghost" fix/24-ghost
rm -rf "$CC/fix+24-ghost"
g update-ref -d refs/heads/fix/24-ghost
g branch fix/111-x origin/main
g branch feat/300-fix+1-a origin/main
g branch worktree-fix+1-legacy origin/main
g branch fix/16-remote origin/main
g push -q origin fix/16-remote fix/5-unique
g branch -D fix/16-remote
g fetch -q --prune origin

R2="$T/repo2"
mkdir -p "$R2"
git -C "$R2" init -q -b main && git -C "$R2" commit -q --allow-empty -m init &&
  git -C "$R2" switch -q -c fix/13-main || setup_fail "repo2"

# ---------------------------------------------------------------- same-repo.sh
run "$R" "$S/same-repo.sh" "$R"
check "same-repo: 본 체크아웃" SAME_REPO
run "$RC_" "$S/same-repo.sh" "$R"
check "same-repo: 같은 디렉터리를 NFC 표기로 연 cwd" SAME_REPO
run "$R/.claude" "$S/same-repo.sh" "$R"
check "same-repo: 본 체크아웃 하위(--git-common-dir 이 상대경로로 나오는 자리)" SAME_REPO
run "$CC/fix+5-unique" "$S/same-repo.sh" "$R"
check "same-repo: 연결 워크트리" SAME_REPO
run "$CC/fix+5-unique/sub" "$S/same-repo.sh" "$R"
check "same-repo: 연결 워크트리 하위" SAME_REPO
run "$R2" "$S/same-repo.sh" "$R"
check "same-repo: 다른 레포 안" OTHER_REPO
run "$T" "$S/same-repo.sh" "$R"
check "same-repo: 레포 밖" NOT_IN_REPO
# git 이 "레포가 아니다" 밖의 이유로 실패하면 레포 밖으로 읽지 않고 멈춘다 — 지워진 등록을 가리키는 .git 파일.
mkdir -p "$T/same-repo-broken"
printf 'gitdir: %s\n' "$T/same-repo-nowhere/.git/worktrees/x" > "$T/same-repo-broken/.git"
run "$T/same-repo-broken" "$S/same-repo.sh" "$R"
check_rc "same-repo: 깨진 .git 파일은 환경 실패" 3
hasnt "same-repo: 그때 NOT_IN_REPO 를 내지 않는다" "NOT_IN_REPO"
# SKILL.md "시작하기 전에"가 이 문구로 "작업 디렉터리의 git 이 깨졌다"를 가린다.
has_prefix "same-repo: 그 stderr 는 git 오류다" "실패: git 오류(레포 밖이 아니다): fatal: "
# 임시 디렉터리에 못 써도 판정을 낸다 — 판정 전에 임시 파일을 만들면 그 실패가 "git 이 깨졌다"(종료 코드 3)로
# 읽힌다. 셋 다 앞으로 그러지 않게 지키는 회귀 방지다(한때 isolation-check.sh 만 임시 파일을 썼다).
run "$T" -c 'TMPDIR="$1" bash "$2" "$3"' _ "$T/no-such-tmp" "$S/same-repo.sh" "$R"
check "same-repo: 임시 디렉터리에 못 써도 판정한다" NOT_IN_REPO
run "$T" -c 'TMPDIR="$1" bash "$2" "$3"' _ "$T/no-such-tmp" "$S/skill-repo.sh" "$T"
check "skill-repo: 임시 디렉터리에 못 써도 판정한다" NOT_IN_REPO
run "$T" -c 'TMPDIR="$1" bash "$2"' _ "$T/no-such-tmp" "$S/isolation-check.sh"
check "isolation: 임시 디렉터리에 못 써도 판정한다" MOVABLE
run_in_deleted_cwd "$T/gone-1" "$S/same-repo.sh" "$R"
check "same-repo: cwd 가 지워짐" CWD_GONE
run "$R" "$S/same-repo.sh" "$CC/fix+5-unique"
check_rc "same-repo: 루트 자리에 연결 워크트리를 넘김" 2

# ---------------------------------------------------------------- skill-repo.sh
# 스킬이 든 레포의 본 체크아웃을 git 에 물어 구한다 — 스킬 경로 문자열을 잘라 구하면 .claude/worktrees/ 밖에 둔
# 워크트리에서 연결 워크트리 자체가 나와 same-repo.sh 가 사용법 오류로 멈췄다(이전 codex 지적).
# 공용 레포에 워크트리를 더하면 뒤 테스트의 등록 목록이 달라지므로 레포를 따로 만든다.
RS="$T/skill-repo-main"
git init -q -b main "$RS" || setup_fail "skill-repo 레포"
git -C "$RS" commit -q --allow-empty -m init || setup_fail "skill-repo 레포 커밋"
mkdir -p "$RS/.claude/skills/issue"
git -C "$RS" worktree add -q "$T/skill-repo-outside" -b out/1 || setup_fail "skill-repo 바깥 워크트리"
mkdir -p "$T/skill-repo-outside/.claude/skills/issue"
ln -s "$T/skill-repo-outside" "$T/skill-repo-link"
skill_root_is() {
  local label=$1 want=$2 p
  p=$(printf '%s\n' "$OUT" | sed -n 's/^path //p')
  if [ -n "$p" ] && [ "$p" -ef "$want" ]; then ok; else bad "$label" "$OUT"; fi
}
run "$T" "$S/skill-repo.sh" "$RS/.claude/skills/issue"
check "skill-repo: 본 체크아웃의 스킬" FOUND
skill_root_is "skill-repo: 그 레포 루트를 낸다" "$RS"
run "$T" "$S/skill-repo.sh" "$T/skill-repo-outside/.claude/skills/issue"
check "skill-repo: .claude/worktrees 밖 워크트리의 스킬" FOUND
skill_root_is "skill-repo: 그때도 연결 워크트리가 아니라 본 체크아웃을 낸다" "$RS"
run "$T" "$S/skill-repo.sh" "$T/skill-repo-link/.claude/skills/issue"
check "skill-repo: 링크를 거친 경로" FOUND
skill_root_is "skill-repo: 링크를 거쳐도 본 체크아웃을 낸다" "$RS"
run "$T" "$S/skill-repo.sh" "$CC/fix+5-unique"
check "skill-repo: .claude/worktrees 안 워크트리" FOUND
skill_root_is "skill-repo: 그 레포의 본 체크아웃" "$R"
run "$R2" "$S/skill-repo.sh" "$RS/.claude/skills/issue"
check "skill-repo: 다른 레포 안에서 불러도" FOUND
skill_root_is "skill-repo: 작업 디렉터리와 무관하다" "$RS"
# 상대경로 인자에 CDPATH 가 걸려도 작업 디렉터리 기준으로 푼다 — 안 비우면 cd 가 CDPATH 쪽 같은 이름으로 가고
# 그 자리를 stdout 에 찍어 출력이 섞인다.
git init -q -b main "$T/skill-repo-other" || setup_fail "skill-repo CDPATH 레포"
mkdir -p "$T/skill-repo-other/.claude/skills/issue"
run "$RS" -c 'CDPATH="$1" bash "$2" .claude/skills/issue' _ "$T/skill-repo-other" "$S/skill-repo.sh"
check "skill-repo: CDPATH 가 있어도" FOUND
skill_root_is "skill-repo: CDPATH 쪽이 아니라 작업 디렉터리 기준" "$RS"
# 공유 .git 이 <루트>/.git 꼴이 아니면 본 체크아웃을 구하지 못한 것이니 환경 실패로 멈춘다.
git init -q -b main --separate-git-dir "$T/skill-repo-sep.git" "$T/skill-repo-sep" || setup_fail "skill-repo separate-git-dir 레포"
run "$T" "$S/skill-repo.sh" "$T/skill-repo-sep"
check_rc "skill-repo: 공유 .git 이 <루트>/.git 꼴이 아니면 환경 실패" 3
run "$T" "$S/skill-repo.sh" "$T/skill-repo-nowhere"
check "skill-repo: 없는 디렉터리" GONE
mkdir -p "$T/skill-repo-norepo"
run "$T" "$S/skill-repo.sh" "$T/skill-repo-norepo"
check "skill-repo: 레포 밖" NOT_IN_REPO
mkdir -p "$T/skill-repo-broken"
printf 'gitdir: %s\n' "$T/skill-repo-nowhere/.git/worktrees/x" > "$T/skill-repo-broken/.git"
run "$T" "$S/skill-repo.sh" "$T/skill-repo-broken"
check_rc "skill-repo: 깨진 .git 파일은 환경 실패" 3
hasnt "skill-repo: 그때 NOT_IN_REPO 를 내지 않는다" "NOT_IN_REPO"
has_prefix "skill-repo: 그 stderr 는 git 오류다" "실패: git 오류(레포 밖이 아니다): fatal: "
run "$T" "$S/skill-repo.sh"
check_rc "skill-repo: 인자 없음" 2
# 없는 것만 GONE 이다 — 파일을 넘기면 사용법 오류다(GONE 이면 문서가 앞선 요청의 루트를 다시 쓰게 해 실수를 가린다).
run "$T" "$S/skill-repo.sh" "$RS/.claude/skills/issue/../../../.git/HEAD"
check_rc "skill-repo: 디렉터리가 아닌 경로" 2
ln -s "$T/skill-repo-nowhere-target" "$T/skill-repo-dangling"
run "$T" "$S/skill-repo.sh" "$T/skill-repo-dangling"
check_rc "skill-repo: 끊긴 링크" 2
# 들어가지 못하는 디렉터리는 레포 밖이 아니라 환경 실패다. root 는 000 폴더도 열므로 root 가 아닐 때만.
if [ "$(id -u)" -ne 0 ]; then
  mkdir -p "$RS/locked-skill"
  chmod 000 "$RS/locked-skill"
  run "$T" "$S/skill-repo.sh" "$RS/locked-skill"
  chmod 755 "$RS/locked-skill"
  check_rc "skill-repo: 들어가지 못하는 디렉터리는 환경 실패" 3
  hasnt "skill-repo: 그때 NOT_IN_REPO 를 내지 않는다" "NOT_IN_REPO"
fi
RU="$T/skill-repo-\$unsafe"
git init -q -b main "$RU" || setup_fail "skill-repo 셸 문자 레포"
run "$T" "$S/skill-repo.sh" "$RU"
check "skill-repo: 셸 문자가 든 루트" FOUND
has_prefix "skill-repo: 그 루트는 명령에 옮기지 않게 escaped 로" "path-escaped "

# ---------------------------------------------------------------- isolation-check.sh
# 옮겨도 되는 세션인지 서 있는 자리로 가린다. 연결 워크트리는 --git-dir 과 --git-common-dir 이 다른지로 본다 —
# --git-dir 에 /.git/worktrees/ 가 있는지만 보면 공유 git 디렉터리 이름이 .git 이 아닌 레포의 워크트리를 놓친다.
# 그 경로 검사도 함께 둔다 — 연결 워크트리 안의 서브모듈은 두 값이 같은 디렉터리라 앞의 비교로는 안 걸린다.
run "$R" "$S/isolation-check.sh"
check "isolation: 본 체크아웃" MOVABLE
run "$R/.claude" "$S/isolation-check.sh"
check "isolation: 본 체크아웃 하위(.claude)" MOVABLE
run "$CC/fix+5-unique" "$S/isolation-check.sh"
check "isolation: .claude/worktrees 안 워크트리" ISOLATED
has "isolation: 그 이유는 경로" "reason worktree-path"
mkdir -p "$CC/isolation-empty"
run "$CC/isolation-empty" "$S/isolation-check.sh"
check "isolation: .claude/worktrees 아래 등록 없는 빈 폴더도 격리로 친다" ISOLATED
rmdir "$CC/isolation-empty"
run "$T/skill-repo-outside" "$S/isolation-check.sh"
check "isolation: .claude/worktrees 밖에 등록된 워크트리" ISOLATED
has "isolation: 그 이유는 연결 워크트리" "reason linked-worktree"
run "$CC" "$S/isolation-check.sh"
check "isolation: 컨테이너 폴더 자체는 워크트리 안이 아니다" MOVABLE
# 대소문자만 다른 경로로 들어와도 경로로 걸린다 — 대소문자를 가리지 않는 볼륨에서만 그 경로가 열린다. 열리지 않으면
# 조용히 건너뛰지 않고 실패로 알린다 — 대소문자를 구분하는 볼륨이거나 픽스처가 깨진 것이다.
upper_cc="${CC%/.claude/worktrees}/.CLAUDE/WORKTREES"
if [ -d "$upper_cc/fix+5-unique" ]; then
  run "$upper_cc/fix+5-unique" "$S/isolation-check.sh"
  check "isolation: 대소문자만 다른 경로" ISOLATED
  has "isolation: 그것도 경로로 걸린다" "reason worktree-path"
else
  bad "isolation: 대소문자만 다른 경로" "$upper_cc/fix+5-unique 가 열리지 않는다 — 대소문자를 구분하는 볼륨이거나 픽스처가 깨졌다"
fi
ln -s "$CC/fix+5-unique" "$T/isolation-link"
run "$T/isolation-link" "$S/isolation-check.sh"
check "isolation: 링크를 거쳐 들어간 .claude/worktrees 안 워크트리" ISOLATED
has "isolation: 실제 경로로 걸린다" "reason worktree-path"
# 반대로 논리 경로만 .claude/worktrees/ 아래인 경우 — 그 안의 링크가 레포 밖 폴더를 가리킨다. 실제 경로만 보면
# 레포 밖이라 MOVABLE 로 통과한다(논리 경로 검사를 빼도 다른 테스트가 모두 통과했다).
mkdir -p "$T/isolation-outside"
ln -s "$T/isolation-outside" "$CC/isolation-logical"
run "$CC/isolation-logical" "$S/isolation-check.sh"
rm "$CC/isolation-logical"
check "isolation: 논리 경로만 .claude/worktrees 안" ISOLATED
has "isolation: 그것도 경로로 걸린다(논리 경로)" "reason worktree-path"
run "$T/skill-repo-link" "$S/isolation-check.sh"
check "isolation: 링크를 거쳐 들어간 바깥 워크트리" ISOLATED
has "isolation: 그것은 연결 워크트리로 걸린다" "reason linked-worktree"
git init -q -b main --separate-git-dir "$T/isolation-sep.git" "$T/isolation-sep" || setup_fail "isolation separate-git-dir 레포"
git -C "$T/isolation-sep" commit -q --allow-empty -m init || setup_fail "isolation separate-git-dir 커밋"
git -C "$T/isolation-sep" worktree add -q "$T/isolation-sep-wt" -b w/1 || setup_fail "isolation separate-git-dir 워크트리"
run "$T/isolation-sep-wt" "$S/isolation-check.sh"
check "isolation: 공유 git 디렉터리 이름이 .git 이 아닌 레포의 워크트리" ISOLATED
has "isolation: 그것도 연결 워크트리로" "reason linked-worktree"
run "$T/isolation-sep" "$S/isolation-check.sh"
check "isolation: 그 레포의 본 체크아웃" MOVABLE
# 서브모듈 배치를 흉내 낸다 — git 디렉터리를 연결 워크트리의 git 디렉터리 아래 modules/ 에 둔 레포.
git init -q -b main "$T/isolation-sup" || setup_fail "isolation 서브모듈 상위 레포"
git -C "$T/isolation-sup" commit -q --allow-empty -m init || setup_fail "isolation 서브모듈 상위 커밋"
git -C "$T/isolation-sup" worktree add -q "$T/isolation-sup-wt" -b w/1 || setup_fail "isolation 서브모듈 상위 워크트리"
sup_wt_gitdir=$(git -C "$T/isolation-sup-wt" rev-parse --path-format=absolute --git-dir) ||
  setup_fail "isolation 서브모듈 상위 워크트리의 git 디렉터리"
mkdir -p "$sup_wt_gitdir/modules" "$T/isolation-sup/.git/modules"
git init -q -b main --separate-git-dir "$sup_wt_gitdir/modules/lib" "$T/isolation-sup-wt/vendor/lib" ||
  setup_fail "isolation 서브모듈"
run "$T/isolation-sup-wt/vendor/lib" "$S/isolation-check.sh"
check "isolation: 바깥 연결 워크트리 안의 서브모듈" ISOLATED
has "isolation: 서브모듈은 경로로 연결 워크트리에 걸린다" "reason linked-worktree"
git init -q -b main --separate-git-dir "$T/isolation-sup/.git/modules/lib" "$T/isolation-sup/vendor/lib" ||
  setup_fail "isolation 본 체크아웃 서브모듈"
run "$T/isolation-sup/vendor/lib" "$S/isolation-check.sh"
check "isolation: 본 체크아웃 안의 서브모듈" MOVABLE
run "$T/skill-repo-norepo" "$S/isolation-check.sh"
check "isolation: 레포 밖" MOVABLE
run_in_deleted_cwd "$T/isolation-gone" "$S/isolation-check.sh"
check "isolation: 작업 디렉터리가 지워짐" CWD_GONE
run "$R" "$S/isolation-check.sh" x
check_rc "isolation: 인자를 받지 않는다" 2
# git 이 "레포가 아니다" 밖의 이유로 실패하면 MOVABLE 로 통과시키지 않고 멈춘다 — 지워진 등록을 가리키는 .git 파일.
mkdir -p "$T/isolation-broken"
printf 'gitdir: %s\n' "$T/isolation-nowhere/.git/worktrees/x" > "$T/isolation-broken/.git"
run "$T/isolation-broken" "$S/isolation-check.sh"
check_rc "isolation: 지워진 등록을 가리키는 .git 파일은 환경 실패" 3
hasnt "isolation: 그때 MOVABLE 을 내지 않는다" "MOVABLE"
has_prefix "isolation: 그 stderr 는 git 오류다" "실패: git 오류(레포 밖이 아니다): fatal: "
# git rev-parse 를 한 번 불러 두 줄로 받으므로, git 디렉터리 경로에 개행이 있으면 줄을 갈라 읽을 수 없다 — 판정하지
# 않고 멈춘다.
NL_REPO="$T/isolation-nl"$'\n'"repo"
git init -q -b main "$NL_REPO" || setup_fail "isolation 개행 경로 레포"
run "$NL_REPO" "$S/isolation-check.sh"
check_rc "isolation: git 디렉터리 경로에 개행이 있으면 환경 실패" 3
hasnt "isolation: 그때 MOVABLE 을 내지 않는다(개행)" "MOVABLE"
# lib.sh git_err_not_repo 는 파일 시스템 경계에서 멈춘 문구도 레포 밖으로 친다 — 실제 경계는 테스트에서 만들기 어려워
# git 이 내는 문구 그대로 본다. 지워진 등록을 가리키는 .git 파일의 문구는 레포 밖이 아니다.
not_repo_msg() { (. "$S/lib.sh" && git_err_not_repo "$1"); }
if not_repo_msg "fatal: not a git repository (or any parent up to mount point /Volumes/x)"$'\n'"Stopping at filesystem boundary (GIT_DISCOVERY_ACROSS_FILESYSTEM not set)."; then
  ok
else
  bad "lib: 파일 시스템 경계에서 멈춘 문구는 레포 밖" "git_err_not_repo 가 거짓을 냈다"
fi
if not_repo_msg "fatal: not a git repository: (null)"; then
  bad "lib: 지워진 등록을 가리키는 .git 파일 문구는 레포 밖이 아니다" "git_err_not_repo 가 참을 냈다"
else
  ok
fi

# ---------------------------------------------------------------- branch-issue.sh
# 요청이 레포를 밝히지 않았을 때 쓰는 신호다 — 이 레포의 연결 워크트리이고 브랜치가 <타입>/<번호>-<슬러그> 일 때만
# 이슈 번호를 낸다. 워크트리를 여럿 더하므로 공용 레포가 아니라 따로 만든 레포에서 본다.
RB="$T/branch-issue-main"
BC="$RB/.claude/worktrees"
git init -q -b main "$RB" || setup_fail "branch-issue 레포"
git -C "$RB" commit -q --allow-empty -m init || setup_fail "branch-issue 레포 커밋"
bi_add() { git -C "$RB" worktree add -q "$@" >/dev/null 2>&1 || setup_fail "branch-issue 워크트리 $*"; }
bi_add "$BC/docs+137-x" -b docs/137-x
mkdir -p "$BC/docs+137-x/sub"
bi_add "$T/bi-outside" -b fix/21-out
bi_add "$BC/bi-test" -b test/26-x
bi_add "$BC/bi-legacy" -b fix+31-legacy
bi_add "$BC/bi-legacy2" -b worktree-fix+32-legacy
bi_add --detach "$BC/bi-detached"
bi_add "$BC/bi-feature" -b feature/22-x
bi_add "$BC/bi-noslug" -b fix/23
bi_add "$BC/bi-dash" -b fix/29-
bi_add "$BC/bi-zero" -b fix/024-x
bi_add "$BC/bi-unsafe" -b 'fix/25-a$b'
bi_add "$BC/bi-nested" -b fix/40-debug/sandbox
bi_add "$BC/bi-upper" -b fix/41-Upper
bi_add "$BC/bi-dot" -b fix/42-a.b
bi_add "$BC/bi-dangling" -b fix/34-dangling
git -C "$RB" update-ref -d refs/heads/fix/34-dangling || setup_fail "branch-issue 브랜치 ref 지우기"
git -C "$RB" switch -q -c fix/27-main || setup_fail "branch-issue 본 체크아웃 브랜치"
# 다른 레포도 따로 만든다 — 공용 레포에 워크트리 등록을 더하면 뒤의 테스트가 그 등록을 본다.
git init -q -b main "$T/bi-other" || setup_fail "branch-issue 다른 레포"
git -C "$T/bi-other" commit -q --allow-empty -m init || setup_fail "branch-issue 다른 레포 커밋"
git -C "$T/bi-other" worktree add -q "$T/bi-r2wt" -b fix/28-other >/dev/null 2>&1 || setup_fail "branch-issue 다른 레포 워크트리"
run "$BC/docs+137-x" "$S/branch-issue.sh" "$RB"
check "branch-issue: 이슈 워크트리" FOUND
has "branch-issue: 이슈 번호를 낸다" "issue 137"
has "branch-issue: 브랜치를 낸다" "branch docs/137-x"
run "$BC/docs+137-x/sub" "$S/branch-issue.sh" "$RB"
check "branch-issue: 이슈 워크트리 하위" FOUND
run "$BC/docs+137-x" "$S/branch-issue.sh" "$RB" 137
check "branch-issue: 받은 번호와 같다" SAME
has "branch-issue: 같을 때도 번호를 낸다" "issue 137"
run "$BC/docs+137-x" "$S/branch-issue.sh" "$RB" 98
check "branch-issue: 받은 번호와 다르다" DIFFERENT
has "branch-issue: 다를 때도 브랜치를 낸다" "branch docs/137-x"
run "$T/bi-outside" "$S/branch-issue.sh" "$RB"
check "branch-issue: .claude/worktrees 밖의 연결 워크트리도 친다" FOUND
has "branch-issue: 그 번호" "issue 21"
run "$BC/bi-test" "$S/branch-issue.sh" "$RB"
check "branch-issue: test 타입(라벨 다섯 밖의 어휘)" FOUND
# 7단계가 이슈 번호를 뽑는 옛 이름 꼴도 친다(merge-cleanup.md "대상 브랜치와 이슈 번호를 특정한다").
run "$BC/bi-legacy" "$S/branch-issue.sh" "$RB" 31
check "branch-issue: 옛 이름 꼴 <타입>+<번호>-…" SAME
has "branch-issue: 옛 이름 꼴의 브랜치" "branch fix+31-legacy"
run "$BC/bi-legacy2" "$S/branch-issue.sh" "$RB" 32
check "branch-issue: 옛 이름 꼴 worktree-<타입>+<번호>-…" SAME
run "$RB" "$S/branch-issue.sh" "$RB" 27
check "branch-issue: 본 체크아웃이 규약 이름의 브랜치에 있어도 신호가 아니다" NONE
has "branch-issue: 그 까닭" "reason main-checkout"
run "$BC/bi-detached" "$S/branch-issue.sh" "$RB"
check "branch-issue: detached" NONE
has "branch-issue: detached 까닭" "reason detached"
# 브랜치 ref 가 지워진 워크트리는 이슈 작업을 이어 할 자리가 아니다 — 앞선 정리가 branch -D 까지 하고 멈춘 자리다.
run "$BC/bi-dangling" "$S/branch-issue.sh" "$RB" 34
check "branch-issue: 브랜치 ref 가 지워진 워크트리" NONE
has "branch-issue: 그 까닭" "reason dangling"
# 같은 이름 아래의 ref(refs/heads/fix/34-dangling/x)가 있어도 그 이름의 ref 가 없으면 지워진 것이다.
git -C "$RB" update-ref refs/heads/fix/34-dangling/x HEAD || setup_fail "branch-issue 아래 ref"
run "$BC/bi-dangling" "$S/branch-issue.sh" "$RB" 34
check "branch-issue: 같은 이름 아래의 ref 만 있어도 지워진 것" NONE
git -C "$RB" update-ref -d refs/heads/fix/34-dangling/x || setup_fail "branch-issue 아래 ref 지우기"
# 슬러그에 / 가 더 들었거나 대문자·점이 든 이름도 이 스킬이 지은 이름이 아니다(이전 codex 지적).
for d in bi-feature bi-noslug bi-dash bi-zero bi-unsafe bi-nested bi-upper bi-dot; do
  run "$BC/$d" "$S/branch-issue.sh" "$RB"
  check "branch-issue: 규약 밖 이름은 신호가 아니다($d)" NONE
  has "branch-issue: 규약 밖 까닭($d)" "reason not-convention"
done
run "$T/bi-other" "$S/branch-issue.sh" "$RB" 13
check "branch-issue: 다른 레포의 본 체크아웃" NONE
has "branch-issue: 다른 레포 까닭" "reason other-repo"
run "$T/bi-r2wt" "$S/branch-issue.sh" "$RB" 28
check "branch-issue: 다른 레포의 연결 워크트리는 규약 이름이어도 신호가 아니다" NONE
has "branch-issue: 다른 레포 워크트리 까닭" "reason other-repo"
run "$T/skill-repo-norepo" "$S/branch-issue.sh" "$RB"
check "branch-issue: 레포 밖" NONE
has "branch-issue: 레포 밖 까닭" "reason not-in-repo"
run_in_deleted_cwd "$T/bi-gone" "$S/branch-issue.sh" "$RB"
check "branch-issue: 작업 디렉터리가 지워짐" CWD_GONE
run "$RB" "$S/branch-issue.sh"
check_rc "branch-issue: 레포 루트 없이 부르면 사용법 오류" 2
run "$RB" "$S/branch-issue.sh" "$T/skill-repo-norepo"
check_rc "branch-issue: 레포 루트에 .git 디렉터리가 없으면 사용법 오류" 2
for bad_num in 0 01 abc -1 ''; do
  run "$RB" "$S/branch-issue.sh" "$RB" "$bad_num"
  check_rc "branch-issue: 이슈 번호가 1 이상의 정수가 아니면 사용법 오류([$bad_num])" 2
done
run "$RB" "$S/branch-issue.sh" "$RB" 1 2
check_rc "branch-issue: 인자가 셋이면 사용법 오류" 2
# 한글 경로의 레포에서 cwd 와 레포 루트의 정규화 표기가 달라도 같은 레포로 본다 — 견주기는 -ef 다.
run "$CC/fix+5-unique" "$S/branch-issue.sh" "$R" 5
check "branch-issue: cwd 는 NFC, 레포 루트는 NFD 표기" SAME
run "$C/fix+5-unique" "$S/branch-issue.sh" "$RC_" 5
check "branch-issue: cwd 는 NFD, 레포 루트는 NFC 표기" SAME
# symbolic-ref 가 "detached"(1) 밖의 이유로 실패하면 rev_parse(lib.sh)와 같은 머리 문구로 멈춘다 — SKILL.md 는 이
# 문구로 "지금 자리의 git 이 깨졌다"를 가린다. 그 실패를 실제로 만들기 어려워 git 을 감싼 가짜로 낸다.
mkdir -p "$T/bi-fakegit"
printf '%s\n' '#!/bin/bash' \
  'if [ "$1" = symbolic-ref ]; then echo "fatal: fake symbolic-ref failure" >&2; exit 128; fi' \
  "exec $(command -v git) \"\$@\"" > "$T/bi-fakegit/git"
chmod +x "$T/bi-fakegit/git"
run "$BC/docs+137-x" -c 'PATH="$1:$PATH" bash "${@:2}"' _ "$T/bi-fakegit" "$S/branch-issue.sh" "$RB"
check_rc "branch-issue: symbolic-ref 가 128 로 실패하면 환경 실패" 3
has_prefix "branch-issue: symbolic-ref 실패의 stderr" "실패: git 오류(레포 밖이 아니다): git symbolic-ref 가 종료 코드 128 로 실패했다 — fatal: fake symbolic-ref failure"

# ---------------------------------------------------------------- inside.sh
run "$CC/fix+5-unique" "$S/inside.sh" "$C/fix+5-unique"
check "inside: 대상 자신(cwd NFC, 인자 NFD)" INSIDE
run "$CC/fix+5-unique/sub" "$S/inside.sh" "$C/fix+5-unique"
check "inside: 대상 하위" INSIDE
run "$C" "$S/inside.sh" "$C/fix+5-unique"
check "inside: 대상 상위" OUTSIDE
run "$R" "$S/inside.sh" "$T/nope"
check "inside: 없는 대상" OUTSIDE
run_in_deleted_cwd "$T/gone-2" "$S/inside.sh" "$R"
check "inside: cwd 가 지워짐(예전 순회가 무한 루프였던 자리)" CWD_GONE

# ---------------------------------------------------------------- find.sh
run "$R" "$S/find.sh" "$SNAP" fix/5-unique
check "find: 규약 이름" FOUND
has "find: 규약 이름 — 경로" "path $CC/fix+5-unique"
has "find: 규약 이름 — 찾은 방법" "match name+branch"
has "find: 규약 이름 — 컨테이너 안" "container in"
if [ -s "$SNAP" ]; then ok; else bad "find: 스냅숏 파일" "비었다"; fi
run "$R" "$S/find.sh" "$SNAP" fix/1-a
check "find: 같은 이름이 레포 밖에, 대소문자만 달리 또 있음" AMBIGUOUS
run "$R" "$S/find.sh" "$SNAP" fix/2-nfd
check "find: NFD 로 등록된 워크트리" FOUND
has "find: NFD 등록 — 등록 바이트 그대로 낸다" "path $C/fix+2-nfd"
run "$R" "$S/find.sh" "$SNAP" fix/3-detached
check "find: 이름으로 찾은 detached" FOUND
has "find: detached 표시" "detached"
has "find: detached — 찾은 방법" "match name"
run "$R" "$S/find.sh" "$SNAP" fix/4-real
check "find: 규약 밖 이름이 브랜치를 쥠" FOUND
has "find: 규약 밖 이름 — 찾은 방법" "match branch"
has "find: 규약 밖 이름 — 경로" "path $CC/exp-4-other"
run "$R" "$S/find.sh" "$SNAP" fix/6-locked
check "find: 잠긴 워크트리" FOUND
has "find: 잠금 표시" "locked in use"
run "$R" "$S/find.sh" "$SNAP" fix/7-prunable
check "find: prunable" FOUND
has_prefix "find: prunable 표시" "prunable "
run "$R" "$S/find.sh" "$SNAP" fix/24-ghost
check "find: 브랜치 ref 가 지워지고 등록만 남아도 이름으로 찾음" FOUND
has "find: 등록의 branch 줄은 ref 를 지워도 남음" "branch refs/heads/fix/24-ghost"
has_prefix "find: 등록만 남은 것은 prunable" "prunable "
has "find: ref 가 지워진 등록은 dangling" "dangling yes"
has_prefix "find: 블록에 head 줄" "head "
hasnt "find: ref 가 지워진 등록은 깨진 등록이 아니다" "unreadable yes"
run "$R" "$S/find.sh" "$SNAP" fix/8-switched
check "find: 이름은 맞는데 다른 브랜치로 바꿔 둠" MISMATCH
has "find: 바꾼 브랜치 표시" "branch refs/heads/fix/8-elsewhere"
run "$R" "$S/find.sh" "$SNAP" fix/12-unsafe
check "find: 셸 특수문자 경로" FOUND
has "find: unsafe 표시" "unsafe yes"
has_prefix "find: unsafe 경로는 escaped 로" "path-escaped "
add "$CC/wip-it's" fix/26-quote
run "$R" "$S/find.sh" "$SNAP" fix/26-quote
check "find: 작은따옴표 경로" FOUND
has "find: 작은따옴표도 unsafe(references/worktree.md 제거 절차 0번 ④)" "unsafe yes"
run "$R" "$S/suffix.sh" "$SNAP" "$CC/wip-it's"
check "suffix: 작은따옴표 경로" UNSAFE
add "$CC/wip-back\\slash" fix/27-backslash
run "$R" "$S/find.sh" "$SNAP" fix/27-backslash
check "find: 백슬래시 경로" FOUND
has "find: 백슬래시도 unsafe" "unsafe yes"
add "$CC/wip-plain-name" fix/28-plain
run "$R" "$S/find.sh" "$SNAP" fix/28-plain
check "find: 평범한 경로" FOUND
hasnt "find: 평범한 경로는 unsafe 가 아님" "unsafe yes"
run "$R" "$S/find.sh" "$SNAP" other/1-a
check "find: 레포 밖 워크트리" FOUND
has "find: 컨테이너 밖" "container out"
run "$R" "$S/find.sh" "$SNAP" fix/99-none
check "find: 못 찾았고 detached 가 있음" DETACHED_CANDIDATES
has "find: detached 후보 경로" "path $CC/fix+3-detached"
run "$R2" "$S/find.sh" "$T/snap2.z" fix/99-none
check "find: 아무것도 없음" NONE
run "$R2" "$S/find.sh" "$T/snap2.z" fix/13-main
check "find: 본 체크아웃이 브랜치를 쥠" MAIN_HOLDS
run "$R" "$S/find.sh" "$SNAP" fix/2-nfd "$CC/fix+2-nfd"
check "find --path: NFC 로 친 경로가 NFD 등록과 맞음" FOUND
has "find --path: 찾은 방법" "match path"
run "$R" "$S/find.sh" "$SNAP" fix/5-unique "$CC/fix+5-unique/"
check "find --path: 끝 /" FOUND
run "$R" "$S/find.sh" "$SNAP" fix/5-unique "$CC/FIX+5-UNIQUE"
check "find --path: 대소문자" FOUND
run "$R" "$S/find.sh" "$SNAP" fix/5-unique "$R"
check "find --path: 본 체크아웃" MAIN
run "$R" "$S/find.sh" "$SNAP" fix/5-unique "$CC/nope"
check "find --path: 없는 경로" GONE
run "$R" "$S/find.sh" "$SNAP" fix/8-switched "$CC/fix+8-switched"
check "find --path: 그 사이 브랜치를 바꿈" MISMATCH
run "$T" "$S/find.sh" "$T/snap3.z" fix/5-unique
check_rc "find: 레포 밖" 3
run "$R" "$S/find.sh" "$SNAP"
check_rc "find: 인자 부족" 2

# ---------------------------------------------------------------- suffix.sh
run "$R" "$S/find.sh" "$SNAP" fix/5-unique
run "$R" "$S/suffix.sh" "$SNAP" "$CC/fix+5-unique"
check "suffix: 유일한 이름" "SUFFIX fix+5-unique"
run "$R" "$S/suffix.sh" "$SNAP" "$CC/fix+1-a"
check "suffix: 겹치면 앞 조각을 붙임" "SUFFIX repo/.claude/worktrees/fix+1-a"
run "$R" "$S/suffix.sh" "$SNAP" "$T/upper/FIX+1-A"
check "suffix: 대소문자만 다른 것도 겹침으로 셈" "SUFFIX upper/FIX+1-A"
run "$R" "$S/suffix.sh" "$SNAP" "$T/k1-$NFC_GUT/same/dupname"
check "suffix: 한글 조각까지 가야 갈림" NON_ASCII
run "$R" "$S/suffix.sh" "$SNAP" "$CC/wip-\$USER-old"
check "suffix: 셸 특수문자" UNSAFE
run "$R" "$S/suffix.sh" "$SNAP" "$CC/nope"
check "suffix: 스냅숏에 없음" GONE
run "$R" "$S/suffix.sh" "$SNAP" "$R"
check "suffix: 본 체크아웃" MAIN
printf 'worktree /m\0HEAD 0\0branch refs/heads/main\0\0worktree /x/a\0HEAD 0\0detached\0\0worktree /y/x/a\0HEAD 0\0detached\0\0' > "$T/syn.z"
run "$R" "$S/suffix.sh" "$T/syn.z" /x/a
check "suffix: 맨 앞까지 붙여도 안 갈림" NO_UNIQUE_SUFFIX

# 문서가 시키는 경로를 끝까지: NFC 절대경로 실패 → 접미사 → 사후 확인.
run "$R" "$S/find.sh" "$SNAP" fix/2-nfd
OUT=$(cd "$R" && git worktree remove -- "$CC/fix+2-nfd" 2>&1)
RC=$?
case "$OUT" in
  *"is not a working tree"*) ok ;;
  *) bad "git: NFC 절대경로가 NFD 등록을 못 잡는다(스크립트가 기대는 전제)" "rc=$RC $OUT" ;;
esac
run "$R" "$S/suffix.sh" "$SNAP" "$CC/fix+2-nfd"
check "suffix: NFD 등록" "SUFFIX fix+2-nfd"
OUT=$(cd "$R" && git worktree remove -- "fix+2-nfd" 2>&1)
RC=$?
check_rc "git: 접미사로 제거" 0
run "$R" "$S/verify-removed.sh" "$SNAP" "$CC/fix+2-nfd"
check "verify: 접미사로 지운 뒤" REMOVED
hasnt "verify: 다른 것은 안 사라짐" "also-gone $CC/fix+5-unique"

# ---------------------------------------------------------------- verify-removed.sh
add "$CC/fix+14-victim" fix/14-victim
run "$R" "$S/find.sh" "$SNAP" fix/5-unique
g worktree remove -- "$CC/fix+14-victim"
run "$R" "$S/verify-removed.sh" "$SNAP" "$CC/fix+5-unique"
check "verify: 다른 것을 지웠음" STILL_PRESENT
has "verify: 대신 사라진 줄" "gone $CC/fix+14-victim"

add "$CC/fix+15-rereg" fix/15-rereg
run "$R" "$S/find.sh" "$SNAP" fix/15-rereg
g worktree remove -- "$CC/fix+15-rereg"
git -C "$R" -c core.precomposeunicode=false worktree add -q "$C/fix+15-rereg" fix/15-rereg >/dev/null 2>&1 ||
  setup_fail "재등록"
run "$R" "$S/verify-removed.sh" "$SNAP" "$CC/fix+15-rereg"
check "verify: 지웠다 다른 바이트로 다시 등록됨" REREGISTERED
# 같은 바이트로 다시 등록되면 스냅숏과 지금 목록만으로는 "그대로 있다"와 가를 수 없다 — gone 줄 없는 STILL_PRESENT 로
# 내고 문서가 멈춘다(references/worktree.md 3번 "사후 확인"). 머리말이 이 경우를 적고 있다.
add "$CC/fix+65-same" fix/65-same
run "$R" "$S/find.sh" "$SNAP" fix/65-same
g worktree remove -- "$CC/fix+65-same"
g worktree add -q "$CC/fix+65-same" fix/65-same
run "$R" "$S/verify-removed.sh" "$SNAP" "$CC/fix+65-same"
check "verify: 지웠다 같은 바이트로 다시 등록됨" STILL_PRESENT
if printf '%s\n' "$OUT" | LC_ALL=C grep -q '^gone'; then bad "verify: 그때 gone 줄이 없다" "$OUT"; else ok; fi
g worktree remove -- "$CC/fix+65-same"
g branch -D fix/65-same

add "$CC/fix+19-a" fix/19-a
add "$CC/fix+19-b" fix/19-b
run "$R" "$S/find.sh" "$SNAP" fix/19-a
g worktree remove -- "$CC/fix+19-a"
g worktree remove -- "$CC/fix+19-b"
run "$R" "$S/verify-removed.sh" "$SNAP" "$CC/fix+19-a"
check "verify: 다른 세션이 함께 지운 것이 있음" REMOVED
has "verify: 함께 사라진 줄" "also-gone $CC/fix+19-b"
run "$R" "$S/verify-removed.sh" "$SNAP" "$CC/nope"
check_rc "verify: 스냅숏에 없는 경로(기준선이 아님)" 3

# ---------------------------------------------------------------- residue.sh
run "$R" "$S/residue.sh" 5
check "residue: 브랜치와 워크트리" RESIDUE
count_lines "residue: 로컬·원격 같은 이름은 한 줄" "branch fix/5-unique" 1
# worktree 줄은 스캔이 잡은 표기(NFD 루트 아래)가 아니라 등록된 바이트(NFC 로 add 했다) 그대로다 — find.sh 의 path 줄과 같다.
has "residue: 등록된 워크트리는 등록 경로로" "worktree $CC/fix+5-unique"
hasnt "residue: 스캔 표기로 내지 않는다" "worktree $C/fix+5-unique"
hasnt "residue: 등록된 것은 고아가 아님" "other-orphan $C/fix+5-unique"
run "$R" "$S/residue.sh" 1
check "residue: 이슈 1" RESIDUE
has "residue: 규약 브랜치" "branch fix/1-a"
has "residue: 옛 EnterWorktree 이름" "branch worktree-fix+1-legacy"
hasnt "residue: 다른 번호 뒤의 +1- 는 안 잡음" "branch feat/300-fix+1-a"
hasnt "residue: 111 은 1 이 아님" "branch fix/111-x"
has "residue: 컨테이너 밖 등록도 이름으로 잡음" "worktree $T/elsewhere/.claude/worktrees/fix+1-a"
count_lines "residue: 컨테이너 안 워크트리는 한 번만" "worktree $CC/fix+1-a" 1
hasnt "residue: 같은 워크트리를 다른 표기로 또 내지 않음" "worktree $C/fix+1-a"
run "$R" "$S/residue.sh" 11
check "residue: 옛 중첩 잔재" RESIDUE
has "residue: 중첩 고아" "orphan $C/fix/11-nested"
# test/ 는 옛 타입 폴더로 보지 않는다 — 이 레포 타입이 아니고, 흔한 이름의 체크아웃(EnterWorktree(name: test))이면 안으로
# 내려갈 때 그 조각(src·69-old …)이 고아 후보로 나온다. 폴더째 남의 고아 한 줄로 낸다(머리말).
mkdir -p "$C/test/69-old" "$C/test/src"
run "$R" "$S/residue.sh" 69
check "residue: test/ 는 옛 타입 폴더가 아니다" CLEAN
has "residue: test 폴더는 한 줄로 남의 고아" "other-orphan $C/test"
hasnt "residue: 그 안의 폴더를 고아로 내지 않는다" "orphan $C/test/69-old"
rm -rf "$C/test"
# 앞자리 0 이 든 이름은 잡지 않는다(알려진 한계) — 0 을 허용하면 docs/01-intro 같은 남의 이름이 1번 이슈 잔재가 된다.
g branch docs/01-intro origin/main
run "$R" "$S/residue.sh" 1
hasnt "residue: 앞자리 0 이 든 남의 이름은 잡지 않는다" "branch docs/01-intro"
g branch -D docs/01-intro
# 옛 중첩 디렉터리 안의 잔재가 링크여도 잡는다 — 바깥 스캔만 링크를 보면 CLEAN 이 된다(이전 codex 지적).
mkdir -p "$T/linked-target2"
ln -s "$T/linked-target2" "$C/fix/60-linked"
run "$R" "$S/residue.sh" 60
check "residue: 중첩 디렉터리 안의 링크 잔재" RESIDUE
has "residue: 그 링크가 고아로 잡힌다" "orphan $C/fix/60-linked"
hasnt "residue: 111 은 11 이 아님" "branch fix/111-x"
run "$R" "$S/residue.sh" 9
check "residue: 고아만" RESIDUE
has "residue: 고아 경로" "orphan $C/fix+9-orphan"
run "$R" "$S/residue.sh" 16
check "residue: 원격에만 있는 브랜치" RESIDUE
has "residue: 원격 브랜치 이름" "branch fix/16-remote"
# 같은 이름의 태그가 있으면 %(refname:short) 가 heads/ 를 붙인다(실측) — 그 이름으로는 아무것도 못 찾는다.
g branch fix/42-tagged origin/main
g tag fix/42-tagged origin/main
run "$R" "$S/residue.sh" 42
has "residue: 같은 이름 태그가 있어도 브랜치 이름 그대로" "branch fix/42-tagged"
hasnt "residue: heads/ 접두어가 붙지 않는다" "branch heads/fix/42-tagged"
# 잔재 조사·머지 정리의 for-each-ref 도 같은 이유로 %(refname) 을 쓴다 — 문서의 명령 그대로다.
OUT=$(git -C "$R" for-each-ref --format='%(refname) %(objectname) %(worktreepath)' "refs/heads/fix/42-tagged" "refs/remotes/origin/fix/42-tagged")
has_prefix "for-each-ref: 태그가 있어도 로컬 줄은 전체 이름" "refs/heads/fix/42-tagged [0-9a-f]\{40\} *$"
# detached·bisect 중인 워크트리에서 부르면 git branch -a 는 유사 줄을 내는데(실측), 그 안의 브랜치 이름이
# 판별식에 걸려 없는 브랜치를 잔재로 보고하면 안 된다. 유사 줄에 브랜치 이름이 들어가려면 브랜치에 붙어
# 있다가 그 이름으로 detach 해야 한다(실측: 이미 detached 면 같은 명령을 쳐도 sha 형태 그대로다).
git -C "$CC/fix+3-detached" switch -q fix/3-detached || setup_fail "브랜치로 복귀"
git -C "$CC/fix+3-detached" checkout -q --detach fix/3-detached || setup_fail "브랜치 이름으로 detach"
run "$CC/fix+3-detached" "$S/residue.sh" 3
hasnt "residue: detached 유사 줄은 브랜치가 아니다" "branch (HEAD detached at refs/heads/fix/3-detached)"
count_lines "residue: 그 브랜치 줄은 하나뿐" "branch fix/3-detached" 1
# 디렉터리를 가리키는 심볼릭 링크도 컨테이너 스캔에 잡혀야 한다 — -type d 만 보면 CLEAN 이 나온다.
mkdir -p "$T/linked-target"
ln -s "$T/linked-target" "$C/fix+50-link"
run "$R" "$S/residue.sh" 50
check "residue: 심볼릭 링크 잔재" RESIDUE
has_prefix "residue: 링크가 고아로 잡힌다" "orphan .*fix+50-link"
# 번호 없는 머지 정리(references/merge-cleanup.md)가 컨테이너를 훑는 명령도 그 링크를 모은다 — 문서의 명령 그대로다.
OUT=$(find -H "$C" -mindepth 1 -maxdepth 1 \( -type d -o -type l \))
has "머지 정리 find: 컨테이너 안 링크도 모은다" "$C/fix+50-link"
has "머지 정리 find: 디렉터리도 모은다" "$C/fix+9-orphan"
# 등록된 워크트리를 가리키는 링크: worktree 줄은 링크 경로가 아니라 등록 경로여야 하고(링크 경로로 내면 화면이
# 실상과 다르고 등록 목록 루프가 -ef 로 진짜 경로를 건너뛴다), 링크 자체는 link 줄로 따로 낸다.
mkdir -p "$T/regs"
add "$T/regs/fix+52-real" fix/52-real
ln -s "$T/regs/fix+52-real" "$C/fix+52-linkreg"
run "$R" "$S/residue.sh" 52
check "residue: 등록된 워크트리를 가리키는 링크" RESIDUE
has "residue: 링크가 아니라 등록 경로를 낸다" "worktree $T/regs/fix+52-real"
hasnt "residue: 링크 경로를 worktree 줄로 내지 않는다" "worktree $C/fix+52-linkreg"
has "residue: 링크 자체는 link 줄로" "link $C/fix+52-linkreg"
has "residue: 링크가 가리키는 등록은 link-target 줄로" "link-target $T/regs/fix+52-real"
count_lines "residue: 링크로 닿은 등록도 한 번만" "worktree $T/regs/fix+52-real" 1
# 컨테이너 안의 등록을 가리키는 링크: 스캔이 링크와 실제 디렉터리로 같은 등록에 두 번 닿아도 한 번만 낸다.
ln -s "$CC/fix+5-unique" "$C/fix+5-alias"
run "$R" "$S/residue.sh" 5
count_lines "residue: 링크와 실제 디렉터리로 두 번 닿아도 한 번만" "worktree $CC/fix+5-unique" 1
has "residue: 컨테이너 안을 가리키는 링크도 link 줄" "link $C/fix+5-alias"
hasnt "residue: 링크 경로는 orphan 이 아니다" "orphan $C/fix+5-alias"
run "$R" "$S/orphan-check.sh" "$C/fix+5-alias"
check "orphan: 등록된 워크트리를 가리키는 링크는 REGISTERED(rm -rf 를 막는다)" REGISTERED
# 이 이슈 이름의 링크가 다른 이슈의 워크트리나 본 체크아웃을 가리키면: 링크는 이 이슈 잔재지만(link), 가리키는
# 등록은 worktree 줄로 올리지 않는다 — 올리면 사람이 그 브랜치 이름으로 답했을 때 정리 절차가 남의 것을 지운다.
ln -s "$CC/fix+5-unique" "$C/fix+55-other"
ln -s "$R" "$C/fix+56-root"
run "$R" "$S/residue.sh" 55
check "residue: 다른 이슈 워크트리를 가리키는 링크도 잔재" RESIDUE
has "residue: 그 링크는 link 줄" "link $C/fix+55-other"
has "residue: 가리키는 곳은 link-target 줄" "link-target $CC/fix+5-unique"
hasnt "residue: 다른 이슈의 등록을 이 이슈 worktree 로 올리지 않는다" "worktree $CC/fix+5-unique"
run "$R" "$S/residue.sh" 56
check "residue: 본 체크아웃을 가리키는 링크도 잔재" RESIDUE
has "residue: 본 체크아웃 링크는 link 줄" "link $C/fix+56-root"
has "residue: 가리키는 곳이 본 체크아웃" "link-target $R"
hasnt "residue: 본 체크아웃을 worktree 로 올리지 않는다" "worktree $R"
run "$R" "$S/residue.sh" 5
hasnt "residue: 남의 이름 링크는 이 이슈 조사에 안 나온다" "link $C/fix+55-other"
count_lines "residue: 남의 이름 링크로 닿아도 등록은 한 번만" "worktree $CC/fix+5-unique" 1
run "$R" "$S/residue.sh" 7
check "residue: prunable 로 남은 브랜치" RESIDUE
has "residue: prunable 브랜치" "branch fix/7-prunable"
run "$R" "$S/residue.sh" 24
check "residue: 디렉터리·브랜치 없이 등록만 남음" RESIDUE
has "residue: 남은 등록" "worktree $CC/fix+24-ghost"
hasnt "residue: 지워진 브랜치는 안 나옴" "branch fix/24-ghost"
run "$R" "$S/residue.sh" 99
check "residue: 이 이슈 것 없음" CLEAN
has "residue: 무관한 고아는 보고" "other-orphan $C/unrelated-dir"
has "residue: 다른 이슈 고아도 보고" "other-orphan $C/fix+10-work"
hasnt "residue: 등록된 규약 밖 이름은 고아가 아님" "other-orphan $C/exp-4-other"
run "$R" "$S/residue.sh" 1a
check_rc "residue: 숫자 아닌 번호" 2
# 앞자리 0 번호는 판별식이 5- 와 맞지 않아 fix/5-unique 를 놓치고 CLEAN 을 냈다 — branch-issue.sh 처럼 사용법 오류로 멈춘다.
run "$R" "$S/residue.sh" 05
check_rc "residue: 앞자리 0 번호" 2
hasnt "residue: 앞자리 0 번호로 CLEAN 을 내지 않는다" "CLEAN"
run "$R" "$S/residue.sh" 0
check_rc "residue: 0 번" 2
run "$T" "$S/residue.sh" 5
check_rc "residue: 레포 밖" 3
# 컨테이너나 옛 중첩 디렉터리를 읽지 못하면 CLEAN(잔재 없음)을 내지 않고 멈춘다 — CLEAN 이면 2단계가 새
# 워크트리로 가 버린다(이전 codex 지적). root 는 000 디렉터리도 읽으므로 root 가 아닐 때만 본다.
if [ "$(id -u)" -ne 0 ]; then
  chmod 000 "$C"
  run "$R" "$S/residue.sh" 99
  chmod 755 "$C"
  check_rc "residue: 컨테이너를 읽지 못하면 환경 실패" 3
  hasnt "residue: 그때 CLEAN 을 내지 않는다" "CLEAN"
  # 종료 코드 3 은 git 실패 같은 다른 환경 실패에도 나오니, find 실패 처리가 멈춘 것인지 문구로 본다.
  has "residue: 그때 못 읽은 컨테이너를 짚는다" "실패: 끝까지 읽지 못했다 — 사람이 직접 확인해야 한다: $C"
  chmod 000 "$C/fix"
  run "$R" "$S/residue.sh" 11
  chmod 755 "$C/fix"
  check_rc "residue: 옛 중첩 디렉터리를 읽지 못하면 환경 실패" 3
  has "residue: 그때 못 읽은 옛 중첩 디렉터리를 짚는다" "실패: 끝까지 읽지 못했다 — 사람이 직접 확인해야 한다: $C/fix"
fi
# 옛 타입 폴더가 심볼릭 링크면 따라가지 않고 그 링크만 남의 고아로 보고한다 — 링크 너머는 레포 밖일 수 있어 그
# 안을 고아로 내면 확인 없이 지워진다. 안의 잔재는 놓친다(알려진 한계). 끊긴 링크도 판정을 막지 않는다.
mkdir -p "$T/linked-type/77-old"
ln -s "$T/linked-type" "$C/docs"
run "$R" "$S/residue.sh" 77
check "residue: 링크인 옛 타입 폴더는 따라가지 않는다" CLEAN
has "residue: 그 링크는 남의 고아로 보고" "other-orphan $C/docs"
hasnt "residue: 링크 너머 폴더를 고아로 내지 않는다" "orphan $C/docs/77-old"
rm "$C/docs"
ln -s "$T/nowhere" "$C/chore"
run "$R" "$S/residue.sh" 99
check "residue: 끊긴 링크인 옛 타입 폴더도 판정을 막지 않는다" CLEAN
has "residue: 끊긴 링크도 남의 고아로 보고" "other-orphan $C/chore"
rm "$C/chore"
# 컨테이너 자체가 링크인 레포는 따로 만든다 — 공용 레포의 컨테이너를 바꾸면 뒤 테스트가 모두 달라진다.
RL="$T/linked-container-repo"
git init -q -b main "$RL" || setup_fail "링크 컨테이너 레포"
git -C "$RL" commit -q --allow-empty -m init || setup_fail "링크 컨테이너 레포 커밋"
mkdir -p "$RL/.claude" "$T/linked-container/fix+78-old"
ln -s "$T/linked-container" "$RL/.claude/worktrees"
run "$RL" "$S/residue.sh" 78
check "residue: 링크인 컨테이너 안의 잔재" RESIDUE
# 링크를 거친 컨테이너는 실제 경로로 훑는다 — 고아가 실제 경로로 나와야 orphan-check.sh 가 레포 밖으로 보고 지우기 전에
# 확인받는다.
has "residue: 링크인 컨테이너 안의 고아는 실제 경로로" "orphan $T/linked-container/fix+78-old"
run "$RL" "$S/orphan-check.sh" "$T/linked-container/fix+78-old"
has "orphan: 링크인 컨테이너 안의 고아는 레포 밖으로 판정" "container out"
# 컨테이너 링크가 끊기면(외장 볼륨이 빠졌다) 컨테이너가 없는 것으로 치지 않고 멈춘다.
rm "$RL/.claude/worktrees"
ln -s "$T/unmounted-volume" "$RL/.claude/worktrees"
run "$RL" "$S/residue.sh" 78
check_rc "residue: 끊긴 컨테이너 링크는 환경 실패" 3
has "residue: 그 링크를 짚는다(컨테이너)" "실패: 컨테이너 자리가 디렉터리가 아니다(끊긴 링크이거나 파일이다) — 사람이 직접 확인해야 한다: $RL/.claude/worktrees"
rm "$RL/.claude/worktrees"
touch "$RL/.claude/worktrees"
run "$RL" "$S/residue.sh" 78
check_rc "residue: 컨테이너 자리가 파일이면 환경 실패" 3
has "residue: 그 파일을 짚는다" "실패: 컨테이너 자리가 디렉터리가 아니다(끊긴 링크이거나 파일이다) — 사람이 직접 확인해야 한다: $RL/.claude/worktrees"
rm "$RL/.claude/worktrees"
rmdir "$RL/.claude"
ln -s "$T/unmounted-claude" "$RL/.claude"
run "$RL" "$S/residue.sh" 78
check_rc "residue: .claude 가 끊긴 링크면 환경 실패" 3
has "residue: 그 링크를 짚는다(.claude)" "실패: 컨테이너 자리가 디렉터리가 아니다(끊긴 링크이거나 파일이다) — 사람이 직접 확인해야 한다: $RL/.claude"
rm "$RL/.claude"
mkdir -p "$T/real-claude/worktrees/fix+79-old"
ln -s "$T/real-claude" "$RL/.claude"
run "$RL" "$S/residue.sh" 79
check "residue: .claude 가 링크여도 그 안을 본다" RESIDUE
has "residue: 그 고아도 실제 경로로" "orphan $T/real-claude/worktrees/fix+79-old"
rm "$RL/.claude"
# .claude 를 열 수 없으면 .claude/worktrees 는 있는지조차 안 보여 CLEAN 이 됐다. root 는 000 폴더도 열므로 root 가 아닐 때만.
if [ "$(id -u)" -ne 0 ]; then
  mkdir -p "$RL/.claude/worktrees/fix+79-old"
  chmod 000 "$RL/.claude"
  run "$RL" "$S/residue.sh" 79
  chmod 755 "$RL/.claude"
  check_rc "residue: .claude 를 열 수 없으면 환경 실패" 3
  has "residue: 그 .claude 를 짚는다" "실패: 끝까지 읽지 못했다 — 사람이 직접 확인해야 한다: $RL/.claude"
fi

# ---------------------------------------------------------------- orphan-check.sh
run "$R" "$S/orphan-check.sh" "$C/fix+9-orphan"
check "orphan: .DS_Store 뿐" EMPTY
has "orphan: 컨테이너 안" "container in"
# 편집기가 남긴 흔적도 지워도 되는 것으로 치지 않는다 — 사람이 볼 파일이다.
mkdir -p "$C/fix+57-editor/.vscode"
touch "$C/fix+57-editor/.vscode/settings.json"
run "$R" "$S/orphan-check.sh" "$C/fix+57-editor"
check "orphan: 편집기 흔적(.vscode)도 다른 파일로 친다" OTHER_FILES
# JetBrains IDE(PyCharm 등)가 열고 있던 워크트리를 지우면 .idea/ 를 되살릴 수 있다 — 흔적으로 치지 않고 사람이 본다.
mkdir -p "$C/fix+56-ide/.idea"
touch "$C/fix+56-ide/.idea/workspace.xml"
run "$R" "$S/orphan-check.sh" "$C/fix+56-ide"
check "orphan: IDE 흔적(.idea)도 다른 파일로 친다" OTHER_FILES
has "orphan: .idea 목록" "other .idea"
run "$R" "$S/orphan-check.sh" "$C/fix+10-work"
check "orphan: 작업 파일이 있음" OTHER_FILES
has "orphan: 작업 파일 목록" "other draft.py"
run "$R" "$S/orphan-check.sh" "$C/fix+5-unique"
check "orphan: 등록된 워크트리" REGISTERED
run "$R" "$S/orphan-check.sh" "$R"
check "orphan: 본 체크아웃" REGISTERED
run "$R" "$S/orphan-check.sh" "$C/nope"
check "orphan: 없음" MISSING
mkdir -p "$C/fix+20-empty"
run "$R" "$S/orphan-check.sh" "$C/fix+20-empty/"
check "orphan: 빈 디렉터리(끝 /)" EMPTY
mkdir -p "$C/fix+21-link"
ln -s / "$C/fix+21-link/root"
run "$R" "$S/orphan-check.sh" "$C/fix+21-link"
check "orphan: 심볼릭 링크" OTHER_FILES
mkdir -p "$C/fix+23-dslink"
ln -s / "$C/fix+23-dslink/.DS_Store"
run "$R" "$S/orphan-check.sh" "$C/fix+23-dslink"
check "orphan: .DS_Store 이름의 심볼릭 링크" OTHER_FILES
mkdir -p "$C/fix+22-dsdir/.DS_Store"
run "$R" "$S/orphan-check.sh" "$C/fix+22-dsdir"
check "orphan: .DS_Store 가 디렉터리" OTHER_FILES
# 읽을 수 없는 디렉터리는 판정하지 않는다 — 목록이 비어 EMPTY(묻지 않고 지우는 판정)가 나오면 안 된다.
# root 는 000 디렉터리도 읽으므로 이 검사는 root 가 아닐 때만 한다.
if [ "$(id -u)" -ne 0 ]; then
  mkdir -p "$C/fix+59-locked-top"
  touch "$C/fix+59-locked-top/work.py"
  chmod 000 "$C/fix+59-locked-top"
  run "$R" "$S/orphan-check.sh" "$C/fix+59-locked-top"
  chmod 755 "$C/fix+59-locked-top"
  check_rc "orphan: 읽을 수 없는 디렉터리는 환경 실패" 3
  hasnt "orphan: 그때 EMPTY 를 내지 않는다" "EMPTY"
  has "orphan: 그때 못 읽은 폴더를 짚는다" "실패: 끝까지 읽지 못했다 — 사람이 직접 확인해야 한다: $C/fix+59-locked-top"
  mkdir -p "$C/fix+60-locked-sub/sub"
  touch "$C/fix+60-locked-sub/sub/work.py"
  chmod 000 "$C/fix+60-locked-sub/sub"
  run "$R" "$S/orphan-check.sh" "$C/fix+60-locked-sub"
  chmod 755 "$C/fix+60-locked-sub/sub"
  check_rc "orphan: 읽을 수 없는 하위 디렉터리도 환경 실패" 3
  # 하위 폴더를 못 읽어도 메시지는 넘긴 폴더를 짚는다 — 사람이 볼 자리는 그 폴더다.
  has "orphan: 하위를 못 읽어도 넘긴 폴더를 짚는다" "실패: 끝까지 읽지 못했다 — 사람이 직접 확인해야 한다: $C/fix+60-locked-sub"
fi
# 되살아난 테스트 캐시 디렉터리도 사람이 본다 — 하위 디렉터리는 그 자체로 다른 파일이다.
mkdir -p "$C/fix+58-cache/.pytest_cache"
touch "$C/fix+58-cache/.pytest_cache/.DS_Store"
run "$R" "$S/orphan-check.sh" "$C/fix+58-cache"
check "orphan: 하위 디렉터리가 있으면 .DS_Store 뿐이어도 다른 파일" OTHER_FILES
has "orphan: 하위 디렉터리 목록" "other .pytest_cache"
# 지운 워크트리 자리를 Finder 로 열면 .DS_Store 가 다시 써지며 디렉터리가 되살아난다.
add "$CC/fix+17-revived" fix/17-revived
rm -rf "$CC/fix+17-revived"
mkdir -p "$CC/fix+17-revived"
touch "$CC/fix+17-revived/.DS_Store"
run "$R" "$S/orphan-check.sh" "$C/fix+17-revived"
check "orphan: prunable 등록 자리에 디렉터리가 되살아남" REGISTERED
mkdir -p "$T/outside-orphan"
run "$R" "$S/orphan-check.sh" "$T/outside-orphan"
check "orphan: 컨테이너 밖" EMPTY
has "orphan: 컨테이너 밖 표시" "container out"
# 다른 파일이 21개를 넘으면 세기를 멈추고 20+ 로 자른다.
mkdir -p "$C/fix+54-src/src/cysuml"
for ((n = 0; n < 30; n++)); do : > "$C/fix+54-src/src/cysuml/f$n.py"; done
run "$R" "$S/orphan-check.sh" "$C/fix+54-src"
check "orphan: 다른 파일 21개째에서 세기를 멈춤" OTHER_FILES
has "orphan: 20+ 표시" "other-more 20+"
if [ "$(printf '%s\n' "$OUT" | LC_ALL=C grep -c '^other ')" -eq 20 ]; then ok; else bad "orphan: other 줄은 20개" "$OUT"; fi
# 딱 20개면 other-more 가 없고, 하나만 늘어도 붙는다 — 새 파일이 21번째 뒤로 가면 other 줄은 그대로일 수 있어서(실측)
# references/worktree.md 4번 4)가 이 줄까지 본다. 어느 이름이 21번째 뒤로 가는지는 파일 시스템 순서라 줄로만 본다.
mkdir -p "$C/fix+67-twenty"
for ((n = 0; n < 20; n++)); do : > "$C/fix+67-twenty/f$n"; done
run "$R" "$S/orphan-check.sh" "$C/fix+67-twenty"
check "orphan: 딱 20개" OTHER_FILES
hasnt "orphan: 딱 20개면 other-more 가 없다" "other-more 20+"
: > "$C/fix+67-twenty/new"
run "$R" "$S/orphan-check.sh" "$C/fix+67-twenty"
has "orphan: 21개가 되면 other-more 가 붙는다" "other-more 20+"
rm -rf "$C/fix+67-twenty"

# ---------------------------------------------------------------- ignored-check.sh
# remove 가 묻지 않고 지우는 무시 대상 중 다시 만들 수 없는 것만 KEEP 으로 낸다. 무시 패턴은 이 레포 .gitignore 를
# 그대로 쓰고 시험용 줄(-*/)만 덧붙인다 — 손으로 옮겨 적으면 실제 파일이 바뀌어도 테스트가 모른다.
IG="$CC/fix+61-ign"
add "$IG" fix/61-ign
cat "$HERE/../../../../.gitignore" > "$IG/.gitignore" || setup_fail "레포 .gitignore 복사"
printf '%s\n' '-*/' >> "$IG/.gitignore"
# 이 스킬은 레포 .gitignore 가 이 셋을 무시한다고 전제한다 — 5단계 PR 본문 파일과 제거 절차 스냅숏을 두는 scratchpad/,
# 워크트리 컨테이너 .claude/worktrees/, 하네스 허용 설정. scratchpad/ 가 빠지면 본 체크아웃 status 가 더러워지고, 그
# 안의 파일이 추적 밖 파일이 되어 아래 scratchpad 검사들도 CLEAN 으로 빠진다(SKILL.md 5단계).
for want in scratchpad/x .claude/worktrees/x .claude/settings.local.json; do
  if git -C "$IG" -c core.excludesFile=/dev/null check-ignore -q --no-index -- "$want"; then ok; else
    bad "ignored: 레포 .gitignore 가 스킬이 쓰는 자리를 무시한다" "$want 가 무시되지 않는다 — 레포 .gitignore 에 줄을 더한다"
  fi
done
# 게이트(uv sync·uv run pytest)·JetBrains IDE·하네스가 만드는 자리는 다시 만들 수 있다 — 어느 깊이든 __pycache__,
# 최상위 .venv·.pytest_cache, 최상위 .idea·*.iml.
mkdir -p "$IG/__pycache__" "$IG/src/cysuml/__pycache__" "$IG/.venv/bin" "$IG/.pytest_cache/v/cache" "$IG/.idea" "$IG/.claude"
touch "$IG/__pycache__/conftest.cpython-312.pyc" "$IG/src/cysuml/__pycache__/draw.cpython-312.pyc" "$IG/.venv/bin/python" \
  "$IG/.pytest_cache/v/cache/nodeids" "$IG/.idea/workspace.xml" "$IG/cysUML.iml" "$IG/.DS_Store" \
  "$IG/.claude/settings.local.json"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: 게이트·JetBrains IDE·하네스가 만드는 자리뿐" CLEAN
# .ruff_cache·*.egg-info 는 게이트가 늘 만든다고 실측한 자리가 아니다 — 최상위·src/ 바로 아래여도 사람이 본다.
mkdir -p "$IG/.ruff_cache/0.1" "$IG/cysuml.egg-info" "$IG/src/cysuml.egg-info"
touch "$IG/.ruff_cache/0.1/r" "$IG/cysuml.egg-info/PKG-INFO" "$IG/src/cysuml.egg-info/PKG-INFO"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: .ruff_cache·egg-info" KEEP
has "ignored: .ruff_cache 줄" "keep .ruff_cache/"
has "ignored: 최상위 egg-info 줄" "keep cysuml.egg-info/"
has "ignored: src 아래 egg-info 줄" "keep src/cysuml.egg-info/"
rm -rf "$IG/.ruff_cache" "$IG/cysuml.egg-info" "$IG/src/cysuml.egg-info"
# __pycache__ 라도 *.pyc 밖의 것이 들었으면 사람이 본다 — 이름만 보고 넘기지 않는다.
printf 'memo\n' > "$IG/src/cysuml/__pycache__/notes.txt"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: pyc 밖의 것이 든 __pycache__" KEEP
has "ignored: 그 __pycache__ 줄" "keep src/cysuml/__pycache__/"
rm -f "$IG/src/cysuml/__pycache__/notes.txt"
# 최상위 build/·dist/ 는 게이트가 만드는 자리가 아니고, .gitignore 에 걸려 사람이 둔 스크립트가 숨을 수 있다 — 사람이
# 본다(이전 리뷰에서 나온 기준이다).
mkdir -p "$IG/build/lib" "$IG/dist"
touch "$IG/build/lib/deploy-helper.sh" "$IG/dist/cysuml-0.1.0.tar.gz"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: 최상위 build·dist" KEEP
has "ignored: 최상위 build 줄" "keep build/"
has "ignored: 최상위 dist 줄" "keep dist/"
hasnt "ignored: .venv 는 목록에 없다" "keep .venv/"
hasnt "ignored: __pycache__ 는 목록에 없다" "keep src/cysuml/__pycache__/"
hasnt "ignored: .idea 는 목록에 없다" "keep .idea/"
rm -rf "$IG/build" "$IG/dist"
# 사람이 만든 무시 대상은 다른 곳에 없을 수 있다 — remove 가 묻지 않고 지우므로 사람이 본다. 최상위 그림 출력 폴더,
# 편집기 설정, __pycache__ 밖의 *.pyc 가 그렇다.
mkdir -p "$IG/diagrams"
touch "$IG/diagrams/class.png"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: 그림 출력 폴더" KEEP
has "ignored: 그림 출력 폴더 줄" "keep diagrams/"
rm -rf "$IG/diagrams"
# 그림 출력 폴더·빌드 산출물 폴더는 최상위만 무시한다 — 같은 이름의 소스 하위 패키지(src/cysuml/diagrams/ 등)가 조용히
# 커밋에서 빠지면 안 된다.
for want in diagrams build dist; do
  if git -C "$IG" -c core.excludesFile=/dev/null check-ignore -q --no-index -- "src/cysuml/$want/x.py"; then
    bad "ignored: 깊은 $want 는 무시하지 않는다" "src/cysuml/$want/ 가 무시된다 — .gitignore 의 $want 줄을 /$want/ 로 둔다"
  else ok; fi
done
# 비밀 값 파일은 다른 곳에 없을 수 있다 — 사람이 본다.
printf 'OPENAI_API_KEY=x\n' > "$IG/.env"
printf 'OPENAI_API_KEY=y\n' > "$IG/.env.local"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: 비밀 값 파일" KEEP
has "ignored: .env 줄" "keep .env"
has "ignored: .env.local 줄" "keep .env.local"
rm -f "$IG/.env" "$IG/.env.local"
mkdir -p "$IG/.vscode"
printf '{}\n' > "$IG/.vscode/settings.json"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: 편집기 설정" KEEP
has "ignored: 편집기 설정 줄" "keep .vscode/"
rm -rf "$IG/.vscode"
: > "$IG/src/legacy.pyc"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: __pycache__ 밖의 pyc" KEEP
has "ignored: __pycache__ 밖의 pyc 줄" "keep src/legacy.pyc"
rm -f "$IG/src/legacy.pyc"
# .idea 안에 팀이 남기려고 만드는 폴더(프로젝트 파일로 저장한 실행 구성 등)가 있으면 사람이 본다.
mkdir -p "$IG/.idea/runConfigurations"
touch "$IG/.idea/runConfigurations/pytest.xml"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: 실행 구성이 든 .idea" KEEP
has "ignored: .idea 줄" "keep .idea/"
rm -rf "$IG/.idea/runConfigurations"
# Shelve Changes 로 치워 둔 변경은 .idea/shelf/ 에만 있다 — 사람이 본다.
mkdir -p "$IG/.idea/shelf"
touch "$IG/.idea/shelf/WIP.patch"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: shelf 가 든 .idea" KEEP
rm -rf "$IG/.idea/shelf"
# codeStyles 는 사람이 프로젝트 코드 스타일을 바꿨을 때만 생긴다 — 사람이 본다.
mkdir -p "$IG/.idea/codeStyles"
touch "$IG/.idea/codeStyles/codeStyleConfig.xml" "$IG/.idea/codeStyles/Project.xml"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: 코드 스타일이 든 .idea" KEEP
has "ignored: 코드 스타일 .idea 줄" "keep .idea/"
rm -rf "$IG/.idea/codeStyles"
# 팀이 남기는 검사 프로필도 사람이 본다.
mkdir -p "$IG/.idea/inspectionProfiles"
touch "$IG/.idea/inspectionProfiles/Project_Default.xml"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: 검사 프로필이 든 .idea" KEEP
rm -rf "$IG/.idea/inspectionProfiles"
# JetBrains IDE 의 DB 연결 설정은 폴더(dataSources/)가 아니라 파일(dataSources.xml·dataSources.local.xml)에 먼저 생긴다 —
# 사람이 본다.
for f in dataSources.xml dataSources.local.xml; do
  touch "$IG/.idea/$f"
  run "$R" "$S/ignored-check.sh" "$IG"
  check "ignored: $f 가 든 .idea" KEEP
  has "ignored: $f .idea 줄" "keep .idea/"
  rm -f "$IG/.idea/$f"
done
# JetBrains IDE 의 HTTP 클라이언트가 자동으로 쌓는 요청 기록은 로컬 상태다 — 이것만 있으면 지워도 된다.
mkdir -p "$IG/.idea/httpRequests"
touch "$IG/.idea/httpRequests/http-requests-log.http"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: HTTP 요청 기록만 든 .idea" CLEAN
rm -rf "$IG/.idea/httpRequests"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: 남긴 폴더를 치운 .idea 는 다시 CLEAN" CLEAN
# scratchpad 를 펼친 목록도 20개에서 끊는다.
mkdir -p "$IG/scratchpad"
for ((n = 0; n < 30; n++)); do : > "$IG/scratchpad/m$n.txt"; done
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: scratchpad 에 남은 것이 많다" KEEP
has "ignored: scratchpad 20+ 표시" "keep-more 20+"
if [ "$(printf '%s\n' "$OUT" | LC_ALL=C grep -c '^keep ')" -eq 20 ]; then ok; else bad "ignored: scratchpad keep 줄은 20개" "$OUT"; fi
rm -rf "$IG/scratchpad"
# 이름만으로 넘기지 않는다 — .venv·.pytest_cache·.ruff_cache·.idea·*.egg-info·*.iml 은 어느 깊이든 무시된다. 게이트·IDE
# 가 만드는 최상위 자리가 아니면 사람이 본다.
mkdir -p "$IG/tools/.venv/bin" "$IG/tools/.pytest_cache" "$IG/tools/.ruff_cache" "$IG/tools/.idea" \
  "$IG/tools/x.egg-info" "$IG/src/cysuml/sub.egg-info" "$IG/lib"
touch "$IG/tools/.venv/bin/python" "$IG/tools/.pytest_cache/c" "$IG/tools/.ruff_cache/c" "$IG/tools/.idea/workspace.xml" \
  "$IG/tools/x.egg-info/PKG-INFO" "$IG/src/cysuml/sub.egg-info/PKG-INFO" "$IG/lib/other.iml" "$IG/src/x.iml"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: 엉뚱한 자리의 .venv·캐시·.idea·egg-info·iml" KEEP
has "ignored: 깊은 .venv 줄" "keep tools/.venv/"
has "ignored: 깊은 .pytest_cache 줄" "keep tools/.pytest_cache/"
has "ignored: 깊은 .ruff_cache 줄" "keep tools/.ruff_cache/"
has "ignored: 깊은 .idea 줄" "keep tools/.idea/"
has "ignored: 다른 폴더 아래 egg-info 줄" "keep tools/x.egg-info/"
has "ignored: src 보다 깊은 egg-info 줄" "keep src/cysuml/sub.egg-info/"
has "ignored: 하위 폴더 iml 줄" "keep lib/other.iml"
has "ignored: src 아래 iml 줄" "keep src/x.iml"
rm -rf "$IG/tools" "$IG/lib" "$IG/src/cysuml/sub.egg-info" "$IG/src/x.iml"
# scratchpad/ 에 남은 것은 5단계가 본문 파일을 지우고 간 뒤의 것이라 사람이 본다(이전 리뷰에서 재현).
mkdir -p "$IG/scratchpad"
touch "$IG/scratchpad/notes.md"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: scratchpad 메모" KEEP
has "ignored: scratchpad 메모 줄" "keep scratchpad/notes.md"
rm -rf "$IG/scratchpad"
# 셈 기록 두 파일(SKILL.md 4단계 "셈 기록")은 PR 이 머지될 때까지 남겨 두는 파일이라 지워도 되는 것으로 친다 — 사람이
# 보게 하면 머지 정리가 매번 멈춘다. 이름이 같아도 일반 파일이 아니거나 더 깊은 자리면 사람이 본다.
mkdir -p "$IG/scratchpad"
printf '%s\n' "counted=3 cap=10 streak=0" > "$IG/scratchpad/issue-rounds"
printf '%s\n' "counted=1 cap=10 streak=0" > "$IG/scratchpad/issue-rereview-rounds"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: scratchpad 의 셈 기록 파일만 있으면" CLEAN
touch "$IG/scratchpad/notes.md"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: 셈 기록 옆의 메모" KEEP
has "ignored: 셈 기록 옆의 메모 줄" "keep scratchpad/notes.md"
hasnt "ignored: 셈 기록 파일은 keep 줄에 없다" "keep scratchpad/issue-rounds"
hasnt "ignored: 재리뷰 셈 기록 파일도 keep 줄에 없다" "keep scratchpad/issue-rereview-rounds"
rm -rf "$IG/scratchpad"
mkdir -p "$IG/scratchpad/issue-rounds" "$IG/scratchpad/sub"
touch "$IG/scratchpad/issue-rounds/x"
printf '%s\n' "counted=3 cap=10 streak=0" > "$IG/scratchpad/sub/issue-rounds"
ln -s "$IG/scratchpad/sub/issue-rounds" "$IG/scratchpad/issue-rereview-rounds"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: 셈 기록 이름의 디렉터리·링크·깊은 자리" KEEP
has "ignored: 셈 기록 이름의 디렉터리" "keep scratchpad/issue-rounds/"
has "ignored: 셈 기록 이름의 링크" "keep scratchpad/issue-rereview-rounds"
has "ignored: 더 깊은 자리의 셈 기록 이름" "keep scratchpad/sub/"
rm -rf "$IG/scratchpad"
# - 로 시작하는 이름도 빈 디렉터리로 잘못 읽지 않는다(ls 옵션으로 읽히면 출력이 비어 '빈 디렉터리'가 된다).
mkdir -p "$IG/-results"
touch "$IG/-results/r.json"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: - 로 시작하는 비지 않은 디렉터리" KEEP
has "ignored: 그 디렉터리 줄" "keep -results/"
rm -rf "$IG/-results"
# 하네스가 워크트리 안에 만드는 빈 .claude/worktrees/ 는 무시 대상이지만 잃을 것이 없다.
mkdir -p "$IG/.claude/worktrees"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: 빈 무시 디렉터리는 CLEAN" CLEAN
mkdir -p "$IG/.claude/worktrees/nested"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: 비지 않은 무시 디렉터리는 KEEP" KEEP
has "ignored: 그 디렉터리 줄" "keep .claude/worktrees/"
rmdir "$IG/.claude/worktrees/nested"
# 이름이 줄바꿈뿐인 파일도 내용이다 — ls 출력을 명령 치환으로 받으면 줄바꿈이 떨어져 '비었다'가 된다.
: > "$IG/.claude/worktrees/"$'\n'
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: 줄바꿈 이름 파일만 있어도 KEEP" KEEP
rm -f "$IG/.claude/worktrees/"$'\n'
# status.showUntrackedFiles=no 여도 판정한다 — 없으면 --ignored=matching 이 rc 128 로 죽는다.
g config status.showUntrackedFiles no
run "$R" "$S/ignored-check.sh" "$IG"
g config --unset status.showUntrackedFiles
check "ignored: showUntrackedFiles=no 설정에서도 판정" CLEAN
# .DS_Store 는 파일일 때만 다시 만들 수 있는 것이다 — 같은 이름의 디렉터리는 orphan-check 와 같게 사람이 본다.
mkdir -p "$IG/src/.DS_Store"
touch "$IG/src/.DS_Store/notes.txt"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: .DS_Store 디렉터리는 KEEP" KEEP
has "ignored: 그 디렉터리 줄" "keep src/.DS_Store/"
rm -rf "$IG/src/.DS_Store"
# 링크는 이름이 맞아도 다시 만들 수 있는 것으로 치지 않는다.
ln -s / "$IG/.idea-link"
printf '.idea-link\n' >> "$IG/.gitignore"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: 무시된 링크는 KEEP" KEEP
rm -f "$IG/.idea-link"
# 다시 만들 수 있는 이름(최상위 *.iml)이어도 링크면 사람이 본다 — 링크 대상은 일반 파일이라 -f 만으로는 못 가린다.
printf 'x\n' > "$T/iml-target"
ln -s "$T/iml-target" "$IG/link.iml"
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: 링크인 iml" KEEP
has "ignored: 링크인 iml 줄" "keep link.iml"
rm -f "$IG/link.iml" "$T/iml-target"
# 스크립트가 그 워크트리 안에서 git 을 부르므로 cwd 가 레포 밖이어도 같다.
mkdir -p "$IG/diagrams"
touch "$IG/diagrams/class.png"
run "$T" "$S/ignored-check.sh" "$IG"
check "ignored: cwd 가 레포 밖이어도 판정" KEEP
has "ignored: 그림 출력 폴더 줄(레포 밖 cwd)" "keep diagrams/"
# 상대경로 인자는 작업 디렉터리 기준으로 푼다 — CDPATH 가 걸리면 cd 가 그쪽 같은 이름으로 가고 그 자리를 stdout 에 찍어
# 첫 줄이 판정 키워드가 아니게 됐다(skill-repo.sh 와 같은 이유).
mkdir -p "$T/ign-cdpath/fix+61-ign"
run "$C" -c 'CDPATH="$1" bash "$2" fix+61-ign' _ "$T/ign-cdpath" "$S/ignored-check.sh"
check "ignored: CDPATH 가 있어도 작업 디렉터리 기준" KEEP
has "ignored: CDPATH 쪽이 아니라 그 워크트리를 판정" "keep diagrams/"
rm -rf "$T/ign-cdpath"
# - 로 시작하는 상대경로도 판정한다 — cd 가 옵션(-66…)이나 OLDPWD(- 하나)로 읽어 들어가지 못했다.
add "$CC/-66-dash" fix/66-dash
add "$CC/-" fix/68-lone-dash
run "$C" "$S/ignored-check.sh" -66-dash
check "ignored: - 로 시작하는 상대경로" CLEAN
run "$C" "$S/ignored-check.sh" -
check "ignored: - 하나인 상대경로" CLEAN
g worktree remove -- "$CC/-66-dash"
g worktree remove -- "$CC/-"
g branch -D fix/66-dash fix/68-lone-dash
for ((n = 0; n < 25; n++)); do : > "$IG/k$n.pyc"; done
run "$R" "$S/ignored-check.sh" "$IG"
check "ignored: 많아도 KEEP" KEEP
has "ignored: 20+ 표시" "keep-more 20+"
if [ "$(printf '%s\n' "$OUT" | LC_ALL=C grep -c '^keep ')" -eq 20 ]; then ok; else bad "ignored: keep 줄은 20개" "$OUT"; fi
# .git 이 없으면 git 이 상위 레포(본 체크아웃)를 보므로 판정하지 않는다.
run "$R" "$S/ignored-check.sh" "$C/fix+9-orphan"
check "ignored: .git 없는 디렉터리" NOT_WORKTREE
run "$R" "$S/ignored-check.sh" "$IG/src"
check "ignored: 워크트리 하위 폴더" NOT_WORKTREE
run "$R" "$S/ignored-check.sh" "$C/nope"
check "ignored: 없음" MISSING
run "$R" "$S/ignored-check.sh"
check_rc "ignored: 인자 없음" 2

# ---------------------------------------------------------------- detached-check.sh
run "$R" "$S/detached-check.sh" fix/3-detached
check "detached: 브랜치에만 있는 커밋에 서 있음" FOUND
has "detached: 경로" "path $CC/fix+3-detached"
run "$R" "$S/detached-check.sh" fix/5-unique
check "detached: 해당 없음" NONE
add "$CC/fix+18-detmain" fix/18-detmain
git -C "$CC/fix+18-detmain" checkout -q --detach origin/main || setup_fail "detach main"
run "$R" "$S/detached-check.sh" fix/5-unique
check "detached: origin/main 커밋에 선 것은 안 걸림" NONE
run "$R" "$S/detached-check.sh" nope
check "detached: 로컬 브랜치 없음" NO_BRANCH
run "$T" "$S/detached-check.sh" fix/5-unique
check_rc "detached: 레포 밖" 3

# ---------------------------------------------------------------- 쌍둥이 등록·detached 필터·원격 전용·깨진 HEAD
# 같은 디렉터리에 표기만 다른 등록이 둘이면, 후보가 하나여도 AMBIGUOUS 여야 한다(절대경로 remove 가 쌍둥이를 지운다).
git -C "$R" -c core.precomposeunicode=false worktree add -q --no-track "$C/exp-twin" -b fix/30-twin origin/main \
  >/dev/null 2>&1 || setup_fail "쌍둥이 NFD 등록"
rm -rf "$C/exp-twin"
add "$CC/exp-twin" fix/30-other
run "$R" "$S/find.sh" "$SNAP" fix/30-twin
check "find: 같은 디렉터리에 표기만 다른 등록이 둘" AMBIGUOUS
has "find: 쌍둥이 표시" "match same-dir"

# DETACHED_CANDIDATES 는 origin/main 에 이미 있는 커밋에 선 detached 를 뺀다.
run "$R" "$S/find.sh" "$SNAP" fix/99-none
check "find: 브랜치 전용 커밋 detached 는 여전히 후보" DETACHED_CANDIDATES
has "find: 브랜치 전용 커밋 detached 후보" "path $CC/fix+3-detached"
hasnt "find: origin/main 커밋 detached 는 후보가 아님" "path $CC/fix+18-detmain"
g worktree remove -- "$CC/fix+3-detached"
run "$R" "$S/find.sh" "$SNAP" fix/99-none
check "find: origin/main 커밋 detached 만 있으면" NONE

# 로컬 브랜치가 없어도 원격 추적 ref 로 detached 를 본다(원격 삭제 앞의 방벽).
add "$CC/fix+29-ro" fix/29-ro
git -C "$CC/fix+29-ro" commit -q --allow-empty -m ro || setup_fail "ro 커밋"
g push -q origin fix/29-ro
g worktree remove -- "$CC/fix+29-ro"
g branch -D fix/29-ro
g fetch -q origin
g worktree add -q --detach "$CC/ro-view" origin/fix/29-ro
run "$R" "$S/detached-check.sh" fix/29-ro
check "detached: 원격에만 있는 브랜치를 detached 로 연 체크아웃" FOUND
has "detached: 원격 추적 ref 기준" "ref refs/remotes/origin/fix/29-ro"
has "detached: 원격 전용 체크아웃 경로" "path $CC/ro-view"
run "$R" "$S/detached-check.sh" fix/16-remote
check "detached: 원격에만 있고 해당 detached 없음" NONE
has "detached: 원격 추적 ref 기준(해당 없음)" "ref refs/remotes/origin/fix/16-remote"
run "$R" "$S/detached-check.sh" fix/5-unique
has "detached: 로컬 브랜치 기준" "ref refs/heads/fix/5-unique"

# 로컬 브랜치가 있어도 원격이 앞서 있으면, 원격 추적 ref 에만 있는 커밋에 선 detached 를 잡는다.
add "$CC/fix+31-both" fix/31-both
git -C "$CC/fix+31-both" commit -q --allow-empty -m both1 || setup_fail "both 커밋 1"
git -C "$CC/fix+31-both" commit -q --allow-empty -m both2 || setup_fail "both 커밋 2"
g push -q origin fix/31-both
git -C "$CC/fix+31-both" reset -q --hard HEAD~1 || setup_fail "both 되감기"
g fetch -q origin
g worktree add -q --detach "$CC/both-view" origin/fix/31-both
run "$R" "$S/detached-check.sh" fix/31-both
check "detached: 원격이 로컬보다 앞선 커밋에 선 체크아웃" FOUND
has "detached: 로컬 ref 줄" "ref refs/heads/fix/31-both"
has "detached: 원격 ref 줄" "ref refs/remotes/origin/fix/31-both"
has "detached: 원격이 앞선 체크아웃 경로" "path $CC/both-view"
g worktree remove -- "$CC/both-view"

# HEAD 를 못 읽는 깨진 detached 등록 하나 때문에 판정이 죽지 않는다.
rm -f "$R/.git/worktrees/ro-view/HEAD"
run "$R" "$S/detached-check.sh" fix/5-unique
check "detached: HEAD 를 못 읽는 등록이 있어도 판정" NONE
has "detached: 깨진 등록 보고" "unreadable $CC/ro-view"

# HEAD 가 0바이트면 git 은 detached 줄도 안 붙인다 — 그래도 판정에서 빼고 보고한다.
g worktree add -q --detach "$CC/zero-view" origin/main
: > "$R/.git/worktrees/zero-view/HEAD"
run "$R" "$S/detached-check.sh" fix/5-unique
check "detached: 0바이트 HEAD 가 있어도 판정" NONE
has "detached: 0바이트 HEAD 보고" "unreadable $CC/zero-view"
hasnt "detached: ref 가 지워진 등록은 보고 대상이 아니다" "unreadable $CC/fix+24-ghost"
run "$R" "$S/find.sh" "$SNAP" fix/5-unique "$CC/zero-view"
check "find: 깨진 HEAD 등록은 정체를 못 가린다" MISMATCH
has "find: 깨진 HEAD 블록 표시" "unreadable yes"

# 커밋을 못 찾는 detached 등록(force-push 뒤 gc 된 커밋)에도 판정이 죽지 않는다.
g worktree add -q --detach "$CC/gone-view" origin/main
echo 0123456789012345678901234567890123456789 > "$R/.git/worktrees/gone-view/HEAD"
run "$R" "$S/detached-check.sh" fix/5-unique
check "detached: 커밋을 못 찾는 등록이 있어도 판정" NONE
has "detached: 커밋을 못 찾는 등록 보고" "unreadable $CC/gone-view"
run "$R" "$S/find.sh" "$SNAP" fix/99-none
has "find: 커밋을 못 찾는 detached 후보에는 표시가 붙는다" "match detached-unresolved"

# ---------------------------------------------------------------- 원격 명령 동작(6번의 전제)
# ls-remote 는 접미사로도 맞는다 — 6번이 "둘째 칸이 정확히 refs/heads/<브랜치> 인 줄만 쓴다"고 못박는 이유.
g branch feat/fix/5-unique origin/main
g push -q origin feat/fix/5-unique
run "$R" -c 'git ls-remote --heads origin fix/5-unique'
has_prefix "원격: ls-remote 가 그 브랜치를 낸다" ".*refs/heads/fix/5-unique"
has_prefix "원격: ls-remote 가 접미사로 다른 브랜치도 낸다" ".*refs/heads/feat/fix/5-unique"
# push --delete 의 --force-with-lease: 낡은 sha 면 거부하고 아무것도 안 지운다(6번 삭제 명령의 전제).
g branch fix/51-lease origin/main
g push -q origin fix/51-lease
OLD=$(git -C "$R" rev-parse refs/heads/fix/51-lease) || setup_fail "lease OLD"
TREE=$(git -C "$R" rev-parse "origin/main^{tree}") || setup_fail "lease TREE"
NEWC=$(git -C "$R" commit-tree "$TREE" -p origin/main -m lease) || setup_fail "lease 커밋"
g push -q origin "$NEWC:refs/heads/fix/51-lease"
# 원격에 같은 이름의 태그가 있으면 맨 이름 --delete 는 둘 중 무엇인지 못 가려 죽는다 — 6번이 refs/heads/ 를 붙이는 이유.
g tag fix/51-lease origin/main
g push -q origin refs/tags/fix/51-lease:refs/tags/fix/51-lease
run "$R" -c 'git push origin --delete fix/51-lease --force-with-lease=refs/heads/fix/51-lease:"$1"' _ "$NEWC"
check_rc "원격: 같은 이름 태그가 있으면 맨 이름 --delete 는 거부된다" 1
has_prefix "원격: 거부 메시지는 matches more than one" ".*matches more than one"
run "$R" -c 'git push origin --delete refs/heads/fix/51-lease --force-with-lease=refs/heads/fix/51-lease:"$1"' _ "$OLD"
check_rc "원격: 낡은 lease 는 거부된다" 1
has_prefix "원격: 거부 메시지는 stale info" ".*stale info"
run "$R" -c 'git ls-remote --heads origin fix/51-lease'
has_prefix "원격: 거부 뒤에도 원격 브랜치가 남는다" ".*refs/heads/fix/51-lease"
run "$R" -c 'git push origin --delete refs/heads/fix/51-lease --force-with-lease=refs/heads/fix/51-lease:"$1"' _ "$NEWC"
check_rc "원격: 맞는 lease 면 지워진다" 0
run "$R" -c 'git ls-remote --heads origin fix/51-lease'
check "원격: 지워진 뒤 ls-remote 는 빈 출력" ""
run "$R" -c 'git ls-remote --tags origin fix/51-lease'
has_prefix "원격: 같은 이름의 태그는 그대로 남는다" ".*refs/tags/fix/51-lease"

# 원격에 브랜치와 같은 이름의 태그가 있으면 fetch 의 맨 이름은 태그로 풀린다(refs/tags 가 refs/heads 보다 먼저
# 맞는다) — 문서가 fetch·refspec 에 refs/heads/ 를 붙이는 이유. 로컬에 그 태그가 이미 있어도(fetch --prune 이
# 따라온다) 같다. 별도 클론에서 돌린다 — 이 시점의 R 에는 없는 커밋을 가리키는 등록(gone-view)이 있어 fetch 가
# bad object worktrees/<id>/HEAD 로 죽는다(SKILL.md 2단계가 적어 둔 그 갈래다).
F="$T/fetch-repo"
git clone -q "$T/origin.git" "$F" 2>/dev/null || setup_fail "fetch 실험용 클론"
f() { git -C "$F" "$@" >/dev/null 2>&1 || setup_fail "git(fetch-repo) $*"; }
NEWB=$(git -C "$F" commit-tree "$TREE" -p origin/main -m tagged) || setup_fail "tagged 커밋"
f update-ref refs/heads/fix/43-tagged "$NEWB"
f tag fix/43-tagged origin/main
TAGC=$(git -C "$F" rev-parse refs/tags/fix/43-tagged) || setup_fail "tagged TAGC"
f push -q origin refs/heads/fix/43-tagged:refs/heads/fix/43-tagged refs/tags/fix/43-tagged:refs/tags/fix/43-tagged
f update-ref -d refs/remotes/origin/fix/43-tagged
run "$F" -c 'git fetch origin fix/43-tagged'
check_rc "원격: 맨 이름 fetch 는 성공한다" 0
run "$F" -c 'git rev-parse FETCH_HEAD'
check "원격: 하지만 받은 것은 태그 커밋" "$TAGC"
run "$F" -c 'git rev-parse --verify -q refs/remotes/origin/fix/43-tagged'
check_rc "원격: 추적 ref 는 안 생긴다" 1
run "$F" -c 'git fetch origin refs/heads/fix/43-tagged'
check_rc "원격: refs/heads/ 를 붙인 fetch" 0
run "$F" -c 'git rev-parse refs/remotes/origin/fix/43-tagged'
check "원격: 추적 ref 가 브랜치 팁으로 생긴다" "$NEWB"
f update-ref -d refs/heads/fix/43-tagged
run "$F" -c 'git fetch origin fix/43-tagged:fix/43-tagged'
check_rc "원격: 맨 이름 refspec 도 성공한다" 0
run "$F" -c 'git rev-parse refs/heads/fix/43-tagged'
check "원격: 하지만 태그 커밋을 가리키는 로컬 브랜치가 생긴다" "$TAGC"
f update-ref -d refs/heads/fix/43-tagged
run "$F" -c 'git fetch origin refs/heads/fix/43-tagged:refs/heads/fix/43-tagged'
check_rc "원격: refs/heads/ 를 양쪽에 붙인 refspec" 0
run "$F" -c 'git rev-parse refs/heads/fix/43-tagged'
check "원격: 로컬 브랜치가 브랜치 팁으로 생긴다" "$NEWB"
# 로컬에 브랜치와 태그가 둘 다 있으면 log·merge-base·rev-parse 의 맨 이름도 태그로 푼다 — 5번 ② 범위와 SKILL.md
# 2단계 재시도의 rev-parse 에 refs/heads/ 를 붙이는 이유.
run "$F" -c 'git rev-parse --verify fix/43-tagged 2>/dev/null'
check "원격: 로컬 맨 이름은 태그로 풀린다" "$TAGC"
run "$F" -c 'git log --oneline fix/43-tagged..refs/heads/fix/43-tagged 2>/dev/null'
has_prefix "원격: 맨 이름..refs/heads 가 브랜치 커밋을 낸다(맨 이름이 태그였다)" ".* tagged"
run "$F" -c 'git log --oneline origin/fix/43-tagged..refs/heads/fix/43-tagged'
check "원격: refs/heads 로 적은 5번 ② 범위는 빈 출력" ""
# worktree add 는 반대다 — 맨 이름은 브랜치를 체크아웃하고, refs/heads/ 를 붙이면 detached 로 열린다.
f worktree add -q "$T/tagged-wt" fix/43-tagged
run "$T/tagged-wt" -c 'git branch --show-current'
check "원격: worktree add 의 맨 이름은 브랜치" "fix/43-tagged"
f worktree remove -- "$T/tagged-wt"
f worktree add -q "$T/tagged-wt2" refs/heads/fix/43-tagged
run "$T/tagged-wt2" -c 'git branch --show-current'
check "원격: worktree add 에 refs/heads/ 를 붙이면 detached" ""
f worktree remove -- "$T/tagged-wt2"

# ---------------------------------------------------------------- 셸 문자가 든 브랜치 이름
# git 은 브랜치 이름에 ; | & ( ) < > 와 한글을 허용한다(git check-ref-format --branch 실측). 따옴표 없이 옮겨 치면
# 그 뒤가 명령으로 실행되므로, 판정 스크립트는 영숫자와 ._/+- 밖의 문자가 든 이름을 branch-escaped 로 낸다.
# 경로 줄의 -escaped(is_unsafe)는 ; 같은 문자를 거르지 않으니 기준이 따로다.
g branch "fix/70-semi;colon" origin/main
g branch "fix/70-pipe(x)|y" origin/main
g branch "fix/70-a+b.c_D" origin/main
run "$R" -c 'git rev-parse --verify -q refs/heads/fix/70-semi;touch "$1"' _ "$T/injected-70"
if [ -e "$T/injected-70" ]; then ok; else bad "git: 따옴표 없는 브랜치 이름의 ; 뒤는 명령으로 실행된다(전제)" "$OUT"; fi
run "$R" -c 'git rev-parse --verify -q "refs/heads/$1" >/dev/null' _ "fix/70-semi;colon"
check_rc "git: 큰따옴표로 감싸면 그 이름 그대로 브랜치를 찾는다" 0
run "$R" "$S/residue.sh" 70
check "residue: 같은 번호에 안전한 이름의 브랜치(fix/70-a+b.c_D)가 함께 있으면 잔재" RESIDUE
has "residue: ; 가 든 브랜치는 escaped 로" 'branch-escaped fix/70-semi\;colon'
has "residue: ( ) | 가 든 브랜치는 escaped 로" 'branch-escaped fix/70-pipe\(x\)\|y'
hasnt "residue: 셸 문자 브랜치를 그대로 내지 않는다" "branch fix/70-semi;colon"
has "residue: 영숫자와 ._/+- 만 든 브랜치는 그대로" "branch fix/70-a+b.c_D"
g branch "fix/71-한글" origin/main
run "$R" "$S/residue.sh" 71
check "residue: escaped 브랜치만 있어도 잔재로 친다(같은 이슈의 팀원 작업일 수 있어 묻는다)" RESIDUE
has "residue: 한글 브랜치도 escaped 로" "branch-escaped \$'fix/71-\\355\\225\\234\\352\\270\\200'"
hasnt "residue: 한글 브랜치를 그대로 내지 않는다" "branch fix/71-한글"
# bash 3.2 의 %q 는 UTF-8 로케일에서 한글을 깨뜨린다 — 사람이 읽을 수 있게 C 로케일 표기로 나와야 한다.
OUT=$(cd "$R" && LC_ALL=en_US.UTF-8 bash "$S/residue.sh" 71 2>&1)
RC=$?
has "residue: UTF-8 로케일에서도 한글 브랜치는 \\ooo 표기로" "branch-escaped \$'fix/71-\\355\\225\\234\\352\\270\\200'"
# 원격에만 남은 이름도 같다 — origin/ 을 떼고 낸다. fetch 는 하지 않는다 — 이 시점의 R 에는 없는 커밋을 가리키는
# 등록(gone-view)이 있어 fetch 가 죽는다. push 가 원격 추적 ref 를 함께 만든다.
g push -q origin "refs/heads/fix/70-semi;colon:refs/heads/fix/72-remote&only"
run "$R" "$S/residue.sh" 72
check "residue: 원격에만 있는 escaped 브랜치도 잔재로 친다" RESIDUE
has "residue: 원격에만 있는 셸 문자 브랜치도 escaped 로" 'branch-escaped fix/72-remote\&only'
# 레코드 블록(wt_print)의 branch 줄도 같은 기준이다 — 이름으로 찾은 워크트리가 셸 문자 브랜치를 쥐면 MISMATCH 블록에 나온다.
add "$CC/fix+73-held" "fix/73-held;x"
run "$R" "$S/find.sh" "$SNAP" fix/73-held
check "find: 이름은 맞는데 셸 문자 브랜치를 쥠" MISMATCH
has "find: 블록의 셸 문자 브랜치는 escaped 로" 'branch-escaped refs/heads/fix/73-held\;x'
hasnt "find: 블록에 셸 문자 브랜치를 그대로 내지 않는다" "branch refs/heads/fix/73-held;x"
hasnt "find: 경로가 평범하면 unsafe 표시는 없다" "unsafe yes"
# 명령에 넣을 수 없는 이름을 인자로 받으면 판정하지 않는다 — branch-escaped 표기(%q)를 옮겨 오면 없는 이름이라
# NONE·NO_BRANCH 가 나오고, 문서는 그 말을 믿고 재부착이나 원격 삭제 앞 확인을 지나간다.
run "$R" "$S/find.sh" "$SNAP" "fix/73-held;x"
check_rc "find: 명령에 넣을 수 없는 브랜치 인자는 받지 않는다" 2
run "$R" "$S/find.sh" "$SNAP" 'fix/70-semi\;colon'
check_rc "find: branch-escaped 표기를 옮겨 와도 받지 않는다" 2
run "$R" "$S/detached-check.sh" "fix/70-semi;colon"
check_rc "detached: 명령에 넣을 수 없는 브랜치 인자는 받지 않는다" 2
# - 로 시작하는 이름은 git branch 로는 못 만들지만 push 로는 원격에 생긴다. 큰따옴표로 감싸도 옵션으로 읽힌다.
g push -q origin "refs/heads/fix/70-a+b.c_D:refs/heads/-fix+74-dash"
run "$R" -c 'git branch -D "$1"' _ "-fix+74-dash"
case "$RC:$OUT" in
  0:*) bad "git: - 로 시작하는 이름은 감싸도 옵션으로 읽힌다(전제)" "rc=$RC $OUT" ;;
  *"unknown switch"*) ok ;;
  *) bad "git: - 로 시작하는 이름은 감싸도 옵션으로 읽힌다(전제)" "rc=$RC $OUT" ;;
esac
run "$R" "$S/residue.sh" 74
has "residue: - 로 시작하는 원격 브랜치도 escaped 로" "branch-escaped -fix+74-dash"
run "$R" "$S/find.sh" "$SNAP" "-fix+74-dash"
check_rc "find: - 로 시작하는 브랜치 인자는 받지 않는다" 2
run "$R" "$S/detached-check.sh" 'fix/70-semi\;colon'
check_rc "detached: branch-escaped 표기를 옮겨 와도 받지 않는다" 2
run "$R" "$S/detached-check.sh" "-fix+74-dash"
check_rc "detached: - 로 시작하는 브랜치 인자는 받지 않는다" 2
# 거절 메시지도 사람이 읽는 값이라 UTF-8 로케일에서 한글이 깨지면 안 된다.
OUT=$(cd "$R" && LC_ALL=en_US.UTF-8 bash "$S/find.sh" "$SNAP" "fix/71-한글" 2>&1)
RC=$?
check_rc "find: 한글 브랜치 인자는 받지 않는다" 2
has "find: 거절 메시지의 한글은 \\ooo 표기로" "사용법: 명령에 넣을 수 없는 브랜치 이름이다 — 사람에게 넘긴다: \$'fix/71-\\355\\225\\234\\352\\270\\200'"
OUT=$(cd "$R" && LC_ALL=en_US.UTF-8 bash "$S/detached-check.sh" "fix/71-한글" 2>&1)
RC=$?
has "detached: 거절 메시지의 한글은 \\ooo 표기로" "사용법: 명령에 넣을 수 없는 브랜치 이름이다 — 사람에게 넘긴다: \$'fix/71-\\355\\225\\234\\352\\270\\200'"
# 레코드 블록은 branch 줄을 refs/heads/ 를 붙인 채 낸다 — - 시작 판정은 그 접두어를 뗀 이름으로 해야 걸린다.
add "$CC/fix+75-held" fix/75-held
g update-ref "refs/heads/-fix+75-other" origin/main
git -C "$CC/fix+75-held" symbolic-ref HEAD "refs/heads/-fix+75-other" >/dev/null 2>&1 ||
  setup_fail "- 로 시작하는 브랜치를 쥔 워크트리"
run "$R" "$S/find.sh" "$SNAP" fix/75-held
check "find: 이름은 맞는데 - 로 시작하는 브랜치를 쥠" MISMATCH
has "find: 블록의 - 시작 브랜치도 escaped 로" "branch-escaped refs/heads/-fix+75-other"
hasnt "find: 블록에 - 시작 브랜치를 그대로 내지 않는다" "branch refs/heads/-fix+75-other"
# refs/heads/ 밖의 ref 를 쥔 등록(HEAD 를 원격 추적 ref 로 돌려 둔 것)은 브랜치 이름으로 옮길 수 없으니 escaped 로 낸다.
add "$CC/fix+76-odd" fix/76-odd
git -C "$CC/fix+76-odd" symbolic-ref HEAD refs/remotes/origin/main >/dev/null 2>&1 ||
  setup_fail "refs/heads 밖의 ref 를 쥔 워크트리"
run "$R" "$S/find.sh" "$SNAP" fix/76-odd
check "find: 이름은 맞는데 refs/heads 밖의 ref 를 쥠" MISMATCH
has "find: refs/heads 밖의 ref 는 escaped 로" "branch-escaped refs/remotes/origin/main"

# ---------------------------------------------------------------- lib.sh 없이 불렀을 때
# lib.sh 를 못 읽으면 판정 키워드를 내지 않고 멈춘다 — 그냥 이어 가면 함수가 없는 채로 끝까지 돌아
# find.sh 는 NONE, residue.sh 는 CLEAN 을 exit 0 으로 내고, 문서가 그 말을 믿는다.
mkdir -p "$T/nolib"
cp "$S"/*.sh "$T/nolib/"
rm -f "$T/nolib/lib.sh"
for s in find residue detached-check orphan-check suffix verify-removed inside same-repo skill-repo isolation-check branch-issue round-count; do
  run "$R" "$T/nolib/$s.sh" x y
  check_rc "lib 없음: $s.sh 가 멈춘다" 3
done
run "$R" "$T/nolib/find.sh" "$SNAP" fix/5-unique
hasnt "lib 없음: find.sh 가 판정을 내지 않는다" "NONE"
run "$R" "$T/nolib/residue.sh" 5
hasnt "lib 없음: residue.sh 가 판정을 내지 않는다" "CLEAN"
run "$R" "$T/nolib/detached-check.sh" fix/5-unique
hasnt "lib 없음: detached-check.sh 가 판정을 내지 않는다" "NO_BRANCH"

# ---------------------------------------------------------------- lib.sh 의 함수 확인 블록
# 판정 스크립트는 lib.sh 를 불러온 바로 다음 줄에 똑같은 확인 블록을 두고, 그 목록은 lib.sh 의 함수 정의와 같아야
# 한다(lib.sh 머리말). 블록이 하나라도 다르거나 lib.sh 에 함수를 더하고 목록을 안 고치면, 빠진 함수를 못 잡는
# 스크립트가 생긴다.
lib_funcs=$(LC_ALL=C sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)().*/\1/p' "$S/lib.sh")
# 위 추출은 줄 맨 앞의 `이름()` 꼴만 본다 — `function 이름 {`·`이름 () {` 처럼 다른 꼴로 정의한 함수는 놓친다. 그래서
# lib.sh 를 실제로 불러 bash 가 아는 함수와 견준다(환경에서 물려받은 함수가 끼지 않게 env -i 로).
lib_defined=$(env -i PATH="$PATH" bash -c '. "$1" >/dev/null 2>&1; declare -F' _ "$S/lib.sh" |
  LC_ALL=C sed 's/^declare -f //' | LC_ALL=C sort)
if [ -n "$lib_defined" ] && [ "$(printf '%s\n' "$lib_funcs" | LC_ALL=C sort)" = "$lib_defined" ]; then
  ok
else
  bad "함수 확인: lib.sh 의 함수는 모두 줄 맨 앞에 '이름()' 꼴로 정의한다(목록을 뽑을 수 있게)" "줄 맨 앞 '이름()':
$lib_funcs
불러 보면 있는 함수:
$lib_defined"
fi
UNSET_MSG="실패: 부른 셸에서 물려받은 함수를 지우지 못했다(lib.sh 머리말)"
CLEAR_LINE="builtin unset -f -- \$(builtin compgen -A function) || { echo \"$UNSET_MSG\" >&2; exit 3; }"
ref_block=
for f in "$S"/*.sh; do
  s=${f##*/}
  [ "$s" = lib.sh ] && continue
  # 불러오는 줄 다음부터 확인 메시지 줄까지. 불러오는 줄이 없거나 바로 다음이 확인이 아니면 첫 줄이 어긋난다.
  block=$(LC_ALL=C awk 'p { print; if (index($0, "exit 3; }")) exit; next } index($0, "/lib.sh\" || exit 3") { p = 1 }' "$f")
  case "$block" in
    'declare -F '*) ok ;;
    *) bad "함수 확인: $s 는 lib.sh 를 불러온 바로 다음 줄에 확인 블록을 둔다" "불러온 다음 줄들:
$block" ;;
  esac
  # 불러오는 줄 바로 앞 줄 — 물려받은 함수를 지우고, 못 지우면 멈추는 줄이어야 한다(lib.sh 머리말).
  before=$(LC_ALL=C awk 'index($0, "/lib.sh\" || exit 3") { print prev; exit } { prev = $0 }' "$f")
  if [ "$before" = "$CLEAR_LINE" ]; then
    ok
  else
    bad "함수 확인: $s 는 lib.sh 를 불러오기 바로 앞 줄에서 물려받은 함수를 지운다" "불러오기 앞 줄: $before"
  fi
  if [ -z "$ref_block" ]; then
    ref_block=$block
    ref_name=$s
  elif [ "$block" = "$ref_block" ]; then
    ok
  else
    bad "함수 확인: $s 의 확인 블록이 $ref_name 와 같다" "$s:
$block
$ref_name:
$ref_block"
  fi
done
block_funcs=$(printf '%s\n' "$ref_block" | LC_ALL=C sed -n '1,/>\/dev\/null/p' |
  LC_ALL=C sed -e 's/^declare -F //' -e 's/ >\/dev\/null.*//' -e 's/ *\\$//' | tr -s ' ' '\n' | LC_ALL=C grep -v '^$')
if [ -n "$lib_funcs" ] && [ "$block_funcs" = "$lib_funcs" ]; then
  ok
else
  bad "함수 확인: 확인 블록의 목록이 lib.sh 의 함수 정의와 같다(순서까지)" "lib.sh:
$lib_funcs
블록:
$block_funcs"
fi
# die_usage·die_env 는 종료 코드를 숫자로 바로 쓴다 — 변수로 두었더니 정의가 빠지거나 셸에서 넘어오거나 -u 에 걸려
# 255·0·1 이 났다(실측). 변수를 다시 들이면 여기서 잡는다.
if LC_ALL=C grep -Eq '^die_usage\(\) \{ .*; exit 2; \}$' "$S/lib.sh" &&
  LC_ALL=C grep -Eq '^die_env\(\) \{ .*; exit 3; \}$' "$S/lib.sh"; then
  ok
else
  bad "함수 확인: lib.sh 의 die_usage·die_env 는 종료 코드를 숫자(2·3)로 바로 쓴다" "$(LC_ALL=C grep -n '^die_' "$S/lib.sh")"
fi

# ---------------------------------------------------------------- lib.sh 에 함수가 빠졌을 때
# 스크립트와 lib.sh 의 버전이 어긋나 함수 하나만 빠져도 판정 키워드를 내지 않고 멈춘다 — 그냥 이어 가면 그 함수가
# command not found 로 흘러 판정이 exit 0 으로 나갔다(한때는 rev_parse 만 막았다). 확인은 불러온 바로
# 다음 줄에 있어 인자와 상관없이 그 메시지 한 줄만 나와야 한다 — 판정 키워드나 사용법 오류가 함께 나오면 확인을
# 지나친 것이다.
LIBFN_MSG="실패: lib.sh 에 판정 스크립트가 쓰는 함수가 없다 — 이 스크립트와 lib.sh 의 버전이 어긋났다(lib.sh 머리말)"
nofn() {
  mkdir -p "$T/nofn-$1"
  cp "$S"/*.sh "$T/nofn-$1/"
  printf '\nunset -f %s\n' "$1" >> "$T/nofn-$1/lib.sh"
}
only_libfn_msg() {
  if [ "$RC" -eq 3 ] && [ "$OUT" = "$LIBFN_MSG" ]; then ok; else bad "$1" "기대: rc 3 과 확인 메시지 한 줄, rc=$RC, 출력:
$OUT"; fi
}
# 모든 판정 스크립트가 직접 쓰는 die_usage 를 빼고 돌린다.
nofn die_usage
for f in "$S"/*.sh; do
  s=${f##*/}
  [ "$s" = lib.sh ] && continue
  run "$R" "$T/nofn-die_usage/$s" x y
  only_libfn_msg "함수 없음(die_usage): $s 가 확인 메시지로 멈춘다"
done
# 이전 실측 표 — 고치기 전에는 판정 키워드를 exit 0 으로 냈다.
nofn print_path_line
run "$T" "$T/nofn-print_path_line/skill-repo.sh" "$RS/.claude/skills/issue"
only_libfn_msg "함수 없음(print_path_line): skill-repo.sh 가 path 줄 없는 FOUND 를 내지 않는다"
run "$R" "$T/nofn-die_usage/same-repo.sh"
only_libfn_msg "함수 없음(die_usage): same-repo.sh 를 인자 없이 불러도 OTHER_REPO 를 내지 않는다"
run "$R" "$T/nofn-die_usage/same-repo.sh" /tmp
only_libfn_msg "함수 없음(die_usage): same-repo.sh /tmp 이 OTHER_REPO 를 내지 않는다"
# 부른 셸이 같은 이름의 함수를 export 해 두어도 확인을 지나치지 않는다(이전 codex 리뷰). 위 nofn 은 끝에
# unset -f 를 덧붙여 물려받은 함수까지 지우므로, 여기서는 정의 줄을 지운 lib.sh 로 실제 낡은 판을 흉내 낸다.
mkdir -p "$T/nodef-print_path_line"
cp "$S"/*.sh "$T/nodef-print_path_line/"
LC_ALL=C sed '/^print_path_line() /d' "$S/lib.sh" > "$T/nodef-print_path_line/lib.sh"
LC_ALL=C grep -q '^print_path_line() ' "$T/nodef-print_path_line/lib.sh" && setup_fail "print_path_line 정의를 지우지 못했다"
run "$T" -c 'print_path_line() { :; }; export -f print_path_line; bash "$@"' _ \
  "$T/nodef-print_path_line/skill-repo.sh" "$RS/.claude/skills/issue"
only_libfn_msg "함수 없음(print_path_line, 셸이 같은 이름을 export): skill-repo.sh 가 path 줄 없는 FOUND 를 내지 않는다"
# 모든 판정 스크립트도 — die_usage 정의를 지운 lib.sh 와, 아무 일도 안 하는 die_usage 를 export 한 셸에서.
mkdir -p "$T/nodef-die_usage"
cp "$S"/*.sh "$T/nodef-die_usage/"
LC_ALL=C sed '/^die_usage() /d' "$S/lib.sh" > "$T/nodef-die_usage/lib.sh"
LC_ALL=C grep -q '^die_usage() ' "$T/nodef-die_usage/lib.sh" && setup_fail "die_usage 정의를 지우지 못했다"
for f in "$S"/*.sh; do
  s=${f##*/}
  [ "$s" = lib.sh ] && continue
  run "$R" -c 'die_usage() { :; }; export -f die_usage; bash "$@"' _ "$T/nodef-die_usage/$s" x y
  only_libfn_msg "함수 없음(die_usage, 셸이 같은 이름을 export): $s 가 확인 메시지로 멈춘다"
done
# die_env 는 rev_parse 안에서 불린다 — 예전 반환값 블록으로도 못 막던 경우다(소유권 오류 자리에서 판정 키워드).
nofn die_env
run "$R" -c 'GIT_TEST_ASSUME_DIFFERENT_OWNER=1 bash "$@"' _ "$T/nofn-die_env/same-repo.sh" "$R"
only_libfn_msg "함수 없음(die_env): 소유권 오류 자리에서 same-repo.sh 가 OTHER_REPO 를 내지 않는다"
run "$R" -c 'GIT_TEST_ASSUME_DIFFERENT_OWNER=1 bash "$@"' _ "$T/nofn-die_env/isolation-check.sh"
only_libfn_msg "함수 없음(die_env): 소유권 오류 자리에서 isolation-check.sh 가 판정을 내지 않는다"
# 이름이 - 로 시작하는 함수를 함께 물려받아도 지우는 줄이 나머지를 지운다 — 이름 앞에 -- 가 없을 때는 unset 이 옵션
# 오류로 하나도 지우지 않고 이어 가, 이 셸에서 skill-repo.sh 가 path 줄 없는 FOUND 를 exit 0 으로 냈다(이전 실측).
run "$T" -c 'function -x { :; }; print_path_line() { :; }; export -f -- -x print_path_line; bash "$@"' _ \
  "$T/nodef-print_path_line/skill-repo.sh" "$RS/.claude/skills/issue"
only_libfn_msg "함수 없음(print_path_line, 셸이 -x 와 같은 이름을 export): skill-repo.sh 가 path 줄 없는 FOUND 를 내지 않는다"
for f in "$S"/*.sh; do
  s=${f##*/}
  [ "$s" = lib.sh ] && continue
  run "$R" -c 'function -x { :; }; die_usage() { :; }; export -f -- -x die_usage; bash "$@"' _ "$T/nodef-die_usage/$s" x y
  only_libfn_msg "함수 없음(die_usage, 셸이 -x 와 같은 이름을 export): $s 가 확인 메시지로 멈춘다"
done
# 온전한 lib.sh 면 -x 를 물려받아도 판정이 그대로다 — -- 가 지우기를 살리고, 지울 것이 없거나 다 지우면 이어 간다.
# 셸이 EXIT_USAGE·EXIT_ENV 를 넘기거나 -u 로 불러도 그대로다 — die_usage·die_env 는 숫자로 끝난다. 인자 없이
# 불러 비교한다 — 인자를 주면 스냅숏을 쓰는 스크립트가 있다. 그래서 대부분 die_usage 갈래만 보고, die_env 갈래는 아래
# 소유권 문제 절이 본다. -u 가 지켜지는 것도 이 갈래들까지다 — 판정 갈래에는 bash 3.2 가 빈 배열을 펼치다 -u 에 걸리는
# 곳이 있다(스크립트는 set -u 를 쓰지 않는다 — lib.sh 머리말).
run "$T" -c 'function -x { :; }; export -f -- -x; bash "$@"' _ "$S/skill-repo.sh" "$RS/.claude/skills/issue"
check "물려받은 -x: skill-repo.sh 가 판정한다" FOUND
skill_root_is "물려받은 -x: skill-repo.sh 가 path 줄을 낸다" "$RS"
for f in "$S"/*.sh; do
  s=${f##*/}
  [ "$s" = lib.sh ] && continue
  run "$R" "$f"
  base_out=$OUT
  base_rc=$RC
  run "$R" -c 'function -x { :; }; export -f -- -x; bash "$@"' _ "$f"
  if [ "$RC" = "$base_rc" ] && [ "$OUT" = "$base_out" ]; then ok; else bad "물려받은 -x: $s 가 물려받지 않았을 때와 같다" "물려받지 않음(rc=$base_rc):
$base_out
물려받음(rc=$RC):
$OUT"; fi
  run "$R" -c 'EXIT_USAGE=0 EXIT_ENV=0 bash "$@"' _ "$f"
  if [ "$RC" = "$base_rc" ] && [ "$OUT" = "$base_out" ]; then ok; else bad "물려받은 EXIT_USAGE=0·EXIT_ENV=0: $s 가 물려받지 않았을 때와 같다" "물려받지 않음(rc=$base_rc):
$base_out
물려받음(rc=$RC):
$OUT"; fi
  run "$R" -c 'bash -u "$@"' _ "$f"
  if [ "$RC" = "$base_rc" ] && [ "$OUT" = "$base_out" ]; then ok; else bad "bash -u 로 부름: $s 가 그냥 불렀을 때와 같다" "그냥 부름(rc=$base_rc):
$base_out
-u 로 부름(rc=$RC):
$OUT"; fi
done
# BASH_ENV 가 종료 코드 변수 이름을 readonly 로 걸어도 판정이 그대로다 — lib.sh 가 그 이름에 대입하지 않는다. 변수로
# 두었을 때는 lib.sh 의 대입이 실패해 확인 블록이 버전 어긋남을 탓하며 멈췄다(이전 실측).
printf 'readonly EXIT_USAGE=0 EXIT_ENV=0\n' > "$T/bashenv-readonly-exit"
run "$R" -c 'e=$1; shift; BASH_ENV=$e bash "$@"' _ "$T/bashenv-readonly-exit" "$S/same-repo.sh" "$R"
if [ "$RC" -eq 0 ] && [ "$OUT" = SAME_REPO ]; then ok; else bad "readonly 종료 코드 변수(BASH_ENV): same-repo.sh 가 bash 오류 없이 SAME_REPO 를 낸다" "rc=$RC, 출력:
$OUT"; fi
# 지울 수 없는 함수(BASH_ENV 가 readonly 로 정의한 것)를 만나면 지우는 줄이 멈춘다 — 이어 가면 그 함수가 lib.sh 의
# 같은 이름 정의를 막아, 온전한 lib.sh 로도 skill-repo.sh 가 path 줄 없는 FOUND 를 exit 0 으로 냈다(이전 실측).
# bash 가 먼저 지우지 못한 이유를 한 줄 내므로 출력 전체가 아니라 끝줄과 줄 수를 본다.
printf 'print_path_line() { :; }\nreadonly -f print_path_line\n' > "$T/bashenv-readonly"
only_unset_msg() {
  if [ "$RC" -eq 3 ] && [ "$(printf '%s\n' "$OUT" | sed -n '$p')" = "$UNSET_MSG" ] &&
    [ "$(printf '%s\n' "$OUT" | LC_ALL=C grep -c '')" -eq 2 ]; then ok; else bad "$1" "기대: rc 3, bash 오류 한 줄 뒤 지우기 실패 메시지, rc=$RC, 출력:
$OUT"; fi
}
for f in "$S"/*.sh; do
  s=${f##*/}
  [ "$s" = lib.sh ] && continue
  run "$R" -c 'e=$1; shift; BASH_ENV=$e bash "$@"' _ "$T/bashenv-readonly" "$f" x y
  only_unset_msg "지울 수 없는 함수(BASH_ENV 의 readonly): $s 가 지우기 실패로 멈춘다"
done
run "$T" -c 'e=$1; shift; BASH_ENV=$e bash "$@"' _ "$T/bashenv-readonly" "$S/skill-repo.sh" "$RS/.claude/skills/issue"
hasnt "지울 수 없는 함수(BASH_ENV 의 readonly): skill-repo.sh 가 path 줄 없는 FOUND 를 내지 않는다" "FOUND"

# ---------------------------------------------------------------- 소유권 문제(safe.directory)
# 소유권 문제도 "레포 밖"이 아니다 — git 의 테스트용 변수로 흉내 낸다(git 2.35.3·2.31.8 부터 있다). 그 변수를 모르는
# git 이면 소유권 오류가 나지 않으니 이유를 알리고 건너뛴다 — 스크립트 결함이 아니라 테스트 도구가 없는 것이다.
# 변수는 판정 스크립트 호출에만 붙인다 — 준비의 git 명령에 붙으면 준비가 깨진다.
# 건너뛸지는 git 이 정말 소유권 오류를 내는지로 정한다 — 다른 이유로 실패한 것을 "변수가 듣는다"로 읽으면 엉뚱한
# 실패가 스크립트 결함처럼 보인다.
owner_test=
owner_probe=$(GIT_TEST_ASSUME_DIFFERENT_OWNER=1 LC_ALL=C git -C "$R" rev-parse --git-dir 2>&1 >/dev/null)
case "$owner_probe" in
  *'dubious ownership'*) owner_test=1 ;;
  *) echo "건너뜀: 이 git($(git --version))에서는 GIT_TEST_ASSUME_DIFFERENT_OWNER=1 이 소유권 오류를 내지 않아 소유권 오류 테스트를 돌리지 않는다${owner_probe:+ — ${owner_probe%%$'\n'*}}" >&2 ;;
esac
if [ -n "$owner_test" ]; then
  run "$R" -c 'GIT_TEST_ASSUME_DIFFERENT_OWNER=1 bash "$@"' _ "$S/same-repo.sh" "$R"
  check_rc "소유권: same-repo.sh 는 환경 실패" 3
  has_prefix "소유권: same-repo.sh 의 stderr" "실패: git 오류(레포 밖이 아니다): fatal: detected dubious ownership"
  # die_env 갈래도 셸이 EXIT_ENV=0 을 넘기거나 -u 로 불러도 3 으로 끝난다 — 종료 코드를 변수로 두었을 때는 정의가 빠진
  # lib.sh 와 겹치면 0·1 이 났다(실측).
  run "$R" -c 'EXIT_ENV=0 GIT_TEST_ASSUME_DIFFERENT_OWNER=1 bash "$@"' _ "$S/same-repo.sh" "$R"
  check_rc "소유권(셸이 EXIT_ENV=0 을 넘김): same-repo.sh 는 환경 실패" 3
  run "$R" -c 'GIT_TEST_ASSUME_DIFFERENT_OWNER=1 bash -u "$@"' _ "$S/same-repo.sh" "$R"
  check_rc "소유권(bash -u): same-repo.sh 는 환경 실패" 3
  run "$T" -c 'GIT_TEST_ASSUME_DIFFERENT_OWNER=1 bash "$@"' _ "$S/skill-repo.sh" "$RS/.claude/skills/issue"
  check_rc "소유권: skill-repo.sh 는 환경 실패" 3
  has_prefix "소유권: skill-repo.sh 의 stderr" "실패: git 오류(레포 밖이 아니다): fatal: detected dubious ownership"
  run "$R" -c 'GIT_TEST_ASSUME_DIFFERENT_OWNER=1 bash "$@"' _ "$S/isolation-check.sh"
  check_rc "소유권: isolation-check.sh 는 환경 실패" 3
  has_prefix "소유권: isolation-check.sh 의 stderr" "실패: git 오류(레포 밖이 아니다): fatal: detected dubious ownership"
  run "$BC/docs+137-x" -c 'GIT_TEST_ASSUME_DIFFERENT_OWNER=1 bash "$@"' _ "$S/branch-issue.sh" "$RB"
  check_rc "소유권: branch-issue.sh 는 환경 실패" 3
  hasnt "소유권: branch-issue.sh 가 NONE 을 내지 않는다" "NONE"
fi

# ---------------------------------------------------------------- dangling 등록의 remove 동작
# 문서 0번 ④의 dangling 갈래가 기대는 git 동작을 고정한다.
# 디렉터리가 남은 dangling 등록: HEAD 를 못 읽어 전부 미커밋으로 보여 remove 가 거부한다.
add "$CC/fix+41-dangle" fix/41-dangle
touch "$CC/fix+41-dangle/wip.txt"
g update-ref -d refs/heads/fix/41-dangle
run "$R" -c 'git worktree remove -- "$1"' _ "$CC/fix+41-dangle"
has_prefix "dangling: 디렉터리가 남으면 remove 가 거부" "fatal: .*contains modified or untracked files"
run "$R" "$S/find.sh" "$SNAP" fix/41-dangle
check "find: 디렉터리가 남은 dangling 등록" FOUND
has "find: dangling 표시" "dangling yes"
# 디렉터리까지 없는 dangling 등록(prunable): remove 가 exit 0 으로 등록만 지운다.
g worktree remove -- "$CC/fix+24-ghost"
run "$R" "$S/find.sh" "$SNAP" fix/24-ghost
hasnt "find: dangling+prunable 등록은 remove 로 치워진다" "path $CC/fix+24-ghost"

# ---------------------------------------------------------------- 되살아난 prunable 등록
# 사람이 디렉터리를 지운 뒤 Finder·JetBrains IDE 가 되살리면 remove 로는 못 지우고 prune 으로만 치운다(문서 3번 갈래의 전제).
# prune 은 다른 prunable 픽스처도 지우므로 맨 끝에 둔다.
run "$R" "$S/orphan-check.sh" "$C/fix+17-revived"
check "orphan: 되살아난 prunable 자리" REGISTERED
has_prefix "orphan: 되살아난 자리는 prunable 표시" "prunable "
run "$R" "$S/orphan-check.sh" "$C/fix+5-unique"
if printf '%s\n' "$OUT" | LC_ALL=C grep -q '^prunable'; then
  bad "orphan: 살아 있는 등록에는 prunable 표시가 없음" "$OUT"
else
  ok
fi
OUT=$(cd "$R" && git worktree remove -- "$CC/fix+17-revived" 2>&1)
RC=$?
case "$OUT" in
  *"validation failed"*".git' does not exist"*) ok ;;
  *) bad "git: 되살아난 prunable 자리의 remove 는 validation failed(전제)" "rc=$RC $OUT" ;;
esac
OUT=$(cd "$R" && git worktree prune --dry-run -v 2>&1)
if printf '%s\n' "$OUT" | LC_ALL=C grep -Fq "Removing worktrees/fix+17-revived: "; then ok; else bad "git: prune --dry-run 은 'Removing worktrees/<id>: <이유>' 꼴로 그 등록을 낸다(문서 3번 판단법의 전제)" "$OUT"; fi
g worktree prune
run "$R" "$S/orphan-check.sh" "$C/fix+17-revived"
check "orphan: prune 뒤에는 EMPTY 판정으로" EMPTY

# ---------------------------------------------------------------- round-count.sh
# 셀프 리뷰 셈 기록(SKILL.md 4단계 "셈 기록")을 읽는다 — 이슈 워크트리 최상위의 scratchpad/issue-rounds(4단계 루프)와
# scratchpad/issue-rereview-rounds(6단계 재리뷰 루프). 기록은 SKILL.md 의 명령과 같은 꼴(mkdir -p, printf '%s\n' "<값>" >
# <파일>)로 쓴다. 워크트리를 더하므로 공용 레포가 아니라 따로 만든 레포에서 본다. 한글 경로 아래 둔다 — 본
# 체크아웃이 한글 폴더 아래 있을 수 있다.
RQ="$T/rc-$NFC_GUT/repo"
mkdir -p "$RQ"
gq() { git -C "$RQ" "$@" >/dev/null 2>&1 || setup_fail "round-count git $*"; }
gq init -q -b main
gq commit -q --allow-empty -m init
QW="$RQ/.claude/worktrees/chore+37-count"
gq worktree add -q -b chore/37-count "$QW" main
rc_put() { mkdir -p "$QW/scratchpad" && printf '%s\n' "$2" > "$QW/scratchpad/$1" || setup_fail "셈 기록 $1"; }
run "$QW" "$S/round-count.sh" review
check "round-count: 기록이 없으면" NONE
rc_put issue-rounds "counted=3 cap=10 streak=1"
run "$QW" "$S/round-count.sh" review
check "round-count: 기록이 있으면" FOUND
has "round-count: counted 줄" "counted 3"
has "round-count: cap 줄" "cap 10"
has "round-count: streak 줄" "streak 1"
if [ "$(printf '%s\n' "$OUT" | LC_ALL=C grep -c '')" -eq 4 ]; then ok; else bad "round-count: FOUND 는 네 줄이다" "$OUT"; fi
# 워크트리 하위 디렉터리에서 불러도 최상위의 기록을 읽는다.
mkdir -p "$QW/src/deep"
run "$QW/src/deep" "$S/round-count.sh" review
has "round-count: 하위 디렉터리에서 불러도 최상위 기록" "counted 3"
# 끝 줄바꿈이 없어도 읽는다(사람이 편집기로 고친 경우).
printf '%s' "counted=4 cap=10 streak=0" > "$QW/scratchpad/issue-rounds"
run "$QW" "$S/round-count.sh" review
has "round-count: 끝 줄바꿈 없이도 읽는다" "counted 4"
# 4단계 루프와 6단계 재리뷰 루프는 따로 둔다 — 재리뷰가 4단계 셈을 덮지 않는다.
run "$QW" "$S/round-count.sh" rereview
check "round-count: 재리뷰 기록은 따로다" NONE
rc_put issue-rereview-rounds "counted=2 cap=10 streak=0"
run "$QW" "$S/round-count.sh" rereview
check "round-count: 재리뷰 기록" FOUND
has "round-count: 재리뷰 counted" "counted 2"
run "$QW" "$S/round-count.sh" review
has "round-count: 재리뷰 기록이 4단계 기록을 덮지 않는다" "counted 4"
# 사람이 늘린 상한, 상한에 닿은 셈, 안전장치로 멈춘 셈(streak 3)도 읽는다.
rc_put issue-rounds "counted=12 cap=12 streak=3"
run "$QW" "$S/round-count.sh" review
check "round-count: 늘린 상한에 닿은 셈" FOUND
has "round-count: 늘린 상한" "cap 12"
has "round-count: 연속 3회로 멈춘 셈" "streak 3"
# 상한을 넘은 셈도 그대로 낸다 — 사람이 알려 준 셈이 늘리기 전 상한을 넘을 수 있고, SKILL.md 가 첫 라운드 전에 묻는다.
rc_put issue-rounds "counted=11 cap=10 streak=0"
run "$QW" "$S/round-count.sh" review
check "round-count: 상한을 넘은 셈" FOUND
has "round-count: 상한을 넘은 셈의 counted" "counted 11"
# 끝 빈 줄은 뗀다 — 편집기가 붙인 빈 줄로 셈을 묻지 않는다.
printf '%s\n\n\n' "counted=5 cap=10 streak=0" > "$QW/scratchpad/issue-rounds"
run "$QW" "$S/round-count.sh" review
check "round-count: 끝 빈 줄" FOUND
has "round-count: 끝 빈 줄 뒤의 counted" "counted 5"
# 꼴이 다르면 BROKEN — 세션이 기록을 잘못 썼거나 사람이 손으로 고친 것이다. 짐작해 읽지 않고 묻게 한다. 줄이 둘이면
# (>> 로 덧붙였다) 어느 줄이 지금 셈인지 모른다.
for v in "counted=03 cap=10 streak=0" "counted=1  cap=10 streak=0" "counted=1 cap=10" "counted=1 cap=10 streak=0 x=1" \
  "cap=10 counted=1 streak=0" "counted=10000 cap=10000 streak=0" "counted=-1 cap=10 streak=0" " counted=1 cap=10 streak=0" \
  "counted=1 cap=10 streak=0 " "counted=a cap=10 streak=0" "counted=1 cap=10 streak=0"$'\r' "" \
  "counted=1 cap=10 streak=0"$'\n'"counted=2 cap=10 streak=0"; do
  rc_put issue-rounds "$v"
  run "$QW" "$S/round-count.sh" review
  check "round-count: 꼴이 다르면 BROKEN [$v]" BROKEN
  has "round-count: 꼴이 다르면 reason format [$v]" "reason format"
done
: > "$QW/scratchpad/issue-rounds"
run "$QW" "$S/round-count.sh" review
check "round-count: 빈 파일" BROKEN
has "round-count: 빈 파일은 format" "reason format"
# NUL 이 든 파일 — 명령 치환이 NUL 을 버리면 꼴에 맞는 값이 남는다.
printf 'counted=1\000 cap=10 streak=0\n' > "$QW/scratchpad/issue-rounds"
run "$QW" "$S/round-count.sh" review
check "round-count: NUL 이 든 파일" BROKEN
has "round-count: NUL 이 든 파일은 format" "reason format"
# 셈이 맞지 않으면 BROKEN range.
for v in "counted=0 cap=0 streak=0" "counted=1 cap=10 streak=4"; do
  rc_put issue-rounds "$v"
  run "$QW" "$S/round-count.sh" review
  check "round-count: 셈이 맞지 않으면 BROKEN [$v]" BROKEN
  has "round-count: 셈이 맞지 않으면 reason range [$v]" "reason range"
done
# 일반 파일이 아니면 BROKEN type — 디렉터리, 심볼릭 링크(가리키는 파일이 맞는 꼴이어도), 끊긴 링크.
rm -f "$QW/scratchpad/issue-rounds"
mkdir "$QW/scratchpad/issue-rounds"
run "$QW" "$S/round-count.sh" review
check "round-count: 디렉터리면" BROKEN
has "round-count: 디렉터리면 reason type" "reason type"
rmdir "$QW/scratchpad/issue-rounds"
printf '%s\n' "counted=1 cap=10 streak=0" > "$T/rc-target"
ln -s "$T/rc-target" "$QW/scratchpad/issue-rounds"
run "$QW" "$S/round-count.sh" review
check "round-count: 심볼릭 링크면" BROKEN
has "round-count: 심볼릭 링크면 reason type" "reason type"
rm -f "$QW/scratchpad/issue-rounds"
ln -s "$T/rc-nowhere" "$QW/scratchpad/issue-rounds"
run "$QW" "$S/round-count.sh" review
check "round-count: 끊긴 링크도 없는 기록으로 치지 않는다" BROKEN
has "round-count: 끊긴 링크는 reason type" "reason type"
rm -f "$QW/scratchpad/issue-rounds"
# scratchpad/ 자체가 링크이거나 파일이면 기록 파일이 있든 없든 type — 링크면 다른 워크트리의 기록을 읽고 덮어쓴다.
rm -rf "$QW/scratchpad"
mkdir -p "$T/rc-shared"
printf '%s\n' "counted=1 cap=10 streak=0" > "$T/rc-shared/issue-rounds"
ln -s "$T/rc-shared" "$QW/scratchpad"
run "$QW" "$S/round-count.sh" review
check "round-count: 링크인 scratchpad" BROKEN
has "round-count: 링크인 scratchpad 는 reason type" "reason type"
run "$QW" "$S/round-count.sh" rereview
check "round-count: 링크인 scratchpad 는 기록이 없어도 type" BROKEN
rm -f "$QW/scratchpad"
: > "$QW/scratchpad"
run "$QW" "$S/round-count.sh" review
check "round-count: 파일인 scratchpad" BROKEN
has "round-count: 파일인 scratchpad 는 reason type" "reason type"
rm -f "$QW/scratchpad"
# 읽을 수 없는 기록은 환경 실패다 — 없는 기록으로 읽으면 셈이 처음으로 돌아간다. root 는 000 파일도 읽으므로 root 가
# 아닐 때만 본다.
if [ "$(id -u)" -ne 0 ]; then
  rc_put issue-rounds "counted=1 cap=10 streak=0"
  chmod 000 "$QW/scratchpad/issue-rounds"
  run "$QW" "$S/round-count.sh" review
  check_rc "round-count: 읽을 수 없는 기록은 환경 실패" 3
  hasnt "round-count: 읽을 수 없는 기록을 NONE 으로 내지 않는다" "NONE"
  chmod 644 "$QW/scratchpad/issue-rounds"
fi
# 워크트리마다 따로다 — 다른 이슈 워크트리의 기록을 읽지 않는다.
gq worktree add -q -b fix/38-other "$RQ/.claude/worktrees/fix+38-other" main
run "$RQ/.claude/worktrees/fix+38-other" "$S/round-count.sh" review
check "round-count: 다른 워크트리의 기록은 읽지 않는다" NONE
# 본 체크아웃에서 부르면 판정하지 않는다 — 본 체크아웃의 scratchpad/ 는 어느 이슈의 것도 아니다.
mkdir -p "$RQ/scratchpad"
printf '%s\n' "counted=1 cap=10 streak=0" > "$RQ/scratchpad/issue-rounds"
run "$RQ" "$S/round-count.sh" review
check_rc "round-count: 본 체크아웃은 환경 실패" 3
hasnt "round-count: 본 체크아웃에서 FOUND 를 내지 않는다" "FOUND"
# 사용법 오류: 인자 개수, 모르는 루프.
run "$QW" "$S/round-count.sh"
check_rc "round-count: 인자 없음은 사용법 오류" 2
run "$QW" "$S/round-count.sh" review x
check_rc "round-count: 인자 둘은 사용법 오류" 2
run "$QW" "$S/round-count.sh" Review
check_rc "round-count: 모르는 루프는 사용법 오류" 2
# 레포 밖에서 부르면 NONE 이 아니라 환경 실패다.
mkdir -p "$T/rc-outside"
run "$T/rc-outside" "$S/round-count.sh" review
check_rc "round-count: 레포 밖은 환경 실패" 3
hasnt "round-count: 레포 밖에서 NONE 을 내지 않는다" "NONE"
# git 이 "레포가 아니다" 밖의 이유로 실패해도 환경 실패다 — 지워진 등록을 가리키는 .git 파일.
mkdir -p "$T/rc-stale"
printf 'gitdir: %s\n' "$RQ/.git/worktrees/rc-gone" > "$T/rc-stale/.git"
run "$T/rc-stale" "$S/round-count.sh" review
check_rc "round-count: 깨진 .git 파일은 환경 실패" 3
has_prefix "round-count: 깨진 .git 파일의 stderr" "실패: git 오류(레포 밖이 아니다)"

# ---------------------------------------------------------------- 문서
SKILL_DIR=$(cd "$HERE/.." && pwd -P)
DOCS=("$SKILL_DIR/SKILL.md" "$SKILL_DIR/references/worktree.md" "$SKILL_DIR/references/merge-cleanup.md")
for f in "${DOCS[@]}"; do
  if [ -f "$f" ]; then ok; else bad "문서: 파일이 있다" "$f"; fi
done
cat "${DOCS[@]}" > "$T/docs.txt" 2>/dev/null

# 스킬을 부를 때 SKILL.md 본문의 달러+숫자·달러+ARGUMENTS 자리는 인자로 치환된다.
OUT=$(LC_ALL=C grep -nE '\$[0-9]|\$\{?ARGUMENTS' "$SKILL_DIR/SKILL.md")
if [ -z "$OUT" ]; then ok; else bad "문서: SKILL.md 에 인자 치환 자리표시자가 없다" "$OUT"; fi

# 문서가 부르는 스크립트는 다 있고, scripts/ 의 스크립트는 문서 어딘가에서 불린다.
for s in $(LC_ALL=C grep -ohE 'scripts/[a-z-]+\.sh' "$T/docs.txt" | LC_ALL=C sort -u); do
  if [ -f "$SKILL_DIR/$s" ]; then ok; else bad "문서: 부르는 스크립트가 있다" "$s"; fi
done
for f in "$S"/*.sh; do
  name=${f##*/}
  [ "$name" = lib.sh ] && continue
  if LC_ALL=C grep -Fq "scripts/$name" "$T/docs.txt"; then ok; else bad "문서: 스크립트를 부르는 곳이 있다" "$name"; fi
done

# 스크립트가 내는 판정 키워드는 문서에 다 적혀 있어야 한다 — 안 적힌 키워드는 갈래가 없다는 뜻이다.
for k in $(LC_ALL=C grep -ohE '(echo "?|state=|verdict=)[A-Z][A-Z_]+' "$S"/*.sh |
  sed -E 's/^(echo "?|state=|verdict=)//' | LC_ALL=C sort -u); do
  if LC_ALL=C grep -qw -- "$k" "$T/docs.txt"; then ok; else bad "문서: 판정 키워드가 적혀 있다" "$k"; fi
done

# 문서의 명령 예시(git·gh·bash 명령이 든 코드 — 맨 앞이든 && ; | $( 뒤든)는 브랜치 자리를 큰따옴표 안에 둔다 —
# 예시를 그대로 옮겨 치면 브랜치 이름의 ; | & 뒤가 명령으로 실행된다. 브랜치 자리는 이름에 "브랜치"나
# "branch" 가 든 자리표시자와 이 스킬이 짓는 <타입>/… 이다. 인라인 코드는 줄을 넘기도 해서 문단 단위로 붙여 보고,
# 큰따옴표 안인지는 코드 조각 처음부터 센 " 개수가 홀수인지로 가린다. 셸 문법을 다 읽는 검사가 아니라서 못 보는
# 모양이 있다 — 예를 들어 \" 같은 이스케이프와 작은따옴표 안의 " 는 셈을 흐트러뜨리고, 코드 블록에서 \ 로 이어 쓴
# 여러 줄 명령은 git·gh·bash 가 없는 둘째 줄부터 보지 않으며, 한 문단의 백틱이 홀수면 인라인 코드 짝이 어긋난다.
# 문서에 그런 모양을 들일 때는 이 검사를 함께 고친다.
QUOTE_CHECK='
  function look(code,   rest, before, n) {
    gsub(/[[:space:]]+/, " ", code)
    sub(/^ /, "", code)
    if (code !~ /(^|[ ;&|(])(git|gh|bash) /) return
    rest = code
    before = ""
    while (match(rest, /<[^<>]*(브랜치|branch)[^<>]*>|<타입>\//)) {
      before = before substr(rest, 1, RSTART - 1)
      n = gsub(/"/, "\"", before)
      if (n % 2 == 0) { print at ": " code; return }
      before = before substr(rest, RSTART, RLENGTH)
      rest = substr(rest, RSTART + RLENGTH)
    }
  }
  # look 도 match 를 불러 RSTART·RLENGTH 를 덮어쓰므로, 다음 자리는 부르기 전에 받아 둔다(안 그러면 줄이 안 줄어
  # 끝나지 않는다).
  function flush(   line, s, l) {
    line = para
    while (match(line, /`[^`]+`/)) {
      s = RSTART
      l = RLENGTH
      look(substr(line, s + 1, l - 2))
      line = substr(line, s + l)
    }
    para = ""
  }
  FNR == 1 { if (para != "") flush(); fence = 0 }
  /^[[:space:]]*```/ { if (para != "") flush(); fence = !fence; next }
  fence { at = FILENAME ":" FNR; look($0); next }
  /^[[:space:]]*$/ { if (para != "") flush(); next }
  { if (para == "") at = FILENAME ":" FNR; para = para " " $0 }
  END { if (para != "") flush() }
'
OUT=$(LC_ALL=C awk "$QUOTE_CHECK" "${DOCS[@]}")
if [ -z "$OUT" ]; then ok; else bad "문서: 명령 예시의 브랜치 자리는 큰따옴표 안에 있다" "$OUT"; fi
# 위 검사가 실제로 잡는지 표본으로 본다 — 줄을 넘는 인라인 코드, 코드 블록, <타입>/… 자리도 잡고, 감싼 것·명령이
# 아닌 코드(오류 문구)는 넘긴다.
printf '%s\n' '예시 `git branch -D <브랜치>` 와 `gh pr list --head' '<브랜치> --json number`.' '' \
  '```' 'bash "<사본>/scripts/find.sh" "<스냅숏>" <브랜치>' 'git branch -m <타입>/<번호>-<슬러그>' '```' '' \
  '`cd "<경로>" && git branch -D <브랜치>` 와 `OUT=$(git log ..refs/heads/<브랜치>)`.' > "$T/doc-probe-bad.md"
OUT=$(LC_ALL=C awk "$QUOTE_CHECK" "$T/doc-probe-bad.md")
count_lines "문서: 따옴표 검사가 && 뒤의 명령도 잡는다" "$T/doc-probe-bad.md:9: cd \"<경로>\" && git branch -D <브랜치>" 1
count_lines "문서: 따옴표 검사가 \$( 안의 명령도 잡는다" "$T/doc-probe-bad.md:9: OUT=\$(git log ..refs/heads/<브랜치>)" 1
count_lines "문서: 따옴표 검사가 줄 단위 인라인 코드를 잡는다" "$T/doc-probe-bad.md:1: git branch -D <브랜치>" 1
count_lines "문서: 따옴표 검사가 줄을 넘는 인라인 코드를 잡는다" "$T/doc-probe-bad.md:1: gh pr list --head <브랜치> --json number" 1
count_lines "문서: 따옴표 검사가 코드 블록을 잡는다" "$T/doc-probe-bad.md:5: bash \"<사본>/scripts/find.sh\" \"<스냅숏>\" <브랜치>" 1
count_lines "문서: 따옴표 검사가 <타입>/… 자리를 잡는다" "$T/doc-probe-bad.md:6: git branch -m <타입>/<번호>-<슬러그>" 1
printf '%s\n' '예시 `git branch -D "<브랜치>"`, `git log "<M>..refs/heads/<브랜치>"`,' \
  "\`fatal: a branch named '<브랜치>' already exists\`, \`origin/<브랜치>\`." > "$T/doc-probe-good.md"
OUT=$(LC_ALL=C awk "$QUOTE_CHECK" "$T/doc-probe-good.md")
if [ -z "$OUT" ]; then ok; else bad "문서: 따옴표 검사가 감싼 것과 명령 아닌 코드는 넘긴다" "$OUT"; fi

# "시작하기 전에"는 SAME_REPO 여도 어느 레포 작업인지 확인한다 — 이 레포 안에 서 있다는 것을 근거로 바로 1단계로
# 가면, 앞선 요청에서 이 레포로 옮겨 온 세션이 다른 레포의 같은 번호를 이 레포 것으로 읽는다. 규칙은
# "어느 레포 작업인지" 한 곳에만 적고 SAME_REPO 갈래와 옮기기 2.가 그곳을 가리킨다 — 두 자리에 따로 적으면 한쪽만
# 고쳐져 갈린다.
OUT=$(LC_ALL=C grep -c '^\*\*어느 레포 작업인지\*\* — ' "$SKILL_DIR/SKILL.md")
if [ "$OUT" = 1 ]; then ok; else bad "문서: \"어느 레포 작업인지\" 규칙이 SKILL.md 한 곳에 있다" "$OUT"; fi
for want in '^- `SAME_REPO` — 아래 "어느 레포 작업인지"대로' '^2\. \*\*어느 레포 작업인지 확인한다\*\* — 위 "어느 레포 작업인지"대로'; do
  if LC_ALL=C grep -q "$want" "$SKILL_DIR/SKILL.md"; then ok; else bad "문서: 시작하기 전에의 두 갈래가 \"어느 레포 작업인지\"를 가리킨다" "$want"; fi
done
OUT=$(LC_ALL=C grep -n '`SAME_REPO` — 그대로' "$SKILL_DIR/SKILL.md")
if [ -z "$OUT" ]; then ok; else bad "문서: SAME_REPO 갈래가 묻지 않고 그대로 가는 옛 문구가 없다" "$OUT"; fi
# 다시 불러 달라는·새 세션을 열어 달라는 멈춤 문구는 모두 레포 이름을 붙여 부르게 한다 — 빠지면 다시 부른 요청에서
# 어느 레포인지부터 다시 묻는다. 줄이 아니라 목록 항목(빈 줄·항목 머리·제목에서 끊는다) 단위로 본다 — 줄 단위면 문구가
# 줄바꿈으로 갈렸을 때 맞는 문구가 실패하고, 같은 항목의 다른 문장에 붙인 안내("어느 쪽이든 레포 이름을 붙여 부르게
# 한다")를 못 본다. 한 항목에 멈춤 문구가 여럿이면 "레포 이름을 붙여"도 그만큼 있어야 한다 — 하나만 보면
# 맞는 문구 하나가 같은 항목의 다른 멈춤 문구를 가린다(셀프 리뷰 7라운드). 새 멈춤 자리를 더할 때 아래 세 꼴 중
# 하나로 쓰면 이 검사에 든다.
STOP_CHECK='
  function flush(   u, stops, names) {
    if (unit != "") {
      u = unit; stops = gsub(/(다시 불러 달라고 요청|불러 달라고 안내|새 세션을 열어 달라고 안내)/, "", u)
      u = unit; names = gsub(/레포 이름을 붙여 (다시 )?(불러|부르)/, "", u)
      if (stops > names) print at
    }
    unit = ""
  }
  FNR == 1 { flush(); fence = 0 }
  /^[[:space:]]*```/ { flush(); fence = !fence; next }
  fence { next }
  /^[[:space:]]*$/ || /^#+ / { flush(); next }
  /^[[:space:]]*(- |[0-9]+\. )/ { flush() }
  { if (unit == "") at = FILENAME ":" FNR; sub(/^[[:space:]]+/, ""); unit = unit " " $0 }
  END { flush() }
'
OUT=$(LC_ALL=C awk "$STOP_CHECK" "${DOCS[@]}")
if [ -z "$OUT" ]; then ok; else bad "문서: 다시 불러 달라는 멈춤 문구가 레포 이름을 붙이게 한다" "$OUT"; fi
# 위 검사가 실제로 잡는지 표본으로 본다 — 레포 이름 없는 새 세션 안내는 잡고, 줄바꿈으로 갈린 문구와 같은 항목의 다른
# 문장에 붙인 안내는 넘긴다.
printf '%s\n' '- 멈추고 그 레포 본 체크아웃에서 새 세션을 열어 달라고 안내한다.' '' \
  '- 멈추고 본 체크아웃 안에서 레포 이름을' '  붙여 다시 불러 달라고 요청한다.' \
  '- 그 레포에서 새 세션을 열어 달라고 안내한다. 어느 쪽이든 레포 이름을 붙여 부르게 한다.' \
  '- 멈추고 본 체크아웃 안에서 다시' '  불러 달라고 요청한다.' > "$T/stop-probe.md"
OUT=$(LC_ALL=C awk "$STOP_CHECK" "$T/stop-probe.md")
count_lines "문서: 멈춤 문구 검사가 레포 이름 없는 새 세션 안내를 잡는다" "$T/stop-probe.md:1" 1
count_lines "문서: 멈춤 문구 검사가 공백에서 줄바꿈된 문구도 잡는다" "$T/stop-probe.md:6" 1
if [ "$(printf '%s\n' "$OUT" | LC_ALL=C grep -c .)" = 2 ]; then ok; else bad "문서: 멈춤 문구 검사가 줄바꿈으로 갈린 맞는 문구와 같은 항목의 안내는 넘긴다" "$OUT"; fi
# 한 항목에 멈춤 문구가 둘인데 "레포 이름을 붙여"가 하나면 잡는다 — 맞는 문구 하나가 다른 멈춤 문구를 가리지 않게.
# 부르라는 말이 따르지 않는 "레포 이름을 붙여"(다른 설명에 든 것)는 세지 않는다.
printf '%s\n' '- 새 세션을 열어 레포 이름을 붙여 불러 달라고 안내한다. 확인이 어긋나면 멈추고 다시 불러 달라고 요청한다.' \
  '' '- 새 세션을 열어 달라고 안내한다. (레포 이름을 붙여 부른 요청이면 이 갈래로 오지 않는다)' > "$T/stop-probe2.md"
OUT=$(LC_ALL=C awk "$STOP_CHECK" "$T/stop-probe2.md")
count_lines "문서: 멈춤 문구 검사가 맞는 문구 옆의 레포 이름 없는 멈춤 문구도 잡는다" "$T/stop-probe2.md:1" 1
count_lines "문서: 멈춤 문구 검사가 부르라는 말 없는 레포 이름 언급을 세지 않는다" "$T/stop-probe2.md:3" 1
# 제거 절차가 새 세션에 적어 주는 문구는 레포 이름을 담는다 — 빠지면 새 세션이 그 문구를 받자마자 어느 레포인지부터
# 묻는다.
for want in '`머지했어 <레포 이름> PR #<PR번호> — ' '`/issue <이슈번호> <레포 이름>` 뒤에'; do
  if LC_ALL=C grep -Fq "$want" "$SKILL_DIR/references/worktree.md"; then ok; else bad "문서: 새 세션에 적어 주는 문구가 레포 이름을 담는다" "$want"; fi
done

# 셀프 리뷰 상한은 10회다. 한 자리만 고쳐 상한을 적은 세 자리(라운드 기록의 n/10, 안전장치의 10회와 "열 번을
# 넘긴")가 갈리거나, 상한의 근거 문장(codex 가 붙지 않은 동안은 셀프리뷰가 유일한 자동 리뷰다)이 빠지거나, 옛
# 숫자(5회)가 되살아나지 않았는지 본다.
for want in '센 라운드인지(n/10)와' '  - **10회**(회 = 센 라운드 수)' '열 번을 넘긴 라운드는' '셀프리뷰가 유일한 자동 리뷰라서 10회로 둔다'; do
  if LC_ALL=C grep -Fq -- "$want" "$SKILL_DIR/SKILL.md"; then ok; else bad "문서: 셀프 리뷰 상한은 10회다" "$want"; fi
done
OUT=$(LC_ALL=C grep -nE 'n/5\)|\*\*5회\*\*|다섯 번을 넘긴|이 사본은 5회' "$SKILL_DIR/SKILL.md")
if [ -z "$OUT" ]; then ok; else bad "문서: 셀프 리뷰 상한의 옛 숫자(5회)가 남지 않았다" "$OUT"; fi

# 완결 라운드 기준 — 리뷰가 판정 없이 목록만 내면 세션이 후보마다 판정을 적어 완결로
# 치고, 그 판정은 사람이 따라가 볼 수 있게 남긴다(P1·P2 가 아니라고 본 후보의 코드 근거, 가릴 수 없는 후보는 실제라면
# P1 감일 때만 멈추고 나머지는 사람에게 넘김, 라운드 기록은 PR 본문에). 깨워 받은 결과는 세되 게이트는 못 닫는다.
# 옛 문장이 되살아나 이 기준이나 기록 규칙을 되돌리지 않았는지 본다.
for want in '세션이 후보마다 코드를 확인해' '판정과 등급을 라운드 기록에 적으면 완결로 친다' '최종 목록 없이 끝난 실행' '근거가 된 코드 위치(파일:줄과 그 라운드의' '코드만 읽어서는 가릴 수 없는 후보' '"가릴 수 없음"으로 본 후보의 근거' '**실제라면 P1 감**' '그 밖이면 게이트는 막지 않고' '그 결과로는 게이트를 닫지 않는다' '**세지 않는 실행이나 깨워 받은 결과가 섞여 연속 3회**' '목록을 낸 실행은(P1·P2 가 나왔어도) 연속을 끊는다' '**라운드 기록**이라 부르고' '4단계의 **라운드 기록**을 본문에' '4단계의 라운드 기록, 개발자 확인 필요 항목'; do
  if LC_ALL=C grep -Fq -- "$want" "$SKILL_DIR/SKILL.md"; then ok; else bad "문서: 판정 없는 라운드도 세션이 판정하면 완결이다" "$want"; fi
done
OUT=$(LC_ALL=C grep -nE '미검증 후보가 남은|완결 보고\(모든 후보의 판정 포함\)|세지 않는 실행이 연속 3회' "$SKILL_DIR/SKILL.md")
if [ -z "$OUT" ]; then ok; else bad "문서: 옛 완결 기준(미검증 후보가 남은 라운드는 세지 않는다)이 남지 않았다" "$OUT"; fi

# 라운드 기록을 PR 갱신·6단계 재리뷰·멈춤 보고에도 남기는 규칙. 옛 순서(본문 파일을 PR 확인보다 먼저)가
# 돌아오면 갱신 갈래가 기존 본문을 받기 전에 파일을 쓴다. 문구는 규칙 머리만 보되, 기존 본문을 받는 명령은 격리
# 세션에서 실행해 본 그대로라 통째로 본다.
for want in '어느 단계에서 어떤 이유로 멈추든 그 보고에도 싣는다' '**이어받은 실행의 셈**' '셈을 PR 본문 기록에서 읽어 잇지는 않는다' '**갱신 갈래는 기존 본문에서 시작한다**' 'gh pr view <번호> --json body --jq '"'"'.body | gsub("\r"; "") | sub("\n+$"; "")'"'"' > "<파일>"' '`gh pr view` 가 0 이 아닌 종료 코드로 끝나면 그 파일을 지우고' '**본문을 쓸 때마다 이번 실행의 라운드 가운데 PR 에 아직 없는 것을 모두 싣는다**' '**기존 라운드 기록 칸은 고치지 않고**' '본문이 길다고 거부하면 멈추고 보고한다' '**이 재리뷰도 4단계 루프 그대로다**' '**셈은 반영 지시마다 새로 센다**'; do
  if LC_ALL=C grep -Fq -- "$want" "$SKILL_DIR/SKILL.md"; then ok; else bad "문서: 라운드 기록을 이어받기·PR 갱신·재리뷰·멈춤 보고로 잇는다" "$want"; fi
done
OUT=$(LC_ALL=C grep -n '갈림길보다 먼저 만든다' "$SKILL_DIR/SKILL.md")
if [ -z "$OUT" ]; then ok; else bad "문서: 본문 파일을 PR 갈림길보다 먼저 만드는 옛 순서가 남지 않았다" "$OUT"; fi
PR_AT=$(LC_ALL=C grep -n '이 브랜치의 PR이 이미 있는지 본다' "$SKILL_DIR/SKILL.md" | head -n 1 | cut -d: -f1)
BODY_AT=$(LC_ALL=C grep -n '^- \*\*본문 파일은 ' "$SKILL_DIR/SKILL.md" | head -n 1 | cut -d: -f1)
if [ -n "$PR_AT" ] && [ -n "$BODY_AT" ] && [ "$PR_AT" -lt "$BODY_AT" ]; then ok; else bad "문서: 5단계는 PR 이 있는지 본 뒤에 본문 파일을 만든다" "PR 확인 ${PR_AT}줄, 본문 파일 ${BODY_AT}줄"; fi

# 셈 기록 — 셈은 이슈 워크트리의 scratchpad/ 파일 한 줄에 두고 round-count.sh 로 읽는다. 쓰는 명령은 문서에
# 있고(스크립트는 판정만 한다), 그 파일 이름은 스크립트가 읽는 이름·ignored-check.sh 가 지워도 되는 것으로 치는 이름과
# 같아야 한다 — 하나만 바뀌면 셈을 못 잇거나 머지 정리가 매번 멈춘다. 쓰기는 git config 가 아니다 — 격리 세션의 명령
# 가드가 공유 설정에 쓰는 git config 를 거부한다(실측). 사람에게 셈을 알려 달라고 하던 옛 인계 문구가 돌아오면 기록과
# 사람 말이 둘 다 셈의 출처가 된다.
for want in '- **셈 기록** — ' 'printf '"'"'%s\n'"'"' "counted=<센 라운드 수> cap=<상한> streak=<연속 3회 셈>" > "<워크트리 루트>/scratchpad/issue-rounds"' 'printf '"'"'%s\n'"'"' "counted=<센 라운드 수> cap=<상한> streak=<연속 3회 셈>" > "<워크트리 루트>/scratchpad/issue-rereview-rounds"' 'mkdir -p "<워크트리 루트>/scratchpad"' 'printf '"'"'%s\n'"'"' "counted=0 cap=10 streak=0" > "<워크트리 루트>/scratchpad/issue-rounds"' 'bash "<스킬 디렉터리>/scripts/round-count.sh" review' '`bash "<스킬 디렉터리>/scripts/round-count.sh" rereview`' '- `NONE`·`BROKEN` — 기록이 없거나' '사람이 그 요청에서 셈을 밝혔으면 밝힌 것은 기록보다 그 값을 쓴다' '일부만 밝혔으면 나머지는 `FOUND` 면 기록에서 잇고' '`streak` 가 3 이면 앞 실행이 연속 3회로 멈춘 것이니' '`counted=0 cap=10 streak=0` 을 쓰고'; do
  if LC_ALL=C grep -Fq -- "$want" "$SKILL_DIR/SKILL.md"; then ok; else bad "문서: 셈은 워크트리의 셈 기록 파일로 잇는다" "$want"; fi
done
for want in '  review) name=issue-rounds ;;' '  rereview) name=issue-rereview-rounds ;;'; do
  if LC_ALL=C grep -Fqx -- "$want" "$S/round-count.sh"; then ok; else bad "문서: round-count.sh 가 문서의 셈 기록 파일을 읽는다" "$want"; fi
done
if LC_ALL=C grep -Fqx -- '    .claude/settings.local.json | scratchpad/issue-rounds | scratchpad/issue-rereview-rounds)' "$S/ignored-check.sh"; then ok; else bad "문서: ignored-check.sh 가 셈 기록 두 파일을 지워도 되는 것으로 친다" "regenerable()"; fi
OUT=$(LC_ALL=C grep -nE '셈을 함께 알려|4단계 셈 모름|git config --replace-all' "$SKILL_DIR/SKILL.md")
if [ -z "$OUT" ]; then ok; else bad "문서: 옛 인계 문구와 브랜치 설정 쓰기가 남지 않았다" "$OUT"; fi

# 번호 없는 머지 정리는 컨테이너의 링크도 모은다 — -type d 만 보면 디렉터리를 가리키는 링크 잔재를 놓친다(residue.sh 와
# 같은 이유, 위 "머지 정리 find" 테스트). 고아 디렉터리를 지우기 직전의 재확인과 재개 판정은 other-more 줄까지 본다 —
# 20개를 보여 주고 승인받은 뒤 새 파일이 21번째 뒤로 가면 other 줄은 그대로다(위 orphan-check.sh 의 20개 경계 테스트).
if LC_ALL=C grep -Fq -- 'find -H "<레포 루트>/.claude/worktrees" -mindepth 1 -maxdepth 1 \( -type d -o -type l \)' "$SKILL_DIR/references/merge-cleanup.md"; then ok; else bad "문서: 번호 없는 머지 정리가 링크도 모은다" "merge-cleanup.md"; fi
OUT=$(LC_ALL=C grep -nF -- '-maxdepth 1 -type d`' "${DOCS[@]}")
if [ -z "$OUT" ]; then ok; else bad "문서: 디렉터리만 모으는 옛 find 가 남지 않았다" "$OUT"; fi
for want in '`OTHER_FILES` 이고, `other-more` 줄이 없고, 사람이' '`OTHER_FILES` 이고 `other-more` 줄 없이 `other` 목록이'; do
  if LC_ALL=C grep -Fq -- "$want" "$SKILL_DIR/references/worktree.md"; then ok; else bad "문서: 고아 재확인은 other-more 줄까지 본다" "$want"; fi
done
# L·R 을 받는 for-each-ref 는 전체 ref 이름을 낸다 — %(refname:short) 는 같은 이름의 태그가 있으면 로컬 줄을 heads/<브랜치>
# 로 내, 줄이 셋 이상일 때 L 을 못 알아보고 "없음"으로 읽을 수 있다(위 "for-each-ref" 테스트).
for f in "$SKILL_DIR/references/worktree.md" "$SKILL_DIR/references/merge-cleanup.md"; do
  if LC_ALL=C grep -Fq -- "git for-each-ref --format='%(refname) %(objectname) %(worktreepath)'" "$f"; then ok; else bad "문서: L·R 을 받는 for-each-ref 는 전체 이름을 낸다" "$f"; fi
done
OUT=$(LC_ALL=C grep -nF -- "--format='%(refname:short)" "${DOCS[@]}")
if [ -z "$OUT" ]; then ok; else bad "문서: 짧은 이름을 내는 옛 for-each-ref 가 남지 않았다" "$OUT"; fi

# 판정 스크립트와 이 테스트는 실행 권한을 둔다(lib.sh 는 불러오기만 하므로 뺀다) — 파일을 새로 써서 바꿔 끼우면 권한이
# 빠진 채 커밋된다(이전 셀프 리뷰). 작업 트리의 권한과, git 이 인덱스에 올려 둔 모드(올렸으면)를 둘 다 본다 — 작업
# 트리에서만 chmod 하고 올리지 않으면 커밋에는 빠진 채 들어간다.
for f in "$S"/*.sh "$HERE/run.sh"; do
  [ "${f##*/}" = lib.sh ] && continue
  if [ -x "$f" ]; then ok; else bad "문서: 스크립트에 실행 권한이 있다" "$f"; fi
  mode=$(git -C "$HERE" ls-files -s -- "$f" 2>/dev/null | cut -d' ' -f1)
  if [ -z "$mode" ] || [ "$mode" = 100755 ]; then ok; else bad "문서: git 에 올린 스크립트 모드가 100755 다" "$f: $mode"; fi
done

# 판정 스크립트가 내는 branch-escaped 줄은 문서에 적혀 있어야 한다 — 안 적히면 그 줄을 받은 모델이 갈래를 모른다.
if LC_ALL=C grep -Fq 'branch-escaped' "$T/docs.txt"; then ok; else bad "문서: branch-escaped 줄이 적혀 있다" "docs"; fi

# ---------------------------------------------------------------- 요약
echo "pass $pass, fail $fail"
[ "$fail" -eq 0 ]
