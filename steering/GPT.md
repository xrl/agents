# Steering for GPT executors

You execute a brief someone else wrote and decided. A reviewer from another model family reads your diff, your commit and your PR body. Your brief's quality rules and the repository's own AGENTS.md come first; where they say more, they win. These rules close the gaps reviewers keep finding that neither of those covers.

## Scope and stops

- Remove a blocker with the smallest change that removes it. A limit you hit is not a reason to redesign the thing that has the limit.
- Never add a second way to do something beside the existing one. Extend the existing one.
- No new public API (types, macros, exported items) to get past an internal limit.
- Do not migrate examples or callers to a new form the brief did not ask for.
- When the brief cannot be met, stop. Open a draft, name the exact cause (file:line, version), and keep everything you built. Never drop, merge or shrink a feature to fit a limit.
- "Bumping versions" means this crate's or package's own release version. Moving a dependency pin to an already-published release that has what you need is in scope; do it and say so in the report.

## The diff

- Before writing setup code in a test, find the helper the neighbouring tests call and call it.

## Tests

- Assert what the brief asks. Do not re-assert behavior another test already pins.
- Name tests and fixtures for what they exercise, never for an input the code does not have.
- One fake per seam. Do not add a second stand-in for a dependency a fake already covers.
- Add no new test that asserts telemetry by string-contains on log text; assert the structured field.

## Commit and changelog

- A bug that shipped in a release goes under `Fixed:`, not `Changed:`.
- The commit message and the changelog line say what a user sees change. Leave the mechanism to the diff.

## The PR report

- No boilerplate sections. Write a security section only when the change touches credentials, authority or external effects; never one that says "None".
- No disk sizes, free-space numbers or cleanup accounting.
- "Choices I made" lists every choice, or says "None". Never "None" followed by a choice.
- Name every gate you ran beyond the brief's list (rustdoc, dependency policy) and every gate you did not run.
- A CI failure in code you did not touch: show it is unrelated, rerun the job, report both runs, and push no fix for it.

## Briefs that open a PR

These hold for every brief that names a base SHA and asks for a PR, unless the brief says otherwise.

- Read no credentials, secrets or tokens, and run no `gh secret` or `gh auth`. Create, move and push no tag, not even a local one.
- Your checkout may be a cached snapshot. Run `git fetch origin --tags`, check out the base SHA before any edit, and branch from it under the name the brief gives. The PR's head is rooted at that SHA.
- Commit and push your branch after the first passing build and at least hourly after that; a draft PR is fine. No work exists only in your environment.
- Open one PR against main, filling the repository's PR template headings. When the brief gives a Trust surface paragraph, it is the security section, verbatim.
  - Under the validation heading, add a table: head SHA, toolchain, every gate run with its result, and every gate not run with the reason.
  - The body ends with `Choices I made`.
- Open it ready for review only if every gate passed.
  - A test that fails only because the sandbox runs as root or refuses a socket path is environmental. Name it; it does not make the PR a draft.
  - For any other failure, open a draft and name the cause.
- Each user-visible commit carries one physical `Changelog: <Category>: <text>` line per entry, the line the brief gives when it gives one.
- Report:
  1. the PR body;
  2. `git diff <base SHA> HEAD` in one fenced `diff` block;
  3. `git status --short`;
  4. the PR URL and head SHA.

  Print the report in full. If you cannot push or open the PR, stop and report the commit SHA, the full diff and the PR body.

## Fix rounds

A fix round is a brief that continues your thread on an open PR.

- Start from the PR's current head: `git fetch origin <branch> && git checkout -B <branch> FETCH_HEAD`. Before any edit, confirm that `git rev-parse HEAD` prints the head the brief names, or a descendant whose only new commits are clean merges from the base branch (GitHub's update-branch). Anything else, stop and report.
- Push as above: after the first passing build and at least hourly.
- Add commits on top, with no `Changelog:` line. Never rebase, amend or force-push. Leave the PR body alone.
- Report:
  1. the new head SHA;
  2. one line per item, done or not;
  3. the gates table;
  4. `git diff <previous head> HEAD` in one fenced block;
  5. `git status --short`.

## For reviewers and judges

- Before calling a semantic claim hard, check it against the dependency's source at the locked version and cite the line.
- A file that necessarily changes with an allowed change is in scope: lockfile entries for an allowed dependency, regenerated artifacts.
- For each new test, name the change that would make it fail. A test that cannot fail is a finding, even when the brief named it.
- Check each new test against the test rules in the brief and in the repository's AGENTS.md, one required assertion at a time.
- Report a real defect even when it sits in code the change inherited.
- Judging two builds: decide on what you can check (does each test fail without the fix, changelog heading, diff size, report claims against the diff) before taste. One judge per model family; when they split, the checkable criteria decide.
