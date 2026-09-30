# pi-subagent-plan, pi-drive, campaign and rust-feature-swarm: snapshot of 2026-09-30

Three Claude Code skills. `pi-subagent-plan` authors the packet (brief, decisions file, agent
files, kickoff, rehearsal) that hands decided work to a cheap pi driver
(`openai-codex/gpt-6-astra`); `pi-drive` runs it turn by turn from Claude Code, answering stops
from the decisions file and escalating only owner actions; `rust-feature-swarm` lands one coupled
multi-lane Rust change with concurrent lane editors behind a tiered cargo gate. Canonical copies
live in `~/.claude/skills/`; this directory is the durable record of where they stood.

Install by copying the skill directories into `~/.claude/skills/`. The scripts under
`pi-drive/scripts/` need `pi` 0.85+, `jq`, `lsof` and `python3`; `rust-feature-swarm/` needs the
Claude Code `Workflow` tool.

All three were refreshed from the canonical copies on 2026-09-28 after a multi-PR deletion
campaign. What that campaign added, generalized ([LAWS.md](../LAWS.md) §42–45 carry the receipts):
a shared file every PR edits is a chokepoint, not work; the split that works is cheap driver and
cheap verifier per stage plus one expensive fresh reviewer per PR, with the coordinator ruling on
each finding before routing it; a numeric target needs a per-unit expectation and a precise unit;
verifiers grep a deletion's distinctive literals before accepting a named survivor; and every
supervisor ruling lands in the decisions file as a numbered `D<n>` before the prompt that relies
on it. `pi-subagent-plan/templates/DRIVER.md` (the sequential-driver brief) is new since the
2026-09-20 snapshot.

`pi-drive` and `pi-subagent-plan` were refreshed again on 2026-09-29 ([LAWS.md](../LAWS.md)
§50–51): every "poll it with short sleeps" became one blocking wait, because a blocked call is
free and a poll is a full read of the driver's context; `pi-check.sh` takes the worktree and
prints commit age, tool calls since the last edit and the most repeated command, because a
running build is not progress; the watch loop reads its disk floor and tripwires from the
effort's `LIMITS.toml`. `rust-feature-swarm` is unchanged from 2026-09-28.

## What the 2026-09-20 run proved

One day: v0.18.0 core release with zero stops (1 h 25 m), the site, fifteen provider releases
including a new repo, and the Pi rollout PR. Both pi skills were edited that evening from the
retro (the `Retro` section in `pi-drive/SKILL.md`, cost rules 8–10 and the new traps in
`pi-subagent-plan/SKILL.md`). The three load-bearing findings:

- A print-mode pi turn ends the moment the driver stops generating, orphaning any async child
  or background gate; every stage prompt now forbids ending the turn while one runs, and a
  mid-stage end is relaunched at once. Launch turns with the harness background runner, never
  `nohup`, so the exit wakes the supervisor.
- Many independent repositories are many driver sessions from one brief template, not one
  driver with a workflow-script fan-out.
- Stops are owner actions and contract surfaces only; a pattern-matched stop clause ("names
  kache") parks a literal driver on ordinary compile diagnostics.

`campaign` is new on 2026-09-30, and `pi-drive` and `pi-subagent-plan` were refreshed the same
day, from Dekopon sub-campaign 4 (v0.29.0, ≈ 9,400 lines in 13 steps, ≈ $154, 51% pi). `campaign`
runs one funded sub-campaign from a folder of state files: a Claude coordinator that rules and
lands, pi sol supervisors that watch, a gpt-6-sol driver, a fresh verifier per commit, one Astra
cross-step review and one Fable read, with the owner's standing orders (a tripwire inside budget is
a report; ask foreseeable decisions early). The refresh: the driver is `gpt-6-sol` at `medium`;
sol supervisors watch code units too (zero decisions of their own across A2-A13); dry runs are sol
only and the one-voice rewrite is no longer a Fable job; a spine step goes to one Opus agent (the
blind A2 judging) and a second review round to an Opus fix agent; a `-ne` driver's verifier runs
outside it through `pi-dry-run.sh`.
