#!/bin/bash
# 이 이슈 번호의 잔재(브랜치·워크트리)와 <레포 루트>/.claude/worktrees 아래의 고아를 찾는다.
# 판정만 한다.
#
# 사용: residue.sh <이슈 번호>
#   부르기 전에 git fetch origin --prune 을 해 둔다 — GitHub 이 지운 브랜치의 원격 추적 ref 가
#   남아 있으면 잔재로 잡힌다.
#   <이슈 번호>는 앞자리 0 없는 1 이상의 정수다(branch-issue.sh 와 같다). 02 를 받으면 판별식이 2- 와 맞지 않아
#   잔재를 놓치고 CLEAN 을 내므로 사용법 오류로 멈춘다.
#
# 이름 판별식: (^|/)<번호>-  또는  (^|/)[a-z-]+\+<번호>-
#   규약 브랜치(fix/278-x), 평탄화한 디렉터리(fix+278-x), 옛 EnterWorktree 이름(worktree-fix+278-x)을
#   잡고, 1278-x·feat/300-fix+278-x 는 안 잡는다. 앞자리 0 이 든 이름(fix/07-x — 번호를 0 째로 받던 옛 실행이 만들 수
#   있었다)도 잡지 않는다(알려진 한계). branch-issue.sh 도 그 이름을 규약 밖으로 보고, 0 을 허용하면 docs/01-intro 같은
#   남의 이름까지 1번 이슈 잔재로 잡는다.
# 세 가지를 훑는다:
#   - 브랜치(로컬·원격)
#   - .claude/worktrees 아래 디렉터리. 등록 여부는 이름이 아니라 등록된 경로와 같은 디렉터리인지(-ef)로
#     본다 — 이름으로 맞추면 레포 밖에 같은 이름이 있을 때 진짜 고아를 놓친다. 등록이 없는 타입 이름
#     디렉터리(feat·fix·refactor·docs·chore)는 옛 중첩 잔재(fix/278-x)로 보고 한 단계 더 본다. branch-issue.sh 가 받는
#     test 는 넣지 않는다 — 이 레포 타입 라벨이 아니라 이 사본이 test/ 를 만들 일이 없고, 흔한 이름이라(EnterWorktree(name:
#     test) 등) 안으로 내려가면 그 체크아웃의 조각이 고아 후보로 나온다.
#     .claude 나 .claude/worktrees 가 링크를 거치면 실제 경로로 바꿔 훑는다 — 그 안의 고아는 실제 경로로 나와 레포 밖으로
#     판정된다(지우기 전에 확인받는다). 옛 타입 폴더가 링크면 따라가지 않고 그 링크만 보고한다(안의 잔재는 놓친다 —
#     알려진 한계).
#   - 등록 목록의 경로 마지막 조각. 위 디렉터리 스캔에 안 걸리는 등록 — .claude/worktrees 밖에 등록된
#     것, 디렉터리가 지워지고 등록만 남은 것 — 을 잡는다. 디렉터리와 브랜치가 사라진 채 등록만 남으면
#     앞의 두 스캔이 모두 빈손인데, 그대로 두면 git worktree add 가 "missing but already registered"
#     로 실패한다.
#
# stdout 첫 줄: CLEAN(이 이슈 것 없음) | RESIDUE(있음) — 다른 이슈의 고아는 판정에 넣지 않는다
# 그 뒤
#   branch <이름>        이 이슈의 브랜치. 로컬·원격의 같은 이름은 한 줄이고 origin/ 은 뗀다. 명령에 넣을 수 없는
#                        이름이면 branch-escaped <%q 표기> 로 낸다(lib.sh branch_unsafe — 경로 줄의 -escaped 보다
#                        기준이 좁다)
#   worktree <경로>      이 이슈 이름의 등록된 워크트리 (위치·디렉터리 유무와 무관, 한 번씩). 경로는 등록된
#                        바이트 그대로다 — find.sh 의 path 줄과 같고, 디렉터리 스캔이 잡은 표기(링크 경로,
#                        다른 정규화)로 내지 않는다
#   link <경로>          .claude/worktrees 아래 심볼릭 링크 중 이 이슈 이름이고 등록된 워크트리를 가리키는 것.
#   link-target <경로>   바로 위 link 줄이 가리키는 등록 경로(본 체크아웃일 수도 있다). 그 등록이 이 이슈 이름이면
#                        worktree 줄에도 나오고, 다른 이슈 것이거나 본 체크아웃이면 worktree 줄에는 안 나온다 —
#                        링크 이름만으로 남의 등록을 이 이슈 잔재로 올리지 않는다.
#                        링크 경로에 git worktree remove 를 치면 링크가 아니라 가리키는 워크트리가 지워지고
#                        (rc 0, 실측), rm -rf 는 끝에 / 가 붙으면 가리키는 디렉터리를 비운다(실측) — 링크 자체는
#                        rm <링크> 로만 치운다
#   orphan <경로>        .claude/worktrees 아래 등록 없는 디렉터리 중 이 이슈 것(컨테이너가 링크를 거치면 실제 경로)
#   other-orphan <경로>  등록 없는 디렉터리 중 이 이슈와 무관한 것 (보고만 한다)
#
# 종료 코드: 0 판정함 · 2 사용법(인자 개수, <이슈 번호>가 앞자리 0 없는 1 이상의 정수가 아니다) · 3 환경 실패(.claude·.claude/worktrees 나 그 안의 옛 중첩 디렉터리를 읽지 못한 경우,
# .claude 나 .claude/worktrees 가 디렉터리가 아닌 경우(끊긴 링크·파일) 포함)

