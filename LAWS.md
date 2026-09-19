# Laws of Software

Opinionated rules with receipts from `rdkit-rs/rdkit`,
`rdkit-rs/rdkit-debian`, `rdkit-rs/cheminee`, `knievel-ads/knievel`,
`vasovagal/corti`, `dekopon-agents/dekopon`, and this workstation. Named exceptions refine the rule;
they do not silently waive it.

## The Build Rules

### 1. Build natively per arch. Stitch with a manifest.

Native runners beat emulation on speed, debugging, and cache hits. Build on an
architecture matrix, then fan in to a small `docker manifest create` job.

- **Receipts:** `cheminee/.github/workflows/build_docker_images.yml:14-20,118-143`
  uses native x86_64/arm runners and a 2-vCPU manifest job;
  `rdkit-debian/.github/workflows/build.yml:57-64` does the same on
  GitHub-hosted runners.

### 2. Don't compile your app inside Docker.

Compile on the host, where native compiler/package caches and debuggers keep the
inner loop fast and understandable; Docker only packages the finished artifact.
Containerized compilation makes cache behavior and failures harder to inspect.
Observed buildx loops fell from ~90 seconds to ~2-second host rebuilds.

- `cheminee/Dockerfile:43-45` copies a runner-built `target/release/cheminee`.
- `knievel/Dockerfile:67-70` likewise keeps Node compilation outside so pnpm's
  native cache works and the image carries no Node toolchain.

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

### 5. CI builds always use a cache. Fast feedback preserves momentum.

Cache setup is always worth the upfront investment. Cache compiler outputs,
dependencies, package-manager stores, and expensive upstream artifacts from the
first workflow; centralize setup so jobs share keys and behavior.

- `rdkit-debian/.github/workflows/build.yml:117` promotes its ~30-minute RDKit
  build to S3; downstream jobs download it instead of rebuilding.
- The same pinned `mozilla/sccache-action@eaed7fb9…` serves RDKit and Cheminee;
  `knievel/.github/actions/rust-setup/action.yml` centralizes Rust caches.

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

### 9. Use poem-openapi: the implementation generates the contract.

For Rust HTTP APIs, use `poem-openapi` every time. Handler types and annotations
are the source of truth; the OpenAPI document is generated from them. Do not use
tooling that makes code and a handwritten spec compete, because they will
drift. If the generated document is checked in, CI must reject regeneration
diffs.

- `cheminee/src/rest_api/api/api_v1.rs:24-37` derives the API with `#[OpenApi]`
  and `#[oai(...)]`.
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

## The Code & API Design Rules

