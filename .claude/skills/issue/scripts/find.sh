#!/bin/bash
# 브랜치(또는 경로)로 워크트리 레코드를 찾는다. 판정만 하고 아무것도 바꾸지 않는다.
#
# 사용: find.sh <스냅숏 파일> <브랜치> [<경로>]
#   cwd 의 git worktree list 를 <스냅숏 파일>에 새로 떠 두고(덮어쓴다) 그 목록으로 판정한다.
#   이 파일이 suffix.sh 의 입력이고 verify-removed.sh 의 기준선이다.
#   <경로>를 주면 그 경로의 레코드만 본다 — NFC/NFD·ASCII 대소문자·끝 / 차이는 같은 경로로 친다.
#
# 후보(<경로> 없이 불렀을 때, 본 체크아웃은 빼고)
#   name    경로 마지막 조각이 평탄화한 브랜치명(/ → +)과 같다
#   branch  branch 줄이 refs/heads/<브랜치> 다 (규약 밖 이름이 브랜치를 쥔 경우를 잡는다)
# <브랜치>는 바이트 그대로 비교한다 — git 출력에서 옮겨 쓴다. 이름·경로 비교만 NFC·ASCII 대소문자를
# 무시하므로, 대소문자만 다른 브랜치명으로 부르면 이름으로 잡힌 레코드가 MISMATCH 로 나온다(안전한 쪽).
# 후보가 하나여도 같은 디렉터리에 표기(NFC/NFD)만 다른 등록이 또 있으면 AMBIGUOUS 다 — 절대경로 remove 는
# 모델이 친 NFC 바이트와 같은 쪽을 지우므로, 고른 레코드가 아닌 쌍둥이가 지워질 수 있다.
#
# stdout 첫 줄
#   MAIN_HOLDS           본 체크아웃이 refs/heads/<브랜치> 를 쥐고 있다 (늘 먼저 본다)
#   FOUND                대상이 하나로 좁혀졌고, 그 레코드가 브랜치를 쥐고 있거나 detached 다
#   MISMATCH             대상이 하나인데 다른 브랜치를 쥐고 있다
#   AMBIGUOUS            대상 후보가 둘 이상이다 — 같은 디렉터리의 쌍둥이 등록이면 match same-dir 가 붙는다
#   DETACHED_CANDIDATES  <경로> 없이 불렀고 후보가 없는데, origin/main 에 없는 커밋에 선 detached 연결
#                        워크트리가 있다. origin/main 에 이미 있는 커밋에 선 것은 이 브랜치의 커밋 위가
#                        아니라서 뺀다. HEAD 를 못 읽거나 origin/main 이 없으면 남긴다(안전한 쪽)
#   NONE                 <경로> 없이 불렀고 후보도 위 detached 연결 워크트리도 없다
#   GONE                 <경로>로 불렀는데 그 경로의 레코드가 없다
#   MAIN                 <경로>가 본 체크아웃이다
# 그 뒤 해당 레코드마다 블록:
#   record <번호> / path <경로>(또는 path-escaped <표기> + unsafe yes) / head <sha> /
#   branch <ref>(명령에 넣을 수 없는 이름이면 branch-escaped <%q 표기> — lib.sh branch_unsafe) 또는 detached /
#   dangling yes(branch 줄은 있는데 HEAD 가 0 — ref 가 지워진 등록) /
#   unreadable yes(HEAD 를 못 읽는 깨진 등록 — 0바이트면 branch·detached 줄이 아예 없고, HEAD 파일이
#   없으면 detached 가 함께 붙는다) / locked [이유] /
#   prunable [이유] / container in|out /
#   match name|branch|name+branch|path|detached|detached-unresolved|same-dir
#     (detached-unresolved 는 HEAD 가 가리키는 커밋을 git 이 못 찾는다는 뜻이다)
#
# 종료 코드: 0 판정함 · 2 사용법(<브랜치>가 명령에 넣을 수 없는 이름일 때 포함) · 3 환경 실패(레포 밖 등, stderr)

builtin unset -f -- $(builtin compgen -A function) || { echo "실패: 부른 셸에서 물려받은 함수를 지우지 못했다(lib.sh 머리말)" >&2; exit 3; }
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh" || exit 3
declare -F die_usage die_env rev_parse git_err_not_repo git_err_line lower_ascii norm is_unsafe \
  branch_unsafe ref_unsafe quote_c require_safe_branch head_unreadable has_non_ascii wt_dump wt_load \
  same_path_hits path_in_container print_checked_line print_path_line wt_print >/dev/null ||
  { echo "실패: lib.sh 에 판정 스크립트가 쓰는 함수가 없다 — 이 스크립트와 lib.sh 의 버전이 어긋났다(lib.sh 머리말)" >&2; exit 3; }

