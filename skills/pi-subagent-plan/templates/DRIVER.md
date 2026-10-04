# <CHANGE NAME> — driver brief

You are the single driver of the <repo> PR that <one sentence of what the PR does>. No workflow
script, no lanes: you edit, run cargo, commit once per stage, and spawn one fresh verifier per
stage. Your supervisor issues one stage per turn and answers your stops; the turn-1 prompt is
`KICKOFF.md`.

`<design>` below means `<ABS PLAN FOLDER>`; always write it out as that absolute path. The worktree
`<ABS WORKTREE>` is your working directory; every repo-relative path resolves from it. Everything
you write lives under `<design>/execution/`; a bare `execution/...` path is never right.

## Read, in this order, nothing else first

1. This file.
2. `<design>/pi/decisions.md` — D1–D<n>, settled. Do not relitigate them. Where this brief points
   at a D-number, the decision's wording is the contract; this brief does not restate it.
3. <the one PLAN section the driver needs, with a `sed -n` range>. **Do not read** the rest of the
   plan, the review, the README, `PLANNER-FEEDBACK.md` or `execution/rehearsal/`.

The repo's `AGENTS.md` is your project context: its §Rust guidelines are the tone and your
tiebreaker; its §Review checklist is how your verifier reads you. <Name every multi-thousand-line
file: never read whole; grep, then read hunks.>

## Where things are

| What | Value |
|---|---|
| Repo | `<owner/repo>` (`origin`); primary checkout `<path>` — never touch it |
| Base | `<sha>` (`origin/main`, <version>); every locator in this packet is at this SHA |
| Branch | `<branch>`, no upstream until your first push |
| Agents | `.pi/agents/{lane-verifier,pr-reviewer}.md` in the worktree (git-excluded; never commit `.pi/`) |
| Gate | `bash <design>/pi/gate.sh` (§Gate) |
| Your files | under `<design>/execution/` only: `stage-N-report.md`, `stage-N-verify-P.md`, `review-P.md`, `pr-body.md`, `logs/*.log`, and a `<topic>-blockers.md` only when stopping. Nothing else: no per-step receipts |

## Authority: keep going, record, stop rarely

Default: **do what makes sense, record it, keep going.** When this brief is silent, wrong or
contradicted by the code, decide the way a senior engineer on this codebase would (AGENTS.md
§Rust guidelines and the nearest sibling decide ties), add one entry to `Driver decisions` — what
you found, what you chose, what you rejected, two or three sentences — and continue. Every
crate-internal name, module layout, error-variant payload, test structure and the order you work
in are yours. So is gitignored, worktree-local config (a `.env` host or port line, a copied
launcher script): change it when a step needs it, journal the old value, restore it at teardown;
it is never a stop. Independent deliverables (screenshots, checks) never block each other: when
one is blocked, finish the others, then report the blocked one.

The four stops: forking, patching or bumping a dependency to make something pass; moving a config
key/value, wire field or decision away from `decisions.md`; deleting something this brief keeps or
keeping what it deletes; owner-only actions (releases, tags, publishing, merging, <any real call to
the paid/external services>). To stop: write every open question into one
`<design>/execution/<topic>-blockers.md` with the mechanism facts and one proposed answer each,
then end your turn with its path. Nothing else is a stop: lock additions, lint fixes, test
rewrites, naming, a verifier you disagree with and a red CI check are handled in the turn and
reported.

## Order of work

For a stage that adds or changes a public type, trait or API. A stage that only re-pins, renames
or deletes skips this.

1. Before writing any code, list the invalid states the API must make unrepresentable: every
   combination of state, call order or value the stage block rules out.
2. For each, name the type that removes it: an enum with the legal variants, a newtype with a
   private constructor, a token consumed by the call that ends it, a `#[must_use]` result.
3. Write the signatures first: every type, trait and enum with its variants, every `fn` with a
   `todo!()` body, and the names of the tests, one per invariant. Only then write bodies.
4. A signature this brief or `decisions.md` fixes stays exactly as written. Improving it is a
   stop, never a Driver decision.

When this section applies, the stage report lists the invalid states from step 1 and the type
that removes each.

## Rules

- Work only in the worktree. Plain `cargo`, always `--locked` except the lock update below. The
  machine's Rust rules are in your global context (`~/.pi/agent/AGENTS.md` §Rust worktrees and
  compiler cache); follow them, never restate or work around them. A `/kache/...` path in a rustc
  diagnostic is the compiler's path remap, not a cache failure. Never delete the worktree's
  `target/`: the supervisor removes it at hand-off.
- **Lock updates are yours.** When a stage adds a dependency line, run `cargo check -p <pkg>`
  once without `--locked`, then `git diff origin/main -- Cargo.lock`: every hunk is an addition.
  An existing package changing version is a bump: revert the lock and stop. Never
  `cargo generate-lockfile`; never `cargo update` without `-p`.
