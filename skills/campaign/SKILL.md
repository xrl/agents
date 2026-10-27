---
name: campaign
description: Run one sub-campaign of a large multi-step code effort economically — a Claude coordinator that rules and lands, pi sol supervisors that watch, a pi GPT driver that builds, a fresh gpt-6-sol verifier per commit, and a few fresh Fable reads — from a folder of state files. Use when Xavier starts a sub-campaign, says "run the campaign", "continue sub-campaign N", or asks how to drive a big change cheaply across many steps. Not for a one-file change (one Opus agent), and not for writing the brief (pi-subagent-plan) or for the mechanics of one pi session (pi-drive).
---

# Running a campaign

**Claude decides; pi does.** Claude quota is the scarce resource, and a coordinator's own wakes are its largest line once supervision moves to pi. Every rule below either keeps Claude out of a loop or makes a Claude call count.

## Who does what

| Role | Model | Lives | Does | Never |
|---|---|---|---|---|
| Coordinator | Claude Opus, one session | until the next landing, or the first natural boundary (a batch launched, a brief frozen) past 200k tokens with a hard stop at 250k, then a fresh session from `RESUME.md` | rules on hand-backs by quoting or adding a decision, launches Opus for `hard` findings, lands, journals, reads spend | supervises a step; rereads a gate; polls; writes a brief, packet or re-check prompt pi can write |
| Brief drafter | pi `gpt-6-sol:medium`, one run | once per sub-campaign | RECON, BRIEF and DECISIONS drafts from DESIGN and the source; the coordinator rules, then the plan check and dry run | decides an owner question |
| Packet writer | pi `gpt-6-sol:medium`, one run | once per sub-campaign | DRIVER, SUPERVISOR, step prompts and verify templates from `templates/`; a sol rehearsal checks it | |
| Supervisor | pi `gpt-6-sol:high`, one session per step; a step that outgrows 120k tokens hands off from its state file | `pi-turn.sh` in the background from its own folder | launches driver turns, runs the verifier, sends fix/integrate/push prompts, runs the scoped re-checks, hands back hard findings | decides scope; edits the worktree; answers a stop without quoting a row |
| Driver | pi `gpt-6-sol:medium`, recipe A, `-nc -ne` | one session per step | edits, builds, commits, gates, easy fixes, witnesses for Opus fixes, pushes on ACCEPT | spawns agents; pushes before ACCEPT; edits Opus fix lines |
| Verifier | pi `gpt-6-sol:high` via `pi-dry-run.sh … bash` | fresh per pass | reviews exactly one commit range, tags findings `hard`/`easy` | cargo, writes |
| Opus | fresh `general-purpose` agent, `model: opus` | one step or one fix | the spine step; `hard` findings as code only | writes tests for its own fix; shares a worktree with a live writer |
| Fable | fresh `campaign-reviewer` | one read | plan check; whole-PR read (trial: Astra on the PR instead, once) | stays resident |
| Astra | pi `gpt-6-astra:xhigh` | once | cross-step review of the assembled unit | |
| Ship | a release-prep step in a lane | once per release | the repository's release procedure (dekopon README §Maintainer release process), with the prep PR's CI as the matrix; under the runner the tick tags, pins and LAN-smokes it (campaign-trail DESIGN A6) | carries authority of its own (it acts under EPOCH.md §Execution contract and its `LIMITS.toml [authority]` table) |

Routing owner-approved 2026-10-01 after sub-campaign 5 (Claude ≤ $69 of ≤ $82): the brief, the packet, the ship phase and all-easy fix rounds were Opus there and move to pi; expected Claude ≈ $35-40 on a unit that size. Claude keeps the spine, `hard` fixes, the plan check, rulings and landing.

