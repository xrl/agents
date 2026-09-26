#!/usr/bin/env bash
# Full token/cost accounting for pi runs, per worktree: the parent driver sessions plus every
# pi-subagents child (verifiers, reviewers, fact-checkers), which run as separate processes and
# never appear in the driver's own log. Reads ~/.pi/agent/sessions/<slug>/, so it still works after
# the worktree itself has been removed.
#
#   pi-usage.sh <worktree-path>...            exact worktrees
#   pi-usage.sh --prefix <path-prefix>        every session dir whose worktree path starts with it
#                                             (e.g. /Users/xavier/code/dekopon/vm-runner catches the
#                                             primary checkout and every vm-runner-* worktree)
#   add --since YYYY-MM-DD to count only sessions/children modified on or after that day
#
# ccusage (`ccusage pi daily`) is right for whole-machine daily totals; it groups children by
# filename (`lane-verifier_transcript`, `session`) across projects, so it cannot attribute them
# to one effort. Costs are pi's own `usage.cost` figures.
set -euo pipefail
exec python3 - "$@" <<'PY'
import json, os, sys, glob, datetime

root = os.path.expanduser("~/.pi/agent/sessions")
args = sys.argv[1:]
since = None
if "--since" in args:
    i = args.index("--since"); since = datetime.datetime.fromisoformat(args[i + 1]).timestamp(); del args[i:i + 2]

def slug(path):
    return "--" + os.path.abspath(path).strip("/").replace("/", "-") + "--"

if args[:1] == ["--prefix"]:
    pre = slug(args[1])[:-2]
    dirs = sorted(d for d in os.listdir(root) if d.startswith(pre))
else:
    dirs = [slug(p) for p in args]
if not dirs:
    sys.exit("usage: pi-usage.sh <worktree>... | --prefix <path> [--since YYYY-MM-DD]")

def recent(path):
    return since is None or os.path.getmtime(path) >= since

rows, tot = [], dict(ps=0, pin=0, pcr=0, pout=0, pcost=0.0, cn=0, ccost=0.0)
for d in dirs:
    base = os.path.join(root, d)
    if not os.path.isdir(base):
        rows.append((d, None)); continue
    r = dict(ps=0, pin=0, pcr=0, pout=0, pcost=0.0, cn=0, ccost=0.0)
    for f in glob.glob(os.path.join(base, "*.jsonl")):
        if not recent(f): continue
        r["ps"] += 1
        for line in open(f, encoding="utf-8", errors="replace"):
            try: e = json.loads(line)
            except ValueError: continue
            m = e.get("message") or {}
            if e.get("type") == "message" and m.get("role") == "assistant" and m.get("usage"):
                u = m["usage"]
                r["pin"] += u.get("input", 0); r["pcr"] += u.get("cacheRead", 0); r["pout"] += u.get("output", 0)
                r["pcost"] += (u.get("cost") or {}).get("total", 0) or 0
    for f in glob.glob(os.path.join(base, "subagent-artifacts", "*_meta.json")):
        if not recent(f): continue
        try: u = json.load(open(f)).get("usage") or {}
        except ValueError: continue
        r["cn"] += 1; r["ccost"] += u.get("cost", 0) or 0
    for k in tot: tot[k] += r[k]
    rows.append((d, r))

print(f"{'worktree (session dir)':<60} {'drv':>3} {'input':>9} {'cacheRd':>10} {'output':>8} {'driver$':>8} {'kids':>4} {'kids$':>7} {'total$':>8}")
for d, r in rows:
    if r is None:
        print(f"{d:<60} (no pi sessions)"); continue
    print(f"{d:<60} {r['ps']:>3} {r['pin']:>9,} {r['pcr']:>10,} {r['pout']:>8,} {r['pcost']:>8.2f} {r['cn']:>4} {r['ccost']:>7.2f} {r['pcost']+r['ccost']:>8.2f}")
if len(rows) > 1:
    t = tot
    print(f"{'TOTAL':<60} {t['ps']:>3} {t['pin']:>9,} {t['pcr']:>10,} {t['pout']:>8,} {t['pcost']:>8.2f} {t['cn']:>4} {t['ccost']:>7.2f} {t['pcost']+t['ccost']:>8.2f}")
PY
