---
name: pi-drive
description: Drive a pi coding-agent session from Claude Code, so a high-level Claude (fable) supervises a cheap driver (gpt-6-sol) turn by turn — issuing stage prompts, reading only the driver's last message and decision files, answering its stops from the decisions file, and escalating to Xavier only for the four hard stops. Two paths — print mode (one process per turn, simplest) and RPC mode (one long-lived process, can steer mid-turn). Use when Xavier says "drive the pi", "run the driver from here", "supervise the pi session", "super high level fable with cheap gpt", or right after a pi-subagent-plan handoff is written and he says yes to being driven. Claude Code only.
argument-hint: "[brief path] [workdir] [print|rpc]"
arguments: [brief, workdir, path]
disable-model-invocation: false
user-invocable: true
---

# Driving pi from Claude Code

The shape: **you are the supervisor, pi is the driver.** The driver (gpt-6-sol, medium
reasoning) does all the editing, building and committing in its own worktree under a brief
written with `pi-subagent-plan` (`DRIVER.md` style: decide-and-record, four hard stops). You
never edit its worktree. You issue one stage at a time, read its last message and its decision
files, answer what it stopped on from the brief's decisions file, and ask Xavier only for the
four hard stops (forking or patching a dependency, moving a contract away from the decisions
file, reversing a keep/delete, owner-only actions). Everything else you decide and record.

Why: nine stops on the asset run each cost a day because the loop ran through Xavier. Through
this skill a non-hard stop costs minutes, and fable's context stays small because it reads
tails, never transcripts.

## Which model drives

`openai-codex/gpt-6-sol` at `medium`, by the owner's decision of 2026-09-30 ("switch to gpt-6-sol
if it really is similar quality"): on the steering eval's effort block it matched `gpt-6.1-sol` at
`medium` on hidden tests and cost ($0.19 a run) and was 1.85 times faster; its blind score was
1.5 lower, all of it on pipe-type shape. Sub-campaign 4 ran A3-A13 on it (≈ 8,000 lines). Where a
step sets a spine's shape, an Opus agent builds it instead (§A sol supervisor, sub-campaign 4).
The stage verifier, the fact-checker and the supervisor run `gpt-6-sol` at `high`; dry runs use
`gpt-6-sol` at `high`.

## Which model supervises

Claude decides and reviews; sol does and watches. The watch loop, relaunches, read-only
verifications and stage prompts are mechanical and the rules live in the prompt, not in the
model. On 2026-09-29 that loop was the largest Claude line of a $356 campaign: 24 opus
supervisor sessions cost about $70, against about $60 of pi for the drivers that wrote the
production code. D took three supervisors and C, J, T and V two each, and every handoff re-read
the same briefs.

So the supervisor is the cheapest tier that has been shown to do it:

1. **A pi sol supervisor for a mechanical unit** (a re-pin, a CI or docs change, a path
   cleanup). The pilot in §A sol supervisor passed on 2026-09-29.
2. **A pi sol supervisor for a code unit too** since sub-campaign 4 (below), and for the ship unit since 2026-10-01. One
   supervisor session per step, resumed from a state file, handed off at 120k tokens. Never `max`:
   a supervisor writes no code.
3. **Fable never runs the loop.** Spawn it as a fresh `Agent` for the rows `pi-subagent-plan`
   §3a gives Claude: a stop the decisions file does not answer (the brief, the decisions file
   and the blocker file only), the plan check and the rehearsal review of a new brief, rulings
   on review findings, and the adversarial review of the landed PR.

The split that works: cheap driver and cheap verifier per stage, one expensive fresh reviewer
per PR before merge; that review is never cut for cost (2026-09-27: $97 of pi for −2,250 lines,
and every real gap came from the fable reviewer; 2026-09-29: 19 fable reviews and plan checks
for about $50 found every P1). What is cut: a Claude shape review after every stage and a
counterexample adversary, neither of which paid in the steering eval. A fix is re-checked by a
fresh pi sol verifier against the finding's Fix line; it gets a second fable pass only when it
moved a contract surface or answered a P1. Say in the first message which tier is supervising,
and report both bills.

## A sol supervisor (three pilots, 2026-09-29)

