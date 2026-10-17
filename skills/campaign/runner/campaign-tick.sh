#!/usr/bin/env bash
# shellcheck disable=SC2016  # jq programs are single-quoted on purpose
# The campaign runner (DESIGN M1, A7). launchd runs one tick every 300 s under a per-epoch flock.
# A tick syncs state from GitHub, launches the lanes `cm next` lists, performs the mechanical acts
# [authority] allows, wakes Claude only for judgment, and pushes the ledger.
#
#   campaign-tick.sh <epoch-dir> <approved-sha | planning>
#
# Trust inputs (N1). [authority] (LIMITS.toml) and the required checks and train (EXECUTION.md
# §Gates, §Train) are read with `git show <approved-sha>:…`, the SHA the owner's plist carries.
# Fable verdicts come only from run/verdicts/, which only lane-fable.sh writes. Tag versions come
# only from cm release steps (00-release/<unit>/<version>). Only LIMITS `paused` is read live.
# The wake can write the ledger but not LIMITS.toml or run/, so it holds no publish or deploy right.
# In `planning` mode there is no [authority], so no merge, tag or pin happens.
set -uo pipefail
. "$(dirname "$0")/lane-lib.sh"
EPOCH=$(cd "$1" && pwd -P); SHA=$2
export CAMPAIGN_EPOCH=$EPOCH CAMPAIGN_CODE=$CODE
ROOT=$(git -C "$EPOCH" rev-parse --show-toplevel); EREL=${EPOCH#"$ROOT"/}; NAME=${EPOCH##*/}
RUN=$EPOCH/run; mkdir -p "$RUN/verdicts" "$RUN/events/done" "$RUN/wakes" "$RUN/deploys" "$RUN/smoke"
exec 9>"$RUN/tick.lock"; flock -n 9 || exit 0
exec >>"$RUN/tick.log" 2>&1
grep -Eq '^[[:space:]]*paused[[:space:]]*=[[:space:]]*true' "$EPOCH/LIMITS.toml" && { log paused; exit 0; }
HOMELAB=${HOMELAB_REPO:-xrl/rpi-homelab}; KCTX=${KUBE_CONTEXT:-rpi}
NOTES=""; ACTED=""
note() { case " · $NOTES · " in *" · $* · "*) ;; *) NOTES="${NOTES:+$NOTES · }$*" ;; esac; log "$*"; }
cm() { command cm -C "$EPOCH" "$@"; }
# Generated files never enter the ledger (DESIGN S3d), whatever the ledger's .gitignore says.
EXCL=$(git -C "$ROOT" rev-parse --path-format=absolute --git-path info/exclude)
grep -qxF '**/run/' "$EXCL" 2>/dev/null || echo '**/run/' >>"$EXCL"

# --- 0. trust inputs, at the approved SHA only ---
AUTH=""; GATES=""; TRAIN=""; EXEC_MD=""
if [ "$SHA" != planning ]; then
  if git -C "$ROOT" cat-file -e "$SHA^{commit}" 2>/dev/null; then
    AUTH=$(git -C "$ROOT" show "$SHA:$EREL/LIMITS.toml" 2>/dev/null)
    EXEC_MD=$(git -C "$ROOT" show "$SHA:$EREL/EXECUTION.md" 2>/dev/null)
    GATES=$(fenced_toml Gates <<<"$EXEC_MD"); TRAIN=$(fenced_toml Train <<<"$EXEC_MD")
  else note "approved SHA $SHA not found: no mechanical acts"; fi
fi
allowed() { [ "$(toml_get authority "$1" <<<"$AUTH")" = true ]; }
auth_has() { toml_get authority "$1" <<<"$AUTH" | toml_list | grep -qxF "$2"; }
train() { toml_str "train.$1" "$2" <<<"$TRAIN"; }

