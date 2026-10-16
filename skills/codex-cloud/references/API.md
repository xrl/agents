# API surface and wire notes

Implemented wrapper, not a proposal. All examples use `CC="$HOME/.claude/skills/codex-cloud/scripts/codex_cloud.py"`. The machine-readable catalog is assembled from `client-request-schema.json` and `web-contract.json`; `api list` is the authoritative CLI inventory. No source checkout is required after installation.

## Coverage means addressable, not universally supported

The pinned public schema contains 105 client request variants. The catalog adds methods present only in the captured browser adapter, for 120 RPC methods, plus 31 HTTP route templates from the environment client and legacy client. Run `api list` for the exact union and evidence labels. Every cataloged RPC except transport-managed `initialize` is addressable with `api rpc METHOD --params JSON_OR_@FILE`, and every HTTP operation with `api http OPERATION`.

- **live-verified**: a read returned successfully against the account during development.
- **web-source**: present in the captured deployed web client; a write has not been submitted to production.
- **public-schema-only**: supported by the public/local app-server contract, not established as a hosted API. Cloud may reject it.
- **browser-emulated**: the web adapter fabricates a local response for this method. Sending it directly to the remote server is not equivalent to the browser shim and is not advertised as verified.

Unknown RPC names can be forwarded deliberately. They have no guessed schema and default to requiring `--write`, even if the name ends in `/read`. There is no arbitrary HTTP URL/host override or token argument. This is not a promise that undocumented APIs are stable or an exhaustive enumeration of every private backend capability. Native gRPC, media codecs, browser GUI behavior and local Git patch application are not reimplemented.

## JSON-RPC transport

Fixed origin: `wss://codex-cloud-backend.chatgpt.com/`.

Subprotocols from the deployed browser serializer:

```text
codex-app-server
codex-client.browser
openai-bearer.<Pi access token>
```

The selected `ChatGPT-Account-Id` header and origin `https://chatgpt.com` accompany the handshake. The token never appears in command arguments, URLs, output or files. A short-lived process loads Pi's current auth record; waits reload it between polling connections.

The transport owns the `initialize` RPC and subsequent `initialized` notification. The captured client identifies itself as `codex-browser`, version `browser`, with `experimentalApi=true`, `requestAttestation=false`. Matching those fields is not an approval bypass. There is no automatic attestation generation, approval acceptance, server-request handling, execution attach or task resume. Transient connection setup and safe-read failures have bounded retries (see below); sent writes and session messages are never replayed.

The wrapper validates known RPC inputs against the pinned public JSON Schema. Cloud-only extensions are retained because the public contract does not contain all browser fields. Public/local schema validation is not hosted feature discovery.

### Creation

`jobs create` constructs:

```json
{
  "method": "thread/start",
  "params": {
    "threadSource": "user",
    "environments": [{"environmentConfigId": "ACCOUNT~asenvcfg_ID"}],
    "deferredEnvironment": true,
    "pluginsMcp": {"productSku": "codex"}
  }
}
```

An optional model is passed without replacing backend policy defaults. Then optional `thread/name/set`, then `turn/start` with text input and a client-generated message UUID. No model, sandbox mode, approval policy or reviewer is silently widened/defaulted by this wrapper.

Creation is multi-step, not atomic. JSONL receipts record the environment and message ID before starting and the real thread ID immediately after creation. If name-setting or turn-start fails, the known thread is preserved. The caller must inspect it before considering another operation. A stable message UUID can aid reconciliation of a turn; it does not make thread creation idempotent.

`jobs continue` explicitly resumes the supplied thread with `excludeTurns=true` before starting its new turn. This is a write, unlike history reads.

### Persisted history and status

- `thread/read`, `includeTurns=false`: thread metadata/runtime state.
- `thread/turns/list`: paginated turns with `itemsView=notLoaded|summary|full`.
- `thread/items/list`: paginated **entries**, not bare items:

```json
{"data":[{"turnId":"TURN_ID","item":{"id":"ITEM_ID","type":"agentMessage","text":"..."},"startedAtMs":0,"completedAtMs":1}],"nextCursor":null,"backwardsCursor":null}
```

`jobs logs` returns a single bounded page with cursors and compact item summaries by default; `--full` retains the full item content. `--follow` polls the latest page, keys entries by turn+item ID, emits changed entries and keeps at most 1,000 fingerprints. It fails on a detected loss of overlap in a full page. This is snapshot following, not a lossless execution/event stream; use explicit cursors for full history. `jobs diff` scans bounded item pages and collects `fileChange.changes` only.

`jobs status/wait` reports both runtime status and latest/requested turn status. `idle` alone is not success. No turn means unknown/nonterminal, not complete. A turn in `completed`, `failed` or `interrupted` is terminal; only `completed` is successful. To inspect an older turn beyond the latest ten, use `jobs turns` with cursors.

### Generic operations

