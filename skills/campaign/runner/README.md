# The campaign runner

A launchd tick on the Mac that runs a campaign's WORKING phase (and PLANNING phase 2), with Claude
woken only for judgment. The design is campaign-trail
`store/designs/campaign-efficiency-design/DESIGN.md` (revision 3): M1, M4, M6 and A3, A6, A7. The
gate rehearses all of it (A4) before the owner loads the plist.

| File | Does |
|---|---|
| `campaign-tick.sh <epoch-dir> <approved-sha\|planning>` | one tick: `cm sync`; launch what `cm next` lists; merges, tags, pins and the LAN smoke under `[authority]`; one `claude -p` wake for judgment events; push |
| `pi-lane.sh <step-dir> <worktree> [--resume \| --integrate <sha>]` | the `pi` lane: sol driver turn, gate-log check, fresh sol verifier, `pi-stage-check.sh`; no supervisor |
| `lane-codex.sh <step-dir> <worktree> [--resume]` | the `codex` lane: a Codex Cloud job whose patches become a branch and a draft PR |
| `lane-claude.sh <step-dir> <worktree> [--resume]` | the `claude-cloud` lane: Opus via `claude --cloud` on the step's branch |
| `lane-fable.sh --pr <url> <head> <step-dir>` or `lane-fable.sh <step-dir>` | the `fable` lane: one read-only Fable read; a PR read writes `run/verdicts/` |
| `lane-opus-fix.sh <step-dir> <worktree> <verify-file>` | the Opus code-only fix of a pi lane's `[hard]` findings; Opus leaves the change uncommitted and the lane commits it |
| `git-guard.sh` | the PreToolUse hook of both `claude -p` lanes: a `git` command spelled with a quote, backslash, `$`, backtick or `{` is refused, so the `--output` deny sees the literal token |
| `wake-working.md`, `wake-planning.md` | the A3 wake prompts |
| `wake.settings.json` | the wake's allowlist: edits inside the epoch but not `LIMITS.toml`, `run/` or `.cm/`; `git status`, `git add`, `git commit`, `cm` and read-only `gh`; no `git log`/`show`/`diff` (the wake reads with Read and Grep), push, tag, merge, `gh api` or shell redirection. Any `>` in a command is denied, so a commit message or journal title says `to`, not `->`. The wake runs `claude -p --restricted --strict-mcp-config --tools Read,Grep,Glob,Edit,Write,Bash --add-dir <ledger root> <agents>/skills`: no user, project or local settings load, the file tools read the ledger and the skills, and the allow rules write only the epoch |
| `campaign-tick.plist.template` | the launchd job: every 300 s, RunAtLoad, the approved SHA as an argument |
| `lane-lib.sh` | shared helpers |

## What the tick trusts (N1)

- `[authority]` (`LIMITS.toml`) and the `toml` blocks of EXECUTION.md §Gates and §Train, read with
  `git show <approved-sha>:…`. Only `paused` is read live from the working tree.
- Fable verdicts only from `<epoch>/run/verdicts/<owner_repo>-<pr>-<head>`, which only
  `lane-fable.sh` writes. The wake cannot edit `run/`, so a MERGE written into the ledger by hand
  never merges anything.
- Tag versions and tag names only from the `tags` that `cm next` lists (release steps
  `00-release/<unit>/<version>` at `merged`, each with the one tag name cm records for it), whose prep
  PR must be merged at that SHA in the §Train repository, with the bump checked against the last tag
  and `release_bumps`.

A merge needs the PR to be the step's own (in its kickoff's `repo:`, on the `campaign/<slug>` branch
the tick cut), every required check named for the repository green at the head (none named is red)
and a MERGE verdict at that head, then `gh pr merge --squash --match-head-commit`. A Fable read that
ends twice without a verdict is an event. A homelab PR, a
plan step's or a pin, also needs `homelab_deploy` and `kubectl --context=rpi get --raw /readyz` in
the same tick; otherwise it stays open and the card says `deploys held: off LAN` (N4). The tick keeps
one open homelab PR at a time. A pin PR merges only when it is pin-only (one file, one line).

After a homelab merge the tick waits for the root app (`app-of-apps`) to be Synced at a revision
that contains the merge, and for the unit's app to be Synced and Healthy against its current spec
(its own revisions are chart versions). Then it runs the LAN smoke: every provider's
`results.json` must hold only `ok` results, and the pod logs must show no error line since the sync.
A smoke it cannot observe (no ready pod, no command lists, logs unreadable) is `smoke held` and
retried next tick; held 40 minutes after the merge, it is an event.

## The blocks EXECUTION.md carries

```toml
# §Gates: the checks a merge requires, by repository (zero named is red)
[required_checks]
"dekopon-agents/dekopon" = ["test (Rust)", "quality (stable)"]   # check-run (job) names, not workflow names
"xrl/rpi-homelab" = ["render", "dekopon-check"]
```

