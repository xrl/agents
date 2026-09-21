---
name: pi-subagent-plan
description: Turn a big, decided piece of work into a self-contained brief plus pi-subagents agent files, a flat workflow script and a kickoff prompt, so Xavier can hand it from Claude Code to a pi session running one cheap/fast model (gpt-6-astra) with the reasoning level as the only tier — nothing Anthropic in the pi run. Use when Xavier says "hand this off to pi", "write a handoff/brief for pi", "offload this to a cheaper model", "pi subagents plan", or asks whether something is "suitable for handing off to a pi/gpt agent". Claude Code only — this is for AUTHORING the plan from Claude; it is not for running inside pi, not for one-file changes (one agent), and not for review-only work (/code-review).
argument-hint: "[design/plan path or PR/issue] [target repo]"
arguments: [target]
disable-model-invocation: false
user-invocable: true
---

# Writing a pi-subagents plan from Claude

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
found, what you chose, what you rejected), keep going; the PR body carries that section*. The
stop list is four vivid items (forking or patching a dependency, moving a contract away from the
decisions file, reversing a keep/delete, owner-only actions), never a taxonomy the model has to
classify against. The literal "stop for any decision the table does not answer" posture cost the
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
   (`execution/stage-N-verify-P.md`), never appended to a growing file the driver rereads.
4. **Rebase onto `origin/main` at the start of every stage**, not only before the PR. A
   workspace-wide lint that merges mid-run is ten minutes at stage 2 and a fix pass at the end.
5. **Independent stages run in parallel.** Measurement (compute) and whole-PR review
   (read-only) do not depend on each other; the supervisor runs one in the background while the
   driver does the other. Say so in the stage list.
6. **Stages of ≤ ~1k changed lines.** A 2.3k-line stage produced five findings and a long gate;
   two halves verify faster, test with `-p`, and fail smaller.
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
    running; poll it.** A print-mode turn otherwise ends with the child orphaned (`pi-drive`).

## 0. Gate: is it ready to hand off?

Say no — and say what is missing — unless all of these are true. Half of a handoff is refusing to
write one too early.

- **Decisions are settled and written down** as a table the implementer must not relitigate.
  Every open question either has the owner's answer or is an explicit stop condition.
- **A fresh adversarial pass has run on the design** (a different fable agent than the designer,
  told to break it, with `file:line` evidence). Its "facts an implementer must be told" list goes
  into the brief verbatim; its amendments are applied to the design *before* the brief is written.
- **The contracts are concrete and machine-checked**: WIT parsed with `wasm-tools component wit`
  on the real files (a `contracts/` folder in the brief dir that lanes copy byte-for-byte), Rust
  seams as signatures, config keys named against the existing struct and its `rename_all`; every
  constant that moves or dies is named with its locator; every consumer of a deleted convention
  is enumerated. Prose WIT in a design is pseudocode until it parses: `as`, `list` and `stream`
  are keywords, a variant case carries one payload, `error` must be defined — the asset run
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
- **The invention audit is empty** (§5).
- **The repo carries the tone and the rubric, the brief points at them.** `AGENTS.md` §"Rust
  guidelines" (yes/no pairs) and §"Review checklist" (tagged findings, two fix passes, the lane
  report's `Choices I made` and `Limits` headings) are what let an editor decide crate internals
  itself; the brief's stop rule names only contract surfaces. Mechanical rules are workspace lints,
  not verifier reading.
- **The baseline is stated**: which PRs are assumed merged, which SHA, which measurements to beat.
- **A dependency move has been diffed, not just named.** When the work re-pins a published crate
  (SDK 0.15 → 0.18), the recon diffs the two published manifests' features and dependencies
  (`cargo info`, or the registry `Cargo.toml`s under `~/.cargo/registry/src/`) and the brief
  names what changed. SDK 0.18.0 dropping Wasmtime's `cache` feature was visible there and cost
  python 3.5 hours of release-job timeouts because nobody looked.