**Result.** One sol supervisor took a sol driver through two stages to a green draft PR
(`dekopon-agents/steering-eval#1`) in 15.7 minutes. The supervisor cost $0.40 of pi, against $3
to $8 for an opus supervisor per unit; the whole unit cost $1.54 of pi. It made no edit in the
driver's worktree and no push, reran the gate and `pi-stage-check.sh` itself after every turn,
and made 0 status calls while a driver turn was alive. The driver never stopped in that pilot, so its stop and hand-back paths ran first in pilot 2,
below.
The packet is `~/code/dekopon/sol-supervisor-pilot/`.

- **Shape.** The supervisor is its own pi session (`openai-codex/gpt-6-sol:high`, session id
  `<effort>-supervisor-<date>`), launched by Claude with `pi-turn.sh` in the background, with
  the plan folder as its cwd so `pi-usage.sh` shows it apart from the driver. Its whole prompt
  is `templates/SUPERVISOR.md`, filled in.
- **Launch and wait, inside pi.** One bash call per driver turn, with the bash tool's
  `timeout` at `3600`: a pid-file check refuses a second live turn, `nohup bash pi-turn.sh … &`
  starts it, its pid goes to a file, and a `while kill -0` loop in the same call waits for it. The rule against `nohup` is about Claude Code's
  runner and does not apply inside pi, but pi has a trap of its own: its `pi-processes` skill
  offers a `process` tool, sol reaches for it, and a process started that way dies when the
  supervisor's print-mode turn ends. In pilot 2 the supervisor did that and ended its turn with
  "Awaiting driver turn 1"; the driver died after two messages. The template forbids it.
- **What it hands back.** A stop the decisions file does not answer, a hard stop, the same
  tripwire firing twice, FIX REQUIRED after verifier pass 2, an auth error or outage, and every
  merge, mark-ready, tag, release, deploy or homelab push. It writes
  `<design>/execution/supervisor-blockers.md` with the mechanism facts and one proposed answer
  each, and ends its turn. The exit wakes Claude, which answers in the decisions file and
  relaunches. Claude reads the blocker file and the final report, nothing else.
- **Pilot 2, planted stops (2026-09-29): failed.** Draft PR `dekopon-agents/dekopon#414`, a
  one-sentence docs fix, $1.08 of pi. The stop the decisions file answered was answered and
  recorded, correctly. The scope question ("should this PR correct two other files too?") was
  not handed back: the supervisor wrote its own decision, "applies D3 and DRIVER.md", and
  relaunched the driver. Its answer was the conservative one and matched what Claude would have
  said, which is how this failure hides. Two causes. The packet leaked: the gate and the
  acceptance check both said "touches only `docs/upgrading.md`". And the model stretched: it
  wrote a first D-number broader than the decision it cited, then cited that. Its first turn
  also launched the driver with the `process` tool and ended.
- **Pilot 3, the rewritten template (2026-09-29): passed.** The unit was the rebase of
  `dekopon-agents/steering-eval#1` onto a main that had moved five commits, two conflicts, $0.39
  for the supervisor. The covered stop was answered by quoting the decision verbatim. The
  uncovered one (a tracking id the packet did not contain) was handed back with nothing decided,
  and resumed from the state file after Claude's answer. No `process` tool, no status calls
  during a live turn. **Its limit:** the uncovered stop had no tempting answer. Pilot 2's
  failure was a scope question with an obvious conservative answer, and that case has not been
  re-tested under the new rule.
- **What that means for routing.** A sol supervisor runs the watch loop well and costs a tenth
  of opus. Use it for mechanical units, rebases and re-pins included. Code units stay on opus at
  medium until a sol supervisor has handed back a real scope question on real work: try it on
  the first small code unit of the next campaign and read its decisions file afterwards, in
  place of a fourth synthetic pilot.