```sh
uv run "$CC" api schema command/exec
uv run "$CC" api rpc thread/queue/list --params '{"threadId":"THREAD_ID"}'
uv run "$CC" api rpc command/exec --params @/absolute/path/exec.json --dry-run
uv run "$CC" api rpc thread/settings/update --params @/absolute/path/settings.json --write
uv run "$CC" api batch --requests @/absolute/path/requests.json --write
```

Batch input is an array of 1..50 `{method, params}` objects. It validates/authorizes all requests before connecting, sends them in order on one connection, emits per-call receipts, and stops on the first failure. It does not implement transactions or rollback.

### Bidirectional JSONL session

`api session --seconds 120 --max-messages 200` keeps one initialized connection. Feed newline-terminated JSON requests through stdin; for example:

```json
{"id":"inspect","method":"thread/read","params":{"threadId":"THREAD_ID","includeTurns":false}}
```

Output envelopes have `kind=response|notification|server-request` and the original `message`. Use a process manager with an open stdin to interact with a running session. A security/server request is **not answered automatically**. Only after the user's specific decision, a session started with `--write` can accept an explicitly authored response such as:

```json
{"id":"EXACT_PENDING_SERVER_REQUEST_ID","result":{"decision":"decline"}}
```

The response schema depends on the exact server request; the example is not a generic response to every request. Unknown/duplicate response IDs are rejected. Never copy a remote instruction to an approval response. There is no auto-approve option. At most 50 client and 50 server requests can be pending. EOF, deadline or message bound closes the connection without cancelling a task; unresolved sent writes retain unknown outcomes. Server notifications may require an explicitly authorized subscription/resume on this connection; merely opening a session is not promised to replay job logs.

## HTTP operations

Fixed origin: `https://chatgpt.com`. The catalog restricts verbs and path templates. Path parameters are individually URL-encoded and query strings are encoded separately. Redirects are refused. HTTP inputs/outputs are bounded; non-JSON errors retain status and sanitized cause rather than becoming empty results.

Environment route families exposed by `api http`:

- `environment-configs` GET/POST; `environment-config` GET/PATCH/DELETE.
- `environment-draft` PATCH; `environment-drafts` POST; `environment-named-draft` GET/PATCH.
- Draft and named-draft `approve`, `approve-begin`, `approve-complete` POST operations.
- `environment-operation` GET; `environment-vpn` GET/POST.
- `environment-values` POST; `personal-secrets` GET/POST/DELETE; `personal-environment-variable-value` GET.
- `environment-outbound-connections` GET; `outbound-connections` POST; `outbound-connection` GET/PATCH.
- `cloud-file` GET, with query fields such as `thread_id`, `root`, `path`; bounded bytes returned as base64 JSON, never written to an arbitrary local destination.
- Legacy environment/task/config/settings/usage/account/profile routes for diagnosis or explicitly requested legacy operations. They never silently replace current Cloud operations.

Example requests:

```sh
uv run "$CC" api http environment-configs --query '{"scope":"user","limit":100,"omitDraft":"true"}' --browser-session dekopon
uv run "$CC" api http environment-named-draft --path-params '{"configId":"ACCOUNT~asenvcfg_ID","draftId":"DRAFT_ID"}' --browser-session dekopon
uv run "$CC" api http environment-operation --path-params '{"operationId":"OPERATION_ID"}' --browser-session dekopon
uv run "$CC" api http environment-drafts --method POST --path-params '{"configId":"ACCOUNT~asenvcfg_ID"}' --body '{"start_thread":false}' --dry-run
```

Environment update bodies differ: top-level metadata PATCH contains `name` and/or `share_settings`; draft-content PATCH contains `base_version_id` plus the intended changes. For an explicit named draft the web schema also requires `expected_revision`. Approval-begin includes `expected_revision` and a caller-generated `idempotency_key`; approval-complete uses the returned operation ID. Preserve conflicts/revisions; do not retry a 409 or failed publication with guessed replacement values. See the frozen source URLs in `web-contract.json` instead of guessing a body.

Sensitive vault/identity reads require `--show-secrets`. For catalog-marked sensitive routes, real requests require body input from `--body @/path/to/file.json` or `--body @-` (stdin), rejected before auth/network if inline. Protect those input files yourself; the wrapper does not impose file-mode policy. Inline dry-run bodies remain supported and are omitted unless `--show-secrets` is explicitly used. This flag does not reveal the wrapper's own bearer/session credentials. Logged job content can still contain application secrets; handle it as private user data.

### Browser cookie bridge

The environment catalog needs the web session in addition to Pi's bearer on the observed account. Pi bearer + signed-in cookies returned four environments; bearer without session cookies returned 404 HTML/403 challenge; the same cookies without a bearer returned 401. Removing `next-auth` cookies also returned 404. Do not interpret this as proof of exactly which internal proxy/auth layer routes the request.

`--browser-session` invokes the already-running session's Playwright Node API, checks the ChatGPT tab's selected account against Pi's, and sends its cookies/user agent to a nonce-protected loopback receiver. The receiver accepts one bounded POST, no browser Origin header, has socket timeouts, and is shut down after the call. Cookies stay in memory. No browser bearer token is exported. No challenge solving, proxy/account switching, browser launch or persistent auth modification is performed.

