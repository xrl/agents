"""Bounded transports for the fixed first-party Codex Cloud origins."""
from __future__ import annotations

import base64
import contextlib
import errno
import http.client
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.request

BASE = "https://chatgpt.com"
WS_URL = "wss://codex-cloud-backend.chatgpt.com/"
MAX_BODY = 4 * 1024 * 1024
TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}
RETRY_DELAYS = (0.5, 1.0)


class CloudError(Exception):
    def __init__(self, message, *, outcome="not-sent", receipt=None, code=None, retryable=False):
        super().__init__(message)
        self.outcome, self.receipt, self.code = outcome, receipt, code
        self.retryable = retryable


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CloudError("Duplicate JSON object key")
        result[key] = value
    return result


def credential_secrets(token, browser_headers=None):
    cookie = (browser_headers or {}).get("Cookie", "")
    values = []
    for part in cookie.split(";"):
        if "=" not in part:
            continue
        name, value = part.strip().split("=", 1)
        if re.search(r"next-auth|cf_clearance|__cf_bm|_cfuvid", name) and len(value) >= 16:
            values.append(value)
    return (token, cookie, *values)


def safe_text(value, secrets=()):
    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "<redacted>")
    text = re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "<redacted-jwt>", text)
    text = re.sub(r"(?i)(bearer\s+)[^\s\"']+", r"\1<redacted>", text)
    return text


def redact(value, secrets=(), show_secrets=False):
    if isinstance(value, dict):
        return {safe_text(str(k), secrets): ("<redacted>" if not show_secrets and re.search(
            r"(?i)(authorization|access.?token|refresh.?token|cookie|password|auth_key|^secret|encrypted_content)", str(k)
        ) else redact(v, secrets, show_secrets)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secrets, show_secrets) for v in value]
    return safe_text(value, secrets) if isinstance(value, str) else value


def retry(operation, attempt, *, timeout):
    """At most three attempts, including backoff in the operation's time budget."""
    deadline = time.monotonic() + timeout
    for index in range(len(RETRY_DELAYS) + 1):
        try:
            return attempt(max(0, deadline - time.monotonic()))
        except CloudError as error:
            if not error.retryable or index == len(RETRY_DELAYS):
                raise
            delay = RETRY_DELAYS[index]
            if deadline - time.monotonic() <= delay:
                raise
            # Never log remote text, payloads, paths, tokens or handshake headers.
            print(f"retry {index + 2}/3 in {delay:g}s: {operation} ({error.outcome})", file=sys.stderr, flush=True)
            time.sleep(delay)
            if time.monotonic() >= deadline:
                raise


def transient_connection(error):
    if isinstance(error, socket.gaierror):
        return error.errno == socket.EAI_AGAIN
    return isinstance(error, (TimeoutError, ConnectionError, http.client.IncompleteRead)) or (
        isinstance(error, OSError) and error.errno in {errno.ETIMEDOUT, errno.ENETUNREACH, errno.EHOSTUNREACH}
    )


def websocket_failure(error):
    """Keep status/close codes, not exception reprs containing auth subprotocols."""
    from websockets.exceptions import ConnectionClosed, InvalidStatus
    if isinstance(error, InvalidStatus):
        status = error.response.status_code
        return f"HTTP {status}", status in TRANSIENT_STATUS, status
    if isinstance(error, ConnectionClosed):
        code = error.rcvd.code if error.rcvd else None
        return f"{type(error).__name__} (close code {code})", code in (None, 1000, 1001, 1011, 1012, 1013, 1014), code
    cause = type(error).__name__
    if isinstance(error, OSError):
        cause += f" (errno={error.errno})"
    return cause, transient_connection(error), None


