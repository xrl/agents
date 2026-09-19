# Rust cache validation

Read before cache diagnosis, upgrades, or verification. **kache is standard;
unverified gates are work to complete, not permission to bypass it.**
First read [host rules](RUST_AGENT_RULES.md).

## Status and authority

As of 2026-09-19, this reorganization adds no new build evidence. The canonical
[switch-time open items](RUST_AGENT_RULES.md#known-open-items-at-the-switch)
remain unverified here: full-workspace correctness, native archive cross-path
misses, debugger source mapping, and dedup-counter meaning. Clippy and edit-loop
checks also remain unclosed in the [dated gate snapshot](RUST_CACHE_HISTORY.md#gates-status-at-the-2026-09-17-switch).
Do not infer closure from adoption, elapsed time, or package-level success.

## Before a check

1. Get authorization for the actual build or configuration change; this checklist
   is not authorization. Coordinate a quiet window for expensive measurements.
2. Record repository/head, toolchain and kache versions, exact command, and scope.
3. Check disk and active builds. Never share targets, bypass kache, or silently
   change incremental settings. Cleanup requires owner quiescence, not just `ps`.
4. Confirm verification controls against the installed version before using them.
   The history mentions both `KACHE_VERIFY=1` and `KACHE_VERIFY_RESTORES=always`;
   their current semantics have not been verified here.

## Evidence to record

- Full-workspace build, Clippy, and tests: exact commands, exit results, head, and
  verification mode. Package success is not a workspace correctness receipt.
- Hidden compile inputs: identify undeclared proc-macro inputs and required keys.
- Performance: uncontended cold/warm timing, hit counts, edit-loop cost, and scope.
- Disk: controlled `df` deltas; exclusive APFS bytes are not total occupancy.
- Debugging/native archives: observed behavior and current issue status, not old
  issue labels copied forward as facts.

Append new dated evidence here; update the canonical host file and its mirrors
when closing a switch-time item. Keep old measurements in
[RUST_CACHE_HISTORY.md](RUST_CACHE_HISTORY.md). On wrapper failures or suspicious
results, stop and report; do not manufacture a green result by switching wrappers.
