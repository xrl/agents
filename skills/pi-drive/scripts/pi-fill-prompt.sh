#!/usr/bin/env bash
# Fill a stage-prompt template's placeholders from live state, so no hand-written sed.
#   pi-fill-prompt.sh <template> <out> <worktree> [prev-report] [pr-number] [KEY=VALUE ...]
# Fills: <sha> and <stage-X head> = worktree HEAD; <hash> = sha256 of prev-report;
# <url> = the PR's URL. Extra KEY=VALUE pairs replace <KEY>. Refuses to write if any of
# those placeholders is still present afterwards (other <…> text, e.g. `--persona <key>`, is left alone).
set -euo pipefail
TPL=$1; OUT=$2; WT=$3; REPORT=${4:-}; PR=${5:-}; shift $(( $# < 5 ? $# : 5 ))
SHA=$(git -C "$WT" rev-parse HEAD)
HASH=""; [ -n "$REPORT" ] && HASH=$(shasum -a 256 "$REPORT" | cut -d' ' -f1)
URL=""; [ -n "$PR" ] && URL=$(cd "$WT" && gh pr view "$PR" --json url -q .url)
python3 - "$TPL" "$OUT" "$SHA" "$HASH" "$URL" "$@" <<'PY'
import re, sys
tpl, out, sha, hsh, url, *pairs = sys.argv[1:]
s = open(tpl).read()
subs = {"<sha>": sha, "<hash>": hsh, "<url>": url}
for p in pairs:
    k, v = p.split("=", 1); subs[f"<{k}>"] = v
for k, v in subs.items():
    if v: s = s.replace(k, v)
s = re.sub(r"<stage-[A-Za-z0-9]+ head>", sha[:10], s)
left = [k for k in subs if k in s] + re.findall(r"<stage-[A-Za-z0-9]+ head>", s)
if left:
    sys.exit(f"unfilled placeholders: {sorted(set(left))}")
open(out, "w").write(s)
print(out)
PY
