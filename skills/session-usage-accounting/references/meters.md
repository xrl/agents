# Meter contract and helper boundary

## Verified evidence, not a universal provider adapter

The completed September 2026 accounting audit reconciled parent Pi JSONL, returned Dynamic
Workflow run snapshots and a separately linked native child. Its recorded estimate was
**$389.948832 at its cutoff**, excluding the audit child, with an active unmetered child and
incomplete workflow provider-response coverage. This is an example, never a default budget,
price table or claim of actual credits. No snapshot ledgers or private source paths ship here.

The audit checked these installed semantic references (locate the actual installed packages;
versions and layouts can change):

- Pi `docs/session-format.md`: session tree, `parentSession`, top-level summary-generation usage,
  retained context versus historical entries, optional nested tool-result usage.
- Pi `dist/core/agent-session.js`, `getSessionStats`: recorded session statistics including
  explicit compactions/nested-tool usage, not just currently retained context.
- pi-ai `dist/api/openai-responses-shared.js`, `finalizeResponse`: provider input includes cached
  tokens; stored Pi `input` subtracts cache reads/writes. Output includes reasoning. **Do not
  apply that subtraction again to stored Pi usage or assume other raw provider formats match.**
- pi-ai `dist/models.js`, `calculateCost`: category tokens times local model-catalog rates,
  possibly tiers; stored dollars are estimates, not account balance reads.
- Dynamic Workflows `src/agent-usage.ts`, `agent.ts`, `workflow.ts`, `workflow-manager.ts`,
  `run-persistence.ts`: finalized deltas, cumulative logical calls/retries, reused-session
  baseline subtraction and zero-token replay callbacks. `workflow-paths.ts`/`workflow-settings.ts`
  establish project namespace resolution. The audit verified one cwd-derived hash namespace;
  do not guess project keys or scan linked projects indiscriminately.

All audited run aggregates reconciled with unique call totals; therefore the detailed call ledger
could replace them. No duplicate/replayed message charges actually occurred in that snapshot.
Replay and retry semantics were source-corroborated, not a historical replay experiment. Synthetic
helper tests establish rejection/dedup behavior, not a forensic guarantee for production histories.

## Arithmetic

`normalizedTotal = input + output + cacheRead + cacheWrite` with nonnegative integer categories.
`reasoning <= output` when present; never add reasoning again. Pi `totalTokens` and workflow
`total` matched normalized totals in the audit. The inspected native status `total` instead meant
`input + output`, omitting cache categories: reconcile against child Pi entries, do not add the
status difference as spend. Unknown total semantics require inspection, not a guessed conversion.

Preserve recorded USD (`usage.cost.total` or workflow `tokenUsage.cost`). Where recorded cost
components exist, reconcile their sum too. Workflow scalar costs do not justify a fabricated
category-dollar breakdown. Decimal arithmetic prevents further binary-float accumulation; an
explicit absolute `1e-8` USD tolerance handles representation noise seen in the audit. Retain original
values and disclose tolerance; material differences fail. No repricing or quantization is needed.

## Library use

Import `scripts/accounting.py` from a task-scoped, reviewed collector; there is no command that
scans home directories or calculates an entire session automatically.

- `bounded_jsonl(path, byte_limit, sha256)` streams only the specified bytes, validates complete
  JSON-object lines and the expected digest. Fully exhaust it **before publishing any result**;
  hashing cannot validate bytes not yet consumed. A partial final line or changed prefix fails.
  It yields raw objects internally: immediately allowlist-project them; never print/store them.
  The caller establishes byte limit, cutoff, header/ancestry, file metadata and expected hash.
- `entry_meters(entry)` selects only top-level assistant, compaction and branch-summary usage;
  a missing selected meter yields `None`. It ignores copied retained tails. Nested tool-result
  usage raises an ownership error so it cannot silently disappear or be double-counted. The
  caller must inspect unknown entry types and decide whether a separate meter exists.
- `normalize(usage)` accepts only the verified **stored Pi/workflow** categories, not raw provider
  responses or native status summaries. It requires all four categories, cost, and one explicit
  total (`totalTokens`/`total`). Missing usage is an error, never a zero. Recorded zero is valid.
- `UniqueMeters.add(keys, meter)` returns false for a verified repeated identity, raises on
  conflicting/bridging identities. Keys are tuples such as `('response', provider, responseId)`
  and `('entry', canonicalSource, entryId)`; never use a missing ID or a bare content fingerprint.
  Canonicalize known mirror paths first. Without stable identity, report duplicate coverage
  unknown rather than claiming automatic deduplication. Fingerprint matching needs independent
  copy/lineage evidence outside this helper.
- `workflow(root_id, launch, run, cutoff)` checks projected launching identity and matching
  session/run IDs, pre-cutoff `updatedAt`, unique `callId`s and aggregate/detail arithmetic.
  `launch` has `toolName`, `toolCallId`, `runId`, extracted **only from an actual launch and its
  paired result** (not status/list/prose). Caller proves that pairing and project namespace.
  Returns the authoritative aggregate once, plus IDs lacking meters. Missing call contributions
  are omitted only for reconciliation; their costs remain unknown even if an aggregate matches.
  Duplicate calls, changed cumulative snapshots and missing aggregates fail. Deduplicate run
  snapshots upstream by identity, selecting one cutoff-valid version, never summing versions.

These helpers deliberately do not infer native inventories, nested-meter ownership, ancestry,
self-audit exclusions, source adapter versions or billing truth. Those are evidence gates in
[the skill](../SKILL.md). If a gate fails, retain a labeled partial report rather than blessing a
whole-session total. Save only allowlisted projections and compact diagnostics in create-only,
owner-only outputs; parser exceptions must never echo the offending raw line.
