# /issue 판정 스크립트의 공용 함수. 실행하지 않고 source 한다.
#
# macOS 기본 bash 3.2 에서 돈다 — 연관 배열·${v,,}·mapfile 을 쓰지 않는다.
# set -u 도 쓰지 않는다: bash 3.2 는 빈 배열을 "${a[@]}" 로 펼치면 unbound 로 죽는다.
#
# 부르는 쪽은 `. "…/lib.sh" || exit 3` 으로 소스 실패를 막는다 — 이 파일을 못 읽었는데 그냥 이어 가면
# 함수가 전부 command not found 로 흘러 스크립트가 **판정 키워드를 내며 exit 0** 으로 끝난다(실측:
# find.sh 는 NONE, residue.sh 는 CLEAN, detached-check.sh 는 NO_BRANCH). 문서는 그 말을 믿고 rm -rf·
# branch -D·push --delete 로 내려간다.
#
# 그래서 부르는 쪽은 불러온 바로 다음 줄에서 이 파일의 함수가 다 있는지 declare -F 로 보고, 없으면 exit 3 으로
# 멈춘다 — 스크립트와 이 파일의 버전이 어긋나 함수 하나만 빠져도 같은 일이 생긴다(실측: print_path_line 이 없으면
# skill-repo.sh 가 path 줄 없는 FOUND 를, die_usage 가 없으면 same-repo.sh 가 OTHER_REPO 를 exit 0 으로 냈다).
# 그 확인은 모든 스크립트에 똑같이 두고 이 파일의 함수를 전부 적는다. 스크립트마다 쓰는 함수만 적으면 이
# 파일 안에서 불리는 함수(rev_parse 안의 die_env 등)나 이름으로 넘기는 함수(residue.sh 의 is_unsafe)를 빠뜨리기
# 쉽다. 함수를 더하거나 빼면 모든 스크립트의 그 확인을 함께 고친다 — tests/run.sh 가 확인이 다 같고 그 목록이 이
# 파일의 정의와 같은지 본다. 확인의 메시지는 die_env 를 쓰지 않는다 — 빠진 것이 die_env 일 수 있다.
# 불러오기 바로 앞 줄에서는 물려받은 함수를 모두 지운다 — 부른 셸이 export -f 한 같은 이름의 함수는 bash 가 스크립트
# 시작 때 들여오고, 이 파일을 불러도 지워지지 않아 위 확인이 그것을 이 파일의 함수로 센다(실측: print_path_line 이 없는
# 이 파일과 빈 print_path_line 을 export 한 셸에서 skill-repo.sh 가 path 줄 없는 FOUND 를 exit 0 으로 냈다 — 이전
# codex 리뷰). 그 자리에서 정의된 함수는 모두 물려받은 것이라 지워도 잃는 것이 없다. 이 줄도 모든 스크립트에 똑같다.
# 이름은 compgen 으로 받는다 — declare -F 는 export 된 함수를 "declare -fx 이름" 으로 내 잘라 내기가 어긋나고, 로케일
# 없는 sed 는 깨진 바이트가 든 이름에서 멈춘다. builtin 을 붙이는 것은 unset·compgen 이라는 이름의 함수를 물려받았어도
# 그것을 부르지 않게 하려는 것이다(declare 를 흉내 낸 함수도 이 줄이 먼저 지운다). 이름 앞의 -- 는 -x 처럼 - 로
# 시작하는 이름을 옵션으로 읽지 않게 한다 — 없으면 unset 이 옵션 오류로 하나도 지우지 않고 이어 갔다(실측).
# 그래도 지우지 못하면(readonly 함수 등) 이어 가지 않고 exit 3 으로 멈춘다. 이 줄과 확인이 막는 것은 버전이 어긋난
# 이 파일과, 셸이 우연히 export 해 둔 같은 이름의 함수다(이름이 - 로 시작해도). 부르는 환경이 일부러 속이는 것 —
# builtin 자체를 덮어쓴 함수, BASH_ENV 로 돌리는 코드 전반, BASHOPTS 의 failglob, 이름에 glob 문자가 든 함수 등 — 은
# 막지 않는다. BASH_ENV 가 readonly 로 심은 함수는 위대로 멈추지만 exit 까지 그렇게 덮으면 그것도 뚫린다. 그런 환경은
# 스크립트 파일도 바꿀 수 있어 이 장치로 막을 수 있는 것이 아니다.
#
# 모든 스크립트의 약속: 판정을 내렸으면 종료 코드 0 과 stdout 첫 줄 키워드.
# 판정을 못 내렸으면 아래 코드와 stderr 메시지. 판정 결과를 비0 종료로 알리지 않는다 —
# "정상인데 종료 코드가 1" 이 실패에 민감한 실행을 멈춰 세운 적이 있다(grep no-match).
#
# git 은 전부 cwd 에서 부른다. 레포 경로를 인자로 받아 -C 로 돌리지 않는다 — 뒤따르는
# 비가역 명령(worktree remove·branch -D)은 모델이 cwd 에서 치므로, 판정만 다른 곳을 보면
# 판정과 실행이 서로 다른 레포를 보게 된다. (skill-repo.sh 는 예외 — 그 머리말과 SKILL.md "스크립트를
# 부르는 법"에 이유가 있다.)