event() { # <key> <text>: one judgment event for the next wake, once per key
  local k=${1//[^A-Za-z0-9._-]/_}
  [ -e "$RUN/events/$k" ] || [ -e "$RUN/events/done/$k" ] || { printf '%s\n' "$2" >"$RUN/events/$k"; log "event $k"; }
}
step_state() { jq -r --arg s "${1##*/}" '.steps[$s].state // empty' "$EPOCH/${1%/*}/.cm/state.json" 2>/dev/null; }
alive() { [ -n "$1" ] && [ "$1" -gt 1 ] 2>/dev/null && kill -0 "$1" 2>/dev/null; }
pr_repo() { sed -E 's#https://github.com/([^/]+/[^/]+)/pull/.*#\1#' <<<"$1"; }

# checks_green <owner/repo> <sha>: 0 every required check named in §Gates passed at sha; 1 one
# failed, or none is named (zero named is red); 2 one is pending or absent.
checks_green() {
  local names runs sts n r s pending=""
  names=$(toml_get required_checks "$1" <<<"$GATES" | toml_list)
  [ -n "$names" ] || return 1
  runs=$(gh api "repos/$1/commits/$2/check-runs?per_page=100" --paginate -q '.check_runs[] | [.name, (.conclusion // "")] | @tsv') || return 2
  sts=$(gh api "repos/$1/commits/$2/status" -q '.statuses[] | [.context, .state] | @tsv') || return 2
  while IFS= read -r n; do
    r=$(awk -F'\t' -v n="$n" '$1 == n { print $2; exit }' <<<"$runs")
    s=$(awk -F'\t' -v n="$n" '$1 == n { print $2; exit }' <<<"$sts")
    case "$r:$s" in success:*|:success) ;; :|:pending) pending=1 ;; *) return 1 ;; esac
  done <<<"$names"
  [ -z "$pending" ] || return 2
}

# --- 1. sync ---
git -C "$ROOT" pull -q --rebase --autostash || note "git pull failed"
cm sync || note "cm sync exited 1 (a PR closed unmerged, or an observation gh could not make)"
NEXT=$(cm next --json 2>/dev/null) || NEXT='{}'   # {steps, waiting, tags} (cm 0.3)

# --- 2. launch what cm lists ---
lane_script() { case $1 in pi) echo pi-lane.sh ;; codex) echo lane-codex.sh ;; claude-cloud) echo lane-claude.sh ;; fable) echo lane-fable.sh ;; opus-fix) echo lane-opus-fix.sh ;; *) return 1 ;; esac; }
start_lane() { # <step> <lane> <args…>: the lane script, detached; recorded in <step>/run/lane.json
  local step=$1 lane=$2 sr=$EPOCH/$1/run script; shift 2
  script=$(lane_script "$lane") || { note "unknown lane $lane for $step"; return 1; }
  mkdir -p "$sr"; rm -f "$sr/exit"
  nohup "$RUNNER/$script" "$@" >>"$sr/lane.log" 2>&1 </dev/null &
  jq -n --arg lane "$lane" --argjson pid "$!" --arg at "$(now)" --args '{lane: $lane, pid: $pid, at: $at, args: $ARGS.positional}' "$@" >"$sr/lane.json"
  log "launched $lane $step"
}
worktree_for() { # <owner/repo> <step>: the step's worktree on branch campaign/<slug>, cut from the default branch
  local clone=$CODE/${1#*/} slug=${2//\//-} wt
  wt=$CODE/${1#*/}.wt/$slug
  [ -d "$wt" ] && { echo "$wt"; return; }
  git -C "$clone" fetch -q origin || return 1
  git -C "$clone" worktree add -q -b "campaign/$slug" "$wt" "$(git -C "$clone" symbolic-ref --short refs/remotes/origin/HEAD)" && echo "$wt"
}
# A step's repository is the `repo: <owner/name>` line of its kickoff.md (cm records none).
step_repo() { sed -nE 's/^repo:[[:space:]]*([^[:space:]]+).*/\1/p' "$EPOCH/$1/kickoff.md" 2>/dev/null | head -1; }
while IFS=$'\t' read -r step lane; do
  [ -n "$step" ] || continue
  case $lane in
    owner) continue ;;
    fable) cm launch "$step" && start_lane "$step" fable "$EPOCH/$step" ;;
    *) repo=$(step_repo "$step")
       wt=$(worktree_for "$repo" "$step") || { note "no worktree for $step (kickoff repo: ${repo:-none})"; continue; }
       cm launch "$step" --worktree "$wt" && start_lane "$step" "$lane" "$EPOCH/$step" "$wt" ;;
  esac
