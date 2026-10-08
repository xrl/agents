---
name: pi-subagent-plan
description: Turn a big, decided piece of work into a self-contained brief plus pi-subagents agent files, a flat workflow script and a kickoff prompt, so Xavier can hand it from Claude Code to a pi session running the cheap/fast sol models (gpt-6-sol drives) with the reasoning level as the main tier — nothing Anthropic in the pi run. Use when Xavier says "hand this off to pi", "write a handoff/brief for pi", "offload this to a cheaper model", "pi subagents plan", or asks whether something is "suitable for handing off to a pi/gpt agent". Claude Code only — this is for AUTHORING the plan from Claude; it is not for running inside pi, not for one-file changes (one agent), and not for review-only work (/code-review).
argument-hint: "[design/plan path or PR/issue] [target repo]"
arguments: [target]
disable-model-invocation: false
user-invocable: true
---

# Writing a pi-subagents plan from Claude

The plan, the review and the packet live in a **plan folder sibling to the checkout** that
receives the implementation (`~/code/<project>/<effort>-design/`), never under the repo's
`docs/` and never as a PR: repo docs describe what is implemented, a plan says on line one that it
is not, its locators rot with every merge, and the execution artifacts beside it cannot be
committed. The multi-LLM plan was opened as a docs PR (#319) and closed unmerged for this reason;
what lands in git afterwards is the changelog, the upgrading note, the rewritten implementation
docs and the commit bodies (the repo squash-merges, so the squash message is the record). The PR
body is a short summary plus test evidence: no D-numbers, no paths on the driver's machine.

The deliverable is a **folder that travels**: a brief an agent with zero conversation context can
execute, the pi agent definitions it needs, a flat workflow script, and the one prompt Xavier
pastes into pi. Templates are in `templates/`. Worked example:
`~/code/dekopon/asset-design/{HANDOFF.md,pi/}` (2026-09-17), whose first run stopped seven times
on defects in the brief — every one is a rule below.

The executor is a **literal, low-judgement orchestrator** that is told to stop rather than
improvise. That is the right safety posture and it means the brief, not the agent, carries every
piece of context. Write for the reader who will take each sentence at face value.

## 0a. Shape: swarm or driver?

Default to **one sequential driver** per PR: a single high-reasoning agent that edits, runs
cargo, commits per stage, and spawns one fresh verifier per stage with a plain `subagent()` call.
No workflow script, no lanes, no gate-runner. Its authority
clause flips the default: *do what makes sense, record it under `Driver decisions` (what you
found, what you chose, what you rejected), keep going; the stage report carries that section and the commit body says the why in prose*. The
stop list is four vivid items (forking or patching a dependency, moving a contract away from the
decisions file, reversing a keep/delete, owner-only actions), never a taxonomy the model has to
classify against. **Start from `templates/DRIVER.md`** (distilled from the #321 brief): it
carries the fixed §Rules and §Don't write this blocks; fill in the placeholders and the stage
blocks, never delete those two; `templates/KICKOFF-DRIVER.md` is its turn-1 prompt (`KICKOFF.md`
is the swarm's); `pi-drive/templates/STAGE-PROMPTS.md` holds the supervisor's turn prompts. A
brief's "read nothing else first" loses to the repo's own `AGENTS.md` read list, which the
driver also holds: name the files to skip, or accept the reads. The literal "stop for any decision the table does not answer" posture cost the
asset run nine stops; the same model decided crate internals fine when allowed to. A swarm (`templates/lanes.workflow.js`) earns its
orchestration only when every lane is independent at compile time *and* the editors are trusted
to decide crate internals *and* wall-clock matters more than stops. The asset run stopped seven
times in three days on the swarm shape (grep gate, container wrapper, contracts, seams, platform,
stage gating, pi output-path collision) and produced its first 2,100 committed lines only once
the stage-1 lanes ran; the driver brief (`~/code/dekopon/asset-design/pi/DRIVER.md`) replaced
it. A driver is slower per PR and has zero seam or orchestration failure modes; the "editors never
run cargo" rule exists for eight parallel builds, not for one.

**Many independent repositories (a fleet re-pin, one PR per provider) are N driver sessions from
one brief template, not one driver with a workflow-script fan-out.** Each session gets the
template with the repo name, worktree, version and pins filled in, its own session id and log,
and the supervisor's watch loop checks every log in one pass (`pi-drive`). The 0.18.0 fleet ran
the first eleven providers through `runs.all` children and lost three of them to the parent's
turn ending, a transient provider error, and a stop routed through the parent; the four
providers that ran as parallel sessions (decision F9) lost none. Workflow scripts stay for
fan-out *inside one repository* where a gate must merge lanes.

## 0b. Cost and wall clock (asset run retro, 2026-09-20)

Three days on the asset core PR; the code was about one of them. The rest was stops routed
through Xavier, one shape reset, infrastructure detours and repeated gates. Quality came from two
things only: machine-checked contracts before the run (nine stops fell to zero code-level stops)
and a fresh read-only verifier per stage (every pass returned real contract bugs). Keep those,
and spend nothing else:

1. **Supervised from fable from turn 1** (`pi-drive`). A stop through Xavier is a day; through
   the supervisor it is a turn. The kickoff says so: stops are answered by the supervisor.
2. **One full gate per stage, at commit.** Scoped `-p` check/clippy/test while iterating; the
   workspace suite once per stage; `cargo package`, OTLP smoke and rustdoc only in the last stage
   (CI runs them on a clean target anyway; a local `cargo package` between two heads of an
   unreleased crate at one version hits Cargo's immutable-registry fingerprint and costs a
   detour). Long gates run in the background to a log file, never as a foreground tool call
   that can time out mid-edit.
3. **Verifier: one read-only pass; a second only when pass 1 returned `contract` findings.**
   Report capped at one page, findings first, one file per stage and pass
   (`execution/stage-N-verify-P.md`), never appended to a growing file the driver rereads. A
   named survivor is a claim: for every deletion the verifier greps the deleted code's
   distinctive literals (ids, error codes, config keys, secret shapes) into what remains and
   finds them asserted before accepting. A cheap verifier approved losing the only test of a
   security property on 2026-09-27.
4. **Rebase onto `origin/main` at the start of every stage**, not only before the PR. A
   workspace-wide lint that merges mid-run is ten minutes at stage 2 and a fix pass at the end.
5. **Independent stages run in parallel.** Measurement (compute) and whole-PR review
   (read-only) do not depend on each other; the supervisor runs one in the background while the
   driver does the other. Say so in the stage list.
6. **Stages of ≤ ~1k changed lines, enforced.** A 2.3k-line stage produced five findings and a
   long gate; two halves verify faster, test with `-p`, and fail smaller. #321's brief wrote
   "about three thousand changed lines" into its own stage 2 and the stages landed at 1.5k–5.1k;
   the planner splits any stage estimated over 1k, the driver splits one that grows past 1.2k,
   and the supervisor's `pi-stage-check.sh` refuses the rest. Line estimates run low: driver
   stages landed at 2.3x and 2.8x their estimates on 2026-09-29. Multiply the planner's
   estimate by 2.5 before applying the cap. Dollars ran under, because driver tokens are cheap.
7. **The packet is the brief, the decisions file and `contracts/`.** Nothing else in the
   driver's read order. Design and review documents are fable-written and fable-reviewed, and were
   the bulk of the token bill; the driver only ever needed the decisions.

Also: the driver does its own build-state cleanup and single-command retries. Spawning a child
for a one-directory delete costs a round trip and a report nobody needs.

8. **Stops are owner actions and contract surfaces, never a pattern to match.** "A build failure
   whose output names kache" parked the 0.18.0 fleet on an ordinary compile error whose
   diagnostics carried the `/kache/...` path remap. Facts like that remap belong in the machine
   rules file the driver already reads, not in a stop clause; a literal driver will match the
   words.
9. **One report file per stage, no per-step receipts.** Left alone, drivers wrote over a hundred
   evidence JSON/log files for eleven providers. Say: logs for long commands, one report per
   stage, nothing else under `execution/`.
10. **Every stage prompt says: do not end the turn while a subagent or background job is still
    running; wait on it with one blocking command, never repeated status calls.** A print-mode
    turn otherwise ends with the child orphaned (`pi-drive`), and a poll costs a full read of
    the driver's context where a blocked call costs nothing.
11. **Nothing reaches the PR unreviewed.** Verifiers and reviewers open with `Reviewed: <sha>`;
    the driver pushes only on `ACCEPT`/`READY` at that SHA, and a commit made after the last
    review gets its own pass. #321 pushed over two `FIX REQUIRED` reviews and then landed a
    412-line commit no reviewer saw.
12. **A cross-stage review** (`agents/pr-reviewer.md`) after the midpoint stage of a ≥ 4-stage
    run and again at the end. Its job is what per-stage verifiers cannot see: work that grows
    with the stream, forward compatibility of every wire parser, pinned assumptions about other
    services, code that exists to satisfy a rule literally.

Receipt: #321 (2026-09-22), whose paranoia patterns came from our own rules, is why
`DRIVER.md` §Don't write this names concrete bans; "don't be paranoid" alone does nothing to a
literal model.

## 0. Gate: is it ready to hand off?

Say no — and say what is missing — unless all of these are true. Half of a handoff is refusing to
write one too early.

- **Decisions are settled and written down** as a table the implementer must not relitigate.
  Every open question either has the owner's answer or is an explicit stop condition.
- **Record the review tier before launch** (§3a, Plan checking versus full review). Run a fresh
  Sol-high brief check; apply §3a's full-review triggers/skip rules. Use a different reviewer
  from the designer; require `file:line` evidence. Copy its "facts an implementer must be told"
  verbatim into the brief; apply coordinator-ruled amendments before launch.
- **The contracts are concrete and machine-checked**: interface definitions (IDL, schema)
  parsed by their own tool on the real files (a `contracts/` folder in the brief dir that lanes copy byte-for-byte), Rust
  seams as signatures, config keys named against the existing struct and its `rename_all`; every
  constant that moves or dies is named with its locator; every consumer of a deleted convention
  is enumerated. A prose interface in a design is pseudocode until it parses: reserved keywords,
  payload rules and undefined types all surface there — the asset run
  stopped on all three. Every "a config key for X", "a budget", "a directory" in the design
  becomes a named key with a value and a mandatory/defaulted call.
- **Cross-lane seams are written, and lanes are staged by what they consume.** If lane C's code
  compiles against types lane A creates, C is stage 2: its editor starts by merging A's branch,
  and the brief carries A's type and function signatures so both sides build the same seam. File
  non-overlap is not enough; compile-time consumption is the graph. **Stage gates are scoped**
  (`cargo check -p` the stage's crates, `args.lanes[*].packages`): a stage-1 seam change breaks its
  stage-2 consumers by construction, so a whole-workspace gate between stages can never pass.
- **Every seam sketch is fact-checked against the real signatures** before the brief ships: the
  existing return and error types, existing names (collisions), and the platform matrix (a flag
  that exists only on Linux, a test that needs `/proc`). The planner's sketch of a widened
  `invoke` changed its error type by accident and collided with a re-export; both stopped the run.
- **A scenario walk closed.** One end-to-end scenario per feature (for assets: upload → edit →
  output → send → edit the output again) walked through every rule in the design by a cheap
  agent, listing each rule it touches and whether it holds. The asset design's "fresh open by
  path" and "path-less output" were each fine alone and contradicted on the second edit.
- **A consequence walk has run on the plan** (pi sol is enough; it needs `bash` for the greps
  and gates, so its prompt says "mutate nothing"). Fact-checkers verify what the
  plan says; this verifies what the plan's changes do to things it does not mention. The
  multi-LLM plan (2026-09-22) had zero wrong locators and still yielded ten seam findings at
  packet time, every one a second-order effect. Before handoff, for every: new dependency edge,
  run the repo's dependency-boundary gates; changed public type, grep its serialization and
  `Debug` consumers and the tests that only build under a feature; "keep today's behavior" or
  "verbatim" claim, read what today does per call (deadlines per send, retries, finish reasons),
  not per concept; named test, check the crate it lives in can reach the fixtures and mocks it
  names (`#[cfg(test)]` does not cross crates; a fixed-URL client needs an injection point with
  a non-test consumer; an example's `#[cfg(test)]` module does not run under `cargo test --lib
  --bins --tests` unless its `[[example]]` sets `test = true`); new enum arm, grep non-exhaustive `let … else`/`if let` over that enum;
  replaced type, list every doc that constructs the old one, not only the docs the feature owns;
  existing record the change makes larger (a journal line, a wire request, a history window),
  name its size limit, what that limit measures (raw or delivered text, decoded or encoded bytes)
  and which field grows, then bound that field, never the whole record. Chat steering
  (2026-09-26) folded messages into three records and found each limit one review round at a
  time; a supervisor cap on the whole journal line regressed long answers.
- **Other clients were read before a provider semantic became a failure.** Any decision that binds,
  pins or refuses on another service's behaviour (bind a continuation to the upstream that served
  it, fail on an event type the docs don't list) cites what two other integrations of the same API
  do, from their source. #321's D34 bound OpenRouter continuations to the upstream provider; no
  other client (Vercel's provider, pydantic-ai, Zed, LiteLLM, Cline) does, and multi-step tool
  turns failed at random under default load balancing. They forward `reasoning_details` and send
  `session_id` for sticky routing. The recon agent does this lookup.
- **Wire formats are forward compatible by default.** The decisions say it once: unknown events,
  items and fields from an external service are ignored; only a malformed known shape errors. A
  contract line like "reject unknown required semantic events" is how #321 made Codex's unknown
  events fatal, with the driver's own test asserting the regression.
- **Every test a decision asks for fails on the code being fixed.** Say what the test must
  observe that the old code does not produce. The cwasm fix's decision read "the load fails and
  the error names the path": the bug already did exactly that, one implementation wrote the test
  to the letter, and it passed on the old code (2026-09-29). Where a decision turns on a check
  ("if the object exists"), say what a failed check means; two implementations of one decisions
  file diverged on `exists()` against `try_exists()`.
- **Every stage is estimated at ≤ ~1k changed lines** (§0b.6); split the rest before handoff.
- **The invention audit is empty** (§5).
- **The verifier's agent file fits the repo.** `templates/agents/lane-verifier.md` assumes Rust
  and an `AGENTS.md` with §Rust guidelines; for a repo with neither, the brief's verify task
  says which rubric applies instead.
- **The repo carries the tone and the rubric, the brief points at them.** `AGENTS.md` §"Rust
  guidelines" (yes/no pairs) and §"Review checklist" (tagged findings, two fix passes, the lane
  report's `Choices I made` heading) are what let an editor decide crate internals
  itself; the brief's stop rule names only contract surfaces. Mechanical rules are workspace lints,
  not verifier reading.
- **The baseline is stated**: which PRs are assumed merged, which SHA, which measurements to beat.
  **Re-verify every base ref at launch**, not only at recon: refs moved under three packets in one
  afternoon on 2026-10-03, and one move (a branch becoming an ancestor of `main` through another
  session's ours-merge) turned a planned merge into a silent no-op that would have deleted the
  feature. `git merge-base --is-ancestor` and `git merge-tree` on the real refs, the hour you launch.
- **Known flakes are in the decisions file before launch.** List each test that fails under
  concurrent heavy builds (with its issue) and the rule: one scoped rerun at the unchanged head,
  green counts. Parallel units on one Mac make these certain; without the row, every one is a
  hand-back or, worse, a driver edit to a test outside its scope.
- **A dependency move has been diffed, not just named.** When the work re-pins a published crate
  (SDK 0.15 → 0.18), the recon diffs the two published manifests' features and dependencies
  (`cargo info`, or the registry `Cargo.toml`s under `~/.cargo/registry/src/`) and the brief
  names what changed. A dropped compile-cache feature was visible there and cost one consumer
  3.5 hours of release-job timeouts because nobody looked.
- **What stays with the owner is explicit**: releases, tags, published packages, private-repo
  commits, paid or real external calls, merges. Agents open PRs; they never merge or approve. Say
  the other half too: version fields edited inside a PR are ordinary work — "chart bump" read
  literally is a stop condition. **The auto-mode classifier enforces this on the coordinator
  too:** merging a PR that only a sol verifier read ("Merge Without Review") and pushing a
  release tag ("Create Public Surface") were refused on 2026-10-03; PRs with a Fable review merged.
  A release plan names each merge and tag as one owner command to paste, written out in full, or
  asks once up front for a permission rule.
- **The rehearsal (§5) passed** with no stops.

## 1. The brief (`HANDOFF.md`)

Sections, in this order. Keep it under ~400 lines; link, don't paste, the design.

1. **Read first, in order** — the guidelines, the decisions file, `contracts/`, the baseline
   numbers, the repo's own `AGENTS.md`/development docs. Not the design or review documents
   (§0b.7). Say what *not* to read.
2. **Mission** — one paragraph, plus the inherited baseline and "verify it or stop".
3. **Repositories, refs, rules** — table of repos with local paths and roles; the non-negotiable
   rules: worktree per PR, one `target/` per worktree, `--locked`, fixtures fetch, disk cap, gate
   list, no shims/leftovers, fail-fast/no-paranoia, owner-only actions, commit attribution, PR
   template. **Machine rules the executor already holds in its own global context
   (`~/.pi/agent/AGENTS.md`) are pointed at, never restated** — a restated copy drifts and the
   agent stops on the conflict. Say which rules are host-only (build wrapper, caches) and that
   containers build plain.
4. **Decisions (settled)** — the table. Cite where each was recorded.
5. **Work packages** — one lettered lane per seam with exact paths, what changes, what is deleted,
   which docs move in the same change, and the tests it must add. Lanes must not overlap files;
   if two must touch one file, name the hunks. **Any preparatory edit** (rebasing a harness,
   generating fixtures, rewriting config) is a stage with an editor, because the orchestrator
   never edits.
6. **Landing order** across repositories, derived from every consumer *at its deployed version*
   and checked against the real artifact, not against what the team believes it imports; say why
   no other order avoids a broken window.
7. **Acceptance** — falsifiable: numbers to beat (re-run the harnesses), fixtures that fail today
   and must pass, and greps that must come back empty **naming retired identifiers, never common
   words** (a grep for `attachments` matched Discord's wire field and the brief's own new
   `attached` field), with the look-alikes that legitimately survive listed beside them. A
   numeric target names the unit it counts ("a behaviour is a contract a user, operator or peer
   relies on"), the expected result per unit, and the rule for the shortfall (anything under the
   bar is justified item by item). "When unsure, keep it" over a fuzzy unit returned a 1.7% cut
   against a ~30% target; the per-unit version returned 12× more (2026-09-27).
8. **Stop and report** — the conditions under which the agent stops instead of working around.
   Every noun here must mean the same thing it means in §5 ("bump", "release", "wrapper").
9. **Not in scope**, and the hold list: everything in flight the run must not touch, the
   supervisor's own open branches and PRs included, not only planned campaigns.
10. **Execution plan** — §2 below.
11. **Running it on pi-subagents** — §3 below.

Style: locators everywhere (`path:line @ ref`); "verify with `git show`" once, not per line; no
narrative history; decisions as facts, not as arguments. Artifacts the brief reuses are named as
they exist: branch names and SHAs, not "the patch"; a patch that spans two repos says which hunk
belongs where.

## 2. Execution plan (roles, levels, preflight, sanity, gates, report)

**Roles and levels.** The driver and the lane editors run `openai-codex/gpt-6-sol` at
`medium` (the owner's dial, 2026-09-30, §3a). The stage verifier, fact-checker, gate-runner and
supervisor run `openai-codex/gpt-6-sol`; the brief checker uses it at `high`.
Use `gpt-6-astra` for small bounded Pi reviews; route consequential review to Fable in Claude (§3a).
Nothing Anthropic: Xavier keeps the Anthropic spend in Claude. One
provider, `openai-codex`, for the whole run. The lever is the
reasoning level (pi: `minimal ~1k`, `low ~2k`, `medium ~8k`, `high ~16k`, `xhigh ~32k`, `max`):
mostly medium; the command runner low; reviewers high/max. Provider ids are `<provider>/<model>`
and the provider segment is not guessable — read `subagent({action:"models"})`.

| Role | Level | Rule |
|---|---|---|
| Orchestrator | the parent pi session, medium | edits no code; runs preflight; routes; runs the last tiers; opens the PR |
| Lane editor (one per lane or prep stage) | medium | **never runs cargo**; edits only its seams; `contact_supervisor` → `need_decision` instead of guessing |
| Gate-runner | low | the **only** agent that runs cargo; merges lane branches; returns JSON with verbatim tails and an attributed lane |
| Verifier (one per lane) | high, **fresh context**, read-only | adversarial acceptance of one lane's diff; a late lane gets one too |
| Brief checker | sol high, fresh, read-only | completeness and executability against settled decisions; no scope authority |
| PR reviewer | fresh: astra xhigh for small bounded Pi review; Fable max in Claude for consequential review | cross-stage: cost over the whole stream, forward compatibility, pinned assumptions about other services, size, coherence; no spawning by default (add `subagent` + `allowNestedSubagents: true` to allow ≤ 2 fact-checkers) |
| Fact-checker | medium, fresh | one pointed question with locators |

**Preflight** (orchestrator, before any lane), executable in the order written: provider auth
valid and the model id confirmed; baseline PRs merged; pinned `origin/main` SHA and **the PR
worktree created from it in the same step** (every later preflight step runs inside it);
`df -h` and no foreign `cargo|rustc`; fixtures fetched; toolchain pins checked *from inside the
worktree* (the repo root may lack `rust-toolchain.toml`); **baseline gate green before any edit**;
review locators re-verified at that SHA. Baseline measurement is a workflow stage (editor + gate
runner), not a preflight action. Lane worktrees come after preflight, from the same SHA.

**Per-lane sanity check**: one command or test per lane the gate-runner runs before the verifier
reads the diff (round-trip test, mirror check, identifier grep, end-to-end fixture).

**Gate tiers**, stop at the first red, route the verbatim failure to the causing lane by `resume`:
`cargo check` → fmt/clippy/rustdoc `-D warnings` → scoped then workspace tests → doc gates →
lane sanity checks + end-to-end fixture → measurement re-run → adversarial review → open the PR
and watch checks. Known flaky tests: one re-run, then report, never silence. Per stage this is
run **once**, at commit (§0b.2); packaging and smoke belong to the last stage only.

**Report**: PR URL + head SHA; per lane, changes with `file:line`; before/after table; every gate
run and result; what in the brief was wrong; what was left out; disagreements; disk before/after
and which `target/` were removed. The report is for the supervisor; the PR body is a short
summary plus the checks run at the pushed head, and the why goes in commit bodies.

## 3. pi-subagents specifics (v0.75.0 installed at `~/.pi/agent/npm/node_modules/pi-subagents`; its `docs/` are the reference, re-check them when in doubt)

Verified there on 2026-09-20 (workflow call shape re-checked on 0.75.0, 2026-10-03): `outputSchema` is a real launch field on `runs.run`/`runs.all`
entries (`docs/workflows.md`, `docs/tool-reference.md`; it cannot be combined with a typed
`gate`); `contact_supervisor` is injected by the supervisor bridge (`docs/configuration.md`,
mode `always`) and is not gated by the `tools` allowlist; project agents resolve from the
session's project root (`docs/agents.md`, `projectRootResolution`), so also copy `.pi/agents/`
into each child worktree when a child's `cwd` differs.

**Agent files**: markdown with YAML frontmatter + system prompt. Project scope
`.pi/agents/**/*.md` overrides user `~/.pi/agent/agents/**/*.md` overrides builtins. Fields that
matter: `name`, `description`, `advertise: false` (keep helper agents out of the parent prompt),
`tools` / `excludeTools` (allowlist `read, grep, find, ls, edit, write, bash`; drop `edit, write`
for read-only roles; `excludeTools: subagent` unless the role may spawn, in which case `tools`
includes `subagent` plus `allowNestedSubagents: true` and `maxSubagentDepth`), `model:
provider/id`, `thinking: minimal|low|medium|high|xhigh|max`, `systemPromptMode: replace`,
`inheritProjectContext` (true for editors and gate-runner, false for fresh reviewers),
`defaultContext: fresh` for verifiers/reviewers, `acceptanceRole: read-only | writer`,
`completionGuard: true` for editors, `timeoutMs` (default foreground deadline is 30 min — set
hours for editors and gate-runners). Overrides without files:
`.pi/settings.json → subagents.agentOverrides.<name>.{model,thinking,tools,…}`. The prompt body
must not promise a tool the frontmatter withholds.

**Tool**: `subagent({ agent, task, cwd, context: "fresh"|"fork", model, isolation:
"none"|"worktree", baseRef, async, timeoutMs, acceptance:{level, criteria, evidence, verify:[{id,
command}]} })`; `{ action: "validate", workflow: "<script path>", args }` before running;
`{ action: "status" | "steer" | "interrupt" | "resume" | "stop", id }` for control;
`maxSubagentSpawnsPerRun` defaults to 64 per run tree.

**Workflow scripts** (`subagent({ workflow: "<script path>", args, cwd })`; a `workflow` value
containing `/` is a file path, relative to the request `cwd`): top-level JS with `await`; `runs.run(key, {…})`,
`runs.all([{key, agent, task, cwd, context, …}])` → **ordered array** (destructure, don't key),
`runs.lanes([{key, stages:[…]}])` for up to 32 lanes × 16 stages where a lane failure blocks only
that lane. **No nested `async` functions or async arrows** — write it flat with `for` loops.
`runs.run("k", { resume: prior.runId, task })` continues a retained child with its context — this
is how a verbatim gate failure goes back to the editor that caused it. Raw scripts cannot call
`runs.host`; permission-sensitive steps go through named workflows. Children reach the parent with
`contact_supervisor({ reason: "need_decision" | "progress_update" })`; the parent answers with
`subagent_supervisor({ action: "reply", replyTo, message })`. Every relative path in a `task`
string resolves from that child's `cwd`; pass absolute paths.

**Worktrees**: pi's `worktree: true` branches from HEAD, captures a patch and *deletes* the
worktree. For a Rust repo whose rule is one persistent `target/` per worktree and a gate that runs
on a merged branch, **create real worktrees in preflight from one pinned SHA and pass them as
`cwd`**; leave `isolation` off. Keep pi's isolation for throwaway explorations.

**Context**: `context: "fresh"` for anything that must not inherit the designer's or editor's
assumptions (verifier, reviewer, fact-checker); `fork` only when the child needs the parent's
conversation. Foreground children do not load the parent's extensions.

**Provider auth**: an expired login kills the run at the first spawn. One provider for the whole
run; the kickoff confirms its auth before anything is spawned.

## 3a. Who does which step: Claude decides and reviews, sol does and watches

The default is pi sol for every step that is procedure, and Claude only where the step is a
judgment about scope, design or what a literal driver will do. Propose this split in the plan
before writing the packet, as a table; Xavier approves it once. The GPT side runs on his
subscription, so its dollars are notional and Claude's are not.

| Step | Tier | Why |
|---|---|---|
| Recon, inventories, release-path lookup | pi sol at medium, fresh, read-only | lookup and extraction. First graded run 2026-09-29: the model-card recon, 235 rows through a headed browser for $1.29, every one of seven spot-checked numbers right. Grade two more; sonnet `Agent` is the measured fallback |
| First draft of the briefs, agent files and kickoff, from the recon and a decided plan | pi sol | large, well-specified prose |
| Dry-run rehearsal of a brief (§5), invention audit, scenario walk, consequence walk | pi sol at high (`pi-dry-run.sh`) and sonnet `Agent` in parallel on the same prompt (owner 2026-10-08, reversing 2026-09-30's sol only); sonnet alone when pi's login is down | a dry run simulates the executor, so sol runs on the executor's model; sonnet misses a different quarter (§5) |
| Prelaunch brief check | pi sol high, fresh, read-only | check settled decisions; scope below |
| **Consequential architectural challenge** | fable max, fresh | Xavier's engineering-taste preference. 2026-09-29: critical error in each of three plans, about $3 each |
| Rewriting the brief in one voice after the plan check and dry run | the coordinator session or pi sol, then a sol rehearsal of the rewrite (owner 2026-09-30: no Fable rewrite) | a Fable rewrite cost more than it found; the rehearsal after it catches what the rewrite breaks |
| **Interfaces on a contract surface** (interface definitions, wire format, config keys, a public SDK or plugin trait) | opus drafts the sketch, naming the states it makes unrepresentable; a fresh fable walks one real scenario through it; Xavier decides | opus's API sketches graded A on 2026-09-28; fable's design reviews found the P1s. The designer never reviews its own sketch |
| Types and signatures inside a crate, behind a fixed entry point | the pi sol driver, by `DRIVER.md` §Order of work | the eval scored exactly this: the order of work added 1.4 points for 4 cents, a Claude-written sketch plus shape review added 0.25 for 6 to 10 times the run cost. No per-stage sketch |
| Editing, building, PRs, releases, watching CI | pi driver (`openai-codex/gpt-6-sol`, medium, recipe A) | the volume; the owner's dial of 2026-09-30 |
| **The step that sets a spine's shape** (the types the later steps extend) | one Opus agent building directly, then the verifier | sub-campaign 4's A2 built both ways: the blind Fable judge landed Opus's spine; pi kept the old plumbing with pipes bolted on |
| A step's fix round | split by the verifier's `hard`/`easy` tags: Opus fixes the hard findings (code only), the pi driver witnesses them and does the easy list; all-easy rounds stay in pi; a failed re-check goes to Opus (`pi-drive` §Fix rounds split by difficulty) | sub-campaign 5 sent every second round to Opus: five Opus fix agents, mostly writing tests, two rounds with no hard finding (owner, 2026-10-01) |
| Per-stage verifier | pi sol (`lane-verifier`, fresh) | cheap and it finds real contract bugs |
| **Cross-stage and whole-design review** | fresh fable in Claude for consequential review; pi astra (`pr-reviewer`, xhigh) for small bounded review | routing preference, not universal ranking. Astra, 2026-09-28: about $6, nine majors, none overlapping Fable's |
| Re-check of a fix against the finding it answers | pi sol verifier, fresh | "did this commit do what the Fix line says" is mechanical. A second fable pass only when the fix moved a contract surface or answered a P1 |
| The watch loop: liveness, relaunches, read-only checks, stage prompts, routing findings | pi sol supervisor for mechanical and code units (`pi-drive` §A sol supervisor: piloted 2026-09-29, passed on sub-campaign 4's A2-A13 with zero decisions of its own); releases and rollouts too (campaign §Who does what: Ship) | mechanical; it was the largest Claude line on 2026-09-29 |
| **Ruling on each review finding** (fix, accepted trade-off, ignore) | fable or the session | this is where scope stays proportionate |
| **A stop the decisions file does not answer** | fable | four or five per day decided the outcome on 2026-09-20: the false kache stop, the python timeout cause, the fan-out shape reset |
| **Adversarial review of the landed PR (§5b)** | fable, fresh | two gpt reviews passed #305 with a 44 GB hole in it |
| Site or docs copy in Xavier's voice | opus writes, fable reviews once | voice rules are judgment |

The bold rows are Claude's. If the session is fable it keeps the bold rows and delegates the
rest to pi. If the session is opus, it spawns a fable `Agent` (`subagent_type: claude`, `model`
per the harness) for each fable row with the decisions file, the brief and the stop's blocker
file as the whole context.

Two checks are not run again: a sonnet adversary hunting counterexamples (0 confirmed in 126
attempts) and a Claude shape review after every stage (+0.25 points for 6 to 10 times a run).
Receipt, 2026-09-29: Claude $240 against pi $116; Opus supervisors ($70) cost more than the
drivers that wrote the code ($60); the reviews and plan checks found every real defect.

### Plan checking versus full review

- Run bounded prelaunch brief checks, stage checks and fix rechecks on fresh, read-only
  `gpt-6-sol:high`. Check settled decisions: signatures, completeness, ownership/order,
  scenarios/consequences, acceptance tests and stops. Cite requirement, source and failure.
- Use full-fat fresh **Fable in Claude** for consequential engineering taste; **Astra** is fine
  for small bounded reviews. Keep Pi OpenAI-only. If Fable is unavailable, stop and ask.
  Do not treat Sol max as a proven substitute.
- Require full review for changes to security/credentials/authority/isolation; public/persisted
  contracts; migrations/cross-service compatibility or rollout order; concurrency/cancellation/
  shutdown; aggregate limits/long-lived state; security/resource-test deletion; new spines/
  cross-stage dependencies; unresolved requirements/material disagreement. Small diffs count.
- Skip only the **additional full-fat prelaunch** pass: settled, local, reversible, no trigger;
  source/consumer and scenario/consequence checks closed; required gates and fresh scoped review.
  Record `Review tier` and the skip reason. Never waive repo/campaign gates or **final fresh
  Fable PR review (§5b)**.
- Leave scope, trade-offs, uncovered stops and finding rulings to the coordinator; record decisions
  before dependent prompts. Rehearse the rewrite. Treat Sol `ACCEPT` as bounded evidence only,
  not authority to broaden scope, merge, release or deploy.
- Keep the expanded Sol brief-check role provisional; require task-matched omission-detection
  evidence, not vendor aggregates, before expanding it.

### Effort: the start of the flat part

Set each role at the lowest effort after which the next step gains under about 1 point on the
benchmarks nearest its work (curves: `~/code/dekopon/effort-tuning-design/execution/CARDS.md`).
Benchmarks are the prior; a task-matched eval overrides them. On the Claude side effort is the
smaller lever: fewer turns and smaller briefs save more than a lower setting.

| Role | Effort |
|---|---|
| Driver, lane editor | `gpt-6-sol` at `medium` |
| Stage verifier, fact-checker, dry runs | `gpt-6-sol` at `high` |
| Gate-runner | sol `low` |
| Recon, inventories, brief and packet drafts | sol `medium` |
| Supervisor | sol `high`; never `max` |
| Interface sketch, spine step | opus `high` |
| Bounded prelaunch brief checker | `gpt-6-sol` `high`; not automatically `max` |
| Small bounded cross-stage reviewer | astra `xhigh` |
| Consequential whole-design challenge, final adversarial PR review | fable `max`, fresh through Claude |

Receipts: 2026-09-29, the cards put `gpt-6-sol`'s knee at `high`, the steering eval
(`~/code/dekopon/steering-eval/REPORT.md`) found `medium` held; dry runs went up from low to high
(sol's factual error rate 11.4% low, 5.1% high). 2026-09-30, the owner moved the driver from
`gpt-6.1-sol` to `gpt-6-sol` at `medium`: same hidden pass rate and cost, 1.85x faster, 1.5 lower
blind on pipe-type shape (so a spine step goes to Opus). As drivers, `gpt-6-astra` ended two of
four runs with a question and no code; Opus scored highest blind at twice the cost.

## 3b. Offer to drive it

After the kickoff and rehearsal, **offer to drive the pi session from Claude Code** with the
`pi-drive` skill: a supervisor issuing one stage per turn and answering non-hard stops
from the decisions file (which tier supervises is §3a's watch-loop row), gpt-6-sol at medium as the driver. Xavier wants this pairing ("super high level
fable with super cheap gpt"); the alternative is him pasting prompts and each stop costing a day.
Say which path (print or RPC) and why in one line.

## 3b2. Runtime windows: boot-check before touching shared state (2026-09-26)

When a stage stops or repoints a shared service (a container, a shared database, a proxy) to run
the branch's build, its first step is a read-only boot check of **everything the window will
use**: every host and route it will open answers (login page 200, not 500 or "blocked host"),
pending migrations are listed, required env/host settings exist. Only then stop the shared
service. One capture run stopped a shared app container first and then found, one turn at a
time, a pending-migration 500 and a refused host: two round trips and a longer outage of the
shared container. Repo-specific checks (which command lists migrations, which env var
admits a host) belong in that repo's agent guide, and the brief points at it.

**Screenshot clips.** A capture of an element that opens a popup (listbox, menu, modal) clips to
the union of the trigger and the popup plus padding, and asserts every item the shot is about
lies inside the clip. One clip was computed from the input alone and cut the dropdown
after two rows while every DOM assertion passed.

## 3c. Vision classification lanes (screenshot pairs, 2026-09-23)

When a run ends with images to judge (before/after pairs, "is this capture blank"), the
classifiers are their own lanes, and they are cheap only if you keep them small:

- **Rubric, not skill.** Each child gets a ≤1 KB rubric (the verdict labels, what each means,
  the one fact the pair must show) plus absolute image paths. All 21 pair children of one
  run read a 15 KB browser skill first, about 370 KB of context spent on nothing.
- **Cheap pass, then Sol.** Luna shortlists and classifies. Sol re-reviews every unclear or
  disagreeing pair before a verdict reaches a PR. Luna picks images well and calls verdicts
  generously (`agent-routing` has the numbers).
- **Schema-capped output.** `outputSchema` with one verdict + a one-line reason per pair. One
  eval child returned 106 KB of text.
- **The capture driver never opens a PNG.** It asserts DOM `facts` with `expect` and writes
  screenshots as evidence only. That held on 2026-09-23: 174 calls, zero image reads.
- **Model ids come from the registry, not memory.** A hand-written pairs workflow ran Sol on
  the retired `gpt-5.6-sol`; grep the script for `gpt-5.6` before launch.

## 4. Kickoff prompt

One prompt to the parent pi session (`templates/KICKOFF.md`). Line 1 is the working directory —
every relative path in the prompt and the brief resolves from it. Then: the model and auth check;
the judgement clause ("where the brief's text and its evident intent conflict, follow the intent,
note it in the report, keep going; where a step needs something a later step creates, create it;
stop only for the owner's actions and for decisions the table does not answer"); a clean-slate
step if a previous attempt left worktrees or branches; numbered steps each pointing at a brief
section (preflight 1–N; worktrees and `.pi/agents/`; lane briefs = the §Work packages block
verbatim + the sanity line + worktree/branch; `validate` then run with `args`; last tiers and PR
without merging; report). End with the stop conditions and what is out of this run.

## 5. Rehearse before handing over

Three cheap passes, each run by **two voices on the same prompt, in parallel**: the driver's own
model at high effort (`openai-codex/gpt-6-sol:high`), because a dry run simulates the executor,
and sonnet (`Agent`, `model: sonnet`), because another family misses different things. The union
of their findings goes through one ruling pass. Not at low: sol's factual error rate is about twice as high there (§3a Effort).
`pi-drive/scripts/pi-dry-run.sh <workdir> <prompt-file> <out.md>` does it with no write, edit
or bash tool, so read-only is enforced; pass `bash` as the fifth argument only when the walk
must check git refs or installed tools. A packet rehearsal cost $0.10 at low on 2026-09-29. When pi's login is down, sonnet
runs alone. **Sol against sonnet, one frozen brief, same prompt (2026-09-29).** Sol at high: 119 s, 39 tool
calls, $0.40. Sonnet: 144 s, 12 tool calls. Of 27 real findings, 13 were found by both, 7 by
sol only and 7 by sonnet only, so each alone caught about three quarters. Neither was the
better one: sol alone found that a failed cell and a model mismatch pass silently; sonnet alone
found that the batch script ran two at a time, which would have broken the pairing the decision
rule rested on, and that nothing checked the effort actually applied. They miss different
things, so both run on every brief (owner, 2026-10-08, gauntlet R1; reverses the 2026-09-30
"sol only" cut). **Rehearse again after
the one-voice rewrite** (sub-campaign 4: a $0.30 sol rehearsal caught a rewrite telling a `-ne`
driver to spawn its own verifier). The sequence that worked: draft, rulings, plan check and dry
run in parallel, rulings on findings, one-voice rewrite, **one** rehearsal (below), hand off. The files are in
`~/code/dekopon/effort-tuning-design/execution/rehearsal/`.
The passes are the **ops rehearsal** below, the **invention audit** and the **scenario walk**. The rehearsal runs
**after** any adversarial pass and re-verifies each amendment that pass applied against the
source: amendments are claims, not facts. Once an adversarial reviewer declared a real
helper nonexistent and rewrote a decision around it; the rehearsal found it in the source.

**Invention audit** — per lane, an agent given only that lane's brief and the design sections it
cites answers: "list every name, type, value, path, default, error shape, ordering and
behaviour you would have to choose yourself to finish this lane, and where you would have to
read another lane's unwritten code". The audit's output has one mandatory line per lane:
**"Calls into other lanes' crates: `<fn>` in `<file:line>` → `<crate>` (lane X)"**, listing
every call site in that lane that reaches a crate another lane owns, or "none". Any such line
means a seam signature in the brief and a stage boundary between the two lanes. Every item goes
into the decisions table with a value, or
becomes an explicit "editor's choice within these bounds" line, or moves the lane to a later
stage. The audit is done when a rerun returns nothing. This is where the asset run's three
stops (an undefined interface type, an unnamed config key, an A↔C seam) would have surfaced for a
few cents instead of a stalled run.

**Scenario walk** — §0's end-to-end scenario against the design: which rule each step touches,
whether the rules compose, with `file:line`.

**Ops rehearsal** —

Run `pi-dry-run.sh` (sol at high, fresh, read-only) and a sonnet `Agent` side by side, each with
the kickoff prompt plus: "DRY
RUN: mutate nothing; walk every step exactly as a literal executor would, with nothing but the
files it has; per step list the exact commands, the directory, every file/worktree/branch/tool/
credential it needs and whether it exists now, and every point where you would stop, guess, or
do the wrong thing. Label each gap **blocking** (owner action, irreversible or public step,
contradicting rules, missing file or tool) or **driver's call** (derivable from the repo, its
docs or the decisions file). Also walk the brief's acceptance section and every agent file." The
rehearsal must cover the acceptance section and the agent frontmatter, not only the
kickoff — the first rehearsal walked the kickoff and missed an acceptance grep that contradicted
the brief's own contract.

**One rehearsal, three exhaustive walks, then hand off.** An open-ended "where would you stop"
pass samples, so no count of passes proves a packet complete, and everything but an irreversible
or public step has a later backstop (silent wrong code meets the verifier, Astra, Fable and CI; a
contradiction or wrong order meets a driver stop and one ruling) cheaper than more hunting. So
the prompt also names three walks a sol pass completes instead of sampling:

1. **Dependency walk:** per step, what it consumes and which earlier step produces it.
2. **Public-action preconditions:** per merge, tag, push, PR state change, production delete or
   secret read, each precondition against the real refs (PR draft state, tag unused, SHA
   equality).
3. **Contradiction sweep:** per value a ruling sets (levels, owners, order, counts), grep every
   packet file.

Fix blocking gaps only; owner prerequisites (an owner action, a concurrent unit's close) are launch
gates, not findings. **Don't pre-chew:** writing the command for a driver's call makes Claude
author what the driver should derive. Spell a command out only where a literal mistake is
irreversible or public (tag push, production delete, secret read) or the step is the only strict
gate; otherwise give outcome plus constraints. Re-rehearse only the changed files, and only if a
fix touched an irreversible or public step; then hand off. (Sub-campaign 2 re-plan, 2026-10-05:
rehearsal patches hand-wrote the import and smoke commands, and the next rehearsal found `jq .id`
where the API returns `sessionId`, a bug a driver reading `openapi.yaml` would not have made.)

Checklist the rehearsal must confirm:

- cwd on line 1; every relative path resolves from it;
- every step runs in a directory an earlier step created;
- the orchestrator never edits; preparatory edits are stages with an editor;
- no noun means two things across sections; no machine rule is restated; host-only rules say so;
- artifacts named as they exist (branches, SHAs, which repo each hunk belongs to);
- agent frontmatter matches the prompt body (tools, spawn permission, model id, level);
- workflow `args` shape matches what the kickoff passes; `task` strings reference sections that
  exist under that name;
- acceptance greps name retired identifiers and list the look-alikes that survive;
- the kickoff tells the orchestrator how to stop for decisions: one `execution/<topic>-blockers.md`
  with every open question, its mechanism facts and one proposed answer, so the owner answers
  once (the asset run did this well; keep it);
- a `CONTINUE.md` can be written from the kickoff by deleting steps: each stage is skippable by
  an `args` key, and stopped pi children are never resumable across runs.

## 5b. Adversarial review of the landed PR (2026-09-20)

After the driver's PR is green, one **fresh fable** agent (`Agent` with `subagent_type: claude`,
not a fork: a fork inherits the supervisor's decisions and confirms them) reviews the PR from
`templates/ADVERSARIAL-REVIEW.md`. It gets the security model, the decisions as contract, the
design's limits table and the guidelines checklist; never the stage reports, verifier files or
measurements. It is told what a finding must contain (file:line, concrete scenario, wrong
outcome) and to write unprovable worries into a five-item list, which is what keeps a fable pass
from returning twenty "considers". Output is one file under `execution/`, verdict first, and the
final message is the verdict line plus counts. First run: PR #305, 15 minutes, ~240k tokens,
one high (a per-request ceiling the design stated and no per-stage verifier had checked) and
four lows, after a gpt verifier per stage and a gpt whole-PR reviewer had both passed it.
Cross-stage limits are exactly what per-stage review cannot see; so is the shape of live state
(existing volumes, data, permissions) that a fresh fixture never has. This review is the one
cost never cut: on 2026-09-27 every real gap across a multi-PR campaign came from it. The
supervisor rules on each finding (fix, accepted trade-off, ignore) before a fresh pi fix session
gets the fix set via `pi-drive`'s `templates/FIX-BRIEF.md`.

## 6. Traps, each seen once

- (2026-09-29) Plan-check findings appended to the brief as "Amendments from the plan check". A
  reader going top down acts on the superseded text first; a rehearsal caught a would-be merge
  to main. After a plan check, rewrite the brief in one voice and delete what it replaced.
- (2026-09-29) An eval's judges cost more than its subjects: $58 of Claude scoring and review
  against about $29 of pi runs, and $52 went to protocol design before any run. Fix the judging
  budget first, and give the scoring to a second family so a Claude subject is not judged only
  by Claude.
- Handing off a *design* instead of a brief: the implementer invents the protocol fields, the
  interface, the release order — differently from what was decided.
- "Additive" claims that aren't: changing an existing interface function's types re-pins every consumer.
- Editors that run cargo: eight overlapping builds took the disk to zero once. Only the
  gate-runner builds; editors' bash is for git/grep.
- The lane that skipped verification held all the must-fixes. Every lane gets a fresh verifier,
  and nothing relaxes it later: it is the cheap part, and trust shows up as fewer FIX REQUIRED.
- Six of nine questions at one stop were sound proposals the editor was forbidden to act on. The
  stop rule must name contract surfaces; everything inside a crate is the editor's.
- Paraphrased failures: the gate-runner returns the verbatim tail and names the lane, or says
  `unknown` and throws — the orchestrator routes by hand.
- Whole-file reads of multi-thousand-line files, Python-heredoc edits, and parking a big context
  through a multi-hour CI wait are the three ways a run burned 100M+ tokens.
- "Fetch fixtures in the PR worktree" came before "create the PR worktree" — the run stopped.
- The kickoff never said its cwd; from the brief's own directory every path failed.
- "Chart bump" was both a lane task and a stop condition — the run stopped.
- The brief said sccache; the machine said kache — the run stopped. Point, don't restate.
- The wrapper example in the brief was the exact env var the machine rule forbids — contradiction
  inside one sentence.
- The host wrapper does not exist inside a Linux container — say containers build plain.
- "Run the harness" needed a rebase first (an edit, which the orchestrator may not do), and the
  patch carried a hunk from another repo.
- The acceptance grep for a common word matched the brief's own new field and a third party's API.
- The reviewer's prompt allowed spawning; its frontmatter didn't.
- Provider ids: `openai-codex/gpt-6-sol`, not `openai/…`. Read them, don't guess.
- An expired Anthropic login killed a gpt run because two agent files still said Anthropic.
- Editors forbidden cargo cannot update `Cargo.lock`; the first `--locked` check on the merged
  branch refuses. The assembler owns the minimal lock update (`cargo check -p` without
  `--locked`, diff must be additions only), never `generate-lockfile`.
- pi-subagents `resume` inherits the original child's `output` path; a resumed fix step in a
  workflow collides with its editor's artifact. Give every resumed step its own `output`.
- Seven stops on one swarm: each was a different category, and each fix was a patch on the
  previous patch. After the third stop, change the shape, not the brief.
- The design's interface used reserved keywords and an invalid variant; nobody had run its
  parser on it. Parse the contract before the brief exists.
- "A config key for the path" and "one byte budget" — no key names, no values, no
  mandatory/defaulted call. The editor proposed; the run stopped. Name every key.
- Lanes A (protocol types) and C/D (their consumers) started in parallel from the same base; C
  asked for "one published seam" and stopped. Stage by consumption, write the seam.
- "Fresh open by path" and "path-less output" were each correct and contradicted on the second
  edit of the same asset. A scenario walk finds it; a per-rule review does not.
- The measurement stage ran with a lock regenerated broadly and upgraded unrelated crates; the
  accepted baseline had to be redone from the base lock with a minimal update. Say "restore the
  base lock, let cargo add only the harness's entries, diff versions against base" in the brief.
- (#321) Codex unknown events and items became fatal where `main` ignored them; the contract said
  "reject unknown required semantic events" and the driver's own test asserted the regression.
- (#321) The SSE framer rescanned and memmoved the partial line on every chunk; Codex
  `response.completed` carries the whole output on one growing line, so it was quadratic in task
  length. Per-item linear scans in the reducers did the same. Three verify/review passes missed
  both; only a cross-stage read follows one long stream end to end.
- (#321) The example's loopback mode could fall back to the real credential file.
- (#321) Redaction that blanked the whole body on any control char or at the read cap, byte
  budgets on error excerpts, `Option<i64>` token counts "so invalid values join semantic
  problems", and production JSON keys sorted so a golden survived `serde_json/preserve_order`
  arriving through a dependency's feature unification. Each is a row in §Don't write this.
- (#321) Timing assertions in tests flake on CI runners and slow hosts; assert structure and order.
- (#321) CHANGELOG `Fixed` entries for bugs the same PR introduced; `Fixed` is for released code.
- `$SHA:crates/...` in zsh: `:c` is a modifier and eats the path. Use `${SHA}:path`.
- The planner's seam sketch said `Result<_, ProtocolError>` where the real client returns
  `ClientError` with execution-uncertainty semantics, and named a type that already existed as a
  re-export. Fact-check seams; never write a signature from memory.
- A brief mandated a platform-only flag unconditionally and the run stopped on the other
  platform. State the platform matrix per mechanism.
- Stage-1 whole-workspace gate on a change that widens a signature consumed by stage 2: red by
  construction. Scope stage gates to the stage's crates.
- A cheap invention audit after a fable design + fable review + planner pass still found ~50
  choices and two planner errors. It is the cheapest check in the pipeline; never skip it.
- `cargo package --workspace` run locally at two heads of the same unreleased version: Cargo's
  tmp-registry fingerprint stays Fresh across re-extraction and the verify step compiles against
  the old rlib. Delete `target/debug/.fingerprint/<crate>-<hash>` (the tmp-registry unit's hash)
  and `target/package/`; not a kache fault though the diagnostics print `/kache/...`. Better:
  don't run packaging locally before the last stage (D19 in the asset packet).
- `#303` (workspace-wide `deny(unwrap_used)`) merged mid-run under ~9k unrebased lines. Rebase
  per stage.
- A 1200 s foreground tool deadline killed the driver mid-stage-2; the recovery cost a turn and a
  tarball of partial state. Background + log file for anything over a few minutes.
- (2026-09-20 fleet) A bare `curl` to crates.io returns 403 from the edge; a verification step
  written that way reports a successful publish as broken. Send a descriptive `-A` User-Agent.
- `pgrep -fl 'cargo|rustc'` as a "no foreign builds" gate matches any process whose environment
  holds `.cargo/bin` in `PATH`. Use `pgrep -x`.
- A bare `gh pr create` prompts for the body and hangs a non-interactive driver; always
  `--title … --body-file …`.
- A re-pin brief must name every pinned crate, dev-dependencies included; one that names only
  the obvious family leaves the rest behind and the tests fail to compile against the new API.
- A build script that pins hashes of contract files panics on drift. Put "read `build.rs` if
  present" in a refresh child's read list.
- A release job with a fixed timeout cannot absorb tests that recompile a component per test.
  Fix the tests (one compile cache per test binary), not the timeout.
- (2026-10-03) A consumer's adversarial review found its dependency's defect: the consumer's review
  showed the dependency logging every clock read, which the consumer's per-row clock use turned
  into millions of records per query. No core-only review could see it. When a
  unit consumes another unit's new API, its adversarial review reads the dependency's diff too,
  and the dependency's release waits for it.
- (2026-10-03) A local build that differs from CI by platform (a Mac toolchain quirk CI on Linux
  never hits) belongs in the packet's `gate.sh`, copied from the repo's agent guide.
- (2026-10-03) A sol supervisor ran driver turns in the foreground; the bash tool's 3600 s timeout
  cut one off and cost a continue turn. The launch-and-wait block in `SUPERVISOR.md` is the pattern;
  for a unit whose gate builds a large component, the turn tripwire goes to 120 minutes.
