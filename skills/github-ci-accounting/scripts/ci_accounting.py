#!/usr/bin/env python3
"""Read-only GitHub Actions minutes accounting. Stdlib only; every call is a `gh api` GET.

usage    minutes by repo for a month (Minutes only), storage listed separately
runs     runs, billed-minutes estimate and minutes per merged PR per ISO week
project  month-to-date minutes, trailing-7-day rate, projected month-end vs included

See ../SKILL.md for the method and its limits.
"""
import argparse
import calendar
import collections
import datetime as dt
import json
import math
import subprocess
import sys
import time

RETRIES = 4
TIMEOUT = 60


class NotFound(Exception):
    pass


def gh_api(path, params=None):
    """The one seam: GET `path` through `gh api` with retry and timeout; returns parsed JSON."""
    cmd = ["gh", "api", "-X", "GET", path]
    for key, value in (params or {}).items():
        cmd += ["-f", f"{key}={value}"]
    error = ""
    for attempt in range(RETRIES):
        try:
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            error = f"timed out after {TIMEOUT}s"
        else:
            if done.returncode == 0:
                return json.loads(done.stdout)
            error = done.stderr.strip()
            if "HTTP 404" in error:
                raise NotFound(path)
        time.sleep(2 ** attempt)
    raise SystemExit(f"gh api {path} failed after {RETRIES} attempts: {error}")


def parse_time(value):
    return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


def iso_week(day):
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


# ---- usage -------------------------------------------------------------------

def usage_items(api, owner, year, month):
    payload = api(f"/users/{owner}/settings/billing/usage", {"year": year, "month": month})
    return [i for i in payload["usageItems"] if i["product"] == "actions"]


def billed_minutes(items):
    """Only Minutes; Actions storage (GigabyteHours) shares the `actions` product."""
    return [i for i in items if i["unitType"] == "Minutes"]


def visibility(api, owner, repo, cache):
    if repo not in cache:
        try:
            cache[repo] = api(f"/repos/{owner}/{repo}")["visibility"]
        except NotFound:
            cache[repo] = "unknown"
    return cache[repo]


def draws_on_quota(vis):
    """Public repos are free; private and deleted (unknown) repos draw on included minutes."""
    return vis != "public"


def usage(api, owner, month):
    year, mon = map(int, month.split("-"))
    items = usage_items(api, owner, year, mon)
    minutes = collections.Counter()
    storage = collections.Counter()
    for item in items:
        bucket = minutes if item["unitType"] == "Minutes" else storage
        bucket[item["repositoryName"]] += item["quantity"]
    cache = {}
    repos = [
        {"repo": repo, "visibility": visibility(api, owner, repo, cache), "minutes": round(q)}
        for repo, q in minutes.most_common()
    ]
    return {
        "owner": owner,
        "month": month,
        "minutes": repos,
        "quota_minutes": sum(r["minutes"] for r in repos if draws_on_quota(r["visibility"])),
        "free_minutes": sum(r["minutes"] for r in repos if not draws_on_quota(r["visibility"])),
        "storage_gb_hours": [
            {"repo": repo, "gb_hours": round(q, 1)} for repo, q in storage.most_common()
        ],
    }


def render_usage(r):
    out = [f"{r['owner']} {r['month']}: Actions minutes (unitType Minutes only)"]
    out += [f"  {m['minutes']:>6}  {m['repo']} ({m['visibility']})" for m in r["minutes"]]
    out.append(f"  {r['quota_minutes']:>6}  draws on included minutes (private + unknown)")
    out.append(f"  {r['free_minutes']:>6}  free (public)")
    out.append("Actions storage, GB-hours (not minutes)")
    out += [f"  {s['gb_hours']:>8}  {s['repo']}" for s in r["storage_gb_hours"]]
    return "\n".join(out)


# ---- runs --------------------------------------------------------------------

def paged(api, path, params, key):
    page = 1
    while True:
        payload = api(path, {**params, "per_page": 100, "page": page})
        rows = payload[key]
        yield from rows
        if len(rows) < 100:
            return
        page += 1


def week_windows(since, until):
    """Monday-aligned windows; one query each keeps every query under the runs API 1000 cap."""
    start = since
    while start <= until:
        end = min(start + dt.timedelta(days=6 - start.weekday()), until)
        yield start, end
        start = end + dt.timedelta(days=1)


def list_runs(api, repo, since, until):
    runs = []
    for start, end in week_windows(since, until):
        runs += paged(api, f"/repos/{repo}/actions/runs",
                      {"created": f"{start.isoformat()}..{end.isoformat()}"}, "workflow_runs")
    return runs


