#!/usr/bin/env bash
# Walk back N assistant prose messages in a pi JSON event log, newest last. Each entry shows the
# tool calls the driver issued since its previous prose (name + a short arg summary), then the
# prose with fenced code collapsed to "[code: N lines]" and capped per message. Never prints tool
# output or thinking. The log is read once; pick a larger N or cap to see more.
#   pi-tail.sh <events.jsonl> [N=3] [chars-per-message=700] [--code]   (--code keeps fences)
set -euo pipefail
LOG=$1; N=${2:-3}; CAP=${3:-700}; KEEP=${4:-}
python3 - "$LOG" "$N" "$CAP" "$KEEP" <<'PY'
import json, sys, re
log, n, cap, keep = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4] == "--code"
entries = []            # [{tools:[...], text:str}]
pending = []            # tool calls since the last prose message
settled = False
def arg_summary(a):
    if not isinstance(a, dict): return ""
    for k in ("command", "path", "action", "task", "message", "pattern", "query"):
        if k in a:
            v = str(a[k]).replace("\n", " ")
            return f"{k}={v[:70]}"
    return json.dumps(a)[:70]
for line in open(log, encoding="utf-8", errors="replace"):
    try: e = json.loads(line)
    except Exception: continue
    t = e.get("type")
    settled = (t == "agent_settled")
    if t != "message_end" or e.get("message", {}).get("role") != "assistant": continue
    text, calls = [], []
    for p in e["message"].get("content", []):
        if p.get("type") == "text" and p.get("text", "").strip(): text.append(p["text"])
        if p.get("type") == "toolCall": calls.append(f'{p.get("name")}({arg_summary(p.get("arguments") or p.get("args"))})')
    pending += calls
    if text:
        entries.append({"tools": pending, "text": "\n".join(text)}); pending = []
if pending: entries.append({"tools": pending, "text": "(no prose after these calls)"})
print(f"settled: {settled} | prose messages: {len(entries)} | showing last {min(n,len(entries))}")
for i, ent in enumerate(entries[-n:], start=max(0, len(entries)-n)):
    print(f"\n=== [{i}] tools since previous prose: {len(ent['tools'])}")
    for c in ent["tools"]: print("   -", c)
    body = ent["text"]
    if not keep:
        body = re.sub(r"```.*?```", lambda m: f"[code: {m.group(0).count(chr(10))} lines]", body, flags=re.S)
    if len(body) > cap: body = body[:cap//2] + f"\n   … [{len(body)-cap} chars elided] …\n" + body[-cap//2:]
    print(body)
PY
