---
name: rx-pr-site
description: Stand up, pin, configure, seed and prove a change on an rx `run-in-k3` PR site (`rx-pr-<N>`, `*.pr-<N>.pull-requests.scientist.com`, a copy-on-write clone of production Aurora) — the label pre-flight, readiness gates, rx-reveal image pins, env traps, loading bronzezilla and personas into the clone, Elasticsearch, read-only prod-clone sampling, the human-path acceptance harness (browser + Claude Code CLI as MCP client), the export replay and memory lanes, and teardown. Use when Xavier says "PR site", "run-in-k3", "pr-<N>", "prod clone", "pin rx-reveal on the PR", "acceptance on the PR site", asks whether a PR env is up, wants bz data or personas on one, or wants a change proven there before staging. Complements rx-browser (driving the pages) and reveal-access-audit (what the rules should be).
---

# rx PR sites

`S=~/.claude/skills/rx-pr-site/scripts` · `N` = PR number · `NS=rx-pr-$N` · `K="kubectl --context k3 -n $NS"`.
Hosts: Backoffice `backoffice.pr-$N.pull-requests.scientist.com`, storefront `pr-$N.pull-requests.scientist.com`
(the `pr-org:` tenant), Reveal `reveal.pr-$N.pull-requests.scientist.com` (`/mcp`, `/health`). Argo app
`argo/rx-pr-$N`; Rails web pods `-l app.kubernetes.io/name=rx,app.kubernetes.io/component=web` (container
`rx`); rx-reveal `rx-pr-$N-rx-reveal-{0,1,2}` (container `rx-reveal`, 4Gi limit; prod has 8Gi).

A PR site is neither local dev nor production: real customer data, writes allowed on bz data only, no
workers. Every write is journaled (actor, command, target, outcome) before the next step.

## Scripts

| script | does | writes? |
|---|---|---|
| `env_status.sh <N>` | one line: Argo sync/health + op phase, ns, clone secrets n/2, PR head + whether its Rails image is in ECR, running Rails and rx-reveal tags, pods | no |
| `wait_env.sh <N> secrets\|built\|ready [s]` | polls the above every 60 s until the condition holds | no |
| `node_watch.sh <dir> [s]` | sidecar: node reclaim events and runner placement during applies; bounded | no |
| `rails_runner.sh <N> <x.rb> …` | copy a script into a fresh web pod `/tmp` dir, `bin/rails runner` it, remove the dir; `--reveal-creds` pipes rx-reveal's DB creds pod to pod | /tmp only |
| `reveal_ro.rb` | one SELECT against `reveal.*` over a READ ONLY connection | no |
| `world_gate_check.rb` | `AuthorizationService` gate matrix for `PAIRS=uid:org,…`, rolled back | no |
| `loader-pod.yaml` | `envsubst` template: throwaway psql pod on the rx-reveal image with clone-owner env | pod |
| `strip_views.py`, `stream_strip_views.py` | drop view DDL from a bz `pg_dump` (streaming one renames the schema) | local |
| `build_rdash.py` | bz dashboards → `.rdash` + `plan.json`, ids remapped to ≥900M | local |
| `publish_dashboards.rb` | PUT + PATCH-publish a plan to the in-cluster rx-reveal as bz-bo-staff | dashboards |
| `es_seed.rb` | Searchkick reindex of bz rows only (refuses >1000) + org-provider fan-out | ES |
| `grid-scope.js` | rx-browser module: capture and replay a dashboard's `widget/data` POST | no |
| `mem_sampler.sh sample\|mark\|procs\|oome` | memory lane sampler, markers, process/cache census, OOME counts | no |
| `mcp_login_pty.py` | runs `claude mcp login` under a pty, writes the authorize URL | local |

Every script answers `--help`. Details: [data-loading](references/data-loading.md),
[acceptance-harness](references/acceptance-harness.md), [mcp-client](references/mcp-client.md),
[memory-lane](references/memory-lane.md), [replay-harness](references/replay-harness.md).

## Lifecycle

