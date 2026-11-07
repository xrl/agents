# Memory lane: rx-reveal under export load

Runs **alone**: no other lane may export while it samples. `S=~/.claude/skills/rx-pr-site/scripts`,
`E=<evidence>/<batch>/mem`, `N` = PR number. The brief must allow exactly one kubectl write: deleting
rx-reveal pods one at a time.

## 1. Clean baseline

Earlier lanes leave pods at whatever their last export peaked at (3.6 GiB after grid PDFs on 11-06), and
no GC mode returns memory to the ~0.12 GiB boot baseline. So restart them, one at a time:

```sh
$S/mem_sampler.sh sample $N $E 5 7200        # run_in_background; touch $E/.stop to end it
for i in 0 1 2; do
  $S/mem_sampler.sh mark $E delete-pod-$i
  kubectl --context k3 -n rx-pr-$N delete pod rx-pr-$N-rx-reveal-$i
  kubectl --context k3 -n rx-pr-$N wait --for=condition=Ready pod/rx-pr-$N-rx-reveal-$i --timeout=300s
  curl -s -o /dev/null -w '%{http_code}\n' https://reveal.pr-$N.pull-requests.scientist.com/health
  $S/mem_sampler.sh mark $E ready-pod-$i "health=200"
done
```

Then 5 minutes idle, bracketed by `mark … baseline-start` / `baseline-end`. Confirm any env trial you are
measuring is in each pod (`kubectl exec … -- printenv <VAR>`); remember the ApplicationSet's `rx-reveal.env`
replaces the chart's env, so a trial set in chart values never arrives.

## 2. Scenarios (browser, bz-bo-staff, maximized grid, Export → Excel/CSV)

| id | what |
|---|---|
| s1, s2 | 36k CSV, 36k Excel |
| s3, s4 | 108k CSV, 108k Excel (the XL scratch draft) |
| s5 | 2 concurrent 108k Excel from sessions `m1`, `m2` |
| s6 | 3 concurrent 108k Excel from `m1`–`m3` |
| idle | 10–15 min, nothing |
| pdf | optional, last and alone: one PDF of the 36k dashboard, to record its curve |

`mark` the start and end of each, and note which pod served it (the sample whose `memory.current` moves).
At each peak: `mem_sampler.sh procs $N $E <scenario>` (Chromium `headless_shell` RSS, `/scratch` and
`~/.cache` size; a pre-baked image shows `/opt/ms-playwright/chromium_headless_shell-*` and an empty
`~/.cache`). Before the first and after the last: `mem_sampler.sh oome $N $E before|after`.

## 3. Outputs

- `samples.csv`: `ts,pod,top_cpu_m,top_mem_mi,memory_peak_bytes,memory_current_bytes,anon_bytes,file_bytes,restarts,ready,last_term_reason`.
- `markers.csv`: `ts,marker,detail`.
- `memory.png`: `memory.current` per pod over time with marker lines. Small; one chart.
- `analysis.json`: `baseline_current_mi` per pod, then per scenario per pod `peak_mi`, `max_cur_mi`,
  `max_top_mi`, `end_cur_mi`, `back_s` (seconds until `memory.current` is back within 500 MiB of baseline,
  `null` if never), plus the idle anon/file split at the end.
- Every exported file counted (108,408 × 37 for XL) so a fast scenario is not a truncated one.

## 4. Pass

0 restarts, 0 OOMKilled, 0 `OutOfMemoryException`; per-pod peak ≤ 3 GiB in a 4 Gi limit; every file
complete. Retention (back within 500 MiB of baseline by 10–15 min) is reported, not assumed: on SDK 2.3,
workstation GC held 0.96–1.31 GiB at 15 min idle (anon 0.45–0.8), and that is the shipped baseline.

`kubectl top` lags and under-reads; `memory.current` includes page cache (`file`), so judge leaks on
`anon` and limits on `memory.peak`. Do not change env or the chart inside the lane: if it fails, report
the curve and stop.
