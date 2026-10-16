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


def execute(argv):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = cli.main(argv)
    return result, [json.loads(line) for line in stream.getvalue().splitlines()]


def context(**kwargs):
    base = dict(write=False, dry_run=False, auth_file="does-not-exist", browser_session=None,
                show_secrets=False, timeout=2, max_pages=5, max_output_bytes=transport.MAX_BODY)
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
