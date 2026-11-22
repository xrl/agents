"""Official Codex ChatGPT login and opt-in existing-browser cookie handoff. No persistence."""
import base64
import fcntl
import http.server
import json
import math
import os
import pathlib
import secrets
import subprocess
import threading
import time

from transport import CloudError, unique_object

# The codex CLI refreshes its own login when the access token is within five minutes of expiry.
REFRESH_WINDOW_SECONDS = 300


def default_auth_file():
    return str(pathlib.Path(os.environ.get("CODEX_HOME") or "~/.codex").expanduser() / "auth.json")


def read_auth(path):
    try:
        with pathlib.Path(path).expanduser().open(encoding="utf-8") as source:
            text = source.read(65537)
        if len(text.encode()) > 65536:
            raise CloudError("Codex auth.json exceeds 64 KiB")
        tokens = json.loads(text, object_pairs_hook=unique_object)["tokens"]
        token, account = tokens["access_token"], tokens["account_id"]
        if not isinstance(token, str) or not isinstance(account, str) or not account:
            raise CloudError("Codex access_token and account_id must be nonempty strings")
        claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
        if not isinstance(claims, dict) or not isinstance(claims.get("https://api.openai.com/auth"), dict):
            raise CloudError("Codex token is missing account claims")
        if claims["https://api.openai.com/auth"].get("chatgpt_account_id") != account:
            raise CloudError("Codex token and account_id disagree")
        if not isinstance(claims["exp"], (int, float)) or not math.isfinite(claims["exp"]):
            raise CloudError("Codex token expiry must be a finite number")
        return token, account, claims["exp"]
    except CloudError:
        raise
    except OSError as e:
        raise CloudError(f"Cannot open Codex auth.json ({type(e).__name__}, errno={e.errno}); run `codex login`") from e
    except (ValueError, KeyError, TypeError, IndexError, RecursionError) as e:
        field = f"; missing field {e.args[0]}" if isinstance(e, KeyError) else ""
        raise CloudError(f"Invalid Codex ChatGPT login ({type(e).__name__}{field}); credential contents suppressed") from e


def refresh_with_codex(path):
    """Have the official codex CLI refresh its own login: any authenticated codex call does it inside the window.

    Returns why a refresh may not have happened (or None); the caller re-reads the file either way, because codex
    persists a refresh before its list request, so a slow or failed list can still leave a fresh login on disk."""
    path = pathlib.Path(path).expanduser().absolute()
    if path.name != "auth.json":
        return f"--auth-file must be <CODEX_HOME>/auth.json for codex to refresh it, not {path.name}"
    home = str(path.parent)
    env = {key: value for key, value in os.environ.items()
           if key not in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN")}
    env["CODEX_HOME"] = home
    try:
        # cwd=home: codex appends a relative error.log (with the account id) to its working directory.
        subprocess.run(["codex", "cloud", "list", "--limit", "1", "--json"], env=env, cwd=home,
                       stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
    except OSError as e:
        return f"cannot execute codex ({type(e).__name__}, errno={e.errno})"
    except subprocess.TimeoutExpired:
        return "codex ran past 60 seconds"
    return None


def load_auth(path, refresh=refresh_with_codex):
    token, account, expiry = read_auth(path)
    if expiry <= time.time() + REFRESH_WINDOW_SECONDS:
        # Refresh tokens are single-use: parallel callers (an Astra gate and its shadows) take turns, and each
        # re-reads after the lock, so only the first one refreshes and the rest pick up its new token.
        lock = pathlib.Path(path).expanduser().absolute().with_name("codex-cloud-refresh.lock")
        try:
            handle = open(lock, "a")
        except OSError as e:
            raise CloudError(f"Cannot open the refresh lock ({type(e).__name__}, errno={e.errno})") from e
        with handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            reason = None
            token, account, expiry = read_auth(path)
            if expiry <= time.time() + REFRESH_WINDOW_SECONDS:
                reason = refresh(path)
                token, account, expiry = read_auth(path)
            if expiry <= time.time() + 30:
                why = f" ({reason})" if reason else ""
                raise CloudError(f"Codex's ChatGPT login is expired and codex did not refresh it{why}; "
                                 "check `codex login status` and the network, and run `codex login` only if the refresh token is dead")
    return token, account


def borrow_browser_cookies(session, account):
    """Nonce-protected loopback handoff: cookies never enter argv, logs or files."""
    state = {}
    nonce = "/" + secrets.token_urlsafe(32)

    class Handler(http.server.BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *_):
            pass

        def do_POST(self):
            if self.path != nonce or state or self.headers.get("Origin"):
                self.send_error(403)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 128 * 1024:
                    raise ValueError()
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("Expected browser handoff object")
                if data.get("accountId") != account:
                    state["error"] = "account mismatch"
                    self.send_error(409)
                    return
                if not isinstance(data.get("ua"), str) or not isinstance(data.get("cookies"), list) or any(
                    not isinstance(cookie, dict) or not all(isinstance(cookie.get(key), str) for key in ("name", "value"))
                    for cookie in data["cookies"]
                ):
                    raise ValueError("Invalid browser handoff fields")
                state.update(data)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")
            except (ValueError, TypeError, OSError, RecursionError) as error:
                state["error"] = type(error).__name__
                self.send_error(400)

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    server.timeout = 5
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    bridge = f"http://127.0.0.1:{server.server_port}{nonce}"
    # No access token or cookie values are interpolated into the command.
    code = """async page => {
      const p=page.context().pages().find(p=>{
        try{return new URL(p.url()).origin==='https://chatgpt.com';}catch{return false;}
      });
      if(!p)throw new Error('Open a signed-in ChatGPT tab first');
      const identity=await p.evaluate(()=>({
        ua:navigator.userAgent,
        accountId:document.documentElement.dataset.themeAccountId
      }));
      const cookies=await p.context().cookies(
        'https://chatgpt.com/api/codex-cloud/v1/environment-configs');
      const r=await p.request.post(BRIDGE,{data:{...identity,cookies}});
      if(!r.ok())throw new Error('Browser/Codex account mismatch or bridge failure');
      return {ok:true};
    }""".replace("BRIDGE", json.dumps(bridge))
    try:
        result = subprocess.run(
            ["playwright-cli", f"-s={session}", "run-code", code],
            capture_output=True, text=True, timeout=25,
        )
        if result.returncode or "cookies" not in state:
            raise CloudError(
                f"Browser cookie handoff failed (exit={result.returncode}, bridge={state.get('error', 'no matching handoff')}); "
                "use an existing signed-in ChatGPT tab on the SAME account as the Codex login"
            )
        return {"User-Agent": state["ua"], "Cookie": "; ".join(
            c["name"] + "=" + c["value"] for c in state["cookies"]
        )}
    except OSError as e:
        raise CloudError(f"Cannot execute playwright-cli ({type(e).__name__}, errno={e.errno})") from e
    except subprocess.TimeoutExpired as error:
        raise CloudError("playwright-cli cookie handoff exceeded 25 seconds") from error
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
