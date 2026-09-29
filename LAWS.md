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

<a id="3-a-tag-is-a-vote-of-confidence-dont-re-run-ci-on-it"></a>

### 3. Tags from protected, green main need release work, not duplicate CI.

A tag cut from branch-protected, green `main` needs only tag-specific work:
build, sign, publish, attest. Do not repeat the already-passed PR matrix solely
because a tag was created.

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
  Historical evidence for the pinning requirement above, not a current merge instruction.

### 42. Contract changes dictate ship order; enumerate consumers at their deployed version.

Before landing a change to a wire format, WIT interface or config key, list
every consumer at the version that is actually deployed, verify each claim
against the real artifact (the binary's imports, a decode of real data) rather
than against what the team believes it uses, and write the ship order into the
PR. Each repository also has its own release ritual: read its tags and release
commits before trusting its README or release automation.

- **Receipt, dekopon, 2026-09-27:** a deployed provider imported lock functions
  everyone "knew" it did not use; a client decoded only because a new field
  happened to be empty; old and new binaries each refused the other's config key.

## The Workstation Rules

These receipts include the workstation and its disk-full/probe incidents.

### 21. Standardize on kache; install a wrapper wherever configuration requires it.

A committed wrapper must be installed in every environment covered by that
configuration. Prefer host-global config over imposing it on every clone.
Current host/container policy: [RUST_AGENT_RULES.md](RUST_AGENT_RULES.md).

### 22. Historical sccache measurements are not kache policy.

See [RUST_CACHE_HISTORY.md](RUST_CACHE_HISTORY.md).

### 23. An abandoned worktree hoards its target/ forever. Remove worktrees when the branch lands.

A worktree's gitignored `target/` has no GC. Before removal, obtain the owner's
agreement that no new commands will start until cleanup finishes, then verify
no build is running there. Preserve dirty work and push unpushed commits before
running `git worktree remove <path>` and `git worktree prune`; bare `rm -rf`
leaves stale `.git/worktrees/` administration.

- **Anti-receipt, 2026-06-09:** four stale hidden Claria/Cousteau worktrees held
  43.6 GiB (22/10/7/3.8), including one with three unpushed commits.

<a id="30-use-kache-as-the-standard-host-compiler-cache-never-share-mains-target"></a>

### 30. Use kache on the host. Never share targets between worktrees.

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

### 55. Label what a run creates in Docker; release it when the result is recorded.

Every container, image, volume and network a run creates carries one label,
so release is one filter and touches nothing else on the machine. Keep them
while iterating on a fix or re-measuring a number. Release them, builder cache
included, in the same turn the result file is written; never keep them "just
in case". Verify with filtered `docker ps -a`, `images`, `volume ls` and
`network ls`, and report `df` before and after. A colima disk image does not
shrink when its contents are deleted; recreating the VM is the owner's call.
Containers build without the host's compiler cache
([RUST_AGENT_RULES.md](RUST_AGENT_RULES.md) rule 12).

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

### 43. Ordering guarantees hold only within the controller that gives them.

Argo sync waves order one Application's resources; a config-reload controller
restarts pods outside that order, and a binary that reaches the cluster before
its config (or after) crash-loops briefly. In an app-of-apps, refresh the parent
so spec and source move together, expect the brief loop, and fail forward with
the next commit rather than reverting by push.

- **Receipt, rpi-homelab, 2026-09-27:** sync waves did not hold under the reload
  controller during a coupled config-key and binary change.

## The Campaign Rules

### 44. A trivial artifact in most agents' diffs is a chokepoint, not work.

When one shared file appears in most open PRs or most agents' tool calls, move
its edit to release time (a `Changelog:` line in each commit message, grepped
from `git log` at release prep) instead of coordinating writers. Land the ready
PRs back to back and rebase the rest once; a head with no CI is a conflicting
head, so rebase rather than wait. Wait on CI with one blocking command, never
repeated status calls. Between waves ask which file most open PRs conflict on,
whose tool calls are mostly polling, and whose spend is out of line with its
diff; report usage at each milestone without being asked.

- **Receipt, dekopon, 2026-09-27:** `CHANGELOG.md [Unreleased]` edits in every
  PR put each remaining PR into conflict after every merge; conflicted heads got
  no CI, one agent polled for 420 tool calls, and about $400 went to churn.

### 45. Merge the head that was reviewed.

A fresh adversarial reviewer reads every PR before merge; cheap agents drive and
verify, the expensive reviewer finds the gaps. The coordinator rules on each
finding (fix, accepted trade-off named in the PR, or ignore) before routing it
back, never pushes onto a reviewed branch, and merges only the reviewed SHA;
rebases and fixes stay with the author agent. A result that meets the letter
but misses the target is redone on its branch, not merged as progress.

- **Receipt, dekopon, 2026-09-27:** across a −2,250-line campaign every real
  gap (a replay orphan, a pre-expansion bug, a dead-end default, a permission
  failure against live state) came from the fresh expensive reviewer.

### 49. Cost follows how long a context lives, not how much work it does.

Where nearly all tokens are cache reads, a coordinator costs about as much as
the driver it supervises. Start one fresh supervisor per unit of work, resumed
from a state file that is written before every wait and at every stage
boundary, and hand off when the context grows large. Keep campaign state in
files a person can edit, so the run can pause for a week, slow down, or lose a
session. Drive nothing from the session that planned it. Sketches, briefs,
rehearsals and reviews are about one percent of spend: never cut one to save
money. Feed actual spend back into the estimate before funding the next
milestone.

- **Receipt, dekopon, 2026-09-29:** on this machine's logs for 15 to 28
  September, 97 to 98% of tokens were cache reads; a fresh supervisor per unit
  cut an estimated $3,127 to $2,658; every review and rehearsal together came
  to about $25.

### 50. A blocked call is free; a poll costs a full read of the context.

Run scoped gates on touched crates at each commit and let CI be the full gate.
Start the gate, the verifier, the review and CI side by side at the commit.
Re-run a bench or soak after a rebase only if the tree hash changed. Read a
gate's log instead of re-running it. A release job does not repeat the checks
that already passed on the same commit (§3).

- **Receipt, dekopon, 2026-09-29:** one unit walked minute by minute was 14
  hours, of which 6.5 were waits the plan had added and 46 minutes were CI.

### 51. Guard the inside of a stage, not only its boundary.

A running build is not progress. Give each lane tripwires a machine can read:
commit age, tool calls since the last edit, repeats of one command, a file
outside the brief's list, spend against the estimate. One firing is a look; the
same one twice after a correction stops the lane. Ask for a first commit by
minute 30. Give every reviewer and recon agent a timebox in minutes, calls and
tokens. Set the budget at the estimate's p90 and the tripwire at its p50, and
stop a lane only at a stage boundary.

### 52. Recon finds facts; a scenario walk finds design errors; a second model family finds a different class.

Recon agents answer what they are asked. Before building, have a fresh
reviewer walk real scripts through the design step by step, and buy one review
from a different model family for each large design. Rehearse every handoff:
give a cheap agent only the files and ask it to name the next action.

- **Receipt, dekopon, 2026-09-28:** four recon agents surfaced none of six
  design errors that one reviewer found by walking a script through the plan. A
  $6.71 review from a second family then found a process-killing input on
  main, a circular CI dependency and an omitted deployed consumer; none
  overlapped the first family's findings.

### 53. Read-only is not harmless, and a default in source is not a production value.

A brief that may query a live store states a time range and a row limit, or
forbids live queries. Production limits are read from the deployed
configuration, never from defaults in source.

- **Receipt, rpi, 2026-09-29:** a read-only study agent ran one
  `GROUP BY trace_id` with a distinct count and OOM-killed the trace store.
- **Receipt, dekopon, 2026-09-28:** three agents reported 30 s and 1 MiB
  limits from source; the deployment ran 300 s and 12 MiB.

### 54. Name the version and the authority before the run.

Where release authorization names one version, write each milestone's version
down when the milestone is funded, with who may decide what: the supervisor,
the called reviewer, the owner. Otherwise a supervisor that finishes overnight
cannot tag, or decides something that was not its to decide.

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

## Relocated code rules

Rules 9–10, 34–41 and 46–48, plus Rust-specific applications, now live in
[CODE_DESIGN_RULES.md](CODE_DESIGN_RULES.md). Legacy anchors above retain old links.
