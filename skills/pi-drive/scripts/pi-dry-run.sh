#!/usr/bin/env bash
# One fresh, read-only pi run for a dry-run rehearsal, invention audit or scenario walk.
# Read-only is enforced, not asked for: the run gets no write, edit or bash tool.
# Run it in the background from Claude Code; the exit is the wake-up. The findings are the
# assistant's final text, written to <out.md>; the event stream goes to <out.md>.jsonl.
#
#   pi-dry-run.sh <workdir> <prompt-file> <out.md> [model[:thinking]] [extra-tools]
#
# Default model is the driver's model (gpt-6-sol since 2026-09-30) at high effort: the rehearsal simulates the executor, and
# sol's factual error rate roughly halves from low to high (model cards, 2026-09-29).
# extra-tools: "bash" when the walk must check git refs or installed tools. With bash the
# run can mutate, so the prompt must then say "mutate nothing".
set -euo pipefail
WORKDIR=$1; PROMPT=$2; OUT=$3; MODEL=${4:-openai-codex/gpt-6-sol:high}; EXTRA=${5:-}
[ -f "$PROMPT" ] || { echo "prompt file not found: $PROMPT" >&2; exit 2; }
PROMPT_ABS="$(cd "$(dirname "$PROMPT")" && pwd)/$(basename "$PROMPT")"
mkdir -p "$(dirname "$OUT")"
OUT_ABS="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
TOOLS="read,grep,find,ls${EXTRA:+,$EXTRA}"
cd "$WORKDIR"
pi --approve --mode json --no-session --model "$MODEL" --tools "$TOOLS" -- "@$PROMPT_ABS" \
  < /dev/null > "$OUT_ABS.jsonl" 2> "$OUT_ABS.err"
python3 - "$OUT_ABS.jsonl" "$OUT_ABS" <<'PY'
import json, sys
last, cost, model = None, 0.0, None
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    try: e = json.loads(line)
    except Exception: continue
    if e.get("type") == "message_end" and e.get("message", {}).get("role") == "assistant":
        last = e["message"]
        cost += ((last.get("usage") or {}).get("cost") or {}).get("total", 0) or 0
        model = last.get("model") or model
text = "".join(p["text"] for p in (last or {}).get("content", []) if p.get("type") == "text")
open(sys.argv[2], "w", encoding="utf-8").write(text)
print(f"model={model} cost_usd={cost:.4f} chars={len(text)} out={sys.argv[2]}")
if not text: sys.exit(1)
PY