if [ $# -ne 2 ] && [ $# -ne 3 ]; then
  die_usage "find.sh <스냅숏 파일> <브랜치> [<경로>]"
fi
snap=$1
branch=$2
[ -n "$snap" ] || die_usage "스냅숏 파일이 비었다"
[ -n "$branch" ] || die_usage "브랜치가 비었다"
require_safe_branch "$branch"
if [ $# -eq 3 ] && [ -z "$3" ]; then die_usage "경로가 비었다"; fi

wt_dump "$snap"
wt_load "$snap"
ref="refs/heads/$branch"

identity_ok() {
  [ "${WT_BRANCH[$1]}" = "$ref" ] || [ "${WT_DETACHED[$1]}" = 1 ]
}

if [ "${WT_BRANCH[0]}" = "$ref" ]; then
  echo MAIN_HOLDS
  wt_print 0 branch
  exit 0
fi

if [ $# -eq 3 ]; then
  same_path_hits "$3"
  case ${#SAME_HITS[@]} in
    0) echo GONE ;;
    1)
      i=${SAME_HITS[0]}
      if [ "$i" -eq 0 ]; then
        echo MAIN
      elif identity_ok "$i"; then
        echo FOUND
      else
        echo MISMATCH
      fi
      wt_print "$i" path
      ;;
    *)
      echo AMBIGUOUS
      for i in "${SAME_HITS[@]}"; do wt_print "$i" same-dir; done
      ;;
  esac
  exit 0
fi

have_origin_main=0
if git rev-parse --verify -q refs/remotes/origin/main >/dev/null; then have_origin_main=1; fi

# detached 레코드 i 를 후보로 남길지. origin/main 의 조상인 커밋에 섰으면 빼고, 못 가리면 남긴다.
# 남길 때 DET_MARK 에 match 표시를 담는다 — 커밋 자체를 못 찾으면(force-push 뒤 gc) detached-unresolved 다.
# 그 레코드는 정체를 가릴 수 없고 3번 remove 도 bad object HEAD 로 실패하므로, 블록에 표시가 있어야 한다.
detached_candidate() {
  local sha=${WT_HEAD[$1]} rc
  DET_MARK=detached
  [ "$have_origin_main" = 1 ] || return 0
  case "$sha" in
    '' | *[!0]*) ;;
    *) return 0 ;;
  esac
  [ -n "$sha" ] || return 0
  git merge-base --is-ancestor "$sha" refs/remotes/origin/main 2>/dev/null
  rc=$?
  case $rc in
    0) return 1 ;;
    1) return 0 ;;
    *)
      DET_MARK=detached-unresolved
      return 0
      ;;
  esac
}

flat=$(norm "${branch//\//+}")
cands=()
kinds=()
detached=()
det_marks=()
for ((i = 1; i < WT_N; i++)); do
  kind=
  if [ "${WT_NORM[$i]##*/}" = "$flat" ]; then kind=name; fi
  if [ "${WT_BRANCH[$i]}" = "$ref" ]; then
    if [ -n "$kind" ]; then kind=name+branch; else kind=branch; fi
  fi
  if [ -n "$kind" ]; then
    cands+=("$i")
    kinds+=("$kind")
  fi
  if [ "${WT_DETACHED[$i]}" = 1 ] && detached_candidate "$i"; then
    detached+=("$i")
    det_marks+=("$DET_MARK")
  fi
done

case ${#cands[@]} in
  0)
    if [ ${#detached[@]} -gt 0 ]; then
      echo DETACHED_CANDIDATES
      for ((k = 0; k < ${#detached[@]}; k++)); do wt_print "${detached[$k]}" "${det_marks[$k]}"; done
    else
      echo NONE
    fi
    ;;
  1)
    i=${cands[0]}
    same_path_hits "${WT_PATH[$i]}"
    if [ ${#SAME_HITS[@]} -ge 2 ]; then
      echo AMBIGUOUS
      for j in "${SAME_HITS[@]}"; do
        if [ "$j" = "$i" ]; then wt_print "$j" "${kinds[0]}"; else wt_print "$j" same-dir; fi
      done
      exit 0
    fi
    if identity_ok "$i"; then echo FOUND; else echo MISMATCH; fi
    wt_print "$i" "${kinds[0]}"
    ;;
  *)
    echo AMBIGUOUS
    for ((k = 0; k < ${#cands[@]}; k++)); do wt_print "${cands[$k]}" "${kinds[$k]}"; done
    ;;
esac
exit 0