builtin unset -f -- $(builtin compgen -A function) || { echo "실패: 부른 셸에서 물려받은 함수를 지우지 못했다(lib.sh 머리말)" >&2; exit 3; }
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh" || exit 3
declare -F die_usage die_env rev_parse git_err_not_repo git_err_line lower_ascii norm is_unsafe \
  branch_unsafe ref_unsafe quote_c require_safe_branch head_unreadable has_non_ascii wt_dump wt_load \
  same_path_hits path_in_container print_checked_line print_path_line wt_print >/dev/null ||
  { echo "실패: lib.sh 에 판정 스크립트가 쓰는 함수가 없다 — 이 스크립트와 lib.sh 의 버전이 어긋났다(lib.sh 머리말)" >&2; exit 3; }

if [ $# -ne 1 ]; then die_usage "residue.sh <이슈 번호>"; fi
n=$1
case "$n" in
  '' | 0* | *[!0123456789]*) die_usage "이슈 번호는 앞자리 0 없는 1 이상의 정수다: $n" ;;
esac
re="(^|/)${n}-|(^|/)[a-z-]+\\+${n}-"

list=$(mktemp "${TMPDIR:-/tmp}/issue-wt-list.XXXXXX") || die_env "임시 파일을 만들 수 없다"
scan=$(mktemp "${TMPDIR:-/tmp}/issue-residue-scan.XXXXXX") || { rm -f "$list"; die_env "임시 파일을 만들 수 없다"; }
subs=$(mktemp "${TMPDIR:-/tmp}/issue-residue-subs.XXXXXX") || { rm -f "$list" "$scan"; die_env "임시 파일을 만들 수 없다"; }
trap 'rm -f "$list" "$scan" "$subs"' EXIT
wt_dump "$list"
wt_load "$list"
root=${WT_PATH[0]}
[ -d "$root" ] || die_env "레포 루트가 디렉터리가 아니다: $root"

verdict=CLEAN
kinds=()
values=()
checks=()
# 셋째 인자는 그 값을 낼 때 쓸 판정 함수다 — 브랜치 줄만 기준이 좁다(lib.sh branch_unsafe).
add_line() { kinds+=("$1"); values+=("$2"); checks+=("${3:-is_unsafe}"); }

# git branch -a 를 쓰지 않는다 — 지금 워크트리가 bisect·detached 중이면 유사 줄을 함께 낸다(실측):
#   (no branch, bisect started on fix/40-x)      (HEAD detached at refs/heads/fix/40-x)
# 둘 다 브랜치 이름을 품어 아래 판별식에 걸리고, 그러면 없는 브랜치가 잔재로 보고돼 제거 절차까지 흘러간다.
# for-each-ref 는 ref 만 내므로 그런 줄이 없다.
# %(refname:short) 를 쓰지 않는다 — 같은 이름의 태그가 있으면 git 이 구분하려고 heads/ 를 붙여
# "heads/fix/5-e" 로 내고(실측), 그 이름으로는 for-each-ref·find.sh·ls-remote 가 전부 빈손이라
# 아무것도 못 지운 채 RESIDUE 만 반복된다. 전체 ref 이름을 받아 접두어를 직접 뗀다.
branches=$(git for-each-ref --format='%(refname)' refs/heads refs/remotes/origin) ||
  die_env "git for-each-ref 실패"