- **Sub-campaign 4, real code (2026-09-30): passed.** Sol supervisors watched A2 (pi side) and
  A3-A13 of a 9,400-line shell rewrite: zero decisions of their own, every third FIX REQUIRED
  handed back with one proposed answer, and a strict reading of a standing ruling handed back
  rather than stretched. Sol supervisors now watch code units too. What went wrong was the
  packet, not the model: a Push prompt that said "amend" after a push (fix: a CI repair is a new
  commit on top), a driver refusing a fix because the prompt did not carry the coordinator's
  authority (fix: quote the ruling file), and one supervisor session carried across five
  resumes that grew to $7 (fix: a fresh session per step). A standing ruling for
  repeated third-FIX cases (fix and one scoped re-check when every finding is in the step's own
  hunks) removed a coordinator wake per step. The packets are
  `~/code/dekopon/campaign/04-shell-bytes/S1a/A4-12/` and the `campaign` skill.
- **Fix rounds split by difficulty (owner, 2026-10-01).** The verifier tags every blocking
  finding `hard` or `easy`. **hard:** a type or trait change across crates, concurrency or
  ordering, cancellation or shutdown, a credential path. **easy:** a missing or weak test, an
  exhaustive match, a record field, wording, a deletion. On `FIX REQUIRED`:
  1. All easy → the **Fix** prompt to the driver (a new commit on top), then one re-check
     scoped to the findings.
  2. Any hard → hand back with the hard list. The coordinator launches one Opus fix agent for
     the hard findings only: code, no tests, one commit, then it ends. Only after that commit
     exists and the agent has exited, the supervisor sends the driver the **Integrate** prompt:
     the Opus SHA, the hard list and the easy list. The driver writes a witness for each Opus
     fix and proves it (revert that fix locally, the test fails, restore), does the easy list,
     gates and commits. It never edits the Opus lines; a witness that shows an Opus fix is
     wrong is a stop and a hand-back. Then one re-check scoped to both commits.
  3. That re-check `FIX REQUIRED` → hand back; the coordinator routes it to an Opus fix agent.
  One writer at a time in a worktree, always: the next writer starts only after the previous
  writer's commit exists and its process has exited. Why: in sub-campaign 5 every pi step failed
  its first verify, and sending every second round to Opus put five Opus fix agents on what were
  mostly missing tests; two of the five rounds had no hard finding at all. A mis-tag costs one pi
  turn, because the re-check catches it and step 3 routes it to Opus.
- **Keep scope out of the packet's machinery.** A gate or acceptance check that names which
  files a PR may touch answers scope questions for the supervisor. Put scope in the decisions
  file, where an answer has to be quoted.
- **Waiting on the supervisor, from Claude Code.** The background task's own completion notice
  is the wake-up. A `pgrep` started right after launch matches nothing and fires early.
- **A dry run does not see the tool environment.** Neither dry run caught the `process` tool or
  the leaked scope: both live in what pi loads and what the gate implies, not in the brief's
  steps.
- **Verdict lines.** pi-subagents appends `Mission: <id> (completed)` to a child's returned
  text, so a verify file saved verbatim does not end with its verdict. The verdict is the last
  line that is exactly `ACCEPT`, `READY` or `FIX REQUIRED`; `pi-stage-check.sh` reads it that
  way and refuses a head whose newest review says `FIX REQUIRED` (it used to check only the
  `Reviewed:` SHA).
- **Worktrees.** `git worktree add <path> -b <branch> origin/main` makes the branch track
  `origin/main`, so a bare `git push` targets main. Run
  `git -C <path> branch --unset-upstream` right after creating it.

## Before the first turn

1. `pi --version` (0.99.1 on 2026-09-29; the Homebrew path still reads 0.85.1), `pi auth check` or `subagent({action:"models"})`-equivalent:
   `pi --list-models gpt-6` shows `openai-codex/gpt-6-sol`. Provider id is
   `openai-codex/…`, not `openai/…`. The same listing must show the model you will run: an id
   pi does not list still launches, with the warning "Using custom model id", and is billed in
   every log at the provider's fallback rate (§Cost accounting).
2. The brief exists and passed `pi-subagent-plan` §5 (invention audit empty). Its dry runs go
   through `scripts/pi-dry-run.sh <workdir> <prompt-file> <out.md>`: one fresh sol run at high
   effort with no write, edit or bash tool, findings in `<out.md>`. The workdir on its
   line 1 exists; `.pi/agents/` in the PR worktree holds the verifier/reviewer files.
