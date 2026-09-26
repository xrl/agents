#!/usr/bin/env bash
# Read-only acceptance check for a driver stage: size against the ~1k cap, and whether the head
# the driver pushed (or will push) is the head its last verifier/reviewer saw.
#   pi-stage-check.sh <worktree> <stage-parent-sha> <execution-dir> [cap=1200]
# Reviewed SHA: the `Reviewed: <sha>` first line of the newest *verify*.md / *review*.md in the
# execution dir. Verdict line last: ok, or every reason not to accept.
set -euo pipefail
WT=$1; PARENT=$2; EXEC=$3; CAP=${4:-1200}
head=$(git -C "$WT" rev-parse HEAD)
read -r ins del < <(git -C "$WT" diff --shortstat "$PARENT" HEAD |
  awk '{i=0;d=0;for(n=1;n<=NF;n++){if($n~/^insertion/)i=$(n-1);if($n~/^deletion/)d=$(n-1)}print i,d}')
changed=$(( ${ins:-0} + ${del:-0} ))
echo "head=${head:0:12} parent=${PARENT:0:12} changed=$changed (+${ins:-0} -${del:-0}) cap=$CAP"

newest=$(ls -t "$EXEC"/*verify*.md "$EXEC"/*review*.md 2>/dev/null | head -1 || true)
reviewed=""
[ -n "$newest" ] && reviewed=$(head -1 "$newest" | sed -nE 's/^Reviewed: *([0-9a-f]{7,40}).*/\1/p')
echo "last_review=${newest:+$(basename "$newest")} reviewed=${reviewed:-unknown}"

problems=()
[ "$changed" -gt "$CAP" ] && problems+=("over cap: $changed > $CAP changed lines (split the stage)")
if [ -z "$reviewed" ]; then
  problems+=("no Reviewed: line in the newest review file")
elif ! full=$(git -C "$WT" rev-parse --verify -q "$reviewed^{commit}"); then
  problems+=("reviewed sha $reviewed not in this repo")
elif [ "$full" != "$head" ]; then
  if git -C "$WT" merge-base --is-ancestor "$full" HEAD; then
    problems+=("unreviewed commits since ${full:0:12}:")
    while read -r l; do problems+=("  $l"); done < <(git -C "$WT" log --oneline --shortstat "$full"..HEAD | paste -d' ' - - - | sed 's/  */ /g')
  else
    problems+=("head was rewritten after review (${full:0:12} is not an ancestor of HEAD)")
  fi
fi
if [ ${#problems[@]} -eq 0 ]; then echo "verdict=ok"; else printf 'verdict=NOT OK\n'; printf '  %s\n' "${problems[@]}"; fi
