#!/usr/bin/env bash
# shellcheck disable=SC2016  # the sed program strips literal backticks
set -euo pipefail
. "$(dirname "$0")/lane-lib.sh"
MODEL=${FABLE_MODEL:-claude-fable-5-1}
TOOLS="Read Grep Glob Bash(git log:*) Bash(git show:*) Bash(git diff:*) Bash(gh pr view:*) Bash(gh pr diff:*)"
DENY=("Bash(git * --output*)" "Bash(*>*)")

read_only() { # <cwd> <prompt> <out.json>: one read-only Fable run; prints the reply text
  (cd "$1" && timeout 2700 claude -p --restricted --strict-mcp-config --tools Read,Grep,Glob,Bash --model "$MODEL" \
    --output-format json --permission-mode dontAsk --allowedTools "$TOOLS" --disallowedTools "${DENY[@]}" --add-dir "$EPOCH" \
    -- "$2" </dev/null >"$3") || { log_cost fable "$3"; exit 30; }
  log_cost fable "$3"
  jq -r '.result // empty' "$3"
}

if [ "${1:-}" != --pr ]; then
  lane_setup "$1"
  TEXT=$(read_only "${2:-$STEP_DIR}" "You are a fresh Fable reviewer for one read. Your task is $STEP_DIR/kickoff.md; follow it exactly. Every row of $EPOCH/EXECUTION.md §Rows and the unit's DECISIONS.md is settled; a finding that contradicts one is not a finding; quote the row ID. Return your findings as text in your final message." "$SR/fable.json")
  [ -n "$TEXT" ] || exit 30
  printf '%s\n' "$TEXT" >"$STEP_DIR/FABLE-READ.md"
  exit 0
fi

URL=$2; H=$3; EPOCH=${CAMPAIGN_EPOCH:?}; STEP_DIR=$(cd "$4" && pwd -P); STEP=${STEP_DIR#"$EPOCH"/}
REPO=$(sed -E 's#https://github.com/([^/]+/[^/]+)/pull/.*#\1#' <<<"$URL"); N=${URL##*/}
VERDICT=$EPOCH/run/verdicts/${REPO//\//_}-$N-$H
CLONE=$CODE/${REPO#*/}
BASE=$(gh pr view "$URL" --json baseRefOid -q .baseRefOid)
git -C "$CLONE" fetch -q origin "pull/$N/head" "$BASE"
[ "$(git -C "$CLONE" rev-parse FETCH_HEAD)" = "$H" ] || { log "head moved past $H; no verdict"; exit 0; }
TMP=$(mktemp -d "${TMPDIR:-/tmp}/fable-read.XXXXXX"); trap 'git -C "$CLONE" worktree remove --force "$TMP/wt" 2>/dev/null; rm -rf "$TMP"' EXIT
git -C "$CLONE" worktree add -q --detach "$TMP/wt" "$H"
NN=${STEP%%/*}
TEXT=$(read_only "$TMP/wt" "You are a fresh Fable reviewer doing one whole-PR read of $URL at exactly head $H, base $BASE. Read \`git diff $BASE...$H\` surface by surface from --stat, in this checkout of the head. The brief is $STEP_DIR/kickoff.md. Every row of $EPOCH/EXECUTION.md §Rows and $EPOCH/$NN/DECISIONS.md is settled; a finding that contradicts one is not a finding; quote the row ID. Changelog trailer wording or category is never blocking: note it for the squash message. Return your findings as text, ranked, each with file:line, the failure and the fix. The last line of your reply is exactly MERGE or FIX BEFORE MERGE." "$TMP/fable.json")
LAST=$(printf '%s\n' "$TEXT" | sed -E 's/[[:space:]*`]+$//; s/^[[:space:]*`]+//' | grep -v '^$' | tail -1) || true
case $LAST in MERGE) V=MERGE ;; "FIX BEFORE MERGE") V=FIX ;; *) log "no verdict line from Fable"; exit 30 ;; esac
printf '%s\n' "$TEXT" >"$STEP_DIR/FABLE-READ-${H:0:12}.md"
printf '%s\nhead %s\npr %s\nat %s\n' "$V" "$H" "$URL" "$(now)" >"$VERDICT.tmp" && mv "$VERDICT.tmp" "$VERDICT"
