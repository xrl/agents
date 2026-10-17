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
| `lane-opus-fix.sh <step-dir> <worktree> <verify-file>` | the Opus code-only fix of a pi lane's `[hard]` findings |
| `wake-working.md`, `wake-planning.md` | the A3 wake prompts |
| `wake.settings.json` | the wake's allowlist: ledger edits but not `LIMITS.toml`, `run/` or `.cm/`; `git`, `cm` and read-only `gh`; no push, tag, merge or `gh api` |
| `campaign-tick.plist.template` | the launchd job: every 300 s, RunAtLoad, the approved SHA as an argument |
| `lane-lib.sh` | shared helpers |

## What the tick trusts (N1)

- `[authority]` (`LIMITS.toml`) and the `toml` blocks of EXECUTION.md §Gates and §Train, read with
  `git show <approved-sha>:…`. Only `paused` is read live from the working tree.
- Fable verdicts only from `<epoch>/run/verdicts/<owner_repo>-<pr>-<head>`, which only
  `lane-fable.sh` writes. The wake cannot edit `run/`, so a MERGE written into the ledger by hand
  never merges anything.
- Tag versions only from the `tags` that `cm next` lists (release steps `00-release/<unit>/<version>`
  at `merged`), whose prep PR must be merged at that SHA in the §Train repository, with the bump checked against the last tag and `release_bumps`.

A merge needs every required check named for the repository green at the head (none named is red)
and a MERGE verdict at that head, then `gh pr merge --squash --match-head-commit`. A pin PR merges
only when it is pin-only (one file, one line), its required checks are green and
`kubectl --context=rpi get --raw /readyz` answers in the same tick; otherwise it stays open and the
card says `deploys held: off LAN` (N4).

## The blocks EXECUTION.md carries

```toml
# §Gates: the checks a merge requires, by repository (zero named is red)
[required_checks]
"dekopon-agents/dekopon" = ["ci / test", "ci / clippy"]
"xrl/rpi-homelab" = ["render"]
```

```toml
# §Train: one table per release unit, 00-release/<unit>/<version>
[train.dekopon]
repo = "dekopon-agents/dekopon"
tag = "v{version}"
image = "ghcr.io/dekopon-agents/dekopon:{version}"   # crane digest source
pin_file = "apps/dekopon.yaml"                      # in the homelab repo
pin_line = "dekopon-image"                          # ERE matching the one line whose sha256: digest the pin replaces
argo_app = "dekopon"
namespace = "dekopon"
pod_selector = "app.kubernetes.io/name=dekopon"
smoke_agent = "ville-github"

[train.dekopon-chart]                               # D4: tagged on the same prep commit; no pin
repo = "dekopon-agents/dekopon"
tag = "dekopon-chart-{version}"
```

A unit without `pin_file` (a library, a tool, the chart) is done at its tag. A release step whose
`kickoff.md` carries the line `revert-safe: yes` has its pin reverted mechanically when the LAN smoke
is red; anything else is an incident event for the wake.

## Lane exit codes (A7)

`0` PR open with checks green at the reviewed head (`run/result.json`) · `10` hard findings: the
tick runs `lane-opus-fix.sh`, then `pi-lane.sh --integrate <sha>` · `20` needs a decision
(`run/handback.md`) · `30` environment or out of time: resumed, twice at most · `40` tripwire twice,
a failed re-check or two red CI rounds. A 20, a 40, a third stop, a Fable FIX, a red LAN smoke, a
pin not Healthy 40 minutes after its merge and an answered OWNER-QUEUE item become events for one
wake. The wake answers with `<NN>/DECISIONS.md` rows and a `decision-N.md`, and the next tick
relaunches the lane with it. Each lane writes only under its step's `run/`; the tick alone runs
`cm advance`.

## The cm 0.3 interface it uses

cm 0.3.0 (dekopon-agents/cm `3f89bad`, its README):

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
- The tag the tick pushes must be one of the names `cm next` lists (`v<version>`,
  `<repo>-<version>`, `<version>`), so `cm sync` records it.

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
