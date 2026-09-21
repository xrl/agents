#!/usr/bin/env bash
# Last assistant text and a one-line tool tally from a pi JSON event log; never the transcript.
#   pi-last.sh <events.jsonl> [max-chars]
set -euo pipefail
python3 - "$1" "${2:-6000}" <<'PY'
import json, sys, collections
last = None; tools = collections.Counter(); settled = False
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    try: e = json.loads(line)
    except Exception: continue
    t = e.get("type")
    if t == "tool_execution_start": tools[e.get("toolName", "?")] += 1
    if t == "message_end" and e.get("message", {}).get("role") == "assistant": last = e["message"]
    settled = (t == "agent_settled")
print("settled:", settled, "| tools:", dict(tools))
if last:
    text = "\n".join(p.get("text", "") for p in last.get("content", []) if p.get("type") == "text")
    print(text[-int(sys.argv[2]):])
PY
