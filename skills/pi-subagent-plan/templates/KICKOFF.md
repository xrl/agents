Your working directory is `<ABS REPO-FAMILY ROOT>/` for everything below; every relative path in
this prompt and in the brief is relative to it. `cd` there first.

You are the orchestrator for the <CHANGE NAME>. The brief is `<BRIEF>`; read it fully first, then
`<DESIGN>` and the "Facts an implementer must be told" list in `<REVIEW>`. Every decision in the
brief's §Decisions is settled — do not relitigate it, do not add scope, no compatibility shims. You
edit no code yourself; you run the brief's §Execution plan through pi-subagents as described in its
§Running it on pi-subagents.

Models: this entire run is `<provider>/<model>` — you and every child. Nothing Anthropic. The
agent files in `<BRIEF-DIR>/pi/agents/` already say so; the reasoning level in each file (medium
editors and fact-checker, low gate-runner, high verifiers, max reviewer) is the only tier. Before
spawning anything, confirm `subagent({action:"models"})` lists that id and that the provider login
is valid; fix `model:` in the agent files if pi names the provider differently.

Judgement: where the brief's text and its evident intent conflict, follow the intent, note the
discrepancy in your report, and keep going. Where a step needs something a later step creates,
create it. Stop only for the actions listed as mine and for decisions the brief's §Decisions does
not answer — and when you stop for decisions, first answer every child's `contact_supervisor`
with stop/preserve, then write one `<BRIEF-DIR>/execution/<topic>-blockers.md` listing every open
question with the mechanism facts and one proposed answer each, so I answer them all at once.

Do this, in order:

1. Clean slate. If a previous attempt left `<PR WORKTREE>` or any `<LANE WORKTREE PATTERN>`
   worktree, `git worktree remove --force` it and `git worktree prune`; delete branches
   `<PR BRANCH>` and `<LANE BRANCH PATTERN>` if present. Preserve untracked fixtures in the primary
   checkout; never edit or switch branches there.
2. Preflight, the brief's §Preflight, steps 1–N (the baseline-measurement step runs inside the
   workflow in step 5): confirm <BASELINE PRs> are merged; fetch and record the `origin/main` SHA
   and create the PR worktree `<PR WORKTREE>` on branch `<PR BRANCH>` from it; check disk and
   foreign `cargo|rustc`; fetch fixtures in the PR worktree; verify toolchain pins from inside the
   worktree; run the baseline gate green before any edit; re-verify the review's locators against
   that SHA with `git show` and note drift.
3. Create the lane worktrees from the same SHA with the shell in the brief, and copy
   `<BRIEF-DIR>/pi/agents/*.md` into the PR worktree's `.pi/agents/`.
4. Build the lane briefs: for each lane, the §Work packages block verbatim plus its sanity-check
   line plus the worktree path and branch, and its `stage` (1 for lanes nothing consumes, 2 for
   lanes that merge stage-1 branches first, per the brief's §Decisions lane order). Validate the script:
   `subagent({ action: "validate", workflowScriptPath: "<BRIEF-DIR>/pi/lanes.workflow.js" })`.
5. Run it: `subagent({ workflowScriptPath: "<BRIEF-DIR>/pi/lanes.workflow.js", args: { prRoot,
   prBranch: "<PR BRANCH>", lanes: [{ key, stage, worktree, branch, brief } …], maxRounds: 3, measure: { sha, worktree: "<MEASURE WORKTREE>",
   branch: "<MEASURE BRANCH>" } } })`. Create the measure worktree from the SHA first, like the
   lane worktrees. Answer every `contact_supervisor` with `need_decision` from the brief's
   §Decisions only; if it does not answer, stop and ask me — never guess.
6. When it returns `{ head, gate, review, lanes, baseline }` with a green gate and `READY`: run
   the remaining tiers yourself — the measurement re-run against the baseline table (acceptance
   in the brief), then open the PR with `.github/pull_request_template.md`, then
   `gh pr checks --watch`. Do not merge, do not approve.
7. Report as the brief's §Report: PR URL and head SHA; per lane what changed with file:line; the
   before/after measurement table; every gate run and its result; what in the brief was wrong;
   what you left out; disagreements; free space before/after and which `target/` you removed.

Stop and report, without working around it, if: a fact in the brief is wrong in a way that
changes a contract; <CHANGE-SPECIFIC HARD STOPS>; the gate is still red after three rounds; a
provider login fails; or any step needs a release, a tag (crate or chart), a published package, a
private-repo commit, or a real external/paid call — those are mine. Editing version fields in
`Chart.yaml`, `Cargo.toml` or `CHANGELOG.md` inside the PR is ordinary work, not a release.

<FOLLOW-ON PACKAGES> are not part of this run; wait for me after the core PR is open.