3. Pick a session id (`asset-core-driver-2026-09-19`) and a state dir in the scratchpad or
   under the brief's `execution/`. Everything the driver must persist goes in files the brief
   names (`execution/*.md`, `Driver decisions` in its report), not in your context.
4. Say which path you are using and why (below). Default: **print**.

## Path A — print mode (default)

One process per turn; the process exit is your wake-up.

```
scripts/pi-turn.sh <workdir> <session-id> openai-codex/gpt-6-sol:medium <log.jsonl> <prompt-file>
```

Run it with the Bash tool, `run_in_background: true`, timeout at the maximum — **never `nohup … &`
from a Bash call**: only the harness's background runner notifies you on exit, and a `nohup`
launch leaves the exit to the next watch tick (four relaunches on the 0.18.0 fleet each waited a
full 15-minute tick for that reason). Turn 1's prompt is the brief's kickoff verbatim
(`DRIVER.md`). When it exits, read
`scripts/pi-tail.sh <log.jsonl> [N=3] [chars=700]`: the last N prose messages, each preceded by
the tool calls the driver issued before it (name + short arg summary), fenced code collapsed to
`[code: N lines]`, the middle of anything over the cap elided. Start with N=3 at 700 and widen
only when a message's elision hides the decision. `scripts/pi-last.sh <log.jsonl>` is the blunt
form (tool tally + final text up to 6k) for when one message is all there is. Then:

- **It finished the stage** → next prompt: "Stage N accepted. Continue with stage N+1 of the
  brief." Keep prompts to two sentences; the brief carries the content.
- **It stopped with a question** → answer from the decisions file, in the driver's own terms,
  as one prompt: the answer, the mechanism fact behind it, "record it under Driver decisions,
  continue". If the decisions file does not answer and it is not a hard stop, decide, write the
  decision into the decisions file first (so the packet stays the source), then prompt.
- **Hard stop** → `AskUserQuestion` with the mechanism and one recommended answer; the driver
  waits. If Xavier is absent, the loop parks; say so in your final message.
- **It claims done** → verify the claim before accepting it: `git -C <worktree> log --oneline`,
  the gate commands it lists, `gh pr view`, and
  `scripts/pi-stage-check.sh <worktree> <stage parent> <design>/execution`. That script prints
  the stage's changed lines against the ~1.2k cap and whether HEAD is the SHA the newest
  verifier/reviewer file names on its `Reviewed:` line; `verdict=NOT OK` is not accepted (send
  the "Unreviewed or oversize head" prompt from `templates/STAGE-PROMPTS.md`). A driver's report
  is a claim, not a receipt. #321 shipped a 412-line commit after its last review and pushed over
  two `FIX REQUIRED` verdicts; this check would have caught both.
- **It met the letter but missed the target** (a 2% cut against a ~30% brief; survivors kept
  "when unsure") → redo the stage on the same branch with the per-unit expectation spelled out
  (`pi-subagent-plan` §1.7). A timid PR is never merged as progress.

Same `--session-id` every turn keeps its context; the first turn logs `No project session found
… creating` to stderr, which is expected. Verified 2026-09-19: print smoke turn returned the text
and `agent_settled`; RPC `get_state` round-tripped. Session files live under `~/.pi/agent/sessions/`;
never read them whole. Print mode cannot steer mid-turn; if you must, `kill $(lsof -t <log.jsonl>)`
ends the turn and the next prompt says what changed. A running pi shows in the process list as
`pi` with no arguments, so `pgrep -f` or `pkill -f` on its session id matches nothing (checked
2026-09-29); find a turn by the pid that launched it or by who holds its log.

## Path B — RPC mode (long-lived, steerable)

One `pi --mode rpc` process behind a FIFO; JSON-line commands in, events out.

```
scripts/pi-rpc-start.sh <workdir> <state-dir> <session-id> openai-codex/gpt-6-sol:medium
scripts/pi-rpc-send.sh  <state-dir> prompt    "<kickoff>"
scripts/pi-rpc-send.sh  <state-dir> steer     "<answer>"      # lands between tool calls, mid-turn
scripts/pi-rpc-send.sh  <state-dir> follow_up "<next stage>"  # after the current turn settles
scripts/pi-rpc-send.sh  <state-dir> abort
scripts/pi-rpc-stop.sh  <state-dir>
```

