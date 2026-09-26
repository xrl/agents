# pi-subagent-plan and pi-drive: snapshot of 2026-09-20

Two Claude Code skills that pair a high-level Claude supervisor (fable) with a cheap pi driver
(`openai-codex/gpt-6-astra`). `pi-subagent-plan` authors the packet (brief, decisions file,
agent files, kickoff, rehearsal); `pi-drive` runs it turn by turn from Claude Code, answering
stops from the decisions file and escalating only owner actions. Canonical copies live in
`~/.claude/skills/`; this directory is the durable record of where they stood after the
Dekopon 0.18.0 release drive.

Install by copying `skills/pi-subagent-plan/` and `skills/pi-drive/` into `~/.claude/skills/`.
The scripts under `pi-drive/scripts/` need `pi` 0.85+, `jq`, `lsof` and `python3`.

`pi-drive/` was refreshed from the canonical copy on 2026-09-26. It adds `scripts/pi-usage.sh`
(per-worktree cost accounting that includes pi-subagents children), `scripts/pi-stage-check.sh`,
`scripts/pi-fill-prompt.sh`, `templates/STAGE-PROMPTS.md`, prompt-by-file turns and the provider
outage signatures. `pi-subagent-plan/` is still the 2026-09-20 snapshot.

## What the 2026-09-20 run proved

One day: v0.18.0 core release with zero stops (1 h 25 m), the site, fifteen provider releases
including a new repo, and the Pi rollout PR. Both skills were edited that evening from the retro
(the `Retro` section in `pi-drive/SKILL.md`, cost rules 8–10 and the new traps in
`pi-subagent-plan/SKILL.md`). The three load-bearing findings:

- A print-mode pi turn ends the moment the driver stops generating, orphaning any async child
  or background gate; every stage prompt now forbids ending the turn while one runs, and a
  mid-stage end is relaunched at once. Launch turns with the harness background runner, never
  `nohup`, so the exit wakes the supervisor.
- Many independent repositories are many driver sessions from one brief template, not one
  driver with a workflow-script fan-out.
- Stops are owner actions and contract surfaces only; a pattern-matched stop clause ("names
  kache") parks a literal driver on ordinary compile diagnostics.
