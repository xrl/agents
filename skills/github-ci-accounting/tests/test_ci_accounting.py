import contextlib
import datetime as dt
import io
import json
import pathlib
import subprocess
import sys
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import ci_accounting as ci

FIXTURES = json.loads((HERE / "fixtures.json").read_text())
NOV_25 = dt.date(2026, 11, 25)


def fake_api(path, params=None):
    """Recorded xrl payloads (2026-11-25), trimmed. Serves the paths the script reads."""
    params = params or {}
    if params.get("page", 1) > 1:
        return {"workflow_runs": [], "jobs": [], "items": []}
    if path == "/users/xrl/settings/billing/usage":
        return FIXTURES["usage_2026_11"] if params["month"] == 11 else {"usageItems": []}
    if path == "/repos/xrl/rpi-homelab/actions/runs":
        start, end = params["created"].split("..")
        return {"workflow_runs": [r for r in FIXTURES["runs"]
                                  if start <= r["created_at"][:10] <= end]}
    if path.startswith("/repos/xrl/rpi-homelab/actions/runs/"):
        return {"jobs": FIXTURES["jobs"][path.split("/")[-2]]}
    if path == "/search/issues":
        return {"items": FIXTURES["merged"]}
    name = path.removeprefix("/repos/xrl/")
    if name in FIXTURES["visibility"]:
        return {"visibility": FIXTURES["visibility"][name]}
    raise ci.NotFound(path)


class Usage(unittest.TestCase):
    def test_storage_is_not_minutes(self):
        r = ci.usage(fake_api, "xrl", "2026-11")
        self.assertEqual(r["minutes"], [
            {"repo": "rpi-homelab", "visibility": "private", "minutes": 811},
            {"repo": "external-secrets", "visibility": "public", "minutes": 12},
        ])
        self.assertEqual(r["quota_minutes"], 811)
        self.assertEqual(r["free_minutes"], 12)
        storage = {s["repo"]: s["gb_hours"] for s in r["storage_gb_hours"]}
        self.assertEqual(storage, {"external-secrets": 231.2, "rpi-homelab": 13.3})

    def test_deleted_repo_draws_on_quota(self):
        self.assertEqual(ci.visibility(fake_api, "xrl", "gone", {}), "unknown")
        self.assertTrue(ci.draws_on_quota("unknown"))
        self.assertFalse(ci.draws_on_quota("public"))


class Jobs(unittest.TestCase):
    def job(self, seconds, **extra):
        start = dt.datetime(2026, 11, 17, 3, 0, 0)
        end = start + dt.timedelta(seconds=seconds)
        return {"name": "j", "conclusion": "success", "labels": ["ubuntu-latest"],
                "started_at": f"{start:%Y-%m-%dT%H:%M:%SZ}",
                "completed_at": f"{end:%Y-%m-%dT%H:%M:%SZ}", **extra}

    def test_each_job_bills_at_least_one_rounded_up_minute(self):
        self.assertEqual([ci.job_minutes(self.job(s)) for s in (0, 7, 60, 61, 371)],
                         [1, 1, 1, 2, 7])

    def test_skipped_and_self_hosted_jobs_are_free(self):
        self.assertEqual(ci.job_minutes(self.job(90, conclusion="skipped")), 0)
        self.assertEqual(ci.job_minutes(self.job(90, labels=["self-hosted", "arm64"])), 0)

    def test_rerun_counts_carried_over_jobs_once(self):
        # Attempt 2 re-ran dekopon-check (90 s) and re-listed the other three jobs.
        self.assertEqual(ci.run_minutes(fake_api, "xrl/rpi-homelab", 44016503880), 5 + 2)


