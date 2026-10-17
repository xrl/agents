# Shared helpers for campaign-tick.sh and the lane scripts. Source it; it sets no shell options.
# shellcheck shell=bash disable=SC2034  # the variables are for the scripts that source this

RUNNER=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
AGENTS_DIR=$(cd "$RUNNER/../../.." && pwd -P)
PI_SCRIPTS=$AGENTS_DIR/skills/pi-drive/scripts
CODEX_CLOUD=$AGENTS_DIR/skills/codex-cloud/scripts/codex_cloud.py
CODE=${CAMPAIGN_CODE:-$HOME/code/dekopon}   # repository clones live at $CODE/<name>, worktrees at $CODE/<name>.wt/<slug>

now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { printf '%s %s\n' "$(now)" "$*" >&2; }

# toml_get <table> <key>: the raw value of a flat `key = value` line in [table], read from stdin.
# Enough for the [authority], [required_checks] and [train.<unit>] tables: one value per line.
toml_get() {
  awk -v want="[$1]" -v key="$2" '
    function trim(s) { gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
    /^[ \t]*\[/ { t = trim($0); sub(/[ \t]*#.*$/, "", t); in_t = (t == want); next }
    in_t && index($0, "=") {
      k = trim(substr($0, 1, index($0, "=") - 1)); gsub(/"/, "", k)
      if (k != key) next
      v = trim(substr($0, index($0, "=") + 1)); sub(/[ \t]+#[^"]*$/, "", v); print v; exit
    }'
}
toml_str() { toml_get "$@" | sed -E 's/^"(.*)"$/\1/'; }      # a quoted string, unquoted
toml_list() { grep -o '"[^"]*"' | tr -d '"'; }               # an array of strings, one per line
# fenced_toml <heading>: the ```toml blocks under "## <heading>" of the markdown on stdin.
fenced_toml() {
  awk -v h="## $1" '/^## / { in_s = (index($0, h) == 1) } in_s && /^```toml/ { f = 1; next } f && /^```/ { f = 0; next } f'
}

# --- lane state; every lane keeps its files under the step's gitignored run/ (DESIGN S3d) ---

# lane_setup <step-dir>: sets STEP_DIR, SR, STATE, EPOCH, STEP, SLUG and records the exit code
# in run/exit, which is how the tick learns the lane ended.
lane_setup() {
  STEP_DIR=$(cd "$1" && pwd -P); SR=$STEP_DIR/run; STATE=$SR/lane-state.json
  EPOCH=${CAMPAIGN_EPOCH:?campaign-tick.sh exports CAMPAIGN_EPOCH}
  STEP=${STEP_DIR#"$EPOCH"/}; SLUG=${STEP//\//-}
  mkdir -p "$SR/prompts"; [ -f "$STATE" ] || echo '{}' >"$STATE"
  trap 'echo $? >"$SR/exit"' EXIT
}
st_get() { jq -r --arg k "$1" '.[$k] // empty' "$STATE"; }
st_set() { local t; t=$(mktemp "$SR/.state.XXXXXX"); jq --arg k "$1" --arg v "$2" '.[$k] = $v' "$STATE" >"$t" && mv "$t" "$STATE"; }
result_pr() { jq -n --arg pr "$1" --arg head "$2" '{pr: $pr, head: $head}' >"$SR/result.json"; }
handback() { printf '%s\n' "$*" >"$SR/handback.md"; exit 20; }

# limit <key>: a LIMITS.toml dial (models), read live; trust inputs never come from here.
limit() { awk -F= -v k="$1" '$1 ~ "^[ \t]*" k "[ \t]*$" { v = $2; gsub(/^[ \t"]+|[ \t"]+$/, "", v); print v; exit }' "$EPOCH/LIMITS.toml"; }

# log_cost <role> <claude -p JSON output>: one line in run/costs.jsonl (the spend scoreboard row).
log_cost() {
  jq -c --arg at "$(now)" --arg role "$1" --arg step "${STEP:-}" \
    '{at: $at, role: $role, step: $step, cost_usd: (.total_cost_usd // null), session_id: (.session_id // null), is_error: .is_error}' \
    "$2" >>"$EPOCH/run/costs.jsonl" 2>/dev/null || true
}

# The one line every GPT executor prompt carries (steering/GPT.md, read at a pinned SHA).
steering_line() {
  local sha=${STEERING_SHA:-$(git -C "$AGENTS_DIR" rev-parse HEAD)}
  echo "Before anything else, read \`git -C $AGENTS_DIR show $sha:steering/GPT.md\`, follow it, and quote its first line back at the top of your report."
}

# newest_decision <file>: the newest decision-N.md the coordinator wrote after <file>, if any.
newest_decision() {
  local d
  # shellcheck disable=SC2012  # decision-N.md names are ours
  d=$(ls -t "$STEP_DIR"/decision-*.md 2>/dev/null | head -1) || true
  [ -n "$d" ] && { [ ! -e "$1" ] || [ "$d" -nt "$1" ]; } && echo "$d"
}

# verify_head <worktree> <base> <head>: one fresh sol verifier over exactly base..head; prints the
# verify file. Its first line is `Reviewed: <head>` and its verdict line ACCEPT or FIX REQUIRED.
verify_head() {
  local wt=$1 base=$2 head=$3 p="$SR/prompts/verify-${3:0:12}.txt" out="$SR/verify-${3:0:12}.md"
  local nn=${STEP%%/*}
  cat >"$p" <<EOF
You did not write this change and owe it nothing. Review exactly \`git -C $wt diff $base $head\` (never against origin/main). The brief is $STEP_DIR/kickoff.md.
Every row of $EPOCH/EXECUTION.md §Rows and $EPOCH/$nn/DECISIONS.md is settled; a finding that contradicts one is not a finding; quote the row ID.
Read the worktree's AGENTS.md review sections, then the diff surface by surface from --stat; grep, never read a large file whole. Your bash is for git, grep, sed and reading logs only: never cargo, and mutate nothing.
Output: first line exactly \`Reviewed: $head\`. Then ranked findings, each tagged \`contract\`, \`guideline\` or \`taste\`, with file:line, the concrete failure and the exact fix. Tag every contract and guideline finding also \`[hard]\` (a type or trait change across crates, concurrency or ordering, cancellation or shutdown, a credential path) or \`[easy]\` (a test, an exhaustive match, a record field, wording, a deletion); when unsure, \`[hard]\`. Taste never blocks. End with ACCEPT or FIX REQUIRED on its own line.
EOF
  "$PI_SCRIPTS/pi-dry-run.sh" "$wt" "$p" "$out" "$(limit verifier_model):high" bash >&2
  echo "$out"
}
verdict_of() { grep -xE '(ACCEPT|FIX REQUIRED)[[:space:]]*' "$1" | tail -1 | sed -E 's/[[:space:]]+$//'; }

# ci_wait <pr-url> <head> <deadline-epoch-seconds>: 0 every check passed at head, 1 a check
# failed, 2 out of time, 3 the head moved.
ci_wait() {
  local b
  while :; do
    [ "$(gh pr view "$1" --json headRefOid -q .headRefOid)" = "$2" ] || return 3
    b=$(gh pr checks "$1" --json bucket -q '.[].bucket' 2>/dev/null) || true
    grep -qxE 'fail|cancel' <<<"$b" && return 1
    [ -n "$b" ] && ! grep -qvxE 'pass|skipping' <<<"$b" && return 0
    [ "$(date +%s)" -lt "$3" ] || return 2
    sleep 60
  done
}
ci_failures() { gh pr checks "$1" --json name,bucket,link -q '.[] | select(.bucket == "fail" or .bucket == "cancel") | "\(.name) \(.link)"' 2>/dev/null || true; }
