"""Synthetic fixtures only: no production discovery or accounting scan."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import re
import tempfile
import unittest
from decimal import Decimal

SKILL = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("accounting", SKILL / "scripts/accounting.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def usage(**changes):
    result = dict(input=10, output=5, cacheRead=20, cacheWrite=3,
                  totalTokens=38, cost="0.123456", reasoning=2)
    result.update(changes)
    return result


def run_fixture():
    launch = dict(toolName="workflow", toolCallId="tool-1", runId="run-1")
    run = dict(runId="run-1", sessionId="root-1", updatedAt="2026-01-01T10:00:00Z",
               status="running", tokenUsage=usage(), agents=[
                   dict(callId="run-1:0", tokenUsage=usage(), status="done"),
                   dict(callId="run-1:1", status="running")])
    return launch, run


class AccountingTests(unittest.TestCase):
    def test_cache_and_reasoning(self):
        meter = a.normalize(usage())
        self.assertEqual(meter["totalTokens"], 38)
        self.assertEqual(meter["costUsd"], Decimal("0.123456"))
        self.assertNotIn("reasoning", meter)
        self.assertEqual(a.normalize(usage(total=38)), meter)

    def test_missing_is_not_zero(self):
        for raw in (None, {}, usage(cost=None), usage(cacheRead=None),
                    usage(totalTokens=15), usage(reasoning=6), usage(input=True),
                    usage(cost="NaN"), usage(cost=-1), usage(total=39)):
            with self.subTest(raw=raw), self.assertRaises(a.Unknown):
                a.normalize(raw)
        zero = dict.fromkeys(a.CATEGORIES, 0)
        zero.update(totalTokens=0, cost=0)
        self.assertEqual(a.normalize(zero)["costUsd"], 0)

    def test_native_status_total_is_not_normalized_total(self):
        native_status = dict(input=10, output=5, total=15)
        with self.assertRaises(a.Unknown):
            a.normalize(native_status)
        self.assertEqual(a.normalize(usage())["totalTokens"] - native_status["total"], 23)

    def test_cost_components_and_noise(self):
        cost = dict(input="0.1", output="0.02", cacheRead="0.003", cacheWrite="0.000456",
                    total="0.12345600000000001")
        a.normalize(usage(cost=cost))
        cost["total"] = "0.2"
        with self.assertRaises(a.Unknown):
            a.normalize(usage(cost=cost))
        del cost["cacheWrite"]
        with self.assertRaises(a.Unknown):
            a.normalize(usage(cost=cost))

    def test_compaction_retained_tail_not_recharged(self):
        message = dict(role="assistant", usage=usage())
        entries = [dict(type="message", message=message),
                   dict(type="compaction", usage=usage(), retainedTail=[message]),
                   dict(type="branch_summary", usage=usage()),
                   dict(type="custom_message", usage=usage())]
        meters = [a.normalize(u) for e in entries for _, u in a.entry_meters(e)]
        self.assertEqual(a.sum_meters(meters)["totalTokens"], 3 * 38)
        self.assertEqual(a.entry_meters(dict(type="compaction")), [("compaction", None)])

    def test_nested_meter_requires_ownership(self):
        with self.assertRaises(a.Unknown):
            a.entry_meters(dict(type="message", message=dict(role="toolResult", usage=usage())))

    def test_duplicates_replayed_prefix_and_mirrors(self):
        unique = a.UniqueMeters()
        meter = a.normalize(usage())
        self.assertTrue(unique.add([("response", "provider", "r1"), ("entry", "source", "e1")], meter))
        self.assertFalse(unique.add([("response", "provider", "r1"), ("entry", "mirror", "e1")], meter))
        self.assertFalse(unique.add([("entry", "mirror", "e1")], meter))
        self.assertTrue(unique.add([("response", "provider", "r2")], meter))
        self.assertEqual(a.sum_meters(unique.meters)["totalTokens"], 76)

    def test_conflicting_or_missing_identity(self):
        unique = a.UniqueMeters()
        meter = a.normalize(usage())
        unique.add([("entry", "source", "e")], meter)
        with self.assertRaises(a.Unknown):
            unique.add([("entry", "source", "e")], a.normalize(usage(cost="1")))
        for keys in ([], [("entry", "source", None)], [("response", "", "r")]):
            with self.assertRaises(a.Unknown):
                unique.add(keys, meter)
        unique.add([("entry", "other", "e")], meter)
        with self.assertRaises(a.Unknown):
            unique.add([("entry", "source", "e"), ("entry", "other", "e")], meter)

    def test_active_snapshot_counts_aggregate_once(self):
        launch, run = run_fixture()
        total, missing = a.workflow("root-1", launch, run, "2026-01-01T11:00:00Z")
        self.assertEqual(total, a.normalize(usage()))
        self.assertEqual(missing, ["run-1:1"])
        # Journal replay is not a call inventory item or an extra meter.
        run["journal"] = [dict(index=0, tokenUsage=usage())]
        self.assertEqual(a.workflow("root-1", launch, run, "2026-01-01T11:00:00Z")[0], total)

    def test_cumulative_resume_snapshots_are_not_increments(self):
        # Caller selects the latest cutoff-valid snapshot, not both as charges.
        launch, run = run_fixture()
        earlier, _ = a.workflow("root-1", launch, run, "2026-01-01T11:00:00Z")
        run["tokenUsage"] = usage(cost="0.2")
        run["agents"][0]["tokenUsage"] = usage(cost="0.2")
        later, _ = a.workflow("root-1", launch, run, "2026-01-01T11:00:00Z")
        identities = a.UniqueMeters()
        identities.add([("run", "run-1")], earlier)
        with self.assertRaises(a.Unknown):
            identities.add([("run", "run-1")], later)

    def test_attribution_requires_matching_root_launch_and_run(self):
        launch, run = run_fixture()
        for root, link, record in [
            ("other-root", launch, run), ("root-1", {}, run),
            ("root-1", dict(launch, runId="other"), run),
            ("root-1", dict(launch, toolName="workflow_status"), run),
            ("root-1", dict(launch, toolCallId=None), run),
        ]:
            with self.assertRaises(a.Unknown):
                a.workflow(root, link, record, "2026-01-01T11:00:00Z")

    def test_workflow_missing_duplicate_or_conflicting_meters(self):
        launch, original = run_fixture()
        variants = [dict(original, tokenUsage=None), dict(original, agents=None)]
        repeated = copy.deepcopy(original)
        repeated["agents"].append(copy.deepcopy(repeated["agents"][0]))
        variants.append(repeated)
        mismatch = copy.deepcopy(original)
        mismatch["agents"][0]["tokenUsage"]["cost"] = "1"
        variants.append(mismatch)
        for run in variants:
            with self.assertRaises(a.Unknown):
                a.workflow("root-1", launch, run, "2026-01-01T11:00:00Z")

    def test_cutoff_timezone_and_newer_cumulative_meter(self):
        launch, run = run_fixture()
        a.workflow("root-1", launch, run, "2026-01-01T05:00:00-05:00")
        for cutoff in ("2026-01-01T09:59:59Z", "2026-01-01T11:00:00", None):
            with self.assertRaises(a.Unknown):
                a.workflow("root-1", launch, run, cutoff)

    def test_stream_bounded_active_append_and_integrity(self):
        prefix = b'{"type":"session","id":"synthetic"}\n'
        digest = hashlib.sha256(prefix).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.jsonl"
            path.write_bytes(prefix + b'{"usage":"later-unfinished')
            self.assertEqual(list(a.bounded_jsonl(path, len(prefix), digest)),
                             [dict(type="session", id="synthetic")])
            for size, checksum in [(len(prefix) - 1, digest), (len(prefix), "wrong"),
                                   (path.stat().st_size, digest)]:
                with self.assertRaises(a.Unknown):
                    list(a.bounded_jsonl(path, size, checksum))
            path.write_bytes(b'{"private":"DO-NOT-ECHO", broken}\n')
            with self.assertRaises(a.Unknown) as error:
                list(a.bounded_jsonl(path, path.stat().st_size, digest))
            self.assertNotIn("DO-NOT-ECHO", str(error.exception))

    def test_skill_frontmatter_links_and_syntax(self):
        text = (SKILL / "SKILL.md").read_text()
        self.assertTrue(text.startswith("---\n"))
        front = dict(line.split(": ", 1) for line in text.split("---", 2)[1].strip().splitlines())
        name = front["name"]
        self.assertEqual(name, SKILL.name)
        self.assertRegex(name, r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
        self.assertLessEqual(len(name), 64)
        self.assertTrue(0 < len(front["description"]) <= 1024)
        self.assertLessEqual(len(front["compatibility"]), 500)
        for path in SKILL.rglob("*.md"):
            for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text()):
                self.assertTrue((path.parent / link).is_file(), link)
        for path in SKILL.rglob("*.py"):
            compile(path.read_text(), str(path), "exec")


if __name__ == "__main__":
    unittest.main()
