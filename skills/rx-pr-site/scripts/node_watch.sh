#!/usr/bin/env bash
set -u

usage() {
  cat <<'EOF'
usage: node_watch.sh <out-dir> [max-seconds=21600]

Read-only sidecar for terraform applies and long syncs. Every 60 s it appends k8s Node events that
look like a reclaim (Terminat|Removing|NodeNotReady|Spot|Interrupt|Rebalance|Disrupt|Deleting) to
<out-dir>/node-events.log (deduplicated) and the runner pods' node placement to
<out-dir>/node-runners.log. Stops at the deadline or when <out-dir>/.stop exists.
Each kubectl call runs under `timeout 30`; the whole loop is bounded by max-seconds.
Env: KUBE_CONTEXT (default k3).
EOF
}

case "${1:-}" in -h|--help) usage; exit 0 ;; '') usage >&2; exit 2 ;; esac

OUT=$1
max=${2:-21600}
CTX=${KUBE_CONTEXT:-k3}
mkdir -p "$OUT"
events=$OUT/node-events.log
runners=$OUT/node-runners.log
touch "$events"
end=$(( $(date +%s) + max ))

while [ "$(date +%s)" -lt "$end" ] && [ ! -e "$OUT/.stop" ]; do
  ts=$(date -u +%FT%TZ)
  timeout 30 kubectl --context "$CTX" get events -A --field-selector involvedObject.kind=Node \
    -o custom-columns='T:.lastTimestamp,R:.reason,N:.involvedObject.name,M:.message' --no-headers 2>/dev/null \
    | grep -E -i 'Terminat|Removing|NodeNotReady|Spot|Interrupt|Rebalance|Disrupt|Deleting' >> "$events"
  sort -u "$events" -o "$events"
  timeout 30 kubectl --context "$CTX" get pods -A -o wide --no-headers 2>/dev/null \
    | grep -E 'runner' | awk -v t="$ts" '{print t" "$1"/"$2" "$4" "$8}' >> "$runners"
  sleep 60
done
