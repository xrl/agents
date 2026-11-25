import contextlib
import datetime as dt
import io
import json
import pathlib
import re
import subprocess
import sys
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import ci_accounting as ci

FIXTURES = json.loads((HERE / "fixtures.json").read_text())
NOV_25 = dt.date(2026, 11, 25)


USAGE = "/users/xrl/settings/billing/usage"


def make_api(usage=None, missing=(), serve=None):
    """Recorded xrl payloads (2026-11-25), trimmed. Serves the paths the script reads.
    `usage` replaces November's usage items, `missing` paths 404, `serve` answers a path itself."""
    november = FIXTURES["usage_2026_11"]["usageItems"] if usage is None else usage

    def api(path, params=None):
        params = params or {}
        if path in missing:
            raise ci.NotFound(path)
        if serve and path in serve:
            return serve[path](params)
        if params.get("page", 1) > 1:
            return {"workflow_runs": [], "jobs": [], "items": []}
        if path == USAGE:
            return {"usageItems": november if params["month"] == 11 else []}
        if re.fullmatch(r"/repos/xrl/[^/]+/actions/runs", path):
            start, end = params["created"].split("..")
            return {"workflow_runs": [r for r in FIXTURES["runs"]
                                      if start <= r["created_at"][:10] <= end]}
        if re.fullmatch(r"/repos/xrl/[^/]+/actions/runs/\d+/jobs", path):
            return {"jobs": FIXTURES["jobs"][path.split("/")[-2]]}
        if path == "/search/issues":
            return {"items": FIXTURES["merged"]}
        name = path.removeprefix("/repos/xrl/")
        if name in FIXTURES["visibility"]:
            return {"visibility": FIXTURES["visibility"][name]}
        raise ci.NotFound(path)
    return api


fake_api = make_api()


def linux(day, quantity, repo="rpi-homelab", sku="Actions Linux"):
    return {"date": f"{day}T03:00:00Z", "product": "actions", "sku": sku,
            "unitType": "Minutes", "quantity": quantity, "repositoryName": repo}


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

    def test_other_runner_skus_are_listed_not_counted(self):
        api = make_api(usage=FIXTURES["usage_2026_11"]["usageItems"]
                       + [linux("2026-11-20", 40, sku="Actions macOS 3-core")])
        r = ci.usage(api, "xrl", "2026-11")
        self.assertEqual(r["quota_minutes"], 811)
        self.assertEqual(r["unnormalized_minutes"], {"Actions macOS 3-core": 40})
        self.assertIn("Actions macOS 3-core minutes: not normalized; check GitHub's multipliers",
                      ci.render_usage(r))

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
        # Attempt 2 re-ran dekopon-check (90 s) and re-listed the other three under new ids.
        self.assertEqual(ci.run_minutes(fake_api, "xrl/rpi-homelab", 44016503880), 5 + 2)

    def test_distinct_jobs_with_one_name_and_timestamps_both_bill(self):
        jobs = [{**self.job(90), "id": 1, "run_attempt": 1},
                {**self.job(90), "id": 2, "run_attempt": 1}]
        self.assertEqual([j["id"] for j in ci.billable_jobs(jobs)], [1, 2])


class Runs(unittest.TestCase):
    def report(self, sample, api=fake_api, repo="xrl/rpi-homelab"):
        return ci.runs_report(api, repo, dt.date(2026, 11, 16), NOV_25, sample)

    def weeks(self, sample):
        return {w["week"]: w for w in self.report(sample)["weeks"]}

    def test_full_sample_prices_every_run(self):
        r = self.report(30)
        # Newest sampled week prices each workflow: W48's 33 s checks job, 6 min probe.
        self.assertEqual(r["minutes_per_run"],
                         {"Dekopon probe": 7.0, "Render configuration": 1.0})
        weeks = {w["week"]: w for w in r["weeks"]}
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

    def test_partial_sample_takes_newest_week_and_scales_by_workflow(self):
        # Two samples, both W48: Render (1 min) and probe (7 min).
        # Unsampled W47 runs fall back to their workflow's mean.
        weeks = self.weeks(2)
        self.assertEqual(weeks["2026-W48"]["est_minutes"], 1 + 7)
        self.assertEqual(weeks["2026-W47"]["est_minutes"], 3 * 1 + 7)

    def test_public_repo_bills_nothing(self):
        r = ci.runs_report(fake_api, "xrl/external-secrets", dt.date(2026, 11, 1), NOV_25, 30)
        self.assertEqual({w["billed_minutes"] for w in r["weeks"]}, {0})

    def test_missing_usage_report_fails_loudly(self):
        with self.assertRaises(ci.NotFound):
            self.report(30, api=make_api(missing={USAGE}))

    def test_runs_listed_twice_count_once(self):
        run = FIXTURES["runs"][0]
        api = make_api(serve={"/repos/xrl/rpi-homelab/actions/runs":
                              lambda params: {"workflow_runs": [run]}})
        self.assertEqual(ci.list_runs(api, "xrl/rpi-homelab", dt.date(2026, 11, 16), NOV_25),
                         [run])

    def test_week_windows_are_monday_aligned(self):
        windows = list(ci.week_windows(dt.date(2026, 11, 18), NOV_25))
        self.assertEqual(windows, [(dt.date(2026, 11, 18), dt.date(2026, 11, 22)),
                                   (dt.date(2026, 11, 23), NOV_25)])


