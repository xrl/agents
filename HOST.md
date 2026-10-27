For local hosts only; cloud agents do not read this file.

# Local host rules

Rules for a developer machine, not a cloud container. Rust compiler cache, targets and disk:
[RUST_AGENT_RULES.md](RUST_AGENT_RULES.md). Worktree law: [LAWS.md](LAWS.md) §31.

## Secrets and unattended runs

- 1Password: count the `op` calls first and serve from disk where you can. Use one `op inject` into 0600 files in a 0700 directory, a shim for tools that need it, one approval, and clean up afterwards.
- Unattended runs never call `op`. Supervisors that run unattended do not have it.
- Local `chatgpt-auth.json` files are stale seeds. Never refresh them by hand.

## Checkouts and worktrees

- Primary checkouts stay on `main` under `~/code`. Preserve dirty work, and report a default branch that is not `main`.
- Substantive work goes in a dedicated worktree on its own branch. Both layouts are allowed (LAWS §31): `<repo>/.worktrees/<name>` or the sibling `<repo>.wt/<name>`. Claude's hidden `.claude/worktrees/` is not.
- Move pre-existing dirty work into the worktree. Never reset it.
- Fetch and fast-forward an unfamiliar open-source clone before diagnosing it.
- The dekopon main-pin guard fires after checkout only. Recover a stranded change with `write-tree` / `commit-tree`.

## Browsers and scratch

- Headed Playwright: use named sessions, make cleanup part of completion, never run `close-all`, and keep artifacts in scratch.
- Never stage files at `/tmp/claude-501/<name>`. Use the session scratchpad.

## Owner-controlled actions

- A full rebuild of the owner's tools (the vagus reindex) needs the owner's say-so.
- The auto-mode classifier refuses destructive git, admin merges and writes to `~/.claude/skills`. Work around the first by creating a new worktree and branch; ask the owner for the others.

## Disk and reporting

- Disk numbers (`df`, store and target sizes) go to the coordinator's journal, never a PR body (steering/GPT.md). RUST_AGENT_RULES asks for them for the owner and coordinator, not for reviewers.
