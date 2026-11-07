#!/usr/bin/env bash
set -u

usage() {
  cat <<'EOF'
usage:
  mem_sampler.sh sample <pr-number> <out-dir> [interval-s=5] [max-s=7200]
  mem_sampler.sh mark   <out-dir> <marker> [detail]
  mem_sampler.sh procs  <pr-number> <out-dir> <label>
  mem_sampler.sh oome   <pr-number> <out-dir> <label>

sample  every interval, for every rx-reveal pod: kubectl top, cgroup memory.peak/current, memory.stat
        anon/file, restarts, ready, last termination reason -> <out-dir>/samples.csv. Stops at max-s or when
        <out-dir>/.stop exists. Run it with run_in_background.
mark    appends ts,marker,detail to <out-dir>/markers.csv (scenario start/end, pod deletes, ready).
procs   per-pod process list (pid, RSS kB, comm) plus du of /scratch, ~/.cache, /tmp and any Chromium or
        SDK bundle files -> <out-dir>/server/procs-<label>.txt. Take one at each peak.
oome    per-pod restart count, OOMKilled, and the count of OutOfMemoryException lines in the current and
        previous container logs -> <out-dir>/server/oome-<label>.txt. Take one before and one after.
All four are read-only (kubectl top/get/exec cat/logs). Every kubectl call runs under `timeout`.
Env: KUBE_CONTEXT (default k3).
EOF
}

CTX=${KUBE_CONTEXT:-k3}
ts() { date -u +%FT%TZ; }
pods_of() {
  timeout 15 kubectl --context "$CTX" -n "rx-pr-$1" get pods -l app.kubernetes.io/name=rx-reveal \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null
}

sample() {
  N=$1; E=$2; every=${3:-5}; max=${4:-7200}
  NS=rx-pr-$N
  mkdir -p "$E"
  out=$E/samples.csv
  [ -f "$out" ] || echo "ts,pod,top_cpu_m,top_mem_mi,memory_peak_bytes,memory_current_bytes,anon_bytes,file_bytes,restarts,ready,last_term_reason" > "$out"
  T=$(mktemp -d)
  end=$(( $(date +%s) + max ))
  while [ "$(date +%s)" -lt "$end" ] && [ ! -e "$E/.stop" ]; do
    t0=$(date +%s)
    now=$(ts)
    pods=$(pods_of "$N")
    for p in $pods; do
      ( timeout 8 kubectl --context "$CTX" -n "$NS" exec "$p" -c rx-reveal -- sh -c \
          'cat /sys/fs/cgroup/memory.peak /sys/fs/cgroup/memory.current; grep -E "^(anon|file) " /sys/fs/cgroup/memory.stat | cut -d" " -f2' \
          2>/dev/null | tr '\n' ' ' > "$T/m-$p" ) &
    done
    ( timeout 8 kubectl --context "$CTX" -n "$NS" top pods -l app.kubernetes.io/name=rx-reveal --no-headers 2>/dev/null > "$T/top" ) &
    ( timeout 8 kubectl --context "$CTX" -n "$NS" get pods -l app.kubernetes.io/name=rx-reveal \
        -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].restartCount} {.status.containerStatuses[0].ready} {.status.containerStatuses[0].lastState.terminated.reason}{"\n"}{end}' \
        2>/dev/null > "$T/st" ) &
    wait
    for p in $pods; do
      pk=; cur=; an=; fl=
      read -r pk cur an fl _ < "$T/m-$p" 2>/dev/null || true
      read -r _ cpu mem _ <<EOF
$(grep "^$p " "$T/top" 2>/dev/null)
EOF
      read -r _ rs rd lr <<EOF
$(grep "^$p " "$T/st" 2>/dev/null)
EOF
      echo "$now,$p,${cpu%m},${mem%Mi},${pk:-},${cur:-},${an:-},${fl:-},${rs:-},${rd:-},${lr:-}" >> "$out"
      rm -f "$T/m-$p"
    done
    el=$(( $(date +%s) - t0 ))
    [ "$el" -lt "$every" ] && sleep $(( every - el ))
  done
  rm -rf "$T"
}

mark() {
  E=$1; m=$2; d=${3:-}
  mkdir -p "$E"
  [ -f "$E/markers.csv" ] || echo "ts,marker,detail" > "$E/markers.csv"
  echo "$(ts),$m,$d" >> "$E/markers.csv"
}

procs() {
  N=$1; E=$2; label=$3
  mkdir -p "$E/server"
  f=$E/server/procs-$label.txt
  : > "$f"
  for p in $(pods_of "$N"); do
    {
      echo "== $p $(ts) [$label]"
      timeout 30 kubectl --context "$CTX" -n "rx-pr-$N" exec "$p" -c rx-reveal -- sh -c \
        'echo "pid rss_kb comm"; for d in /proc/[0-9]*; do [ -r $d/status ] || continue; c=$(cat $d/comm 2>/dev/null); r=$(awk "/^VmRSS/{print \$2}" $d/status 2>/dev/null); echo "${d#/proc/} ${r:-0} $c"; done; echo "-- du"; du -sh /scratch $HOME/.cache /tmp 2>/dev/null; echo "-- chromium/sdk files"; find /scratch $HOME /tmp /opt -maxdepth 6 \( -iname "*chrom*" -o -iname "*reveal-sdk*" -o -iname "*headless*" \) 2>/dev/null | head -20' 2>&1
    } >> "$f"
  done
  cat "$f"
}

oome() {
  N=$1; E=$2; label=$3
  mkdir -p "$E/server"
  f=$E/server/oome-$label.txt
  echo "ts,pod,restarts,last_term_reason,oome_current,oome_previous" > "$f"
  for p in $(pods_of "$N"); do
    st=$(timeout 15 kubectl --context "$CTX" -n "rx-pr-$N" get pod "$p" \
      -o jsonpath='{.status.containerStatuses[0].restartCount},{.status.containerStatuses[0].lastState.terminated.reason}' 2>/dev/null)
    cur=$(timeout 60 kubectl --context "$CTX" -n "rx-pr-$N" logs "$p" -c rx-reveal 2>/dev/null | grep -c OutOfMemoryException)
    prev=$(timeout 60 kubectl --context "$CTX" -n "rx-pr-$N" logs "$p" -c rx-reveal --previous 2>/dev/null | grep -c OutOfMemoryException)
    echo "$(ts),$p,$st,$cur,$prev" >> "$f"
  done
  cat "$f"
}

case "${1:-}" in
  sample) [ $# -ge 3 ] || { usage >&2; exit 2; }; shift; sample "$@" ;;
  mark) [ $# -ge 3 ] || { usage >&2; exit 2; }; shift; mark "$@" ;;
  procs) [ $# -eq 4 ] || { usage >&2; exit 2; }; shift; procs "$@" ;;
  oome) [ $# -eq 4 ] || { usage >&2; exit 2; }; shift; oome "$@" ;;
  -h|--help) usage ;;
  *) usage >&2; exit 2 ;;
esac