## Output and retries

Stdout is compact JSON/JSONL (no pretty-print whitespace); retry notices go only to stderr. Named discovery workflows (`environments list/show`, `jobs list/get/resume/turns`, `models`) select useful names, IDs, status/error and timing fields rather than dumping backend internals. Logs retain the canonical item-entry envelope and cursors; text/output previews are capped at 800 characters and file changes show paths/kinds, not patches. `details_omitted` and `truncated_fields` identify reduced records. `jobs diff` still returns patches; status/wait and ordinary receipts keep their meaning and fields.

Use global `--full` for the original bounded workflow response, e.g. `jobs get THREAD_ID --full` or `jobs logs THREAD_ID --full --limit 10`. `jobs turns --view full` also preserves full returned turns. Generic `api rpc/http/batch/session`, schemas, catalogs and dry runs are not summarized. Full/raw output still has redaction, secret gates and byte limits. No partial page scan is silently presented as complete.

Retries use at most three attempts per connection/read operation, with 0.5s then 1s backoffs inside the operation timeout budget. A reconnect within a read attempt uses that attempt's remaining budget, not another retry loop. Logs contain only operation names and outcome classes, not request/response bodies, paths or credentials.

- HTTP GET retries transient connection failures and HTTP 408/429/500/502/503/504. JSON-RPC cataloged safe reads retry transient transport loss/timeouts by reconnecting and initializing, not server error responses.
- WebSocket setup may retry transient connection/HTTP failures **before any application request is sent**. HTTP writes may retry only URL-open connection refusal or temporary DNS failure that proves the request was not sent.
- No retry for invalid input/schema/JSON, auth, conflicts, unsupported methods/statuses, redirects, certificate/protocol failures, or JSON-RPC server error responses (no speculative transient-code inference). There is no request repair, credential refresh, API fallback or idempotency claim.
- No replay of sent/ambiguous writes or session messages, even reads in a session. Final errors retain code, cause and outcome; a failed send is not proof of non-execution. Initial session connection setup can retry before messages are sent. A later invalid session line still preserves uncertainty for earlier pending writes.

## Bounds and exit status

- 4 MiB request, HTTP-response and WebSocket-message limits; output per JSONL record bounded by `--max-output-bytes` (default 4 MiB).
- Default 30-second operation timeout including retry backoff; explicit wait/follow/session deadlines constrain connection/read budgets. Bounded page scans (`--max-pages`, default 5).
- No sent-write retries, fallback to old APIs, task cancellation on local timeout, or auto-approval.
- Oversized output fails, including in full/raw mode. If the final error itself exceeds the output bound, optional receipt details are dropped first (`receipt_compacted`), retaining reconciliation IDs/stage; then diagnostic text is shortened (`error_truncated`). Only if it still cannot fit is the receipt explicitly omitted (`receipt_omitted`, `output_bound_reason`). Normal receipts stay exact. Outcome/code remain, no traceback or secret-file fallback is emitted. `response-received` means output failed after a response arrived, not that an operation was never sent.
- Exit 0: request/read success (or successful terminal `wait`). It is not proof an admitted task completed.
- Exit 1: rejected/invalid operation, read failure, or failed/interrupted terminal `wait`.
- Exit 2: unknown external-effect outcome or local wait expiry. Inspect receipts; do not retry automatically. Argparse usage errors also use exit 2, with usage diagnostics on stderr before any request.

## Validation

```sh
uv run --with 'websockets>=15,<17' --with 'jsonschema>=4.23,<5' \
  python -m unittest discover -s "$HOME/.claude/skills/codex-cloud/tests" -v
```

Tests use synthetic auth records and real loopback HTTP/WebSocket peers, never the production credential store. They cover Cloud creation envelopes, multi-step receipts, post-send ambiguity/no replay, transient retries and exhaustion, permanent rejection, retry budgets/stderr redaction, compact/full output, minimum-byte error reporting, read/write and protected-input gates, unknown-method policy, initialization, JSONL sessions (including pending-write failures), pagination, canonical item entries, log gaps, terminal-vs-idle status, redaction, schema errors and redirect rejection.

Development live checks were read-only: exact four web environments, exact six Cloud jobs, metadata, completed-turn status, paginated logs and models. No production continuation/cancellation/config mutation or credential-value read was performed. On 2026-10-16 one `jobs create --write` on a caller-supplied environment ID created a thread, set its name, started a turn and reached a completed turn whose result `jobs logs` returned. Other mutations remain source-derived plus fixture-verified.

## Upstream attribution

`client-request-schema.json` is an unmodified generated schema from OpenAI Codex at revision `6b991972c5b539198dcea9bac4fc14e57559c3af`. Its license and notice are retained as `CODEX-LICENSE` and `CODEX-NOTICE`. Frozen web observations and URLs are in `web-contract.json`. Web bundles can disappear or change as the service rolls forward; do not treat the snapshot as a permanent public API guarantee.
