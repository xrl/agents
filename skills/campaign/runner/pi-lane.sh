#!/usr/bin/env bash
# The `pi` lane (DESIGN M4, A7): a sol driver turn, the gate-log check, a fresh sol verifier and
# pi-stage-check.sh, then routing by exit code. It replaces the sol supervisor. Resumable: every
# phase is recorded in run/lane-state.json, so a killed call picks up where it stopped.
#
#   pi-lane.sh <step-dir> <worktree> [--resume | --integrate <opus-fix-sha>]
#
# Exit: 0 PR open, checks green at the reviewed head (run/result.json) | 10 hard findings (the
# tick runs lane-opus-fix.sh) | 20 needs a decision (run/handback.md) | 30 environment or out of
# time (the tick resumes it) | 40 tripwire twice, failed re-check or 2 red CI rounds.
set -euo pipefail
. "$(dirname "$0")/lane-lib.sh"
lane_setup "$1"
WT=$(cd "$2" && pwd -P); MODE=${3:-}; FIX_SHA=${4:-}
DEADLINE=$(( $(date +%s) + 100 * 60 ))
DRIVER="$(limit driver_model):$(limit driver_effort)"
pi() { command pi -nc -ne "$@"; }; export -f pi

[ -n "$(st_get base)" ] || { st_set base "$(git -C "$WT" rev-parse HEAD)"; st_set branch "$(git -C "$WT" branch --show-current)"; st_set phase kickoff; }
BASE=$(st_get base); BRANCH=$(st_get branch)
REPO=$(cd "$WT" && gh repo view --json nameWithOwner -q .nameWithOwner)
FRAME="You are the pi driver for campaign step $STEP in worktree $WT (branch $BRANCH, base $BASE), the only writer of that worktree. Do not use pi's process tool, bg_wait or any managed background process. Decide under ambiguity and record it in your report; never end a turn with a question. A correction is a new commit on top, never an amend. Catch up with the base by rebasing, never by merging main."
GATE_RULE="Then run the gate commands in $STEP_DIR/kickoff.md (copied from CI), and append to $SR/gate.log a line \`HEAD=<git rev-parse HEAD>\` followed by \`GATE_EXIT=<the gate's exit status>\`. Leave the tree clean. Write your report to $SR/report.md and end the turn."

prompt() { # name, text → a prompt file for pi-turn.sh
  local f="$SR/prompts/$1.txt"; printf '%s\n\n%s\n' "$FRAME" "$2" >"$f"; echo "$f"
}
turn() { # one driver turn; dies with 30 on an environment failure
  local left=$(( DEADLINE - $(date +%s) ))
  [ "$left" -gt 60 ] || exit 30
  timeout "$left" "$PI_SCRIPTS/pi-turn.sh" "$WT" "$SLUG" "$DRIVER" "$SR/driver.jsonl" "$1" >"$SR/driver-last.txt" || exit 30
  [ "$SR/handback.md" -nt "$1" ] && exit 20
  return 0
}
gate_green() { # the last HEAD= line is the current head, GATE_EXIT=0 follows it, and the tree is clean
  local head; head=$(git -C "$WT" rev-parse HEAD)
  [ -z "$(git -C "$WT" status --porcelain)" ] &&
    [ "$(grep '^HEAD=' "$SR/gate.log" 2>/dev/null | tail -1)" = "HEAD=$head" ] &&
    [ "$(sed -n "/^HEAD=$head\$/,\$p" "$SR/gate.log" | grep '^GATE_EXIT=' | tail -1)" = GATE_EXIT=0 ]
}
bump() { local n=$(( $(st_get "$1" || echo 0) + 1 )); st_set "$1" "$n"; [ "$n" -le "$2" ] || exit 40; }

