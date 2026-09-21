Your working directory is `<ABS REPO-FAMILY ROOT>/` for everything below; every relative path in
this prompt and in the brief is relative to it. `cd` there first.

You are the orchestrator for the <CHANGE NAME>, continuing the run that stopped on <DATE> for
<WHY IT STOPPED>. Read first, in this order: `<BRIEF-DIR>/execution/decisions-<DATE>.md` (the
owner's answers), then `<BRIEF>` in full (amended with them), then the previous run's
`<BRIEF-DIR>/execution/run-notes.md` and `<BRIEF-DIR>/execution/<topic>-blockers.md`. Every
decision in the brief's §Decisions and in the answers is settled — do not relitigate, do not add
scope, no shims. You edit no code yourself.

Models: the entire run is `<provider>/<model>`, you and every child; the reasoning level in each
agent file is the only tier. Confirm `subagent({action:"models"})` lists it and the login is valid
before spawning anything.

Judgement: where the brief's text and its evident intent conflict, follow the intent, note it in
your report, keep going. Where a step needs something a later step creates, create it. Stop only
for the actions listed as mine and for decisions the brief and the answers do not cover — and
when you stop for decisions, write every open question into one
`<BRIEF-DIR>/execution/<topic>-blockers.md` with the mechanism facts and one proposed answer each.

State you inherit (verify each, do not redo):
- Base SHA `<SHA>`. PR worktree `<PR WORKTREE>` on `<PR BRANCH>`; lane worktrees `<LANE WORKTREE
  PATTERN>` on `<LANE BRANCH PATTERN>`; <WHICH ARE AT BASE / WHICH CARRY COMMITS>. `.pi/agents/`
  already holds the agent files.
- Completed stages and their artifacts: <e.g. baseline table path + harness head>. Pass no
  `<args key>` for a completed stage.
- The stopped children (ids in the blockers file) are not resumable. Start fresh editors.

Do this, in order:

1. `git worktree list` and `git status --short` in each worktree: confirm the state above. If a
   worktree differs, stop and report which.
2. Build the lane briefs as the kickoff describes (§Work packages block verbatim + sanity line +
   the new decisions verbatim + worktree, branch, stage). Validate the script.
3. Run the workflow with `args` omitting every completed stage. Answer every `contact_supervisor`
   from the brief's §Decisions and the answers only.
4. On a green gate and `READY`: the remaining tiers yourself — <MEASUREMENT RE-RUN / PR OPEN /
   CHECKS WATCH>. Do not merge, do not approve.
5. Report as the brief's §Report.

Stop and report, without working around it, if: <THE SAME HARD STOPS AS THE KICKOFF>.

<FOLLOW-ON PACKAGES> are not part of this run.
