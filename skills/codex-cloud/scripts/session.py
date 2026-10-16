"""Bounded bidirectional JSONL driver; no implicit approval or task resumption."""
import json
import os
import select
import sys
import time

import catalog
from transport import MAX_BODY, CloudError, unique_object, websocket_failure


def validate_message(ctx, message, pending_clients, pending_servers):
    if not isinstance(message, dict) or type(message.get("id")) not in (str, int):
        raise CloudError("Session messages require a string/integer id")
    ident = message["id"]
    if "method" in message:
        if message["method"] == "initialize":
            raise CloudError("initialize is transport-managed")
        if ident in pending_clients:
            raise CloudError("Duplicate pending client request id")
        if len(pending_clients) >= 50:
            raise CloudError("At most 50 outstanding client requests")
        mutation = not isinstance(message["method"], str) or message["method"] not in catalog.READ_METHODS
        ctx.guard(mutation)
        catalog.validate_rpc(message["method"], message.get("params", {}))
        return "request", mutation
    if set(message) not in ({"id", "result"}, {"id", "error"}):
        raise CloudError("Responses require exactly id + result or id + error")
    if ident not in pending_servers:
        raise CloudError("Cannot answer an unknown server request id")
    ctx.guard(True)  # Explicit policy decision, including denial; never automatically answer.
    return "response", True


def run_session(ctx, args):
    if ctx.args.dry_run:
        return {"dry_run": True, "session": {"seconds": args.seconds, "max_messages": args.max_messages},
                "note": "No stdin read, connection, task resume or approval response"}
    from websockets.exceptions import WebSocketException
    pending_clients, pending_servers = {}, set()
    deadline, buffer, count, eof = time.monotonic() + args.seconds, b"", 0, False
    ctx.deadline = deadline
    try:
        with ctx.rpc() as rpc:
            socket = rpc.socket
            while time.monotonic() < deadline and count < args.max_messages:
                if not eof and select.select([sys.stdin], [], [], 0)[0]:
                    chunk = os.read(sys.stdin.fileno(), 65536)
                    if not chunk:
                        eof = True
                        if buffer.strip():
                            raise CloudError("Session input must end with newline")
                    buffer += chunk
                    if len(buffer) > MAX_BODY:
                        raise CloudError("JSONL input buffer exceeds 4 MiB")
                # Drain buffered lines even after EOF; never lose a second line in a read.
                while b"\n" in buffer and count < args.max_messages:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        message = json.loads(line, object_pairs_hook=unique_object)
                    except (ValueError, RecursionError) as error:
                        raise CloudError(f"Invalid JSONL input ({type(error).__name__}); values omitted") from error
                    kind, mutation = validate_message(ctx, message, pending_clients, pending_servers)
                    encoded = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
                    if len(encoded.encode()) > MAX_BODY:
                        raise CloudError("Session request exceeds 4 MiB")
                    if kind == "request":
                        pending_clients[message["id"]] = {"method": message["method"], "mutation": mutation}
                    else:
                        pending_servers.remove(message["id"])
                    try:
                        socket.send(encoded)
                    except (OSError, WebSocketException) as error:
                        cause, _, code = websocket_failure(error)
                        raise CloudError(f"Session send: {cause}", code=code,
                                         outcome="unknown" if mutation else "read-failed") from error
                    count += 1
                if count >= args.max_messages or (eof and not pending_clients):
                    break
                try:
                    message = json.loads(socket.recv(timeout=min(.1, max(.001, deadline - time.monotonic()))),
                                         object_pairs_hook=unique_object)
                except TimeoutError:
                    continue
                except (ValueError, RecursionError) as error:
                    raise CloudError(f"Invalid session response JSON ({type(error).__name__})", outcome="read-failed") from error
                except (OSError, WebSocketException) as error:
                    cause, _, code = websocket_failure(error)
                    raise CloudError(f"Session receive: {cause}", code=code, outcome="read-failed") from error
                if not isinstance(message, dict) or ("id" in message and type(message["id"]) not in (str, int)):
                    raise CloudError("Invalid session response object/id", outcome="read-failed")
                if "id" in message and "method" in message:
                    if len(pending_servers) >= 50 or message["id"] in pending_servers:
                        raise CloudError("Duplicate/excess server request; no requests answered")
                    pending_servers.add(message["id"])
                    kind = "server-request"
                elif "id" in message:
                    if message["id"] not in pending_clients or ("result" in message) == ("error" in message):
                        raise CloudError("Unexpected/malformed session response", outcome="read-failed")
                    del pending_clients[message["id"]]
                    kind = "response"
                else:
                    kind = "notification"
                ctx.emit({"kind": kind, "message": message})
                count += 1
        if pending_clients:
            raise CloudError("Session ended with pending requests; do not automatically retry writes", outcome="read-failed")
    except (CloudError, OSError) as error:
        if not isinstance(error, CloudError):
            error = CloudError(f"Session I/O failed ({type(error).__name__}, errno={error.errno})", outcome="read-failed")
        if any(p["mutation"] for p in pending_clients.values()):
            error.outcome = "unknown"
        error.receipt = {"pending_requests": pending_clients}
        raise error
    return {"session_ended": "eof" if eof else "bound", "messages": count,
            "unanswered_server_requests": list(pending_servers), "task_cancelled": False}