Wake-up: the `Monitor` tool on `<state-dir>/events.jsonl` for a line containing
`"type":"agent_settled"` (not `agent_end`, which can be followed by a retry or a queued
continuation). Read with `scripts/pi-last.sh <state-dir>/events.jsonl`. Startup emits
`extension_ui_request` lines with `method: setWidget`; those need no answer. A `select`, `confirm`
or `input` request does (`pi-rpc-send.sh <state-dir> ui <request-id> <value|confirm|deny>`), or
it times out and resolves to nothing, which usually means the driver proceeds without it. Use RPC when you expect
to redirect a running stage (a wrong assumption you can see in the tool tally), or when turn
boundaries are hours apart and you want `get_state` between them. Cost: a process you must
remember to stop; `pi-rpc-stop.sh` at the end of the session.

## Rules for the supervisor

- Read tails: `pi-tail.sh` output, the brief's `execution/*.md` the driver writes, `git log`
  and `git diff --stat` of its worktree. Never the JSON log whole, never a session file, never
  tool output or thinking from the log (`pi-tail.sh` prints neither).
- **A print-mode turn ends the moment the driver stops generating, even if an async `subagent`
  child or a background gate it launched is still running.** The child is orphaned (a child that
  was polling CI simply stops polling), the process exits, and you get a "turn ended" with no
  report and no question. Seen five times on the 0.18.0 fleet (file, gpt-image, asset, python
  twice). Two defences, both mandatory: every stage prompt carries the line *"do not end your
  turn while a subagent or background job is still running: wait on it with one blocking command
  that returns when it finishes, never repeated status calls"* (a blocked call is free; every
  poll is a full read of the driver's context), and a turn that ends mid-stage is relaunched at once with *"your previous turn
  ended mid-stage; continue from the current state (git log, gh pr view, subagent status for
  any verifier you spawned); write the report when done"*. A foreground `subagent()` call does
  keep the process alive; `ps` for `cargo`/`rustc` shows what the child is doing.
- One stage per prompt, from `templates/STAGE-PROMPTS.md`. Do not re-explain the brief; point at its section. Each stage prompt
  opens with "rebase onto origin/main first" and closes with "one full gate at commit, no
  packaging or smoke before the last stage, long commands in the background to a log file"
  (`pi-subagent-plan` §0b). If the brief predates §0b, the prompt overrides it and says so.
- Run independent stages in parallel: when the driver reaches the measurement stage, the
  supervisor starts the container harness itself in the background (read-only for the
  worktree: its own harness worktree, its own target volume) and sends the driver the review
  stage in the same turn. Merge the numbers into the driver's report afterwards.
- Verifier discipline: accept one read-only pass; ask for a second only when pass 1 had
  `contract` findings. If the driver spawns a child for work it could do in one command,
  the next prompt says to do such things itself.
- Verify claims of green gates yourself with the same commands (`--locked`, scoped `-p`), in the
  driver's worktree, read-only. Never edit or push there: rebases and fixes are the driver's, so
  the reviewed head stays the head that merges; if something is wrong, the next prompt says so.
- A defect in the **plan** (a seam it missed, an "as today" that is not, a claim the source
  contradicts) is two records, not one: the D<n> that resolves it for the driver, and one line in
  `<plan folder>/PLANNER-FEEDBACK.md` stating the general lesson, so the planner's next plan and
  the `pi-subagent-plan` gate absorb it. The planner answers with a verdict file beside it; a
  supervisor overruled there amends the D<n>, never the plan.
- Every decision you make on the driver's behalf goes into the packet's decisions file before
  the prompt that relies on it, numbered like the rest (D19…). The packet is the source, your
  context is not.
- Disk: the driver builds; check `df -h` between stages; four heavy *core-workspace* builds max
  on this Mac. Provider (wasm component) builds are small and their wall clock is GitHub
  runners, not local disk: run every independent provider at once, never in batches of three
  (the 0.18.0 re-pin lost about an hour to batching).
