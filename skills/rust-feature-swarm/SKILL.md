---
name: rust-feature-swarm
description: Land a multi-part Rust change that must ship as ONE coupled PR (a review's findings on a branch, a feature split into lanes, a refactor with several interdependent units) with a swarm of concurrent opus lane editors that stay in their lanes and never run cargo, a coordinator gate tiered cargo check → lint → test → full-CI that routes verbatim failures back to the lane whose change caused them, adversarial acceptance verifiers, then a single fable review, per-lane commits, and a push. Use when Xavier asks for a "swarm", "agent swarm", "fan out agents to land X", "lane editors", "reconciler loop", or many concurrent implementers without a bunch of agents running cargo. Not for a one-file change (one agent), not for review-only work (/code-review), and not for a list of INDEPENDENT findings — those are 4–7× cheaper per finding as one worktree + one PR each (the Aug 2026 burndown pattern).
argument-hint: "[what to land: PR review comment URL, issue, or brief path] [worktree]"
arguments: [target]
disable-model-invocation: false
user-invocable: true
---

# Rust feature agent swarm

Xavier's strategy, verbatim: *lots of concurrent editors trying to stay in their lane; they
throw their hands up if they need something out of their lane → a reconciler runs a quick
`cargo check` and kicks off another fleet of concurrent editors scoped to the new failures →
another reconcile → until done → run the tests → back to the reconciler loop → a fable review of
all the changes → PR.*

This skill is that loop plus what its first run taught (dekopon PR #197 review fixes,
2026-09-09/10: two Workflow runs of 12 and 19 agents, then a 7-minute full lane set and the push;
retrospective reports in that session's scratchpad, `retro-execution.md`, `retro-guardrails.md`,
`retro-x-feature.md`). Read §0 before choosing this shape.

## 0. When the swarm pays, measured

First run, ten findings in four lanes: 183 min end to end, 250 agent-minutes, 31 agents,
~3.6M subagent tokens; 25 agent-min and 18 wall-min per finding. The August per-PR pipeline
(one opus agent per finding, own worktree, own PR, two at a time) cost 6 agent-min and ~3
wall-min per finding. The swarm is the right shape only when the findings are coupled enough
that they must land together (shared predicates, one changelog, one branch under review).
Where it lost time, in order: routing artifacts (8 of 12 fix agents, 42 agent-min, 25% of
wall), a 17-minute test hang, one gate round that did clippy and the full scoped test run
together (27 min), and a verifier nit that cost 20 min. Each has a rule below.

The fan-in itself (one cargo run instead of four) saved only 6–13 min of compile. Its real cost
was latency: a lane that tightens a shared predicate cannot see the fallout until the next
gate. Make discovery cheap (a check tier over reverse dependents runs in about a minute)
rather than let lanes run cargo.

## 1. Before launching (fable, in the main session)

1. **Worktree.** Never the main checkout. One worktree for the whole swarm (`git worktree add
   ../.worktrees/<name> -b <branch> <base-sha>` from the repo root; dekopon:
   `~/code/dekopon/.worktrees/`); every lane edits the same tree. `cd` into it before launching
   so agents inherit it, and still put the absolute path in every prompt.
2. **Scout with Explore agents, decide everything up front.** Line-cited briefs per lane; every
   design choice stated as a decision. Check every literal you put in a brief against the tree:
   one wrong probe name copied from the plan into a chart message survived two verify rounds.
   A wire-format, WIT or config-key change also fixes the ship order: enumerate every consumer
   at its *deployed* version, verify each against the real artifact, write the order into the
   PR (dekopon `AGENTS.md` §Releases across repos and GitOps).
3. **Acceptance lines.** One sentence per item, keyed `S1…`, checkable against the tree. These
   ids are the only ones verifiers may use.
4. **Ownership table** — this table IS the router, written as code, not prose:
   - `author`: prefixes the lane creates its change in. Disjoint across lanes.
   - `blast`: prefixes the lane's change can BREAK and may therefore edit for repair (test
     fixtures, consumers of a tightened API, integration tests, charts that render its config).
     Not disjoint; first match wins in lane order. Find consumers with
     `cargo tree -i -p <crate> --workspace --prefix none --edges normal | sort -u`.
   - `forbid`: paths inside a prefix the lane must not touch (e.g. `Chart.yaml`).
   Repair ownership follows the causing change. A path no lane may edit is a routing bug you
   pay for in fix rounds; the template widens the requesting lane rather than bouncing.
5. **Shared files.** A file every lane needs is a chokepoint, not work. Where the repo takes
   the edit at release time instead (`Changelog:` commit-message lines; dekopon `AGENTS.md`
   §Large multi-agent runs), pass `changelog: null` and no lane touches it. Otherwise one writer
   lane; the others return bullets and a single-writer step inserts them. Never bullet
   branch-local churn (a script added and deleted on the same branch drew a residue-grep failure).
