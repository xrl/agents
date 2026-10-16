"""Pi OAuth and opt-in existing-browser cookie handoff. No persistence."""
import base64
import http.server
import json
import math
import pathlib
import secrets
import subprocess
import threading
import time

from transport import CloudError, unique_object


def load_auth(path):
    try:
        with pathlib.Path(path).expanduser().open(encoding="utf-8") as source:
            text = source.read(65537)
        if len(text.encode()) > 65536:
            raise CloudError("Pi auth record exceeds 64 KiB")
        record = json.loads(text, object_pairs_hook=unique_object)["openai-codex"]
        token, account = record["access"], record["accountId"]
        if not isinstance(token, str) or not isinstance(account, str) or not account:
            raise CloudError("Pi access token and accountId must be nonempty strings")
        claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
        if not isinstance(claims, dict) or not isinstance(claims.get("https://api.openai.com/auth"), dict):
            raise CloudError("Pi token is missing account claims")
        if claims["https://api.openai.com/auth"].get("chatgpt_account_id") != account:
            raise CloudError("Pi token and selected account ID disagree")
        if not isinstance(claims["exp"], (int, float)) or not math.isfinite(claims["exp"]):
            raise CloudError("Pi token expiry must be a finite number")
        if claims["exp"] <= time.time() + 30:
            raise CloudError("Pi's Codex token is expired; refresh it through Pi first")
        return token, account
    except OSError as e:
        raise CloudError(f"Cannot open Pi's OAuth store ({type(e).__name__}, errno={e.errno})") from e
    except (ValueError, KeyError, TypeError, IndexError, RecursionError) as e:
        field = f"; missing field {e.args[0]}" if isinstance(e, KeyError) else ""
        raise CloudError(f"Invalid Pi openai-codex OAuth record ({type(e).__name__}{field}); credential contents suppressed") from e


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
      if(!r.ok())throw new Error('Browser/Pi account mismatch or bridge failure');
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
                "use an existing signed-in ChatGPT tab on the SAME account as Pi"
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