- **Many independent repos = many pi sessions, not one driver with a workflow script.** One
  brief template with the repo name filled in, one session id per repo, one log per repo, the
  watch loop checks each log in one `for` loop. The 0.18.0 fleet's workflow-script fan-out lost
  children three different ways (parent turn ended, a transient Codex error, a stop routed
  through the parent); the four parallel sessions that replaced it (F9) had none of those.
- A turn that writes no `session` event within seconds is blocked on stdin: pi waits on an
  inherited socket. `pi-turn.sh` redirects `< /dev/null` (added 2026-09-20 after a 22-minute
  stall); if you launch pi by hand, do the same. Check with `jq -r .type <log> | head -3`.
- **Prompts go by file, never inline in argv.** Write every stage prompt to a file and pass its
  path; `pi-turn.sh` hands pi `@<abs path>` (changed 2026-09-23), which pi expands into a
  `<file>` block. Long command lines are fragile under the sandbox (a capture run hit it;
  the 100/300/600-byte ladder did not reproduce a hard limit), and the file block caches:
  one test turn read 17,920 tokens from cache for 1,272 fresh ones. By hand:
  `pi … -- "@/abs/prompt.md"`. Short literal text still works for one-liners.
- Auth: an expired OpenAI login shows as an immediate exit with an error in `<log>.err`.
  Tell Xavier; do not switch models.
