#!/usr/bin/env bash
# One-line health of a running pi print-mode turn, for an unattended watch loop.
#   pi-check.sh <events.jsonl> [worktree]
# alive: a process still has the log open (pi's argv shows only "pi", so pgrep -f cannot find it).
# log_age_min: minutes since the log last grew. builds: live cargo/rustc/kache compiles (the idle
# kache daemon excluded). containers: docker containers up. prose_msgs: assistant text messages.
# commit_age_min: minutes since the worktree's HEAD commit ("?" without the worktree argument).
# calls_since_edit: tool calls since the driver last edited or wrote a file.
# top_cmd: the most repeated bash command since the driver's last `git commit`, as count x text.
# A running build is not progress: read the last three beside builds.
set -euo pipefail
LOG=$1
WT=${2:-}
P=$(lsof -t "$LOG" 2>/dev/null | head -1 || true); alive=no; [ -n "$P" ] && alive=yes
now=$(date +%s); m=$(stat -f %m "$LOG" 2>/dev/null || stat -c %Y "$LOG"); age=$(( (now-m)/60 ))
lines=$(wc -l < "$LOG" | tr -d ' '); last=$(tail -1 "$LOG" | jq -r '.type' 2>/dev/null || echo '?')
builds=$(ps -Ao command | grep -E '^(/[^ ]*/)?(cargo|rustc|kache) |docker (run|exec)' | grep -vc 'kache daemon' || true)
containers=$(docker ps -q 2>/dev/null | wc -l | tr -d ' ' || true)
prose=$(grep -c '"type":"message_end","message":{"role":"assistant","content":\[{"type":"text"' "$LOG" || true)
free=$(df -h "$HOME" | awk 'NR==2{print $4}')
commit_age='?'
if [ -n "$WT" ]; then
  ct=$(git -C "$WT" log -1 --format=%ct 2>/dev/null || true)
  [ -n "$ct" ] && commit_age=$(( (now-ct)/60 ))
fi
tools=$(grep '"type":"tool_execution_start"' "$LOG" 2>/dev/null \
  | jq -r '[.toolName, ((.args.command // "") | gsub("[\n\t]"; " ") | .[0:60])] | @tsv' 2>/dev/null || true)
calls_since_edit=$(printf '%s\n' "$tools" | awk -F'\t' '$1=="edit"||$1=="write"{n=0;next} NF{n++} END{print n+0}')
top=$(printf '%s\n' "$tools" \
  | awk -F'\t' '$1=="bash" && $2 ~ /git commit/ {delete c; next} $1=="bash" && $2!="" {c[$2]++}
      END{b=0; t=""; for(k in c) if(c[k]>b){b=c[k]; t=k} if(b>0) printf "%dx %s", b, t}')
echo "pid=${P:-none} alive=$alive log_age_min=$age lines=$lines last=$last builds=$builds containers=$containers prose_msgs=$prose free=$free commit_age_min=$commit_age calls_since_edit=$calls_since_edit top_cmd=\"${top:-none}\""
