# pi-subagent-plan: material moved out of SKILL.md

Receipts, incident narratives and the former §6 trap list, removed verbatim from [SKILL.md](SKILL.md) on the rules diet (dates kept). Not standing rules; no entry point tells an agent to read this first.

## Former §6, in full

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

## Opening: why the plan folder

Why not
the product repo: repo docs describe what is implemented, a plan says on line one that it
is not, its locators rot with every merge, and the execution artifacts beside it cannot be
committed. The multi-LLM plan was opened as a docs PR (#319) and closed unmerged for this reason;
what lands in git afterwards is the changelog, the upgrading note, the rewritten implementation
docs and the commit bodies (the repo squash-merges, so the squash message is the record). The PR
body is a short summary plus test evidence: no D-numbers, no paths on the driver's machine.

## 0a swarm history (asset run: nine stops, seven swarm stops)

The literal "stop for any decision the table does not answer" posture cost the
asset run nine stops; the same model decided crate internals fine when allowed to. A swarm (`templates/lanes.workflow.js`) earns its
orchestration only when every lane is independent at compile time *and* the editors are trusted
to decide crate internals *and* wall-clock matters more than stops. The asset run stopped seven
times in three days on the swarm shape (grep gate, container wrapper, contracts, seams, platform,
stage gating, pi output-path collision) and produced its first 2,100 committed lines only once
the stage-1 lanes ran; the driver brief (`~/code/dekopon/asset-design/pi/DRIVER.md`) replaced
it. A driver is slower per PR and has zero seam or orchestration failure modes; the "editors never
run cargo" rule exists for eight parallel builds, not for one.

## 0a fleet receipt

The 0.18.0 fleet ran
the first eleven providers through `runs.all` children and lost three of them to the parent's
turn ending, a transient provider error, and a stop routed through the parent; the four
providers that ran as parallel sessions (decision F9) lost none. Workflow scripts

## 0b retro opening

Three days on the asset core PR; the code was about one of them. The rest was stops routed
through Xavier, one shape reset, infrastructure detours and repeated gates. Quality came from two
things only: machine-checked contracts before the run (nine stops fell to zero code-level stops)
and a fresh read-only verifier per stage (every pass returned real contract bugs). Keep those,
and spend nothing else:

## 0b.3 receipt

A
   named survivor is a claim: for every deletion the verifier greps the deleted code's
   distinctive literals (ids, error codes, config keys, secret shapes) into what remains and
   finds them asserted before accepting. A cheap verifier approved losing the only test of a
   security property on 2026-09-27.

## 0b.6 narrative

A 2.3k-line stage produced five findings and a
   long gate; two halves verify faster, test with `-p`, and fail smaller. #321's brief wrote
   "about three thousand changed lines" into its own stage 2 and the stages landed at 1.5k–5.1k;
   the planner splits

## 0b.6 estimates

the driver splits one that grows past 1.2k,
   and the supervisor's `pi-stage-check.sh` refuses the rest. Line estimates run low: driver
   stages landed at 2.3x and 2.8x their estimates on 2026-09-29. Multiply the planner's
   estimate by 2.5 before applying the cap. Dollars ran under, because driver tokens are cheap.

## 0b.7 rationale

Design and review documents are fable-written and fable-reviewed, and were
   the bulk of the token bill; the driver only ever needed the decisions.

## 0b.8

"A build failure
   whose output names kache" parked the 0.18.0 fleet on an ordinary compile error whose
   diagnostics carried the `/kache/...` path remap. Facts like that remap belong in the machine
   rules file the driver already reads, not in a stop clause; a literal driver will match the
   words.

## 0b.9

Left alone, drivers wrote over a hundred
   evidence JSON/log files for eleven providers. Say:

## 0b.11

#321 pushed over two `FIX REQUIRED` reviews and then landed a
    412-line commit no reviewer saw.

## 0b receipt

Receipt: #321 (2026-09-22), whose paranoia patterns came from our own rules, is why
`DRIVER.md` §Don't write this names concrete bans; "don't be paranoid" alone does nothing to a
literal model.

## 0 gate: parsed contracts

— the asset run
  stopped on all three.

## 0 gate: seam sketch

The planner's sketch of a widened
  `invoke` changed its error type by accident and collided with a re-export; both stopped the run.

## 0 gate: scenario walk

The asset design's "fresh open by
  path" and "path-less output" were each fine alone and contradicted on the second edit.

## 0 gate: consequence walk receipt

The
  multi-LLM plan (2026-09-22) had zero wrong locators and still yielded ten seam findings at
  packet time, every one a second-order effect.

## 0 gate: chat steering

Chat steering
  (2026-09-26) folded messages into three records and found each limit one review round at a
  time; a supervisor cap on the whole journal line regressed long answers.

## 0 gate: other clients

#321's D34 bound OpenRouter continuations to the upstream provider; no
  other client (Vercel's provider, pydantic-ai, Zed, LiteLLM, Cline) does, and multi-step tool
  turns failed at random under default load balancing. They forward `reasoning_details` and send
  `session_id` for sticky routing. The recon agent does this lookup.

## 0 gate: forward compat receipt

A
  contract line like "reject unknown required semantic events" is how #321 made Codex's unknown
  events fatal, with the driver's own test asserting the regression.

## 0 gate: tests fail on old code

The cwasm fix's decision read "the load fails and
  the error names the path": the bug already did exactly that, one implementation wrote the test
  to the letter, and it passed on the old code (2026-09-29). Where a decision turns on a check
  ("if the object exists"), say what a failed check means; two implementations of one decisions
  file diverged on `exists()` against `try_exists()`.

## 0 gate: refs moved

: refs moved under three packets in one
  afternoon on 2026-10-03, and one move (a branch becoming an ancestor of `main` through another
  session's ours-merge) turned a planned merge into a silent no-op that would have deleted the
  feature. `git merge-base

## 0 gate: dependency move

A dropped compile-cache feature was visible there and cost one consumer
  3.5 hours of release-job timeouts because nobody looked.

## 0 gate: classifier

"chart bump" read
  literally is a stop condition. **The auto-mode classifier enforces this on the coordinator
  too:** merging a PR that only a sol verifier read ("Merge Without Review") and pushing a
  release tag ("Create Public Surface") were refused on 2026-10-03; PRs with a Fable review merged.
  A release plan

## 1.7 acceptance

"When unsure, keep it" over a fuzzy unit returned a 1.7% cut
   against a ~30% target; the per-unit version returned 12× more (2026-09-27).

## 3a recon receipt

First graded run 2026-09-29: the model-card recon, 235 rows through a headed browser for $1.29, every one of seven spot-checked numbers right. Grade two more; sonnet `Agent` is the measured fallback

## 3a architectural receipt

2026-09-29: critical error in each of three plans, about $3 each

## 3a types row

| the eval scored exactly this: the order of work added 1.4 points for 4 cents, a Claude-written sketch plus shape review added 0.25 for 6 to 10 times the run cost. No per-stage sketch |

## 3a receipt

Receipt, 2026-09-29: Claude $240 against pi $116; Opus supervisors ($70) cost more than the
drivers that wrote the code ($60); the reviews and plan checks found every real defect.

## 3a effort receipts

Receipts: 2026-09-29, the cards put `gpt-6-sol`'s knee at `high`, the steering eval
(`~/code/dekopon/steering-eval/REPORT.md`) found `medium` held; dry runs went up from low to high
(sol's factual error rate 11.4% low, 5.1% high). 2026-09-30, the owner moved the driver from
`gpt-6.1-sol` to `gpt-6-sol` at `medium`: same hidden pass rate and cost, 1.85x faster, 1.5 lower
blind on pipe-type shape (so a spine step goes to Opus). As drivers, `gpt-6-astra` ended two of
four runs with a question and no code; Opus scored highest blind at twice the cost.

## 3b why

Xavier wants this pairing ("super high level
fable with super cheap gpt"); the alternative is him pasting prompts and each stop costing a day.
Say

## 3b2 receipt

One capture run stopped a shared app container first and then found, one turn at a
time, a pending-migration 500 and a refused host: two round trips and a longer outage of the
shared container.

## 3c rubric

All 21 pair children of one
  run read a 15 KB browser skill first, about 370 KB of context spent on nothing.

## 3c schema

One
  eval child returned 106 KB of text.

## 3c driver

That held on 2026-09-23: 174 calls, zero image reads.

## 5 sol vs sonnet

**Sol against sonnet, one frozen brief, same prompt (2026-09-29).** Sol at high: 119 s, 39 tool
calls, $0.40. Sonnet: 144 s, 12 tool calls. Of 27 real findings, 13 were found by both, 7 by
sol only and 7 by sonnet only, so each alone caught about three quarters. Neither was the
better one: sol alone found that a failed cell and a model mismatch pass silently; sonnet alone
found that the batch script ran two at a time, which would have broken the pairing the decision
rule rested on, and that nothing checked the effort actually applied. They miss different
things, so both run on every brief (owner, 2026-10-08, gauntlet R1; reverses the 2026-09-30
"sol only" cut).

## 5 cost

A packet rehearsal cost $0.10 at low on 2026-09-29.

## 5 rewrite receipt

(sub-campaign 4: a $0.30 sol rehearsal caught a rewrite telling a `-ne`
driver to spawn its own verifier)

## 5 amendments

Once an adversarial reviewer declared a real
helper nonexistent and rewrote a decision around it; the rehearsal found it in the source.

## 5 invention audit

This is where the asset run's three
stops (an undefined interface type, an unnamed config key, an A↔C seam) would have surfaced for a
few cents instead of a stalled run.

## 5 pre-chew

(Sub-campaign 2 re-plan, 2026-10-05:
rehearsal patches hand-wrote the import and smoke commands, and the next rehearsal found `jq .id`
where the API returns `sessionId`, a bug a driver reading `openapi.yaml` would not have made.)

## 5b first run

First run: PR #305, 15 minutes, ~240k tokens,
one high (a per-request ceiling the design stated and no per-stage verifier had checked) and
four lows, after a gpt verifier per stage and a gpt whole-PR reviewer had both passed it.
Cross-stage limits

## Opening worked example

Worked example:
`~/code/dekopon/asset-design/{HANDOFF.md,pi/}` (2026-09-17), whose first run stopped seven times
on defects in the brief — every one is a rule below.

## 3a fix-round why

| sub-campaign 5 sent every second round to Opus: five Opus fix agents, mostly writing tests, two rounds with no hard finding (owner, 2026-10-01) |

## 3a interfaces why

| opus's API sketches graded A on 2026-09-28; fable's design reviews found the P1s. The designer never reviews its own sketch |

## 3a spine why

| sub-campaign 4's A2 built both ways: the blind Fable judge landed Opus's spine; pi kept the old plumbing with pipes bolted on |

## 3a stops why

| four or five per day decided the outcome on 2026-09-20: the false kache stop, the python timeout cause, the fan-out shape reset |

## 3c cheap pass

Luna shortlists and classifies. Sol re-reviews every unclear or
  disagreeing pair before a verdict reaches a PR. Luna picks images well and calls verdicts
  generously (`agent-routing` has the numbers).

## 3c ids

A hand-written pairs workflow ran Sol on
  the retired `gpt-5.6-sol`; grep the script for `gpt-5.6` before launch.

## 5 sequence

The sequence that worked: draft, rulings, plan check and dry
run in parallel, rulings on findings, one-voice rewrite, **one** rehearsal (below), hand off. The files are in
`~/code/dekopon/effort-tuning-design/execution/rehearsal/`.