- **Provider outage signatures (2026-09-25).** A turn whose assistant messages end with
  `stopReason: error` and `WebSocket closed 1011`, then (on pi's auto-retry) `Incorrect API key
  provided: sk-svcac…`, is an OpenAI Codex outage, not our credential: pi never sends an `sk-` key
  on `openai-codex`, and `pi auth check` still says `ready`. Do not tell Xavier to log in again.
  Read it with `jq -c 'select(.type=="message_end" and .message.role=="assistant") |
  .message | {stopReason, errorMessage}' <log>`. Relaunch the same prompt once; if the second try
  shows the same pair, check `https://status.openai.com/api/v2/summary.json` and **pause the run**:
  launch nothing until the Codex incident is gone from that feed for 5 minutes. Poll it in a
  background loop, not per turn. No smoke test before ordinary turns.
- **A new model on its launch day runs slow and retries (2026-09-29).** Two of eight
  `gpt-6.1-sol` runs auto-retried on `Codex SSE response headers timed out after 300000ms`,
  `upstream connect error … connection timeout` and a Cloudflare 504 page; one turn took 708 s
  where its neighbours took about 310 s. pi's retry succeeded each time, so this is not a stall
  and not an outage: leave the turn alone. Count them with
  `grep -c '"type":"auto_retry_start"' <log>`, and drop runs that retried from any wall-clock
  comparison.
- **Say "back" conservatively.** One good reply during an incident means nothing: on 2026-09-25 a
  low-reasoning call failed while a high-reasoning one answered, and the stage relaunched on a
  single pong died the same way. "Back" means the incident is closed on the status feed for 5
  minutes and two consecutive calls at the run's model and level succeed, 5 minutes apart. Never
  start a stage that changes shared state (stops a container, migrates, writes fixtures) on less.
- **Fill prompt placeholders with `scripts/pi-fill-prompt.sh`**, never by hand-written `sed`: it
  takes the template, the output path and the previous stage's report, fills `<sha>`/`<hash>`/
  `<url>`/`<stage-X head>` from `git rev-parse HEAD`, the report's sha256 and `gh pr view`, and
  refuses to write a prompt that still contains an unfilled `<…>` placeholder it knows.
- End of run: the driver's PR URL and head SHA, every stage's verdict, the decisions you made,
  the hard stops you asked, the `scripts/pi-usage.sh` table for every worktree the run used
  (§Cost accounting), and `pi-rpc-stop.sh` if on path B.

## Cost accounting

`scripts/pi-usage.sh <worktree>...` (or `--prefix <path>` for every worktree of one repo, plus
`--since YYYY-MM-DD`) prints per-worktree driver sessions, input, cache-read and output tokens,
driver cost, child count and child cost, and a total. It reads `~/.pi/agent/sessions/<slug>/`:
the parent `*.jsonl` (assistant `usage.cost.total`) plus every pi-subagents child's
`subagent-artifacts/*_meta.json` (`usage.cost`). Children are separate processes and never appear in the
driver's own log, so summing the driver log alone undercounts; on the vm-runner core run the
verifiers were ~14% of the total. It still works after `git worktree remove`, so reap freely.
`--prefix` matches on the slug, so `/Users/xavier/code/dekopon/dekopon` would also catch
`dekopon-provider-*`: name worktrees exactly when repos share a stem. `ccusage pi daily` is
right for whole-machine daily totals but groups children by filename (`lane-verifier_transcript`,
`session`) across projects, so it cannot attribute them to one effort. Claude-side spend (fable
reviews, sonnet rehearsals) is not in these files: that is `ccusage claude session`.

A dry run through `pi-dry-run.sh` runs with `--no-session`, so `pi-usage.sh` never sees it: its
cost is the `cost_usd=` on the line the script prints.

**pi's dollars are only as good as its registry.** A model id the installed pi does not list is
priced at the provider default: on `openai-codex` that was `gpt-5.5` ($5 / $0.50 cached / $30),
so the `gpt-6.1-sol` eval logged $0.66 a run for $0.21 of tokens and would have fired every
tripwire three times early. Before trusting a number for a new model, check
`pi --list-models <id>` and reprice the logged tokens at the published rates
(`~/code/dekopon/steering-eval/bin/reprice.py` does it from `log.jsonl`). pi prices are list
prices; the GPT side runs on Xavier's subscription, so they are notional.

**Report Claude spend by role, not only by model.** A per-model total hides where it went.
Group the day's transcripts under `~/.claude/projects/<project>/` by each subagent's
`meta.json` (`agentType`, `description`), deduplicate usage by message id, and scale to the
ccusage totals. On 2026-09-29 that showed supervisors at 29% of Claude spend and the coordinator
session at 17%, where the handoff had said the coordinator "stayed small".

Run it between stages, unasked, and read it beside the diff: spend out of line with diff size,
or a tool tally that is mostly polling, means the driver is stuck on a chokepoint, not working
(dekopon `AGENTS.md` §Large multi-agent runs has the between-wave checks). The 2026-09-27
supervisor did not look until Xavier asked.

## Unattended: the watch loop (2026-09-20)

When Xavier leaves ("make sure it won't get stuck overnight"), run the loop with `ScheduleWakeup`
at 900 s and keep every wakeup to one `scripts/pi-check.sh <log> <worktree>` call plus at most one
`pi-tail.sh` and one small read-only verification. The wakeup prompt carries the whole rule set
so a wakeup needs no memory of this file; copy this block into it and fill the brackets:

- Healthy (`alive=yes` and: `log_age_min<20`, or `builds>0`, or a relevant container is up, or a
  PR check is pending): `noop: true`, reschedule 900 s. A `gh pr checks --watch` idles the log for
  a long time; an open PR with pending checks is healthy.
- Tripwire, checked even when healthy, because a running build is not progress:
  `commit_age_min>=90`, `calls_since_edit>40`, or `top_cmd` at more than 5x. The thresholds are
  the effort's `LIMITS.toml` where it has one. First firing: one `pi-tail.sh` look and, if the
  driver is looping, a correction prompt at its next turn. The same tripwire again after a
  correction: stop the lane and report.
- Turn ended (`alive=no`; `pi-check.sh` prints nothing at all when no process holds the log —
  treat an empty line as `alive=no`): `pi-tail.sh <log> 2 1000`; verify claims read-only
  (`git log`, `git status --short`, `gh pr view --json headRefOid,state`, `gh pr checks`); then
  the next stage as a new `pi-turn.sh` turn in the background, and put the new log path in the
  next wakeup prompt. Ended mid-stage with no report and no question: relaunch at once with the
  continue prompt above. Non-hard stops: decide, record as D<n+1> in the packet's decisions
  file, prompt. Hard stops: park, `stop: true`, report in the final message.
- Several sessions at once: one wakeup runs `pi-check.sh` over every live log in a `for` loop
  and applies these rules per log; the done condition names every report file that must exist.
- Stalled (`alive=yes`, `log_age_min>=20`, `builds=0`, nothing pending): `kill $(lsof -t <log>)`,
  relaunch the same prompt file, note it. Check `<log>.err` first: an empty log with a live pid is
  the stdin stall above, not a model hang.
- Disk: read the floor from the effort's `LIMITS.toml` (`min_free_disk_gib`, less
  `kache_headroom_gib`); 25 GiB where the effort has no such file. Free under the floor → launch
  no more builds, report.
