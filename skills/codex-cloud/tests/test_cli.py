import argparse
import base64
import contextlib
import hashlib
import http.server
import io
import json
import pathlib
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import codex_cloud as cli
import catalog
import session
import transport


class SocketPeer:
    """Real local WebSocket peer; no production credentials or services."""
    def __init__(self, responses):
        self.responses, self.requests, self.headers = responses, [], None

    def __enter__(self):
        from websockets.sync.server import serve
        def handler(ws):
            self.headers = ws.request.headers
            try:
                for raw in ws:
                    message = json.loads(raw)
                    self.requests.append(message)
                    if "id" not in message:
                        continue
                    response = self.responses(message)
                    if response == "disconnect":
                        ws.close()
                        return
                    ws.send(json.dumps({"id": message["id"], **response}))
            except Exception as e:
                self.error = e
        self.server = serve(handler, "127.0.0.1", 0, subprotocols=["codex-app-server"])
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.url = f"ws://127.0.0.1:{self.server.socket.getsockname()[1]}/"
        self.patch = mock.patch.object(transport, "WS_URL", self.url)
        self.patch.start()
        return self

    def __exit__(self, *_):
        self.patch.stop()
        self.server.shutdown()
        self.thread.join(timeout=5)


@contextlib.contextmanager
def http_peer(responses):
    requests, responses = [], iter(responses)

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self):
            requests.append(self.command)
            # Unread POST bytes can reset the connection instead of delivering the response.
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            status, body = next(responses)
            self.send_response(status)
            self.end_headers()
            self.wfile.write(body if isinstance(body, bytes) else json.dumps(body).encode())

        do_GET = do_POST = respond

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        with mock.patch.object(transport, "BASE", f"http://127.0.0.1:{server.server_port}"):
            yield transport.Http("fixture-token", "fixture-account", timeout=5), requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def execute(argv):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = cli.main(argv)
    return result, [json.loads(line) for line in stream.getvalue().splitlines()]


def context(**kwargs):
    base = dict(write=False, dry_run=False, auth_file="does-not-exist", browser_session=None,
                show_secrets=False, full=False, timeout=2, max_pages=5, max_output_bytes=transport.MAX_BODY)
    return cli.Context(argparse.Namespace(**{**base, **kwargs}))