class Runs(unittest.TestCase):
    def report(self, sample):
        r = ci.runs_report(fake_api, "xrl/rpi-homelab", dt.date(2026, 11, 16), NOV_25, sample)
        return {w["week"]: w for w in r["weeks"]}

    def test_full_sample_prices_every_run(self):
        weeks = self.report(30)
        w47, w48 = weeks["2026-W47"], weeks["2026-W48"]
        self.assertEqual((w47["runs"], w47["reruns"], w47["est_minutes"]), (4, 1, 21))
        self.assertEqual((w48["runs"], w48["est_minutes"]), (2, 8))
        self.assertEqual((w47["merged_prs"], w48["merged_prs"]), (54, 25))
        self.assertEqual((w47["billed_minutes"], w48["billed_minutes"]), (684, 127))
        self.assertEqual(w47["billed_minutes_per_pr"], 12.7)
        self.assertEqual(w48["billed_minutes_per_pr"], 5.1)
        self.assertEqual(w47["by_workflow_event"], {
            "Render configuration [pull_request]": 2,
            "Render configuration [push]": 1,
            "Dekopon probe [push]": 1,
        })

    def test_partial_sample_scales_by_workflow(self):
        # Two samples: one Render run (5 min) and one probe (4 min), both W47.
        # Unsampled W48 runs fall back to their workflow's mean.
        weeks = self.report(2)
        self.assertEqual(weeks["2026-W47"]["est_minutes"], 3 * 5 + 4)
        self.assertEqual(weeks["2026-W48"]["est_minutes"], 5 + 4)

    def test_week_windows_are_monday_aligned(self):
        windows = list(ci.week_windows(dt.date(2026, 11, 18), NOV_25))
        self.assertEqual(windows, [(dt.date(2026, 11, 18), dt.date(2026, 11, 22)),
                                   (dt.date(2026, 11, 23), NOV_25)])


class Project(unittest.TestCase):
    def test_trailing_week_rate_projects_month_end(self):
        r = ci.project(fake_api, "xrl", 1000, NOV_25)
        # Complete days before the 25th: 755. Trailing 11-18..11-24: 634 / 7.
        self.assertEqual(r["month_to_date"], 811)
        self.assertEqual(r["trailing_7_day_rate"], 90.6)
        self.assertEqual(r["projected_month_end"], round(755 + 634 / 7 * 6))
        self.assertEqual(r["runs_out_on"], "2026-11-27")

    def test_no_run_out_under_included(self):
        self.assertIsNone(ci.project(fake_api, "xrl", 2000, NOV_25)["runs_out_on"])

    def test_early_month_window_reads_previous_month(self):
        r = ci.project(fake_api, "xrl", 2000, dt.date(2026, 12, 2))
        # Window 11-25..12-01 holds only 11-25's 56 minutes.
        self.assertEqual((r["month_to_date"], r["trailing_7_day_rate"]), (0, 8.0))
        self.assertEqual(r["projected_month_end"], 8 * 30)  # 12-02..12-31


class Cli(unittest.TestCase):
    def test_json_usage(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ci.main(["--json", "usage", "--month", "2026-11"], api=fake_api, today=NOV_25)
        self.assertEqual(json.loads(out.getvalue())["quota_minutes"], 811)

    def test_gh_api_is_a_get_that_retries_then_stops_on_404(self):
        flaky = [subprocess.TimeoutExpired("gh", 60),
                 subprocess.CompletedProcess([], 0, stdout='{"ok": 1}', stderr="")]
        with mock.patch.object(ci.subprocess, "run", side_effect=flaky) as run, \
                mock.patch.object(ci.time, "sleep"):
            self.assertEqual(ci.gh_api("/x", {"a": 1}), {"ok": 1})
        self.assertEqual(run.call_args.args[0], ["gh", "api", "-X", "GET", "/x", "-f", "a=1"])
        missing = subprocess.CompletedProcess([], 1, stdout="", stderr="gh: Not Found (HTTP 404)")
        with mock.patch.object(ci.subprocess, "run", return_value=missing) as run, \
                mock.patch.object(ci.time, "sleep"):
            with self.assertRaises(ci.NotFound):
                ci.gh_api("/gone")
        self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
