# pi-drive: material moved out of SKILL.md

Incident narratives, pilot comparisons and receipts removed verbatim from [SKILL.md](SKILL.md) on the rules diet. Not standing rules; no entry point tells an agent to read this first.

## Opening

Why: nine stops on the asset run each cost a day because the loop ran through Xavier. Through
this skill a non-hard stop costs minutes, and fable's context stays small because it reads
tails, never transcripts.

## Which model drives (eval receipt)

on the steering eval's effort block it matched `gpt-6.1-sol` at
`medium` on hidden tests and cost ($0.19 a run) and was 1.85 times faster; its blind score was
1.5 lower, all of it on pipe-type shape. Sub-campaign 4 ran A3-A13 on it (≈ 8,000 lines). Where a
step sets a spine's shape, an Opus agent builds it instead (§A sol supervisor, sub-campaign 4).

## Which model drives (caveat)

Do not conflate that observation with the 1.85x receipt above or infer universal speed gains.

## Which model supervises (cost narrative)

The watch loop, relaunches, read-only
verifications and stage prompts are mechanical and the rules live in the prompt, not in the
model. On 2026-09-29 that loop was the largest Claude line of a $356 campaign: 24 opus
supervisor sessions cost about $70, against about $60 of pi for the drivers that wrote the
production code. D took three supervisors and C, J, T and V two each, and every handoff re-read
the same briefs.

## A sol supervisor (pilot receipts)

Receipts: 2026-09-29 pilot 1 passed (two stages, $0.40 supervisor); pilot 2 failed (a scope
question answered instead of handed back, because the gate leaked scope, and a driver launched
with the `process` tool died); pilot 3 passed on the rewritten template. 2026-09-30 sub-campaign
4 (A2-A13, 9,400 lines) passed with zero decisions of the supervisors' own; a session carried
across five resumes grew to $7.

## Fix rounds (why)

One writer at a time in a worktree, always: the next writer starts only after the previous
  writer's commit exists and its process has exited. Why: in sub-campaign 5 every pi step failed
  its first verify, and sending every second round to Opus put five Opus fix agents on what were
  mostly missing tests; two of the five rounds had no hard finding at all. A mis-tag costs one pi
  turn, because the re-check catches it and step 3 routes it to Opus.

## Dry run note

- **A dry run does not see the tool environment.** Neither dry run caught the `process` tool or
  the leaked scope: both live in what pi loads and what the gate implies, not in the brief's
  steps.

## Verified 2026-09-19

Verified 2026-09-19: print smoke turn returned the text
and `agent_settled`; RPC `get_state` round-tripped.

## Seen five times

Seen five times on the 0.18.0 fleet (file, gpt-image, asset, python
  twice).

## #321

#321 shipped a 412-line commit after its last review and pushed over
  two `FIX REQUIRED` verdicts; this check would have caught both.

## fleet fan-out

The 0.18.0 fleet's workflow-script fan-out lost
  children three different ways (parent turn ended, a transient Codex error, a stop routed
  through the parent); the four parallel sessions that replaced it (F9) had none of those.

## New-model launch day

- **A new model on its launch day runs slow and retries (2026-09-29).** Two of eight
  `gpt-6.1-sol` runs auto-retried on `Codex SSE response headers timed out after 300000ms`,
  `upstream connect error … connection timeout` and a Cloudflare 504 page; one turn took 708 s
  where its neighbours took about 310 s. pi's retry succeeded each time, so this is not a stall
  and not an outage: leave the turn alone. Count them with
  `grep -c '"type":"auto_retry_start"' <log>`, and drop runs that retried from any wall-clock
  comparison.

## Cost: gpt-6.1-sol receipt

so the `gpt-6.1-sol` eval logged $0.66 a run for $0.21 of tokens and would have fired every
tripwire three times early. Before

## Cost: by role receipt

On 2026-09-29 that showed supervisors at 29% of Claude spend and the coordinator
session at 17%, where the handoff had said the coordinator "stayed small".

## Cost: 09-27

The 2026-09-27
supervisor did not look until Xavier asked.

## 0.18.0 receipt

## Receipt: the 0.18.0 release and fleet drive (2026-09-20)

Core, site and fifteen providers in one ~9 h day, under three of it code; drivers wrote 100+
per-step evidence files. Ask for one report per stage and no per-step receipts.

## FIX-BRIEF first use

First use: PR #305's
`fable-review-2026-09-20.md`, session `fable-fix-2026-09-20`.

## The split that works (receipts)

per PR before merge; that review is never cut for cost (2026-09-27: $97 of pi for −2,250 lines,
and every real gap came from the fable reviewer; 2026-09-29: 19 fable reviews and plan checks
for about $50 found every P1). What is cut

## nohup receipt

(four relaunches on the 0.18.0 fleet each waited a
full 15-minute tick for that reason)

## Prompts by file

Long command lines are fragile under the sandbox (a capture run hit it;
  the 100/300/600-byte ladder did not reproduce a hard limit), and the file block caches:
  one test turn read 17,920 tokens from cache for 1,272 fresh ones.

## Provider outage jq

Read it with `jq -c 'select(.type=="message_end" and .message.role=="assistant") |
  .message | {stopReason, errorMessage}' <log>`. Relaunch

## RPC setWidget

Startup emits
`extension_ui_request` lines with `method: setWidget`; those need no answer.

## Cost accounting detail

the parent `*.jsonl` (assistant `usage.cost.total`) plus every pi-subagents child's
`subagent-artifacts/*_meta.json` (`usage.cost`). Children are separate processes and never appear in the
driver's own log, so summing the driver log alone undercounts; on the vm-runner core run the
verifiers were ~14% of the total. It still works after `git worktree remove`, so reap freely.
`--prefix` matches on the slug, so `~/code/proj/proj` would also catch
`proj-plugin-*`: name worktrees exactly when repos share a stem. `ccusage pi daily` is
right for whole-machine daily totals but groups children by filename (`lane-verifier_transcript`,
`session`) across projects, so it cannot attribute them to one effort. Claude-side spend (fable
reviews, sonnet rehearsals) is not in these files: that is `ccusage claude session`.

## kache path receipt

(the 0.18.0 fleet parked on it once)

## pi-last (original wording)

`scripts/pi-last.sh <log.jsonl>` is the blunt
form (tool tally + final text up to 6k) for when one message is all there is.

## Cost reprice (original wording)

Before trusting a number for a new model, check
`pi --list-models <id>` and reprice the logged tokens at the published rates
(`~/code/dekopon/steering-eval/bin/reprice.py` does it from `log.jsonl`). pi prices are list
prices; the GPT side runs on Xavier's subscription, so they are notional.

## Worktree wording (original wording)

- **Worktrees.** `git worktree add <path> -b <branch> origin/main` makes the branch track
  `origin/main`, so a bare `git push` targets main. Run
  `git -C <path> branch --unset-upstream` right after creating it.