matched=$(printf '%s\n' "$branches" | sed -e 's#^refs/heads/##' -e 's#^refs/remotes/origin/##' |
  LC_ALL=C grep -E "$re" | LC_ALL=C sort -u)
while IFS= read -r b; do
  [ -n "$b" ] || continue
  add_line branch "$b" branch_unsafe
  # 명령에 넣을 수 없는 이름(branch-escaped)도 잔재로 친다. 이 스킬이 만든 브랜치는 아니지만 이 이슈 번호와 맞으니
  # 팀원이 같은 이슈로 한 작업일 수 있다 — other-orphan 처럼 보고만 하고 넘어가면 묻지 않고 두 번째 브랜치와 PR 을
  # 만든다. 그 브랜치가 남아 있는 동안 매번 묻는 비용을 감수한다(사람이 정한 기준이다).
  verdict=RESIDUE
done <<EOF
$matched
EOF

# 인자와 같은 디렉터리(-ef)로 등록된 레코드가 있으면 참이고 그 번호를 REG_HIT 에 담는다. -ef 는 링크를 따라가므로
# 등록된 워크트리를 가리키는 링크도 여기서 잡힌다.
registered_dir() {
  local i
  for ((i = 0; i < WT_N; i++)); do
    if [ "$1" -ef "${WT_PATH[$i]}" ]; then
      REG_HIT=$i
      return 0
    fi
  done
  return 1
}

matches_issue() {
  case "$1" in *$'\n'*) return 1 ;; esac
  printf '%s\n' "$1" | LC_ALL=C grep -Eq "$re"
}

