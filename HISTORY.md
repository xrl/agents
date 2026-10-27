# Receipts and recipes removed from LAWS.md

Evidence and one-off recipes for rules in [LAWS.md](LAWS.md), moved verbatim with their dates. Rule text stays in LAWS.md. Not standing rules; no entry point tells an agent to read this first.

### 1. Build natively per arch. Stitch with a manifest.

- **Receipts:** `cheminee/.github/workflows/build_docker_images.yml:14-20,118-143`
  uses native x86_64/arm runners and a 2-vCPU manifest job;
  `rdkit-debian/.github/workflows/build.yml:57-64` does the same on
  GitHub-hosted runners.

### 3. Tags from protected, green main need release work, not duplicate CI.

- **Receipts:** `knievel/.github/workflows/release.yml:14-23` states this
  contract; `cheminee/.github/workflows/build_docker_images.yml:1-4` and
  `cheminee/.github/workflows/generate_ruby_gem.yaml:1-3` are tag-only;
  `cheminee/.github/workflows/test_suite.yml:2` is PR-only.

### 33. Publish crates from CI over OIDC. Stored registry tokens are bootstrap credentials, not operating credentials.

- **Source receipt:** crates.io creates a 30-minute token;
  `crates-io-auth-action@c6f97d42` (v1.0.5's verified commit) exchanges and
  revokes it.

### 33. Publish crates from CI over OIDC. Stored registry tokens are bootstrap credentials, not operating credentials.

- **Near-miss:** `claria#135` / `a3d2299` derives and registers twelve crates,
  but its OIDC job reaches floating actions directly and through `rust-setup`.
  Historical evidence for the pinning requirement above, not a current merge instruction.

### 42. Contract changes dictate ship order; enumerate consumers at their deployed version.

- **Receipt, dekopon, 2026-09-27:** a deployed provider imported lock functions
  everyone "knew" it did not use; a client decoded only because a new field
  happened to be empty; old and new binaries each refused the other's config key.

### 23. An abandoned worktree hoards its target/ forever. Remove worktrees when the branch lands.

- **Anti-receipt, 2026-06-09:** four stale hidden Claria/Cousteau worktrees held
  43.6 GiB (22/10/7/3.8), including one with three unpushed commits.

### 31. Worktrees are aggressive, branch-per-agent, and explicitly tracked.

- **Repeat anti-receipt, 2026-07-26:** at 94% disk use (26 GiB free), five
  hidden, merged Claria worktrees held ~47 GiB (15/14/13/5.4 GiB plus one
  cleaned) seven weeks after §23's incident; removing them restored it.

### 24. Kubernetes core services should use selfHeal.

- **Receipt, a production k3s cluster, 2026-06-09:** drift-deleted ARC
  `Certificate`/`Issuer` resources went unnoticed behind a retained Secret;
  renewal failed, the cert expired, and GHA lost workers for 80 minutes while
  the app had seen no commit in seven months.

### 25. Apps that install CRDs use ServerSideApply — and must be able to reach Synced.

- **Receipt:** ARC had been OutOfSync/Failed on five CRDs since November,
  masking the certificate drift in §24. Splitting, ignoring and skipping CRDs
  made it Synced for the first time since Nov 2025.

### 43. Ordering guarantees hold only within the controller that gives them.

- **Receipt, rpi-homelab, 2026-09-27:** sync waves did not hold under the reload
  controller during a coupled config-key and binary change.

### 44. A trivial artifact in most agents' diffs is a chokepoint, not work.

- **Receipt, dekopon, 2026-09-27:** `CHANGELOG.md [Unreleased]` edits in every
  PR put each remaining PR into conflict after every merge; conflicted heads got
  no CI, one agent polled for 420 tool calls, and about $400 went to churn.

### 45. Merge the head that was reviewed.

- **Receipt, dekopon, 2026-09-27:** across a −2,250-line campaign every real
  gap (a replay orphan, a pre-expansion bug, a dead-end default, a permission
  failure against live state) came from the fresh expensive reviewer.

### 49. Cost follows how long a context lives, not how much work it does.

- **Receipt, dekopon, 2026-09-29:** on this machine's logs for 15 to 28
  September, 97 to 98% of tokens were cache reads; a fresh supervisor per unit
  cut an estimated $3,127 to $2,658; every review and rehearsal together came
  to about $25.

### 49. Cost follows how long a context lives, not how much work it does.

- **Receipt, dekopon, 2026-10-15:** a 62-agent planning-and-fix session came to
  about $230 at list prices. Cache writes from 57 cold Opus starts were the
  largest line, about $88. The follow-ups resumed on warm agents (a gzip
  rework, a CI correction, a lock re-mirror) needed no re-brief.

### 50. A blocked call is free; a poll costs a full read of the context.

- **Receipt, dekopon, 2026-09-29:** one unit walked minute by minute was 14
  hours, of which 6.5 were waits the plan had added and 46 minutes were CI.

### 52. Recon finds facts; a scenario walk finds design errors; a second model family finds a different class.

- **Receipt, dekopon, 2026-09-28:** four recon agents surfaced none of six
  design errors that one reviewer found by walking a script through the plan. A
  $6.71 review from a second family then found a process-killing input on
  main, a circular CI dependency and an omitted deployed consumer; none
  overlapped the first family's findings.

### 53. Read-only is not harmless, and a default in source is not a production value.

- **Receipt, rpi, 2026-09-29:** a read-only study agent ran one
  `GROUP BY trace_id` with a distinct count and OOM-killed the trace store.

### 53. Read-only is not harmless, and a default in source is not a production value.

- **Receipt, dekopon, 2026-09-28:** three agents reported 30 s and 1 MiB
  limits from source; the deployment ran 300 s and 12 MiB.

### 56. Always fail forward: corrections are new commits, including in a PR.

- **Receipt, 2026-09-30:** a supervisor's push prompt said "amend"; the driver's
  push was rejected and the step waited on a ruling.

### 33. Publish crates from CI over OIDC. Stored registry tokens are bootstrap credentials, not operating credentials.

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

### 2. Prefer host compilation when it produces runtime-compatible artifacts.

- `cheminee/Dockerfile:43-45` copies a runner-built `target/release/cheminee`.
- `knievel/Dockerfile:67-70` likewise keeps Node compilation outside so pnpm's
  native cache works and the image carries no Node toolchain.

### 5. Cache expensive reusable CI work when it improves total job time.

- `rdkit-debian/.github/workflows/build.yml:117` promotes its ~30-minute RDKit
  build to S3; downstream jobs download it instead of rebuilding.
- The same pinned `mozilla/sccache-action@eaed7fb9…` serves RDKit and Cheminee;
  `knievel/.github/actions/rust-setup/action.yml` centralizes Rust caches.