def job_minutes(job):
    """GitHub bills each job at least one rounded-up minute; skipped and self-hosted jobs are free."""
    if job["conclusion"] == "skipped" or not job.get("started_at") or not job.get("completed_at"):
        return 0
    if "self-hosted" in job.get("labels", []):
        return 0
    seconds = (parse_time(job["completed_at"]) - parse_time(job["started_at"])).total_seconds()
    return max(1, math.ceil(seconds / 60))


def run_minutes(api, repo, run_id):
    """All attempts; a later attempt re-lists the jobs it did not re-run, so count each once."""
    jobs = paged(api, f"/repos/{repo}/actions/runs/{run_id}/jobs", {"filter": "all"}, "jobs")
    unique = {(j["name"], j.get("started_at"), j.get("completed_at")): j for j in jobs}
    return sum(job_minutes(j) for j in unique.values())


def run_week(run):
    return iso_week(parse_time(run["created_at"]).date())


def pick_sample(runs, n):
    """Round-robin over (workflow, week) strata, largest first, evenly spaced inside each."""
    strata = collections.defaultdict(list)
    for run in sorted(runs, key=lambda r: r["created_at"]):
        strata[(run["name"], run_week(run))].append(run)
    order = sorted(strata, key=lambda k: (-len(strata[k]), k))
    quota = dict.fromkeys(order, 0)
    left = min(n, len(runs))
    while left:
        for key in order:
            if left and quota[key] < len(strata[key]):
                quota[key] += 1
                left -= 1
    sample = []
    for key in order:
        rows, k = strata[key], quota[key]
        sample += [rows[(i * len(rows)) // k] for i in range(k)]
    return sample


def mean(values):
    return sum(values) / len(values)


def merged_prs(api, repo, since):
    q = f"repo:{repo} is:pr is:merged merged:>={since.isoformat()}"
    weeks = collections.Counter()
    for item in paged(api, "/search/issues", {"q": q}, "items"):
        weeks[iso_week(parse_time(item["pull_request"]["merged_at"]).date())] += 1
    return weeks


def billed_by_week(api, repo, since, until):
    """Actual billed minutes for the repo from the owner's usage report, per ISO week."""
    owner, name = repo.split("/")
    weeks = collections.Counter()
    month = since.replace(day=1)
    while month <= until:
        try:
            items = billed_minutes(usage_items(api, owner, month.year, month.month))
        except NotFound:
            return weeks
        for item in items:
            day = parse_time(item["date"]).date()
            if item["repositoryName"] == name and since <= day <= until:
                weeks[iso_week(day)] += item["quantity"]
        month = (month + dt.timedelta(days=32)).replace(day=1)
    return weeks


def per_pr(minutes, prs):
    return round(minutes / prs, 1) if prs else None


def runs_report(api, repo, since, until, sample_size):
    runs = list_runs(api, repo, since, until)
    sample = pick_sample(runs, sample_size)
    by_stratum = collections.defaultdict(list)
    by_workflow = collections.defaultdict(list)
    for run in sample:
        minutes = run_minutes(api, repo, run["id"])
        by_stratum[(run["name"], run_week(run))].append(minutes)
        by_workflow[run["name"]].append(minutes)
    overall = mean([m for ms in by_workflow.values() for m in ms]) if sample else 0.0

    def price(run):
        stratum = by_stratum.get((run["name"], run_week(run)))
        if stratum:
            return mean(stratum)
        workflow = by_workflow.get(run["name"])
        return mean(workflow) if workflow else overall

    merged = merged_prs(api, repo, since)
    billed = billed_by_week(api, repo, since, until)
    weeks = collections.defaultdict(lambda: {"runs": 0, "reruns": 0, "minutes": 0.0,
                                             "by_workflow_event": collections.Counter()})
    for run in runs:
        w = weeks[run_week(run)]
        w["runs"] += 1
        w["reruns"] += run.get("run_attempt", 1) > 1
        w["minutes"] += price(run)
        w["by_workflow_event"][f"{run['name']} [{run['event']}]"] += 1
    rows = []
    for week in sorted(set(weeks) | set(merged) | set(billed)):
        w, prs = weeks[week], merged.get(week, 0)
        rows.append({
            "week": week,
            "runs": w["runs"],
            "reruns": w["reruns"],
            "merged_prs": prs,
            "est_minutes": round(w["minutes"]),
            "est_minutes_per_pr": per_pr(w["minutes"], prs),
            "billed_minutes": round(billed.get(week, 0)),
            "billed_minutes_per_pr": per_pr(billed.get(week, 0), prs),
            "by_workflow_event": dict(w["by_workflow_event"].most_common()),
        })
    return {
        "repo": repo,
        "since": since.isoformat(),
        "sampled_runs": len(sample),
        "minutes_per_run": {k: round(mean(v), 1) for k, v in sorted(by_workflow.items())},
        "weeks": rows,
    }


def render_runs(r):
    out = [f"{r['repo']} since {r['since']}: {r['sampled_runs']} runs priced from their jobs"
           " (ceil per job, per workflow and week)"]
    out += [f"  {v:>6} min/run  {k}" for k, v in r["minutes_per_run"].items()]
    out.append(f"  {'week':<9} {'runs':>5} {'reruns':>6} {'PRs':>4} {'est min':>8} {'est/PR':>7}"
               f" {'billed':>7} {'billed/PR':>9}")
    for w in r["weeks"]:
        est, bill = (("-" if v is None else v)
                     for v in (w["est_minutes_per_pr"], w["billed_minutes_per_pr"]))
        out.append(f"  {w['week']:<9} {w['runs']:>5} {w['reruns']:>6} {w['merged_prs']:>4}"
                   f" {w['est_minutes']:>8} {est:>7} {w['billed_minutes']:>7} {bill:>9}")
        out += [f"      {n:>4}  {k}" for k, n in w["by_workflow_event"].items()]
    return "\n".join(out)


# ---- project -----------------------------------------------------------------

def daily_quota_minutes(api, owner, year, month):
    cache = {}
    days = collections.Counter()
    for item in billed_minutes(usage_items(api, owner, year, month)):
        if draws_on_quota(visibility(api, owner, item["repositoryName"], cache)):
            days[parse_time(item["date"]).date()] += item["quantity"]
    return days


def project(api, owner, included, today):
    days = daily_quota_minutes(api, owner, today.year, today.month)
    window_start = today - dt.timedelta(days=7)
    if window_start.month != today.month:
        days.update(daily_quota_minutes(api, owner, window_start.year, window_start.month))
    month_start = today.replace(day=1)
    mtd = sum(q for d, q in days.items() if d >= month_start)
    complete = sum(q for d, q in days.items() if month_start <= d < today)
    rate = sum(q for d, q in days.items() if window_start <= d < today) / 7
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    remaining = days_in_month - today.day + 1
    projected = complete + rate * remaining
    result = {
        "owner": owner,
        "today": today.isoformat(),
        "month_to_date": round(mtd),
        "trailing_7_day_rate": round(rate, 1),
        "projected_month_end": round(projected),
        "included": included,
        "runs_out_on": None,
    }
    if projected > included and rate:
        out_day = today + dt.timedelta(days=max(0, math.ceil((included - complete) / rate) - 1))
        result["runs_out_on"] = out_day.isoformat()
    return result


def render_project(r):
    out = [
        f"{r['owner']} as of {r['today']} (minutes that draw on included; public repos excluded)",
        f"  month to date      {r['month_to_date']}",
        f"  trailing 7-day     {r['trailing_7_day_rate']}/day",
        f"  projected month    {r['projected_month_end']} of {r['included']} included",
    ]
    if r["runs_out_on"]:
        out.append(f"  runs out on        {r['runs_out_on']}")
    return "\n".join(out)


# ---- cli ---------------------------------------------------------------------

def main(argv=None, api=gh_api, today=None):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("usage")
    p.add_argument("--owner", default="xrl")
    p.add_argument("--month", default=today.strftime("%Y-%m"))
    p = sub.add_parser("runs")
    p.add_argument("repo")
    p.add_argument("--since", required=True, type=dt.date.fromisoformat)
    p.add_argument("--sample", type=int, default=30)
    p = sub.add_parser("project")
    p.add_argument("--owner", default="xrl")
    p.add_argument("--included", type=int, default=2000)
    args = parser.parse_args(argv)
    if args.command == "usage":
        report, render = usage(api, args.owner, args.month), render_usage
    elif args.command == "runs":
        report, render = runs_report(api, args.repo, args.since, today, args.sample), render_runs
    else:
        report, render = project(api, args.owner, args.included, today), render_project
    print(json.dumps(report, indent=2) if args.json else render(report))


if __name__ == "__main__":
    sys.exit(main())