```toml
# §Train: one table per release unit, 00-release/<unit>/<version>
[train.dekopon]
repo = "dekopon-agents/dekopon"
tag = "v{version}"                                  # the `cm init --tag` pattern; the tick tags with the name cm lists
image = "ghcr.io/dekopon-agents/dekopon:{version}"   # crane digest source
pin_file = "apps/dekopon.yaml"                      # in the homelab repo
pin_line = "^            digest: sha256:"          # ERE for the one line whose digest the pin replaces (the 12-space top-level image.digest)
argo_app = "dekopon"
namespace = "dekopon"
pod_selector = "app.kubernetes.io/name=dekopon"
smoke_agent = "ville-github"

[train.dekopon-chart]                               # D4: one commit, two tags; no pin
repo = "dekopon-agents/dekopon"
tag = "dekopon-chart-{version}"
with = "dekopon"
```

A unit without `pin_file` (a library, a tool, the chart) is done at its tag. A unit with
`with = "<unit>"` is released from that unit's prep PR: declare its release step with `--lane owner`
(`cm init 00-release/dekopon-chart/<version> --lane owner --github dekopon-agents/dekopon --tag 'dekopon-chart-{version}'`) and a
`kickoff.md` carrying the same `repo:`; when the prep lane opens its PR, the tick moves that step to
`pr-open` on the same PR, and both are tagged at the one prep merge. A release step whose
`kickoff.md` carries the line `revert-safe: yes` has its pin reverted mechanically when the LAN smoke
is red; anything else is an incident event for the wake.

## Lane exit codes (A7)

`0` PR open with checks green at the reviewed head (`run/result.json`) · `10` hard findings: the
tick runs `lane-opus-fix.sh`, then `pi-lane.sh --integrate <sha>` · `20` needs a decision
(`run/handback.md`) · `30` environment or out of time: resumed, twice at most · `40` tripwire twice,
a failed re-check or two red CI rounds. In the `codex` lane `20` also covers an unknown job-creation
outcome, which is never retried. A 20, a 40, a third stop, a Fable FIX, a red LAN smoke, a
pin not Healthy 40 minutes after its merge and an answered OWNER-QUEUE item become events for one
wake. The wake answers with `<NN>/DECISIONS.md` rows and a `decision-N.md`, and the next tick
relaunches the lane with it. Each lane writes only under its step's `run/`; the tick alone runs
`cm advance`.

## The cm 0.3.1 interface it uses

cm 0.3.1 (dekopon-agents/cm `20d35c3`, its README):

- `cm next --json`: `steps` (`target`, `lane`, `kickoff`) are launched; `tags` (`target`, `repo`,
  `version`, `sha`, `tags`) are the merged release steps waiting for their tag. A step's
  repository is the `repo: <owner/name>` line of its `kickoff.md`, which every non-`fable` step
  carries, release steps included.
- `cm sync` moves pr-open → merged → released → deployed from GitHub and rewrites `CARD.md`, whose
  first line is `Last run: <stamp>`. The tick adds a `Tick: …` second line with its notes
  (`deploys held: off LAN`, refusals).
- `cm launch <step> [--worktree]`, `cm advance <step> <state> [--sha --pr --digest --repo]` and
  `cm journal`. The tick reads `<NN-name>/<unit>/.cm/state.json` only for the PRs of `pr-open`
  steps and a release step's prep PR.
- Every release step is declared with its repository and tag:
  `cm init 00-release/<unit>/<version> --lane <lane> --github <owner/name> --tag '<prefix>{version}'`
  (`--tag` defaults to `v{version}`; without `--github` the prep PR must be in a repository named
  `<unit>`). The tag the tick pushes is the one name `cm next` lists for the step; with more than
  one listed (cm 0.3.0) it refuses.

## Install (owner, at the gate)

Needs on the Mac: `flock` (`brew install flock`), GNU `timeout` (coreutils), `jq`, `gh`, `cm`,
`kubectl` with the `rpi` context, `crane`, `uv`, `pi`, `claude`, and bash from Homebrew (`/bin/bash`
3.2 is not enough). The smoke command lists, one private `<provider>.txt` per provider, go in
`~/.config/campaign/smoke/`; `~/.config/campaign/codex-envs` holds `<owner/repo> <environment-id>`
lines. The ledger's `.gitignore` should carry `**/run/`; until it does, the tick adds it to the
clone's `.git/info/exclude`.

```sh
E=~/code/dekopon/campaign-trail/store/epochs/<epoch>; mkdir -p "$E/run"
sed -e "s#@AGENTS@#$HOME/code/xrl/agents#g" -e "s#@EPOCH_DIR@#$E#g" -e "s#@EPOCH_NAME@#${E##*/}#g" \
    -e "s#@APPROVED_SHA@#<approved sha>#g" -e "s#@HOME@#$HOME#g" \
    ~/code/xrl/agents/skills/campaign/runner/campaign-tick.plist.template \
    > ~/Library/LaunchAgents/com.xrl.campaign-tick.${E##*/}.plist
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.xrl.campaign-tick.${E##*/}.plist
```

`paused = true` in the epoch's `LIMITS.toml` stops it at the next tick;
`launchctl bootout "gui/$(id -u)/com.xrl.campaign-tick.<epoch>"` unloads it.
