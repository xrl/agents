# Rust agent rules for this machine

Canonical text. `~/.claude/CLAUDE.md` imports this file; `~/.pi/agent/AGENTS.md` §"Rust worktrees
and compiler cache" is a verbatim copy. Change all three together. Rationale and measurements:
[RUST_WORKTREES.md](RUST_WORKTREES.md). Updated 2026-09-17.

## Machine state

- **kache is the global `rustc-wrapper`** in `~/.cargo/config.toml` (Homebrew `kache`, 0.22.0 at
  the switch). It replaced sccache on 2026-09-17 by owner decision, with copy-on-write restores
  as the reason: outputs live once in a content-addressed store and are cloned into each
  worktree's own `target/`.
- Store `~/Library/Caches/kache`, config `~/.config/kache/config.toml`: local-only, **20 GiB**
  cap, `cache_executables = false`, adaptive incremental on. Daemon runs on demand; the launchd
  service is deliberately **not** installed.
- Every worktree keeps its own default `target/`. No global `CARGO_TARGET_DIR`, `build.target-dir`
  or `build.build-dir`, ever.
- sccache is retired as the wrapper. Its binary may remain; its server should not be running.

## Rules

1. **Run ordinary `cargo …`.** The wrapper is infrastructure. Never set `RUSTC_WRAPPER` or
   `CARGO_BUILD_RUSTC_WRAPPER` in the environment, never run `kache init` (it would install the
   daemon as a service), never edit `~/.cargo/config.toml` or the kache config unless the owner
   asks for exactly that.
2. **If a build fails in a way that involves kache, or results look suspicious, stop and tell
   the owner.** Do not bypass the wrapper, do not set `KACHE_FALLBACK`, do not switch to sccache.
   `kache doctor`, `kache why-miss <crate>` and `kache stats` are for diagnosis; report what they
   say.
3. **Never share a build directory between worktrees.** A shared `CARGO_TARGET_DIR`/`build-dir`
   serializes builds and can serve another worktree's code with tests still passing
   (cargo#17312/#12516, reproduced on dekopon).
4. **A target kache has built stays with kache** (#971: restored rlib/rmeta are mode 444). A
   target built earlier by sccache is fine to continue under kache; the reverse is not.
5. Leave Cargo incremental settings alone; kache's adaptive incremental lane handles it. Do not
   set `CARGO_INCREMENTAL=0` to improve statistics.
6. Never hardlink active build outputs; never forge source mtimes to make a copied target Fresh.
7. Prefer package/test-scoped Cargo commands while iterating; run workspace-wide gates once,
   when required.
8. `cargo clean` is not routine hygiene. When work lands, `git worktree remove <path>` then
   `git worktree prune`; never `rm -rf` a registered worktree.
9. Parallel agent workers each own a worktree whose `target/` grows to tens of GB. The
   orchestrator deletes a worker's `target/` at hand-off (commits integrated, no cargo/rustc
   running there). With kache a reaped target comes back in seconds, so this is the cheap lever;
   the store and any target with a live build are never the lever.
10. Under disk pressure: check live `cargo`/`rustc` processes and registered worktrees first;
    remove inactive per-worktree `target/` directories before touching the store; never stop or
    purge the store while builds are active. Follow the `free-up-worktree-space` skill rather than
    guessing. Report compiler-store size and worktree-target size separately; `df` or APFS
    private size is the receipt, `du` counts every clone at full size.
11. A cache hit is executable code. Cache-key correctness, hidden compile inputs (proc macros
    reading undeclared files need `extra_inputs`), toolchain identity and the local-only trust
    boundary are security properties, not tuning details.
12. The wrapper is a **host** setting. A Linux container (measurement harnesses, CI images) builds
    with plain `cargo` and no wrapper: never mount `~/.cargo/config.toml` into it, never pass
    `RUSTC_WRAPPER` in, never install kache inside it. Its target lives in a named volume, not
    in the worktree's `target/`.

## Known open items at the switch

- Gate 1 of the pilot (a `KACHE_VERIFY=1` full dekopon workspace build + clippy + test) had not
  been run when kache went global; package-level correctness had passed. Run it in a quiet window
  and record the result here.
- #998: on macOS, `cc`-built archives with DWARF (`ring`, `zstd-sys`, `psm`) take a path-bound
  key and miss in every checkout. Hit rate only, not correctness; `CFLAGS=-g0` works around it.
- lldb on a kache-built binary needs `settings set target.source-map /kache/workspace <checkout>`.
- `kache stats` reported `Dedup: 0.0% savings` at the switch; whether that counter reflects
  cross-target clones or only intra-store dedup is unverified.