- Scope to packages while iterating (`cargo check|clippy|test -p … --locked`); the full gate once
  per stage. Anything that can run over two minutes runs in the background to a log under
  `<design>/execution/logs/`, and you wait on it with one blocking command (§Gate). Write the
  stage report while it runs, not status calls.
- **A stage is at most ~1k changed lines.** If `git diff --shortstat <stage parent>` passes ~1.2k,
  split it: commit and verify the first half as stage Na, then the rest as Nb.
- One commit per stage, conventional subject. **The commit body carries the why**: the choices a
  reviewer would question and your Driver decisions for that stage, in prose, without D-numbers
  or local paths (the repo squash-merges; the squash message is what survives). Stage files by
  path; never `git add .` or `-A`; never commit `.pi/`, fixtures, targets or anything under
  `<design>`.
- No shims, aliases, `#[deprecated]`, re-exports of old names, transitional types, retries,
  checker scripts or `*Unknown` states in what the PR ships.
- Every new public item, dependency, config field and error variant has a non-test consumer in
  the same PR.
- **Wire formats are forward compatible.** A response, event stream or item list from an external
  service: unknown events, item types and fields are ignored (a trace line at most); only a
  *known* shape that is malformed is an error. A test asserting that an unknown event fails is a
  regression, not coverage.
