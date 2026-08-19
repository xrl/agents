# Concurrent Rust worktrees without N× disk

Status: **kache pilot; sccache remains the machine-wide default** (2026-08-18).

## Verdict

The right boundary is:

- **Separate Cargo lock domains:** every worktree keeps its own `target/`.
- **Shared physical bytes:** compiler outputs live once in a content-addressed store and are materialized into each `target/` with copy-on-write clones.
- **Bounded storage:** the compiler store has a hard cap, and stale worktrees still get reaped.

That gives agents true concurrent Cargo processes without paying for N physical copies of every identical artifact. A shared `CARGO_TARGET_DIR` is the wrong abstraction: Cargo protects it with build/artifact locks, so independent agents serialize. Plain per-worktree targets are safe but multiply disk. `sccache` avoids compilation, but its normal restore writes another physical copy into every target.

On APFS, a reflink is the missing primitive. It gives every target file a separate inode and therefore separate mutation/locking semantics, while unchanged extents share physical blocks. This is **logical isolation with physical sharing**, not a shared build directory.

## Current machine state

Production/default:

- Homebrew `sccache 0.17.0`
- Global wrapper in `~/.cargo/config.toml`
- Local cache in `~/Library/Caches/Mozilla.sccache`
- Hard cap: 8 GiB
- Per-worktree `target/`; no global `CARGO_TARGET_DIR`

Pilot tooling:

- Homebrew `kache 0.14.2`, installed but **not** the global wrapper
- Pilot config: `~/.config/kache/config.toml`
- Local-only 8 GiB store; no daemon or remote cache
- Homebrew `fclones 0.35.0` for read-only duplicate measurement and possible offline APFS reflink migration

Do not run `kache init` yet: it would replace the global sccache wrapper and install a daemon before the pilot gates below are complete.

## What was measured

### sccache is a CPU cache, not target deduplication

The machine-wide sccache reached its old 32 GiB ceiling while worktree targets remained full-sized. Reducing it to 16 GiB reclaimed about 16 GiB, but another concurrent build wave later drove the disk to 115 MiB free. The emergency ceiling is now 8 GiB.

This does not make sccache bad. Its pre-incident cumulative hit rate was about 74% overall and 67% for Rust, with local hits around 3 ms. It makes deleting a target cheap to recover from. It does not make a live target small.

### Post-hoc APFS deduplication helps, but is cleanup rather than architecture

A read-only `fclones` scan of three Dekopon targets selected 23.7 GB of files at least 1 MiB. It found 2.2 GB physically deduplicable across 482 files; an APFS reflink dry-run projected about 2.1 GB reclaimed. No files were changed.

Useful as a migration/maintenance tool, but it has three limits:

1. The disk peak already happened before the scan.
2. Hashing and replacement must not race a build.
3. Exact-byte matches miss semantically reusable outputs whose embedded paths differ.

Never hardlink active Cargo outputs. If `fclones dedupe` is adopted, run it only behind a maintenance lock after every Cargo/rustc process is idle, and verify metadata-sensitive builds first.

### Zero-copy compiler-cache probe

An isolated `kache 0.14.2` probe built two divergent worktree roots concurrently, each with a private target and the same dependency graph:

- Cold concurrent wall time: 25.5 s.
- 28 cacheable units compiled; the peer worktree restored the other 28.
- No `Blocking waiting for file lock on build/artifact directory` message.
- Target A: 151.6 MiB logical; target B: 132.2 MiB logical.
- Kache identified about 210 MiB of those targets as cache-backed APFS CoW data against a 98.3 MiB content-addressed store.
- Deleting both targets and rebuilding concurrently took about 9–10 s per worktree with all cacheable units hitting.
- Restores were 100% zero-copy; no artifact bytes were copied.
- Both produced binaries ran successfully; a full blob checksum scrub passed.

The cost is stricter keying: warm-hit key computation averaged roughly 168 ms per unit in this small probe, much slower than sccache's local lookup. The wall-clock result stayed concurrent because Cargo and kache parallelized independent units.

## Candidate: kache