1. **The label runs production terraform.** Adding or removing `run-in-k3` makes rx's "PR Database Clone"
   workflow dispatch infra's `Terraform: rds` (`rds.yaml`) and `Terraform: keycloak` (`keycloak.yaml`) on
   main against the **production** workspaces (`module "pr_clones"` lives in
   `infra/terraform/rds/rx-production-aurora.tf`), so any unapplied drift rides along. Pre-flight, every time:
   ```sh
   gh run list -R scientist-hq/infra --workflow rds.yaml -L 3; gh run list -R scientist-hq/infra --workflow keycloak.yaml -L 3
   gh run view <last id> -R scientist-hq/infra --log | grep -m3 -E 'No changes|Plan: '      # both must say No changes
   gh api "repos/scientist-hq/infra/commits?sha=main&since=<that run's createdAt>" -q '.[].sha'   # must be empty
   ```
   No run in flight either. Add the label once and never remove it mid-run. Closing the PR also dispatches
   teardown, so never close a PR site's PR on your own call. `pr-org:<sub>` and `pr-dw-schema:<schema>`
   labels don't touch terraform.
2. **Timeline.** Keycloak apply (4 added), rds apply ~9 min (mostly a redundant database-wide ANALYZE,
   infra#981), Rails image 11–15 min per push, first sync ~45 min, mostly waiting on the Rails image, not ES.
   The deploy bot gives up after 10 min; that is not a failure. Gate with
   `wait_env.sh $N secrets` (terraform wrote both clone secrets), then `built`, then `ready`
   (Argo Synced/Healthy), each `run_in_background`. The PR status comment never posts (infra#981).
3. **A runner reclaim can kill an apply.** The `gha-cxxlarge` ASG's AZRebalance (not cluster-autoscaler)
   killed a runner mid-`alter_roles`: cluster and writer existed, no k8s secrets, rx-reveal stuck in
   CreateContainerConfigError. Re-dispatch `gh workflow run rds.yaml -R scientist-hq/infra --ref main` (it
   converged on retry 1; give it ~5 tries) and run `node_watch.sh <dir>` beside it. Fixes open: k3#943, infra#982.
4. **Alert noise.** A normal first sync fires a critical `ArgoCDAppUnsyncable` into #k8s-alertmanager while
   the es-restore hook runs (k3#944). Not page-worthy; say so in the journal.
5. **Teardown.** After the change ships to staging: label pre-flight again, remove `run-in-k3`, delete the
   scratch rx-reveal build branch. A clone whose 45-day S3 marker expires is reaped silently and the env
   sits in CreateContainerConfigError holding EBS and ES memory: tear down long-lived sites on purpose.

## Images and pins

1. **The PR site runs rx-reveal 0.9.0 unless you pin it.** The PR ApplicationSet pins `rx-reveal.image.tag`
   inline, and inline values beat the branch chart, so a values bump on the branch does nothing. Pin by
   hard-coding the tag in `rx-reveal/charts/rx-reveal/templates/statefulset.yaml`
   (`image: "{{ .Values.image.repository }}:manual-<sha8>"`) in an `[integration-only]` commit.
2. **Build `manual-<sha8>`** with `gh workflow run rx-reveal-release.yml -R scientist-hq/rx --ref <scratch branch>`
   from a branch with no PR (`integration-rxr-build-*`), so the push doesn't start a second Rails build.
   Each dispatch posts to Slack through a hardcoded webhook (rx#43424): expected, not yours to silence.
3. **Env for rx-reveal goes in the statefulset template.** The ApplicationSet's `rx-reveal.env` replaces
   the chart's env list, so env set in chart values (DATAS, `DOTNET_gcServer` trials) never reaches the pods.
4. **Push ordering.** (a) Pin only after the tag is in ECR:
   `aws ecr describe-images --repository-name rx-reveal --image-ids imageTag=manual-<sha8> --region eu-central-1`.
   (b) Before every push, `gh pr view $N --json mergeable,mergeStateStatus`: a PR CONFLICTING with its
   **base** runs no PR workflows, so Rails stays on the old image while rx-reveal rolls. (c) Argo syncs the new
   SHA at once and the hooks sit in ErrImagePull until the image lands: wait for `built`, don't diagnose.
   (d) A hook waiting on an image that will never build blocks Argo indefinitely (103 min seen). Terminating
   the operation is an `argo`-namespace write, so Xavier runs it:
   `kubectl -n argo patch application rx-pr-$N --type merge -p '{"status":{"operationState":{"phase":"Terminating"}}}'`.
5. **One writer for the integration branch.** Each push rebuilds Rails and cancels the build in flight;
   batch merges and push once.

## Config

A Reveal/MCP PR site needs, until the open PRs merge (`[integration-only]` commits meanwhile):

- `RX_DOMAIN` on `rx-pr-site` (rx#43421). Without it `McpIssuer` advertises **production**
  `backoffice.scientist.com/oidc` from the PR env.
- `Reveal.Mcp`, `TrustedJwtIssuers` (`rx-static` must stay listed, or browser tokens break) and
  `DataWarehouse.Schema` templated from the PR number (k3#946; the schema via a `pr-dw-schema:` label).
  The appsettings ConfigMap is mounted by `subPath` with no checksum: a ConfigMap change alone never reaches
  a running pod.
- Ingress `proxy-body-size: 200m` and rx-reveal limit 4Gi (both on k3-applications main).
- `REVEAL_USAGE_LOG_NAMESPACE=production` for usage pages; otherwise the site counts its own namespace's logs.
- One storefront tenant per env: `pr-org:<subdomain>` → `PR_SITE_FORCE_SUBDOMAIN`. RLS across two buyer orgs
  needs masquerade or MCP.
- Before pointing any client at it: `/.well-known/oauth-protected-resource` must name `pr-$N`.

**It is slow, and that is known.** The chart's 3-leader RedisCluster behind a plain `url:` client answers
`MOVED`, so 2 of 3 cache keys miss (rx#43445). The ~3 s Backoffice home is ~670 ms of DB plus a cold
render, not Redis or S3. Don't benchmark Rails here.

## Data safety

The clone **is** production data: real customers, users and dashboard titles, plus 12,333 unfinished prod
`good_jobs`, inert only because no worker runs.

- Never enable workers or cron. `perform_deliveries=false` (rx#43447's mail guard) and the Salesforce + cron
  guard (rx#43446) must be on the branch before any write that can enqueue.
- After any write, list jobs it enqueued and discard them (`GoodJob::Job#discard_job`; Salesforce, Mail and
  Embedding jobs on 11-05). Record before/after unfinished counts.
- The prod attachments bucket answers AccessDenied to `k3-rx-pr`: logos are 0-byte 200s, uploads fail.
  Not your bug.
- Real names appear in Backoffice and dashboard lists: prod-clone screenshots stay local; only bz-data shots
  leave the machine, after a privacy pass. Reports carry ids, never emails or names.
- `ANTHROPIC_ADMIN_API_KEY` is mounted into every PR namespace: never print pod env wholesale.

## Data

1. **Load bronzezilla** as `sci_rx_production` from a throwaway pod (`loader-pod.yaml`) with
   `kubectl exec -i … psql -1 < dump` (7 MB in 4 s, 1.77 GB in 66 s). **Strip the dbt views first**
   (`strip_views.py` / `stream_strip_views.py`): 107 of them read `public.*`, and the schema grant would hand
   real rows to `reveal_transform`. Probe `CREATE SCHEMA` in a rolled-back transaction first. ANALYZE only
   the loaded schemas, table by table; the clone inherits production's `pg_statistic`.
   Steps and SQL: [data-loading](references/data-loading.md).
2. **`reveal.*` is closed to the Rails role** ("permission denied for schema reveal"). Read it with the
   rx-reveal pod's own `REVEAL_DB_*` creds piped pod to pod:
   `rails_runner.sh $N $S/reveal_ro.rb --reveal-creds --with q.sql -- q.sql`.
3. **Publish dashboards** with `build_rdash.py` → `rails_runner.sh $N $S/publish_dashboards.rb --with out -- out`.
4. **Stress fixtures stay on the clone:** `bronzezilla_transform.reveal_marketplace_report_stress`
   (36,136 rows), `_stress_xl` (108,408 = 3 copies, `quote_group_id + k*100000`), dashboard
   BZ-EXPORT-STRESS-36K `99114753-0901-52fa-836a-b5d62f06a950` (37-col grid). The old browser 2M-cell cap
   is ≈54,054 rows at 37 columns; XL proves a path is uncapped.

## Elasticsearch

- The `es-restore` Sync hook (wave 5, `backoffLimit: 0`, 3600 s deadline) gates Rails (wave 10): a failed or
  timed-out restore leaves Rails undeployed until the next push.
- `pg_inventory_items_*` (81.4 GB) dominates the restore and overruns the deadline. Use
  `ES_RESTORE_EXCLUDE` (rx#43429) or delete that index by exact name in the PR cluster
  (`Searchkick.client.indices.delete(index: "<exact name>")` via `rails_runner.sh`): it turns green at once.
- **Never `searchkick:reindex:all`.** Seed bz docs only: `rails_runner.sh $N $S/es_seed.rb --env ORG_PROVIDER_ORG_IDS=<bz canonical orgs>`
  (ids ≥900M, refuses >1000 rows per model). The org-provider fan-out is ~27k docs, 3–5 min per org;
  retry once on `Net::ReadTimeout`.

## Personas and logins

- **Sync** with `rake bronzezilla:sync_personas[identities.json]`, `BZ_ALLOW_PR_CLONE=rx-pr-$N`, password on
  stdin ([data-loading §6](references/data-loading.md#6-personas-needs-rx43447-on-the-pr-branch)). It needs
  rx#43447 on the PR branch: without it the sync aborts on NoOutboundGuard and writes domain rules onto
  Backoffice 175, which flips `allows_anonymous_users?` false for all of Backoffice. A re-run resets every
  persona password.
- **Roster** (`@bronzezilla.example`): bz-bo-staff (admin, `become-user`, reveal_bi_admin/internal, provider
  13472), bz-bo-author (internal + `site_rep` on bz_a/bz_b), bz-supplier-mcp, bz-supplier-s, bz-viewer-a1,
  bz-mcp-a, bz-orgadm-a. bz_b has no warehouse rows of its own; they sit on bz_b1.
- **Passwords** live in the campaign's persona password files (one per role group); refer to them by path,
  never print them, and stop before 10 failed logins per persona.
- **Logins:** the UI offers only Keycloak/Google SSO, but the server takes passwords. Use rx-browser's
  `login` module with `--actor-file` (`{key, email, rails_user_id}`) and `--secrets` (a 0600 `{"password":…}`
  JSON built from the password file in a 0700 temp dir, deleted after) on the Backoffice or storefront origin.
- Logging a persona into a host where it isn't a member auto-adds the membership (MissingOrgAction), and
  Backoffice password logins join org 175. Log each persona into its own host only.
- Masquerade, View-as and scratch-draft flows: rx-browser `reveal.md` / `reveal-gotchas.md`.

## Prove it

1. **Read-only prod-clone sampling is the rule oracle.** Wherever a change depends on real data shapes
   (memberships, flags, sub-orgs, grants), sample the clone: `rails_runner.sh` with
   `SET TRANSACTION READ ONLY` + `raise ActiveRecord::Rollback`, ids not emails. On 11-05 this found 22/37
   internal users over the 200 cap, 18 staff minting bypass on 20 customer orgs, and 37 internal users
   listing 10 dashboards they couldn't open. Gate matrices: `PAIRS=… rails_runner.sh $N $S/world_gate_check.rb`.
2. **Acceptance walks the human path or it is a FAIL.** One brief per lane, check JSON
   `{role,path,steps,expected,actual,pass,artifacts,ts}`, Opus-judged clipped shots in `verdicts.json`,
   OOME/restart census before and after, scratch-draft writes only, ≤1.2 KB JSON and one journal line per
   lane. Never hand a tester an identity or host you haven't proven green.
   [acceptance-harness](references/acceptance-harness.md).
3. **Memory lane runs alone:** clean baseline by deleting rx-reveal pods one at a time, `mem_sampler.sh`
   every 5 s, 36k/108k CSV and XLSX then 2× and 3× concurrent, then idle.
   [memory-lane](references/memory-lane.md).
4. **Replay the browser's own export/widget request** with edited bodies (gold table, other schema, outside
   RLS, LocalFile, tautology custom query); anonymous POSTs must 401.
   [replay-harness](references/replay-harness.md).

## MCP client

The Claude Code CLI is the client: scratch `CLAUDE_CONFIG_DIR`,
`claude mcp add --transport http --scope local reveal-pr-$N https://reveal.pr-$N.pull-requests.scientist.com/mcp`,
`mcp_login_pty.py` in the background (the login needs a TTY), consent in the persona's playwright session,
then `claude -p` on Bedrock (`CLAUDE_CODE_USE_BEDROCK=1 AWS_PROFILE=scientist AWS_REGION=us-east-1`)
restricted to `mcp__reveal-pr-$N`, every transcript saved. Clean up the server, the keychain item
`Claude Code-credentials-<hash>` and the dir. mcporter only cross-checks raw JSON.
[mcp-client](references/mcp-client.md).