def paged(fetch, *, key="data", cursor_key="nextCursor", max_pages=5):
    rows, cursor, seen = [], None, set()
    for _ in range(max_pages):
        page = fetch(cursor)
        if not isinstance(page, dict) or not isinstance(page.get(key), list):
            raise CloudError(f"Expected an object containing the {key!r} array", outcome="read-failed")
        rows.extend(page[key])
        cursor = page.get(cursor_key)
        if cursor is None:
            return rows
        if not isinstance(cursor, str) or not cursor or cursor in seen:
            raise CloudError("Invalid/repeated pagination cursor", outcome="read-failed")
        seen.add(cursor)
    raise CloudError("Pagination limit reached; increase --max-pages; partial results not reported as complete", outcome="read-failed")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class Http:
    def __init__(self, token, account, browser_headers=None, timeout=30):
        self.timeout = timeout
        self.secrets = credential_secrets(token, browser_headers)
        self.headers = {
            "Authorization": "Bearer " + token, "ChatGPT-Account-Id": account,
            "Accept": "application/json", "Content-Type": "application/json",
            "User-Agent": "codex-cloud-skill/1", **(browser_headers or {}),
        }
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, method, path, body=None, *, binary=False):
        if not path.startswith(("/api/codex-cloud/v1/", "/backend-api/wham/", "/codex/app/api/codex/v1/")):
            raise CloudError("HTTP path outside fixed Cloud API prefixes")
        if any(c in path for c in ("\r", "\n", "\\", "#")):
            raise CloudError("Invalid HTTP path")
        data = None if body is None else json.dumps(body).encode()
        if data is not None and len(data) > MAX_BODY:
            raise CloudError("Request exceeds 4 MiB")
        request = urllib.request.Request(BASE + path, headers=self.headers, method=method, data=data)
        return retry(f"HTTP {method}", lambda timeout: self._request(request, timeout, binary), timeout=self.timeout)

    def _request(self, request, timeout, binary):
        mutation = request.method != "GET"
        outcome = "unknown" if mutation else "read-failed"
        operation = f"{request.method} {request.selector.split('?')[0]}"
        if timeout <= 0:
            raise CloudError(f"{operation}: request deadline reached")
        try:
            try:
                response = self.opener.open(request, timeout=timeout)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                status = response.status
                raw = response.read(MAX_BODY + 1)
        except (OSError, urllib.error.URLError, http.client.HTTPException) as error:
            cause = error.reason if isinstance(error, urllib.error.URLError) else error
            # Only these URL-open failures prove that no HTTP request was sent.
            not_sent = isinstance(error, urllib.error.URLError) and isinstance(cause, (ConnectionRefusedError, socket.gaierror))
            raise CloudError(
                safe_text(f"{operation}: {type(cause).__name__}: {cause}", self.secrets)[:1600],
                outcome="not-sent" if not_sent else outcome,
                retryable=transient_connection(cause) and (not mutation or not_sent),
            ) from error
        if len(raw) > MAX_BODY:
            raise CloudError("HTTP response exceeds 4 MiB", outcome=outcome)
        if binary and 200 <= status < 300:
            return {"bytes": len(raw), "base64": base64.b64encode(raw).decode()}
        try:
            payload = json.loads(raw, object_pairs_hook=unique_object) if raw else None
        except (ValueError, RecursionError, CloudError) as error:
            if 200 <= status < 300:
                raise CloudError(f"{operation}: invalid JSON response ({type(error).__name__})", outcome=outcome) from error
            payload = None  # Preserve HTTP status even when its error body isn't JSON.
        if not 200 <= status < 300:
            details = payload.get("detail", payload.get("message", payload.get("error", ""))) if isinstance(payload, dict) else "non-JSON response"
            hint = "; use --browser-session with a signed-in same-account ChatGPT tab" if request.selector.startswith("/api/") and status in (401, 403, 404) else ""
            raise CloudError(
                safe_text(f"{operation}: HTTP {status}: {details}", self.secrets)[:1600] + hint,
                outcome=("unknown" if mutation and (status >= 500 or status == 408 or 300 <= status < 400) else "rejected" if mutation else "read-failed"), code=status,
                retryable=not mutation and status in TRANSIENT_STATUS,
            )
        return payload