- **What stays with the owner is explicit**: releases, tags, published packages, private-repo
  commits, paid or real external calls, merges. Agents open PRs; they never merge or approve. Say
  the other half too: version fields edited inside a PR are ordinary work — "chart bump" read
  literally is a stop condition.
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
6. **Landing order** across repositories, with why no other order avoids a broken window.
7. **Acceptance** — falsifiable: numbers to beat (re-run the harnesses), fixtures that fail today
   and must pass, and greps that must come back empty **naming retired identifiers, never common
   words** (a grep for `attachments` matched Discord's wire field and the brief's own new
   `attached` field), with the look-alikes that legitimately survive listed beside them.
8. **Stop and report** — the conditions under which the agent stops instead of working around.
   Every noun here must mean the same thing it means in §5 ("bump", "release", "wrapper").
9. **Not in scope.**
10. **Execution plan** — §2 below.
11. **Running it on pi-subagents** — §3 below.

Style: locators everywhere (`path:line @ ref`); "verify with `git show`" once, not per line; no
narrative history; decisions as facts, not as arguments. Artifacts the brief reuses are named as
they exist: branch names and SHAs, not "the patch"; a patch that spans two repos says which hunk
belongs where.

## 2. Execution plan (roles, levels, preflight, sanity, gates, report)

**Roles and levels.** The whole pi run uses one cheap/fast model (`openai-codex/gpt-6-astra` as
of 2026-09-17; nothing Anthropic — Xavier keeps the Anthropic spend in Claude). The lever is the
reasoning level (pi: `minimal ~1k`, `low ~2k`, `medium ~8k`, `high ~16k`, `xhigh ~32k`, `max`):
mostly medium; the command runner low; reviewers high/max. Provider ids are `<provider>/<model>`
and the provider segment is not guessable — read `subagent({action:"models"})`.

| Role | Level | Rule |
|---|---|---|
| Orchestrator | the parent pi session, medium | edits no code; runs preflight; routes; runs the last tiers; opens the PR |
| Lane editor (one per lane or prep stage) | medium | **never runs cargo**; edits only its seams; `contact_supervisor` → `need_decision` instead of guessing |
| Gate-runner | low | the **only** agent that runs cargo; merges lane branches; returns JSON with verbatim tails and an attributed lane |
| Verifier (one per lane) | high, **fresh context**, read-only | adversarial acceptance of one lane's diff; a late lane gets one too |
| PR reviewer | max, fresh context | whole assembled PR; coherence across lanes; ≤ 2 fact-checkers (needs `subagent` in `tools` and `allowNestedSubagents: true`) |
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
and which `target/` were removed.

## 3. pi-subagents specifics (v0.70.0 installed at `~/.pi/agent/npm/node_modules/pi-subagents`; its `docs/` are the reference, re-check them when in doubt)

