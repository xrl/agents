#!/usr/bin/env bash
# The `codex` lane (DESIGN M4, A7): a Codex Cloud job dispatched through codex_cloud.py. Its
# patches become commits on the step's branch and a draft PR; no build runs on the Mac. Fixes go
# back to the same job with `jobs continue`. A fresh sol verifier reads every head.
#
#   lane-codex.sh <step-dir> <worktree> [--resume]
#
# The Codex environment per repository comes from $CODEX_ENVS (default
# ~/.config/campaign/codex-envs), lines of `<owner/repo> <environment-config-id>`: owner pre-flight.
# Exit codes as pi-lane.sh; 20 also covers an unknown job-creation outcome, which is never retried.
set -euo pipefail
. "$(dirname "$0")/lane-lib.sh"
lane_setup "$1"
WT=$(cd "$2" && pwd -P)
DEADLINE=$(( $(date +%s) + 100 * 60 ))
cc() { uv run "$CODEX_CLOUD" "$@"; }
[ -n "$(st_get base)" ] || { st_set base "$(git -C "$WT" rev-parse HEAD)"; st_set branch "$(git -C "$WT" branch --show-current)"; st_set applied 0; }
BASE=$(st_get base); BRANCH=$(st_get branch)
REPO=$(cd "$WT" && gh repo view --json nameWithOwner -q .nameWithOwner)
bump() { local n=$(( $(st_get "$1") + 1 )); st_set "$1" "$n"; [ "$n" -le "$2" ] || exit 40; }

send() { # <name> <text>: create the job, or continue it; the outcome of a sent write is never guessed
  local f="$SR/prompts/codex-$1.txt" thread; thread=$(st_get thread)
  printf '%s\n' "$2" >"$f"
  if [ -z "$thread" ]; then
    local env; env=$(awk -v r="$REPO" '$1 == r { print $2 }' "${CODEX_ENVS:-$HOME/.config/campaign/codex-envs}")
    [ -n "$env" ] || exit 30
    cc jobs create --environment-id "$env" --prompt-file "$f" --title "$SLUG" --write >"$SR/codex-create.json" ||
      handback "Codex job creation for $STEP ended with an unknown outcome; inspect $SR/codex-create.json before any retry."
    thread=$(jq -r '.thread_id // .receipt.thread_id // empty' "$SR/codex-create.json")
    [ -n "$thread" ] || handback "Codex job creation for $STEP returned no thread id; see $SR/codex-create.json."
    st_set thread "$thread"
  else
    cc jobs continue "$thread" --prompt-file "$f" --write >"$SR/codex-continue.json" ||
      handback "Codex continue on $thread ended with an unknown outcome; inspect it before any retry."
  fi
  st_set phase wait
}

apply_new() { # apply the job's not-yet-applied file changes, oldest first, as one new commit
  cc jobs diff "$(st_get thread)" --full >"$SR/codex-diff.json"
  local total applied i; total=$(jq '.changes | length' "$SR/codex-diff.json"); applied=$(st_get applied)
  [ "$total" -gt "$applied" ] || return 1
  for (( i = total - applied - 1; i >= 0; i-- )); do   # the list is newest first
    jq -r --argjson i "$i" '.changes[$i].diff' "$SR/codex-diff.json" >"$SR/codex-change.diff"
    git -C "$WT" apply --3way --whitespace=nowarn "$SR/codex-change.diff" ||
      handback "A Codex patch for $(jq -r --argjson i "$i" '.changes[$i].path' "$SR/codex-diff.json") does not apply on $BRANCH."
  done
  local msg="$WT/.codex-commit-msg"
  git -C "$WT" add -A
  if [ -f "$msg" ]; then git -C "$WT" rm -q --cached .codex-commit-msg; git -C "$WT" commit -q -F "$msg"; rm -f "$msg"
  else git -C "$WT" commit -q -m "$STEP: Codex Cloud build (job $(st_get thread))"; fi
  st_set applied "$total"
}

DECISION=$(newest_decision "$SR/decision.used") || true
if [ -z "$(st_get thread)" ]; then
  send kickoff "$(steering_line)
You build campaign step $STEP in $REPO from base $BASE. The brief follows verbatim; every row it cites is settled. Implement it, run the gate commands it lists, and commit nothing: this lane turns your file changes into a commit on its own branch. Write the commit message, Changelog: trailers included, to .codex-commit-msg at the repository root. If the brief cannot be met, stop and say exactly why.

$(cat "$STEP_DIR/step.md")"
elif [ -n "$DECISION" ]; then
  touch "$SR/decision.used"; st_set fix_rounds 0; st_set ci_rounds 0
  send decision "The coordinator's decision, verbatim (your authority for what it says):

$(cat "$DECISION")

Make the change, rerun the gates, and update .codex-commit-msg for this commit."
fi

while :; do
  case $(st_get phase) in
    wait)
      left=$(( DEADLINE - $(date +%s) )); [ "$left" -gt 60 ] || exit 30
      rc=0; cc jobs wait "$(st_get thread)" --deadline "$left" --interval 30 >"$SR/codex-wait.json" || rc=$?
      case $rc in 0) ;; 2) exit 30 ;; *) handback "Codex job $(st_get thread) failed or was interrupted; see $SR/codex-wait.json." ;; esac
      apply_new || handback "Codex job $(st_get thread) finished with no new file changes."
      st_set phase verify ;;
    verify)
      HEAD=$(git -C "$WT" rev-parse HEAD); V=$(verify_head "$WT" "$BASE" "$HEAD")
      case $(verdict_of "$V") in
        ACCEPT) st_set phase push ;;
        "FIX REQUIRED") bump fix_rounds 2; send fix "A reviewer found these defects. Fix each one; the earlier changes stay:

$(cat "$V")" ;;
        *) exit 30 ;;
      esac ;;
    push)
      git -C "$WT" push -q -u origin "HEAD:$BRANCH"
      if [ -z "$(st_get pr)" ]; then
        st_set pr "$(cd "$WT" && gh pr create -R "$REPO" --draft --head "$BRANCH" --title "$(git -C "$WT" log --reverse --format=%s "$BASE..HEAD" | head -1)" --body "Campaign step $STEP, built by Codex Cloud job $(st_get thread).")"
      fi
      st_set phase ci ;;
    ci)
      HEAD=$(git -C "$WT" rev-parse HEAD); PR=$(st_get pr); rc=0
      ci_wait "$PR" "$HEAD" "$DEADLINE" || rc=$?
      case $rc in
        0) result_pr "$PR" "$HEAD"; st_set phase finished; exit 0 ;;
        1) bump ci_rounds 1; send ci "CI is red on the pushed commit. Failed checks: $(ci_failures "$PR"). Fix the cause." ;;
        2) exit 30 ;;
        *) st_set phase verify ;;
      esac ;;
    finished) result_pr "$(st_get pr)" "$(git -C "$WT" rev-parse HEAD)"; exit 0 ;;
    *) exit 30 ;;
  esac
done