# 같은 등록을 worktree 줄로 이미 냈으면 참. 디렉터리 스캔(링크로도, 실제 디렉터리로도 닿을 수 있다)과
# 등록 목록 루프가 같은 등록을 두 번 내지 않게 한다. 바이트가 같으면 -ef 없이도 같은 것이고, 디렉터리가
# 없는 등록(prunable)은 -ef 가 늘 거짓이라 바이트 비교가 먼저다.
reported_worktree() {
  local k
  for ((k = 0; k < ${#kinds[@]}; k++)); do
    [ "${kinds[$k]}" = worktree ] || continue
    if [ "${values[$k]}" = "$1" ] || [ "${values[$k]}" -ef "$1" ]; then return 0; fi
  done
  return 1
}

# 등록 경로를 낸다 — 스캔이 잡은 표기가 아니라 등록된 바이트 그대로. 링크로 닿은 등록을 링크 경로로 내면
# 사람이 보는 화면이 실상과 다르고, 아래 등록 목록 루프가 -ef 로 "이미 냈다"고 보고 진짜 경로를 건너뛴다.
report_worktree() {
  reported_worktree "$1" && return 0
  add_line worktree "$1"
  verdict=RESIDUE
}

classify() {
  if registered_dir "$1"; then
    matches_issue "$2" || return 0
    # worktree 줄은 등록 자체가 이 이슈 이름일 때만 — 링크 이름만 보고 내면 링크가 가리키는 다른 이슈의
    # 워크트리(또는 본 체크아웃)가 이 이슈 잔재로 화면에 올라, 사람이 그 브랜치 이름으로 답하면 정리 절차가
    # 남의 워크트리·브랜치를 지운다.
    if [ "$REG_HIT" -ne 0 ] && matches_issue "${WT_PATH[$REG_HIT]##*/}"; then
      report_worktree "${WT_PATH[$REG_HIT]}"
    fi
    if [ -L "$1" ]; then
      add_line link "$1"
      add_line link-target "${WT_PATH[$REG_HIT]}"
      verdict=RESIDUE
    fi
  elif matches_issue "$2"; then
    add_line orphan "$1"
    verdict=RESIDUE
  else
    add_line other-orphan "$1"
  fi
}

container="$root/.claude/worktrees"
# 컨테이너 자리를 볼 수 없으면 멈춘다 — 없는 것으로 치면 CLEAN 이 나온다. 둘 다 없는 것은 정상이다.
for p in "$root/.claude" "$container"; do
  if { [ -e "$p" ] || [ -L "$p" ]; } && [ ! -d "$p" ]; then
    die_env "컨테이너 자리가 디렉터리가 아니다(끊긴 링크이거나 파일이다) — 사람이 직접 확인해야 한다: $p"
  fi
done
# .claude 를 열 수 없으면 .claude/worktrees 는 -e 도 거짓이라 위 검사에 안 걸린다.
if [ -d "$root/.claude" ] && [ ! -x "$root/.claude" ]; then
  die_env "끝까지 읽지 못했다 — 사람이 직접 확인해야 한다: $root/.claude"
fi
if [ -d "$container" ]; then
  # 컨테이너가 링크를 거치면 실제 경로로 바꿔 훑는다. macOS find 는 시작점 링크를 따라가지 않아 안을 못 보고,
  # 링크 경로로 내면 orphan-check.sh 가 레포 안으로 보아 제거 절차 4번이 레포 밖 폴더를 확인 없이 지운다.
  if [ -L "$root/.claude" ] || [ -L "$container" ]; then
    container=$(CDPATH='' cd -P "$container" && pwd -P) ||
      die_env "끝까지 읽지 못했다 — 사람이 직접 확인해야 한다: $root/.claude/worktrees"
  fi
  # find 가 실패하면(읽을 수 없는 디렉터리) 판정하지 않는다. 그대로 두면 목록이 비어 CLEAN 이 나오고, 2단계는
  # CLEAN 을 "이 이슈의 잔재가 없다"로 믿고 새 워크트리로 간다. /bin/bash(3.2)는 프로세스 치환의 종료 코드를
  # 받을 수 없어 파일로 받는다(orphan-check.sh 와 같은 방식).
  # -type l 도 받는다 — 디렉터리를 가리키는 심볼릭 링크는 -type d 에 안 걸려서, 그런 잔재가 있으면
  # "이 이슈 것은 없다"(CLEAN)로 끝나 버린다. 아래 -ef 판정은 링크를 따라가므로 분류는 그대로다.
  find "$container" -mindepth 1 -maxdepth 1 \( -type d -o -type l \) -print0 > "$scan" ||
    die_env "끝까지 읽지 못했다 — 사람이 직접 확인해야 한다: $container"
  while IFS= read -r -d '' d; do
    name=${d##*/}
    if ! registered_dir "$d"; then
      case "$name" in
        feat | fix | refactor | docs | chore)
          # 옛 타입 폴더가 링크면 따라가지 않고 아래 classify 로 그 링크만 보고한다 — 링크 너머는 레포 밖일 수
          # 있어 그 안을 고아로 내면 확인 없이 지워진다. 안의 잔재는 놓친다(알려진 한계).
          if [ ! -L "$d" ]; then
            # 바깥 스캔처럼 링크도 받는다 — -type d 만 보면 링크로 남은 옛 잔재(fix/11-old)를 놓쳐 CLEAN 이 된다.
            find "$d" -mindepth 1 -maxdepth 1 \( -type d -o -type l \) -print0 > "$subs" ||
              die_env "끝까지 읽지 못했다 — 사람이 직접 확인해야 한다: $d"
            nested=0
            while IFS= read -r -d '' sub; do
              nested=1
              classify "$sub" "$name/${sub##*/}"
            done < "$subs"
            [ "$nested" = 1 ] && continue
          fi
          ;;
      esac
    fi
    classify "$d" "$name"
  done < "$scan"
fi

# 디렉터리 스캔이 이미 낸 워크트리는 다시 내지 않는다(report_worktree 가 가린다). 디렉터리가 없는 등록
# (등록만 남음)은 스캔이 낼 수 없었으므로 여기서 처음 나온다.
for ((i = 1; i < WT_N; i++)); do
  p=${WT_PATH[$i]}
  matches_issue "${p##*/}" || continue
  report_worktree "$p"
done

echo "$verdict"
for ((k = 0; k < ${#kinds[@]}; k++)); do
  print_checked_line "${checks[$k]}" "${kinds[$k]}" "${values[$k]}"
done
exit 0
