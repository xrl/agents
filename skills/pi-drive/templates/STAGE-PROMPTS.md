# Supervisor turn prompts (not driver reading)

Turn 1 is `KICKOFF.md` verbatim. Each later turn is one of these, filled in. Session id
`<effort>-driver-<date>`, model `openai-codex/gpt-6-astra:high`, workdir the worktree, one log per
turn under `<design>/execution/pi/`. Before sending "Next stage", run
`scripts/pi-stage-check.sh <worktree> <stage parent> <design>/execution`: accept only when HEAD
is the reviewed SHA and the stage is under the cap (or was split).

**Next stage (N = 2..last):**

> Stage N−1 accepted at <sha>. Stage N now: rebase onto origin/main first and check the previous
> head's PR checks, then DRIVER.md §Stages step by step and the stage N block; §Don't write this
> applies. One commit (the why in its body), one full gate after it in the background to
> `<design>/execution/logs/stage-N-gate.log`; no packaging or smoke; the report at
> `<design>/execution/stage-N-report.md`, the verifier (`async: false`, or async polled to completion when the harness requires final-review children to run async); push only on `ACCEPT`,
> never over FIX REQUIRED; refresh the PR body. <Cross-review stages: then the pr-reviewer; last
> stage: `gh pr ready` only on `READY`, `gh pr checks --watch` in the background and polled.> Do
> not end your turn while a subagent or background job is still running: poll it with short
> sleeps until it finishes. End with the verdict, head SHA and report path.

**Answer to a stop:**

> <The answer, in your terms.> <The mechanism fact behind it.> Recorded as D<n> in
> `pi/decisions.md`. Record it under Driver decisions and continue stage N from the current
> state. Do not end your turn while a subagent or background job is still running.

**Turn ended mid-stage with no report or question:**

> Your previous turn ended mid-stage. Continue stage N from the current state (`git log`,
> `git status`, the gate log, any verifier you spawned); write the report when done. Do not end
> your turn while a subagent or background job is still running: poll it with short sleeps until
> it finishes.

**Unreviewed or oversize head (from `pi-stage-check.sh`):**

> HEAD <sha> is not the SHA your last verifier reviewed (<reviewed sha>; commits since: <list>)
> / stage N is <n> changed lines, over the ~1k cap. Run a fresh verifier over <reviewed>..HEAD
> (or split the stage as DRIVER.md §Rules says), apply its findings, update the report and the PR
> body, push only on ACCEPT. Do not end your turn while a subagent or background job is still
> running.

**Correction after a failed read-only check:**

> Your report says <claim>; at <sha> <command> shows <verbatim line>. Fix it within stage N,
> amend, rerun the gate once, re-verify, update the report. Do not end your turn while a subagent
> or background job is still running.
