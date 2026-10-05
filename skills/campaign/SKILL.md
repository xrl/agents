---
name: campaign
description: Run one funded sub-campaign of a large multi-step code effort economically — a Claude coordinator that rules and lands, pi sol supervisors that watch, a pi GPT driver that builds, a fresh gpt-6-sol verifier per commit, and a few fresh Fable reads — from a folder of state files. Use when Xavier funds a sub-campaign, says "run the campaign", "continue sub-campaign N", or asks how to drive a big change cheaply across many steps. Not for a one-file change (one Opus agent), and not for writing the brief (pi-subagent-plan) or for the mechanics of one pi session (pi-drive).
---

# Running a campaign

**Claude decides; pi does.** Claude quota is the scarce resource, and a coordinator's own wakes are its largest line once supervision moves to pi. Every rule below either keeps Claude out of a loop or makes a Claude call count.

## Who does what

| Role | Model | Lives | Does | Never |
|---|---|---|---|---|
| Coordinator | Claude Opus, one session | until the next landing or 120k tokens, whichever comes first, then a fresh session from `RESUME.md` | rules on hand-backs by quoting or adding a decision, launches Opus for `hard` findings, lands, journals, reads spend | supervises a step; rereads a gate; polls; writes a brief, packet or re-check prompt pi can write |
| Brief drafter | pi `gpt-6-sol:medium`, one run | once per sub-campaign | RECON, BRIEF and DECISIONS drafts from DESIGN and the source; the coordinator rules, then the plan check and dry run | decides an owner question |
| Packet writer | pi `gpt-6-sol:medium`, one run | once per sub-campaign | DRIVER, SUPERVISOR, step prompts and verify templates from `templates/`; a sol rehearsal checks it | |
| Supervisor | pi `gpt-6-sol:high`, one session per step; a step that outgrows 120k tokens hands off from its state file | `pi-turn.sh` in the background from its own folder | launches driver turns, runs the verifier, sends fix/integrate/push prompts, runs the scoped re-checks, hands back hard findings | decides scope; edits the worktree; answers a stop without quoting a row |
| Driver | pi `gpt-6-sol:medium`, recipe A, `-nc -ne` | one session per step | edits, builds, commits, gates, easy fixes, witnesses for Opus fixes, pushes on ACCEPT | spawns agents; pushes before ACCEPT; edits Opus fix lines |
| Verifier | pi `gpt-6-sol:high` via `pi-dry-run.sh … bash` | fresh per pass | reviews exactly one commit range, tags findings `hard`/`easy` | cargo, writes |
| Opus | fresh `general-purpose` agent, `model: opus` | one step or one fix | the spine step; `hard` findings as code only | writes tests for its own fix; shares a worktree with a live writer |
| Fable | fresh `campaign-reviewer` | one read | plan check; whole-PR read (trial: Astra on the PR instead, once) | stays resident |
| Astra | pi `gpt-6-astra:xhigh` | once | cross-step review of the assembled unit | |
| Ship | pi sol supervisor + pi driver | once | prep, checks, PR, merge, tag, verify, the deployment rollout end to end once the owner has authorized pi to ship; the funding line quoted as authority | |

Routing owner-approved 2026-10-01 after sub-campaign 5 (Claude ≤ $69 of ≤ $82): the brief, the packet, the ship phase and all-easy fix rounds were Opus there and move to pi; expected Claude ≈ $35-40 on a unit that size. Claude keeps the spine, `hard` fixes, the plan check, rulings and landing.

