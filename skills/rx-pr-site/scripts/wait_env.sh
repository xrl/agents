#!/usr/bin/env bash
set -u

usage() {
  cat <<'EOF'
usage: wait_env.sh <pr-number> <secrets|built|ready> [max-seconds=3600]

Polls env_status.sh every 60 s until the condition holds, then prints "MET <status>" and exits 0;
prints "TIMEOUT <status>" and exits 1 at the deadline.
  secrets  both clone secrets exist (terraform alter_roles finished)
  built    the PR head's Rails image pr-<N>-<sha8> is in ECR
  ready    Argo reports Synced/Healthy
Run it with run_in_background; it is read-only.
EOF
}

case "${1:-}" in -h|--help) usage; exit 0 ;; esac
[ $# -ge 2 ] || { usage >&2; exit 2; }

N=$1
want=$2
max=${3:-3600}
case $want in
  secrets) pat='secrets=2/2' ;;
  built) pat='head_built=yes' ;;
  ready) pat='app=Synced/Healthy' ;;
  *) usage >&2; exit 2 ;;
esac

here=$(cd "$(dirname "$0")" && pwd)
end=$(( $(date +%s) + max ))
while :; do
  s=$("$here/env_status.sh" "$N")
  if printf '%s\n' "$s" | grep -q "$pat"; then
    echo "MET $s"
    exit 0
  fi
  if [ "$(date +%s)" -ge "$end" ]; then
    echo "TIMEOUT $s"
    exit 1
  fi
  sleep 60
done