# 종료 코드는 숫자로 바로 쓴다(뜻은 SKILL.md "스크립트를 부르는 법") — 변수로 두었더니 버전이 어긋난 이 파일에 정의가
# 빠지면 exit "" 로 255 가, 거기에 셸이 EXIT_ENV=0 을 넘기면 0 이, bash -u 로 부르면 unbound 로 1 이 났다(실측).
die_usage() { echo "사용법: $*" >&2; exit 2; }
die_env() { echo "실패: $*" >&2; exit 3; }

# git 이 "레포가 아니다"로 실패한 것과 그 밖의 실패를 가르는 판정 스크립트가 쓴다. 레포 밖만 판정 키워드로 내고,
# 그 밖의 실패는 환경 실패로 멈춘다 — 지워진 등록을 가리키는 .git 파일이나 소유권 문제(safe.directory)까지 레포
# 밖으로 읽으면 깨진 자리를 "레포 밖"이라고 보고한다. 그런 스크립트는 아래 rev_parse 로 git 을 부른다 —
# 다시 부르는 인자와 오류 문구가 한 곳에서 같아야 해서다(스크립트마다 따로 적었더니 다시 부르는 인자가 서로 달라져
# 원인이 stderr 에서 사라졌다).
#
# git rev-parse <인자…> 를 cwd 에서 부른다. 성공하면 stdout 을 REV_OUT 에 담고 0, git 이 "레포가 아니다"로 실패하면 1.
# 그 밖의 실패는 die_env 로 멈춘다(stderr 는 "실패: git 오류(레포 밖이 아니다): <git 오류 한 줄>").
# 0·1 만 돌려주므로 부르는 쪽은 `if ! rev_parse` 로 받는다 — 이 함수나 이 함수가 부르는 함수가 없는 경우는 불러온
# 직후의 확인이 막는다(머리말. 그 확인을 두기 전에는 부르는 쪽마다 반환값을 0·1·그 밖으로 갈랐다). `$(...)` 안에서
# 부르면 die_env 가 그 서브셸만 끝내고 REV_OUT 도 바깥에 남지 않는다 — 서브셸이 꼭 필요하면(skill-repo.sh) 서브셸의
# 종료 코드를 받아 바깥에서 가른다.
# stdout 과 stderr 를 따로 받으려고 실패했을 때만 같은 인자로 한 번 더 부른다 — 임시 파일에 받으면 임시 디렉터리에
# 못 쓰는 환경에서 판정 전에 멈추고, 그 멈춤이 "git 이 깨졌다"로 읽힌다. 그 사이 상태가 바뀌어 두 번째가 성공하면
# 오류 문구가 비어 "레포가 아니다"로 읽히지 않으니 멈추는 쪽으로 간다. 두 번째가 "레포가 아니다"로 실패하면 그것을
# 따른다 — 그 사이 .git 이 사라진 것이니 지금은 레포 밖이 맞다. 오류 문구는 LC_ALL=C 로 고정한다.
rev_parse() {
  local err
  if REV_OUT=$(git rev-parse "$@" 2>/dev/null); then
    return 0
  fi
  err=$(LC_ALL=C git rev-parse "$@" 2>&1 >/dev/null)
  if git_err_not_repo "$err"; then
    return 1
  fi
  die_env "git 오류(레포 밖이 아니다): $(git_err_line "$err")"
}

