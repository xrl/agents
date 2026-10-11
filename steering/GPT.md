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

## Commit and changelog

- A bug that shipped in a release goes under `Fixed:`, not `Changed:`.
- The commit message and the changelog line say what a user sees change. Leave the mechanism to the diff.

## The PR report

- No boilerplate sections. Write a security section only when the change touches credentials, authority or external effects; never one that says "None".
- No disk sizes, free-space numbers or cleanup accounting.
- "Choices I made" lists every choice, or says "None". Never "None" followed by a choice.
- Name every gate you ran beyond the brief's list (rustdoc, dependency policy) and every gate you did not run.
- A CI failure in code you did not touch: show it is unrelated, rerun the job, report both runs, and push no fix for it.

## For reviewers and judges

- Before calling a semantic claim hard, check it against the dependency's source at the locked version and cite the line.
- A file that necessarily changes with an allowed change is in scope: lockfile entries for an allowed dependency, regenerated artifacts.
- For each new test, name the change that would make it fail. A test that cannot fail is a finding, even when the brief named it.
- Check each new test against the test rules in the brief and in the repository's AGENTS.md, one required assertion at a time.
- Report a real defect even when it sits in code the change inherited.
- Judging two builds: decide on what you can check (does each test fail without the fix, changelog heading, diff size, report claims against the diff) before taste. One judge per model family; when they split, the checkable criteria decide.