Design-shaping steps (the one where the spine's types are set) may go to one Opus agent instead of the driver: on A2 of sub-campaign 4 the blind judge preferred Opus's spine; pi had the better tests and the better numbers, cost $5.26 of pi and no Claude. Mechanical steps go to pi.

## The folder

`campaign/` holds the state; a session that forgets everything resumes from it.

| File | Owner | Holds |
|---|---|---|
| `RESUME.md` banner | coordinator | what is running, what to read next |
| `JOURNAL.md` | coordinator, append only | every launch, ruling, landing and spend line, with the owner's words quoted |
| `LIMITS.toml` | owner (coordinator applies measured dials) | budgets, tripwire, models, disk floor, timeboxes |
| `NN-name/BRIEF.md` | written once, rewritten in one voice after the plan check | steps, landing model, routing, budget, stops, hold list |
| `NN-name/DECISIONS.md` | settled rows D1..Dn + red witnesses | the only thing a stop may be answered from |
| `NN-name/<unit>/STATE.md` | the unit's one writer | alive table (worktrees, sessions, PRs), intent before every push, next action |
| `<unit>/<step>/` | the supervisor | `SUPERVISOR.md`, `verify.tpl.md`, `supervisor-state.md`, `supervisor-decisions.md` (S-numbers), blockers, report |

## Before a step launches

1. `LIMITS.toml`: not paused, spend within the funded budget, free disk minus kache headroom over the floor, heavy builds under the cap.
2. A worktree cut from the integration head, upstream unset, fixtures fetched.
3. The step prompt: the row verbatim, the packages, the witnesses, what the previous step landed in one paragraph, "decide under ambiguity and record it; never end a turn with a question".
4. The verify template: `verifier-role.md` + the range + the row + the step's specific checks + **every coordinator ruling so far**, stated as "not findings". A ruling missing from the template is re-raised by the next verifier.
5. The supervisor packet from `templates/SUPERVISOR.example.md` (pi-drive's template, adapted: the supervisor runs the verifier itself, reads the driver's gate log instead of rerunning it, writes S-numbers in its own file, never in DECISIONS.md).
6. STATE alive table and a journal line, then `pi() { command pi -ne "$@"; }; export -f pi; pi-turn.sh <step folder> <session> openai-codex/gpt-6-sol:high <log> kickoff.md` with `run_in_background`, every path absolute (`pi-turn.sh` changes into the step folder before it writes the log).
7. For a release: list every repo that links the changed contract, not only the ones that implement it. A client that embeds the runtime or decodes the wire (an operator console, a CLI) is a fleet member and re-pins and releases with the providers. Leave one out only when the release provably changes no type it decodes, and say so in the plan.

## The coordinator loop

Wake only on a completion notice. A supervisor's notice comes at the end of its turn, up to 100 minutes, so a merge or a deploy inside the turn is invisible until then. Every status to the owner says when it was read ("as of 19:19Z") and what may have happened since; when the owner asks about a running lane, re-read its state file and the live artifacts before answering. On each notice:

| Event | Do |
|---|---|
| Supervisor ends with a report | read `supervisor-state.md` and its decisions log (did it decide anything it should have handed back?); land or queue the next step |
| Supervisor hands back | read `supervisor-blockers.md` and the verifier file only; rule; write `coordinator-ruling-N.md` with the exact next prompts; relaunch with a two-line resume |
| Third FIX REQUIRED | rule on the finding, not the count. Real and scoped → one fix turn and a **re-check scoped to that finding** (`templates/recheck.example.md`), not a full re-review. Pre-existing or unreachable in this step → carry it to a named step and write the carry into STATE and every later verify template |
| An Opus agent near 300k context | fresh agent from its `NOTES.md`; below that, resume it with SendMessage |

Rulings that recur: a fix re-check that raises new pre-existing defects is not grounds to block; the verifier's number is not the contract, the row is (sub-campaign 4: `null\n` vs `display(Null)` + newline); a test that cannot fail before the fix is kept as a pin when a later step can make the path reachable.

## Measuring both ways (when a step is worth it)

Same row, same decisions, same verifier; separate worktrees; neither may read the other. Judge blind: detached worktrees `-x`/`-y` by coin flip, reports and verify files redacted of model, tool, branch and PR names, the key in a file the judge is not pointed to. The judge returns findings per build, a verdict, fix-before-landing vs carry, and at most three ports from the loser. The winner's author makes the fixes as a second commit; a scoped re-check; the coordinator squash-lands. Record per-role spend, wall clock, passes and the verdict.

## Landing

Coordinator only, on the integration branch: `git merge --squash origin/<branch>`, one commit whose body keeps every `Changelog:` line one per physical line, `git diff --quiet HEAD origin/<branch>` must hold (tree identical), push, close the PRs with the landing SHA, reap worktrees with `df` before and after. The author pushes its own branch; the coordinator never pushes onto a reviewed branch.

## Closing

The closing session asks no question: a question at the end means reviving an expensive context to answer it (owner, 2026-10-05). The owner still decides the rules ("We should always strive to improve our rules by asking me", 2026-10-04); the closing step leaves the decisions where he can answer them without Claude:

1. **Lessons become an open PR.** One commit per lesson, each body carrying its receipt, on the skill's or rule file's repo. Leave it unmerged: his merge, edit or partial revert is the vote. Journal-only lessons get lost.
2. **Scope calls take the cheaper default.** Apply the no-spend or smaller option, file the alternative as an issue with a recommendation and its cost, and journal it as applied by default. He vetoes in any later session.
3. **Anything that cannot default goes in `OWNER-QUEUE.md`,** one item per heading with the recommendation and a line for his answer. The next session's `/loop` reads it first and acts on the answers.
4. **Ask live only while he is demonstrably present** (he wrote in the last few minutes), batched early, per standing order 2. Never as the last act of a session.

Every coordinator session ends, at a close or a clean stop, with a fenced `/loop …` command that runs in a fresh context: the next unit's, filled in (folder, scope, end state, version), or this unit's resume if it stopped early. Write the same command into the `RESUME.md` banner. Shape (owner, 2026-10-01):

```
/loop You are the campaign coordinator for <unit> (<scope>), funded per JOURNAL.md. Read campaign/RESUME.md, OWNER-QUEUE.md, <NN-name>/STATE.md and LIMITS.toml, and follow the campaign skill. <what to draft and check>, then drive <unit> to <end state: merged on main / vX.Y.Z released and live on the Pi>. No check-ins: decide under ambiguity and journal it. Wake only on completion notices. Write state before every wait.
```

## Spend

pi: `pi-usage.sh <worktree> <supervisor folder>` plus each verifier's printed `cost_usd` (dry runs have no session). Claude: by role, not model (pi-drive §Cost accounting). Project at every landing; journal a tripwire crossing; stop past the funded budget. Sub-campaign 4 actuals: ≈ $154 for 13 steps and ≈ 9,400 lines; pi ≈ $78 (≈ $4.60 per step of driver + supervisor, ≈ $1.20 of verifiers per step), Claude ≈ $76 (two coordinator sessions with ≈ 20 wakes, the A2 Opus build, two Fable reads, the ship supervisor). A sol supervisor session carried across resumes grew to $7: start a fresh one every few steps.

Claude's number is the coordinator session's `/cost`, which includes its subagents. ccusage 5-hour blocks count Claude only: never subtract pi from them (2026-10-02: reported $15, real $62).

### Where Claude money goes (rest of 6, 2026-10-02: $62 Claude, $47 pi)

Opus was $47, almost all of it 134M cache-read tokens: every tool call re-reads the whole context, so cost ≈ context size × calls. Three things drove it, and each has a rule:

1. **Size Opus steps at ≤ 800 changed production lines.** At a contract break the tests move with the code: S1b-1 was estimated at 1,400 and came to ≈ 4,000 gross. It took four Opus agents, three of them ending at the 300k cap, where every call re-reads the largest context.
2. **An Opus agent stops when production code compiles and its witnesses are green.** It commits and writes NOTES. The test fix-up, the full gate and the verifier go to a pi driver as the next step. The S1b-1c finish was exactly that work, and pi did it.
3. **The coordinator hands off after each landing, or past 120k tokens.** It writes STATE and prints its `/loop`, and a fresh session continues. One coordinator session ran six hours, with a context of several hundred k re-read on about 150 turns.

The Fable reads ($15) were worth it: they found the design break before the build, and the final read cleared the merge. Keep them.

## Things that bite

- The classifier refuses destructive git (`reset --hard`, deleting a remote branch). Cut a new worktree and branch instead and leave the old ones for the owner.
- The driver runs with `-nc`: no global context files. Put the machine's Rust rules in its read list (`~/code/xrl/agents/RUST_AGENT_RULES.md`).
- A pi turn is found by its pid file, never by `pgrep`.
- No heartbeat means a hung turn stalls the run until someone looks; none hung in sub-campaign 4.
- A subagent's completion notice can arrive before its hand-back message for the same turn; check the PR, not the notice.
- `gh run view`/`gh pr checks` from a non-repo cwd fail silently: always pass `-R <owner/repo>`.
- A prompt that says "amend" after a push diverges the branch: CI fixes are new commits on top.
- A driver that runs under DRIVER.md's third-FIX stop refuses a fix unless the prompt quotes the coordinator ruling that authorizes it.
- Grepping task output files can pull whole subagent transcripts into the coordinator's context; read only the named output of a Bash task.
- A Bash background task dies at 2 h. A pi supervisor turn that runs several steps outlives that, and its driver dies with it (the RG supervisor died mid-RG-b, 2026-10-02). Launch one supervisor turn per step.
- Launch a pi turn with `run_in_background`. A foreground `&` is killed as soon as the call returns.
- Deleting a live unit's `target/` forces a cold rebuild. Overlapped with another build, it dipped free disk from 69 to 13 GiB for a minute. Check disk when a build launches, never in the middle of one.
- When a pilot needs a core fix while a driver owns the core worktree, commit the fix on a side branch cut from the pushed head. The pilot pins to it, and the core step cherry-picks it. That keeps one writer per worktree.
- Start the PR's Fable read at the pushed head beside the unit's last CI wait, never after it: it needs the local head, not CI. A CI fix commit gets a scoped re-read of its delta, so the merged head is still the reviewed one.
- The classifier refuses `gh pr merge` into a shared workflow repo whose `@main` other repos call. Ask the owner for that merge up front.
- Start a step when its own dependency lands, not when the whole unit does. 2026-10-03: curl's typed-SDK migration needed only S1b on main but waited for S2, so the testkit defect it found surfaced hours late.
- Before a push, the driver runs CI's own steps for what it touched: every generated artifact CI byte-compares, every docs check its change triggers, `cargo doc` with `-D warnings`, `cargo deny`. The repo's own list lives in its agent guide. 2026-10-03: four CI reds (a rustdoc link, an advisory, generated bytes, an undocumented event) each cost a fix turn plus a CI cycle.
- A pi turn that dies on `fetch failed` twice is a network problem, not a model one. Hand the half-done easy fix to one Claude agent working from the uncommitted diff rather than retrying a third time.
- `gh pr merge --rebase` rewrites SHAs. A pilot that must pin to the merged commit waits for the merge, then pins to `mergeCommit.oid`.
- Every background probe, watch or poll loop runs under `timeout <s>`, never `while true`. A loop left by the v0.32 rollout session hit the WhatsApp webhook every 5 s for 23 hours; a day later its 15,000 refusals looked like a production fault and cost a diagnosis.
- Smoke-test probes come from each provider's own `help` or capability list, not from the CLI tool it imitates. The v0.33 gh probe used `--limit` and `--state merged`, which the gh provider does not take.
- No spans is not a broken exporter. Spans exist only when there is traffic: before calling a telemetry gap a fault, send one known request and look for its span (2026-10-04: a five-hour gap was a quiet evening).
- Proportion the ceremony. Config chores and small single-repo changes take a sol recon, then a sol supervisor + driver + one sol verifier per commit: no Fable plan check, no dry run. Four chore lanes landed that way on 2026-10-04 (curl grant, console assets, two homelab cleanups); the one fix round the verifier forced closed three real holes.
- pi's built-in `process` tool survives `-ne`, and a supervisor may prefer it, citing a harness rule over the packet. A driver started that way dies when the supervisor's turn ends. Every packet forbids the `process` tool by name. If a supervisor also refuses `nohup`, the foreground launch in `templates/SUPERVISOR.example.md` is the answer: it holds the turn open, which is the in-turn wait anyway (sub-campaign 8, PYTHON rulings 1-2).
- A supervisor that looks for other supervisors finds its own pi process and stops. It happened three times on 2026-10-04 (R1, ROLLOUT, CLEANUP), the third after the packet defined a duplicate as "a live pid file with no receipt, never your own process". Defining it does not work; forbidding the check does. Every packet says: do not check for other supervisors, the coordinator launches exactly one per lane; check only the lane's DRIVER pid files. The coordinator's launch or resume prompt names the session ("You are <session>, the only supervisor for this lane").
- A supervisor can launch its driver before it has created the driver's worktree; `pi-turn.sh` then exits 1 at `cd`. Packets say "create the worktree, then launch".
- Heavy-build counting in the launch wrapper alone misses builds that start later in a long turn: the python driver overlapped six fleet builds (sub-campaign 8). The driver counts live builds before each heavy build, not only at launch.
- A version bump changes every checked example `.wasm`: the crates' exact pins reach the guest build. The byte proof is the local pinned rebuild against CI's pinned rebuild, never against the old bytes; the WIT imports and exports must match the previous release. Sub-campaign 9's SHIP stopped on a rule that compared against the old bytes.
- A homelab commit that touches both `apps/dekopon.yaml` and `manifests/dekopon/` is two Argo applies: app-of-apps owns the first, the child app the second. If the child syncs first, it prunes what the old pod template still mounts, and the pod wedges. Chain the merge with the app-of-apps hard refresh and sync. Touch the child only once its `targetRevision` shows the new chart. Sub-campaign 9's rename rolled out that way with a 54 s outage.
- The PR image check builds from the latest published release, so a binary rename fails it until the renamed release exists. Gate PR mode on the release version, and delete the gate in the first PR after the tag (sub-campaign 9, R9-15 and #464).
- Start a dependent lane from a `timeout`-bounded until-loop on the artifact it needs, not from the previous lane's report. In sub-campaign 9, CONSOLE started on a crates-ready watcher in the middle of SHIP and finished first.
- Before reaping a worktree at a landing, grep the later steps' packets for its path. A packet that names it as a read-only cwd stops its supervisor at launch (sub-campaign 2: SMOKE stopped because it named the V worktree just reaped after the merge). Repoint the packet to a detached worktree at the release tag.
- Console smoke runs `dekopon-console --agent <agent> --no-color` (the RPi's is `ville-github`) and the provider's own command word (vm's is `ssh`). A bare `dekopon-console` attests as a subject with no attestor and is refused `no attestor authority for this subject`: an invocation error, not an owner credential refusal (sub-campaign 2 SMOKE ruling 2). A provider whose only ReadOnly call needs an existing async job (vm `ssh --job`) is proven at help level plus the direct API path; journal the gap.
- Every Opus code-only fix prompt says: a fix to unreleased work carries no `Changelog:` line; run `cargo fmt --all` before committing; the driver may change Opus's lines only by `cargo fmt --all` output, taken verbatim (it may remove tokens such as redundant braces). Sub-campaign 2 V2R: `Fixed` lines and a "no token changes" ruling cost two supervisor turns.
- Dashboard SQL never selects a field that is emitted only on a rare path: OpenObserve fails the whole panel with HTTP 400 `unknown field` until the first such record lands. The ASSEMBLE dashboard audit checks each selected column has been emitted by the smoke's ordinary traffic (sub-campaign 2: GUEST_BY_SESSION and `vm_runner_guest_timed_out`, homelab #172).
- Schedule a post-rollout check at the earliest point its witnesses exist, not at a fixed "+24 h". That point is the latest predicted event it must see (an idle reap at 30 min) plus one ordinary hour clear of rollout and smoke traffic. Run it from the closing session, not a fresh one the next day. A volume bound measured in an hour with no unit traffic bounds only the baseline, so the report also gives the per-session record count from the smoke. Sub-campaign 2: the owner waived a 19-hour wait; the check ran about 5 h after the rollout ($0.20 of pi), saw the idle end, and got 1,440 records/day from `telemetry.health` alone.

## Routing decided for sub-campaign 6 (owner, 2026-09-30)

Opus builds the seam step where shape decides; pi fans out the mechanical steps with one verifier pass per commit; Astra once on the assembled unit; Fable once on the PR. From sub-campaign 4: third pi rounds cost ≈ $40-50 of pi and 2-3 h, and the coordinator's wakes ≈ $15-20 of Claude. Confirmed at the 04 close.

**Fix rounds (owner, 2026-10-01, replaces "second round to Opus"):** split by the verifier's `hard`/`easy` tags. Opus fixes only hard findings (code, no tests); the pi driver then witnesses the Opus fix, does the easy list and gates; an all-easy round never wakes Opus; a failed re-check goes to Opus. One writer per worktree at a time. The rule and the prompts: `pi-drive` §Fix rounds split by difficulty and `templates/SUPERVISOR.example.md`. Sub-campaign 5 (≤ $82, five Opus fix rounds, two with no hard finding) is why.

## Standing orders (owner, 2026-09-30)

1. A tripwire inside the funded budget is a journal line, not a stop; only spend past the budget and owner-only items block.
2. Ask a foreseeable owner decision the moment a projection shows it, batched, with a recommendation.
3. A blocking question left unanswered: journal it, write every state file, stop cleanly, so the owner answers in a fresh short session.
4. **Ship without the straggler (owner, 2026-10-03).** A non-essential repo does not hold up a fleet rollout. When one is stuck (a release snag, a failing review, an owner-only step), ship without it and journal why it blocked.
