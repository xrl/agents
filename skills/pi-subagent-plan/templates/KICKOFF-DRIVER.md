<!-- Turn-1 prompt for a single sequential driver (the default shape, SKILL.md section 0a).
     KICKOFF.md beside this file is for the swarm shape: an orchestrator, lanes and a workflow
     script. First used for the cwasm fix, 2026-09-29. Fill every <…>; delete this comment. -->
Your working directory is `<ABS WORKTREE>/` for everything below; every relative path in this
prompt and in the brief is relative to it. `cd` there first.

You are the driver of <one line: what the PR does>. The brief is `<ABS PLAN FOLDER>/pi/DRIVER.md`;
read it fully first, then the files its §Read list names, in that order. Every decision in
`<ABS PLAN FOLDER>/pi/decisions.md` is settled: do not relitigate it, do not add scope, no
compatibility shims.

Model: this run is `<provider/model>`, you and your verifier. Nothing Anthropic.

Judgement: where the brief's text and its evident intent conflict, follow the intent, record the
discrepancy under Driver decisions, and keep going. Stop only for the stops in the brief's
§Authority, by writing `<ABS PLAN FOLDER>/execution/<topic>-blockers.md` and ending your turn
with its path.

Do stage 1 now: DRIVER.md §Stages step by step and the stage 1 block; §Rules and §Don't write
this apply. Follow step 1 for the base-update merge and record the stage base SHA. One
implementation commit (the why in its body<, one `Changelog:` line>); later fixes are new commits
on top. One full gate per head in the background (the first to
`<ABS PLAN FOLDER>/execution/logs/stage-1-gate.log`); no packaging or smoke. The report at
`<ABS PLAN FOLDER>/execution/stage-1-report.md`, the verifier (`async: false`, or async and
waited on to completion if the harness requires it); push only on `ACCEPT`, never over FIX
REQUIRED; open the PR as a draft. Do not wait on CI in this turn. Do not end your turn while a
subagent or background job is still running: wait on it with one blocking command that returns
when it finishes, never repeated status calls. End with the verdict, head SHA, PR URL and
report path.
