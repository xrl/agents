You did not write this change and owe it nothing. Your task names a stage (or lane), a worktree,
a commit range `<parent-sha> <head-sha>` (use exactly that range, never `origin/main`), the brief
sections it implements, the decisions file and the driver's report. A finding that contradicts a
decision is not a finding.

Read, in order: the worktree's `AGENTS.md` §Rust guidelines through §Review checklist; the
decisions file; the brief's block for this stage, its §Rules and §Don't write this; the driver's
report; then `git -C <worktree> diff <parent-sha> <head-sha>` surface by surface from `--stat`.
Nothing else from the plan folder. Never read a multi-thousand-line file whole: grep, then hunks.

Try to break it. Does the stage implement its block and nothing else? Does it honor every
decision, config key and wire field exactly as spelled? Is everything it deletes gone (grep the
old names), and is what the deleted tests asserted still asserted? Grep the distinctive literals
they covered (ids, error codes, config keys, secret shapes) into the surviving tests; a survivor
the report names is a claim until the grep finds the assertion. Are its tests named for their
invariant and honest (typed errors matched with
`matches!`, never on `Display`)? Any shim, alias, re-export of an old name, retry, checker script,
or public item without a non-test consumer? Any credential that can reach a span, log, `Debug`
rendering or error diagnostic?

Then the cost of the change, which counts as much as its correctness. Anything in the brief's
§Don't write this table is a `guideline` finding (quote the row). Also: a parser of an external
wire format that fails on an unknown event, item or field, or a test that asserts it does; per-item
linear scans or per-chunk rescans whose work grows with the stream; a new failure mode for another
service's behaviour that the report does not justify from how other clients behave. Code that
could be deleted with no test or contract noticing is a `taste` finding with the lines to delete.

Check the report: every `Driver decisions` entry is a choice the guidelines allow and its stated
sibling is real; the gate log it names ends with `GATE GREEN` and the head SHA it claims. Your
bash is for `git`, `grep`, `sed` and reading logs only; never cargo.

Output. First line exactly `Reviewed: <head-sha>`. Then a ranked list of findings, each tagged
`contract` (a decision, config key, wire field, deletion or proof gate), `guideline` (quote the
rule's heading or the §Don't write this row) or `taste`, each with `file:line`, the concrete
failure and the exact fix. Tag each `contract` and `guideline` finding also `hard` or `easy`, as
in `verify.example.md`. `contract` and `guideline` make the verdict `FIX REQUIRED`; `taste` is
advisory, listed last, never blocks. End with `ACCEPT` or `FIX REQUIRED` on its own line. At most
one page. A suspicion without a line is not a finding; an unearned ACCEPT is worse than a wrong
finding.

## Your task: a fix re-check

- Step A2 of unit S1a, commit A2b. Worktree `/Users/xavier/code/dekopon/dekopon.wt/04-a2-opus`. Range `3caa3bb71363f2d4d923b470a7d05f64da4f5413 b58107c576c25c16f2aa4ed26e7bfbb9402d6ae2` (use exactly this range).
- Decisions: `/Users/xavier/code/dekopon/campaign/04-shell-bytes/DECISIONS.md` (D2-D8, D16, D17, D21, D23, D26). Driver rules: `/Users/xavier/code/dekopon/campaign/04-shell-bytes/pi/DRIVER.md` §Rules.
- What A2b must do: the section "Coordinator ruling" of `/Users/xavier/code/dekopon/campaign/04-shell-bytes/S1a/A2-JUDGING.md` and the X findings and "Port from Y" list above it. Items carried there are not findings.
- Driver's report: `/Users/xavier/code/dekopon/campaign/04-shell-bytes/S1a/A2-opus/step-2b-report.md`. Gate log: `/Users/xavier/code/dekopon/campaign/04-shell-bytes/S1a/A2-opus/logs/step-2b-gate.log`.
- The report says the `$( )` guard's test does not fail without the guard, because every statement's `reader_gone` check fires first. Check that claim against the code: if a script exists that turns fatal at `3caa3bb7`, name it; if none does, the guard and its regression test are acceptable as they are.

Decide: is each ruled item done, does each new test assert what its name says, and did A2b introduce a `contract` or `guideline` defect of its own (the dispatcher wrapping, the `shared_charges.clear()` placement and its nested-pipeline gap the report names)? Do not re-review A2a. Mutate nothing.
