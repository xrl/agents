# Laws of Software

Pithy, opinionated rules I work by. Every law has receipts in the repos I run
(`rdkit-rs/rdkit`, `rdkit-rs/rdkit-debian`, `rdkit-rs/cheminee`,
`knievel-ads/knievel`, `vasovagal/corti`). Where a repo breaks a law, I say so — the rule survives
because the exception is named.

## The Build Rules

### 1. Build natively per arch. Stitch with a manifest.

Native runners beat emulation on speed, debuggability, and cache hit rate. A
matrix of arch-specific runners + a tiny `docker manifest create` job to
fan-in is the recipe.

- `cheminee/.github/workflows/build_docker_images.yml:14-20` — matrix of
  `buildjet-16vcpu-ubuntu-2204` and `…-arm`; a separate 2-vCPU `push` job at
  L118-143 stitches with `docker manifest create -x86_64 -aarch64`.
- `rdkit-debian/.github/workflows/build.yml:57-64` — same shape on
  GitHub-hosted `ubuntu-latest` and `ubuntu-24.04-arm`.

**Exception, not aspiration:** `knievel/.github/workflows/release.yml:54-89`
falls back to `setup-qemu-action` + buildx for the multi-arch *server* image
because a hosted Linux arm64 runner isn't worth the spend yet. Native is the
default; emulation is a budget decision and you write it down.

### 2. Don't compile your app inside Docker.

Cargo cache, sccache, and your debugger all live on the host. A Dockerfile
that runs `cargo build` throws away the host's cache, hides errors behind a
buildx layer, and makes "rebuild and try again" a 90-second round trip
instead of a 2-second one. The image's job is to *package* a binary, not
produce one.

- `cheminee/Dockerfile:43-45` — `COPY target/release/cheminee
  /usr/local/bin/cheminee`. No `cargo` in the Dockerfile. The build happens on
  the runner with sccache (`build_docker_images.yml:82-83`).
- `knievel/Dockerfile:67-70` — explicit comment: *"The Node build runs OUTSIDE
  the container so pnpm's store cache works natively, and the Dockerfile
  stays free of a Node toolchain."*

**Honest exception:** if the artifact only ever ships as a container, the
in-Docker build cost is paid once at release. The knievel server image *does*
compile inside Docker (`knievel/Dockerfile:22-56`) for exactly that reason —
it's never distributed any other way. The CLI binaries from the same repo,
which *are* distributed standalone, build natively
(`release.yml:108-151`). **The artifact's distribution shape determines the
build shape.**

**Other honest exception:** building a *system library* (RDKit C++ → `.deb`)
inside a pinned `debian:bookworm` container is fine — that's using Docker as
a clean toolchain for a one-shot, S3-cached output, not as your inner-loop
compiler (`rdkit-debian/.github/workflows/build.yml:65`,
`rdkit-debian/Dockerfile`).

### 3. A tag is a vote of confidence. Don't re-run CI on it.

Tags are cut from `main`. `main` is already green because branch protection
made it green. Re-running the per-PR matrix on the tag commit is a tautology
that costs ~25 min of release wall-time and produces near-zero new signal.
Release workflows do only tag-specific work: build, sign, publish, attest.

- `knievel/.github/workflows/release.yml:14-23` is the manifesto: *"this
  workflow trusts the PR gate and only does the things that are intrinsically
  tag-specific."*
- `cheminee/.github/workflows/build_docker_images.yml:1-4` and
  `generate_ruby_gem.yaml:1-3` both `on: push: tags: ['*']` with no `needs:`
  on tests.
- `cheminee/test_suite.yml:2` runs only on `pull_request` — it doesn't even
  *exist* for tags.

**Corollary:** tag-triggered jobs are parallel siblings, not chained.
Cheminee's tag fans out to a Docker build *and* a Ruby gem build at the same
time off the same tag.

## The Release & Artifact Rules

### 4. Pin by digest, not by floating tag.

OCI tags are mutable references; digests aren't. Once a consumer pulls a
digest, that's the bits they have forever. Don't re-point a tag — cut a new
patch.

