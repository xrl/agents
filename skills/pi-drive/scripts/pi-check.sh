#!/usr/bin/env bash
# One-line health of a running pi print-mode turn, for an unattended watch loop.
#   pi-check.sh <events.jsonl>
# alive: a process still has the log open (pi's argv shows only "pi", so pgrep -f cannot find it).
# log_age_min: minutes since the log last grew. builds: live cargo/rustc/kache compiles (the idle
# kache daemon excluded). containers: docker containers up. prose_msgs: assistant text messages.
set -euo pipefail
LOG=$1
P=$(lsof -t "$LOG" 2>/dev/null | head -1); alive=no; [ -n "$P" ] && alive=yes
now=$(date +%s); m=$(stat -f %m "$LOG" 2>/dev/null || stat -c %Y "$LOG"); age=$(( (now-m)/60 ))
lines=$(wc -l < "$LOG" | tr -d ' '); last=$(tail -1 "$LOG" | jq -r '.type' 2>/dev/null || echo '?')
builds=$(ps -Ao command | grep -E '^(/[^ ]*/)?(cargo|rustc|kache) |docker (run|exec)' | grep -vc 'kache daemon' || true)
containers=$(docker ps -q 2>/dev/null | wc -l | tr -d ' ')
prose=$(grep -c '"type":"message_end","message":{"role":"assistant","content":\[{"type":"text"' "$LOG" || true)
free=$(df -h "$HOME" | awk 'NR==2{print $4}')
echo "pid=${P:-none} alive=$alive log_age_min=$age lines=$lines last=$last builds=$builds containers=$containers prose_msgs=$prose free=$free"