Verified there on 2026-09-20: `outputSchema` is a real launch field on `runs.run`/`runs.all`
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
command}]} })`; `{ action: "validate", workflowScript|workflowScriptPath }` before running;
`{ action: "status" | "steer" | "interrupt" | "resume" | "stop", id }` for control;
`maxSubagentSpawnsPerRun` defaults to 64 per run tree.

**Workflow scripts** (`workflowScriptPath`): top-level JS with `await`; `runs.run(key, {…})`,
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

## 3b. Offer to drive it

After the kickoff and rehearsal, **offer to drive the pi session from Claude Code** with the
`pi-drive` skill: fable as supervisor issuing one stage per turn and answering non-hard stops
from the decisions file, gpt-6-astra as the driver. Xavier wants this pairing ("super high level
fable with super cheap gpt"); the alternative is him pasting prompts and each stop costing a day.
Say which path (print or RPC) and why in one line.

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

Three cheap passes, each a fresh read-only agent (sonnet or the target model at low effort):
the **ops rehearsal** below, the **invention audit** and the **scenario walk**.

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
stops (an undefined WIT `error`, an unnamed config key, an A↔C seam) would have surfaced for a
few cents instead of a stalled run.

**Scenario walk** — §0's end-to-end scenario against the design: which rule each step touches,
whether the rules compose, with `file:line`.

**Ops rehearsal** —

Spawn a cheap, fresh, **read-only** agent (sonnet is enough) with the kickoff prompt plus: "DRY
RUN: mutate nothing; walk every step exactly as a literal executor would, with nothing but the
files it has; per step list the exact commands, the directory, every file/worktree/branch/tool/
credential it needs and whether it exists now, and every point where you would stop, guess, or
do the wrong thing. Also walk the brief's acceptance section and every agent file." Fix the brief
until the walk has no stops. The rehearsal must cover the acceptance section and the agent
frontmatter, not only the kickoff — the first rehearsal walked the kickoff and missed an
acceptance grep that contradicted the brief's own contract.

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
Cross-stage limits are exactly what per-stage review cannot see. Its findings then go to a fresh
pi fix session via `pi-drive`'s `templates/FIX-BRIEF.md`.

## 6. Traps, each seen once

- Handing off a *design* instead of a brief: the implementer invents the protocol fields, the WIT,
  the release order — differently from what was decided.
- "Additive" claims that aren't: changing an existing WIT function's types re-pins every provider.
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
- Provider ids: `openai-codex/gpt-6-astra`, not `openai/…`. Read them, don't guess.
- An expired Anthropic login killed a gpt run because two agent files still said Anthropic.
- Editors forbidden cargo cannot update `Cargo.lock`; the first `--locked` check on the merged
  branch refuses. The assembler owns the minimal lock update (`cargo check -p` without
  `--locked`, diff must be additions only), never `generate-lockfile`.
- pi-subagents `resume` inherits the original child's `output` path; a resumed fix step in a
  workflow collides with its editor's artifact. Give every resumed step its own `output`.
- Seven stops on one swarm: each was a different category, and each fix was a patch on the
  previous patch. After the third stop, change the shape, not the brief.
- The design's WIT used three keywords (`as`, `list`, `stream`) and a two-payload variant; nobody
  had run `wasm-tools` on it. Parse the contract before the brief exists.
- "A config key for the path" and "one byte budget" — no key names, no values, no
  mandatory/defaulted call. The editor proposed; the run stopped. Name every key.
- Lanes A (protocol types) and C/D (their consumers) started in parallel from the same base; C
  asked for "one published seam" and stopped. Stage by consumption, write the seam.
- "Fresh open by path" and "path-less output" were each correct and contradicted on the second
  edit of the same asset. A scenario walk finds it; a per-rule review does not.
- The measurement stage ran with a lock regenerated broadly and upgraded unrelated crates; the
  accepted baseline had to be redone from the base lock with a minimal update. Say "restore the
  base lock, let cargo add only the harness's entries, diff versions against base" in the brief.
- `$SHA:crates/...` in zsh: `:c` is a modifier and eats the path. Use `${SHA}:path`.
- The planner's seam sketch said `Result<_, ProtocolError>` where the real client returns
  `ClientError` with execution-uncertainty semantics, and named a type that already existed as a
  re-export. Fact-check seams; never write a signature from memory.
- `MSG_CMSG_CLOEXEC` is Linux-only; the brief mandated it unconditionally and the run stopped on
  macOS. State the platform matrix per mechanism.
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
- Providers pin the core crates (`dekopon-core`, `-capability`, `-broker`, `-broker-host`,
  `-shell`) as exact dev-dependencies at the workspace version; a re-pin brief that names only
  `dekopon-provider-*` leaves them behind and the tests fail to compile against the new API.
- python's `build.rs` pins SHA-256 hashes of its WIT files and panics on drift; a WIT refresh
  must recompute them. Say "read `build.rs` if present" in the child's read list.
- A new provider whose name equals an interface it imports (`asset` ↔ `dekopon:asset@0.1.0`)
  needs a distinct own package name (`dekopon:asset-provider`); the "name it like ripgrep does"
  rule collides there.
- The shared provider release job has `timeout-minutes: 30` and rebuilds from a clean checkout;
  a component whose tests recompile it per test (RustPython after the SDK dropped Wasmtime
  `cache`) cannot fit. Fix the tests (one compile cache per test binary), not the timeout.
