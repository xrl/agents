---
name: pi-drive
description: Drive a pi coding-agent session from Claude Code, so a high-level Claude (fable) supervises a cheap driver (gpt-6-astra) turn by turn — issuing stage prompts, reading only the driver's last message and decision files, answering its stops from the decisions file, and escalating to Xavier only for the four hard stops. Two paths — print mode (one process per turn, simplest) and RPC mode (one long-lived process, can steer mid-turn). Use when Xavier says "drive the pi", "run the driver from here", "supervise the pi session", "super high level fable with cheap gpt", or right after a pi-subagent-plan handoff is written and he says yes to being driven. Claude Code only.
argument-hint: "[brief path] [workdir] [print|rpc]"
arguments: [brief, workdir, path]
disable-model-invocation: false
user-invocable: true
---

# Driving pi from Claude Code

The shape: **you are the supervisor, pi is the driver.** The driver (gpt-6-astra, high
reasoning) does all the editing, building and committing in its own worktree under a brief
written with `pi-subagent-plan` (`DRIVER.md` style: decide-and-record, four hard stops). You
never edit its worktree. You issue one stage at a time, read its last message and its decision
files, answer what it stopped on from the brief's decisions file, and ask Xavier only for the
four hard stops (forking or patching a dependency, moving a contract away from the decisions
file, reversing a keep/delete, owner-only actions). Everything else you decide and record.

Why: nine stops on the asset run each cost a day because the loop ran through Xavier. Through
this skill a non-hard stop costs minutes, and fable's context stays small because it reads
tails, never transcripts.

## Before the first turn

1. `pi --version` (0.85.x verified), `pi auth check` or `subagent({action:"models"})`-equivalent:
   `pi --list-models gpt-6-astra` shows `openai-codex/gpt-6-astra`. Provider id is
   `openai-codex/…`, not `openai/…`.
2. The brief exists and passed `pi-subagent-plan` §5 (invention audit empty). The workdir on its
   line 1 exists; `.pi/agents/` in the PR worktree holds the verifier/reviewer files.
3. Pick a session id (`asset-core-driver-2026-09-19`) and a state dir in the scratchpad or
   under the brief's `execution/`. Everything the driver must persist goes in files the brief
   names (`execution/*.md`, `Driver decisions` in its report), not in your context.
4. Say which path you are using and why (below). Default: **print**.

## Path A — print mode (default)

One process per turn; the process exit is your wake-up.

```
scripts/pi-turn.sh <workdir> <session-id> openai-codex/gpt-6-astra:high <log.jsonl> <prompt-file>
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
  the gate commands it lists, `gh pr view`. A driver's report is a claim, not a receipt.

Same `--session-id` every turn keeps its context; the first turn logs `No project session found
… creating` to stderr, which is expected. Verified 2026-09-19: print smoke turn returned the text
and `agent_settled`; RPC `get_state` round-tripped. Session files live under `~/.pi/agent/sessions/`;
never read them whole. Print mode cannot steer mid-turn; if you must, `pkill -f "session-id <id>"`
ends the turn and the next prompt says what changed.

## Path B — RPC mode (long-lived, steerable)

One `pi --mode rpc` process behind a FIFO; JSON-line commands in, events out.

```
scripts/pi-rpc-start.sh <workdir> <state-dir> <session-id> openai-codex/gpt-6-astra:high
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
  turn while a subagent or background job is still running: poll it with short sleeps until it
  finishes"*, and a turn that ends mid-stage is relaunched at once with *"your previous turn
  ended mid-stage; continue from the current state (git log, gh pr view, subagent status for
  any verifier you spawned); write the report when done"*. A foreground `subagent()` call does
  keep the process alive; `ps` for `cargo`/`rustc` shows what the child is doing.
- One stage per prompt. Do not re-explain the brief; point at its section. Each stage prompt
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
  driver's worktree, read-only. Never edit there; if something is wrong, the next prompt says so.
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
- Auth: an expired OpenAI login shows as an immediate exit with an error in `<log>.err`.
  Tell Xavier; do not switch models.
- End of run: the driver's PR URL and head SHA, every stage's verdict, the decisions you made,
  the hard stops you asked, and `pi-rpc-stop.sh` if on path B.

## Unattended: the watch loop (2026-09-20)

When Xavier leaves ("make sure it won't get stuck overnight"), run the loop with `ScheduleWakeup`
at 900 s and keep every wakeup to one `scripts/pi-check.sh <log>` call plus at most one
`pi-tail.sh` and one small read-only verification. The wakeup prompt carries the whole rule set
so a wakeup needs no memory of this file; copy this block into it and fill the brackets:

- Healthy (`alive=yes` and: `log_age_min<20`, or `builds>0`, or a relevant container is up, or a
  PR check is pending): `noop: true`, reschedule 900 s. A `gh pr checks --watch` idles the log for
  a long time; an open PR with pending checks is healthy.
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
- Disk: free < 8 GiB → launch no more builds, report.
- Done (PR open, every check pass/skipping at the pushed head): `stop: true`, then the final
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
files, not the OCI manifest (verify the release assets instead).

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
failure), do not write a packet: start a **fresh** pi session (new `--session-id`) with
`templates/FIX-BRIEF.md` filled in, one turn, then the watch loop. The brief's shape: cwd line;
role and the PR/worktree/head; read order (guidelines → decisions → the review file in full; the
stage/verifier files forbidden); "its Fix lines are the spec"; the no-list (WIT, wire, config
keys, dependencies → blocker file instead; no shims, no ignored tests); scoped tests while
iterating, one full gate in the background to a log under `execution/`; one conventional commit,
push, `gh pr checks --watch`, at most two CI rounds; the report fields. First use: PR #305's
`fable-review-2026-09-20.md`, session `fable-fix-2026-09-20`.

## Offer it

When writing a `pi-subagent-plan` handoff, end by offering to drive it from here with this
skill. The pairing Xavier wants is a very high-level Claude over a very cheap driver; he pastes
nothing, and the stops that used to take a day take a turn.