done < <(jq -r '.steps[]? | [.target, (.lane // "")] | @tsv' <<<"$NEXT")

# --- 3. mechanical acts ---

# 3a. lane outcomes
on_exit() { # <step> <lane-json> <rc>
  local step=$1 sr=$EPOCH/$1/run lane wt n
  lane=$(jq -r .lane "$2"); wt=$(jq -r '.args[1] // empty' "$2")
  case $lane:$3 in
    opus-fix:0) echo 0 >"$sr/resumes"; start_lane "$step" pi "$EPOCH/$step" "$wt" --integrate "$(jq -r .fix_sha "$sr/result.json")" ;;
    *:0) echo 0 >"$sr/resumes"
         local pr head; pr=$(jq -r '.pr // empty' "$sr/result.json" 2>/dev/null); head=$(jq -r '.head // empty' "$sr/result.json" 2>/dev/null)
         if [ -z "$pr" ]; then event "finished-${step//\//-}-$(date +%s)" "Lane $lane finished $step; its output is in $step/."
         elif [ "$(step_state "$step")" = launched ]; then cm advance "$step" pr-open --sha "$head" --pr "$pr" --repo "$wt" || note "cm advance pr-open refused for $step"; fi ;;
    opus-fix:*) event "opus-fix-${step//\//-}-$(date +%s)" "The Opus fix on $step exited $3: $step/run/handback.md, $step/run/lane.log." ;;
    pi:10) start_lane "$step" opus-fix "$EPOCH/$step" "$wt" "$(jq -r '.findings // empty' "$sr/lane-state.json")" ;;
    *:30|*:crash)
         n=$(( $(cat "$sr/resumes" 2>/dev/null || echo 0) + 1 )); echo "$n" >"$sr/resumes"
         if [ "$n" -le 2 ]; then start_lane "$step" "$lane" "$EPOCH/$step" ${wt:+"$wt"} --resume
         else event "crashed-${step//\//-}-$(date +%s)" "Lane $lane on $step stopped twice (last: $3); see $step/run/lane.log."; fi ;;
    *) event "lane-${step//\//-}-$(date +%s)" "Lane $lane on $step exited $3 (20 hand-back: $step/run/handback.md; 40 tripwire: $step/run/lane.log)." ;;
  esac
}
for lj in "$EPOCH"/*/*/*/run/lane.json; do
  [ -f "$lj" ] || continue
  sr=${lj%/lane.json}; step=${sr%/run}; step=${step#"$EPOCH"/}
  if [ -f "$sr/exit" ]; then rc=$(cat "$sr/exit"); mv "$sr/exit" "$sr/exit.seen"; on_exit "$step" "$lj" "$rc"
  elif [ -f "$sr/exit.seen" ] && [ "$sr/exit.seen" -nt "$lj" ]; then
    # finished: a decision the wake wrote since is the lane's next prompt (the build lane's, after an Opus fix)
    # shellcheck disable=SC2012  # decision-N.md names are ours
    d=$(ls -t "$EPOCH/$step"/decision-*.md 2>/dev/null | head -1)
    if [ -n "$d" ] && [ "$d" -nt "$sr/exit.seen" ]; then
      lane=$(jq -r .lane "$lj"); [ "$lane" = opus-fix ] && lane=pi
      start_lane "$step" "$lane" "$EPOCH/$step" "$(jq -r '.args[1] // empty' "$lj")" --resume
    fi
  elif ! alive "$(jq -r .pid "$lj")"; then echo crash >"$sr/exit.seen"; on_exit "$step" "$lj" crash
  fi
done

# 3b. Fable reads and merges of plan PRs: every required check green at H and a MERGE verdict at H
merge_pr() { # <url> <head>
  local body; body=$(gh pr view "$1" --json commits -q '.commits[].messageBody' | grep -E '^Changelog:' || true)
  [ "$(gh pr view "$1" --json isDraft -q .isDraft)" = false ] || gh pr ready "$1" || return 1
  gh pr merge "$1" --squash --match-head-commit "$2" --body "$body" && { ACTED=1; log "merged $1 at $2"; }
}
for f in "$EPOCH"/*/*/.cm/state.json; do
  [ -f "$f" ] || continue
  unit=${f%/.cm/state.json}; unit=${unit#"$EPOCH"/}
  jq -r --arg u "$unit" '.steps | to_entries[] | select(.value.state == "pr-open") | ["\($u)/\(.key)", (.value.evidence.pr // "")] | @tsv' "$f"
done | while IFS=$'\t' read -r step url; do
  [ -n "$url" ] || continue
  repo=$(pr_repo "$url"); H=$(gh pr view "$url" --json state,headRefOid -q 'select(.state == "OPEN") | .headRefOid') || continue
  if [ -z "$H" ] || ! checks_green "$repo" "$H"; then continue; fi
  key=${repo//\//_}-${url##*/}-$H; vf=$RUN/verdicts/$key
  if [ ! -f "$vf" ]; then
    alive "$(cat "$vf.pid" 2>/dev/null)" && continue
    nohup "$RUNNER/lane-fable.sh" --pr "$url" "$H" "$EPOCH/$step" >>"$vf.log" 2>&1 </dev/null & echo $! >"$vf.pid"
    continue
  fi
  case $(head -1 "$vf") in
    MERGE) allowed merge && merge_pr "$url" "$H" && touch "$RUN/acted" ;;
    *) event "fable-$key" "Fable FIX on $url at $H ($step): $step/FABLE-READ-${H:0:12}.md" ;;
  esac
done
[ -f "$RUN/acted" ] && { ACTED=1; rm -f "$RUN/acted"; }   # the loop above runs in a subshell

# 3c. Tags: `cm next` lists each merged release step with its version and the prep merge to tag;
# the bump is checked against the last tag
bump_kind() { # <last> <new>
  local a b c x y z; IFS=. read -r a b c <<<"$1"; IFS=. read -r x y z <<<"$2"
  if [ "$x" -gt "$a" ]; then echo major; elif [ "$x" -eq "$a" ] && [ "$y" -gt "$b" ]; then echo minor
  elif [ "$x" -eq "$a" ] && [ "$y" -eq "$b" ] && [ "$z" -gt "$c" ]; then echo patch; else echo none; fi
}
in_flight() { grep -lE '"phase": *"(tagged|revert|pinned|merged)"' "$RUN"/deploys/"$1"-*.json >/dev/null 2>&1; }
cut_release() { # <unit> <version> <merge-sha> <repo cm read from the prep PR> <tag names cm accepts>
  local unit=$1 ver=$2 sha=$3 pr repo pat tag prefix clone last kind
  pr=$(jq -r --arg v "$ver" '.steps[$v].evidence.pr // empty' "$EPOCH/00-release/$unit/.cm/state.json")
  repo=$(train "$unit" repo); pat=$(train "$unit" tag); pat=${pat:-v\{version\}}
  [ -n "$repo" ] || { note "no §Train entry for $unit"; return; }
  [ "$repo" = "$4" ] || { note "refused: $unit prep PR is in ${4:-no repo}, §Train says $repo"; return; }
  auth_has release_repos "$repo" || { note "release of $repo not in [authority]"; return; }
  [[ $ver =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { note "refused: $unit version $ver"; return; }
  tag=${pat//\{version\}/$ver}; prefix=${pat%%\{version\}*}; clone=$CODE/${repo#*/}
  grep -qxF "$tag" <<<"$5" || { note "refused: tag $tag is not one cm sync recognizes for $unit"; return; }
  [ -f "$RUN/deploys/$unit-$ver.json" ] && return
  in_flight "$unit" && return   # one release of a unit in flight
  git -C "$clone" fetch -q --tags origin || return
  [ "$(pr_repo "$pr")" = "$repo" ] && [ "$(gh pr view "$pr" --json state,mergeCommit -q '.state + " " + .mergeCommit.oid')" = "MERGED $sha" ] ||
    { note "refused: $unit $ver evidence does not match its prep PR"; return; }
  last=$(git -C "$clone" tag -l "${prefix}[0-9]*" --sort=-v:refname | head -1); last=${last#"$prefix"}
  [ -n "$last" ] || { note "refused: $unit has no previous tag"; return; }
  kind=$(bump_kind "$last" "$ver")
  auth_has release_bumps "$kind" || { note "refused: $unit $last → $ver is a $kind bump"; return; }
  if ! { git -C "$clone" tag -a "$tag" -m "$tag" "$sha" && git -C "$clone" push -q origin "refs/tags/$tag"; }; then note "tag push failed: $tag"; return; fi
  jq -n --arg unit "$unit" --arg ver "$ver" --arg tag "$tag" --arg repo "$repo" \
    --arg phase "$( [ -n "$(train "$unit" pin_file)" ] && echo tagged || echo "done" )" \
    '{unit: $unit, ver: $ver, tag: $tag, repo: $repo, phase: $phase}' >"$RUN/deploys/$unit-$ver.json"
  cm journal "Release: $repo $tag at ${sha:0:12} ($last → $ver, $kind)" </dev/null
  ACTED=1
}
if [ -n "$AUTH" ]; then
  while IFS=$'\t' read -r target repo ver sha names; do
    [ -n "$target" ] || continue
    unit=${target#00-release/}; unit=${unit%/*}
    cut_release "$unit" "$ver" "$sha" "$repo" "$(tr ' ' '\n' <<<"$names")"
  done < <(jq -r '.tags[]? | [.target, (.repo // ""), .version, (.sha // ""), (.tags | join(" "))] | @tsv' <<<"$NEXT")
fi

# 3d. Deploys: pin PR → merge on the LAN → Argo Synced/Healthy → LAN smoke → receipt (DESIGN M6, A6)
rec_get() { jq -r --arg k "$2" '.[$k] // empty' "$1"; }
rec_set() { local t; t=$(mktemp "$RUN/.rec.XXXXXX"); jq "${@:2}" "$1" >"$t" && mv "$t" "$1"; }
open_pin_pr() { # <record> <branch> <commit-message> <edit-function> → sets pr and phase pinned
  local rec=$1 br=$2 hc=$CODE/${HOMELAB#*/} wt url
  [ "$(gh pr list -R "$HOMELAB" --state open --json headRefName -q '[.[] | select(.headRefName | startswith("pin/"))] | length')" = 0 ] || return 0
  wt=$RUN/homelab-${br//\//-}; git -C "$hc" fetch -q origin || return 0
  git -C "$hc" worktree add -q -B "$br" "$wt" origin/main || return 0
  if "$4" "$wt" && ! git -C "$wt" diff --quiet HEAD; then
    git -C "$wt" commit -qam "$3" && git -C "$wt" push -q -u origin "$br" &&
      url=$(gh pr create -R "$HOMELAB" --head "$br" --base main --title "$3" --body "Pin-only change opened by the campaign tick ($NAME).") &&
      rec_set "$rec" --arg pr "$url" '.pr = $pr | .phase = "pinned"' && ACTED=1
  else note "pin edit failed for $br"; fi
  git -C "$hc" worktree remove --force "$wt"
}
PIN_FILE=""; PIN_LINE=""; PIN_DIGEST=""; REVERT_SHA=""
edit_pin() { # exactly one line matches pin_line; its sha256 digest becomes the release's
  [ "$(grep -cE "$PIN_LINE" "$1/$PIN_FILE")" = 1 ] || return 1
  awk -v re="$PIN_LINE" -v d="$PIN_DIGEST" '$0 ~ re { sub(/sha256:[0-9a-f]+/, d) } 1' "$1/$PIN_FILE" >"$1/.pin.tmp" && mv "$1/.pin.tmp" "$1/$PIN_FILE"
}
edit_revert() { git -C "$1" revert --no-commit "$REVERT_SHA"; }

lan_ok() { [ "$(timeout 20 kubectl --context="$KCTX" get --raw /readyz 2>/dev/null)" = ok ]; }
smoke() { # <record>: once per provider command list; one receipt line; cm advance deployed
  local rec=$1 unit ver ns sel agent pod dir ok=0 total=0 errs cmds since receipt
  unit=$(rec_get "$rec" unit); ver=$(rec_get "$rec" ver); since=$(rec_get "$rec" synced_at)
  ns=$(train "$unit" namespace); ns=${ns:-dekopon}; sel=$(train "$unit" pod_selector); sel=${sel:-app.kubernetes.io/name=dekopon}
  agent=$(train "$unit" smoke_agent); agent=${agent:-ville-github}; dir=$RUN/smoke/$unit-$ver; mkdir -p "$dir"
  pod=$(kubectl --context="$KCTX" -n "$ns" get pods -l "$sel" -o json |
    jq -r 'first(.items[] | select(.status.containerStatuses and all(.status.containerStatuses[]; .ready)) | .metadata.name) // empty')
  for cmds in "${SMOKE_COMMANDS:-$HOME/.config/campaign/smoke}"/*.txt; do
    [ -f "$cmds" ] && [ -n "$pod" ] || continue
    total=$(( total + 1 ))
    timeout 600 python3 -I "$ROOT/tools/smoke/console-sequence.py" --pod "$pod" --agent "$agent" --input "$cmds" \
      --receipt-dir "$dir/$(basename "$cmds" .txt)" >"$dir/$(basename "$cmds" .txt).out" 2>&1 && ok=$(( ok + 1 ))
  done
  errs=$(kubectl --context="$KCTX" -n "$ns" logs "$pod" --all-containers --since-time="$since" 2>/dev/null | grep -cE '\bERROR\b|"level":"error"') || true
  # console-sequence.py checks framing, not broker success, so any gateway or broker error line is red too
  receipt="$unit $ver: pin $(rec_get "$rec" pr), digest $(rec_get "$rec" digest), LAN smoke transport $ok/$total providers, ${errs:-0} error lines since $since; receipts in run/smoke/$unit-$ver/"
  cm journal "Deployed $unit $ver" --body-file - <<<"$receipt"
  if [ "$total" -gt 0 ] && [ "$ok" = "$total" ] && [ "${errs:-0}" = 0 ]; then
    cm advance "00-release/$unit/$ver" deployed --digest "$(rec_get "$rec" digest)" || note "cm advance deployed refused for $unit $ver"
    rec_set "$rec" '.phase = "done"'
  else
    rec_set "$rec" '.phase = "failed"'
    event "smoke-$unit-$ver" "LAN smoke red after the $unit $ver deploy: $receipt"
    if grep -qx 'revert-safe: yes' "$EPOCH/00-release/$unit/$ver/kickoff.md" 2>/dev/null; then
      jq -n --arg unit "$unit" --arg ver "revert-$ver" --arg sha "$(rec_get "$rec" merge_sha)" \
        '{unit: $unit, ver: $ver, revert_of: $sha, phase: "revert"}' >"$RUN/deploys/$unit-revert-$ver.json"
    fi
  fi
  ACTED=1
}
for rec in "$RUN"/deploys/*.json; do
  [ -f "$rec" ] || continue
  unit=$(rec_get "$rec" unit); ver=$(rec_get "$rec" ver)
  case $(rec_get "$rec" phase) in
    tagged|revert) allowed homelab_deploy || { note "homelab deploy not in [authority]"; continue; }
      if [ "$(rec_get "$rec" phase)" = revert ]; then
        REVERT_SHA=$(rec_get "$rec" revert_of); open_pin_pr "$rec" "pin/$unit-$ver" "Revert $unit ${ver#revert-} pin" edit_revert; continue
      fi
      wf=$(train "$unit" release_workflow); run=$(gh run list -R "$(rec_get "$rec" repo)" --workflow "${wf:-release.yml}" --json headBranch,status,conclusion \
        -q "[.[] | select(.headBranch == \"$(rec_get "$rec" tag)\")][0] | .status + \" \" + (.conclusion // \"\")")
      case $run in
        "completed success")
          image=$(train "$unit" image); PIN_DIGEST=$(crane digest "${image//\{version\}/$ver}") || { note "no digest for $unit $ver"; continue; }
          PIN_FILE=$(train "$unit" pin_file); PIN_LINE=$(train "$unit" pin_line)
          rec_set "$rec" --arg d "$PIN_DIGEST" '.digest = $d'
          open_pin_pr "$rec" "pin/$unit-$ver" "Pin $unit $ver" edit_pin ;;
        completed*) event "release-red-$unit-$ver" "The release run for $unit $(rec_get "$rec" tag) ended: $run." ;;
      esac ;;
    pinned) pr=$(rec_get "$rec" pr)
      info=$(gh pr view "$pr" --json state,headRefOid,mergeCommit,files,additions,deletions) || continue
      H=$(jq -r .headRefOid <<<"$info")
      if [ "$(jq -r .state <<<"$info")" = OPEN ]; then
        [ "$(jq -r '[(.files | length), .files[0].path, .additions, .deletions] | map(tostring) | join(" ")' <<<"$info")" = "1 $(train "$unit" pin_file) 1 1" ] ||
          { note "$pr is not pin-only: left for the owner"; continue; }
        checks_green "$HOMELAB" "$H" || continue
        lan_ok || { note "deploys held: off LAN"; continue; }
        gh pr merge "$pr" --squash --match-head-commit "$H" || continue
        info=$(gh pr view "$pr" --json state,mergeCommit); ACTED=1
      fi
      [ "$(jq -r .state <<<"$info")" = MERGED ] &&
        rec_set "$rec" --arg s "$(jq -r .mergeCommit.oid <<<"$info")" --argjson t "$(date +%s)" '.merge_sha = $s | .merged_epoch = $t | .phase = "merged"' ;;
    merged) app=$(train "$unit" argo_app)
      a=$(kubectl --context="$KCTX" -n argocd get applications.argoproj.io "${app:-dekopon}" -o json 2>/dev/null) || { note "deploys held: off LAN"; continue; }
      if [ "$(jq -r '[.status.sync.status, .status.health.status, .status.sync.revision] | join(" ")' <<<"$a")" = "Synced Healthy $(rec_get "$rec" merge_sha)" ]; then
        rec_set "$rec" --arg t "$(jq -r '.status.operationState.finishedAt // empty' <<<"$a")" '.synced_at = $t'
        case $ver in revert-*) cm journal "Reverted $unit ${ver#revert-}: pin $(rec_get "$rec" pr) is Synced and Healthy" </dev/null; rec_set "$rec" '.phase = "done"' ;;
                      *) smoke "$rec" ;; esac
      elif [ $(( $(date +%s) - $(rec_get "$rec" merged_epoch) )) -gt 2400 ]; then
        event "not-healthy-$unit-$ver" "Argo is not Synced and Healthy at $(rec_get "$rec" merge_sha) 40 minutes after the $unit $ver pin merged."
      fi ;;
  esac
done

# --- 4. judgment: one wake for every pending event ---
QH=$(git -C "$ROOT" hash-object "$EPOCH/OWNER-QUEUE.md" 2>/dev/null || true)
if [ -f "$RUN/queue.hash" ] && [ "$QH" != "$(cat "$RUN/queue.hash")" ] && grep -qi 'answer' "$EPOCH/OWNER-QUEUE.md"; then
  event "queue-$QH" "OWNER-QUEUE.md changed and carries an answer."
fi
echo "$QH" >"$RUN/queue.hash"
EVENTS=$(find "$RUN/events" -maxdepth 1 -type f | sort)
if [ -n "$EVENTS" ] && ! [ -n "$(find "$RUN/wake-failed" -mmin -30 2>/dev/null)" ]; then
  if [ -n "$AUTH" ]; then TPL=$RUNNER/wake-working.md; else TPL=$RUNNER/wake-planning.md; fi
  AUTHORITY=$(awk '/^> \*\*Authorized for/ { f = 1 } f && !/^>/ { exit } f' <<<"$(git -C "$ROOT" show "$SHA:$EREL/EPOCH.md" 2>/dev/null)")
  LIST=$(while IFS= read -r e; do printf -- '- %s\n' "$(cat "$e")"; done <<<"$EVENTS")
  P=$(sed '1,/^---$/d' "$TPL"); AUTHORITY=${AUTHORITY:-(no authority block at the approved SHA)}
  P=${P//<epoch>/"$NAME"}; P=${P//<sha>/"$SHA"}; P=${P//<authority>/"$AUTHORITY"}; P=${P//<events>/"$LIST"}
  cp "$RUNNER/wake.settings.json" "$RUN/wake.settings.json"
  OUT=$RUN/wakes/$(date -u +%Y%m%dT%H%M%SZ).json
  log "wake: $(wc -l <<<"$EVENTS" | tr -d ' ') events"
  if (cd "$EPOCH" && timeout 2700 claude -p --model "${WAKE_MODEL:-claude-opus-5-5}" --settings "$RUN/wake.settings.json" \
        --output-format json "$P" </dev/null >"$OUT") && [ "$(jq -r .is_error "$OUT")" = false ]; then
    while IFS= read -r e; do mv "$e" "$RUN/events/done/"; done <<<"$EVENTS"
    git -C "$ROOT" hash-object "$EPOCH/OWNER-QUEUE.md" >"$RUN/queue.hash" 2>/dev/null
    ACTED=1
  else touch "$RUN/wake-failed"; note "wake failed: $OUT"; fi
  log_cost wake "$OUT"
fi

# --- 5. the card's tick line, then push at an act or after 30 minutes unpushed (DESIGN S3c) ---
# cm sync rewrote CARD.md with `Last run: <stamp>` first; the tick's line goes second (N4: "deploys held")
C=$EPOCH/CARD.md
TICK="Tick: $([ -n "$AUTH" ] && echo "plan ${SHA:0:12}" || echo planning)${NOTES:+ · $NOTES}"
[ -f "$C" ] && awk -v t="$TICK" 'NR == 2 && /^Tick: / { next } { print } NR == 1 { print t }' "$C" >"$C.tmp" && mv "$C.tmp" "$C"
LAST_PUSH=$(cat "$RUN/last-push" 2>/dev/null || echo 0)
if [ -n "$ACTED" ] || [ $(( $(date +%s) - LAST_PUSH )) -ge 1800 ]; then
  git -C "$ROOT" add -A -- "$EREL"
  git -C "$ROOT" diff --cached --quiet || git -C "$ROOT" commit -qm "$NAME: tick $(now)"
  if [ -n "$(git -C "$ROOT" log '@{u}..' --oneline 2>/dev/null)" ]; then
    if git -C "$ROOT" pull -q --rebase --autostash && git -C "$ROOT" push -q; then date +%s >"$RUN/last-push"; else note "push failed"; fi
  else date +%s >"$RUN/last-push"; fi
fi
log "tick done${NOTES:+: $NOTES}"
