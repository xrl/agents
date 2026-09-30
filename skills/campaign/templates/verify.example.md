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
failure and the exact fix. `contract` and `guideline` make the verdict `FIX REQUIRED`; `taste` is
advisory, listed last, never blocks. End with `ACCEPT` or `FIX REQUIRED` on its own line. At most
one page. A suspicion without a line is not a finding; an unearned ACCEPT is worse than a wrong
finding.

## Your task

- Step <HALF> of unit S1a. Worktree `/Users/xavier/code/dekopon/dekopon.wt/04-s1a-2`.
- Commit range: `<PARENT> <HEAD>` (use exactly this range).
- Decisions file: `/Users/xavier/code/dekopon/campaign/04-shell-bytes/DECISIONS.md`. This step's contract is D18; D16 and D3/D4/D8 for the `head -1` witness; D26 applies to everything. Witnesses: the D18 row and the D3/D4/D8/D16 `while true; do echo y; done | head -1` row of the Witnesses table.
- The brief for this step is its row, and the driver's rules are `/Users/xavier/code/dekopon/campaign/04-shell-bytes/pi/DRIVER.md` §Rules (treat that section as §Don't write this). Nothing else from the plan folder.
- Driver's report: `<REPORT>`. Gate log: `<GATELOG>` (green line `GATE_EXIT=0` or the driver's own).
- Coordinator rulings already made, not findings: a successful provider `Null` crosses a pipe as `display(Null)` (empty) plus one newline; the model-facing `OutputBuffer` pending-line bound and incremental scan, lossy invalid UTF-8 in a final-stage `cat`, `f > buf` for a function, and the uncharged accumulation in `pipe.rs` `read_line`/`drain` and `builtin_input` are carried to A4; the nested-pipeline copy-on-write refund under-count is an accepted trade-off.

Step row:

| Step | What lands | Decisions | Witnesses | Packages | Lines |
|---|---|---|---|---|---|
| **A3** `head`/`tail` | Two new builtins, reserved words and every mirror, the fleet check first | D18 | The D18 row | shell, core, provider-sdk | 600 |

Specific checks: `head` and `tail` accept exactly D18's forms and fail loudly on anything else; `head -n 0` prints nothing and closes its input; `tail -n +N` retains nothing and `+0`/`+1` both mean the first line; `tail -n N` charges its retained lines and is refused past the budget; fragmented and unterminated input; both are in `RESERVED_COMMAND_WORDS` (`dekopon-core/src/lib.rs`, sorted) and every mirror (the drift test, the provider-sdk message, the shell README, the prompt); the report records the fleet check; the `head -1` witness ends with status 0 under `pipefail` and joins every thread. Say whether anything in the diff is outside the row.

Mutate nothing: no file writes, no cargo, no git commands that change state.
