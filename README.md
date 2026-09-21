# agents

Opinionated engineering guides. **Start with the task, not a full-library read.**

| Need | Read |
|---|---|
| Agent entrypoint and reading triggers | [AGENTS.md](AGENTS.md) |
| Code/API taste, error handling, testing | [CODE_DESIGN_RULES.md](CODE_DESIGN_RULES.md) |
| Build/release, GitOps, worktree conventions | [LAWS.md](LAWS.md) |
| Current host Rust policy | [RUST_AGENT_RULES.md](RUST_AGENT_RULES.md) |
| Why private targets and copy-on-write | [RUST_WORKTREES.md](RUST_WORKTREES.md) |
| Cache checks and evidence requirements | [RUST_CACHE_VALIDATION.md](RUST_CACHE_VALIDATION.md) |
| Dated experiments and superseded plans | [RUST_CACHE_HISTORY.md](RUST_CACHE_HISTORY.md) |
| Choosing a delegation engine | [orchestration skill](skills/choose-orchestration/SKILL.md) |
| Handing work to a cheap pi driver and supervising it | [pi skills snapshot](skills/PI-SKILLS.md): [pi-subagent-plan](skills/pi-subagent-plan/SKILL.md), [pi-drive](skills/pi-drive/SKILL.md) |

## Loading and installation

These are navigation links, not `@include` directives. The repository `AGENTS.md`
routes relevant reads; it does not concatenate the guides or apply them globally
when working in another repository. kache remains the standard host wrapper.

Claude's global file references `RUST_AGENT_RULES.md`; Pi's global file mirrors
its operational body without expanding Claude-style imports. Keep the canonical
host file and both adapters synchronized when host policy changes.

To install the skill, copy the complete `skills/choose-orchestration/` directory
into `~/.pi/agent/skills/`, reviewing any existing copy first, then run `/reload`.
Invoke `/skill:choose-orchestration` with a task. Selection does not authorize launch.