class Project(unittest.TestCase):
    def test_trailing_rates_project_month_end(self):
        r = ci.project(fake_api, "xrl", 1000, NOV_25)
        # Complete days before the 25th: 755. 11-18..11-24: 634 / 7; 11-22..11-24: 243 / 3.
        self.assertEqual(r["month_to_date"], 811)
        self.assertFalse(r["exhausted"])
        self.assertEqual(r["trailing"], {
            "7_day": {"rate": 90.6, "projected_month_end": round(755 + 634 / 7 * 6),
                      "runs_out_on": "2026-11-27"},
            "3_day": {"rate": 81.0, "projected_month_end": 755 + 81 * 6,
                      "runs_out_on": "2026-11-28"},
        })

    def test_no_run_out_under_included(self):
        r = ci.project(fake_api, "xrl", 2000, NOV_25)
        self.assertEqual({t["runs_out_on"] for t in r["trailing"].values()}, {None})

    def test_projection_never_below_observed_usage(self):
        r = ci.project(make_api(usage=[linux("2026-11-25", 1500)]), "xrl", 2000, NOV_25)
        self.assertEqual(r["trailing"]["7_day"]["rate"], 0)
        self.assertEqual(r["trailing"]["7_day"]["projected_month_end"], 1500)
        self.assertFalse(r["exhausted"])

    def test_already_exhausted_regardless_of_rate(self):
        r = ci.project(make_api(usage=[linux("2026-11-25", 1500)]), "xrl", 1000, NOV_25)
        self.assertTrue(r["exhausted"])
        self.assertEqual({t["runs_out_on"] for t in r["trailing"].values()}, {None})
        self.assertIn("already exhausted", ci.render_project(r))

    def test_early_month_window_reads_previous_month(self):
        r = ci.project(fake_api, "xrl", 2000, dt.date(2026, 12, 2))
        # Window 11-25..12-01 holds only 11-25's 56 minutes.
        t = r["trailing"]["7_day"]
        self.assertEqual((r["month_to_date"], t["rate"]), (0, 8.0))
        self.assertEqual(t["projected_month_end"], 8 * 30)  # 12-02..12-31


class Paging(unittest.TestCase):
    def test_incomplete_results_fail(self):
        api = make_api(serve={"/search/issues":
                              lambda params: {"incomplete_results": True, "items": []}})
        with self.assertRaises(SystemExit):
            ci.merged_prs(api, "xrl/rpi-homelab", dt.date(2026, 11, 16))

    def test_result_cap_warns(self):
        page = [FIXTURES["merged"][0]] * 100
        api = make_api(serve={"/search/issues": lambda params: {"items": page}})
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rows = list(ci.paged(api, "/search/issues", {"q": "x"}, "items"))
        self.assertEqual(len(rows), ci.RESULT_CAP)
        self.assertIn("reached the 1000-result cap", err.getvalue())


class Cli(unittest.TestCase):
    def test_sample_must_be_positive(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            ci.main(["runs", "xrl/rpi-homelab", "--since", "2026-11-16", "--sample", "-1"],
                    api=fake_api, today=NOV_25)

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
        down = subprocess.CompletedProcess([], 1, stdout="", stderr="TLS handshake timeout")
        with mock.patch.object(ci.subprocess, "run", return_value=down), \
                mock.patch.object(ci.time, "sleep") as sleep:
            with self.assertRaises(SystemExit):
                ci.gh_api("/down")
        self.assertEqual(sleep.call_count, ci.RETRIES - 1)


if __name__ == "__main__":
    unittest.main()
