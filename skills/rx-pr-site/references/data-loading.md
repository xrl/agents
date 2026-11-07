# Loading bronzezilla into a PR-site clone

`S=~/.claude/skills/rx-pr-site/scripts`, `N` = PR number, `NS=rx-pr-$N`, `K="kubectl --context k3 -n $NS"`.
Every step here writes the clone. Journal each one (actor, command, target, outcome) before moving on.

## 0. Inputs (built locally, never on the clone)

- A `pg_dump -n bronzezilla_transform --no-owner --no-acl -Fp` of a local bronzezilla world after dbt
  `reveal`+`gold`. The world's dbt bronze/silver models are **views over `public.*`**: harmless over fixtures,
  real customer rows on a clone.
- `identities.json` from the same world (the persona sync input).
- The bz dashboards as JSON lines (`id, name, description, content, all_organizations, all_providers,
  organization_ids, provider_ids, user_grants, excluded_organization_ids, excluded_provider_ids`) from the
  local `reveal.dashboards`, and an id map from local ids to the ≥900M PR-site ids.

## 1. Strip the views

```sh
python3 -I $S/strip_views.py world.sql world.noviews.sql                       # fits in memory (7 MB)
python3 -I $S/stream_strip_views.py stress.sql stress.noviews.sql --to-schema bronzezilla_stress   # 1.77 GB, one pass
```

Both drop every VIEW chunk (107 on the 11-05 world) and refuse to write if a kept chunk still names
`public.`. Every `reveal_*`/`gold_*` model is a table, so nothing Reveal reads is lost. Without this,
`GRANT SELECT ON ALL TABLES IN SCHEMA … TO <transform role>` hands real rows to `reveal_transform`.

## 2. Loader pod

```sh
export PR=$N NAME=bz-loader IMAGE=554546661178.dkr.ecr.eu-central-1.amazonaws.com/rx-reveal:<tag running on the site>
envsubst < $S/loader-pod.yaml | kubectl --context k3 apply -f -
$K wait --for=condition=Ready pod/bz-loader --timeout=180s
```

The rx-reveal image carries `psql`; the pod's env comes from `rx-pr-postgres-direct-secret` (PG* =
`sci_rx_production`, the clone owner role) plus `RT_*` from the transform secret. Same template for any
side-table loader (`NAME=csv-loader`). It self-expires after 6 h; delete it when done.

## 3. Probe, then load in one transaction

```sh
$K exec bz-loader -- psql -v ON_ERROR_STOP=1 -c 'BEGIN; CREATE SCHEMA rx_pr_site_probe; ROLLBACK;'
$K exec -i bz-loader -- psql -1 -v ON_ERROR_STOP=1 < load.sql
```

`load.sql` = `DROP SCHEMA IF EXISTS <schema> CASCADE;` + the stripped dump + the grants:
`GRANT USAGE ON SCHEMA <schema> TO <transform role>; GRANT SELECT ON ALL TABLES IN SCHEMA <schema> TO <transform role>;`
(the role is `RT_USER` in the pod; read it with `$K exec bz-loader -- printenv RT_USER`, it is not a secret).
Streaming over `exec -i` needs no `kubectl cp`: 7 MB in 4 s, 1.77 GB in 66 s. On 11-05 `sci_rx_production`
could `CREATE SCHEMA`; never assume it, hence the probe.

## 4. ANALYZE only what you loaded

The clone inherits `pg_statistic` from production (`public` 94 %, `transform` 100 % covered at clone time).
Analyze the loaded schemas table by table:

```sh
$K exec bz-loader -- psql -At -c "SELECT format('ANALYZE %I.%I;', schemaname, tablename) FROM pg_tables WHERE schemaname IN ('bronzezilla_transform','bronzezilla_stress')" \
  | $K exec -i bz-loader -- psql -v ON_ERROR_STOP=1
```

Never a database-wide ANALYZE (it is what makes the terraform `alter_roles` step take 9 min, infra#981).

## 5. Point rx-reveal at the schema

`Reveal.DataWarehouse.Schema` on the PR site: a `pr-dw-schema:<schema>` label once k3#946 merges, an
`[integration-only]` values commit until then. The appsettings ConfigMap is mounted by `subPath` with no
checksum annotation, so a ConfigMap change alone never reaches a running pod: the pods must roll.

## 6. Personas (needs rx#43447 on the PR branch)

```sh
P=$($K get pods -l app.kubernetes.io/name=rx,app.kubernetes.io/component=web --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
$K exec $P -c rx -- mkdir -p /tmp/bz && $K cp -c rx identities.json $P:/tmp/bz/identities.json
$K exec -i $P -c rx -- sh -c 'read -r BZ_PERSONA_PASSWORD; export BZ_PERSONA_PASSWORD; BZ_ALLOW_PR_CLONE=rx-pr-'$N' bundle exec rake "bronzezilla:sync_personas[/tmp/bz/identities.json]"' < <persona password file>
$K exec $P -c rx -- rm -rf /tmp/bz
```

The password goes over stdin, never argv. Read the printed JSON: `organization_provider_reindex` lists each
canonical org's deferred reindex as `ok` or an error class. A re-run resets every persona's password to the
file's value. Without #43447 on the branch, the sync aborts on NoOutboundGuard (the org-provider reindex
is explicit, not a callback) and writes exact-email domain rules onto Backoffice org 175, which flips
`allows_anonymous_users?` false for all of Backoffice. Do not hand-patch around that: get #43447 onto the branch.

## 7. Dashboards

```sh
python3 -I $S/build_rdash.py dashboards.jsonl out/ --id-map ids.json [--stress-grid BZ-GRID --stress-columns-file cols.txt]
$S/rails_runner.sh $N $S/publish_dashboards.rb --with out -- out
```

`build_rdash.py` remaps org/provider/user ids inside the publish bodies and repoints
`rx_development.transform.` → `sci_rx_production.bronzezilla_transform.`. `publish_dashboards.rb` mints a
Backoffice admin token for bz-bo-staff and PUT + PATCH-publishes each entry to the in-cluster rx-reveal
(`server` in the output is `http://rx-pr-<N>-rx-reveal:5111`). Expect `save` 201/200 and `publish` 200 per row.

## 8. Elasticsearch, bz rows only

```sh
$S/rails_runner.sh $N $S/es_seed.rb --env ORG_PROVIDER_ORG_IDS=900000001,900000004
```

Users and orgs index in ~2 s. The org-provider fan-out is ~27k docs and 3–5 min per canonical org; the
first try right after a restore can hit `Net::ReadTimeout`: retry that org once.

## 9. Stress fixtures (keep them on the clone)

| fixture | rows | built as |
|---|---|---|
| `bronzezilla_transform.reveal_marketplace_report_stress` | 36,136 | `CREATE TABLE … AS SELECT * FROM bronzezilla_stress.reveal_marketplace_report` + grant |
| `bronzezilla_transform.reveal_marketplace_report_stress_xl` | 108,408 | 3 copies with `quote_group_id + k*100000`, k = 0..2 |
| dashboard BZ-EXPORT-STRESS-36K `99114753-0901-52fa-836a-b5d62f06a950` | 37-col grid | published to bz_a, bz_b |

The browser's old 2M-cell cap is ≈54,054 rows at 37 columns; the XL table is what proves a path is
uncapped. Scratch drafts over the XL table are rebuilt per run and deleted.

## 10. Clean up

`$K delete pod bz-loader`, `rm` any `/tmp` dir you created in a web pod (rails_runner.sh does this itself),
and a journal line naming what stays (schemas, stress tables, the 36K dashboard).
