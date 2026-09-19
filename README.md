# agents

Opinionated workflow and environment guides for human-and-agent development.

- [Laws of Software](LAWS.md) — concise rules with receipts.
- [Concurrent Rust worktrees without N× disk](RUST_WORKTREES.md) — Cargo lock boundaries, why shared build dirs serve wrong code, historical sccache measurements, APFS reflinks, standard kache adoption, and cleanup policy.
- [Rust agent rules](RUST_AGENT_RULES.md) — canonical current host policy: kache, private targets, safe cleanup, and outstanding validation gates.

## Pi skills

- [Choose an orchestration engine](skills/choose-orchestration/SKILL.md) — decide between direct execution, pi-subagents, and Dynamic Workflows using a reusable decision matrix and launch guardrails.

To install, copy `skills/choose-orchestration/` into `~/.pi/agent/skills/` (review any existing copy before replacing it), then run `/reload` in Pi. Invoke `/skill:choose-orchestration` with a task to get a routing recommendation; invoking the skill alone does not launch agents.
