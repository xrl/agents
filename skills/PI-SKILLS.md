# campaign, pi-subagent-plan, pi-drive and rust-feature-swarm

Four Claude Code skills. Each `SKILL.md` owns its current routing and execution rules.

- [`campaign`](campaign/SKILL.md) runs one sub-campaign from a folder of state files: a
  Claude coordinator rules and lands, pi sol supervisors watch, a pi `gpt-6-sol` driver builds.
- [`pi-subagent-plan`](pi-subagent-plan/SKILL.md) writes the packet (brief, decisions file, agent
  files, kickoff, rehearsal) that hands decided work to a pi `gpt-6-sol` driver.
- [`pi-drive`](pi-drive/SKILL.md) supervises that driver turn by turn, answering stops from the
  decisions file and escalating only owner actions.
- [`rust-feature-swarm`](rust-feature-swarm/SKILL.md) lands one coupled multi-lane Rust change
  with concurrent lane editors behind a tiered cargo gate.

This directory is canonical: `~/.claude/skills/<name>` is a symlink into it, and edits land here
through a PR. Install with `ln -s ~/code/xrl/agents/skills/<name> ~/.claude/skills/<name>`;
update with `git pull --ff-only` on `main`.

Requirements: the scripts under `pi-drive/scripts/` need `pi` 0.85+, `jq`, `lsof` and `python3`;
`rust-feature-swarm/` needs the Claude Code `Workflow` tool.
