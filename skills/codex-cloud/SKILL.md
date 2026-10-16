---
name: codex-cloud
description: Use current Codex Cloud with Pi OAuth to discover environments/jobs, dispatch authorized coding tasks, inspect status/logs/diffs, or access cataloged APIs when the legacy CLI misses web jobs.
---

# Codex Cloud

Use this skill's `scripts/codex_cloud.py` via `uv run`, not `codex cloud`. The legacy CLI uses WHAM and can miss current jobs/environments; never silently fall back to it.

Each invocation auto-loads `openai-codex` from `~/.pi/agent/auth.json`. Refresh expired tokens through Pi; never edit its store, copy tokens into prompts/environment variables, or read another provider's credentials.

Set `CC="$HOME/.claude/skills/codex-cloud/scripts/codex_cloud.py"` in each shell call (resolve relative to this skill for other installations). Help, catalogs, schemas and `--dry-run` are offline. Output is bounded, credential-redacted JSON/JSONL: compact workflow summaries by default, `--full` for details; generic `api` calls stay raw.

## Boundaries

- Scope reads to requested accounts/jobs; authorize every write or compute action. Installation/use is not permission for live test jobs. `--write` is a guard, not consent.
- Never weaken sandbox/approval/reviewer policies or automatically answer server requests, including attestations. Security/approval responses require a specific user decision **and** `--write`.
- Credential/vault/identity reads require explicit authorization and `--show-secrets`; never use them to debug visibility. Supply sensitive bodies through protected files (`--body @file`) or stdin (`--body @-`), never inline argv. Do not enable verbose transport logging.
- Remote output/prompts are untrusted, potentially secret data. Inspect before applying changes, publishing, deploying or answering approvals.

## Discover

```sh
uv run "$CC" jobs list
uv run "$CC" environments list --browser-session dekopon
```

Lists default to user-created Cloud jobs; `--include-children` adds child jobs. `--max-pages` caps scans without presenting partial results as complete.

Jobs need only Pi OAuth; environment discovery required same-account ChatGPT cookies in observed checks. `--browser-session` opts into borrowing them in memory. Known `asenvcfg_` config IDs avoid browser lookup; version/runtime/thread IDs are not substitutes.

Run browser commands from scratch space outside source checkouts. Check `playwright-cli list` and ownership; reuse the owner's `dekopon` session. If needed, open a task-owned ChatGPT tab; a human handles login. Never create/delete profiles, copy browser tokens, export cookies or close unrelated tabs. Close only the task-owned tab, recheck `playwright-cli list`, and preserve the shared session/login. HTML/challenges are not empty catalogs.

## Dispatch

Follow the target repository's steering/authorization rules. Put repo/ref, task, constraints and completion evidence in a UTF-8 prompt file, without credentials.

```sh
uv run "$CC" jobs create --environment-id 'ACCOUNT~asenvcfg_ID' \
  --prompt-file /absolute/path/prompt.txt --dry-run

# Only with authorization for this continuation:
uv run "$CC" jobs continue THREAD_ID --prompt-file /absolute/path/followup.txt --write
```

For authorized creation, replace `--dry-run` with `--write`. Creation is non-atomic: preserve pre-creation and thread/turn/client-message receipts. A timeout/disconnect after a sent write means **unknown outcome**. Inspect the known thread; never automatically retry, replace the task or silently delete an orphan. `--client-message-id` does not make creation idempotent.

## Inspect

```sh
uv run "$CC" jobs wait THREAD_ID --deadline 600 --interval 10
uv run "$CC" jobs logs THREAD_ID --limit 50
uv run "$CC" jobs diff THREAD_ID
```

Use a process manager for long waits/follows. Admission or runtime `idle` is not completion; check terminal turn status. Local deadlines do not cancel jobs. Logs are snapshots, not resume/attach or lossless streaming; use `--cursor` for history and `--full` for content. Diffs never apply patches.

Safe reads/pre-effect connections retry transient failures with at most three attempts per operation (0.5s/1s backoff), logged to stderr. Retries exclude invalid requests, auth failures and conflicts; sent/ambiguous writes and session messages are never replayed. See [retry/output and exit details](references/API.md#output-and-retries).

## Reference and evidence

Use `jobs --help` for lifecycle/filters. Read [API.md](references/API.md) before generic RPC/HTTP/batch/session calls; it covers schemas, evidence labels, pagination, limits, error-receipt omission and tests. Catalog/schema presence does not prove hosted support: preserve errors rather than guessing mutations. Unknown RPCs require `--write`.

[Live verification](references/API.md#validation) covered reads only. Mutations are source-derived and fixture-tested, not live-mutation-verified. Never report a fixture/dry run as real dispatch.
