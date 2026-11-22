# agents

Opinionated engineering guides. **Start with the task, not a full-library read.**

| Need | Read |
|---|---|
| Agent entrypoint and reading triggers | [AGENTS.md](AGENTS.md) |
| Code/API taste, error handling, testing | [CODE_DESIGN_RULES.md](CODE_DESIGN_RULES.md) |
| Build/release, GitOps, worktree conventions, multi-PR and multi-agent campaigns | [LAWS.md](LAWS.md) |
| Current host Rust policy | [RUST_AGENT_RULES.md](RUST_AGENT_RULES.md) |
| Steering for GPT executors, read by URL at a pinned SHA | [steering/GPT.md](steering/GPT.md) |
| Why private targets and copy-on-write | [RUST_WORKTREES.md](RUST_WORKTREES.md) |
| Cache checks and evidence requirements | [RUST_CACHE_VALIDATION.md](RUST_CACHE_VALIDATION.md) |
| Dated experiments and superseded plans | [RUST_CACHE_HISTORY.md](RUST_CACHE_HISTORY.md) |
| Handing work to a GPT executor | official Codex: `codex exec` locally, Codex Cloud for cloud tasks; prompts open with [steering/GPT.md](steering/GPT.md) |
| Current Codex Cloud jobs, environments, logs and API access using the official Codex login | [codex-cloud](skills/codex-cloud/SKILL.md) |
| Landing one coupled multi-lane Rust change with a swarm | [rust-feature-swarm](skills/rust-feature-swarm/SKILL.md) |
| Standing up and proving a change on an rx `run-in-k3` PR site (prod clone) | [rx-pr-site](skills/rx-pr-site/SKILL.md) |

## Loading and installation

These are navigation links, not `@include` directives. The repository `AGENTS.md`
routes relevant reads; it does not concatenate the guides or apply them globally
when working in another repository. kache remains the standard host wrapper.

Claude's global file imports `RUST_AGENT_RULES.md`; Codex's global `AGENTS.md` points at it. There
is one copy.

The Claude Code skills (`skills/rust-feature-swarm/`, `skills/rx-pr-site/`) install
as symlinks, `ln -s ~/code/xrl/agents/skills/<name> ~/.claude/skills/<name>`, and update with
`git pull --ff-only` on `main`.
The self-contained `skills/codex-cloud/` skill can instead be copied in full to
`~/.claude/skills/codex-cloud/`; it needs `uv` and, only for web-session-assisted HTTP calls,
an existing signed-in `playwright-cli` session. Its API catalog is pinned, not auto-updated.