These rules generalize Dekopon's contribution and review conventions. The
[source snapshot](https://github.com/dekopon-agents/dekopon/blob/4c91530f60ddb5113040ce78f29fd137e11b3f87/CONTRIBUTING.md#review-checklist)
is a policy receipt, not a claim that every implementation already complies.

### 34. Preserve error causes; report each failure once.

Return an error that names the failed operation and preserves its cause, or
record the cause at the point where the error is deliberately discarded.
Silent `map_err(|_| …)`, `let _ = fallible()`, and multi-cause checks collapsed
into a bool lose the evidence needed to debug. Avoid logging the same failure
at every propagation layer; choose the reporting boundary. Preserve diagnostic
meaning without exposing credentials or sensitive payloads.

- **Policy receipt:** Dekopon's review checklist requires cause kind or errno
  at discard sites and one report per refusal or failure cause.

### 35. Classify errors by the decision callers must make.

Model retryable versus permanent failures and executed versus not-executed
outcomes where callers need those distinctions. Preserve an unknown outcome
when an external effect may have happened; a timeout is not proof it did not.
Never label permanent exhaustion transient or exit successfully with essential
daemon work dead.

- **Policy receipt:** Dekopon's review checklist classifies errors along
  caller-action axes and rejects completed work being reported as timed out.

### 36. Report all validation conflicts together.

For authored configuration, collect independent conflicts and return them in
one diagnostic pass. Never silently use last-wins duplicate keys. A malformed
structure or unsafe dependency can prevent further checks; stop those checks
rather than inventing secondary errors. Keep diagnostic work and output bounded.

- **Policy receipt:** Dekopon's change guidelines require validation tests with
  at least two simultaneous conflicts and assertions that both are reported.

### 37. Bound everything that grows or blocks; give it an owner.

Set limits for retained state and peer-controlled allocations. Enforce claimed
lengths rather than trusting them when preallocating. Give threads, connections,
and network reads an explicit lifecycle, deadlines where they can stall, and
an observer for failure or exit. State retained across turns needs eviction or
deduplication; deduplication alone does not bound unique entries.

- **Policy receipt:** Dekopon's review checklist requires bounded growth,
  ownership, deadlines, and exit observers.

### 38. Construct expensive reusable resources once, not per request.

Reuse HTTP/model clients, Wasmtime engines, linkers, compiled components, and
workers at the process or session scope that owns them. Reuse must respect
credential, tenant, concurrency, and lifecycle boundaries; do not turn
request-specific mutable state into a global singleton.

- **Policy receipt:** Dekopon's review checklist names these resources and
  rejects constructing them per request or invocation.

### 39. New public surface needs a real consumer now.

A new public item, dependency, config field, or error variant needs a non-test
consumer in the same change. Otherwise keep it private or delete it: parsed but
unread configuration and unreachable variants are not useful scaffolding.
For a library whose consumers ship separately, an explicit supported external
use case and contract tests are the named exception; speculative extensibility
is not.

- **Policy receipt:** Dekopon's review checklist requires same-PR non-test
  consumers; the external-library exception generalizes that application rule.

### 40. Keep one definition per fact; test unavoidable mirrors.

Share the authoritative definition rather than maintaining a second validator
or constant by hand. When a packaging or trust boundary requires a mirror,
carry an equality-pinning or conformance test. A mirror must not accept what
the authority rejects. Sharing a definition is not permission to collapse
otherwise independent security boundaries.

- **Policy receipt:** Dekopon's review checklist requires shared definitions
  or equality-pinning tests for mirrors of an authority.

### 41. Tests pin behavior and failure causes, not implementation details.

Name tests for the behavior they guarantee and keep them beside the owning
code. Exercise failure paths and assert that the surfaced error or diagnostic
retains the cause, rather than merely asserting failure. Pin stable CLI output
where it is a contract. Use loopback mock peers; never depend on another
application's real credential store.

- **Policy receipt:** Dekopon's change guidelines specify behavior-named tests,
  cause assertions, loopback peers, and credential-store isolation.

### Rust-specific applications

- Never hold tracing `Entered`/`EnteredSpan` guards across `.await`; use
  `.instrument(span)` or a synchronous `in_scope` instead.
- Avoid panics on user input, unnecessary async dependencies, and public APIs
  based on `anyhow`; expose errors callers can act on. Avoid `unsafe` unless a
  justified requirement and documented safety invariants warrant it.
- Preserve project lint policy. Any justified allowance is site-scoped and
  explains why it is safe, not widened to a module or crate for convenience.

These applications come from the same source snapshot's **Change guidelines**
and **Review checklist**; they are Rust-specific expressions of the rules,
not a mandate to copy Dekopon's full lint configuration.

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

Each worktree needs its own `target/`. A shared `CARGO_TARGET_DIR` or
`build.build-dir` takes a coarse Cargo lock and serializes agents. Across
divergent commits, it also serves the other worktree's code. sccache reuses
compilation without that lock, but each target still stores restored files.
Physical deduplication is §32.

- **Wrong-code receipt, 2026-09-10:** two dekopon worktrees shared one
  build-dir. The divergent one reported 40/40 Fresh, linked main's code, and
  its tests passed. Cargo hashes path packages relative to the workspace root
  (`rust-lang/cargo#17312`, a duplicate of #12516). `-Zfine-grain-locking` still
  reran 49/50 units and hung 2 of 5 pairs.

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
- **kache 0.19.0 on `dekopon-storage-host`, 2026-09-10:** workspace crates
  hit across worktree paths. Deleted targets rebuilt at 62/63 hits, leaving
  2.7 MiB of APFS private bytes each. Tests and a checksum scrub passed.
- kache remains a pilot pending these (#760 closed 2026-08-20):
  - `kunobi-ninja/kache#971`: restored files keep mode 444.
  - #998: cc DWARF archives miss per checkout.
  - Clippy under the wrapper.
  - One full-workspace `KACHE_VERIFY=1` run.
- The architecture, not the tool, is law; see `RUST_WORKTREES.md`.

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

### 28. An inline override carries only real overrides. Never restate a default.

Restating a default adds no information and silently pins today's value against
future chart changes. Delete any override equal to `values.yaml`.

### 29. Mirror the chart's `values.yaml` key order in the override.

Mirror the chart's key order so comparison is one top-to-bottom scan; order by
the chart, not insertion history.