- `knievel/RELEASE_PLAYBOOK.md:71-83`, with the Helm chart pinning
  `image.tag=sha256:<digest>` at L99-100.

### 5. Cache big upstreams in S3, not in your build system.

GitHub Actions cache, runner cache, layer cache — all of it evicts. RDKit
takes ~30 minutes to compile from source; we never do, because we built it
once and put the tarball in `s3://rdkit-rs-debian/`. Every downstream `curl`s
it.

- Producer: `rdkit-debian/.github/workflows/build.yml:117` pushes to S3.
- Consumers: `rdkit/.github/workflows/test_suite.yml:41-46`,
  `cheminee/Dockerfile:11-21` curl prebuilt
  `rdkit_2024_09_1_ubuntu_22_04_*.tar.gz` from the bucket.

### 6. Disable build-time downloads in vendored C++ deps.

CMake's habit of fetching from GitHub at configure time is incompatible with
reproducible, offline-capable builds. Turn the features off rather than
maintain patch sets.

- `rdkit-debian/build.sh:38-43` — `-DRDK_BUILD_COORDGEN_SUPPORT=OFF
  -DRDK_BUILD_MAEPARSER_SUPPORT=OFF -DRDK_BUILD_FREESASA_SUPPORT=OFF`.

### 7. The version of the upstream lives in the tag.

A `git tag` should answer "what RDKit is in this build?" without reading a
lockfile.

- `rdkit-debian` tag format `Release_YYYY_MM_P+BUILD_NUMBER`
  (`rdkit-debian/.github/workflows/build.yml:31-43`) — upstream version
  + packaging revision in one string.

### 8. `sccache`/`rust-cache` everywhere, identically configured.

Pinned action SHA, identical setup steps across every workflow in every repo.
Drift here means cache-misses you never debug.

- `mozilla/sccache-action@eaed7fb9...` reused verbatim at
  `rdkit/.github/workflows/test_suite.yml:23-30` and
  `cheminee/.github/workflows/test_suite.yml:20-27`.
- `knievel/.github/actions/rust-setup/action.yml` centralizes
  `Swatinem/rust-cache` so every CI job inherits the same setup.

### 33. Publish crates from CI over OIDC. Stored registry tokens are bootstrap credentials, not operating credentials.

crates.io Trusted Publishing exchanges a GitHub OIDC JWT for a registry token
scoped to the registered crates. The token expires after 30 minutes, and
`rust-lang/crates-io-auth-action` revokes it again in its post step. A stored
API token can also be crate-scoped, endpoint-scoped, and given an expiry — do
not exaggerate its blast radius — but it remains an independently reusable
bearer credential that has to be distributed, rotated, and revoked. Eliminate
the standing CI secret; use OIDC for steady-state publishing.

`id-token: write` belongs only on the smallest publish job. It is a **job-wide
capability**, not a permission granted to the auth step: any action or command
in that job can request a valid JWT for the same workflow identity. Therefore:

- SHA-pin every `uses:` edge in the privileged job, including actions reached
  through local composite actions. Pinning only the auth action is not enough.
- Build, test, and run `cargo publish --dry-run` without `id-token: write` first.
  Keep the real publish job short and give it no permission beyond
  `id-token: write` and, if it checks out source, `contents: read`.
- Bind a protected GitHub Environment when branch/tag or reviewer gates are
  available, and register that same environment at crates.io.
- Pass the action's token output only to the publish step. Never persist or log
  it, even though expiry and the post-step revocation bound a leak.

**The crates.io side is a JSON API, not just a settings form.** Use a short-lived
setup token with the `trusted-publishing` endpoint scope and only the intended
crate scopes:

```
POST https://crates.io/api/v1/trusted_publishing/github_configs
Authorization: <scoped setup token>
{"github_config":{"crate":"claria-core","repository_owner":"claria-ai",
                  "repository_name":"claria","workflow_filename":"publish.yml",
                  "environment":"release"}}
```

For a workspace, derive the crate list from `cargo metadata`; its `publish`
field already distinguishes unrestricted publishing (`null`), disabled
publishing (`[]`), and named registries. Do not maintain a second crate array.
`cargo publish --workspace` derives dependency order and waits for each crate
to reach the index before publishing dependants.

