#!/usr/bin/env bash
set -u

usage() {
  cat <<'EOF'
usage: env_status.sh <pr-number>

One read-only status line for the run-in-k3 PR site rx-pr-<N>:
  app=<sync>/<health> op=<argo operation phase> ns=<phase> secrets=<n>/2
  head=<PR head sha8> head_built=yes|no ecr_tags=<count of pr-<N>-* Rails tags in ECR>
  rails=<Rails image tag running> rxr=<rx-reveal image tag running> pods=[count x name:phase]

Env: KUBE_CONTEXT (default k3), AWS_PROFILE (default scientist), RX_REPO (default scientist-hq/rx).
Every external call is bounded by `timeout 30`.
EOF
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  ''|*[!0-9]*) usage >&2; exit 2 ;;
esac

N=$1
NS=rx-pr-$N
CTX=${KUBE_CONTEXT:-k3}
REPO=${RX_REPO:-scientist-hq/rx}
k() { timeout 30 kubectl --context "$CTX" "$@" 2>/dev/null; }

app=$(k -n argo get application "rx-pr-$N" -o jsonpath='{.status.sync.status}/{.status.health.status}') || app=none
op=$(k -n argo get application "rx-pr-$N" -o jsonpath='{.status.operationState.phase}') || op=none
ns=$(k get ns "$NS" -o jsonpath='{.status.phase}') || ns=none
sec=$(k -n "$NS" get secret rx-pr-postgres-direct-secret rx-reveal-postgres-direct-secret -o name | wc -l | tr -d ' ')
rails=$(k -n "$NS" get deployment "rx-pr-$N" -o jsonpath='{.spec.template.spec.containers[0].image}' | sed 's/.*://')
rxr=$(k -n "$NS" get statefulset "rx-pr-$N-rx-reveal" -o jsonpath='{.spec.template.spec.containers[0].image}' | sed 's/.*://')
pods=$(k -n "$NS" get pods --no-headers | awk '{print $1":"$3}' | sed -E 's/-[a-z0-9]{8,10}-[a-z0-9]{5}:/:/' | sort | uniq -c | awk '{printf "%s×%s ",$1,$2}')
img=$(AWS_PROFILE=${AWS_PROFILE:-scientist} timeout 30 aws ecr list-images --repository-name rx-pr --region eu-central-1 \
  --filter tagStatus=TAGGED --query "imageIds[?starts_with(imageTag,'pr-$N-')].imageTag" --output text 2>/dev/null | tr '\t' ' ')
head=$(timeout 30 gh pr view "$N" -R "$REPO" --json headRefOid -q '.headRefOid[0:8]' 2>/dev/null)
built=no
case " $img " in *" pr-$N-$head "*) built=yes ;; esac

echo "app=${app:-none} op=${op:-none} ns=${ns:-none} secrets=$sec/2 head=${head:-?} head_built=$built ecr_tags=$(printf '%s\n' $img | grep -c .) rails=${rails:-none} rxr=${rxr:-none} pods=[${pods% }]"
