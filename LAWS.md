# Laws of Software

Opinionated rules with receipts from `rdkit-rs/rdkit`,
`rdkit-rs/rdkit-debian`, `rdkit-rs/cheminee`, `knievel-ads/knievel`,
`vasovagal/corti`, and this workstation. Named exceptions refine the rule;
they do not silently waive it.

## The Build Rules

### 1. Build natively per arch. Stitch with a manifest.

Native runners beat emulation on speed, debugging, and cache hits. Build on an
architecture matrix, then fan in to a small `docker manifest create` job.

- **Receipts:** `cheminee/.github/workflows/build_docker_images.yml:14-20,118-143`
  uses native x86_64/arm runners and a 2-vCPU manifest job;
  `rdkit-debian/.github/workflows/build.yml:57-64` does the same on
  GitHub-hosted runners.
- **Budget exception:** `knievel/.github/workflows/release.yml:54-89` uses
  QEMU/buildx and `cross` for Linux musl because hosted Linux arm64 is not worth
  the spend. Write down such emulation decisions.

### 2. Don't compile your app inside Docker.

Build apps on the host, where Cargo/sccache/debuggers turn observed ~90-second
buildx loops into ~2-second rebuilds; Docker should package the result.

- **Receipts:** `cheminee/Dockerfile:43-45` copies `target/release/cheminee`
  after runner+sccache compilation
  (`cheminee/.github/workflows/build_docker_images.yml:82-83`).
  `knievel/Dockerfile:67-70` keeps Node compilation outside so pnpm's native
  cache works and the image needs no Node toolchain.
- **Distribution exception:** a container-only artifact may pay the Docker
  compile cost once at release. Knievel's server does
  (`knievel/Dockerfile:22-56`), while its standalone CLIs build natively
  (`knievel/.github/workflows/release.yml:108-151`). Build shape follows
  distribution shape.
- **Toolchain exception:** a pinned container may build a one-shot, cached
  system library. RDKit C++ becomes an S3-cached `.deb` this way
  (`rdkit-debian/.github/workflows/build.yml:65`,
  `rdkit-debian/Dockerfile`).

### 3. A tag is a vote of confidence. Don't re-run CI on it.

A tag cut from branch-protected, green `main` needs only tag-specific work:
build, sign, publish, attest. Re-running the PR matrix adds ~25 minutes, not
signal.

- **Receipts:** `knievel/.github/workflows/release.yml:14-23` states this
  contract; `cheminee/.github/workflows/build_docker_images.yml:1-4` and
  `cheminee/.github/workflows/generate_ruby_gem.yaml:1-3` are tag-only;
  `cheminee/.github/workflows/test_suite.yml:2` is PR-only.
- Tag jobs are parallel siblings unless a real dependency exists: Cheminee
  builds its image and gem concurrently from the same tag.

## The Release & Artifact Rules

### 4. Pin by digest, not by floating tag.

OCI tags move; digests do not. Consumers pin digests, and changed bits get a new
patch release (`knievel/RELEASE_PLAYBOOK.md:71-83,99-100`).

### 5. Cache big upstreams in S3, not in your build system.

Ephemeral runner/layer caches evict. Compile expensive upstreams once: RDKit
costs ~30 minutes. `rdkit-debian/.github/workflows/build.yml:117` uploads it to
`s3://rdkit-rs-debian/`; `rdkit/.github/workflows/test_suite.yml:41-46` and
`cheminee/Dockerfile:11-21` download the prebuilt tarballs.

### 6. Disable build-time downloads in vendored C++ deps.

Configure-time GitHub fetches break reproducible/offline builds. Disable those
features rather than patching them (`rdkit-debian/build.sh:38-43` disables
CoordGen, MaeParser, and FreeSASA downloads).

### 7. The version of the upstream lives in the tag.

A tag should identify the upstream without a lockfile. `rdkit-debian` uses
`Release_YYYY_MM_P+BUILD_NUMBER`
(`rdkit-debian/.github/workflows/build.yml:31-43`): upstream version plus
packaging revision.

### 8. `sccache`/`rust-cache` everywhere, identically configured.

Pin action SHAs and centralize setup; drift creates opaque misses. The same
`mozilla/sccache-action@eaed7fb9…` appears in
`rdkit/.github/workflows/test_suite.yml:23-30` and
`cheminee/.github/workflows/test_suite.yml:20-27`;
`knievel/.github/actions/rust-setup/action.yml` centralizes
`Swatinem/rust-cache`.

### 33. Publish crates from CI over OIDC. Stored registry tokens are bootstrap credentials, not operating credentials.

