# Working in xrl/agents

**Read the guide for the task, not the whole library.** Links are navigation,
not automatic imports. If a required guide is unavailable, stop that action.

## Read before acting

| Task | Guide |
|---|---|
| Code or API design/review | [CODE_DESIGN_RULES.md](CODE_DESIGN_RULES.md) |
| Builds, releases, GitOps, worktree conventions | [LAWS.md](LAWS.md) |
| Host Cargo, compiler cache, target cleanup | [RUST_AGENT_RULES.md](RUST_AGENT_RULES.md) |
| Cache diagnosis, upgrades, verification | Host rules, then [RUST_CACHE_VALIDATION.md](RUST_CACHE_VALIDATION.md) |
| Worktree/cache architecture | [RUST_WORKTREES.md](RUST_WORKTREES.md) |
| Measurements or past rollout decisions | [RUST_CACHE_HISTORY.md](RUST_CACHE_HISTORY.md) |
| Choosing delegation | [orchestration skill](skills/choose-orchestration/SKILL.md) |
| Offloading decided work to pi, driving it from Claude | [pi skills snapshot](skills/PI-SKILLS.md) |

## Authority and upkeep

- kache is standard. Current host rules outrank historical recipes.
- Docs do not authorize builds, deployment, delegation, or configuration changes.
- Preserve safety constraints, named exceptions, rule IDs, and receipt dates.
- Edit canonical policy, not a local mirror. Host-rule edits require synchronized
  adapters; moving other documents does not authorize global instruction changes.
- Keep history out of operational guides. Link to evidence instead of repeating it.
- Validate local links/anchors and `git diff --check`; report checks actually run.