Design-shaping steps (the one where the spine's types are set) may go to one Opus agent instead of the driver: on A2 of sub-campaign 4 the blind judge preferred Opus's spine; pi had the better tests and the better numbers, cost $5.26 of pi and no Claude. Mechanical steps go to pi.

A sub-campaign of independent units (one per provider) runs as one Opus unit agent at a time, launched from a shared brief, and each agent marches its own unit: rule, packet, the pi steps, smoke and landing. The coordinator only launches the agents, rules on what they send up, and re-reads each landing. Each agent pings the coordinator every 30 minutes and at every step boundary, so the coordinator's context stays current without polling. Sub-campaign 10 (2026-10-06) landed five providers and a core/console release that way overnight, ≈ 1.5–2.5 h per provider.

## The runner (an epoch that loads the tick)

From Diaphanous Dilettantes, WORKING has no long-lived coordinator. A launchd tick on the Mac,
[`runner/campaign-tick.sh`](runner/README.md), syncs state with `cm sync`, launches what `cm next`
lists into a lane (`pi-lane.sh`, `lane-codex.sh`, `lane-claude.sh`, `lane-fable.sh`), merges
reviewed green heads, tags, pins and runs the LAN smoke under `[authority]`, and wakes Claude with
one `claude -p` run only for judgment: a hand-back, a Fable FIX, a red smoke, an answered
OWNER-QUEUE item. A wake answers with a decision row and `decision-N.md`, commits and ends; it holds
no publish or deploy right. The pi lane needs no supervisor, so the Coordinator and Supervisor rows
above and the handoff caps under Spend apply only to attended sessions (Cruciferous and earlier).

## The folder

The selected campaign root holds the state; a session that forgets everything resumes from it.
For Dekopon's current epochs, use `~/code/dekopon/campaign-trail/store/epochs/<epoch>/`,
not the closed `~/code/dekopon/campaign/` archive. Read the selected execution root's
`LIMITS.toml`: Advanced Schlubbing's `cm-trial/LIMITS.toml` and Bounded Bounces'
`LIMITS.toml` are distinct. New Dekopon rollouts use the local ignored
`~/code/dekopon/campaign-trail/.runtime/homelab.lock` and the shared
`~/code/dekopon/campaign-trail/tools/smoke/` transport. Dated packets in the
archive retain old paths as historical evidence; never relaunch one as-is. This
navigation does not change the generic folder contract for other campaigns.

| File | Owner | Holds |
|---|---|---|
| `RESUME.md` banner | coordinator | what is running, what to read next |
| `JOURNAL.md` | coordinator, append only | the coordinator writes five kinds of entry only (cm's own launch, advance and sync entries are cm's, not these): the owner's words, verbatim; contract or plan-row decisions, one line plus the path; lessons; handoffs; one line per release. Push at a landing, a release or a handoff, or after 30 minutes unpushed, never per wake. Generated files go under the step's gitignored `run/`; evidence over 256 KB is linked, not committed |
| `LIMITS.toml` | owner (coordinator applies measured dials) | runaway ceiling, models, disk floor, timeboxes |
| `NN-name/BRIEF.md` | written once, rewritten in one voice after the plan check | steps, landing model, routing, stops, hold list |
| `NN-name/DECISIONS.md` | settled rows D1..Dn + red witnesses | the only thing a stop may be answered from |
| `NN-name/<unit>/STATE.md` | the unit's one writer | alive table (worktrees, sessions, PRs), intent before every push, next action |
| `<unit>/<step>/` | the supervisor | `SUPERVISOR.md`, `verify.tpl.md`, `supervisor-state.md`, `supervisor-decisions.md` (S-numbers), blockers, report |

## Before a step launches

1. `LIMITS.toml`: not paused, spend under the runaway ceiling, free disk minus kache headroom over the floor, heavy builds under the cap.
2. A worktree cut from the integration head, upstream unset, fixtures fetched.
3. The step prompt: the row verbatim, the packages, the witnesses, what the previous step landed in one paragraph, "decide under ambiguity and record it; never end a turn with a question".
4. The verify template: `verifier-role.md` + the range + the row + the step's specific checks + this sentence, never a copy of the decisions: "Every row of EXECUTION.md §Rows and `<NN>/DECISIONS.md` is settled; a finding that contradicts one is not a finding; quote the row ID." Execution rows are `E…`, unit rows carry their prefix (`09-D21`).
5. The supervisor packet from `templates/SUPERVISOR.example.md` (pi-drive's template, adapted: the supervisor runs the verifier itself, reads the driver's gate log instead of rerunning it, writes S-numbers in its own file, never in DECISIONS.md).
6. STATE alive table and a journal line, then `pi() { command pi -ne "$@"; }; export -f pi; pi-turn.sh <step folder> <session> openai-codex/gpt-6-sol:high <log> kickoff.md` with `run_in_background`, every path absolute (`pi-turn.sh` changes into the step folder before it writes the log).
7. For a release: list every repo that links the changed contract, not only the ones that implement it. A client that embeds the runtime or decodes the wire (an operator console, a CLI) is a fleet member and re-pins and releases with the providers. Leave one out only when the release provably changes no type it decodes, and say so in the plan.

## The coordinator loop

Wake only on a completion notice. A supervisor's notice comes at the end of its turn, up to 100 minutes, so a merge or a deploy inside the turn is invisible until then. Every status to the owner says when it was read ("as of 19:19Z") and what may have happened since; when the owner asks about a running lane, re-read its state file and the live artifacts before answering. On each notice:

| Event | Do |
|---|---|
| Supervisor ends with a report | read `supervisor-state.md` and its decisions log (did it decide anything it should have handed back?); land or queue the next step |
| Supervisor hands back | read `supervisor-blockers.md` and the verifier file only; decide by appending one row to `<NN>/DECISIONS.md` with its `cause: plan\|env\|code\|new`, and write `decision-N.md`, the lane's exact next prompt (it replaces `coordinator-ruling-N.md` and `resume-N.md`); relaunch with a two-line resume. "Ruling" means an owner answer; the coordinator writes decisions |
| Third FIX REQUIRED | rule on the finding, not the count. Real and scoped → one fix turn and a **re-check scoped to that finding** (`templates/recheck.example.md`), not a full re-review. Pre-existing or unreachable in this step → carry it to a named step and write the carry into STATE and every later verify template |
| An Opus agent near 300k context | fresh agent from its `NOTES.md`; below that, resume it with SendMessage |

A fix text names the defect and the behaviour that must hold, never an implementation to delete: "`Tee` needs no `Drop`" made an Opus fixer remove the `Drop` that kept a mid-stream drop's meter record inside the call span, and cost a fix round (2026-10-10, dekopon #525 round 1).

Rulings that recur: a fix re-check that raises new pre-existing defects is not grounds to block; the verifier's number is not the contract, the row is (sub-campaign 4: `null\n` vs `display(Null)` + newline); a test that cannot fail before the fix is kept as a pin when a later step can make the path reachable.
**A retiring coordinator keeps deciding until its successor is up (owner, 2026-10-16).** Past its handoff cap it launches nothing new: no new step, no new Opus build, no new Fable read. But it still answers a completion notice whose next action is only a decision: it reads the blockers, writes `decision-N.md` and resumes that lane's supervisor with a two-line prompt. It stops when the RESUME banner carries a newer session's line (the fresh session writes that first) or when a notice needs anything beyond a decision, and journals each wake it takes as retired. 2026-10-16: Cruciferous Loop 6 retired at 10:23Z, all three supervisors handed back by 10:35Z, and nothing ran until the owner started the next session at 14:56Z.


## Measuring both ways (when a step is worth it)

Same row, same decisions, same verifier; separate worktrees; neither may read the other. Judge blind: detached worktrees `-x`/`-y` by coin flip, reports and verify files redacted of model, tool, branch and PR names, the key in a file the judge is not pointed to. The judge returns findings per build, a verdict, fix-before-landing vs carry, and at most three ports from the loser. The winner's author makes the fixes as a second commit; a scoped re-check; the coordinator squash-lands. Record per-role spend, wall clock, passes and the verdict.

## Landing

Coordinator only, on the integration branch: `git merge --squash origin/<branch>`, one commit whose body keeps every `Changelog:` line one per physical line, `git diff --quiet HEAD origin/<branch>` must hold (tree identical), push, close the PRs with the landing SHA, reap worktrees with `df` before and after. The author pushes its own branch; the coordinator never pushes onto a reviewed branch.

## Closing

The closing session asks no question: a question at the end means reviving an expensive context to answer it (owner, 2026-10-05). The owner still decides the rules ("We should always strive to improve our rules by asking me", 2026-10-04); the closing step leaves the decisions where he can answer them without Claude:

1. **Lessons become an open PR.** One commit per lesson, each body carrying its receipt, on the skill's or rule file's repo. Leave it unmerged: his merge, edit or partial revert is the vote. Journal-only lessons get lost. Every open lessons PR is merged or closed in one owner batch at the next OPEN → PLANNING kickoff; no skill pin while one is open (owner, 2026-10-17: "Batch vote at kickoff").
2. **Scope calls take the cheaper default.** Apply the no-spend or smaller option, file the alternative as an issue with a recommendation and its cost, and journal it as applied by default. He vetoes in any later session.
3. **Anything that cannot default goes in `OWNER-QUEUE.md`,** one item per heading with the recommendation and a line for his answer. He drains it with the coordinator before any new `/loop` (below).
4. **Ask live only while he is demonstrably present** (he wrote in the last few minutes), batched early, per standing order 2. Never as the last act of a session.

Every coordinator session ends, at a close or a clean stop, with a fenced `/loop …` command that runs in a fresh context: the next unit's, filled in (folder, scope, end state, version), or this unit's resume if it stopped early. Write the same command into the `RESUME.md` banner.

**No `/loop` while `OWNER-QUEUE.md` has an open item** (owner, 2026-10-12: "I think offering a `/loop` while my owner-queue.md is still running has contributed to unfinished epochs. let's make a rule: no `/loop` proposals until the queue is drained. it makes it very confusing to juggle "little threads" and "kicking off a big task""). A session that stops with items open ends with the queue instead: each item's exact action, one line each. The RESUME banner says `OWNER-QUEUE not drained: /loop withheld` in place of the command. The `/loop` is printed only by the session that sees the queue empty, and that includes a session the owner drains item by item. Shape (owner, 2026-10-01):

```
/loop You are the campaign coordinator for <unit> (<scope>). Read <campaign root>/RESUME.md, OWNER-QUEUE.md, <NN-name>/STATE.md and the selected execution root's LIMITS.toml, and follow the campaign skill. <what to draft and check>, then drive <unit> to <end state: merged on main / vX.Y.Z released and live on the Pi>. No check-ins: decide under ambiguity and journal it. Wake only on completion notices. Write state before every wait.
```

## Spend

pi: `pi-usage.sh <worktree> <supervisor folder>` plus each verifier's printed `cost_usd` (dry runs have no session). Claude: by role, not model (pi-drive §Cost accounting). Journal spend at every landing as a record, not a gate. There is no funding step, no budget and no money tripwire (owner, 2026-10-08: "ditch the money thing, it hasn't really caught anything"). The one money stop is the runaway ceiling in `LIMITS.toml`, $1,000 per epoch, which catches a loop burning money, not ordinary spend. Sub-campaign 4 actuals: ≈ $154 for 13 steps and ≈ 9,400 lines; pi ≈ $78 (≈ $4.60 per step of driver + supervisor, ≈ $1.20 of verifiers per step), Claude ≈ $76 (two coordinator sessions with ≈ 20 wakes, the A2 Opus build, two Fable reads, the ship supervisor). A sol supervisor session carried across resumes grew to $7: start a fresh one every few steps.

Claude's number is the coordinator session's `/cost`, which includes its subagents. ccusage 5-hour blocks count Claude only: never subtract pi from them (2026-10-02: reported $15, real $62).

### Where Claude money goes (rest of 6, 2026-10-02: $62 Claude, $47 pi)

Opus was $47, almost all of it 134M cache-read tokens: every tool call re-reads the whole context, so cost ≈ context size × calls. Three things drove it, and each has a rule:

1. **Size Opus steps at ≤ 800 changed production lines.** At a contract break the tests move with the code: S1b-1 was estimated at 1,400 and came to ≈ 4,000 gross. It took four Opus agents, three of them ending at the 300k cap, where every call re-reads the largest context.
2. **An Opus agent stops when production code compiles and its witnesses are green.** It commits and writes NOTES. The test fix-up, the full gate and the verifier go to a pi driver as the next step. The S1b-1c finish was exactly that work, and pi did it.
3. **The coordinator hands off after each landing, or at the first natural boundary past 200k tokens (hard stop 250k).** It writes STATE and prints its `/loop`, and a fresh session continues. A fresh session starts at ≈ 60k of fixed load and ≈ 100k once it has read its state, so a 120k cap left ≈ 20-35k of work and spent ≈ 40% of each session's reads on startup; at 250k the cost per working call is about the same and startup falls under 10% (owner, 2026-10-15: "250k is great"). No compaction instead of handoffs: it fires near the window limit, so the coordinator would idle at its largest context, and its summary blurs ruling numbers and paths that a handoff writes exactly. One coordinator session ran six hours, with a context of several hundred k re-read on about 150 turns.

The Fable reads ($15) were worth it: they found the design break before the build, and the final read cleared the merge. Keep them.

## Things that bite

Incident receipts for the other 51 bullets, and the original wording of all 66, are in [HISTORY.md](HISTORY.md); read it only for evidence.

- The classifier refuses destructive git (`reset --hard`, deleting a remote branch). Cut a new worktree and branch instead and leave the old ones for the owner.
- A driver that runs under DRIVER.md's third-FIX stop refuses a fix unless the prompt quotes the coordinator decision that authorizes it.
- A ruling sent to a lane that cannot ask back (Codex through a relay, a cloud session) is checked against the brief, row by row, before it is sent, and it goes to every arm building the same unit. 2026-10-10, T1c bake-off: a relayed scope ruling told Codex that pre-admission refusals record `failed` where the brief said the refusal outcome; both judges' decisive findings against the Codex build were that ruling's.
- Authority is stated once, in EPOCH.md §Execution contract with its `LIMITS.toml [authority]` table, and answered at the gate from the authority ledger; every prompt points to it, quoting it by reference, never restating it. Approving a sub-campaign authorized its releases, but the classifier refused the coordinator's next action as "Merge Without Review" right after it merged a reviewed, green core PR, and work stopped until the owner said "merges authorized" (sub-campaign 11, #478). Under the runner the tick merges in shell, outside the classifier.
- The classifier refuses `gh pr merge` into a shared workflow repo whose `@main` other repos call. Ask the owner for that merge up front.
- Before a push, the driver runs CI's own steps for what it touched: every generated artifact CI byte-compares, every docs check its change triggers, `cargo doc` with `-D warnings`, `cargo deny`. The repo's own list lives in its agent guide. 2026-10-03: four CI reds (a rustdoc link, an advisory, generated bytes, an undocumented event) each cost a fix turn plus a CI cycle.
- Every background probe, watch or poll loop runs under `timeout <s>`, never `while true`. A loop left by the v0.32 rollout session hit the WhatsApp webhook every 5 s for 23 hours; a day later its 15,000 refusals looked like a production fault and cost a diagnosis.
- `cm close` needs every step at `done` or `blocked:<reason>`, and `done` comes only after `released` (a tag) and `deployed` (a digest). Take the tag from `git tag --contains <merge sha>` in the step's repo; `cm` accepts any tag that resolves, so the closer checks that the tag contains the merge. Take the digest from what the RPi runs: the pod's image ID, or a provider-set pin matched against its registry tag. Pass `--repo` once the worktree is reaped. A step that was released but is not live, docs only, a study, or superseded by a split closes as `blocked:<one-word-reason>` (Cruciferous close, 2026-10-17).
- A smoke leg's verdict never comes from scraping the console TUI. Bordered echoes, repaint and sidebar text, and a provider printing its own `[exit code: 0]` each fooled a matcher: three verifier rounds in sub-campaign 11 (CONSOLE-DEV, R11-14..16). A leg passes on the broker's record of the call (Succeeded in the leg's window) plus a result line the supervisor quotes from the saved screen. The script only captures.
- A gate counts only what its own lane created. A container or image another session left behind is recorded as pre-existing, never stopped, and never turns the gate red. A local pre-push step never runs a repo CI script or Compose file that starts Docker (a chart permission script, an OpenObserve smoke): the PR's CI runs it on GitHub's runner and is authoritative. Advanced-schlubbing: a pre-existing labelled container stopped the 0.39.0 rollout, and repo CI scripts that start Docker stopped the 0.40.0 release three times.
- A core release is two tags, core then chart, and the chart is cut from main. Every other core PR holds until the chart tag exists, then merges one at a time, each riding the next minor. A merge between the two tags puts unreleased code under the chart's tag.
- Every brief, recon included, says: never read or print a credential file (`~/.config/dekopon/broker-credentials.yaml`, auth JSON, kubeconfigs); a step that needs one edits a scratch copy by script or skips the call. A read-only recon agent is not safe by being read-only: one printed both GitHub PATs into its transcript, and rotation is the owner's.
- A homelab change of one or a few files (a pin, a grant block, a route flag) goes to one Opus agent with merge and Argo sync authorized, not a pi packet. It is the only homelab writer until it reports. Advanced-schlubbing: four such changes (rpi-homelab #186, #188, #189, #194) each merged, synced and verified live inside one agent run; a pi packet for a three-line change costs more than the change.
- A kache store over its cap with GC evicting nothing is a kache fault (rule 2), not disk pressure to reap around. Read `kache stats` and `kache doctor`, put the numbers in OWNER-QUEUE with a purge recommendation, and stop the lane at its disk gate. Never purge on the coordinator's own call. Advanced-schlubbing: 51.2 GiB against a 40 GiB cap (128%), last GC evicted 0, doctor clean; purged on the owner's word.
- Changelog trailer wording or category is never blocking in a Fable read; the reviewer notes it for the squash message, and the coordinator fixes it there. `CHANGELOG.md` is written only at release prep from `git log`, so a trailer is a breadcrumb, not a merge gate (owner, 2026-10-16). Every Fable prompt says so. Cruciferous #604 came back FIX BEFORE MERGE over one trailer word.

## Routing decided for sub-campaign 6 (owner, 2026-09-30)

Opus builds the seam step where shape decides; pi fans out the mechanical steps with one verifier pass per commit; Astra once on the assembled unit; Fable once on the PR. From sub-campaign 4: third pi rounds cost ≈ $40-50 of pi and 2-3 h, and the coordinator's wakes ≈ $15-20 of Claude. Confirmed at the 04 close.

**Fix rounds (owner, 2026-10-01, replaces "second round to Opus"):** split by the verifier's `hard`/`easy` tags. Opus fixes only hard findings (code, no tests); the pi driver then witnesses the Opus fix, does the easy list and gates; an all-easy round never wakes Opus; a failed re-check goes to Opus. One writer per worktree at a time. The rule and the prompts: `pi-drive` §Fix rounds split by difficulty and `templates/SUPERVISOR.example.md`. Sub-campaign 5 (≤ $82, five Opus fix rounds, two with no hard finding) is why.

## Standing orders (owner, 2026-09-30)

1. No money gate (owner, 2026-10-08). Never ask for funding or price a wave; a tripwire is a journal line, not a stop. Only the runaway ceiling and owner-only items block.
2. Ask a foreseeable owner decision the moment a projection shows it, batched, with a recommendation.
3. A blocking question left unanswered: journal it, write every state file, stop cleanly, so the owner answers in a fresh short session.
4. **Ship without the straggler (owner, 2026-10-03).** A non-essential repo does not hold up a fleet rollout. When one is stuck (a release snag, a failing review, an owner-only step), ship without it and journal why it blocked.
