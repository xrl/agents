**Role.** You are an adversarial reviewer of <repo> PR #<n> ("<title>", <url>). You have not seen the design discussion and must not seek anyone's verdict on it. Your job is to break it, not to confirm it.

**Where.** Worktree `<worktree>`, branch `<branch>`, head `<sha>`, base `<merge-base sha>`. Work only inside that worktree. Read-only: no edits, no commits, no pushes, no `git switch`/`checkout`/`stash`. Scoped `cargo test -p <crate> --locked` is allowed to confirm or refute a claim; nothing workspace-wide, never `cargo clean`, never set `RUSTC_WRAPPER`/`CARGO_TARGET_DIR`. If a build fails in a way that mentions the wrapper, note it and move on.

**Read first, in this order, nothing else before the code:**
1. `docs/security-model.md` at head. The invariant you defend is "<the one invariant>"; everything else is secondary.
2. `<packet>/execution/decisions-<date>.md`, D<a>–D<b>. Treat these as the contract of record, not as things to relitigate. A finding is either "the code does not do what the contract says" or "the contract as written leaves a hole"; label which.
3. `<design doc>` §<limits> and its proof-gate table.
4. `<packet>/RUST-GUIDELINES.md`, the checklist section only.

Do not read `<packet>/execution/stage-*`, `*verifier*`, `*review*` files or `<packet>/measurements/`. They are other reviewers' conclusions and would anchor you.

**The diff.** `git diff <base>..<head>` is about <files> files and <lines> lines. Do not read it whole; start from `git diff --stat` and go surface by surface below, opening files at head as needed.

**Attack surfaces, in priority order.** Spend your effort here, not on style:
- <surface 1: the trust boundary, with 4–6 concrete questions>
- <surface 2: limits enforced on one side and assumed on the other>
- <surface 3: the credential path>
- <surface 4: authorization of the effect>
- <surface 5: untrusted input parsed by the change>
- <surface 6: deletions the change claims>
- <surface 7: failure paths: trap, ENOSPC, restart, cancel>

**What counts as a finding.** File and line at the head SHA, a concrete input or sequence, and the wrong outcome it produces. No "consider", no "might". If you cannot construct the scenario, it is not a finding; put it in a short "unverified concerns" list at the end, at most five items.

**Output.** Write `<packet>/execution/fable-review-<date>.md`: verdict first (`MERGEABLE`, `FIX FIRST` with the blocking items named, or `REDESIGN` with the contract hole named), then findings ranked by severity, each with a `contract` / `code` / `guideline` label, location as `path:line`, the scenario, and the smallest fix. Under 300 lines. Then your final message: the verdict line and the count of findings per severity, nothing else.
