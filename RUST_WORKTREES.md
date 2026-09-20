# Rust worktrees: share bytes, not build directories

Read for cache/worktree architecture. For commands and safety rules, read
[RUST_AGENT_RULES.md](RUST_AGENT_RULES.md). **kache is the standard host wrapper.**

## The boundary

- Each worktree owns its `target/` and Cargo lock domain.
- kache restores cached outputs using copy-on-write where supported.
- APFS clones have separate inodes while sharing unchanged extents.
- Private targets still grow; cleanup requires an ownership handoff preventing
  new builds, followed by a check that no build is running.

## Why shared targets are wrong

Cargo can identify path packages relative to the workspace root. Two divergent
worktrees sharing a build directory can therefore reuse the same unit slot and
run the other worktree's code—even with passing tests. Coarse locks serialize
builds; finer locks do not fix artifact identity.

The 2026-09-10 Dekopon probe reproduced 40/40 Fresh units from the wrong tree.
See [measurements and sources](RUST_CACHE_HISTORY.md#shared-target-and-build-dirs-are-incorrect).

## Copy-on-write is not hardlinking

A clone separates mutation; a hardlink shares an inode. Never hardlink active
outputs or chmod restored cache artifacts: a hardlink fallback can expose the
store to writes. Do not switch wrappers on a kache-built target.

A content-addressed cache is executable input. Key correctness, hidden proc-macro
inputs, toolchain identity, and the local trust boundary matter more than hit rate.

## Measure the right thing

APFS private size counts exclusive bytes, not total occupancy. Shared extents
can remain allocated after store eviction. `du` counts clones at full size;
neither it nor summed private sizes proves reclaimed disk space. Use controlled
`df` deltas, and report store and target measurements separately.

## Do not infer relocation safety

Clone-seeding targets is unnecessary under kache. Preserved mtimes can hide stale
source; checksum freshness addresses that problem, not compiled-in paths such as
`CARGO_MANIFEST_DIR`. Path-sensitive units need separate validation or rebuilding.
Never forge old source mtimes to obtain Fresh results.

## Evidence and open checks

- [History](RUST_CACHE_HISTORY.md): experiments, alternatives, rollout snapshots.
- [Validation](RUST_CACHE_VALIDATION.md): how to resolve outstanding checks.
- [Host policy](RUST_AGENT_RULES.md): current settings and mandatory safety rules.

## Relocated study sections

Legacy section anchors below lead here; the full dated study is in
[RUST_CACHE_HISTORY.md](RUST_CACHE_HISTORY.md), not an additional operating guide.

<a id="concurrent-rust-worktrees-without-n-disk"></a>
<a id="verdict"></a>
<a id="current-machine-state"></a>
<a id="what-was-measured"></a>
<a id="sccache-is-a-cpu-cache-not-target-deduplication"></a>
<a id="where-a-dekopon-targets-bytes-are"></a>
<a id="post-hoc-apfs-deduplication-helps-but-is-cleanup-rather-than-architecture"></a>
<a id="real-package-comparison-2026-09-10"></a>
<a id="shared-target-and-build-dirs-are-incorrect"></a>
<a id="candidate-kache"></a>
<a id="gates-status-at-the-2026-09-17-switch"></a>
<a id="rollout-executed-2026-09-17-globally-rather-than-scoped"></a>
<a id="clone-seeded-targets-stable-fallback"></a>
<a id="cargos-native-direction-corrected-2026-09-11"></a>
<a id="dead-ends"></a>
<a id="agent-rules"></a>
<a id="sources"></a>
