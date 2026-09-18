# Concurrent Rust worktrees without N× disk

Status: **kache is the machine-wide wrapper since 2026-09-17** (owner decision; gates 1–3 below were not all met — see [RUST_AGENT_RULES.md](RUST_AGENT_RULES.md) §Known open items). The agent-facing rules live in [RUST_AGENT_RULES.md](RUST_AGENT_RULES.md); this document is the study and the rationale. (updated 2026-09-17; first written 2026-08-18)

## Verdict

The right boundary is:

- **Separate Cargo lock domains:** every worktree keeps its own `target/`.
- **Shared physical bytes:** compiler outputs live once in a content-addressed store and are materialized into each `target/` with copy-on-write clones.
- **Bounded storage:** the compiler store has a hard cap, and idle targets still get reaped.

On APFS, a reflink is the missing primitive. It gives every target file a separate inode and therefore separate mutation/locking semantics, while unchanged extents share physical blocks. This is **logical isolation with physical sharing**, not a shared build directory.

Two things are now settled:

1. **Sharing a target or build dir is incorrect, not just slow.**
   - Worktrees at different commits map each workspace crate to the same unit slot.
   - Freshness compares mtimes, so one worktree can run the other's code while its tests pass.
   - Reproduced on dekopon on 2026-09-10. Upstream this is cargo#17312, closed as a duplicate of #12516, which is still open. Cargo says it is "unlikely to change the relative paths".
2. **kache is the only shipping tool that shares build outputs correctly on APFS.**
   - On a real dekopon package it reused workspace crates across worktree paths and copied zero bytes on restore.
   - It took no build-dir lock and passed tests and a checksum scrub.
   - It remains gated on open macOS bugs (below).

There is no VFS route. macOS has no overlayfs, and FSKit, macFUSE and fuse-t all route every rustc file operation through user space.

## Current machine state

See [RUST_AGENT_RULES.md](RUST_AGENT_RULES.md) §Machine state — the one place this is kept. In
short: kache 0.22.0 is `build.rustc-wrapper` in `~/.cargo/config.toml`; store 20 GiB, local-only,
no executables, daemon on demand and not installed as a service; sccache retired as the wrapper.
History: sccache 0.17.0 was the default until 2026-09-17, with an 8 GiB cap after the 2026-09
disk incident; kache ran as an env-override pilot (`RUSTC_WRAPPER=/opt/homebrew/bin/kache`) for
pi-run builds from 2026-09-11.

## What was measured

### sccache is a CPU cache, not target deduplication

The machine-wide sccache reached its old 32 GiB ceiling while worktree targets remained full-sized. Reducing it to 16 GiB reclaimed about 16 GiB, but another concurrent build wave later drove the disk to 115 MiB free. The emergency ceiling is now 8 GiB.

Its pre-incident cumulative hit rate was about 74% overall and 67% for Rust, with local hits around 3 ms. It makes deleting a target cheap to recover from. It does not make a live target small:

- It never caches incremental workspace crates.
- Rust cache keys still include the checkout path. `SCCACHE_BASEDIRS` normalizes C/C++ only (mozilla/sccache#2652).
- The opt-in clone-restore mode (mozilla/sccache#2739, `file_clone`) is open with no reviews. Even if merged, it would share dependencies only.

### Where a dekopon target's bytes are

A read-only split of a live 14.2 GiB target (2026-09-10):

| Component | GiB |
|---|---|
| incremental | 4.3 |
| `.o` | 2.8 |
| rlib | 2.8 |
| 47 test/bin executables | 2.0 |
| rmeta | 1.0 |
| proc-macro dylibs | 0.3 |

rlib+rmeta, the part any dependency dedup can share, is ~27%. Incremental is ~30%.

### Post-hoc APFS deduplication helps, but is cleanup rather than architecture

A read-only `fclones` scan of three Dekopon targets selected 23.7 GB of files at least 1 MiB. It found 2.2 GB physically deduplicable across 482 files; an APFS reflink dry-run projected about 2.1 GB reclaimed. No files were changed.

Useful as a migration/maintenance tool, but it has three limits:

1. The disk peak already happened before the scan.
2. Hashing and replacement must not race a build. `fclones dedupe` only re-checks file length unless given `--modified-before`.
3. Exact-byte matches miss semantically reusable outputs whose embedded paths differ.

Never hardlink active Cargo outputs.

### Real-package comparison (2026-09-10)

`dekopon-storage-host`: 40 units, stable 1.97 with sccache, nightly 1.100, kache 0.19.0.

"Physical" is APFS private size (`ATTR_CMNEXT_PRIVATESIZE`), the bytes shared with no clone. A live agent swarm moved `df` by 30 GiB mid-run, so `df` could not be used.

| Mechanism | Build | Fresh / rebuilt | Physical | Correct |
|---|---|---|---|---|
| Own target (baseline) | 10.4 s cold | 0/40 | 310 MiB | yes |
| Cloned target, stable, divergent commit | clone 0.6 s + 3.2 s | 37/3 | 47 MiB | yes |
| Cloned target, sources forced older than seed | 0.2 s | 40/0 | 0 | **no**: main's code, tests pass |
| kache, two worktrees concurrently | 11.5 / 12.5 s | 30 restored cross-path | 23 + 11 MiB | yes |
| kache, both targets deleted, rebuilt | 6.8 / 7.0 s | 62/63 hits | 2.7 + 2.5 MiB | yes |
| Shared build-dir, coarse lock (nightly) | second waits for the whole first build | 40/0 | shared | **no** |
| Shared build-dir, `-Zfine-grain-locking` | 9–16 s, hung 2/5 | 49/50 rerun | shared | **no** |
| Cloned target + `-Zchecksum-freshness` | 0.17 s same commit / 1.7 s divergent | 40/0 ; 39/1 | 0 ; 97 MiB | yes |

kache costs:

- ~120–156 ms of key computation plus ~80 ms of dep-info per unit.
- ~10 build scripts recompile on every build.
- Edit loop: 1.55 s, then 1.44 s, then 0.59 s once its adaptive incremental lane engaged, against ~0.54 s flat for Cargo incremental + sccache.

The 2026-08-18 kache 0.14.2 probe on a small two-root graph agreed:

- The builds ran concurrently with no lock wait.
- The peer restored 28 of 56 cacheable units.
- Deleted targets rebuilt in 9–10 s with 100% zero-copy restores.

## Shared target and build dirs are incorrect

- **Same slot.** Path packages hash relative to the workspace root, so `crates/foo` is the same unit in every worktree (`build/dekopon-storage-host/145d5a5a2677edea/`). A newer dep-info written by another worktree counts as Fresh.
- **Coarse lock.** The second worktree printed `Blocking waiting for file lock on build directory`, reported 40/40 Fresh, and linked main's code.
- **`-Zfine-grain-locking`:**
  - It waited on per-unit locks, then reran 49 of 50 units anyway: serialization without dedup.
  - `cargo test` in the first worktree then ran the second worktree's test binaries.
  - 2 of 5 concurrent pairs hung at 0% CPU in `flock`, and 2 of 4 more with `-Zchecksum-freshness` added.

## Candidate: kache

[`kache`](https://github.com/kunobi-ninja/kache) is a `RUSTC_WRAPPER` with a content-addressed blob store.

- **Restores:** it tries an APFS clone first, then a hardlink (rlib/rmeta only, never executables), then a copy.
- **Locks:** per-key locks prevent duplicate compiler work without introducing a single Cargo target lock.
- **Path normalization:** checkout paths become `/kache/workspace` placeholders, and kache injects `--remap-path-prefix`.
- **`CARGO_MANIFEST_DIR`:** it stays in the key, so a crate using `env!("CARGO_MANIFEST_DIR")` misses across worktrees instead of silently reusing the other checkout's path.

Since 2026-08-18:

- **#760** closed 2026-08-20.
  - The reporter was using a shared `CARGO_TARGET_DIR`, and two kache path bugs were also fixed.
  - Proc macros that read files through undeclared `std::fs` calls still need `extra_inputs`.
- **0.15.0:** concurrent hardlink restores no longer share mutable inodes. The cache key format changed.
- **0.17.0:** the size default is now 5% of the disk. `KACHE_VERIFY=1` recompiles every hit and compares.
- **0.19.0:** fixes missing source info in macOS dSYMs for cached debug builds (#996).
- **Maintenance:** one effective maintainer; 0.14.2 → 0.19.0 took 27 days. Pin versions and treat upgrades as events.

Open (checked 2026-09-11):

- **#971, no fix PR.** Restored rlib/rmeta keep the store's mode 444, so a later non-kache build in that target fails with "not writeable".
  - Cargo's fingerprint ignores `RUSTC_WRAPPER`: switching sccache→kache is safe, kache→sccache breaks.
  - Rollback: `chmod u+w` those files, or delete the target.
- **#998, fix PR #999 open.** On macOS, `cc`-built archives with DWARF take a path-bound key, so `ring`, `zstd-sys` and `psm` miss in every checkout. This costs hit rate, not correctness; `CFLAGS=-g0` works around it.
- **#720:** the macOS daemon times out on restart.

Verification command (kache is now the configured wrapper, so no env override):

```bash
KACHE_VERIFY_RESTORES=always cargo test -p <package>
```

Do not add `KACHE_FALLBACK=sccache`: two compiler stores obscure disk measurements and consume headroom.

### Gates (status at the 2026-09-17 switch)

1. **Real-repo correctness:** one `KACHE_VERIFY=1` full dekopon workspace build + clippy + test.
   - Run it in a quiet window; it recompiles every hit, so it counts as a heavy build.
   - Package-level correctness passed on 2026-09-10.
2. **Clippy:** unverified with `clippy-driver` as `RUSTC_WORKSPACE_WRAPPER` under kache.
3. **Edit-loop latency:** ~1 s extra on the first two edits of a small crate. Re-measure on a large hot crate before choosing `cache.incremental_crates`.
4. **Hidden compile inputs:** proc macros that read undeclared files need `extra_inputs`.
5. **Debugger fidelity:** lldb needs `settings set target.source-map /kache/workspace <checkout>`. Executable caching stays off.
6. **Native dependencies:** track #998. Pilot `CC="kache cc"` / `CXX="kache c++"` separately.
7. **Store cap and daemon:** keep the 8 GiB pin, and decide the daemon explicitly.
8. **Disk behavior:** measure with `df` or APFS private size, never `du` alone.

### Rollout (executed 2026-09-17, globally rather than scoped)

The owner chose the global wrapper over the directory-scoped variant below, with a 20 GiB store,
before gates 1–3 were closed. The scoped plan is kept for the record:

1. **Byte-triggered reaper.** When free space drops below a floor, delete `target/` in worktrees with no live cargo/rustc, oldest first.
   - It works under either wrapper; with kache a reaped target comes back in seconds.
2. **Gate 1** in a quiet window.
3. **Scope kache by directory, not globally:** `~/code/dekopon/.worktrees/.cargo/config.toml` with `build.rustc-wrapper = "/opt/homebrew/bin/kache"`.
   - Cargo merges configs from the cwd upward, and deeper files beat `~/.cargo/config.toml`. The swarm switches; the main checkout and sibling repos stay on sccache.
   - A build escapes that scope when cargo runs from outside the tree (`--manifest-path`), when the worktree lives elsewhere, or when `RUSTC_WRAPPER` / `CARGO_BUILD_RUSTC_WRAPPER` is set in the environment.
   - Do not delete existing targets at the switch; they stay Fresh.
4. **Amend the global incremental rule** for that scope in the same change: kache replaces Cargo incremental with its adaptive lane.
5. **Hold the swarm at its 4-heavy-build cap**, record `df` and store size, then raise the cap.

## Clone-seeded targets (stable fallback)

`cp -c -R -p <base>/target <new>/target` clones a warm target in seconds with mtimes preserved; worktrunk's `wt step copy-ignored` does the same file by file.

- Registry and git dependency units stay Fresh and share extents.
- Every workspace crate rebuilds, because checkout mtimes are newer.

Rules:

- **Sources must be newer than the seed.** A seed built after the checkout serves stale code. With source mtimes forced older, a divergent worktree reported 40/40 Fresh and ran main's code while its tests passed. Touch tracked files after seeding if the order is in doubt; never forge old mtimes.
- **Seed only an empty `target/`,** from a base nobody builds into.
- **Drift is safe.** Unit hashes do not depend on the worktree path, so Cargo.lock or feature drift just rebuilds.
- **`CARGO_MANIFEST_DIR` is untracked.** A Fresh unit keeps the seed's value, so dekopon's test-support `workspace_root()` then points at the seed worktree.
- **Avoid a single whole-directory `clonefile`.** It blocks changes to that tree while it runs, and worktrunk reverted it after a 236K-file target saturated APFS metadata IO.
- **Unmeasured variant:** clone the frozen base tree *including sources*, then let git rewrite only the files that differ. Only changed crates would rebuild on stable. It carries the same `CARGO_MANIFEST_DIR` hazard.

With `-Zchecksum-freshness` (config form `build.fingerprint = "content"`, cargo#17382), a cloned target is correct regardless of mtimes: 0 rebuilds on the same commit, one crate on a divergent commit. It is nightly-only; revisit when it stabilizes.

kache makes clone-seeding redundant: it already restores dependencies as clones.

## Cargo's native direction (corrected 2026-09-11)

- **`build.build-dir` stabilized in Cargo 1.91** (2025-10-30), not 1.97 as this document previously said.
  - 1.96 gave build-dir its own `.cargo-build-lock` (cargo#16708).
  - 1.97 made `.cargo-lock` shared and added `.cargo-artifact-lock` (cargo#16886).
- **The new per-unit build-dir layout** stabilized 2026-08-18 (cargo#17354) and ships in Cargo 1.100 on 2026-11-12.
- **`-Zfine-grain-locking`** makes the build lock shared and adds one lock per unit; the artifact lock stays exclusive. It is still `-Z`, with no stabilization PR or FCP. It is not a sharing mechanism for divergent worktrees (above). Tracking: [cargo#4282](https://github.com/rust-lang/cargo/issues/4282).
- **The cross-workspace cache** ([cargo#5931](https://github.com/rust-lang/cargo/issues/5931), 2026 project goal) targets nightly around October 2026.
  - It covers registry and git packages only, hardlinked from a content-addressed store.
  - Workspace crates are out of scope.
- **cargo#17453** proposes moving all build-dir content into a reflink-first content-addressed store. Proposal only.
- **Target-dir GC** (cargo#13136) has a PR idle since July; `-Zgc` covers only `~/.cargo`.

Do not put `RUSTC_BOOTSTRAP=1` or nightly Cargo into the global developer path to get any of this early.

## Dead ends

- **Shared `CARGO_TARGET_DIR` or `build.build-dir`:** incorrect for divergent worktrees, and fine-grain locking hangs.
- **Overlay or union filesystems for `target/`:** macOS has none. An FSKit passthrough filesystem burned 100–150% CPU, against 40% on macFUSE (Apple Developer Forums thread 799283), and fuse-t cannot set atime and mtime independently.
- **APFS snapshots as a base layer:** volume-wide, read-only, and they need root plus an entitlement.
- **Per-agent APFS volumes or disk images for sharing:** clones cannot cross volumes.
- **A per-worktree `build.build-dir` under one cache root:** shares nothing, and removing the worktree no longer frees the bytes.
- **Linux VM builds for macOS artifacts:** Docker's Mac file sharing can truncate timestamps to whole seconds, which breaks freshness. A target kept inside the VM only produces Linux artifacts.

## Agent rules

Moved to [RUST_AGENT_RULES.md](RUST_AGENT_RULES.md), the single canonical copy that
`~/.claude/CLAUDE.md` imports and `~/.pi/agent/AGENTS.md` mirrors.

## Sources

- **kache:** kunobi-ninja/kache issues #720, #760, #971, #996, #998; PR #999; `docs/deduplication.mdx`
- **sccache:** mozilla/sccache PR #2739; issue #2652
- **Cargo:** rust-lang/cargo #4282, #5931, #12516, #13136, #14136, #16708, #16886, #17312, #17354, #17382, #17453
- **Project goal:** [cargo cross-workspace cache](https://rust-lang.github.io/rust-project-goals/2026/cargo-cross-workspace-cache.html)
- **worktrunk:** [`wt step copy-ignored`](https://worktrunk.dev/step/); max-sixty/worktrunk #736, #3150
- **Practitioner write-up:** [howardjohn: shared Rust builds](https://blog.howardjohn.info/posts/shared-rust-build/) (2026-02-18)
