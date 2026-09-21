#!/usr/bin/env bash
# One pi turn in print mode, appended to a persistent session. Run it in the background from
# Claude Code; the exit is the wake-up. Output: the assistant's final text on stdout, the full
# event stream in $LOG (JSON lines), so the driver can be read by tail, never by transcript.
#
#   pi-turn.sh <workdir> <session-id> <model[:thinking]> <log-file> <prompt-file-or-text>
set -euo pipefail
WORKDIR=$1; SESSION=$2; MODEL=$3; LOG=$4; PROMPT=$5
if [ -f "$PROMPT" ]; then MSG=$(cat "$PROMPT"); else MSG=$PROMPT; fi
cd "$WORKDIR"
# --approve trusts project-local .pi/ files (agents, settings) without a TUI prompt.
# --mode json streams every event; the last assistant text is extracted below.
pi --approve --mode json --session-id "$SESSION" --model "$MODEL" -- "$MSG" < /dev/null >> "$LOG" 2>>"$LOG.err"
# Final assistant text: the last message_end whose message.role is assistant.
python3 - "$LOG" <<'PY'
import json, sys
last = None
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    try: e = json.loads(line)
    except Exception: continue
    if e.get("type") == "message_end" and e.get("message", {}).get("role") == "assistant":
        last = e["message"]
if last:
    for part in last.get("content", []):
        if part.get("type") == "text": print(part["text"])
PY