class Rpc:
    def __init__(self, socket, *, token="", timeout=30, account=None, deadline=None):
        self.socket, self.token, self.timeout, self.counter = socket, token, timeout, 0
        self.account, self.deadline = account, deadline

    def call(self, method, params, *, mutation=False):
        timeout = self.timeout if self.deadline is None else min(self.timeout, self.deadline - time.monotonic())
        reconnect = False

        def attempt(remaining):
            nonlocal reconnect
            deadline = time.monotonic() + remaining
            if reconnect:
                self.socket.close()
                self.socket = open_rpc(self.token, self.account, timeout=max(0, deadline - time.monotonic())).socket
            reconnect = True
            return self._call(method, params, mutation=mutation, timeout=deadline - time.monotonic())

        if mutation or self.account is None:
            return self._call(method, params, mutation=mutation, timeout=timeout)
        return retry(f"RPC {method}", attempt, timeout=timeout)

    def _call(self, method, params, *, mutation=False, timeout=None):
        from websockets.exceptions import WebSocketException
        self.counter += 1
        ident = self.counter
        message = json.dumps({"id": ident, "method": method, "params": params})
        if len(message.encode()) > MAX_BODY:
            raise CloudError("RPC request exceeds 4 MiB")
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        if deadline <= time.monotonic():
            raise CloudError(f"RPC {method}: request deadline reached")
        # Even a failed send can have delivered bytes. Never replay a mutation.
        outcome = "unknown" if mutation else "read-failed"
        try:
            self.socket.send(message)
            for _ in range(1000):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("RPC deadline exceeded")
                reply = json.loads(self.socket.recv(timeout=remaining), object_pairs_hook=unique_object)
                if not isinstance(reply, dict):
                    raise CloudError(f"RPC {method}: expected response object", outcome=outcome)
                if reply.get("id") != ident or "method" in reply:
                    continue  # Never answer server requests or approvals automatically.
                if "error" in reply:
                    error = reply["error"]
                    if ("result" in reply or not isinstance(error, dict) or not isinstance(error.get("message"), str)
                            or type(error.get("code")) is not int):
                        raise CloudError(f"RPC {method}: malformed error response", outcome=outcome)
                    raise CloudError(
                        safe_text(f"RPC {method}: {error['message']}", (self.token,))[:1600],
                        outcome="rejected" if mutation else "read-failed", code=error.get("code"),
                    )
                if "result" not in reply:
                    raise CloudError(f"RPC {method}: response missing result/error", outcome=outcome)
                return reply["result"]
            raise CloudError("Too many unsolicited messages", outcome=outcome)
        except CloudError as error:
            if error.outcome == "not-sent":
                error.outcome = outcome
            raise
        except (ValueError, RecursionError) as error:
            raise CloudError(f"RPC {method}: invalid JSON response ({type(error).__name__})", outcome=outcome) from error
        except (OSError, WebSocketException) as error:
            cause, transient, code = websocket_failure(error)
            raise CloudError(f"RPC {method}: {cause}", outcome=outcome, code=code,
                             retryable=not mutation and transient) from error


def open_rpc(token, account, *, timeout):
    from websockets.exceptions import WebSocketException
    from websockets.sync.client import connect
    if timeout <= 0:
        raise CloudError("Cloud WebSocket connection deadline reached")
    deadline = time.monotonic() + timeout
    try:
        socket = connect(
            WS_URL, subprotocols=["codex-app-server", "codex-client.browser", "openai-bearer." + token],
            additional_headers={"ChatGPT-Account-Id": account}, origin=BASE,
            open_timeout=min(timeout, 30), close_timeout=1, max_size=MAX_BODY,
        )
    except (OSError, WebSocketException) as error:
        cause, transient, code = websocket_failure(error)
        raise CloudError(f"Cloud WebSocket handshake: {cause}", code=code, retryable=transient) from error
    rpc = Rpc(socket, token=token, account=account, timeout=timeout)
    try:
        rpc._call("initialize", {
            "clientInfo": {"name": "codex-browser", "title": "Codex Cloud skill", "version": "browser"},
            "capabilities": {"experimentalApi": True, "requestAttestation": False},
        }, timeout=deadline - time.monotonic())
        socket.send(json.dumps({"method": "initialized"}))
    except (CloudError, OSError, WebSocketException) as error:
        socket.close()
        if isinstance(error, CloudError):
            error.outcome = "not-sent"  # No application request has been sent.
            raise
        cause, transient, code = websocket_failure(error)
        raise CloudError(f"Initialization acknowledgement: {cause}", code=code, retryable=transient) from error
    return rpc


@contextlib.contextmanager
def connect_rpc(token, account, *, timeout=30, deadline=None):
    budget = timeout if deadline is None else min(timeout, deadline - time.monotonic())
    rpc = retry("WebSocket connect", lambda remaining: open_rpc(token, account, timeout=remaining), timeout=budget)
    rpc.timeout, rpc.deadline = timeout, deadline
    try:
        yield rpc
    finally:
        rpc.socket.close()
