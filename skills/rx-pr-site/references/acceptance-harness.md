# Human-path acceptance on a PR site

One brief per lane, one agent per lane, evidence under one folder per batch. The worked examples are the
11-05 campaign's `campaign/ACCEPTANCE.md`, `ws11/ACCEPT-B4.md` and `ws12/ACCEPT-B5.md` under
`~/code/assaydepot/overnight-20261105/`.

## Rules every lane brief carries

- **Walk only the paths a human walks.** Browser password login through rx-browser's `login` module, the real
  menus, the real OAuth consent, the Claude Code CLI as MCP client ([mcp-client](mcp-client.md)). No
  server-minted sessions, no preset session orgs, no direct API calls in place of the UI. A path that needs a
  shortcut is a FAIL, logged as a product gap. Security replays are the one exception, and they are labelled
  as findings, not UI paths ([replay-harness](replay-harness.md)).
- **Never `playwright-cli kill-all`.** Close only sessions you opened, by exact name. Use rx-browser registry
  slots or the session names the brief assigns.
- **No passwords in any output.** Stop before 10 failed logins per persona.
- **Writes:** only what a human does through the UI on bz data (exports, View-as, masquerade) plus scratch
  drafts you create and delete, each deletion verified (gone from `/admin/reveal`, its show page reads
  "Failed to load dashboard", `archived_at` set). Never save or publish an existing dashboard. Never touch
  real orgs' data beyond read-only checks. View-mode More Options → Save As forks a "(Copy)" draft at once:
  count it as a write and delete it.
- **SQL is read-only**, through `kubectl exec` in `rx-pr-<N>` only ([rails_runner.sh](../scripts/rails_runner.sh),
  [reveal_ro.rb](../scripts/reveal_ro.rb)).
- **Watch the server** before and after every heavy step: `mem_sampler.sh oome <N> <dir> <label>` (restarts,
  OOMKilled, `OutOfMemoryException` counts) and `kubectl top pods`. 0 restarts proves nothing alone: a 4 Gi
  .NET pod caps its heap near 75 % and dies as a managed OOME (HTTP 500), not an OOMKill.
- **A lane that loads memory runs alone.** It owns the only export traffic for its duration.
- **Journal** one line per lane, `acceptance-<batch>-<lane>`, in the campaign JOURNAL.

## Check record

Each check writes `<evidence>/<lane>/<check>.json`:

```json
{
  "role": "bz-viewer-a1 (999000002, org 900000002)",
  "path": "storefront → Reports → G-CANON-A → maximize grid → ⋮ → Export → CSV",
  "steps": ["login module on https://pr-<N>.pull-requests.scientist.com", "..."],
  "expected": "42 rows, organization_id ∈ {900000002}",
  "actual": "42 rows, organization_id ∈ {900000002}; POST /Dashboard/exportDataToExcelCsv 200 1.2 s",
  "pass": true,
  "artifacts": ["shots/g-canon-a-menu.png", "files/g-canon-a.csv", "net/export.json"],
  "ts": "2026-11-06T18:40:11Z"
}
```

Rules for the fields: `role` names the persona key, user id and acting org; `path` is the click path a
person would follow; `actual` carries numbers, never adjectives; `artifacts` are paths relative to the
lane folder.

- Screenshots are clipped (trigger plus popup for menus, every item inside the clip) and judged by one Opus
  vision pass against a ≤1 KB rubric; verdicts go in `<lane>/verdicts.json` as `{shot, claim, verdict, why}`.
  Prod-clone screenshots can carry real customer names: they stay local unless the privacy pass clears them.
- Downloaded files are counted in python (`openpyxl` read-only for xlsx). RLS is checked by joining
  `quote_group_id` back to the warehouse table, not by trusting an org column. Export N is compared with a
  read-only SQL count over the same `[from,to)` window in the browser's IANA zone.
- Every Excel/CSV cell records the export request URL and status from the network log.

## Lane brief template

```markdown
# <Batch> acceptance: <what changed, one line>
Site rx-pr-<N>; integration <sha10>; Rails pr-<N>-<sha8>; rx-reveal manual-<sha8> (<SDK version>).
What changed: <3–5 bullets of behaviour, not files>.
Read first: rx-pr-site SKILL.md + references/acceptance-harness.md; rx-browser SKILL.md + reveal.md; <prior matrix>.
Evidence: <O>/evidence/acceptance/<batch>/<lane>/.

## Hard rules
<the rules above, verbatim, plus the kubectl writes this lane may make, by exact command>

## Lane `<name>` (sessions <s1>, <s2>)
1. <check id>: persona, path, expected (numbers), how to count.
2. ...

## Report
≤1.2 KB JSON: pass/fail per check, N vs SQL, peak memory, product gaps, evidence path.
Append `acceptance-<batch>-<lane>` to JOURNAL.md.
```

## Role matrix worth reusing

| persona | host | proves |
|---|---|---|
| bz-bo-staff | backoffice | admin: unfiltered on Backoffice, View-as, Become, scratch drafts, MCP as admin |
| bz-bo-author | backoffice `/reports/internal` | internal: listing == opening, draft save without publish, MCP act-as list |
| bz-mcp-a | storefront | customer admin: own org only, no sub-orgs; MCP answers name bz_a |
| bz-viewer-a1 | storefront | viewer: granted dashboards, bz_a1 rows only; MCP login refused |
| bz-supplier-s | backoffice provider tab | supplier viewer: provider S rows; MCP refused |
| bz-supplier-mcp | backoffice provider tab | supplier internal: provider S only over MCP |
| bz-orgadm-a | storefront | org admin without Reveal: no menu, MCP refused |

Reference numbers from the 11-05/06 bz world: staff 136 / 36,136 / 108,408 rows on S37 / 36K / XL;
viewer 42; supplier 98. Re-derive them with SQL if the world was rebuilt.