# The first prompt of this call.
DECISION=$(newest_decision "$SR/decision.used") || true
case $MODE in
  --integrate)
    P=$(prompt integrate "Opus fixed the [hard] findings of $(st_get findings) in commit $FIX_SHA. For each Opus fix, write a witness test and prove it: revert that fix locally, the test fails, restore it. Then fix the [easy] findings in the same file. Never edit the Opus lines except by \`cargo fmt --all\` output, taken verbatim; a witness that shows an Opus fix is wrong is a stop: write $SR/handback.md. Commit. $GATE_RULE")
    st_set phase driver ;;
  --resume)
    if [ -n "$DECISION" ]; then
      P=$(prompt decision "The coordinator's decision, verbatim from $DECISION (it is your authority for what it says):

$(cat "$DECISION")

$GATE_RULE"); touch "$SR/decision.used"
      for k in gate_fails fix_rounds ci_rounds; do st_set "$k" 0; done; st_set phase driver
    else
      P=$(prompt resume "Your previous turn was cut off. Read $SR/report.md if it exists and git log $BASE..HEAD, then finish the step. $GATE_RULE")
    fi ;;
  *)
    P=$(prompt kickoff "$(steering_line)
Your brief is $STEP_DIR/kickoff.md: its row, packages, witnesses and gates. Every row of $EPOCH/EXECUTION.md §Rows and of the unit's DECISIONS.md is settled. Read $AGENTS_DIR/RUST_AGENT_RULES.md and the worktree's AGENTS.md. Implement the step and commit, with the Changelog: trailers the repo uses. If it cannot be done without a decision outside the brief, write $SR/handback.md (the question, the options, your recommendation) and stop. $GATE_RULE") ;;
esac
[ "$(st_get phase)" = kickoff ] && st_set phase driver

while :; do
  case $(st_get phase) in
    driver) turn "$P"; st_set phase gate ;;
    gate)
      if gate_green; then st_set phase verify; else
        bump gate_fails 1
        P=$(prompt gate "The gate log $SR/gate.log does not end green at the current head with a clean tree. Fix what failed. $GATE_RULE"); st_set phase driver
      fi ;;
    verify)
      HEAD=$(git -C "$WT" rev-parse HEAD); V=$(verify_head "$WT" "$BASE" "$HEAD")
      case $(verdict_of "$V") in
        ACCEPT) # Step size is a planning rule, not a stop: the cap is off, the reviewed-head check stays.
          "$PI_SCRIPTS/pi-stage-check.sh" "$WT" "$BASE" "$SR" 1000000 >"$SR/stage-check.txt" || exit 40; st_set phase push ;;
        "FIX REQUIRED")
          st_set findings "$V"
          grep -qF '[hard]' "$V" && exit 10
          bump fix_rounds 2
          P=$(prompt fix "The verifier's findings in $V are all [easy]. Fix each one as a new commit on top. $GATE_RULE"); st_set phase driver ;;
        *) exit 30 ;;   # the verifier produced no verdict: a pi or network failure
      esac ;;
    push)
      git -C "$WT" push -q --force-with-lease -u origin "HEAD:$BRANCH"   # the lane's own branch (LAWS §56)
      PR=$(st_get pr)
      if [ -z "$PR" ]; then
        [ -s "$SR/report.md" ] || echo "Campaign step $STEP." >"$SR/report.md"
        PR=$(cd "$WT" && gh pr create -R "$REPO" --head "$BRANCH" --title "$(git -C "$WT" log --reverse --format=%s "$BASE..HEAD" | head -1)" --body-file "$SR/report.md")
        st_set pr "$PR"
      fi
      st_set phase ci ;;
    ci)
      HEAD=$(git -C "$WT" rev-parse HEAD); PR=$(st_get pr); rc=0
      ci_wait "$PR" "$HEAD" "$DEADLINE" || rc=$?
      case $rc in
        0) result_pr "$PR" "$HEAD"; st_set phase finished; exit 0 ;;
        1) bump ci_rounds 1
           P=$(prompt ci "CI is red on $PR at $HEAD. Failed checks: $(ci_failures "$PR"). Read the failed logs with \`gh run view --log-failed -R $REPO\`, fix the cause as a new commit. $GATE_RULE"); st_set phase driver ;;
        2) exit 30 ;;
        *) st_set phase verify ;;   # the head moved: review what is there now
      esac ;;
    finished) result_pr "$(st_get pr)" "$(git -C "$WT" rev-parse HEAD)"; exit 0 ;;
  esac
done
