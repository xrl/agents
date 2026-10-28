#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["websockets>=15,<17", "jsonschema>=4.23,<5"]
# ///
"""Current Codex Cloud CLI. Auto-loads Pi OAuth; never invokes the codex CLI.

All output is JSON. Global flags work before or after subcommands. --write is a
mechanical guard, NOT authorization. --dry-run constructs requests without auth,
browser access or network. See ../SKILL.md for authority and safety boundaries.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
import time
import uuid

import auth
import catalog
from transport import BASE, MAX_BODY, CloudError, Http, connect_rpc, credential_secrets, paged, redact, safe_text, unique_object


class _OutputError(Exception):
    """Stop workflow/error reporting when stdout itself is unusable."""


class Context:
    def __init__(self, args):
        self.args, self.token, self.account, self.browser_headers = args, None, None, None
        self.receipt = {}
        self.deadline = None

    def credentials(self):
        if self.token is None:
            self.token, self.account = auth.load_auth(self.args.auth_file)
        return self.token, self.account

    def http(self, browser=True):
        token, account = self.credentials()
        if browser and self.browser_headers is None and self.args.browser_session:
            self.browser_headers = auth.borrow_browser_cookies(self.args.browser_session, account)
        return Http(token, account, self.browser_headers if browser else None, timeout=self.args.timeout)

    def rpc(self):
        token, account = self.credentials()
        return connect_rpc(token, account, timeout=self.args.timeout, deadline=self.deadline)

    def guard(self, mutation):
        if mutation and not (self.args.write or self.args.dry_run):
            raise CloudError("This operation changes remote state/consumes compute; require --write after user authorization, or --dry-run")

    def call(self, rpc, method, params):
        mutation = method not in catalog.READ_METHODS
        self.guard(mutation)
        catalog.validate_rpc(method, params)
        return rpc.call(method, params, mutation=mutation)

    def emit(self, value, *, error=False):
        secrets = credential_secrets(self.token or "", self.browser_headers)
        value = workflow_output(self.args, redact(value, secrets, self.args.show_secrets))
        def encode():
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        text = encode()
        if len(text.encode()) > self.args.max_output_bytes:
            if not error:
                raise CloudError("Output exceeds --max-output-bytes; request a smaller page or use the summary view",
                                 outcome="response-received", receipt=self.receipt)
            receipt = value.get("receipt")
            if isinstance(receipt, dict):
                compact = {key: item for key, item in receipt.items() if key in (
                    "thread_id", "turn_id", "client_message_id", "stage", "threadId", "turnId",
                    "clientUserMessageId", "method", "completed_calls",
                )}
                if compact and compact != receipt:
                    value.update(receipt=compact, receipt_compacted=True)
            text = encode()
            if len(text.encode()) > self.args.max_output_bytes:
                value["error"] = value["error"][:400]
                while len(json.dumps(value["error"], ensure_ascii=False).encode()) > 400:
                    value["error"] = value["error"][:len(value["error"]) // 2]
                value["error_truncated"] = True
                text = encode()
            if len(text.encode()) > self.args.max_output_bytes:
                value.update(receipt=None, receipt_omitted=True, output_bound_reason="Reconciliation receipt exceeds --max-output-bytes")
                text = encode()
        try:
            print(text, flush=True)
        except (OSError, ValueError) as error:
            raise _OutputError from error


def summarize(record, fields):
    if not isinstance(record, dict):
        raise CloudError("Expected an object in workflow response", outcome="read-failed")
    fields = set(fields.split()) | {"id", "status", "error", "code", "outcome", "receipt"}
    result = {key: value for key, value in record.items()
              if key in fields or key.endswith(("Id", "_id", "Cursor", "_cursor"))}
    if len(result) != len(record):
        result["details_omitted"] = True
    for key in ("preview", "description", "text", "aggregatedOutput"):
        if isinstance(result.get(key), str) and len(result[key]) > 800:
            result[key] = result[key][:800]
            result.setdefault("truncated_fields", []).append(key)
    return result


def workflow_output(args, value):
    """Summarize only named workflows; raw APIs, errors and receipts stay intact."""
    if args.full or args.dry_run or not isinstance(value, dict) or "error" in value:
        return value
    group, action = getattr(args, "group", None), getattr(args, "action", None)
    fields = None
    if group == "environments" and action in ("list", "show"):
        fields = "name description scope revision created_at updated_at"
    elif group == "models":
        fields = "model displayName description isDefault hidden"
    elif group == "jobs":
        if action in ("list", "get", "resume"):
            fields = "name preview createdAt updatedAt gitInfo source"
        elif action == "turns" and args.view != "full":
            fields = "startedAtMs completedAtMs"
        elif action == "continue" and "result" in value:
            result = value["result"]
            return {**value, "result": {**result, "turn": summarize(result["turn"], "")}}
        elif action == "logs":
            def item_entry(entry):
                item = summarize(entry["item"], "type text summary command cwd exitCode aggregatedOutput changes")
                if "changes" in item:
                    item["changes"] = [summarize(change, "path kind") for change in item["changes"]]
                return {**entry, "item": item}
            if "data" in value:
                return {**value, "data": [item_entry(entry) for entry in value["data"]]}
            return item_entry(value) if "item" in value else value
    if fields is None:
        return value
    if "data" in value:
        return {**value, "data": [summarize(row, fields) for row in value["data"]]}
    if "thread" in value:
        return {**value, "thread": summarize(value["thread"], fields)}
    return summarize(value, fields)


def read_json(spec):
    if spec is None:
        return {}
    try:
        text = read_text(spec[1:]) if spec.startswith("@") else spec
        if len(text.encode()) > MAX_BODY:
            raise CloudError("JSON input exceeds 4 MiB")
        return json.loads(text, object_pairs_hook=unique_object)
    except json.JSONDecodeError as error:
        raise CloudError(f"Invalid JSON: {error.msg} at line {error.lineno}, column {error.colno}") from error



def read_text(path):
    if path == "-":
        text = sys.stdin.read(MAX_BODY + 1)
    else:
        try:
            with pathlib.Path(path).expanduser().open(encoding="utf-8") as source:
                text = source.read(MAX_BODY + 1)
        except (OSError, UnicodeError) as error:
            raise CloudError(f"Cannot read input file ({type(error).__name__}, errno={getattr(error, 'errno', None)})") from error
    if len(text.encode()) > MAX_BODY:
        raise CloudError("Input exceeds 4 MiB")
    return text


def request_plan(method, params):
    catalog.validate_rpc(method, params)
    return {"transport": "rpc", "method": method, "params": params, "mutation": method not in catalog.READ_METHODS}


def do_rpc(ctx, method, params):
    plan = request_plan(method, params)
    ctx.guard(plan["mutation"])
    if ctx.args.dry_run:
        return {"dry_run": True, "requests": [plan]}
    if plan["mutation"]:
        ctx.receipt = {"method": method, **{key: params[key] for key in ("threadId", "turnId", "clientUserMessageId") if params and key in params}}
    with ctx.rpc() as rpc:
        return ctx.call(rpc, method, params)


def do_http(ctx, operation, method, path_params=None, query=None, body=None):
    entry, path = catalog.http_path(operation, {} if path_params is None else path_params, {} if query is None else query)
    if method not in entry["methods"]:
        raise CloudError(f"{operation} supports only: {', '.join(entry['methods'])}")
    ctx.guard(method != "GET")
    if method == "GET" and body is not None:
        raise CloudError("GET request cannot carry a body")
    if entry.get("sensitive") and method == "GET" and not (ctx.args.show_secrets or ctx.args.dry_run):
        raise CloudError("Credential/vault/identity route requires explicit --show-secrets and user authorization")
    if ctx.args.dry_run:
        return {"dry_run": True, "transport": "http", "method": method, "path": path,
                "body": "<sensitive body omitted>" if entry.get("sensitive") and not ctx.args.show_secrets else body}
    return ctx.http(browser=not operation.startswith("legacy-")).request(method, path, body, binary=entry.get("response") == "binary")


def environment_list(ctx):
    if ctx.args.dry_run:
        return {"dry_run": True, "requests": [{"method": "GET", "path": catalog.http_path("environment-configs", {},
                {"scope": scope, "limit": 100, "omitDraft": "true"})[1]} for scope in ("user", "workspace")]}
    http = ctx.http()
    found = {}
    for scope in ("user", "workspace"):
        def fetch(cursor):
            query = {"scope": scope, "limit": 100, "omitDraft": "true"}
            if cursor is not None:
                query["cursor"] = cursor
            return http.request("GET", catalog.http_path("environment-configs", {}, query)[1])
        for item in paged(fetch, cursor_key="next_cursor", max_pages=ctx.args.max_pages):
            found[item["id"]] = item
    return {"data": list(found.values())}


def resolve_environment(ctx, args):
    ident = args.environment_id
    if args.environment:
        if ctx.args.dry_run:
            raise CloudError("Offline --dry-run needs --environment-id; resolving a name would require network access")
        rows = environment_list(ctx)["data"]
        matches = [row for row in rows if row["name"] == args.environment or row["id"] == args.environment]
        if len(matches) != 1:
            raise CloudError("Environment name must resolve to exactly one published config")
        ident = matches[0]["id"]
    if not ident or not re.fullmatch(r"(?:[A-Za-z0-9_-]+~)?asenvcfg_[A-Za-z0-9_-]+", ident):
        raise CloudError("Expected a current asenvcfg_ environment-config ID, not a legacy environment/version/runtime ID")
    return ident


EFFORT_HELP = ("Reasoning effort, checked against model/list before any write (omitted: the model default). "
               "--dry-run shows the params and stays offline: it does not call model/list.")


def check_effort(ctx, model, effort):
    """Refuse an effort the model does not advertise; the server silently accepts any value."""
    if effort is None or ctx.args.dry_run:
        return
    rows = do_rpc(ctx, "model/list", {"limit": 100}).get("data", [])
    row = next((r for r in rows if (r.get("model") == model if model else r.get("isDefault"))), None)
    if row is None:
        raise CloudError(f"model/list has no {'model ' + repr(model) if model else 'default model'} to check --effort against")
    supported = [o if isinstance(o, str) else o.get("reasoningEffort") for o in row.get("supportedReasoningEfforts", [])]
    if effort not in supported:
        raise CloudError(f"--effort {effort!r} is not supported by {row.get('model')}; supported: {', '.join(map(str, supported))}")


def creation_requests(args, environment_id):
    prompt = read_text(args.prompt_file)
    if not prompt.strip():
        raise CloudError("Prompt must not be empty")
    start = {"threadSource": "user", "environments": [{"environmentConfigId": environment_id}],
             "deferredEnvironment": True, "pluginsMcp": {"productSku": "codex"}}
    if args.model:
        start["model"] = args.model
    if args.effort:
        start["config"] = {"model_reasoning_effort": args.effort}
    steps = [request_plan("thread/start", start)]
    if args.title:
        steps.append(request_plan("thread/name/set", {"threadId": "$thread.id", "name": args.title}))
    turn = {"threadId": "$thread.id", "input": [{"type": "text", "text": prompt, "text_elements": []}],
            "clientUserMessageId": args.client_message_id or str(uuid.uuid4())}
    if args.effort:
        turn["effort"] = args.effort
    steps.append(request_plan("turn/start", turn))
    return steps


def create_job(ctx, args):
    ctx.guard(True)  # Refuse before resolving names, loading auth or reading browser cookies.
    steps = creation_requests(args, resolve_environment(ctx, args))
    check_effort(ctx, args.model, args.effort)
    if ctx.args.dry_run:
        return {"dry_run": True, "requests": steps, "note": "No task submitted; Cloud creation is source-derived, not live-mutation-verified"}
    ctx.receipt = {"stage": "before-thread-start", "environment_config_id": steps[0]["params"]["environments"][0]["environmentConfigId"],
                   "client_message_id": steps[-1]["params"]["clientUserMessageId"]}
    ctx.emit({"receipt": ctx.receipt})
    with ctx.rpc() as rpc:
        try:
            start = ctx.call(rpc, "thread/start", steps[0]["params"])
            thread = start.get("thread") if isinstance(start, dict) else None
            thread_id = thread.get("id") if isinstance(thread, dict) else None
            if not isinstance(thread_id, str) or not thread_id:
                raise CloudError("thread/start returned no valid thread ID", outcome="unknown")
            ctx.receipt.update(thread_id=thread_id, stage="thread-created", url=BASE + "/local/" + thread_id,
                               reasoning_effort=thread.get("reasoningEffort"))
            ctx.emit({"receipt": ctx.receipt})  # Durable receipt before a second side effect.
            for field, wanted, echoed in (("model", args.model, thread.get("model")),
                                          ("reasoningEffort", args.effort, thread.get("reasoningEffort"))):
                if wanted and echoed != wanted:
                    raise CloudError(f"thread/start echoed {field} {echoed!r}, requested {wanted!r}; no turn sent, thread {thread_id} kept")
            for step in steps[1:]:
                params = {**step["params"], "threadId": thread_id}
                if step["method"] == "turn/start":
                    ctx.receipt["client_message_id"] = params["clientUserMessageId"]
                result = ctx.call(rpc, step["method"], params)
                if step["method"] == "turn/start":
                    turn = result.get("turn") if isinstance(result, dict) else None
                    if not isinstance(turn, dict) or not isinstance(turn.get("id"), str):
                        raise CloudError("turn/start returned no valid turn ID; inspect the known thread before retrying", outcome="unknown")
                    ctx.receipt.update(stage="turn-admitted", turn_id=turn["id"])
            return {"receipt": ctx.receipt, "note": "Admission is not successful completion; poll this thread ID"}
        except CloudError as e:
            e.receipt = dict(ctx.receipt)
            raise


def status_snapshot(ctx, rpc, ident, turn_id=None):
    metadata = ctx.call(rpc, "thread/read", {"threadId": ident, "includeTurns": False})
    thread = metadata.get("thread", {})
    turns = ctx.call(rpc, "thread/turns/list", {"threadId": ident, "limit": 10, "sortDirection": "desc", "itemsView": "notLoaded"})
    turn = next((t for t in turns.get("data", []) if turn_id is None or t.get("id") == turn_id), None)
    if turn_id and turn is None:
        raise CloudError("Requested turn not in latest ten turns; use `jobs turns` with pagination")
    state = None if turn is None else turn.get("status")
    return {"thread_id": ident, "name": thread.get("name"), "runtime_status": thread.get("status"),
            "turn_id": None if turn is None else turn.get("id"), "turn_status": state,
            "error": None if turn is None else turn.get("error"),
            "done": state in ("completed", "failed", "interrupted"),
            "successful": state == "completed", "url": BASE + "/local/" + ident}


def wait_status(ctx, args):
    if ctx.args.dry_run:
        return {"dry_run": True, "requests": [request_plan("thread/read", {"threadId": args.id, "includeTurns": False}),
                request_plan("thread/turns/list", {"threadId": args.id, "limit": 10, "itemsView": "notLoaded"})]}
    deadline = ctx.deadline = time.monotonic() + args.deadline
    result = None
    while True:
        if result is not None and time.monotonic() >= deadline:
            raise CloudError("Wait deadline reached; job was NOT cancelled", outcome="still-running", receipt=result)
        with ctx.rpc() as rpc:
            result = status_snapshot(ctx, rpc, args.id, args.turn_id)
        if args.action == "status" or result["done"]:
            return result
        ctx.emit(result)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CloudError("Wait deadline reached; job was NOT cancelled", outcome="still-running", receipt=result)
        time.sleep(min(args.interval, remaining))
        # New connection reloads updated Pi credentials during a long wait.
        ctx.token, ctx.account = None, None


def logs(ctx, args):
    if args.follow and ctx.args.dry_run:
        return do_rpc(ctx, "thread/items/list", {"threadId": args.id, "limit": args.limit, "sortDirection": "desc"})
    deadline, seen, last_cursor = time.monotonic() + args.deadline, {}, None
    if args.follow:
        ctx.deadline = deadline
    while True:
        if args.follow and time.monotonic() >= deadline:
            return {"follow_ended": "deadline", "job_cancelled": False, "nextCursor": last_cursor}
        params = {"threadId": args.id, "limit": args.limit, "sortDirection": "desc"}
        if args.turn_id:
            params["turnId"] = args.turn_id
        if args.cursor:
            params["cursor"] = args.cursor
        result = do_rpc(ctx, "thread/items/list", params)
        if not args.follow or ctx.args.dry_run:
            return result
        last_cursor = result.get("nextCursor")
        data = result.get("data", [])
        keys = [str(entry["turnId"]) + ":" + str(entry["item"]["id"]) for entry in data]
        if seen and len(data) >= args.limit and not any(key in seen for key in keys):
            raise CloudError("Log burst exceeds newest-page window; use jobs logs with explicit cursors", outcome="read-failed")
        for entry, ident in reversed(list(zip(data, keys))):
            fingerprint = hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()
            if seen.get(ident) != fingerprint:
                ctx.emit({"thread_id": args.id, **entry})
                seen[ident] = fingerprint
        if len(seen) > 1000:
            raise CloudError("Log-follow deduplication bound reached; restart follow", outcome="read-failed")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {"follow_ended": "deadline", "job_cancelled": False, "nextCursor": result.get("nextCursor")}
        time.sleep(min(args.interval, remaining))
        ctx.token, ctx.account = None, None


def run_jobs(ctx, args):
    action = args.action
    if action == "create":
        return create_job(ctx, args)
    if action in ("status", "wait"):
        return wait_status(ctx, args)
    if action == "logs":
        return logs(ctx, args)
    if action == "list":
        params = {"archived": args.archived, "limit": args.limit, "sortKey": "updated_at", "useStateDbOnly": True,
                  "originators": ["codex_cloud", "codex_work_cca"] if args.include_children else ["codex_cloud"]}
        if ctx.args.dry_run:
            return do_rpc(ctx, "thread/list", params)
        with ctx.rpc() as rpc:
            return {"data": paged(lambda cursor: ctx.call(rpc, "thread/list", {**params, "cursor": cursor}), max_pages=ctx.args.max_pages)}
    if action == "get":
        return do_rpc(ctx, "thread/read", {"threadId": args.id, "includeTurns": False})
    if action == "turns":
        return do_rpc(ctx, "thread/turns/list", {"threadId": args.id, "limit": args.limit, "cursor": args.cursor,
                "sortDirection": "desc", "itemsView": args.view})
    if action == "diff":
        params = {"threadId": args.id, "limit": args.limit, "sortDirection": "desc"}
        if ctx.args.dry_run:
            return do_rpc(ctx, "thread/items/list", params)
        with ctx.rpc() as rpc:
            items = paged(lambda cursor: ctx.call(rpc, "thread/items/list", {**params, "cursor": cursor}), max_pages=ctx.args.max_pages)
        return {"changes": [change for entry in items if entry["item"].get("type") == "fileChange" for change in entry["item"].get("changes", [])],
                "note": "Reported patches only; nothing applied to a local checkout"}
    if action == "continue":
        ctx.guard(True)
        prompt = read_text(args.prompt_file)
        if not prompt.strip():
            raise CloudError("Prompt must not be empty")
        turn = {"threadId": args.id, "input": [{"type": "text", "text": prompt, "text_elements": []}],
                "clientUserMessageId": args.client_message_id or str(uuid.uuid4())}
        if args.effort:
            turn["effort"] = args.effort
        check_effort(ctx, None, args.effort)
        steps = [request_plan("thread/resume", {"threadId": args.id, "excludeTurns": True}), request_plan("turn/start", turn)]
        if ctx.args.dry_run:
            return {"dry_run": True, "requests": steps}
        ctx.receipt = {"thread_id": args.id, "client_message_id": steps[1]["params"]["clientUserMessageId"]}
        if args.effort:
            ctx.receipt.update(reasoning_effort=args.effort, reasoning_effort_scope="turn-only, not echoed by the server")
        try:
            with ctx.rpc() as rpc:
                ctx.emit({"receipt": ctx.receipt})
                for step in steps:
                    result = ctx.call(rpc, step["method"], step["params"])
                    ctx.receipt["stage"] = step["method"]
                turn = result.get("turn") if isinstance(result, dict) else None
                if not isinstance(turn, dict) or not isinstance(turn.get("id"), str) or not turn["id"]:
                    raise CloudError("turn/start returned no valid turn ID; inspect the known thread before retrying", outcome="unknown")
                ctx.receipt.update(stage="turn-admitted", turn_id=turn["id"])
            return {"receipt": ctx.receipt, "result": result}
        except CloudError as e:
            e.receipt = ctx.receipt
            raise
    methods = {"archive": "thread/archive", "unarchive": "thread/unarchive", "rename": "thread/name/set",
               "resume": "thread/resume", "stop": "thread/stop", "cancel": "turn/interrupt", "delete": "thread/delete"}
    params = {"threadId": args.id}
    if action == "rename":
        params["name"] = args.name
    if action == "cancel":
        params["turnId"] = args.turn_id
    if action == "resume":
        params["excludeTurns"] = True
    return do_rpc(ctx, methods[action], params)


def run_api(ctx, args):
    if args.action == "list":
        data = {"sources": catalog.WEB["sources"]}
        if args.transport in ("all", "rpc"):
            data["rpc"] = catalog.rpc_entries()
        if args.transport in ("all", "http"):
            data["http"] = catalog.WEB["http"]
        return data
    if args.action == "schema":
        return catalog.params_schema(args.method)
    if args.action == "rpc":
        if args.method == "initialize":
            raise CloudError("initialize is managed by the transport; do not initialize twice")
        return do_rpc(ctx, args.method, read_json(args.params))
    if args.action == "http":
        entry = catalog.WEB["http"].get(args.operation, {})
        if entry.get("sensitive") and args.body is not None and not args.body.startswith("@") and not args.dry_run:
            raise CloudError("Sensitive HTTP bodies require @file or @- (stdin), never inline JSON")
        return do_http(ctx, args.operation, args.method, read_json(args.path_params), read_json(args.query),
                       None if args.body is None else read_json(args.body))
    if args.action == "batch":
        requests = read_json(args.requests)
        if not isinstance(requests, list) or not 1 <= len(requests) <= 50:
            raise CloudError("Batch must contain 1..50 {method, params} objects")
        if any(not isinstance(r, dict) or "method" not in r or set(r) - {"method", "params"} for r in requests):
            raise CloudError("Each batch request requires method and optional params only")
        plans = [request_plan(r["method"], r.get("params", {})) for r in requests]
        if any(p["method"] == "initialize" for p in plans):
            raise CloudError("initialize is transport-managed")
        ctx.guard(any(p["mutation"] for p in plans))
        if ctx.args.dry_run:
            return {"dry_run": True, "requests": plans}
        results = []
        try:
            with ctx.rpc() as rpc:
                for plan in plans:
                    result = ctx.call(rpc, plan["method"], plan["params"])
                    results.append({"method": plan["method"], "result": result})
                    ctx.emit(results[-1])
        except CloudError as e:
            e.receipt = {"completed_calls": len(results)}
            raise
        return {"completed_calls": len(results)}
    if args.action == "session":
        from session import run_session
        return run_session(ctx, args)
    raise CloudError("Unknown API action")


def positive(value):
    number = float(value)
    if not 0 < number <= 86400:
        raise argparse.ArgumentTypeError("must be >0 and <=86400 seconds")
    return number


def page_size(value):
    number = int(value)
    if not 1 <= number <= 100:
        raise argparse.ArgumentTypeError("must be 1..100")
    return number


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--auth-file", default="~/.pi/agent/auth.json")
    common.add_argument("--browser-session", help="Existing signed-in playwright-cli session; no automatic browser launch")
    common.add_argument("--write", action="store_true", help="Permit explicitly user-authorized mutations/compute")
    common.add_argument("--dry-run", action="store_true", help="Offline request construction only")
    common.add_argument("--show-secrets", action="store_true", help="Explicitly permit sensitive vault/identity reads/output")
    common.add_argument("--full", action="store_true", help="Full bounded workflow data instead of summaries; api commands are always raw")
    common.add_argument("--timeout", type=positive, default=30, help="Per-operation timeout including retries/backoff (seconds)")
    common.add_argument("--max-pages", type=int, choices=range(1, 21), default=5, metavar="1..20")
    common.add_argument("--max-output-bytes", type=int, choices=range(1024, MAX_BODY + 1), default=MAX_BODY, metavar="1024..4194304")
    parser = argparse.ArgumentParser(description=__doc__, parents=[common])
    groups = parser.add_subparsers(dest="group", required=True)
    env = groups.add_parser("environments").add_subparsers(dest="action", required=True)
    env.add_parser("list")
    for action in ("show", "create", "update", "delete"):
        p = env.add_parser(action)
        if action != "create":
            p.add_argument("id")
        if action in ("create", "update"):
            p.add_argument("--body", required=True, help="JSON or @file; HTTP API body, not an invented schema")
    jobs = groups.add_parser("jobs").add_subparsers(dest="action", required=True)
    p = jobs.add_parser("list")
    p.add_argument("--archived", action="store_true")
    p.add_argument("--include-children", action="store_true")
    p.add_argument("--limit", type=page_size, default=100)
    p = jobs.add_parser("create")
    env_arg = p.add_mutually_exclusive_group(required=True)
    env_arg.add_argument("--environment-id")
    env_arg.add_argument("--environment", help="Exact published config name; requires web catalog access")
    p.add_argument("--prompt-file", required=True, help="UTF-8 prompt file or - for stdin")
    p.add_argument("--model")
    p.add_argument("--effort", help=EFFORT_HELP)
    p.add_argument("--title")
    p.add_argument("--client-message-id")
    for action in ("get", "status", "wait", "logs", "turns", "diff", "archive", "unarchive", "rename", "resume", "stop", "cancel", "delete", "continue"):
        p = jobs.add_parser(action)
        p.add_argument("id")
        if action in ("status", "wait", "logs"):
            p.add_argument("--turn-id")
            p.add_argument("--deadline", type=positive, default=300 if action == "wait" else 60)
            p.add_argument("--interval", type=positive, default=10)
        if action in ("logs", "turns", "diff"):
            p.add_argument("--limit", type=page_size, default=50)
        if action in ("logs", "turns"):
            p.add_argument("--cursor")
        if action == "logs":
            p.add_argument("--follow", action="store_true", help="Bounded snapshot polling, not a resume/attach")
        if action == "turns":
            p.add_argument("--view", choices=["notLoaded", "summary", "full"], default="summary")
        if action == "rename":
            p.add_argument("name")
        if action == "cancel":
            p.add_argument("--turn-id", required=True)
        if action == "continue":
            p.add_argument("--prompt-file", required=True)
            p.add_argument("--effort", help=EFFORT_HELP + " Continue checks the default model; the effort applies to this turn only.")
            p.add_argument("--client-message-id")
    groups.add_parser("models")
    groups.add_parser("diagnose")
    api = groups.add_parser("api").add_subparsers(dest="action", required=True)
    p = api.add_parser("list")
    p.add_argument("--transport", choices=["all", "rpc", "http"], default="all")
    p = api.add_parser("schema")
    p.add_argument("method")
    p = api.add_parser("rpc")
    p.add_argument("method")
    p.add_argument("--params", default="{}", help="JSON or @file")
    p = api.add_parser("http")
    p.add_argument("operation")
    p.add_argument("--method", choices=["GET", "POST", "PATCH", "DELETE"], default="GET")
    p.add_argument("--path-params", default="{}")
    p.add_argument("--query", default="{}")
    p.add_argument("--body")
    p = api.add_parser("batch")
    p.add_argument("--requests", required=True, help="JSON array or @file; one connection, stops on failure")
    p = api.add_parser("session", help="Bidirectional JSONL session; server approval requests are surfaced, never auto-answered")
    p.add_argument("--seconds", type=positive, default=120)
    p.add_argument("--max-messages", type=int, choices=range(1, 1001), default=200, metavar="1..1000")
    return parser, common


def dispatch(ctx, args):
    if args.group == "jobs":
        return run_jobs(ctx, args)
    if args.group == "environments":
        if args.action == "list":
            return environment_list(ctx)
        return do_http(ctx, "environment-configs" if args.action == "create" else "environment-config",
                       {"show": "GET", "create": "POST", "update": "PATCH", "delete": "DELETE"}[args.action],
                       {} if args.action == "create" else {"configId": args.id},
                       body=read_json(args.body) if args.action in ("create", "update") else None)
    if args.group == "api":
        return run_api(ctx, args)
    if args.group == "models":
        return do_rpc(ctx, "model/list", {"limit": 100})
    if args.group == "diagnose":
        result = {}
        for operation in ("legacy-environments", "legacy-tasks"):
            result[operation] = do_http(ctx, operation, "GET", query={"limit": 20, "task_filter": "current"} if operation == "legacy-tasks" else {})
        return result
    raise CloudError("Unknown command")


def main(argv=None):
    parser, common = build_parser()
    globals_, rest = common.parse_known_args(argv)
    args = parser.parse_args(rest)
    vars(args).update(vars(globals_))
    ctx = Context(args)
    exit_code, emitting = 1, False
    try:
        try:
            result = dispatch(ctx, args)
            exit_code = 0
            if args.group == "jobs" and args.action == "wait" and result.get("done") and not result.get("successful"):
                exit_code = 1
            emitting = True
            ctx.emit(result)
        except CloudError as e:
            exit_code = 2 if e.outcome in ("unknown", "still-running") else 1
            ctx.emit({"error": safe_text(str(e), (ctx.token or "",)), "code": e.code,
                      "outcome": e.outcome, "receipt": e.receipt or ctx.receipt or None,
                      "retry_automatically": False}, error=True)
        except (OSError, ValueError, KeyError, TypeError, RecursionError) as e:
            if emitting and isinstance(e, OSError):
                raise  # A failed output channel cannot carry another error record.
            exit_code = 2 if ctx.receipt else 1
            # Preserve safe diagnostics, never arbitrary input values from exception reprs.
            detail = f", missing field {e.args[0]!r}" if isinstance(e, KeyError) else f", errno={e.errno}" if isinstance(e, OSError) else ""
            ctx.emit({"error": f"Local input/response error ({type(e).__name__}{detail})", "outcome": "unknown" if ctx.receipt else "not-sent",
                      "receipt": ctx.receipt or None, "retry_automatically": False}, error=True)
    except (_OutputError, OSError):
        # Prevent interpreter shutdown from retrying a failed buffered stream.
        sys.stdout = None
        try:
            print("codex-cloud: stdout write failed; do not retry mutations automatically", file=sys.stderr, flush=True)
        except (OSError, ValueError):
            sys.stderr = None  # No usable diagnostic channel remains.
        return exit_code or 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