crates.io Trusted Publishing exchanges a GitHub OIDC JWT for a crate-scoped,
30-minute token; `rust-lang/crates-io-auth-action` revokes it in its post step.
Stored API tokens can also be scoped and expired, but remain reusable bearer
credentials requiring distribution, rotation, and revocation. Use OIDC for
normal publishing.

`id-token: write` is job-wide: every action or command in that job can request
a JWT for the same workflow identity. Therefore:

- grant it only to a minimal publish job; use only `contents: read` if checkout
  is required;
- SHA-pin every direct `uses:` and every transitive `uses:` inside composites;
- build, test, and run `cargo publish --dry-run` in an unprivileged job first;
- bind a protected GitHub Environment when reviewer/ref gates are available and
  register the same environment at crates.io; and
- expose the temporary token only to the publish step; never persist or log it.

The crates.io settings form fronts a JSON API:

```text
POST https://crates.io/api/v1/trusted_publishing/github_configs
Authorization: <short-lived token scoped to trusted-publishing + these crates>
{"github_config":{"crate":"claria-core","repository_owner":"claria-ai",
 "repository_name":"claria","workflow_filename":"publish.yml","environment":"release"}}
```

For workspaces, derive packages from `cargo metadata`: `publish` is `null`
(unrestricted), `[]` (disabled), or a registry list. `cargo publish --workspace`
orders dependencies and waits for each crate to enter the index. The GitHub
binding covers owner identity, repo, workflow **filename**, and optional
environment—not branch/tag—so filename/environment changes require
re-registration.

Current crates.io requires an existing crate before storing this binding. The
live API returned post-auth `404 crate … does not exist` for all twelve Claria
0.32.0 crates on 2026-08-18. Bootstrap once with an expiring `publish-new`
token, register with a `trusted-publishing` token, then revoke both.