# git 이 "레포가 아니다"로 실패했으면 참 — <git stderr> 는 LC_ALL=C 로 부른 git 의 것이다. 레포 밖은
# "not a git repository (or any of the parent directories)"(파일 시스템 경계에서 멈췄으면 "(or any parent up to
# mount point …)")로 실패하고, 지워진 등록을 가리키는 .git 파일은 "not a git repository: <경로>"로 실패하므로(git
# 2.54.0 실측 — 경로 자리가 "(null)" 이기도 하다) 괄호까지 본다. git 이 레포로 보지 않는 .git(빈 디렉터리 등)은 git
# 이 그 위로 올라가 같은 문구로 끝나므로 문구로는 가를 수 없다 — 그 자리는 레포 밖으로 읽힌다.
git_err_not_repo() {
  case "$1" in *'not a git repository (or any'*) return 0 ;; esac
  return 1
}
# die_env 의 한 줄에 넣을 git 오류. fatal: 줄을 고르는 것은 소유권 오류처럼 fatal: 뒤에 여러 줄 안내가 붙어서다.
# 비었으면(두 번째 호출이 성공했다) 그 사실을 적는다 — 빈 채로 두면 원인이 지워진 줄 모른다.
git_err_line() {
  local l
  l=$(printf '%s\n' "$1" | LC_ALL=C grep -m1 '^fatal:') || l=${1%%$'\n'*}
  [ -n "$l" ] || l="(두 번째로 불렀을 때는 오류가 없었다)"
  printf '%s' "$l"
}

lower_ascii() { printf '%s' "$1" | LC_ALL=C tr 'A-Z' 'a-z'; }

# 경로 비교용 정규형: NFC + ASCII 소문자. 이 볼륨은 정규화·대소문자에 무관하고
# (core.precomposeunicode·core.ignorecase), 모델이 옮겨 치는 경로는 NFC 라서 등록된 바이트
# 그대로는 비교할 수 없다. iconv 가 못 읽는 바이트(깨진 UTF-8)면 원래 바이트로 비교한다.
norm() {
  local r
  if r=$(printf '%s' "$1" | iconv -f UTF-8-MAC -t UTF-8 2>/dev/null); then
    lower_ascii "$r"
  else
    lower_ascii "$1"
  fi
}

# 문서가 경로를 넣는 명령 모양에서 셸이 건드리는 문자가 있으면 참 — 큰따옴표 안에서 먼저 확장되는
# $ 백틱 " \, osascript -e '…' 의 작은따옴표를 닫아 버리는 ', 줄 단위 출력을 깨는 개행·제어 문자.
is_unsafe() {
  case "$1" in *$'\n'*) return 0 ;; esac
  printf '%s' "$1" | LC_ALL=C grep -q "[\$\`\"\\\\'[:cntrl:]]"
}

# 브랜치 이름을 명령에 넣을 수 없으면 참 — 영숫자와 . _ / + - 밖의 문자가 있거나 - 로 시작한다. 경로(is_unsafe)보다
# 기준이 좁다 — 경로는 큰따옴표로 감싸 치니 한글·공백·; 가 있어도 되지만, 브랜치 이름은 문서 예시에서 따옴표 없이
# 옮겨지기 쉽고 git 은 ; | & ( ) < > 같은 셸 문자와 한글을 이름에 허용한다(git check-ref-format --branch 실측).
# - 로 시작하면 감싸도 옵션으로 읽힌다(git branch -D "-x" 가 unknown switch) — git branch 로는 못 만들지만 push 로
# 들어온 원격 브랜치는 그런 이름일 수 있다(실측). 이 스킬이 만드는 이름(<타입>/<번호>-<영어 슬러그>)은 늘
# 이 안에 들므로, 걸리는 것은 남이 만든 브랜치다.
# 글자를 범위(A-Z) 대신 하나씩 적는다 — case 의 범위는 로케일 정렬을 따른다. 한글은 UTF-8 로케일에선 한 글자,
# C 로케일에선 바이트들로 읽히는데 어느 쪽이든 이 목록 밖이다.
branch_unsafe() {
  case "$1" in
    *$'\n'* | -*) return 0 ;;
    *[!ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._/+-]*) return 0 ;;
  esac
  return 1
}

