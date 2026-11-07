#!/usr/bin/env bash
set -u

usage() {
  cat <<'EOF'
usage: rails_runner.sh <pr-number> <script.rb> [--with <path>]... [--env K=V]... [--reveal-creds | --stdin <file>] [-- script args...]

Copies <script.rb> (and every --with file or directory) into a fresh /tmp dir of one Running Rails web pod
of rx-pr-<N>, runs `bin/rails runner <dir>/<script.rb> args` there, prints its stdout, and removes the dir
on exit. Pods change on every rollout, so the pod is picked fresh each call and named on stderr.
  --env K=V        passed to the runner via env(1); never use it for a secret (it lands on argv)
  --reveal-creds   pipes the rx-reveal pod's own PG_HOST/PG_PORT/PG_DATABASE/REVEAL_DB_USER/REVEAL_DB_PASSWORD
                   to the runner's stdin, pod to pod (for reveal_ro.rb and the reveal.* pattern)
  --stdin <file>   feeds a local file (e.g. a 0600 password file) to the runner's stdin
The copy and the rm are the only writes this wrapper makes; what the script writes is the script's business.
Env: KUBE_CONTEXT (default k3).
EOF
}

case "${1:-}" in -h|--help) usage; exit 0 ;; esac
[ $# -ge 2 ] || { usage >&2; exit 2; }

N=$1
script=$2
shift 2
NS=rx-pr-$N
CTX=${KUBE_CONTEXT:-k3}
withs=()
envs=(RX_PR_SITE_RUNNER=1)
args=()
creds=no
stdin_file=
while [ $# -gt 0 ]; do
  case $1 in
    --with) withs+=("$2"); shift 2 ;;
    --env) envs+=("$2"); shift 2 ;;
    --reveal-creds) creds=yes; shift ;;
    --stdin) stdin_file=$2; shift 2 ;;
    --) shift; args=("$@"); break ;;
    *) usage >&2; exit 2 ;;
  esac
done
[ -f "$script" ] || { echo "no such script: $script" >&2; exit 2; }

k() { kubectl --context "$CTX" -n "$NS" "$@"; }
pod=$(timeout 30 kubectl --context "$CTX" -n "$NS" get pods -l app.kubernetes.io/name=rx,app.kubernetes.io/component=web \
  --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
[ -n "$pod" ] || { echo "no Running web pod in $NS" >&2; exit 1; }
echo "pod=$pod" >&2

dir=/tmp/rx-pr-site-$(date +%s)-$$
cleanup() { timeout 60 kubectl --context "$CTX" -n "$NS" exec "$pod" -c rx -- rm -rf "$dir" >/dev/null 2>&1; }
trap cleanup EXIT
k exec "$pod" -c rx -- mkdir -p "$dir" || exit 1
k cp -c rx "$script" "$pod:$dir/$(basename "$script")" || exit 1
for w in ${withs[@]+"${withs[@]}"}; do
  k cp -c rx "$w" "$pod:$dir/$(basename "$w")" || exit 1
done

run=(exec -i "$pod" -c rx -- env "${envs[@]}" bin/rails runner "$dir/$(basename "$script")" ${args[@]+"${args[@]}"})
if [ "$creds" = yes ]; then
  k exec "rx-pr-$N-rx-reveal-0" -c rx-reveal -- sh -c 'printf "%s\n" "$PG_HOST" "$PG_PORT" "$PG_DATABASE" "$REVEAL_DB_USER" "$REVEAL_DB_PASSWORD"' \
    | k "${run[@]}"
elif [ -n "$stdin_file" ]; then
  k "${run[@]}" < "$stdin_file"
else
  k "${run[@]}" < /dev/null
fi