- Done (PR open, every check pass/skipping at the pushed head, and `pi-stage-check.sh` says
  `verdict=ok` for that head): `stop: true`, then the final
  report (PR URL, head SHA, stage verdicts, decisions made, numbers, what is deferred, dead
  worktrees and targets to reap) and one dated line in the project memory note.

CI failure logs: `gh run view --log-failed` returns nothing on this repo. Use
`gh run view <run> --json jobs -q '.jobs[]|select(.conclusion=="failure")|"\(.name) \(.databaseId)"'`,
then `gh api repos/<owner>/<repo>/actions/jobs/<job> -q '.steps[]|"\(.conclusion)\t\(.name)"'` for
the failing step, then
`curl -sL -H "Authorization: Bearer $(gh auth token)" https://api.github.com/repos/<owner>/<repo>/actions/jobs/<job>/logs | grep -n -iE 'error|must |failed|panicked|exit code' | tail -15`.
Send the driver the verbatim error line, never a paraphrase.

Things a literal driver stops on that are not stops (answer from these, record, continue):
`/kache/...` in a rustc source-location note is the compiler-diagnostics path remap, never a
kache failure (the 0.18.0 fleet parked on it once); a `Codex error: Unable to verify … access`
is transient, resume or respawn the child on the same model; `gh attestation verify oci://…`
returns 404 for every provider because the shared release workflow attests the wasm and SBOM
files, not the OCI manifest (verify the release assets instead); a red local test after a fixture
bump in a fresh worktree is a stale gitignored fixture until CI disagrees: refetch, then compare.

## Retro: the 0.18.0 release and fleet drive (2026-09-20)

One day, ~9 hours wall clock, of which the code was under three: core release with zero stops
(1 h 25 m), site push (10 m), eleven provider re-pins (~2 h, batched three at a time), four
code-change providers in parallel sessions (~1 h), python alone 3 h 25 m (a real regression: SDK
0.18.0 dropped Wasmtime's `cache` feature, every testkit test recompiled RustPython, the shared
release job's 30-minute timeout fired twice; fixed inside python's tests). The process losses
were the orphaned-child turn boundary above (~1.5 h across five relaunches), the batching (~1 h),
one false hard stop and one transient (15 m each). The briefs were not over-specified: the two
sonnet dry runs found nineteen defects, at least six of them guaranteed stops or wrong actions.
What was too much: drivers wrote 100+ per-step evidence files under `execution/`; ask for one
report per stage and no per-step receipts.

## One-turn fix session (fresh pi, review-driven)

For a bounded work list that already exists as a file (an adversarial review's F1–Fn, a CI
failure), do not write a packet. First rule on every finding yourself: fix, accepted trade-off
(named in the PR), or ignore; the brief carries the fix set only, since a driver handed a raw
review argues with it or does all of it. Then start a **fresh** pi session (new `--session-id`)
with `templates/FIX-BRIEF.md` filled in, one turn, then the watch loop. The brief's shape: cwd line;
role and the PR/worktree/head; read order (guidelines → decisions → the review file in full; the
stage/verifier files forbidden); "its Fix lines are the spec"; the no-list (WIT, wire, config
keys, dependencies → blocker file instead; no shims, no ignored tests); the §Don't write this
patterns and forward-compat default from `pi-subagent-plan/templates/DRIVER.md`; scoped tests
while iterating, one full gate in the background to a log under `execution/`; one conventional
commit whose body says why (no D-numbers, no local paths), one fresh verifier, push only on
`ACCEPT`, `gh pr checks --watch`, at most two CI rounds; the report fields. First use: PR #305's
`fable-review-2026-09-20.md`, session `fable-fix-2026-09-20`.

## Offer it

When writing a `pi-subagent-plan` handoff, end by offering to drive it from here with this
skill. The pairing Xavier wants is a very high-level Claude over a very cheap driver; he pastes
nothing, and the stops that used to take a day take a turn.