class CliTests(unittest.TestCase):
    def test_auth_reloads_the_current_pi_token(self):
        def token(account, label, expiry):
            claims = {"exp": expiry, "https://api.openai.com/auth": {"chatgpt_account_id": account}}
            return "header." + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=") + "." + label
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp, "auth.json")
            for label in ("first", "second"):
                value = token("account", label, time.time()+3600)
                path.write_text(json.dumps({"openai-codex": {"access": value, "accountId": "account"}}))
                self.assertEqual(cli.auth.load_auth(path), (value, "account"))
            path.write_text(json.dumps({"openai-codex": {"access": token("account", "expired", 1), "accountId": "account"}}))
            with self.assertRaisesRegex(transport.CloudError, "expired"):
                cli.auth.load_auth(path)

    def test_missing_auth_error_retains_cause_without_credentials(self):
        with self.assertRaisesRegex(transport.CloudError, "FileNotFoundError"):
            cli.auth.load_auth("/does-not-exist/pi-auth-fixture")

    def test_cookie_redaction_preserves_noncredential_ids(self):
        secrets = transport.credential_secrets("oauth-token", {"Cookie": "oai-hlib=1; _account=account-id; __Secure-next-auth.session-token.0=private-cookie-123456789"})
        result = transport.redact({"id": "account-id~asenvcfg_123", "message": "private-cookie-123456789"}, secrets)
        self.assertEqual(result["id"], "account-id~asenvcfg_123")
        self.assertEqual(result["message"], "<redacted>")

    def test_poll_deadlines_keep_receipts_and_cursors_without_another_read(self):
        snapshot = {"thread_id": "fixture", "done": False}
        page = {"data": [], "nextCursor": "older"}
        for during_read in (False, True):
            ctx = context()
            ctx.emit = mock.Mock()
            ctx.rpc = mock.Mock(return_value=contextlib.nullcontext(object()))
            args = argparse.Namespace(id="fixture", action="wait", deadline=1, interval=10, turn_id=None)
            clock = [0, 2] if during_read else [0, .5, 2]
            with self.subTest(during_read=during_read), mock.patch.object(cli.time, "monotonic", side_effect=clock), mock.patch.object(cli.time, "sleep"):
                with mock.patch.object(cli, "status_snapshot", return_value=snapshot) as read, self.assertRaises(transport.CloudError) as raised:
                    cli.wait_status(ctx, args)
                self.assertEqual(raised.exception.outcome, "still-running")
                self.assertIs(raised.exception.receipt, snapshot)
                read.assert_called_once()
            args = argparse.Namespace(id="fixture", follow=True, limit=1, deadline=1, interval=10, turn_id=None, cursor=None)
            clock = [0, 0, 2] if during_read else [0, 0, .5, 2]
            with mock.patch.object(cli.time, "monotonic", side_effect=clock), mock.patch.object(cli.time, "sleep"):
                with mock.patch.object(cli, "do_rpc", return_value=page) as read:
                    self.assertEqual(cli.logs(ctx, args), {"follow_ended": "deadline", "job_cancelled": False, "nextCursor": "older"})
                read.assert_called_once()

    def test_follow_detects_a_newest_page_gap_before_advancing(self):
        def page(ident):
            return {"data": [{"turnId": "turn", "item": {"id": ident, "type": "agentMessage", "text": "fixture"}}], "nextCursor": "older"}
        ctx = context()
        ctx.emit = lambda _: None
        args = argparse.Namespace(id="thread", follow=True, limit=1, deadline=60, interval=1, turn_id=None, cursor=None)
        with mock.patch.object(cli, "do_rpc", side_effect=[page("old"), page("new")]), mock.patch.object(cli.time, "sleep"):
            with self.assertRaisesRegex(transport.CloudError, "Log burst"):
                cli.logs(ctx, args)

    def test_real_jsonl_session_drains_input_and_closes(self):
        def reply(req):
            return {"result": {} if req["method"] == "initialize" else {"thread": {"id": "fixture"}}}
        with tempfile.TemporaryFile(mode="w+") as source:
            source.write('{"id":"read","method":"thread/read","params":{"threadId":"fixture","includeTurns":false}}\n')
            source.seek(0)
            with SocketPeer(reply), mock.patch.object(cli.auth, "load_auth", return_value=("fixture-token", "fixture-account")), mock.patch.object(sys, "stdin", source):
                code, lines = execute(["api", "session", "--seconds", "2"])
        self.assertEqual(code, 0)
        self.assertEqual(lines[0]["kind"], "response")
        self.assertEqual(lines[-1]["session_ended"], "eof")
        self.assertFalse(lines[-1]["task_cancelled"])

    def test_catalog_covers_every_public_and_browser_method(self):
        names = {entry["method"] for entry in catalog.rpc_entries()}
        self.assertEqual(names, set(catalog.REQUESTS) | set(catalog.WEB["browser_rpc_methods"]))
        self.assertEqual(len(names), 120)
        self.assertEqual(len(catalog.WEB["http"]), 31)
        self.assertEqual(hashlib.sha256((catalog.REFERENCES / 'client-request-schema.json').read_bytes()).hexdigest(),
                         catalog.WEB['sources']['schema_sha256'])
        by_name = {entry["method"]: entry for entry in catalog.rpc_entries()}
        self.assertTrue(by_name["command/exec"]["mutation"])
        self.assertIn("emulated", by_name["config/read"]["evidence"])

    def test_catalog_and_help_need_no_auth(self):
        with mock.patch.object(cli.auth, "load_auth", side_effect=AssertionError("no auth")):
            code, lines = execute(["api", "list"])
            self.assertEqual(code, 0)
            self.assertIn("http", lines[0])

    def test_guard_fails_before_loading_auth(self):
        with mock.patch.object(cli.auth, "load_auth", side_effect=AssertionError("no auth")):
            for argv in (["jobs", "archive", "thread"], ["api", "rpc", "undocumented/change"],
                         ["api", "http", "environment-config", "--method", "DELETE", "--path-params", '{"configId":"env"}']):
                code, lines = execute(argv)
                self.assertEqual(code, 1)
                self.assertIn("--write", lines[0]["error"])

    def test_create_dry_run_is_offline_and_matches_cloud_envelope(self):
        with tempfile.TemporaryDirectory() as temp:
            prompt = pathlib.Path(temp, "prompt.txt")
            prompt.write_text("Implement the authorized change")
            with mock.patch.object(cli.auth, "load_auth", side_effect=AssertionError("no auth")), mock.patch.object(cli.auth, "borrow_browser_cookies", side_effect=AssertionError("no browser")):
                code, lines = execute(["jobs", "create", "--environment-id", "account~asenvcfg_fixture",
                                      "--prompt-file", str(prompt), "--title", "fixture", "--dry-run"])
            self.assertEqual(code, 0)
            requests = lines[0]["requests"]
            self.assertEqual([r["method"] for r in requests], ["thread/start", "thread/name/set", "turn/start"])
            params = requests[0]["params"]
            self.assertEqual(params["environments"], [{"environmentConfigId": "account~asenvcfg_fixture"}])
            self.assertTrue(params["deferredEnvironment"])
            self.assertEqual(params["pluginsMcp"], {"productSku": "codex"})
            self.assertNotIn("sandbox", params)
            self.assertNotIn("approvalPolicy", params)
            self.assertEqual(requests[-1]["params"]["input"][0]["text_elements"], [])

    def test_create_rejects_legacy_and_version_ids_offline(self):
        with tempfile.TemporaryDirectory() as temp:
            p = pathlib.Path(temp, "prompt")
            p.write_text("fixture")
            for ident in ["legacy_env", "cecfgver_version", "ccarenv_runtime"]:
                code, _ = execute(["jobs", "create", "--environment-id", ident, "--prompt-file", str(p), "--dry-run"])
                self.assertEqual(code, 1)

    def test_short_and_empty_pages_follow_cursor(self):
        pages = iter([{"data": [], "nextCursor": "a"}, {"data": [1], "nextCursor": "b"}, {"data": [2], "nextCursor": None}])
        self.assertEqual(transport.paged(lambda _: next(pages)), [1, 2])

    def test_repeated_or_exhausted_pagination_fails(self):
        for bound in (1, 3):
            with self.assertRaises(transport.CloudError):
                transport.paged(lambda _: {"data": [], "nextCursor": "same"}, max_pages=bound)

    def test_unknown_methods_default_to_write(self):
        ctx = context()
        with self.assertRaisesRegex(transport.CloudError, "--write"):
            cli.do_rpc(ctx, "future/read", {})

    def test_bad_schema_does_not_echo_sensitive_values(self):
        with self.assertRaises(transport.CloudError) as raised:
            catalog.validate_rpc("turn/start", {"threadId": 123, "input": "private-secret"})
        self.assertIn("violates", str(raised.exception))
        self.assertNotIn("private-secret", str(raised.exception))

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(transport.CloudError, "Duplicate"):
            cli.read_json('{"a":1,"a":2}')

    def test_http_path_encoding_and_exact_parameter_names(self):
        _, path = catalog.http_path("environment-config", {"configId": "one/two"}, {})
        self.assertTrue(path.endswith("one%2Ftwo"))
        for params in ({}, {"configId": ".."}, {"configId": "one", "extra": 1}):
            with self.assertRaises(transport.CloudError):
                catalog.http_path("environment-config", params, {})

    def test_sensitive_http_requires_explicit_read_authorization(self):
        code, lines = execute(["api", "http", "personal-environment-variable-value", "--path-params", '{"id":"assec_fixture"}'])
        self.assertEqual(code, 1)
        self.assertIn("--show-secrets", lines[0]["error"])

    def test_sensitive_body_omitted_from_dry_run(self):
        code, lines = execute(["api", "http", "environment-values", "--method", "POST", "--body", '{"name":"key","value":"private-secret"}', "--dry-run"])
        self.assertEqual(code, 0)
        self.assertNotIn("private-secret", json.dumps(lines))

    def test_redaction_even_in_show_secrets_mode_protects_own_token(self):
        value = transport.redact({"text": "Bearer fixture-token", "accessToken": "fixture-token"}, ("fixture-token",), True)
        self.assertNotIn("fixture-token", json.dumps(value))

    def test_idle_is_not_completion_without_terminal_turn(self):
        class Rpc:
            def call(self, method, params, mutation=False):
                return {"thread": {"name": "fixture", "status": {"type": "idle"}}} if method == "thread/read" else {"data": []}
        result = cli.status_snapshot(context(), Rpc(), "fixture")
        self.assertFalse(result["done"])
        self.assertFalse(result["successful"])

    def test_diff_uses_canonical_item_entry_envelope(self):
        class Rpc:
            def call(self, method, params, mutation=False):
                return {"data": [{"turnId": "turn", "item": {"id": "item", "type": "fileChange", "changes": [{"path": "file", "diff": "patch"}]}}], "nextCursor": None}
        ctx = context()
        @contextlib.contextmanager
        def rpc():
            yield Rpc()
        ctx.rpc = rpc
        result = cli.run_jobs(ctx, argparse.Namespace(action="diff", id="fixture", limit=10))
        self.assertEqual(result["changes"], [{"path": "file", "diff": "patch"}])

    def test_session_never_answers_unknown_approval(self):
        with self.assertRaisesRegex(transport.CloudError, "unknown server"):
            session.validate_message(context(write=True), {"id": 22, "result": {"decision": "accept"}}, {}, set())
        with self.assertRaisesRegex(transport.CloudError, "--write"):
            session.validate_message(context(), {"id": 22, "result": {"decision": "accept"}}, {}, {22})

    def test_session_ids_accept_json_strings_and_integers_but_not_booleans(self):
        for ident in ("read", 17, True, False, None, 1.5, [], {}):
            message = {"id": ident, "method": "thread/read", "params": {"threadId": "fixture"}}
            with self.subTest(ident=ident):
                if type(ident) in (str, int):
                    self.assertEqual(session.validate_message(context(), message, {}, set()), ("request", False))
                else:
                    with self.assertRaisesRegex(transport.CloudError, "string/integer id"):
                        session.validate_message(context(), message, {}, set())

    def test_session_write_request_checked_before_send(self):
        with self.assertRaisesRegex(transport.CloudError, "--write"):
            session.validate_message(context(), {"id": "one", "method": "turn/start", "params": {}}, {}, set())

    def test_real_websocket_handshake_and_read(self):
        def reply(req):
            return {"result": {} if req["method"] == "initialize" else {"thread": {"id": "fixture"}}}
        with SocketPeer(reply) as peer, mock.patch.object(cli.auth, "load_auth", return_value=("fixture-token", "fixture-account")):
            code, lines = execute(["jobs", "get", "fixture"])
            self.assertEqual(code, 0)
            self.assertEqual(lines[0]["thread"]["id"], "fixture")
            self.assertEqual([r["method"] for r in peer.requests], ["initialize", "initialized", "thread/read"])
            self.assertEqual(peer.headers["ChatGPT-Account-Id"], "fixture-account")
            self.assertIn("openai-bearer.fixture-token", peer.headers["Sec-WebSocket-Protocol"])

    def test_continue_preserves_turn_input_and_admission_or_disconnect_receipt(self):
        for disconnect in (False, True):
            def reply(req):
                if req["method"] == "turn/start":
                    return "disconnect" if disconnect else {"result": {"turn": {"id": "admitted-turn", "status": "inProgress"}}}
                return {"result": {}}
            with self.subTest(disconnect=disconnect), tempfile.TemporaryDirectory() as temp:
                prompt = pathlib.Path(temp, "prompt")
                prompt.write_text("Authorized follow-up")
                with SocketPeer(reply) as peer, mock.patch.object(cli.auth, "load_auth", return_value=("token", "account")):
                    code, lines = execute(["jobs", "continue", "known-thread", "--prompt-file", str(prompt),
                                           "--client-message-id", "stable-message", "--write"])
            requests = [r for r in peer.requests if r["method"] not in ("initialize", "initialized")]
            self.assertEqual([r["method"] for r in requests], ["thread/resume", "turn/start"])
            self.assertEqual(requests[0]["params"], {"threadId": "known-thread", "excludeTurns": True})
            self.assertEqual(requests[1]["params"], {"threadId": "known-thread", "clientUserMessageId": "stable-message",
                "input": [{"type": "text", "text": "Authorized follow-up", "text_elements": []}]})
            self.assertEqual(code, 2 if disconnect else 0)
            self.assertEqual(lines[0]["receipt"], {"thread_id": "known-thread", "client_message_id": "stable-message"})
            receipt = {**lines[0]["receipt"], "stage": "thread/resume" if disconnect else "turn-admitted"}
            if disconnect:
                self.assertEqual(lines[-1]["outcome"], "unknown")
            else:
                receipt["turn_id"] = "admitted-turn"
            self.assertEqual(lines[-1]["receipt"], receipt)

    def test_batch_preserves_completed_count_when_the_next_call_fails(self):
        def reply(req):
            return "disconnect" if req["method"] == "thread/archive" else {"result": {"thread": {"id": "fixture"}}}
        requests = [{"method": method, "params": {"threadId": "fixture"}} for method in ("thread/read", "thread/archive")]
        with SocketPeer(reply) as peer, mock.patch.object(cli.auth, "load_auth", return_value=("token", "account")):
            code, lines = execute(["api", "batch", "--requests", json.dumps(requests), "--write"])
        self.assertEqual(code, 2)
        self.assertEqual(lines[0], {"method": "thread/read", "result": {"thread": {"id": "fixture"}}})
        self.assertEqual(lines[-1]["outcome"], "unknown")
        self.assertEqual(lines[-1]["receipt"], {"completed_calls": 1})
        self.assertEqual([r["method"] for r in peer.requests].count("thread/archive"), 1)

    def test_create_disconnect_preserves_receipt_and_unknown_outcome(self):
        def reply(req):
            if req["method"] == "initialize":
                return {"result": {}}
            if req["method"] == "thread/start":
                return {"result": {"thread": {"id": "created-thread"}}}
            return "disconnect"
        with tempfile.TemporaryDirectory() as temp:
            p = pathlib.Path(temp, "prompt")
            p.write_text("fixture")
            with SocketPeer(reply), mock.patch.object(cli.auth, "load_auth", return_value=("fixture-token", "fixture-account")):
                code, lines = execute(["jobs", "create", "--environment-id", "asenvcfg_fixture", "--prompt-file", str(p), "--write"])
            self.assertEqual(code, 2)
            self.assertEqual(lines[-1]["outcome"], "unknown")
            self.assertEqual(lines[-1]["receipt"]["thread_id"], "created-thread")
            self.assertFalse(lines[-1]["retry_automatically"])
            self.assertNotIn("fixture-token", json.dumps(lines))

    def test_failed_terminal_wait_exits_nonzero(self):
        def reply(req):
            method = req["method"]
            if method == "thread/read":
                return {"result": {"thread": {"status": {"type": "idle"}}}}
            if method == "thread/turns/list":
                return {"result": {"data": [{"id": "turn", "status": "failed", "error": {"message": "fixture"}}]}}
            return {"result": {}}
        with SocketPeer(reply), mock.patch.object(cli.auth, "load_auth", return_value=("token", "account")):
            code, lines = execute(["jobs", "wait", "fixture"])
        self.assertEqual(code, 1)
        self.assertTrue(lines[-1]["done"])
        self.assertFalse(lines[-1]["successful"])

    def test_http_transient_reads_retry_three_times_with_stderr_only(self):
        logs, output = io.StringIO(), io.StringIO()
        with http_peer([(503, {"error": "fixture-token"}), (429, b"challenge"), (200, {"id": "ok"})]) as (client, requests):
            with mock.patch.object(transport.time, "sleep") as sleep, contextlib.redirect_stderr(logs), contextlib.redirect_stdout(output):
                self.assertEqual(client.request("GET", "/api/codex-cloud/v1/environment-configs"), {"id": "ok"})
        self.assertEqual(requests, ["GET"] * 3)
        self.assertEqual(sleep.call_args_list, [mock.call(.5), mock.call(1)])
        self.assertEqual(len(logs.getvalue().splitlines()), 2)
        self.assertIn("retry 3/3", logs.getvalue())
        self.assertNotIn("fixture-token", logs.getvalue())
        self.assertEqual(output.getvalue(), "")

    def test_http_permanent_rejections_never_retry(self):
        for status in (400, 401, 403, 404, 409, 422, 501):
            with self.subTest(status=status), http_peer([(status, {"message": "permanent rejection"})]) as (client, requests):
                with mock.patch.object(transport.time, "sleep") as sleep, self.assertRaises(transport.CloudError) as raised:
                    client.request("GET", "/backend-api/wham/tasks/list")
                self.assertEqual(raised.exception.code, status)
                self.assertIn("permanent rejection", str(raised.exception))
                self.assertEqual(requests, ["GET"])
                sleep.assert_not_called()

    def test_http_sent_write_failure_is_unknown_and_not_replayed(self):
        with http_peer([(503, {"error": "backend unavailable"})]) as (client, requests):
            with mock.patch.object(transport.time, "sleep") as sleep, self.assertRaises(transport.CloudError) as raised:
                client.request("POST", "/backend-api/wham/tasks", {"prompt": "fixture"})
            self.assertEqual(raised.exception.outcome, "unknown")
            self.assertEqual(raised.exception.code, 503)
            self.assertEqual(requests, ["POST"])
            sleep.assert_not_called()

    def test_http_only_proven_pre_send_write_failures_retry(self):
        for cause, expected_calls, outcome in (
            (ConnectionRefusedError("fixture refusal"), 3, "not-sent"),
            (ConnectionResetError("fixture reset"), 1, "unknown"),
            (TimeoutError("fixture timeout"), 1, "unknown"),
        ):
            client = transport.Http("token", "account", timeout=5)
            with self.subTest(cause=type(cause).__name__), mock.patch.object(client.opener, "open", side_effect=urllib.error.URLError(cause)) as request:
                with mock.patch.object(transport.time, "sleep"), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(transport.CloudError) as raised:
                    client.request("POST", "/backend-api/wham/tasks", {})
                self.assertEqual(request.call_count, expected_calls)
                self.assertEqual(raised.exception.outcome, outcome)
                self.assertIn(type(cause).__name__, str(raised.exception))
                self.assertIsNotNone(raised.exception.__cause__)

    def test_http_bad_json_does_not_retry_and_null_is_valid(self):
        with http_peer([(200, b"not json"), (200, None)]) as (client, requests):
            with mock.patch.object(transport.time, "sleep") as sleep, self.assertRaisesRegex(transport.CloudError, "JSONDecodeError"):
                client.request("GET", "/backend-api/wham/tasks/list")
            sleep.assert_not_called()
            self.assertIsNone(client.request("GET", "/backend-api/wham/tasks/list"))
            self.assertEqual(requests, ["GET", "GET"])

    def test_websocket_read_disconnect_reconnects_without_replaying_writes(self):
        calls = 0
        def reply(req):
            nonlocal calls
            if req["method"] == "initialize":
                return {"result": {}}
            calls += 1
            return "disconnect" if calls < 3 else {"result": {"thread": {"id": "fixture"}}}
        logs = io.StringIO()
        with SocketPeer(reply) as peer, mock.patch.object(cli.auth, "load_auth", return_value=("fixture-token", "account")):
            with mock.patch.object(transport.time, "sleep") as sleep, contextlib.redirect_stderr(logs):
                code, lines = execute(["jobs", "get", "fixture"])
        self.assertEqual(code, 0)
        self.assertEqual(lines[0]["thread"]["id"], "fixture")
        self.assertEqual([r["method"] for r in peer.requests].count("thread/read"), 3)
        self.assertEqual([r["method"] for r in peer.requests].count("initialize"), 3)
        self.assertEqual(sleep.call_args_list, [mock.call(.5), mock.call(1)])
        self.assertNotIn("fixture-token", logs.getvalue())

    def test_rpc_rejections_preserve_code_and_never_retry(self):
        for error_code in (-32600, -32601, -32602, -32603, 401, 409):
            socket = mock.Mock()
            socket.recv.return_value = json.dumps({"id": 1, "error": {"code": error_code, "message": "fixture-token rejected"}})
            rpc = transport.Rpc(socket, token="fixture-token", account="account")
            with self.subTest(code=error_code), mock.patch.object(transport.time, "sleep") as sleep, self.assertRaises(transport.CloudError) as raised:
                rpc.call("thread/read", {"threadId": "fixture"})
            self.assertEqual(raised.exception.code, error_code)
            self.assertIn("rejected", str(raised.exception))
            self.assertNotIn("fixture-token", str(raised.exception))
            socket.send.assert_called_once()
            sleep.assert_not_called()

    def test_rpc_sent_write_timeout_and_malformed_response_are_unknown(self):
        for response in (TimeoutError("private token"), json.dumps({"id": 1}), "[]", '{"id":1,"id":1}'):
            socket = mock.Mock()
            if isinstance(response, Exception):
                socket.recv.side_effect = response
            else:
                socket.recv.return_value = response
            with self.subTest(response=type(response).__name__), mock.patch.object(transport.time, "sleep") as sleep, self.assertRaises(transport.CloudError) as raised:
                transport.Rpc(socket, account="account").call("thread/start", {}, mutation=True)
            self.assertEqual(raised.exception.outcome, "unknown")
            socket.send.assert_called_once()
            sleep.assert_not_called()

    def test_websocket_connection_refusal_retries_before_one_write(self):
        from websockets.sync.client import connect
        attempts = 0
        def flaky_connect(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ConnectionRefusedError("fixture")
            return connect(*args, **kwargs)
        with SocketPeer(lambda _: {"result": {}}) as peer, mock.patch.object(cli.auth, "load_auth", return_value=("token", "account")):
            with mock.patch("websockets.sync.client.connect", side_effect=flaky_connect), mock.patch.object(transport.time, "sleep"), contextlib.redirect_stderr(io.StringIO()):
                code, _ = execute(["jobs", "archive", "fixture", "--write"])
        self.assertEqual(code, 0)
        self.assertEqual(attempts, 3)
        self.assertEqual([r["method"] for r in peer.requests].count("thread/archive"), 1)

    def test_websocket_auth_handshake_rejection_never_retries(self):
        from websockets.datastructures import Headers
        from websockets.exceptions import InvalidStatus
        from websockets.http11 import Response
        rejection = InvalidStatus(Response(401, "private fixture-token", Headers(), b"fixture-token"))
        with mock.patch("websockets.sync.client.connect", side_effect=rejection) as connect, mock.patch.object(transport.time, "sleep") as sleep:
            with self.assertRaises(transport.CloudError) as raised:
                with transport.connect_rpc("fixture-token", "account"):
                    self.fail("Must not connect")
        self.assertEqual(raised.exception.code, 401)
        self.assertEqual(raised.exception.outcome, "not-sent")
        self.assertNotIn("fixture-token", str(raised.exception))
        connect.assert_called_once()
        sleep.assert_not_called()

    def test_retry_exhaustion_preserves_last_failure_and_deadline(self):
        error = transport.CloudError("fixture read failure", outcome="read-failed", retryable=True)
        for timeout, attempts in ((.1, 1), (10, 3)):
            operation = mock.Mock(side_effect=error)
            with self.subTest(timeout=timeout), mock.patch.object(transport.time, "sleep"), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(transport.CloudError) as raised:
                    transport.retry("fixture", operation, timeout=timeout)
                self.assertIs(raised.exception, error)
                self.assertEqual(operation.call_count, attempts)

    def test_backoff_expiry_preserves_original_failure(self):
        failure = transport.CloudError("original timeout", retryable=True)
        attempt = mock.Mock(side_effect=failure)
        with mock.patch.object(transport.time, "monotonic", side_effect=[0, 0, 0, 2]), mock.patch.object(transport.time, "sleep"), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(transport.CloudError) as raised:
                transport.retry("fixture", attempt, timeout=1)
        self.assertIs(raised.exception, failure)
        attempt.assert_called_once()

    def test_excessive_json_nesting_rejects_locally_and_preserves_unknown_write(self):
        nested = "[" * 20000 + "0" + "]" * 20000
        with mock.patch.object(cli.auth, "load_auth", side_effect=AssertionError("no auth")):
            code, lines = execute(["api", "rpc", "thread/read", "--params", nested])
        self.assertEqual(code, 1)
        self.assertIn("RecursionError", lines[0]["error"])
        socket = mock.Mock()
        socket.recv.return_value = '{"id":1,"result":' + nested + '}'
        with self.assertRaises(transport.CloudError) as raised:
            transport.Rpc(socket).call("thread/start", {}, mutation=True)
        self.assertEqual(raised.exception.outcome, "unknown")
        self.assertIn("RecursionError", str(raised.exception))
        socket.send.assert_called_once()

    def test_discovery_summaries_keep_environment_and_model_selection_fields(self):
        for group, action, row, omitted in (
            ("environments", "list", {"id": "env", "name": "project", "published_version_id": "version", "draft": {"large": "details"}}, "draft"),
            ("models", None, {"id": "model", "model": "codex", "isDefault": True, "supportedReasoningEfforts": ["large"]}, "supportedReasoningEfforts"),
        ):
            args = context(group=group, action=action).args
            value = {"data": [row], "nextCursor": "next"}
            summary = cli.workflow_output(args, value)
            self.assertEqual(summary["nextCursor"], "next")
            self.assertNotIn(omitted, summary["data"][0])
            for key in row.keys() - {omitted}:
                self.assertEqual(summary["data"][0][key], row[key])
            args.full = True
            self.assertEqual(cli.workflow_output(args, value), value)

    def test_reconnect_consumes_the_read_retry_budget(self):
        now = [0.0]
        rpc = transport.Rpc(mock.Mock(), account="account", timeout=2)
        def reconnect(*args, **kwargs):
            now[0] += .75
            return transport.Rpc(mock.Mock())
        def sleep(seconds):
            now[0] += seconds
        failure = transport.CloudError("fixture reset", retryable=True)
        with mock.patch.object(transport.time, "monotonic", side_effect=lambda: now[0]), mock.patch.object(transport.time, "sleep", side_effect=sleep):
            with mock.patch.object(transport, "open_rpc", side_effect=reconnect), mock.patch.object(rpc, "_call", side_effect=[failure, {}]) as call, contextlib.redirect_stderr(io.StringIO()):
                rpc.call("thread/read", {})
        self.assertEqual(call.call_args.kwargs["timeout"], .75)

    def test_local_bad_requests_fail_before_auth_without_fallback(self):
        requests = (
            ["api", "http", "environment-configs", "--query", "[]"],
            ["api", "http", "environment-configs", "--path-params", "[]"],
            ["api", "batch", "--requests", '[{"params":{}}]'],
            ["api", "rpc", "thread/read", "--params", '{"threadId":12}'],
        )
        with mock.patch.object(cli.auth, "load_auth", side_effect=AssertionError("no auth")):
            for argv in requests:
                with self.subTest(argv=argv):
                    code, lines = execute(argv)
                    self.assertEqual(code, 1)
                    self.assertEqual(lines[0]["outcome"], "not-sent")

    def test_sensitive_inline_body_rejected_before_auth_but_file_allowed(self):
        with mock.patch.object(cli.auth, "load_auth", side_effect=AssertionError("no auth")):
            code, lines = execute(["api", "http", "environment-values", "--method", "POST", "--body", '{"value":"private"}', "--write"])
        self.assertEqual(code, 1)
        self.assertIn("@file", lines[0]["error"])
        self.assertNotIn("private", json.dumps(lines))
        with tempfile.TemporaryDirectory() as temp:
            body = pathlib.Path(temp, "body.json")
            body.write_text('{"value":"private"}')
            with mock.patch.object(cli.Context, "http") as http:
                http.return_value.request.return_value = {"id": "saved"}
                code, lines = execute(["api", "http", "environment-values", "--method", "POST", "--body", "@" + str(body), "--write"])
            self.assertEqual(code, 0)
            self.assertEqual(lines, [{"id": "saved"}])
            self.assertEqual(http.return_value.request.call_args.args[2], {"value": "private"})

    def test_workflow_summaries_preserve_ids_status_errors_and_cursors(self):
        row = {"id": "thread", "environmentConfigId": "env", "name": "fixture", "status": {"type": "idle"},
               "error": {"message": "failure cause"}, "preview": "x" * 5000, "turns": [{"id": "turn"}]}
        value = {"data": [row], "nextCursor": "next", "backwardsCursor": "previous"}
        ctx = context(group="jobs", action="list")
        summary = cli.workflow_output(ctx.args, value)
        self.assertEqual(summary["nextCursor"], "next")
        self.assertEqual(summary["backwardsCursor"], "previous")
        for field in ("id", "environmentConfigId", "status", "error"):
            self.assertEqual(summary["data"][0][field], row[field])
        self.assertEqual(len(summary["data"][0]["preview"]), 800)
        self.assertEqual(summary["data"][0]["truncated_fields"], ["preview"])
        self.assertTrue(summary["data"][0]["details_omitted"])
        self.assertNotIn("turns", summary["data"][0])
        ctx.args.full = True
        self.assertEqual(cli.workflow_output(ctx.args, value), value)

    def test_logs_summary_keeps_canonical_entries_and_full_restores_content(self):
        entry = {"turnId": "turn", "startedAtMs": 1, "item": {"id": "item", "type": "agentMessage", "text": "x" * 5000}}
        value = {"data": [entry], "nextCursor": "older"}
        args = context(group="jobs", action="logs").args
        summary = cli.workflow_output(args, value)
        self.assertEqual(summary["data"][0]["turnId"], "turn")
        self.assertEqual(summary["data"][0]["startedAtMs"], 1)
        self.assertEqual(summary["data"][0]["item"]["id"], "item")
        self.assertEqual(len(summary["data"][0]["item"]["text"]), 800)
        self.assertEqual(summary["nextCursor"], "older")
        args.full = True
        self.assertEqual(cli.workflow_output(args, value), value)

    def test_explicit_raw_views_and_receipts_are_not_summarized(self):
        value = {"turn": {"id": "turn", "items": [{"text": "x" * 5000}]}, "receipt": {"thread_id": "thread"}}
        for group, action, extra in (("api", "rpc", {}), ("jobs", "turns", {"view": "full"}), ("jobs", "create", {})):
            with self.subTest(group=group, action=action):
                self.assertEqual(cli.workflow_output(context(group=group, action=action, **extra).args, value), value)

    def test_credentials_are_redacted_before_preview_truncation_and_in_keys(self):
        ctx = context(group="jobs", action="get", show_secrets=True)
        ctx.token = "private-token-" + "x" * 1000
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            ctx.emit({"thread": {"id": "fixture", "preview": ctx.token}})
        self.assertEqual(json.loads(output.getvalue())["thread"]["preview"], "<redacted>")
        self.assertEqual(transport.redact({ctx.token: "value"}, (ctx.token,), True), {"<redacted>": "value"})

    def test_output_is_compact_json_and_bound_errors_retain_receipt(self):
        output = io.StringIO()
        with mock.patch.object(cli, "dispatch", return_value={"ok": True}), contextlib.redirect_stdout(output):
            self.assertEqual(cli.main(["api", "rpc", "thread/list"]), 0)
        self.assertEqual(output.getvalue(), '{"ok":true}\n')
        def large_result(ctx, args):
            ctx.receipt = {"thread_id": "known-thread"}
            return {"text": "x" * 2000}
        with mock.patch.object(cli, "dispatch", side_effect=large_result):
            code, lines = execute(["api", "rpc", "thread/read", "--max-output-bytes", "1024"])
        self.assertEqual(code, 1)
        self.assertEqual(lines[0]["outcome"], "response-received")
        self.assertEqual(lines[0]["receipt"]["thread_id"], "known-thread")
        self.assertNotIn("x" * 100, json.dumps(lines))

    def test_terminal_output_failure_is_reported_once_without_sensitive_causes(self):
        for failure, expected_code in (
            (None, 1),
            (transport.CloudError("sanitized operation failure"), 1),
            (transport.CloudError("sanitized operation failure", outcome="unknown"), 2),
            (ValueError("private-fixture-local-secret"), 1),
        ):
            def dispatch(ctx, args):
                if failure is not None:
                    try:
                        raise RuntimeError("private-fixture-secret")
                    except RuntimeError as cause:
                        raise failure from cause
                return {"receipt": {"thread_id": "fixture"}}

            for output_error in (BrokenPipeError("private-fixture-output-secret"), OSError("private-fixture-output-secret")):
                for stderr_closed in (False, True):
                    errors = io.StringIO()
                    stderr_failure = mock.patch.object(errors, "write", side_effect=BrokenPipeError("private-fixture-stderr-secret")) if stderr_closed else contextlib.nullcontext()
                    with self.subTest(failure=type(failure).__name__, output=type(output_error).__name__, stderr_closed=stderr_closed):
                        with mock.patch.object(cli, "dispatch", side_effect=dispatch) as operation, mock.patch.object(cli.Context, "emit", side_effect=output_error) as emit:
                            with contextlib.redirect_stderr(errors), stderr_failure:
                                code, lines = execute(["api", "rpc", "thread/start", "--write"])
                        self.assertEqual(code, expected_code)
                        self.assertEqual(lines, [])
                        operation.assert_called_once()
                        emit.assert_called_once()
                        self.assertEqual(errors.getvalue(), "" if stderr_closed else
                                         "codex-cloud: stdout write failed; do not retry mutations automatically\n")

    def test_terminal_output_failure_stops_streaming_before_another_mutation(self):
        for method in ("write", "flush"):
            next_mutation = mock.Mock()
            receipt = {"receipt": {"thread_id": "fixture", "stage": "thread-created"}}

            def dispatch(ctx, args):
                with mock.patch.object(sys.stdout, method, side_effect=BrokenPipeError("private-fixture-output-secret")):
                    ctx.emit(receipt)
                next_mutation()

            with self.subTest(method=method), mock.patch.object(cli, "dispatch", side_effect=dispatch), contextlib.redirect_stderr(io.StringIO()) as errors:
                code, lines = execute(["api", "rpc", "thread/start", "--write"])
            self.assertEqual(code, 1)
            self.assertEqual(lines, [receipt] if method == "flush" else [])
            next_mutation.assert_not_called()
            self.assertEqual(errors.getvalue(), "codex-cloud: stdout write failed; do not retry mutations automatically\n")

    def test_error_reporting_never_leaks_chained_credentials_at_minimum_output_bound(self):
        for receipt, expected in (
            ({"thread_id": "known-thread", "turn_id": "turn", "client_message_id": "message", "stage": "turn/start", "optional": "x" * 5000}, "receipt_compacted"),
            ({"thread_id": "x" * 5000}, "receipt_omitted"),
        ):
            def fail(ctx, args):
                ctx.token = "private-fixture-token"
                try:
                    raise OSError("private-fixture-token in sensitive chained cause")
                except OSError as cause:
                    raise transport.CloudError("private-fixture-token " + "\0é" * 5000, outcome="unknown", code=503, receipt=receipt) from cause
            with self.subTest(expected=expected), mock.patch.object(cli, "dispatch", side_effect=fail), contextlib.redirect_stderr(io.StringIO()) as errors:
                code, lines = execute(["api", "rpc", "thread/start", "--write", "--max-output-bytes", "1024"])
            self.assertEqual(code, 2)
            self.assertEqual(lines[0]["outcome"], "unknown")
            self.assertEqual(lines[0]["code"], 503)
            self.assertTrue(lines[0][expected])
            self.assertLessEqual(len(json.dumps(lines[0], ensure_ascii=False, separators=(",", ":")).encode()), 1024)
            self.assertNotIn("private-fixture-token", json.dumps(lines))
            self.assertEqual(errors.getvalue(), "")
            if expected == "receipt_compacted":
                self.assertEqual(lines[0]["receipt"]["thread_id"], "known-thread")
                self.assertEqual(lines[0]["receipt"]["turn_id"], "turn")
                self.assertEqual(lines[0]["receipt"]["client_message_id"], "message")
                self.assertEqual(lines[0]["receipt"]["stage"], "turn/start")
            else:
                self.assertIsNone(lines[0]["receipt"])
                self.assertIn("--max-output-bytes", lines[0]["output_bound_reason"])

    def test_session_validation_failure_preserves_already_sent_write(self):
        with tempfile.TemporaryFile(mode="w+") as source:
            source.write('{"id":"write","method":"thread/archive","params":{"threadId":"fixture"}}\nnot-json\n')
            source.seek(0)
            with SocketPeer(lambda _: {"result": {}}) as peer, mock.patch.object(cli.auth, "load_auth", return_value=("token", "account")), mock.patch.object(sys, "stdin", source):
                code, lines = execute(["api", "session", "--write", "--seconds", "2"])
        self.assertEqual(code, 2)
        self.assertEqual(lines[-1]["outcome"], "unknown")
        self.assertEqual(lines[-1]["receipt"]["pending_requests"]["write"]["method"], "thread/archive")
        self.assertIn("JSONDecodeError", lines[-1]["error"])
        self.assertEqual([r["method"] for r in peer.requests].count("thread/archive"), 1)

    def test_session_numeric_id_read_receipts_are_preserved_without_replay(self):
        with tempfile.TemporaryFile(mode="w+") as source:
            source.write('{"id":17,"method":"thread/read","params":{"threadId":"fixture"}}\n')
            source.seek(0)
            with SocketPeer(lambda req: {"result": {}} if req["method"] == "initialize" else "disconnect") as peer:
                with mock.patch.object(cli.auth, "load_auth", return_value=("token", "account")), mock.patch.object(sys, "stdin", source), mock.patch.object(transport.time, "sleep") as sleep:
                    code, lines = execute(["api", "session", "--seconds", "2"])
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1]["outcome"], "read-failed")
        self.assertEqual(lines[-1]["receipt"]["pending_requests"]["17"]["method"], "thread/read")
        self.assertEqual([r["method"] for r in peer.requests].count("thread/read"), 1)
        sleep.assert_not_called()

    def test_real_http_refuses_redirect_and_returns_empty_success(self):
        requests = []
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self):
                requests.append(self.path)
                if self.path.endswith("redirect"):
                    self.send_response(302)
                    self.send_header("Location", "/destination")
                else:
                    self.send_response(204)
                self.end_headers()
        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            with mock.patch.object(transport, "BASE", f"http://127.0.0.1:{server.server_port}"):
                client = transport.Http("token", "account", timeout=2)
                with self.assertRaises(transport.CloudError) as raised:
                    client.request("GET", "/backend-api/wham/redirect")
                self.assertEqual(raised.exception.code, 302)
                self.assertIsNone(client.request("GET", "/backend-api/wham/empty"))
            self.assertNotIn("/destination", requests)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