6. **Gate commands, tiered** (§3), and **fixtures first** (dekopon:
   `ci/fetch-external-provider-components.sh examples/providers` as the first `test` command;
   `echo-provider.wasm` is gitignored and a scoped unit test needs it). Refetch after any
   fixture bump: a red gate that CI passes is a stale fixture, not a bug.

## 2. Lanes (what the editors get)

The template injects the rules; the load-bearing parts:

- Edit only your editable prefixes (author + blast). Out of lane → `items[].blocked_on_path`
  with the exact change. **Never name a lane.** Both runs stalled on an agent-named owner
  (A guessed B; later D guessed A); the router maps the path, in code.
- Never run cargo/rustc/clippy/tests. Allowed cheap checks per lane only: `rustfmt --edition
  2024 --check <own file>`, sub-second python unittest scripts, `helm template`, `actionlint`.
- Never git add/commit/stash/checkout. Undo = `git show HEAD:<path> > <path>`.
- Other lanes edit the same tree concurrently: never report their work missing; the gate is
  the only judge of the tree (a lane read the chart before another lane wrote it and burned a
  fix round on a false "missing" claim).
- Return the typed object: `files_touched`, `items[{id, done, summary, acceptance_evidence,
  blocked_on_path?}]`, `changelog_bullets`. The script checks ownership and item coverage
  BEFORE any gate runs; those bounce as bookkeeping rounds that do not count against the
  repair cap. (A `ran_cargo` attestation fired zero times in 31 transcripts and is gone.)

Model: opus for editors, fix agents, and verifiers (at most two, §4); sonnet for the shared-file
writer and the in-script gate. Fresh fix agents per round, handed the brief + previous return +
their own `git diff` + verbatim failures; transcript continuity was not needed and was not missed.

## 3. Reconciler: the tiered gate

Cheap tiers first, so a compile-class failure costs a two-minute round, not a 27-minute one.
Any fix restarts at tier 0. Every tier runs the repo's CI commands in CI's order (dekopon:
`.github/workflows/ci.yml`), scoped with `-p` until `full`.

```
check:  cargo check -p <touched pkgs + reverse deps> --all-targets --all-features --locked
lint:   cargo fmt --all --check
        cargo clippy -p <same> --all-targets --all-features --locked -- -D warnings
        cargo machete
        RUSTDOCFLAGS="-D warnings" cargo doc -p <same> --all-features --no-deps --locked
test:   <fixture fetch>
        cargo test -p <same> --all-features --locked --no-run
        cargo test -p <same> --all-features --locked
        cargo test -p <same> --all-features --locked --doc
        <python gate scripts, helm lint/template incl. negative renders, actionlint, residue grep>
full:   the repo's complete local definition of done (dekopon: docs/development.md
        #root-workspace verbatim + provider example workspaces + python gates + release-metadata
        + docs gates + chart job with kubeconform + wit-package.yml component rebuilds when
        guest-linked crates change), skipping only lanes untouched by the change
```

**Who runs it.** Default: the coordinator, in Bash, in the main session — the script has no
shell, so an in-script gate is a sonnet agent that costs minutes of reasoning and millions of
cache-read tokens per round to relay output. Run the tier yourself, route the failures with the
same prefix table, and invoke the template in `mode: 'fix'` with `messagesByLane` and the last
call's `summaries` for the fleet; `mode: 'verify'` for a verifier round. Use the in-script gate
loop (`mode: 'implement'` without `loop: false`) only when you want the whole thing hands-off.

Hangs: CI runs `cargo test`, not nextest, so the gate does too. Give every cargo command a
10-minute timeout; a run that hits it names the tests that started and never finished as `HUNG`
failures, then reruns with them skipped. The `--no-run` split keeps a compile failure from reading
as a hang. Neither has been exercised in a run yet; run 1 lost 17.5 minutes to two stub servers
parked in `accept()` once the tightened client refused their socket.

Routing (in script code): `path` → author prefix → blast prefix → `crate` (`crates/<name>/`)
→ test path's crate. In the first run this attributed 16 of 16 gate failures. Unroutable
failures are logged; if they are all that remains the run stops for you — ambiguity stops,
it never fans out. One message per lane per round carrying every failure attributed to it.

Caps: 3 informative fix rounds per lane (rounds that carried gate or verifier information),
2 bookkeeping rounds per lane, 8 gate rounds as a backstop that has never bound. On a cap the
run returns the residue; never widen.

## 4. After the tests: verify, full, then the tail

