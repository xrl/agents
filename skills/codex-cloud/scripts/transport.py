"""Bounded transports for the fixed first-party Codex Cloud origins."""
from __future__ import annotations

import base64
import contextlib
import json
import re
import time
import urllib.error
import urllib.request

BASE = "https://chatgpt.com"
WS_URL = "wss://codex-cloud-backend.chatgpt.com/"
MAX_BODY = 4 * 1024 * 1024


class CloudError(Exception):
    def __init__(self, message, *, outcome="not-sent", receipt=None, code=None):
        super().__init__(message)
        self.outcome, self.receipt, self.code = outcome, receipt, code


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
        return {k: ("<redacted>" if not show_secrets and re.search(
            r"(?i)(authorization|access.?token|refresh.?token|cookie|password|auth_key|^secret|encrypted_content)", k
        ) else redact(v, secrets, show_secrets)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secrets, show_secrets) for v in value]
    return safe_text(value, secrets) if isinstance(value, str) else value


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
        mutation = method != "GET"
        try:
            response = self.opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            response = e
        except (OSError, urllib.error.URLError) as e:
            raise CloudError(
                safe_text(f"{method} {path.split('?')[0]}: {type(e).__name__}: {e}", self.secrets),
                outcome="unknown" if mutation else "read-failed",
            ) from None
        try:
            with response:
                status = response.status
                raw = response.read(MAX_BODY + 1)
        except OSError as e:
            raise CloudError(f"{method}: response read failed ({type(e).__name__})", outcome="unknown" if mutation else "read-failed") from None
        if len(raw) > MAX_BODY:
            raise CloudError("HTTP response exceeds 4 MiB", outcome="unknown" if mutation else "read-failed")
        if binary and 200 <= status < 300:
            return {"bytes": len(raw), "base64": base64.b64encode(raw).decode()}
        try:
            payload = json.loads(raw) if raw else None
        except (ValueError, UnicodeError):
            payload = None
        if not 200 <= status < 300:
            details = payload.get("detail", payload.get("message", payload.get("error", ""))) if isinstance(payload, dict) else "non-JSON response"
            hint = "; use --browser-session with a signed-in same-account ChatGPT tab" if path.startswith("/api/") and status in (401, 403, 404) else ""
            raise CloudError(
                safe_text(f"{method} {path.split('?')[0]}: HTTP {status}: {details}", self.secrets)[:1600] + hint,
                outcome=("unknown" if mutation and status >= 500 else "rejected" if mutation else "read-failed"), code=status,
            )
        if raw and payload is None:
            raise CloudError("Expected JSON API response", outcome="unknown" if mutation else "read-failed")
        return payload


class Rpc:
    def __init__(self, socket, *, token="", timeout=30):
        self.socket, self.token, self.timeout, self.counter = socket, token, timeout, 0

    def call(self, method, params, *, mutation=False):
        self.counter += 1
        ident = self.counter
        message = json.dumps({"id": ident, "method": method, "params": params})
        if len(message.encode()) > MAX_BODY:
            raise CloudError("RPC request exceeds 4 MiB")
        # A failed send can have delivered bytes; do not retry mutations.
        outcome = "unknown" if mutation else "read-failed"
        try:
            self.socket.send(message)
            deadline = time.monotonic() + self.timeout
            for _ in range(1000):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("RPC deadline exceeded")
                reply = json.loads(self.socket.recv(timeout=remaining))
                if reply.get("id") != ident or "method" in reply:
                    continue  # Do NOT answer server requests or approvals automatically.
                if "error" in reply:
                    error = reply["error"]
                    raise CloudError(
                        safe_text(f"RPC {method}: {error.get('message', 'server error')}", (self.token,))[:1600],
                        outcome="rejected" if mutation else "read-failed", code=error.get("code"),
                    )
                return reply.get("result", {})
            raise CloudError("Too many unsolicited messages", outcome=outcome)
        except CloudError:
            raise
        except Exception as e:
            # WebSocket exception reprs can include the Authorization subprotocol.
            if isinstance(e, (TimeoutError, ValueError)):
                cause = safe_text(str(e), (self.token,))[:400]
            else:
                cause = "connection closed/failed; handshake credentials suppressed"
            raise CloudError(f"RPC {method}: {type(e).__name__}: {cause}", outcome=outcome) from None


@contextlib.contextmanager
def connect_rpc(token, account, *, timeout=30):
    from websockets.sync.client import connect
    socket = None
    try:
        try:
            socket = connect(
                WS_URL, subprotocols=["codex-app-server", "codex-client.browser", "openai-bearer." + token],
                additional_headers={"ChatGPT-Account-Id": account}, origin=BASE,
                open_timeout=min(timeout, 30), close_timeout=5, max_size=MAX_BODY,
            )
        except Exception as e:
            raise CloudError(f"Cloud WebSocket handshake failed ({type(e).__name__}; credentials suppressed)") from None
        rpc = Rpc(socket, token=token, timeout=timeout)
        rpc.call("initialize", {
            "clientInfo": {"name": "codex-browser", "title": "Codex Cloud skill", "version": "browser"},
            "capabilities": {"experimentalApi": True, "requestAttestation": False},
        })
        try:
            socket.send(json.dumps({"method": "initialized"}))
        except Exception as e:
            raise CloudError(f"Initialization acknowledgement failed ({type(e).__name__})") from None
        yield rpc
    finally:
        if socket is not None:
            socket.close()