[`kache`](https://github.com/kunobi-ninja/kache) is a `RUSTC_WRAPPER` with a content-addressed blob store. On APFS it reflinks blobs into each target, giving separate inodes and shared extents. Per-key locks prevent duplicate compiler work without introducing a single Cargo target lock.

Pilot command:

```bash
RUSTC_WRAPPER=/opt/homebrew/bin/kache \
KACHE_VERIFY_RESTORES=always \
cargo test -p <package>
```

The global pilot config keeps it local-only, bounded to 8 GiB, disables executable caching, and does not install a daemon. Do not add `KACHE_FALLBACK=sccache` during disk measurements: two compiler stores obscure the result and consume the headroom the pilot is trying to preserve.

### Gates before making it global

Kache is young and correctness matters more than hit rate.

1. **Real-repo correctness:** build/test Claria and Dekopon from two paths; compare behavior with uncached builds.
2. **Edit-loop latency:** kache normally removes Cargo's incremental flag and uses an adaptive isolated incremental lane for changing primary units. Large hot crates may need `cache.incremental_crates`; measure before choosing names.
3. **Hidden compile inputs:** audit proc macros and compile-time file reads. Kache supports per-crate `extra_inputs`, but [issue #760](https://github.com/kunobi-ninja/kache/issues/760) demonstrates an unresolved stale-hit case involving `include_dir!`/proc-macro file reads across worktrees.
4. **Debugger fidelity:** executable caching stays off until LLDB and dSYM restoration are verified on macOS.
5. **Native dependencies:** pilot `CC="kache cc"` / `CXX="kache c++"` separately. Unsupported compiler shapes pass through; do not assume `cc-rs` discovers kache the way it discovers sccache.
6. **Integrity:** keep sampled or always-on restore verification during the pilot and run `kache doctor --checksums` periodically. Blob integrity does not prove an under-keyed compile was semantically correct, so required project tests remain the final gate.
7. **Disk behavior:** use `kache clean --dry-run` and `df`, not `du` alone. `du` can report the logical size of every reflink even when APFS stores the extents once.

Only after those pass:

1. stop all Cargo/rustc work;
2. replace the global wrapper with `/opt/homebrew/bin/kache`;
3. run representative clean-target builds;
4. verify reports, tests, debugging, and physical disk use;
5. stop and remove the old sccache store only after rollback is no longer needed.

## Cargo's native direction

Cargo 1.97 has stabilized the split between:

- `target-dir`: final user-facing artifacts;
- `build-dir`: intermediate dependencies, fingerprints, build-script output, and incremental state.

Cargo also contains `-Zfine-grain-locking`, which replaces the whole-build-cache lock with per-unit locking and implicitly enables the new build-dir layout. This is directly aimed at concurrent build caches, but it remains nightly-only and its tracking work is still open:

- [fine-grained locking #4282](https://github.com/rust-lang/cargo/issues/4282)
- [per-user compiled artifact cache #5931](https://github.com/rust-lang/cargo/issues/5931)

A shared intermediate `build-dir` plus local final `target-dir`s may eventually become the native answer. Do not put `RUSTC_BOOTSTRAP=1` or nightly Cargo into the global developer path to get it early. The cache and locking implementation is still evolving, and divergent worktrees are exactly the correctness-sensitive case.

## Agent rules

1. Ordinary builds remain `cargo ...`; the configured wrapper is infrastructure, not something each agent invents.
2. Never point concurrent worktrees at one `CARGO_TARGET_DIR` under Cargo's coarse lock.
3. Never hardlink active build outputs. Reflinks are safe because later writes are copy-on-write.
4. Do not run `cargo clean` as routine hygiene. Remove completed worktrees; delete an inactive target only under disk pressure.
5. Prefer narrow package/test commands during iteration, then required workspace gates once.
6. Treat compiler cache size and worktree target size separately in disk reports.
7. `df` is the physical-space receipt on APFS. `du` is still useful for logical ownership, but it can double-count shared extents.
8. A cache hit is executable code. Cache-key correctness, hidden inputs, toolchain identity, and local-only trust boundaries are security properties, not tuning details.