1. **Verify**: at most two adversarial opus verifiers (`maxVerifiers`), the lanes split between
   them, read-only, refuting each acceptance line with file:line evidence, plus changelog bullet
   present, no local paths/TODOs/identifiers, failure-path tests assert the cause, every-conflict
   validation where asked, nothing edited outside the lane's prefixes. Two is the cap: four opus
   fact-checkers re-reading the same crates burned 49M tokens on 2026-09-11. Verifiers **grade**
   each gap: `blocking` (acceptance not met, or shipped prose false) routes back; nits are
   returned to you. In the first run verify produced every product change after green (six
   findings, four landed), and one ungraded wording nit cost 20 minutes and four agents. You
   rule on every finding before anything is routed: fix, accepted trade-off (named in the PR),
   or ignore; a lane never receives a raw verdict. Verifiers test against the shape of live
   state (existing data, volumes, permissions), not only a fresh fixture: on 2026-09-27 a fresh
   reviewer found a permission failure a fresh-volume test had passed.
2. **Full** tier once, then the script returns `{green, summaries, verdicts, nits}`.
3. **Fable tail** (you): read `git diff main...HEAD` once against the acceptance lines and the
   nits (the first run's tail found three more: a changelog overclaim, a wrong probe name, a
   test with no positive control); commit per lane (`git add -A -- <lane files>` so deletions
   and new files land; conventional subject; session trailers); ff-merge/push; PR edits and
   reply; one blocking `gh pr checks --watch`, never polling; a commit made after the review
   gets its own pass and the reviewed head is the head that merges; `git worktree remove` +
   `prune` once green.

## 5. Continuation (the tree is the durable state)

Agents never commit, so a stopped run loses nothing; run 1's cap cost 3.5 minutes of recovery
and the fix its last agent wrote is in the landed head. To continue: extract each lane's latest
return from `<transcriptDir>/journal.jsonl` (latest `result` per lane; strip absolute path
prefixes from `files_touched`), fix the routing or brief flaw that stopped the run, relaunch with
`mode: 'continue'` and those returns as `args.summaries`. Do not `resumeFromRunId` after
changing prompts: any prompt edit is a cache miss that re-runs implementers on an edited tree.
Never restart completed implementation to recover conversation context.

## 6. Lessons, with the evidence (dekopon PR #197, 2026-09-10)

- **Agents must not name owners.** `blocked_on_group` was the one field an agent filled by
  guessing; both guesses were wrong and each cost three opus runs (~22 min, ~56k output tokens,
  zero diff). 8 of 12 fix agents across both runs were routing artifacts. Hence
  `blocked_on_path`, the router in code, and blast prefixes so repair ownership follows the
  causing change.
- **Ownership violations were cleanup, not protection.** All three firings were undoing a
  misroute; the same 14-site fixture fix landed regardless. Keep the check, but it is why
  bookkeeping rounds no longer count against the repair cap.
- **Untyped verdict ids trip caps.** A verifier returned an id (`OWNERSHIP`) outside the
  acceptance set with `met=false`, its own gap saying no code change was needed, and that hit
  the fix cap. Verdict ids are now the acceptance enum and gaps are graded.
- **Concurrent editors see each other mid-flight.** Only the gate judges the tree.
- **Hangs are the expensive failure.** 1,052 s for two hung tests; 66 s of it overlapped
  useful work. Name them from the log and rerun without them.
- **Tier the gate.** Run 1's single gate round was 27 minutes, 84% in the test stage, for
  failures a check tier would have named in one.
- **Include reverse dependents in the scoped set.** The 14 gate failures were in scope, but
  the consumer crate whose fixtures the same change broke was not, and its fix was done blind.
- **`Date.now()`/`Math.random()` are unavailable in scripts**; stamp results after return.

## 7. Launch recipe

```
Workflow({ scriptPath: '/Users/xavier/.claude/skills/rust-feature-swarm/swarm-template.js', args: {
  worktree, scratch, review, mode: 'implement', loop: false,      // fan out, then you run the gate
  lanes: [{ key:'A', name, items:['S1','S3'], author:['crates/x/'], blast:['crates/y/','tests/'],
            forbid:[], allowed:'rustfmt --edition 2024 --check <own .rs>', brief }],
  acceptance: { S1:'…', S3:'…' },
  gates: { check:[…], lint:[…], test:[…], full:[…] },              // used by the in-script loop
  changelog:'CHANGELOG.md', changelogOwner:'D', maxFixPerLane:3, maxGateRounds:8, maxVerifiers:2 } })
// then, per red tier you ran yourself:
Workflow({ scriptPath, args: { ...same, mode:'fix', summaries: <last result's summaries>, messagesByLane: { A: ['<verbatim>'] } } })
// after green: mode:'verify' with summaries; blocking gaps → another mode:'fix'; then the full tier and the tail.
```
Pass `args` as a real JSON object, never a string. Read `journal.jsonl` before diagnosing an
empty result. Write the plan (briefs, table, decisions) to the plan file first; the retrospective
agents will want it.
