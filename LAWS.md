# Laws of Software

Opinionated rules with receipts from `rdkit-rs/rdkit`,
`rdkit-rs/rdkit-debian`, `rdkit-rs/cheminee`, `knievel-ads/knievel`,
`vasovagal/corti`, `dekopon-agents/dekopon`, and this workstation. Named exceptions refine the rule;
they do not silently waive it.

Read for build/release, GitOps, or worktree conventions. For code review, go
directly to [CODE_DESIGN_RULES.md](CODE_DESIGN_RULES.md).

## The Build Rules

### 1. Build natively per arch. Stitch with a manifest.

Native runners beat emulation on speed, debugging, and cache hits. Build on an
architecture matrix, then fan in to a small `docker manifest create` job.

- **Receipts:** `cheminee/.github/workflows/build_docker_images.yml:14-20,118-143`
  uses native x86_64/arm runners and a 2-vCPU manifest job;
  `rdkit-debian/.github/workflows/build.yml:57-64` does the same on
  GitHub-hosted runners.

### 2. Prefer host compilation when it produces runtime-compatible artifacts.

Compile on the host when its target, sysroot, native libraries, and runtime ABI
match deployment requirements; Docker can then package the finished artifact.
Matching CPU architecture alone is insufficient: a macOS executable cannot run
in Linux, and a newer host glibc can exceed the runtime image's version.
Use a pinned container builder with appropriate cache mounts when it establishes
the required environment. Measure the full loop rather than banning containers.
Observed buildx loops fell from ~90 seconds to ~2-second host rebuilds in the
projects below; that is a receipt for those environments, not a universal result.

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

### 5. Cache expensive reusable CI work when it improves total job time.

Measure restore, decompression, save, and miss costs as well as compilation.
Cache compiler outputs, dependencies, package-manager stores, and expensive
upstream artifacts when reuse beats those costs; centralize compatible keys and
setup. Bypass or remove caches whose overhead exceeds their benefit, especially
for short jobs or high key churn. Fast feedback, not cache presence, is the goal.

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
- build, test, and verify packages in an unprivileged job first;
- do not rerun compilation in the privileged job: ordinary `cargo publish`
  verification can execute build scripts and procedural macros. An earlier
  dry run does not isolate a later privileged compilation;
- bind the upload to the exact verified package contents: record package
  digests in the unprivileged phase, transfer those artifacts through a trusted
  handoff, and verify their digests before upload. Use an upload path that does
  not rebuild them. If using `cargo publish --no-verify`, note that it may still
  repackage: compare the actual upload package to the verified artifact and
  establish that packaging cannot execute untrusted code for the selected
  Cargo version. The flag alone is not an artifact-identity guarantee;
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

## Relocated code rules

Rules 9–10 and 34–41, plus Rust-specific applications, now live in
[CODE_DESIGN_RULES.md](CODE_DESIGN_RULES.md). Legacy anchors are retained below.

<a id="the-service--api-rules"></a>
<a id="the-code--api-design-rules"></a>
<a id="9-one-authoritative-api-contract-poem-openapi-for-implementation-first-rust-services"></a>
<a id="10-generated-clients-live-in-their-own-repo-upstream-commits-downstream-publishes-same-tag"></a>
<a id="34-preserve-error-causes-report-each-failure-once"></a>
<a id="35-classify-errors-by-the-decision-callers-must-make"></a>
<a id="36-report-all-validation-conflicts-together"></a>
<a id="37-bound-everything-that-grows-or-blocks-give-it-an-owner"></a>
<a id="38-construct-expensive-reusable-resources-once-not-per-request"></a>
<a id="39-new-public-surface-needs-a-real-consumer-now"></a>
<a id="40-keep-one-definition-per-fact-test-unavoidable-mirrors"></a>
<a id="41-tests-pin-behavior-and-failure-causes-not-implementation-details"></a>
<a id="rust-specific-applications"></a>

## The Workstation Rules

These receipts include the workstation and its disk-full/probe incidents.

### 21. Standardize on kache; install a wrapper wherever configuration requires it.

A committed wrapper must be installed in every environment covered by that
configuration. Prefer host-global config over imposing it on every clone.
Current host/container policy: [RUST_AGENT_RULES.md](RUST_AGENT_RULES.md).

### 22. Historical sccache measurements are not kache policy.

See [RUST_CACHE_HISTORY.md](RUST_CACHE_HISTORY.md).

### 23. An abandoned worktree hoards its target/ forever. Remove worktrees when the branch lands.

A worktree's gitignored `target/` has no GC. After pushing anything unpushed,
run `git worktree remove <path>` and `git worktree prune`; bare `rm -rf` leaves
stale `.git/worktrees/` administration.

- **Anti-receipt, 2026-06-09:** four stale hidden Claria/Cousteau worktrees held
  43.6 GiB (22/10/7/3.8), including one with three unpushed commits.

### 30. Use kache as the standard host compiler cache. Never share `main`'s `target/`.

See [RUST_WORKTREES.md](RUST_WORKTREES.md).

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

See [RUST_WORKTREES.md](RUST_WORKTREES.md).

## The GitOps Rules

### 24. Kubernetes core services should use selfHeal.

Without ArgoCD `selfHeal`, live drift can persist until another sync. Enable
`automated.selfHeal: true` for core controllers, networking, certs, and
observability. Decide `prune` separately: restoration of declared resources
does not justify automatic deletion of removed resources. Protect namespaces,
CRDs, and other destructive resource classes with explicit prune exclusions or
approval gates. A business app may omit self-healing for deliberate live
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

### 28. Remove redundant defaults; retain intentional policy pins.

An override equal to `values.yaml` is redundant unless it intentionally pins an
operational or security invariant across chart upgrades. Retain and briefly
explain such pins, for example authentication, `allowPrivilegeEscalation: false`,
or a required replica count. Delete defaults that carry no independent policy.

### 29. Mirror the chart's `values.yaml` key order in the override.

Mirror the chart's key order so comparison is one top-to-bottom scan; order by
the chart, not insertion history.