# 레코드의 branch 값(ref)을 명령에 넣을 수 없으면 참. refs/heads/ 밖의 ref 는 브랜치 이름으로 옮길 수 없으니 늘 참이고,
# - 시작 판정은 이름 자리에서 해야 한다 — ref 째로 보면 첫 글자가 늘 r 이라 refs/heads/-x 가 걸리지 않는다.
ref_unsafe() {
  case "$1" in
    refs/heads/*) branch_unsafe "${1#refs/heads/}" ;;
    *) return 0 ;;
  esac
}

# %q 표기를 C 로케일로 낸다. macOS /bin/bash 3.2 의 %q 는 UTF-8 로케일에서 한글의 첫 바이트를 날것으로 남겨 깨진
# 글자를 낸다 — 사람에게 넘기는 값이라 읽을 수 있어야 한다. C 로케일이면 전부 \ooo 로 나온다. LC_ALL=C printf 처럼
# 앞에 붙이는 꼴은 bash 3.2 에서 안 먹고, local 로 대입해야 먹는다(실측).
quote_c() {
  local LC_ALL=C
  printf '%q' "$1"
}

# <브랜치> 인자가 명령에 넣을 수 없는 이름이면 사용법 오류로 멈춘다 — branch-escaped 줄의 %q 표기를 옮겨 오면 없는
# 이름이라 판정이 "없다"(NONE·NO_BRANCH)로 나오고, 문서는 그 말을 믿고 재부착이나 원격 삭제 앞 확인을 지나간다.
require_safe_branch() {
  if branch_unsafe "$1"; then
    die_usage "명령에 넣을 수 없는 브랜치 이름이다 — 사람에게 넘긴다: $(quote_c "$1")"
  fi
}

# 레코드의 HEAD 를 못 읽으면 참 — 값이 비었거나 전부 0이다. 세 모양이 있다(git 2.50.1 실측):
#   HEAD 파일이 없다      → HEAD 0000… + detached
#   HEAD 가 0바이트다     → HEAD 0000… 만 (branch 도 detached 도 없다)
#   브랜치 ref 가 지워졌다 → HEAD 0000… + branch refs/heads/<이름> (매달린 심볼릭 HEAD)
# 마지막은 "등록만 남은 잔재"라 제거 절차가 치우는 정상 경로다 — wt_print 가 dangling 으로 따로 낸다.
head_unreadable() {
  local sha=${WT_HEAD[$1]}
  [ -n "$sha" ] || return 0
  case "$sha" in *[!0]*) return 1 ;; esac
  return 0
}

# 인쇄 가능한 ASCII 밖의 바이트가 있으면 참.
has_non_ascii() {
  case "$1" in *$'\n'*) return 0 ;; esac
  printf '%s' "$1" | LC_ALL=C grep -q '[^ -~]'
}

# cwd 에서 git worktree list --porcelain -z 를 파일로 뜬다. -z 라 경로에 개행이 있어도
# 레코드가 깨지지 않는다. git 이 죽어도 리다이렉트는 빈 파일을 만드므로 비었으면 실패로 친다.
wt_dump() {
  local out=$1 dir
  dir=$(dirname "$out")
  mkdir -p "$dir" || die_env "디렉터리를 만들 수 없다: $dir"
  git worktree list --porcelain -z > "$out" || die_env "git worktree list 실패"
  [ -s "$out" ] || die_env "git worktree list 가 아무것도 내지 않았다"
}

# -z 덤프를 레코드 단위 병렬 배열로 읽는다. 첫 레코드(0번)가 본 체크아웃이다.
#   WT_N                 레코드 수
#   WT_PATH[i]           등록된 경로 바이트 그대로
#   WT_NORM[i]           norm 한 경로
#   WT_LOWER[i]          ASCII 소문자만 한 경로 (git 의 접미사 비교와 같은 기준)
#   WT_HEAD[i]  WT_BRANCH[i](없으면 빈 값)  WT_DETACHED[i]  WT_BARE[i]
#   WT_LOCKED[i]  WT_LOCKED_REASON[i]  WT_PRUNABLE[i]  WT_PRUNABLE_REASON[i]
wt_load() {
  local f i=-1
  WT_PATH=(); WT_NORM=(); WT_LOWER=(); WT_HEAD=(); WT_BRANCH=(); WT_DETACHED=(); WT_BARE=()
  WT_LOCKED=(); WT_LOCKED_REASON=(); WT_PRUNABLE=(); WT_PRUNABLE_REASON=()
  while IFS= read -r -d '' f; do
    case "$f" in
      '') ;;
      'worktree '*)
        i=$((i + 1))
        WT_PATH[$i]=${f#worktree }
        WT_HEAD[$i]=''; WT_BRANCH[$i]=''; WT_DETACHED[$i]=0; WT_BARE[$i]=0
        WT_LOCKED[$i]=0; WT_LOCKED_REASON[$i]=''; WT_PRUNABLE[$i]=0; WT_PRUNABLE_REASON[$i]=''
        ;;
      *)
        [ "$i" -ge 0 ] || die_env "워크트리 목록 형식이 이상하다: 첫 worktree 줄 앞에 필드가 있다"
        case "$f" in
          'HEAD '*) WT_HEAD[$i]=${f#HEAD } ;;
          'branch '*) WT_BRANCH[$i]=${f#branch } ;;
          detached) WT_DETACHED[$i]=1 ;;
          bare) WT_BARE[$i]=1 ;;
          locked) WT_LOCKED[$i]=1 ;;
          'locked '*) WT_LOCKED[$i]=1; WT_LOCKED_REASON[$i]=${f#locked } ;;
          prunable) WT_PRUNABLE[$i]=1 ;;
          'prunable '*) WT_PRUNABLE[$i]=1; WT_PRUNABLE_REASON[$i]=${f#prunable } ;;
        esac
        ;;
    esac
  done < "$1"
  WT_N=$((i + 1))
  [ "$WT_N" -ge 1 ] || die_env "워크트리 레코드가 없다: $1"
  for ((i = 0; i < WT_N; i++)); do
    WT_NORM[$i]=$(norm "${WT_PATH[$i]}")
    WT_LOWER[$i]=$(lower_ascii "${WT_PATH[$i]}")
  done
}

# 인자 경로와 norm 이 같은 레코드 번호를 SAME_HITS 에 담는다. 끝의 / 는 뗀다.
same_path_hits() {
  local want=$1 i
  while [ "$want" != "/" ] && [ "${want%/}" != "$want" ]; do want=${want%/}; done
  want=$(norm "$want")
  SAME_HITS=()
  for ((i = 0; i < WT_N; i++)); do
    [ "${WT_NORM[$i]}" = "$want" ] && SAME_HITS+=("$i")
  done
  return 0
}

# 경로가 <레포 루트>/.claude/worktrees/ 아래면 참. 루트는 첫 레코드다.
# 심볼릭 링크 표기가 섞여 "밖" 으로 나오면 사람에게 묻는 쪽으로 틀리므로 안전하다.
path_in_container() {
  local p
  p=$(norm "$1")
  case "$p" in "${WT_NORM[0]}/.claude/worktrees/"?*) return 0 ;; esac
  return 1
}

# "<라벨> <값>" 한 줄. <판정 함수>가 참이면 "<라벨>-escaped <%q 표기>" 로 낸다. 경로 줄과 브랜치 줄은 판정 기준만
# 다르고 표기는 같아야 한다 — 문서는 라벨과 무관하게 -escaped 줄을 명령에 옮기지 않는다는 한 규칙으로 둘 다 막는다.
print_checked_line() {
  if "$1" "$3"; then
    printf '%s-escaped %s\n' "$2" "$(quote_c "$3")"
  else
    printf '%s %s\n' "$2" "$3"
  fi
}
print_path_line() { print_checked_line is_unsafe "$1" "$2"; }

# 레코드 i 를 블록으로 낸다. $2 = 어떻게 찾았는지 (없으면 match 줄을 안 낸다).
wt_print() {
  local i=$1 r
  echo "record $i"
  print_path_line path "${WT_PATH[$i]}"
  if is_unsafe "${WT_PATH[$i]}"; then echo "unsafe yes"; fi
  if [ -n "${WT_HEAD[$i]}" ]; then echo "head ${WT_HEAD[$i]}"; fi
  if [ "${WT_DETACHED[$i]}" = 1 ]; then
    echo "detached"
  elif [ -n "${WT_BRANCH[$i]}" ]; then
    print_checked_line ref_unsafe branch "${WT_BRANCH[$i]}"
  elif [ "${WT_BARE[$i]}" = 1 ]; then
    echo "bare"
  fi
  if [ "${WT_BARE[$i]}" != 1 ] && head_unreadable "$i"; then
    if [ -n "${WT_BRANCH[$i]}" ]; then echo "dangling yes"; else echo "unreadable yes"; fi
  fi
  if [ "${WT_LOCKED[$i]}" = 1 ]; then
    r=${WT_LOCKED_REASON[$i]}
    if [ -n "$r" ]; then echo "locked ${r//$'\n'/ }"; else echo "locked"; fi
  fi
  if [ "${WT_PRUNABLE[$i]}" = 1 ]; then
    r=${WT_PRUNABLE_REASON[$i]}
    if [ -n "$r" ]; then echo "prunable ${r//$'\n'/ }"; else echo "prunable"; fi
  fi
  if path_in_container "${WT_PATH[$i]}"; then echo "container in"; else echo "container out"; fi
  if [ -n "$2" ]; then echo "match $2"; fi
  return 0
}
