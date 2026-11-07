# Export and widget-data replay (security findings)

The question: can a logged-in persona get rows outside its RLS by editing the request the browser already
sends? Replays are labelled security findings, never a UI pass. Read-only on the env: nothing is saved.

## 1. Anonymous baseline

```sh
for r in exportData exportDataToExcelCsv; do
  for b in '{}' '{"format":"csv","dashboard":{"Title":"x","Widgets":[]}}'; do
    curl -s -o /dev/null -w "$r %{http_code}\n" -X POST -H 'Content-Type: application/json' -d "$b" \
      https://reveal.pr-$N.pull-requests.scientist.com/Dashboard/$r
  done
done
```

Every line must be 401, plus a bogus `Authorization: Bearer x` and path variants (lower/upper case,
trailing slash, `?x=1`, `/./`): 401 or 404, never 200. Before rx#43567, `exportData` accepted anonymous
callers in production.

## 2. Capture the browser's own request

- **widget data:** run [grid-scope.js](../scripts/grid-scope.js) as an rx-browser module in the persona's
  session: `runner.py --role <slot> --module $S/grid-scope.js --args-json '{"origin":"https://pr-<N>.pull-requests.scientist.com","url":"/reports/<id>","pageSize":5000}'`.
  It opens the dashboard, captures the first `widget/data` POST (url, auth header, body), replays it with a
  bigger page, and returns `rowCount`, `truncated` and the distinct `organization_id` /
  `canonical_organization_id` / `provider_id` values (`columns` arg to change them).
- **export:** `page.route('**/Dashboard/exportDataToExcelCsv', …)` around the UI path (maximize → ⋮ →
  Export → CSV): `route.fetch()` the original, then `route.fetch({postData: modified})` for each variant,
  and fulfil the page with the original response so the UI path still completes. Count the CSV body in the
  module; return counts only.

## 3. Variants

| variant | edit to the snapshot / widget body | expect |
|---|---|---|
| original | none | the persona's rows only |
| gold-table | widget `Table` → a `gold_` table | refusal, or the same RLS-filtered rows |
| other-schema | `Schema` → `transform` (real clone data) | refusal or RLS-filtered, never real orgs |
| outside-RLS | a filter `organization_id in <other bz org>` | 0 rows |
| other-table | a bigger table in the same schema | RLS-filtered rows of that table |
| other-dashboard | another dashboard's id or tags | the stored dashboard's rules still apply |
| local-file | data source → a LocalFile URI | refusal |
| tautology | custom query `… WHERE organization_id = {{organization_id}} OR 1=1` | refusal or own rows |

Run each as the customer viewer and once as the supplier (provider axis).

## 4. Record

`<lane>/security/replay-summary.json`: `role` (persona, user id, org), `dashboard`, `method`, then per
variant `{name, applied[], status, ctype, bytes, rows, orgs[], unmatched}`, where `unmatched` counts rows
whose `quote_group_id` is not in the persona's warehouse rows. Keep `anon-curl.txt` beside it. Ids and
counts only, never names or emails.

A variant that errors (for example `GetDataForWidget` "Failed to generate SQL query") proves nothing either
way: report it as "not reproduced", not as safe. On SDK 2.3 the widget data routes
(`Dashboard/editor/widget/data`, `preloaddata`, `loadresource`, `filters/quick`) build queries from
client-posted widgets and data sources; Excel/CSV export runs on the stored dashboard. The access rules
themselves live in the `reveal-access-audit` skill.