- **Before encoding a failure in someone else's semantics** (binding a continuation to one
  upstream, refusing a response shape, pinning a routing choice), look at how two other clients
  of that service behave (their source, not their docs' prose). If none of them fails there, you
  don't either; record the finding as a Driver decision.
- CHANGELOG: `Fixed` is only for bugs in released code; a bug this PR introduced and fixed is not
  an entry.
- **Never edit a test outside this PR's scope to get a gate green.** A test that fails only under
  load (a deadline, a timeout) and passes on a scoped rerun is a flake: if `decisions.md` lists it,
  rerun it once and report both lines; if not, report it and stop the stage. On 2026-10-03 a
  driver widened a deadline in an unrelated crate; the commit was dropped and became an issue.
- **Do not end your turn while a subagent or background job is still running: wait on it with one
  blocking command that returns when it finishes, never repeated status calls.** A blocked call
  costs nothing; every status call re-reads your whole context.

## Don't write this

Each of these reads as care and is cost. The verifier flags them as `guideline`.

| Don't | Do |
|---|---|
| A signed or wider type so an invalid value can "join the semantic errors" (`Option<i64>` token counts) | The tight type (`NonZeroU32`, `u32`); reject at the parse boundary |
| Test twins at a limit: exactly-the-ceiling beside one-over, a 1-ns-over timeout cap, ±`EPSILON` float edges | One test per behaviour. Test a limit only where the limit *is* the feature |
| A byte budget on an error-message excerpt | The message; the existing body cap already bounds it |
| Redaction that blanks the whole body when a control char or the read cap is hit | A gsub: strip controls → replace exact secrets longest-first → truncate; if the read itself was cut, drop a trailing partial secret |
| Canonicalizing production bytes (sorting JSON keys) so a golden fixture is stable | Compare parsed `serde_json::Value`s in the test |
| Wall-clock assertions (`elapsed < 50ms`), sleeps as synchronization | Assert order and structure; drive time with the runtime's paused clock or a channel |
| Per-item linear scans over a growing list; a stream buffer rescanned or memmoved on every chunk | Index once; scan only the new bytes (keep a cursor) |
| More code when unsure | Less. A net-negative diff is a good stage |

## Gate

While iterating: `cargo check|clippy|test -p <the stage's packages> --locked`. After the stage
commit, once, in the background, then one blocking wait with the tool's longest timeout:

```
mkdir -p <design>/execution/logs
nohup bash <design>/pi/gate.sh > <design>/execution/logs/stage-N-gate.log 2>&1 < /dev/null &
echo $! > <design>/execution/logs/stage-N-gate.pid
```

```
while kill -0 "$(cat <design>/execution/logs/stage-N-gate.pid)" 2>/dev/null; do sleep 15; done
tail -5 <design>/execution/logs/stage-N-gate.log
```

If the tool's timeout cuts the wait, issue the same wait again. Never read the log in a loop of
separate calls.

Green means the log's last block is `== GATE GREEN`, the commit it gated, and an empty
`git status --short`. A known-flaky test gets one rerun, then goes in the report; never ignored,
never `--test-threads=1`. <If the PR touches `[[example]]` targets: `--lib --bins --tests` does
not run an example's `#[cfg(test)]` module unless its `[[example]]` entry sets `test = true`.>

## Stages

Every stage, in order:

1. `git fetch origin && git rebase origin/main`; record conflicts in the report. From stage 2:
   `gh pr checks <url>` for the pushed head; a red **required** check is fixed first, with a new commit on
   top; a pushed commit is never amended. Pending is not red.
2. Implement the stage block below. Scoped checks while iterating.
3. `df -h ~`. Commit (one commit; amend it for every later fix in this stage until it is pushed).
4. The full gate in the background (§Gate); one blocking wait to green.
5. Draft `<design>/execution/stage-N-report.md` (§Report): the verifier reads it.
6. **Verify** (§Verify). Apply every `contract` and `guideline` finding — a finding that
   contradicts a decision is declined with its D-number — amend, rerun the gate once, update the
   report. Pass 2 whenever you changed the commit after pass 1, because only a reviewed head is
   pushed (step 7): over the whole stage when pass 1 had a `contract` finding, over the amended
   delta alone otherwise. There is no pass 3, except one: when pass 2's blocking findings are all
   tagged `easy`, fix them, re-gate once, and run one verifier scoped to those findings over the
   fix delta; push on its `ACCEPT`. Any `hard` finding after pass 2 ends the turn.
7. **Push only when the last verdict is `ACCEPT`, at the SHA it reviewed.** If pass 2 still says
   `FIX REQUIRED`, do not push: end the turn with both verdicts side by side; the supervisor
   decides. Every commit you push has a verifier or reviewer file whose `Reviewed:` line names it
   (or a descendant that contains it); a commit made after the last review gets its own pass.
8. Write `<design>/execution/pr-body.md` (§Report); stage 1 `gh pr create --draft --title "<the
   commit subject>" --body-file <that file>`, later stages `gh pr edit --body-file <that file>`.
   End the turn with the stage verdict, the head SHA, the PR URL and the report path.

<Stage blocks: **Stage N — title.** What lands, the D-numbers it implements, packages, exit
criteria. Each ≤ ~1k changed lines by estimate; the planner splits anything larger.>

**Cross-stage review.** <For ≥ 4 stages: after stage <midpoint>, and again after the last stage.>
Instead of step 6's verifier on those stages, also run:

```
subagent({ agent: "pr-reviewer", context: "fresh", async: false, cwd: "<ABS WORKTREE>",
  task: "Review <origin/main>...<head-sha> as one change against <design>/pi/DRIVER.md
  §Rules and §Don't write this, and <design>/pi/decisions.md." })
```

Save it to `<design>/execution/review-P.md`. Same fix rules as step 6. After the last stage: only
on `READY` does `gh pr ready` run; then one blocking `gh pr checks --watch --fail-fast <url>`,
its output to `<design>/execution/logs/checks.log`. No checks 60 s after a push: run
`gh pr view --json mergeable`; `CONFLICTING` means rebase once, anything else is reported. A red
check: fix in a new commit on top (the head is pushed), re-gate, **re-verify the new head**, push,
at most two rounds. Otherwise leave the PR a draft and end the turn with what remains.

## Verify

<If the driver runs under `steering-eval/bin/subject-turn.sh` (`-ne`: no `subagent` tool), delete this section and §Cross-stage review's call: the supervisor runs the verifier outside the driver with `pi-drive/scripts/pi-dry-run.sh <worktree> <prompt> <out.md> openai-codex/gpt-6-sol:high bash` and sends the verdict back as the next turn (sub-campaign 4). Keep the stop list in one place, the brief, and point at it; a restated count drifts.>

```
subagent({ agent: "lane-verifier", context: "fresh", async: false, cwd: "<ABS WORKTREE>",
  task: "Verify stage N: diff <parent-sha> <head-sha> against <design>/pi/DRIVER.md §Stages
  (stage N block), §Rules and §Don't write this, and <design>/pi/decisions.md. Driver's report:
  <design>/execution/stage-N-report.md." })
```

`async: false` keeps your turn alive until it returns (if the harness refuses a foreground final-review child, launch it async and wait on it to completion in the same turn); if it comes back with a run id instead of
the verdict, check `subagent status` no more than once a minute, with one `sleep 60` call
between checks, until it finishes. Pass no `acceptance`
field: read the verdict from the returned text. Nothing resumes your turn when a child finishes;
every wait happens inside the turn. Save the returned text verbatim to
`<design>/execution/stage-N-verify-P.md`, where N is the stage and P the pass number
(`stage-1-verify-1.md`, then `stage-1-verify-2.md`). `taste` findings are yours to take or decline with a
sentence in the report.

## Report

`stage-N-report.md`, one page: head SHA; what changed with `file:line`; the gate log path and its
last block; verifier verdicts and what you did with each finding; `Driver decisions` (cumulative,
numbered). Stage 1's report opens with the preflight results. The final stage's report adds every
CI check and result, what in this brief was wrong, what you left out, and free disk before and
after.

`<design>/execution/pr-body.md` is `.github/pull_request_template.md` filled in: a short summary
of what the PR does and the test evidence (checks run at the pushed head). No D-numbers, no
`Driver decisions` list, no paths on this machine; the rationale lives in the commit bodies.

## Not in scope

<list>, releases, deployment and deleting `target/`.
