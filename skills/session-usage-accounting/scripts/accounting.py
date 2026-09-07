"""Read-only accounting primitives; no discovery, network, writes, or CLI.

Caller owns source attribution, cutoff capture, allowlist projection and coverage.
Never print raw entries. Missing/ambiguous meters raise Unknown, not numeric zero.
"""
import hashlib
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation

CATEGORIES = ("input", "output", "cacheRead", "cacheWrite")
FIELDS = CATEGORIES + ("totalTokens", "costUsd")
USD_TOLERANCE = Decimal("1e-8")


class Unknown(ValueError):
    """Incomplete or conflicting accounting evidence (safe metadata-only message)."""


def bounded_jsonl(path, byte_limit, sha256):
    """Yield JSON objects within a hashed byte prefix; exhaust before using results."""
    if type(byte_limit) is not int or byte_limit <= 0:
        raise Unknown("invalid byte boundary")
    digest = hashlib.sha256()
    remaining = byte_limit
    with open(path, "rb") as stream:
        while remaining:
            raw = stream.readline(remaining)
            if not raw or not raw.endswith(b"\n"):
                raise Unknown("truncated or partial snapshot line")
            remaining -= len(raw)
            digest.update(raw)
            try:
                entry = json.loads(raw, parse_float=Decimal)
            except (ValueError, UnicodeError):
                raise Unknown("invalid snapshot JSON") from None
            if not isinstance(entry, dict):
                raise Unknown("snapshot entry is not an object")
            yield entry
    if digest.hexdigest() != sha256:
        raise Unknown("snapshot digest mismatch")


def entry_meters(entry):
    """Return (kind, usage-or-None) pairs, never recurse into retained/copied context."""
    if not isinstance(entry, dict):
        raise Unknown("invalid session entry")
    kind = entry.get("type")
    if kind in ("compaction", "branch_summary"):
        return [(kind, entry.get("usage"))]
    if kind == "message":
        message = entry.get("message", {})
        if not isinstance(message, dict):
            raise Unknown("invalid session message")
        if message.get("role") == "assistant":
            return [("assistant", message.get("usage"))]
        if message.get("role") == "toolResult" and message.get("usage") is not None:
            raise Unknown("nested tool meter needs ownership reconciliation")
    return []


def dollars(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal, str)):
        raise Unknown("missing or invalid recorded cost")
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise Unknown("invalid recorded cost") from None
    if not number.is_finite() or number < 0:
        raise Unknown("invalid recorded cost")
    return number


def normalize(usage):
    """Strict stored Pi/workflow usage only. No native-status/provider conversion."""
    if not isinstance(usage, dict):
        raise Unknown("missing usage")
    for key in CATEGORIES:
        if type(usage.get(key)) is not int or usage[key] < 0:
            raise Unknown("missing or invalid token category")
    result = {key: usage[key] for key in CATEGORIES}
    total = sum(result.values())
    totals = [usage[key] for key in ("totalTokens", "total") if key in usage]
    if not totals or any(type(value) is not int or value != total for value in totals):
        raise Unknown("missing or inconsistent normalized total")
    if "reasoning" in usage:
        reasoning = usage["reasoning"]
        if type(reasoning) is not int or not 0 <= reasoning <= result["output"]:
            raise Unknown("reasoning is not an output subset")
    cost = usage.get("cost")
    if isinstance(cost, dict):
        recorded = dollars(cost.get("total"))
        if any(key in cost for key in CATEGORIES):
            components = sum((dollars(cost.get(key)) for key in CATEGORIES), Decimal(0))
            if abs(components - recorded) > USD_TOLERANCE:
                raise Unknown("cost component mismatch")
    else:
        recorded = dollars(cost)
    return dict(result, totalTokens=total, costUsd=recorded)


def sum_meters(meters):
    """Sum already-normalized, non-overlapping meters; never pass missing rows."""
    total = dict.fromkeys(FIELDS, 0)
    total["costUsd"] = Decimal(0)
    for meter in meters:
        for key in FIELDS:
            total[key] += meter[key]
    return total


def agrees(left, right):
    return all(left[key] == right[key] for key in FIELDS[:-1]) and abs(
        left["costUsd"] - right["costUsd"]
    ) <= USD_TOLERANCE


class UniqueMeters:
    """Alias-aware deduplication by proven identity, not matching token amounts."""

    def __init__(self):
        self.aliases = {}
        self.meters = []

    def add(self, keys, meter):
        keys = list(keys)
        if not keys or any(not isinstance(k, tuple) or len(k) < 2 or
                           any(not isinstance(part, str) or not part for part in k) for k in keys):
            raise Unknown("missing stable meter identity")
        found = {self.aliases[key] for key in keys if key in self.aliases}
        if len(found) > 1:
            raise Unknown("identity bridges previously separate charges")
        is_new = not found
        if found:
            index = found.pop()
            if not agrees(self.meters[index], meter):
                raise Unknown("conflicting duplicate meter")
        else:
            index = len(self.meters)
            self.meters.append(dict(meter))
        for key in keys:
            self.aliases[key] = index
        return is_new


def utc(value):
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        raise Unknown("missing or invalid timestamp") from None
    if stamp.tzinfo is None:
        raise Unknown("timestamp lacks timezone")
    return stamp


def workflow(root_id, launch, run, cutoff):
    """Validate one attributed snapshot; return aggregate and unmetered call IDs.

    launch is a caller-verified projection of an actual launching tool call and
    its paired result. This function cannot prove provenance from arbitrary JSON.
    """
    if not isinstance(launch, dict) or not isinstance(run, dict):
        raise Unknown("invalid workflow metadata")
    if (not root_id or launch.get("toolName") != "workflow" or
            not launch.get("toolCallId") or not launch.get("runId") or
            launch["runId"] != run.get("runId") or run.get("sessionId") != root_id):
        raise Unknown("unattributed workflow")
    if utc(run.get("updatedAt")) > utc(cutoff):
        raise Unknown("workflow snapshot newer than cutoff")
    aggregate = normalize(run.get("tokenUsage"))
    if not isinstance(run.get("agents"), list):
        raise Unknown("missing call inventory")
    seen, meters, unmetered = set(), [], []
    for agent in run["agents"]:
        if not isinstance(agent, dict):
            raise Unknown("invalid logical call metadata")
        call = agent.get("callId")
        if not isinstance(call, str) or not call or call in seen:
            raise Unknown("missing or duplicate logical call identity")
        seen.add(call)
        if agent.get("tokenUsage") is None:
            unmetered.append(call)
        else:
            meters.append(normalize(agent["tokenUsage"]))
    if not agrees(aggregate, sum_meters(meters)):
        raise Unknown("workflow aggregate/detail mismatch")
    return aggregate, unmetered