The GitHub binding is repository-owner identity, repository, workflow
**filename**, and optional environment — not a branch or tag. Rename the
workflow or change its environment and the exchange stops authenticating until
the configs are updated.

**The first publish still needs an API token under crates.io's current model.**
The config endpoint authenticates and scope-checks the caller, then resolves
`crate` as an existing crate before storing a binding. A new name therefore
returns `404 crate "x" does not exist`. Verified against the live API on
2026-08-18: all twelve Claria 0.32.0 crates reached exactly that post-auth
failure. Bootstrap them once with an expiring token scoped to `publish-new`,
register Trusted Publishing with a token scoped to `trusted-publishing`, then
revoke the setup credentials. Bootstrap with tokens; do not operate with them.

- **Source receipt:** crates.io's token-exchange controller sets a 30-minute
  expiry; `crates-io-auth-action@c6f97d42` (v1.0.5's verified commit) performs
  the exchange and its post action sends the revocation.
- **Workspace receipt:** `claria#135` / `a3d2299` derives twelve publishable
  crates from metadata and automates the JSON registration. Review also found
  the important near-miss: its OIDC-enabled job still reaches floating action
  refs, directly and through `rust-setup`. Those refs must be SHA-pinned or
  moved to an unprivileged job before that workflow is safe to merge.

## The Service & API Rules

### 9. The OpenAPI spec is the contract. Server and clients derive from it.

Hand-written clients drift. The spec lives in code (annotations on handlers),
gets emitted as a build artifact, and CI fails if the checked-in spec ever
disagrees with the source.

- `cheminee/src/rest_api/api/api_v1.rs:24-37` — `#[OpenApi]` +
  `#[oai(path = "...", method = "post")]` (`poem-openapi`); spec is derived
  from source.
- `knievel/.github/workflows/ci.yml:162-169` — `openapi-drift` job runs
  `cargo xtask openapi --check` so a hand-edited spec fails CI.

### 10. Generated clients live in their own repo. Upstream commits, downstream publishes. Same tag.

Clients are not vendored into the server repo, and they're not published from
the server repo either. The server's tag workflow generates the client code
and pushes a commit (with the matching version/tag) to the client repo. The
client repo's own CI takes it from there: it builds and publishes to the
language registry. This keeps three concerns from tangling: the API source of
truth, the generated artifact, and the language-specific release machinery.

- `cheminee/.github/workflows/generate_ruby_gem.yaml:65-83` — the upstream
  tag job runs `cheminee rest-api-server spec -o openapi.json`, runs
  `openapi-generators/openapitools-generator-action`, then auto-commits to
  `cheminee-ruby`. The downstream repo's `rake release` does the actual
  publish.
- `knievel/.github/workflows/release.yml:299-315, 362-369` — `release-ruby-gem`
  regenerates from `openapi.yaml` at upstream tag time and pushes to the
  client repo, which owns publishing.

**Why same tag:** a consumer reading a bug report that says "broken in
v1.4.2" needs to find v1.4.2 of the client. Different tags between server and
client means a lookup table no one maintains.

**Why downstream publishes:** RubyGems / npm / crates.io credentials live
where the artifact is. The server repo doesn't need a `GEM_HOST_API_KEY`; the
client repo does. Blast radius shrinks; secrets stay scoped.

### 11. One binary, many subcommands.

The server, the bulk-indexer, and the ops tools live in the same binary and
ship in the same image. `kubectl exec` and run an ops command in the
production image — same code, same deps, no separate "tools" container to
keep in sync.

- `cheminee/src/main.rs:15-32` — `clap` subcommands: `rest-api-server`,
  `bulk-index`, `index-sdf`, `fetch-pubchem`, all the searches.
- `cheminee/charts/cheminee/templates/deployment.yaml:41-44` — pod runs
  `cheminee rest-api-server`; the same image runs `cheminee index-sdf` via
  `kubectl exec`.

### 12. Schema versions are values in a registry, not migrations.

For analytical schemas where multiple shapes coexist (`descriptor_v1`,
`descriptor_v2`, …), bumping a key is cheaper and safer than running a
migration over historical data.

- `cheminee/src/schema/mod.rs:10` — `LIBRARY: HashMap<&'static str, Schema>`
  keyed by version; old indexes keep working.

### 13. Migrations on transactional schemas are additive forever.

The opposite of #11, for OLTP. `ADD COLUMN`, `CREATE TABLE`, `CREATE INDEX`
only. No `DROP`. A column marked deprecated for ≥ 6 months can be dropped
with a commit linking the deprecation. Enforced in CI.

- `knievel/RELEASE_CHECKLIST.md:51-55`, gated by
  `cargo xtask lint-migrations` at `ci.yml:136`.

### 14. Tenancy enforced at three layers, with a CI assertion.

Postgres RLS, query-layer re-check, and a manifest gate that asserts every
endpoint has a cross-tenant test. One layer of tenancy enforcement is one
bug away from a leak.

- `knievel/ARCHITECTURE.md:230-235`, with `xtask check-cross-tenant` at
  `ci.yml:137`.

### 15. Make staleness explicit. Make lossiness named.

A read snapshot that's seconds stale serves decisions; a fake `/health` that
hides a degraded writer doesn't. If a path is intentionally lossy, it has a
counter with a name.

- `knievel/ARCHITECTURE.md:294-301` — 5 s staleness SLO; `events.dropped`
  counter for the lossy-by-design events channel.
- `cheminee/charts/cheminee/templates/deployment.yaml:61-68` — liveness
  points at `/api/v1/openapi.json` with `# TODO: We need a low-cost health
  endpoint`. **An honest TODO in a manifest beats a fake `/health`.**

## The Code-Layout Rules

### 16. Workspace crates move in lockstep.

If `-sys` and the high-level crate are in one workspace, they release
together. FFI version skew is a footgun; remove the gun.

- `rdkit/README.md:24-35` mandates `cargo workspaces version patch`;
  `rdkit/Cargo.toml:19` pins `rdkit-sys = { path = "rdkit-sys", version =
  "0.4.9" }`.

### 17. Enforce file-pairing conventions in `build.rs`.

If your FFI requires a `.rs` bridge to be paired with a `.cc` impl and a `.h`
header, a missing pair should panic the build, not silently ignore the orphan.

- `rdkit/rdkit-sys/build.rs:80-103` walks `src/bridge/*.rs` and panics if
  `wrapper/src/<name>.cc` or `wrapper/include/<name>.h` is missing.

## The Workflow Rules

### 18. One workflow per release event, not per artifact.

Splitting "publish image" and "publish gem" into separate workflows feels
modular and multiplies the trigger surface. Keep release jobs in one
workflow, fanned out by `needs:` only when there's a real dependency.

- `knievel/ARCHITECTURE.md:378-382` calls this out explicitly.

### 19. Release workflows must be re-run-safe.

Image push is idempotent by digest. Gem publish refuses to overwrite. A
half-finished release is the most expensive kind, so plan to re-run from any
step.

- `knievel/RELEASE_PLAYBOOK.md:118-134`; `release.yml:7-12` sets
  `cancel-in-progress: false`; `release.yml:429-432` refuses to re-publish a
  taken gem version.

## The Dependency Rules

### 20. New deps enter at their latest stable — verified upstream, not from memory.

- **Anti-receipt:** `corti` PR #37 pinned `sccache 0.10.0`; mozilla/sccache was already at `0.15.0` (2026-04-29).
- **Exception:** pin behind latest only with a written reason + link.

## The Workstation Rules

Receipts here include the workstation itself, not just repos — these laws were
bought with a disk-full incident and probe builds, both dated.

### 21. One global rustc-wrapper. Commit it into a repo only paired with CI that installs sccache.

`~/.cargo/config.toml` setting `[build] rustc-wrapper = "sccache"` covers every
repo and every worktree on the machine — one line, zero per-repo config. But
cargo hard-errors when the wrapper binary is missing, so committing the wrapper
into a repo's `.cargo/config.toml` makes sccache *mandatory* for every fresh
clone and every CI runner. That's only legal when the repo's CI installs
sccache itself.

- `~/.cargo/config.toml:6-7` — the global wrapper; verified 2026-06-09 that no
  repo under `~/code` overrides `rustc-wrapper` (knievel's `.cargo/config.toml`
  is just an `[alias]` section), so this one line is the whole local story.
- `corti/.cargo/config.toml:14` commits the wrapper deliberately — paired with
  `corti/.github/actions/rust-setup/action.yml:43-46` installing sccache
  v0.15.0 via pinned `mozilla-actions/sccache-action` (LAWS §8).
- vagus takes the other lawful branch: no committed wrapper, global wrapper
  locally, `Swatinem/rust-cache` in CI
  (`vagus/.github/actions/rust-setup/action.yml:36`). Both shapes are fine;
  committed-wrapper-without-CI-install is the only broken one.

### 22. sccache caches your dependencies, not your crates. "non-cacheable: incremental" is healthy.

Workspace-member crates compile incrementally under the dev profile, and
sccache cannot cache incremental compiles — so `sccache --show-stats` showing
your own crates as "non-cacheable, reason: incremental" is the system working,
not broken. Don't "fix" it with `CARGO_INCREMENTAL=0` locally: every `CARGO_*`
env var is hashed into the sccache key, so setting it inconsistently splits the
cache namespace and causes spurious *dependency* misses — and it buys nothing
anyway, because workspace-crate keys embed the checkout path (`-C metadata` /
`--out-dir`), so they never hit across worktrees. Judge sccache by the only
number that matters: `sccache --zero-stats`, then the first build in a fresh
worktree with the same `Cargo.lock` should show ~100% hits on registry deps.

- Probe-verified on this workstation, 2026-06-09: fresh dir + same `Cargo.lock`
  = 100% dep cache hits; `CARGO_INCREMENTAL=0` probe = zero new cross-worktree
  hits on workspace crates (path-bound keys).
- Never cacheable regardless: proc-macros, build-script binaries, any linked
  crate-type, and the link step itself. Budget your expectations accordingly.
- CI is the exception that proves the env-var rule:
  `corti/.github/actions/rust-setup/action.yml:58` sets `CARGO_INCREMENTAL=0`
  — correct *there*, because every run is a fresh checkout at one path and
  sccache silently bypasses incremental builds otherwise. The law is about
  your laptop.

### 23. An abandoned worktree hoards its target/ forever. Remove worktrees when the branch lands.

`target/` is per-checkout, gitignored, and invisible from the main repo —
nothing ever GCs it. The drill when a branch lands: push anything unpushed,
then `git worktree remove <path>` + `git worktree prune`. Never bare `rm -rf`
a worktree directory — it strands the admin entry in `.git/worktrees/`.

- **Anti-receipt:** 43.6G across four stale `.claude/worktrees/` in claria +
  cousteau (22G, 10G, 7G, 3.8G of `target/`), found 2026-06-09 during a
  disk-full incident — one of them sitting on 3 unpushed commits the whole
  time.

### 30. sccache aggressively on every Rust project. Never share `main`'s `target/`.

Many worktrees each cold-compiling the same dependency graph burns CPU and
disk for nothing. The first fix is sccache (§21). The fix is *not* pointing
every worktree at one `CARGO_TARGET_DIR`: cargo takes an exclusive lock on the
target directory, so a dev server in one worktree and a test run in another
serialize behind `Blocking waiting for file lock on build directory`. sccache
buys compiler reuse without the Cargo lock. Say the cost out loud: `target/`
stays per-worktree and stays large. sccache stops you *recompiling*; it does not
stop you *storing*. Physical deduplication is a separate requirement (§32).

- **Receipt**, claria rollout on this workstation, 2026-07-26: fresh worktree,
  cold cache, 138s. Fresh worktree, warm cache, quiet machine, 55s at ~98% hit
  rate.
- **Methodology, and it's a trap:** sccache stats are global across every client
  on the machine, so a concurrent build in an unrelated project lands inside
  your delta. The contended runs measured that day were discarded, not averaged
  in. `--zero-stats`, one build, read stats — on a quiet machine or not at all.
- 2.5G of cache after a full build + test + clippy matrix against the original
  32 GiB cap. By 2026-08-18 the cache had reached all 32 GiB while worktree
  targets stayed full-sized. A later build wave drove the disk to 115 MiB free
  even after a first reduction to 16 GiB; the emergency cap is now 8 GiB. A
  ceiling is not a reservation, but it absolutely belongs in the disk budget.
- **Finding that contradicted the assumption going in:** `cc-rs` picks up the
  rustc-wrapper on its own — 823 `c [clang]` hits — so C/C++ in native deps is
  cached without wrapping `cc` separately.
- The non-cacheable ceiling is proc-macros: `serde_derive`, `specta-macros`,
  `tokio-macros`, `zerocopy-derive` refused with reason `crate-type`, 490 of 622
  non-cacheable calls. That's §22 working, not a miss to chase.

### 31. Worktrees are aggressive, branch-per-agent, and siblings of the main checkout.

If the main checkout is `~/code/org/foo` (origin
`https://github.com/org/foo`), then branch `perf/make-faster` lives at
`~/code/org/foo-perf-make-faster`. Flat, sibling, named for the branch. One
flavor of worktree, no nesting schemes, no per-tool directory.

The naming is the small half. The law is that worktrees must be **in the
developer's face**. `ls ~/code/org` is the dashboard: a sibling list that keeps
growing is a signal that code is not landing in `main` fast enough and branches
are going stale. A hidden `.claude/worktrees/` deletes that signal, and what you
can't see you don't reap (§23).

**Tooling consequence:** Claude Code's built-in agent worktree isolation creates
worktrees under `.claude/worktrees/` and therefore violates this law. Honoring
it means agents create worktrees explicitly —
`git worktree add ../foo-perf-make-faster -b perf/make-faster` — rather than
relying on the built-in.

- **Anti-receipt, the second time:** §23's incident recurred seven weeks later.
  2026-07-26, ~47GB across five stale `.claude/worktrees/` in claria alone (15G,
  14G, 13G, 5.4G, plus one already cleaned), disk at 94% with 26 GiB free, every
  one of them on a branch already merged to `main`. Same-day cleanup reclaimed
  the ~47GB. A law broken twice in seven weeks by the same hidden directory is
  the argument for the sibling convention.
- **Corollary:** `cargo clean` before switching worktrees is a disk-management
  reflex, not hygiene. Each worktree owns its `target/` and cargo's
  fingerprinting handles staleness — cleaning throws away work you then rebuild.
  Reap whole worktrees; don't clean live ones.

### 32. Share bytes, not Cargo lock domains.

True concurrent builds require a private `target/` per worktree. Efficient
concurrent builds require those private files to share physical storage
underneath Cargo. A content-addressed store materialized through copy-on-write
reflinks gives each target a separate inode and lock domain while APFS stores
unchanged extents once. Logical isolation and physical sharing are compatible;
a shared `CARGO_TARGET_DIR` is not required.

- **Receipt, isolated `kache 0.14.2` probe, 2026-08-18:** two divergent
  worktree roots built concurrently with no Cargo build-directory wait. Of 56
  cacheable cold requests, 28 compiled and the peer restored 28; roughly 210
  MiB across two logical targets was cache-backed CoW data against a 98 MiB
  content-addressed store. Rebuilding both from deleted targets took 9–10 s,
  with 100% zero-copy restores.
- **Counter-receipt, post-hoc dedupe:** `fclones` found only 2.2 GB of exact
  duplicate files among 23.7 GB of ≥1 MiB files in three existing Dekopon
  targets. Reflinking after the fact helps, but it pays the disk peak first and
  needs a build-free maintenance window.
- **The tool is not yet the law:** kache remains an opt-in pilot while its
  hidden-input correctness boundary is audited (notably
  `kunobi-ninja/kache#760`) and large-crate incremental edit loops are measured.
  The durable rule is separate locks plus shared immutable bytes. See
  `RUST_WORKTREES.md` for the rollout gates and Cargo's native fine-grained
  locking roadmap.

## The GitOps Rules

### 24. Kubernetes core services should use selfHeal.

ArgoCD's `automated` sync without `selfHeal` only re-applies on new commits.
A resource deleted or mutated live stays that way until the next push — for a
quiet infra app, that can be months. Controllers, operators, networking,
cert-manager resources, observability: `automated: {prune: true, selfHeal:
true}`. Business apps may omit selfHeal deliberately so manual debugging
tweaks aren't reverted within seconds; that omission is a choice to write
down, not a default to inherit.

- **Receipt:** scientist-hq k3, 2026-06-09. The ARC webhook's cert-manager
  `Certificate`/`Issuer` were drift-deleted (origin unknown); the Secret
  stayed behind so nothing looked wrong; the cert silently aged past its
  May 10 renewal and expired June 9 — GHA couldn't start workers for 80
  minutes. The app's last commit was Nov 11. Fixed in
  `k3-applications@553385e`.

### 25. Apps that install CRDs use ServerSideApply — and must be able to reach Synced.

Client-side apply fails on large CRDs (`metadata.annotations: Too long: may
not be more than 262144 bytes`). Use SSA for any CRD-installing app, and for
truly huge CRDs the split pattern: a dedicated `<app>-crds` Application plus
`helm.skipCrds` on the main app. SSA alone may still diff forever on
apiserver-normalized fields (`preserveUnknownFields` pruned on write,
`conversion.strategy` defaulted) — pair it with ServerSideDiff or
`ignoreDifferences`. The second half is the law's point: an app that can't
reach Synced becomes wallpaper, and wallpaper hides real drift.

- **Receipt:** the same outage. The ARC app had been OutOfSync/Failed on its
  5 CRDs since at least November; the permanently red app masked the
  Certificate drift that caused the incident. `k3-applications@b92954b..4ad839f`
  (crds app, ignoreDifferences, skipCrds) got it to Synced for the first
  time since Nov 2025.

### 26. Inline `values: |` in the ApplicationSet, not a per-app values file.

A standalone per-application values file is one more file to find, diff, and
keep in sync with the generator that consumes it. Keep the overrides where the
Application is declared: an inline `values: |` block in the ApplicationSet
template. Don't add new per-app values files to a GitOps values repo; the
direction of travel is to migrate the existing ones *into* ApplicationSet
literals. The file is the thing to avoid — not the chart, and not overrides
themselves.

### 27. A Helm chart may live in the values repo.

The override-file rule (§26) is about *values files*, not charts. When the
GitOps/values repo is the most sensible home for a chart — it's bespoke to this
deployment, or co-evolves with the ApplicationSet that renders it — keep the
chart there. Co-locating the chart with the Application that uses it is fine;
only the standalone per-app values file is the smell.

### 28. An inline override carries only real overrides. Never restate a default.

A `values: |` block that copies a chart's `values.yaml` default verbatim adds
zero information and silently pins you to today's default — the next chart bump
that moves it sails past you. Include only the keys whose value meaningfully
differs from the chart's `values.yaml`. If the line matches the default,
delete it.

### 29. Mirror the chart's `values.yaml` key order in the override.

A reader diffing your override against the chart should scan top-to-bottom
once, not jump around. If `foo:` precedes `bar:` in the chart's `values.yaml`,
`foo:` precedes `bar:` in your override block. Override order is a function of
the chart, not of when you happened to add each key.

---

## Caveats

- **Law 1 isn't strict.** `knievel/release.yml:54` uses qemu+buildx and
  `cross` for Linux musl. Native is the goal; emulation is the budget
  fallback for arm64 Linux until pricing changes.
- **Law 2 isn't strict.** The knievel server image compiles in Docker; the
  rdkit-debian `.deb` builds in Docker. Both are deliberate. The
  refinement (build shape follows distribution shape; pinned-toolchain
  containers OK for system deps) is part of the law, not an evasion of it.
- **Dependencies in `Cargo.toml` should be wired into the binary or
  removed.** `cheminee/Cargo.toml:19,21` pulls in `prometheus` and the
  `poem` `prometheus` feature, but no `/metrics` route is wired
  (`grep` confirms). Listed-but-unwired is dead weight; either ship the
  endpoint or drop the dep.
