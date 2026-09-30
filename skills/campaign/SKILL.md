---
name: campaign
description: Run one funded sub-campaign of a large multi-step code effort economically — a Claude coordinator that rules and lands, pi sol supervisors that watch, a pi GPT driver that builds, a fresh gpt-6-sol verifier per commit, and a few fresh Fable reads — from a folder of state files. Use when Xavier funds a sub-campaign, says "run the campaign", "continue sub-campaign N", or asks how to drive a big change cheaply across many steps. Not for a one-file change (one Opus agent), and not for writing the brief (pi-subagent-plan) or for the mechanics of one pi session (pi-drive).
---

<!-- STAGED, 2026-09-30: drafted at A3, filled from sub-campaign 4 actuals at its close. Installing it into ~/.claude/skills is the owner's call. -->

# Running a campaign

**Claude decides; pi does.** Claude quota is the scarce resource, and a coordinator's own wakes are its largest line once supervision moves to pi. Every rule below either keeps Claude out of a loop or makes a Claude call count.

## Who does what

| Role | Model | Lives | Does | Never |
|---|---|---|---|---|
| Coordinator | Claude Opus, one session | across units until ~240k tokens, then a fresh session from `RESUME.md` | rules on hand-backs by quoting or adding a decision, lands, journals, reads spend | supervises a step; rereads a gate; polls |
| Supervisor | pi `gpt-6-sol:high`, one session per step (or per run of steps) | `pi-turn.sh` in the background from its own folder | launches driver turns, runs the verifier, sends fix/push prompts, hands back | decides scope; edits the worktree; answers a stop without quoting a row |
| Driver | pi `gpt-6-sol:medium`, recipe A, `-nc -ne` | one session per unit | edits, builds, commits, gates, pushes on ACCEPT | spawns agents; pushes before ACCEPT |
| Verifier | pi `gpt-6-sol:high` via `pi-dry-run.sh … bash` | fresh per pass | reviews exactly one commit range | cargo, writes |
| Fable | fresh `campaign-reviewer` | one read | plan check, the both-ways judging, unit head, whole PR | stays resident |
| Astra | pi `gpt-6-astra:xhigh` | once | cross-step review of the assembled unit | |
| Ship | `campaign-supervisor-medium` | once | merge, tag, verify release | |

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

1. `LIMITS.toml`: not paused, spend under the tripwire, free disk minus kache headroom over the floor, heavy builds under the cap.
2. A worktree cut from the integration head, upstream unset, fixtures fetched.
3. The step prompt: the row verbatim, the packages, the witnesses, what the previous step landed in one paragraph, "decide under ambiguity and record it; never end a turn with a question".
4. The verify template: `verifier-role.md` + the range + the row + the step's specific checks + **every coordinator ruling so far**, stated as "not findings". A ruling missing from the template is re-raised by the next verifier.
5. The supervisor packet from `templates/SUPERVISOR.example.md` (pi-drive's template, adapted: the supervisor runs the verifier itself, reads the driver's gate log instead of rerunning it, writes S-numbers in its own file, never in DECISIONS.md).
6. STATE alive table and a journal line, then `pi-turn.sh <step folder> <session> openai-codex/gpt-6-sol:high <log> kickoff.md` with `run_in_background`.

## The coordinator loop

Wake only on a completion notice. On each:

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

## Spend

pi: `pi-usage.sh <worktree> <supervisor folder>` plus each verifier's printed `cost_usd` (dry runs have no session). Claude: by role, not model (pi-drive §Cost accounting). Project at every landing; stop at the tripwire. Sub-campaign 4 actuals: ≈ $154 for 13 steps and ≈ 9,400 lines; pi ≈ $78 (≈ $4.60 per step of driver + supervisor, ≈ $1.20 of verifiers per step), Claude ≈ $76 (two coordinator sessions with ≈ 20 wakes, the A2 Opus build, two Fable reads, the ship supervisor). A sol supervisor session carried across resumes grew to $7: start a fresh one every few steps.

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

## Routing decided for sub-campaign 6 (owner, 2026-09-30)

Opus builds the seam step where shape decides; pi fans out the mechanical steps with one verifier pass per commit; a second review round goes to an Opus fix agent; Astra once on the assembled unit; Fable once on the PR. From sub-campaign 4: third pi rounds cost ≈ $40-50 of pi and 2-3 h, and the coordinator's wakes ≈ $15-20 of Claude. Confirmed at the 04 close.

## Standing orders (owner, 2026-09-30)

1. A tripwire inside the funded budget is a journal line, not a stop; only spend past the budget and owner-only items block.
2. Ask a foreseeable owner decision the moment a projection shows it, batched, with a recommendation.
3. A blocking question left unanswered: journal it, write every state file, stop cleanly, so the owner answers in a fresh short session.
