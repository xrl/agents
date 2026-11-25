---
name: github-ci-accounting
description: Account for GitHub Actions minutes on a personal account - billed minutes by repo, minutes per merged PR per week, waste priced in minutes per month, and a month-end projection against the plan's included minutes. Use when Xavier asks about "CI spend", "Actions minutes", "are we going to run out", "CI waste" or "minutes per PR". Read-only; fixes go to the repo owner as cards.
---

# GitHub CI accounting

Run `scripts/ci_accounting.py` with `python3 -I` (stdlib only, every call a `gh api` GET with retry and timeout). `--json` before the subcommand prints the report as JSON.

```sh
CI="$HOME/code/xrl/agents/skills/github-ci-accounting/scripts/ci_accounting.py"
python3 -I "$CI" usage --owner xrl [--month 2026-11]
python3 -I "$CI" runs xrl/rpi-homelab --since 2026-10-01 [--sample 30]
python3 -I "$CI" project --owner xrl [--included 2000]
```

## Method

- **Billed minutes come only from `gh api /users/<owner>/settings/billing/usage`**, filtered to `product == "actions"` and `unitType == "Minutes"`. Actions storage (`GigabyteHours`) shares the product; counting it overstated November by 373 (2026-11-25). `usage` lists storage separately, in GB-hours.
- **Public repos cost no minutes.** The report still lists their minutes; `usage` marks them free. Private repos, and deleted ones whose visibility returns 404, draw on the plan's included minutes (Free: 2,000/month, resets on the 1st).
- **Job count drives cost.** Each job bills at least one rounded-up minute, so twenty 10-second jobs cost 20 minutes. The runs API carries no minutes: `runs` samples `/repos/<r>/actions/runs/<id>/jobs?filter=all` across (workflow, week) strata, bills each job `ceil` minutes (skipped and self-hosted jobs free, jobs a re-run carried over counted once), and scales each stratum's mean to its run count. Its `billed` column is the usage report's actual minutes for that repo; trust it over the estimate, and use the estimate to split the bill across workflows and events.
- **Report minutes per merged PR per week, not raw totals.** More PRs is fine; waste per task is not (owner rule: no egregious, lazy waste). Merged PRs come from the search API (`is:pr is:merged merged:>=`).
- **Project at the trailing 7-day rate.** `project` adds the complete days of the month to the rate over the 7 days before today times the days left including today, and names the day the included minutes run out.

## Waste checklist

Price each finding in minutes/month from the `runs` output: runs/week of the pattern × minutes/run × 4.3.

- Push-to-main re-runs of checks the PR already passed (`[push]` rows of a PR-gating workflow).
- No `concurrency` with `cancel-in-progress` on PR workflows, so superseded pushes run to completion.
- Runs on draft PRs.
- Missing `paths` filters: the workflow runs on PRs that touch none of its inputs.
- Work split into many short jobs, each paying the one-minute floor.
- Long-held jobs: probes, polling, sleeps waiting on something else.
- Schedules (`[schedule]` rows).
- Re-runs (`reruns` = runs with `run_attempt > 1`).

## Boundaries

Read-only. Never re-run, cancel or edit workflows from this skill; each fix goes to the repo owner as a card carrying its minutes/month. This skill answers on demand: a standing spend alarm is a CI job or alert rule, not an agent told to look ([LAWS.md §60](../../LAWS.md#60-separate-judgement-from-mechanics)).
