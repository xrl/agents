# pi-subagent-plan, pi-drive and rust-feature-swarm: snapshot of 2026-09-28

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
