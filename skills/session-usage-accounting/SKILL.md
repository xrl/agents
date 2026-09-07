---
name: session-usage-accounting
description: Reconstruct attributable recorded token usage and local USD estimates for one Pi root session, including workflow and native children. Use for whole-session cost audits, snapshot reconciliation, or explaining cache and replay accounting. Not for provider billing access, quota conversion, project-wide surveillance, or controlling active work.
compatibility: Python 3 standard library and authorized local Pi accounting records. Verify installed session and orchestration meter semantics before adapting collectors.
---

# Session usage accounting

Produce a **recorded snapshot**, not an invoice. Stay direct and read-only. Reuse an existing
completed audit and its sanitized projections when they answer the question; do not rescan merely
to explain its result. Resolve all relative paths below against this skill directory.

## 1. Bound identity and time before collecting

- Establish the requested root from its session header, not a summary, cwd, date, or filename alone.
  Follow `parentSession` links when present; stop on missing, cyclic, or ambiguous ancestry. Do not
  automatically include sibling forks. State which continuations/descendants are attributable.
- Fix a UTC cutoff and explicit source inventory. Stream JSONL only to a captured byte boundary;
  hash those exact bytes, record last included timestamp, size and source identity. Report partial
  final lines. For mutable run/status JSON, capture bytes once, record hash, mtime and `updatedAt`,
  reject post-cutoff or changing snapshots. Non-atomic reads must be labeled as such. A timestamp
  filter cannot recover an older cumulative meter from a newer file.
- Project only accounting metadata: IDs, causal links, timestamps, lifecycle, model/provider when
  recorded, usage and hashes. Inspect field shapes before values. Never load transcripts into the
  caller's context; keep detailed ledgers in a new owner-only, create-only evidence directory.
- Identify this audit's own run/child and exclude it from the primary total or report it separately.
  Its final meter may not exist yet. Parent preparation/launch turns remain parent usage; if the
  final audit charge is later added, add it once under a clearly later cutoff.

## 2. Build causal links, then choose non-overlapping authorities

| Layer | Attribution | Meter to count |
| --- | --- | --- |
| Parent | Verified root/continuation header and source | Unique top-level assistant `message.usage`, plus explicit compaction/branch-summary `usage` |
| Dynamic Workflow | Actual launching parent `workflow` call → paired tool result `details.runId` → matching run `sessionId`; verify project namespace | One committed run `tokenUsage`; substitute unique per-`callId` meters only if their sum reconciles in every category and cost |
| Separate native child | Parent launch/tool-call ID → durable orchestration status/receipt → child inventory/backlink → exact child session | Unique child Pi usage entries; status totals, model attempts and orchestration totals are cross-checks only |

Prose mentions, status/list calls, script text, project membership and result displays are **not
launch evidence**. Follow only proven links, including further descendants if any. Report incomplete
child inventories. Do not sum a native child again if a workflow meter already covers it.
Check parent/child tool-result usage for nested LLM work: it can be a real meter, but may mirror a
child meter already selected. Resolve ownership before adding; absence of overlap in one audit is
not a universal promise. Stop the affected subtotal if meter ownership is ambiguous.

## 3. Deduplicate executions, not amounts

- Count historical recorded calls across the session tree, not just current post-compaction context.
  A summary, `tokensBefore`, copied `retainedTail`, backup, artifact transcript, JSON/CSV twin, or UI
  aggregate is not another charge. Explicit summary-generation usage is a separate charge.
- Check provider-scoped response IDs and source-scoped entry IDs. Deduplicate verified copies;
  conflicting usage for the same identity is a reconciliation failure. Fingerprints corroborate
  copies, but equal text or token amounts alone cannot prove two requests are the same.
- Count each returned run once and each logical call once. Cumulative progress snapshots are not
  increments. Replayed completed prefixes/journal callbacks are not new executions. A genuinely
  rerun attempt costs money even when it repeats text or fails acceptance.
- The inspected workflow implementation commits finalized attempt deltas, accumulates retries in
  logical calls, subtracts reused-session baselines and does not commit journal replay again.
  Verify these semantics for the runtime being audited; current source is not proof of all older
  runtimes. Do not manually subtract retries/replay from a committed meter a second time.

## 4. Normalize and reconcile

Read [the meter reference](references/meters.md) before adapting a source. Normalize uncached
`input`, `output`, `cacheRead`, `cacheWrite`; sum these four once. Reasoning is a subset of output
in the verified format. Never assume every provider's raw input or native `total` has this meaning.
Use recorded costs with decimal arithmetic, not today's catalog rates. Report tokens separately
from **local USD estimates**, actual credits, subscription quotas and invoices (unknown without an
authorized independent meter/conversion).

The optional [stdlib helper](scripts/accounting.py) provides bounded JSONL reading, top-level meter
selection, strict normalization, identity deduplication and workflow reconciliation. It is a small
**library**, not a live discovery tool or turnkey audit: a task-scoped collector must prove causal
links, select sources, sanitize outputs and record coverage. See its docstrings and the reference.
Validate changes without production logs:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s "$SKILL_DIR/tests" -v
```

Set `SKILL_DIR` to this skill's resolved directory. Save sanitized projections and parser identity
so arithmetic can be replayed offline in a different new directory. Independently cross-check
category sums, component costs where present, workflow aggregate/per-call reconciliation and
completed + observed-active subtotals. Never add aggregate and detail ledgers together.

## 5. Report a small, qualified answer

Return root and cutoff, non-overlapping category totals, normalized token definitions, completed
versus observed-active spend, metered/logical counts (not API-request counts), exclusions, gaps and
reproduction paths. A running child without usage is **unmetered**, not free; explicit recorded zero
is distinct from missing. Failed/unreported work may have provider charges invisible locally.
Report missing compactions, provider-response inventory gaps, model labels and ambiguous meters
as unknown. No exact whole-session or provider completeness claim while material gaps remain.

**Safety:** no raw transcript, task, code, reasoning-text or credential dumps (including errors);
no billing login, network scraping, secret configuration, global log sweep, waits for completion,
launches/resumes, steering, cancellation, production source/worktree/target changes or cleanup.
If required evidence is unavailable, return the bounded known subtotal and exact gap, not an
invented zero, price, exchange rate, or a replacement investigation.