- **Source receipt:** crates.io creates a 30-minute token;
  `crates-io-auth-action@c6f97d42` (v1.0.5's verified commit) exchanges and
  revokes it.
- **Near-miss:** `claria#135` / `a3d2299` derives and registers twelve crates,
  but its OIDC job reaches floating actions directly and through `rust-setup`.
  Pin or move them before merge.

## The Service & API Rules

### 9. The OpenAPI spec is the contract. Server and clients derive from it.

Handwritten clients drift. Generate the spec from handler annotations and fail
CI when the checked-in copy differs.

- `cheminee/src/rest_api/api/api_v1.rs:24-37` derives it with `#[OpenApi]` and
  `#[oai(...)]`.
- `knievel/.github/workflows/ci.yml:162-169` runs
  `cargo xtask openapi --check`.

### 10. Generated clients live in their own repo. Upstream commits, downstream publishes. Same tag.

The server owns the spec and, on a tag, commits generated clients with that tag
to client repos. Each client repo builds and publishes itself. This separates
API source, generated artifact, and registry credentials while keeping bug
versions directly searchable.

- `cheminee/.github/workflows/generate_ruby_gem.yaml:65-83` generates and
  pushes to `cheminee-ruby`; that repo runs `rake release`.
- `knievel/.github/workflows/release.yml:299-315,362-369` generates from
  `openapi.yaml` and pushes to its client repo for publication.

### 11. One binary, many subcommands.

Ship server, bulk, and ops commands in one image so production has the exact
ops code it needs, not a drifting tools container. `cheminee/src/main.rs:15-32`
defines the `clap` commands; its deployment runs `rest-api-server`, while the
same image can `kubectl exec … index-sdf`
(`cheminee/charts/cheminee/templates/deployment.yaml:41-44`).

### 12. Schema versions are values in a registry, not migrations.

When historical shapes coexist (`descriptor_v1`, `descriptor_v2`, …), add a
version key instead of rewriting history. `cheminee/src/schema/mod.rs:10` keeps
a version-keyed `HashMap<&'static str, Schema>` so old indexes remain valid.

### 13. Migrations on transactional schemas are additive forever.

For OLTP—the opposite of §12—allow `ADD COLUMN`, `CREATE TABLE`, and
`CREATE INDEX`; no `DROP` until a ≥6-month deprecation linked by the removal
commit. Knievel documents this at `knievel/RELEASE_CHECKLIST.md:51-55` and
enforces it with `cargo xtask lint-migrations`
(`knievel/.github/workflows/ci.yml:136`).

### 14. Tenancy enforced at three layers, with a CI assertion.

Use Postgres RLS, a query-layer re-check, and a CI manifest gate requiring a
cross-tenant test for every endpoint (`knievel/ARCHITECTURE.md:230-235`,
`xtask check-cross-tenant` at `knievel/.github/workflows/ci.yml:137`). One layer
is one bug from a leak.

### 15. Make staleness explicit. Make lossiness named.

State stale-read bounds; name and count intentional loss. Knievel declares a
5-second staleness SLO and `events.dropped` counter
(`knievel/ARCHITECTURE.md:294-301`). Cheminee honestly marks its OpenAPI
liveness probe as a TODO instead of inventing `/health`
(`cheminee/charts/cheminee/templates/deployment.yaml:61-68`).

## The Code-Layout Rules

### 16. Workspace crates move in lockstep.

Release colocated FFI layers together; version skew is a footgun.
`rdkit/README.md:24-35` mandates `cargo workspaces version patch`, and
`rdkit/Cargo.toml:19` pairs the path dependency with version `0.4.9`.

### 17. Enforce file-pairing conventions in `build.rs`.

Missing FFI bridge/implementation/header peers should fail the build, not be
ignored. `rdkit/rdkit-sys/build.rs:80-103` walks each `src/bridge/*.rs` and
requires matching `wrapper/src/<name>.cc` and `wrapper/include/<name>.h`.

## The Workflow Rules

### 18. One workflow per release event, not per artifact.

Separate artifact workflows multiply trigger surfaces. Keep release jobs in one
workflow and use `needs:` only for real dependencies
(`knievel/ARCHITECTURE.md:378-382`).

### 19. Release workflows must be re-run-safe.

Plan recovery from every step: digest pushes are idempotent; registry publishes
may not be. `knievel/RELEASE_PLAYBOOK.md:118-134`,
`knievel/.github/workflows/release.yml:7-12` disables cancellation, and
`knievel/.github/workflows/release.yml:429-432` refuses an existing gem version.

## The Dependency Rules

### 20. New deps enter at their latest stable — verified upstream, not from memory.

- **Anti-receipt:** Corti PR #37 chose sccache 0.10.0 when 0.15.0 was current
  (2026-04-29).
- Pin older only with a written reason and link.

## The Workstation Rules

These receipts include the workstation and its disk-full/probe incidents.

### 21. One global rustc-wrapper. Commit it into a repo only paired with CI that installs sccache.

`~/.cargo/config.toml:6-7` can cover every local repo/worktree. A committed
wrapper makes its binary mandatory in every clone and CI runner, so the repo's
CI must install it.

- **Receipts:** the global config covers `~/code` with no repo override
  (verified 2026-06-09). Corti deliberately commits one at
  `corti/.cargo/config.toml:14` and installs sccache v0.15.0 via a pinned action
  (`corti/.github/actions/rust-setup/action.yml:43-46`); Vagus commits none and
  uses `Swatinem/rust-cache` in CI
  (`vagus/.github/actions/rust-setup/action.yml:36`). Both are lawful;
  committed-wrapper-without-install is not.

### 22. sccache caches your dependencies, not your crates. "non-cacheable: incremental" is healthy.

Local workspace crates are incremental, which sccache cannot cache;
`non-cacheable: incremental` is healthy. Do not set `CARGO_INCREMENTAL=0`
locally: inconsistent `CARGO_*` values split cache keys, and path-bound
workspace keys still cannot hit across worktrees. Measure what matters with
`--zero-stats`: a fresh worktree sharing `Cargo.lock` should approach 100% hits
on registry dependencies.

- **Probe, 2026-06-09:** same lockfile gave 100% dependency hits;
  `CARGO_INCREMENTAL=0` added no workspace cross-worktree hits.
- Proc macros, build-script binaries, linked crate types, and linking itself are
  never cacheable.
- **CI exception:** fresh, stable-path CI checkouts should disable incremental;
  Corti does at `corti/.github/actions/rust-setup/action.yml:58`.

### 23. An abandoned worktree hoards its target/ forever. Remove worktrees when the branch lands.

A worktree's gitignored `target/` has no GC. After pushing anything unpushed,
run `git worktree remove <path>` and `git worktree prune`; bare `rm -rf` leaves
stale `.git/worktrees/` administration.

- **Anti-receipt, 2026-06-09:** four stale hidden Claria/Cousteau worktrees held
  43.6 GiB (22/10/7/3.8), including one with three unpushed commits.

### 30. sccache aggressively on every Rust project. Never share `main`'s `target/`.

Each worktree needs its own `target/`; a shared `CARGO_TARGET_DIR` takes a coarse
Cargo lock and serializes agents. sccache reuses compilation without that lock,
but each target still stores restored files. Physical deduplication is §32.

- **Claria receipt, 2026-07-26:** fresh worktree: 138 s cold, 55 s warm at ~98%
  hits. Because stats are machine-global, measure with `--zero-stats` and one
  build on a quiet machine; discard contended deltas.
- The cache grew from 2.5 GiB after one build/test/clippy matrix to its 32 GiB
  cap by 2026-08-18. A 16 GiB cap still preceded a 115 MiB-free incident; the
  emergency cap is 8 GiB. Include the ceiling in disk budgets.
- `cc-rs` inherited the wrapper automatically (823 Clang hits); do not wrap
  `cc` separately.
- Proc macros dominated non-cacheable calls (490/622, `crate-type`), as §22
  predicts.

### 31. Worktrees are aggressive, branch-per-agent, and siblings of the main checkout.

For `~/code/org/foo`, branch `perf/make-faster` lives at
`~/code/org/foo-perf-make-faster`: flat, sibling, branch-named. `ls ~/code/org`
is the dashboard. Claude Code's built-in isolation creates hidden
`.claude/worktrees/`, concealing stale branches and violating this law. Create
explicitly:

```bash
git worktree add ../foo-perf-make-faster -b perf/make-faster
```

- **Repeat anti-receipt, 2026-07-26:** at 94% disk use (26 GiB free), five
  hidden, merged Claria worktrees held ~47 GiB (15/14/13/5.4 GiB plus one
  cleaned) seven weeks after §23's incident; removing them restored it.
- `cargo clean` is not worktree hygiene: reap landed worktrees, not live targets.

### 32. Share bytes, not Cargo lock domains.

Keep a private `target/` per worktree, but materialize immutable
content-addressed artifacts through APFS copy-on-write reflinks. Separate inodes
preserve locks/mutation; shared extents avoid N physical copies.

- **kache 0.14.2 probe, 2026-08-18:** two divergent roots built concurrently
  without a Cargo lock wait; of 56 cacheable requests, 28 compiled and the peer
  restored 28. About 210 MiB of two targets shared a 98 MiB store; rebuilding
  deleted targets took
  9–10 s with 100% zero-copy restores.
- **fclones counter-receipt:** only 2.2 GiB of exact duplicates among 23.7 GiB
  of large files in three Dekopon targets; post-hoc dedupe also requires idle
  builds and pays the disk peak first.
- kache remains a pilot pending hidden-input correctness
  (`kunobi-ninja/kache#760`) and large-crate incremental testing. The
  architecture—not the tool—is law; see
  `RUST_WORKTREES.md`.

## The GitOps Rules

### 24. Kubernetes core services should use selfHeal.

Without ArgoCD `selfHeal`, live drift persists until a new commit. Set
`automated: {prune: true, selfHeal: true}` for core controllers, networking,
certs, and observability. A business app may omit it for deliberate live
debugging, but must document that choice.

- **Receipt, scientist-hq k3, 2026-06-09:** drift-deleted ARC
  `Certificate`/`Issuer` resources went unnoticed behind a retained Secret;
  renewal failed, the cert expired, and GHA lost workers for 80 minutes while
  the app had seen no commit since Nov 11. Fixed in `k3-applications@553385e`.

### 25. Apps that install CRDs use ServerSideApply — and must be able to reach Synced.

Client-side apply can exceed the 262144-byte annotation limit. Use SSA; for
huge CRDs split a `<app>-crds` Application and set `helm.skipCrds` on the main
app. If API normalization (for example pruned `preserveUnknownFields` or a
defaulted `conversion.strategy`) causes permanent diffs, add ServerSideDiff or
precise `ignoreDifferences`. Permanently red apps hide real drift.

- **Receipt:** ARC had been OutOfSync/Failed on five CRDs since November,
  masking the certificate drift in §24. `k3-applications@b92954b..4ad839f`
  split/ignored/skipped CRDs and made it Synced for the first time since Nov 2025.

### 26. Inline `values: |` in the ApplicationSet, not a per-app values file.

Keep real overrides in the generating ApplicationSet's `values: |` block.
Migrate existing standalone per-app values files there; the file—not charts or
overrides—is the smell.

### 27. A Helm chart may live in the values repo.

§26 forbids standalone per-app values files, not charts. Co-locate a bespoke or
co-evolving chart with its ApplicationSet when that is its natural home.

### 28. An inline override carries only real overrides. Never restate a default.

Restating a default adds no information and silently pins today's value against
future chart changes. Delete any override equal to `values.yaml`.

### 29. Mirror the chart's `values.yaml` key order in the override.

Mirror the chart's key order so comparison is one top-to-bottom scan; order by
the chart, not insertion history.

---

## Caveats

- `cheminee/Cargo.toml:19,21` includes `prometheus` and Poem's `prometheus`
  feature but exposes no `/metrics` route. Wire listed dependencies into the
  binary or remove them.
