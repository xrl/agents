#!/usr/bin/env bash
# `claude --cloud` refuses a non-interactive shell, so it runs under script(1) for a terminal, and
# --permission-mode precedes --cloud.
set -euo pipefail
. "$(dirname "$0")/lane-lib.sh"
lane_setup "$1"
WT=$(cd "$2" && pwd -P)
DEADLINE=$(( $(date +%s) + 100 * 60 ))
[ -n "$(st_get base)" ] || { st_set base "$(git -C "$WT" rev-parse HEAD)"; st_set branch "$(git -C "$WT" branch --show-current)"; }
BASE=$(st_get base); BRANCH=$(st_get branch)
REPO=$(cd "$WT" && gh repo view --json nameWithOwner -q .nameWithOwner)
bump() { local n=$(( $(st_get "$1") + 1 )); st_set "$1" "$n"; [ "$n" -le "$2" ] || exit 40; }

run_cloud() { # <name> <task text>: start one cloud session on the branch
  local f="$SR/prompts/cloud-$1.txt"
  cat >"$f" <<EOF
You build campaign step $STEP in $REPO on branch $BRANCH (base $BASE), which is already pushed. Push your commits to $BRANCH only, as new commits on top; never amend, force-push, merge, tag or release. If no pull request exists for $BRANCH, open one against the default branch. When the work is pushed and its gates pass locally, comment exactly READY on the pull request. If the task cannot be met, comment BLOCKED and the exact cause instead.

$2
EOF
  git -C "$WT" push -q -u origin "HEAD:$BRANCH"
  st_set launched "$(now)"; st_set phase wait
  local cmd; cmd=(claude --permission-mode auto --model "${OPUS_MODEL:-claude-opus-5-5}" --cloud "$(cat "$f")")
  if [ "$(uname)" = Darwin ]; then (cd "$WT" && timeout 300 script -q /dev/null "${cmd[@]}" </dev/null >"$SR/cloud-$1.log" 2>&1) || exit 30
  else (cd "$WT" && timeout 300 script -qec "$(printf '%q ' "${cmd[@]}")" /dev/null </dev/null >"$SR/cloud-$1.log" 2>&1) || exit 30; fi
}

DECISION=$(newest_decision "$SR/decision.used") || true
if [ -z "$(st_get phase)" ]; then
  run_cloud kickoff "The brief follows verbatim; every row of EXECUTION.md §Rows and the unit's DECISIONS.md it cites is settled.

$(cat "$STEP_DIR/kickoff.md")"
elif [ -n "$DECISION" ]; then
  touch "$SR/decision.used"; st_set fix_rounds 0; st_set ci_rounds 0
  run_cloud decision "The coordinator's decision, verbatim (your authority for what it says):

$(cat "$DECISION")"
fi

while :; do
  case $(st_get phase) in
    wait) # until the session comments READY or BLOCKED after this run started
      PR=$(gh pr list -R "$REPO" --head "$BRANCH" --state open --json url -q '.[0].url // empty')
      if [ -n "$PR" ]; then
        st_set pr "$PR"
        SAID=$(gh pr view "$PR" --json comments -q "[.comments[] | select(.createdAt > \"$(st_get launched)\") | .body | split(\"\n\")[0]] | last // empty")
        case $SAID in
          READY*) git -C "$WT" fetch -q origin "$BRANCH"; git -C "$WT" merge -q --ff-only "origin/$BRANCH"; st_set phase verify; continue ;;
          BLOCKED*) handback "The cloud session for $STEP is blocked: see $PR." ;;
        esac
      fi
      [ "$(date +%s)" -lt "$DEADLINE" ] || exit 30
      sleep 60 ;;
    verify)
      HEAD=$(git -C "$WT" rev-parse HEAD); V=$(verify_head "$WT" "$BASE" "$HEAD")
      case $(verdict_of "$V") in
        ACCEPT) st_set phase ci ;;
        "FIX REQUIRED") bump fix_rounds 2; run_cloud "fix-${HEAD:0:12}" "A reviewer found these defects at $HEAD. Fix each one on the branch:

$(cat "$V")" ;;
        *) exit 30 ;;
      esac ;;
    ci)
      HEAD=$(git -C "$WT" rev-parse HEAD); PR=$(st_get pr); rc=0
      ci_wait "$PR" "$HEAD" "$DEADLINE" || rc=$?
      case $rc in
        0) result_pr "$PR" "$HEAD"; st_set phase finished; exit 0 ;;
        1) bump ci_rounds 1; run_cloud "ci-${HEAD:0:12}" "CI is red on $PR at $HEAD. Failed checks: $(ci_failures "$PR"). Fix the cause." ;;
        2) exit 30 ;;
        *) git -C "$WT" fetch -q origin "$BRANCH"; git -C "$WT" merge -q --ff-only "origin/$BRANCH"; st_set phase verify ;;
      esac ;;
    finished) result_pr "$(st_get pr)" "$(git -C "$WT" rev-parse HEAD)"; exit 0 ;;
    *) exit 30 ;;
  esac
done
