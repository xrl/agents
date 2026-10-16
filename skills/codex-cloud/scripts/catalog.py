"""One runtime catalog assembled from frozen public and observed web contracts."""
import json
from itertools import islice
import pathlib
import re
import urllib.parse

from transport import CloudError

REFERENCES = pathlib.Path(__file__).resolve().parent.parent / "references"
WEB = json.loads((REFERENCES / "web-contract.json").read_text())
SCHEMA = json.loads((REFERENCES / "client-request-schema.json").read_text())
REQUESTS = {row["properties"]["method"]["enum"][0]: row for row in SCHEMA["oneOf"]}
READ_METHODS = frozenset(WEB["read_rpc_methods"]) | {"initialize"}


def rpc_entries():
    output = []
    for method in sorted(set(REQUESTS) | set(WEB["browser_rpc_methods"])):
        evidence = "live-verified" if method in WEB["live_verified_rpc"] else "web-source" if method in WEB["browser_rpc_methods"] else "public-schema-only"
        if method in WEB["browser_emulated_methods"]:
            evidence = "browser-emulated; remote support unverified"
        output.append({"method": method, "mutation": method not in READ_METHODS, "evidence": evidence,
                       "has_public_params_schema": method in REQUESTS})
    return output


def validate_rpc(method, params):
    if not isinstance(method, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_/-]{0,199}", method):
        raise CloudError("Invalid RPC method name")
    if not isinstance(params, dict) and params is not None:
        raise CloudError("RPC params must be an object or null")
    variant = REQUESTS.get(method)
    if variant is None:
        return  # Undocumented Cloud extensions are forwarded, never invented or auto-classified read-only.
    from jsonschema import Draft7Validator
    schema = {**variant, "definitions": SCHEMA["definitions"]}
    errors = list(islice(Draft7Validator(schema).iter_errors({"id": 1, "method": method, "params": params}), 10))
    if errors:
        # Do not echo values from ValidationError.message (could include passwords).
        details = [f"{'.'.join(map(str, e.path)) or 'request'} violates {e.validator}" for e in errors]
        raise CloudError("Invalid RPC request: " + "; ".join(details))


def params_schema(method):
    if method not in REQUESTS:
        return {"method": method, "params_schema": None, "note": "Cloud extension; consult web evidence, no public schema"}
    return {"method": method, "params_schema": REQUESTS[method]["properties"].get("params"),
            "definitions": SCHEMA["definitions"]}


def http_path(operation, path_params, query):
    entry = WEB["http"].get(operation)
    if entry is None:
        raise CloudError("Unknown HTTP operation; use `api list --transport http`")
    if not isinstance(path_params, dict):
        raise CloudError("Path parameters must be an object")
    if not isinstance(query, dict):
        raise CloudError("Query must be an object")
    path = entry["path"]
    required = set(re.findall(r"\{(\w+)\}", path))
    if required != set(path_params):
        raise CloudError(f"Path parameter names must be exactly: {', '.join(sorted(required)) or '(none)'}")
    for name in required:
        value = path_params[name]
        if not isinstance(value, str) or not value or value in (".", ".."):
            raise CloudError(f"Invalid {name}")
        path = path.replace("{" + name + "}", urllib.parse.quote(value, safe=""))
    if query:
        path += "?" + urllib.parse.urlencode(query, doseq=True)
    return entry, path
