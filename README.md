# agents

Opinionated workflow and environment guides for human-and-agent development.

- [Laws of Software](LAWS.md) — concise rules with receipts.
- [Concurrent Rust worktrees without N× disk](RUST_WORKTREES.md) — Cargo lock boundaries, sccache, APFS reflinks, the kache pilot, and cleanup policy.

## Pi skills

- [Choose an orchestration engine](skills/choose-orchestration/SKILL.md) — decide between direct execution, pi-subagents, and Dynamic Workflows using a reusable decision matrix and launch guardrails.

To install, copy `skills/choose-orchestration/` into `~/.pi/agent/skills/` (review any existing copy before replacing it), then run `/reload` in Pi. Invoke `/skill:choose-orchestration` with a task to get a routing recommendation; invoking the skill alone does not launch agents.
