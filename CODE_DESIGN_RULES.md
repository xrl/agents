# Code & API design

Read before implementation or code review. **Keep one authority, preserve causes,
bound resources, reuse safely, require real consumers, test behavior, and keep
limits and contracts free of special cases.**

## The Service & API Rules

### 9. One authoritative API contract; poem-openapi for implementation-first Rust services.

Default to `poem-openapi` for implementation-first Rust HTTP APIs: handler types
and annotations generate the OpenAPI document. For contract-first APIs, the
agreed specification can instead generate server interfaces and clients, with
conformance tests for the implementation. Do not make independently maintained
code and specifications compete. CI must reject regeneration diffs for checked-in
generated contracts and enforce conformance to the chosen authority.

- `cheminee/src/rest_api/api/api_v1.rs:24-37` derives the API with `#[OpenApi]`
  and `#[oai(...)]`.
- `knievel/.github/workflows/ci.yml:162-169` runs
  `cargo xtask openapi --check`.

### 10. Generated clients live in their own repo. Upstream commits, downstream publishes. Same tag.

The server owns the spec and, on a tag, commits generated clients with that tag
to client repos. Each client repo builds and publishes itself. This separates
API source, generated artifact, and registry credentials while keeping bug
versions directly searchable.

- `cheminee/.github/workflows/generate_ruby_gem.yaml:65-83` generates and
  pushes to `cheminee-ruby`; that repo runs `rake release`.
- `knievel/.github/workflows/release.yml:299-315,362-369` generates from
  `openapi.yaml` and pushes to its client repo for publication.

## The Code & API Design Rules

These rules generalize Dekopon's contribution and review conventions. The
[source snapshot](https://github.com/dekopon-agents/dekopon/blob/4c91530f60ddb5113040ce78f29fd137e11b3f87/CONTRIBUTING.md#review-checklist)
is a policy receipt, not a claim that every implementation already complies.

### 34. Preserve error causes; report each failure once.

Return an error that names the failed operation and preserves its cause, or
record the cause at the point where the error is deliberately discarded.
Silent `map_err(|_| …)`, `let _ = fallible()`, and multi-cause checks collapsed
into a bool lose the evidence needed to debug. Avoid logging the same failure
at every propagation layer; choose the reporting boundary. Preserve diagnostic
meaning without exposing credentials or sensitive payloads.

- Add context; never erase causes or downgrade error specificity.
- Typed errors at library/caller-decision boundaries; `anyhow` at application boundaries.

### 35. Classify errors by the decision callers must make.

Model retryable versus permanent failures and executed versus not-executed
outcomes where callers need those distinctions. Preserve an unknown outcome
when an external effect may have happened; a timeout is not proof it did not.
Never label permanent exhaustion transient or exit successfully with essential
daemon work dead.

### 36. Report all validation conflicts together.

For authored configuration, collect independent conflicts and return them in
one diagnostic pass. Never silently use last-wins duplicate keys. A malformed
structure or unsafe dependency can prevent further checks; stop those checks
rather than inventing secondary errors. Keep diagnostic work and output bounded.
Test at least two simultaneous independent conflicts and assert both are reported.

### 37. Bound everything that grows or blocks; give it an owner.

Set limits for retained state and peer-controlled allocations. Enforce claimed
lengths rather than trusting them when preallocating. Give threads, connections,
and network reads an explicit lifecycle, deadlines where they can stall, and
an observer for failure or exit. State retained across turns needs eviction or
deduplication; deduplication alone does not bound unique entries.

- Top-down, acyclic ownership; one lifecycle owner per task or resource.
- Observe task exits and failures; detached work needs explicit justification and an owner.
- Cancellation must preserve external-effect outcomes, including uncertainty.
- Bound allocation, admission and retention at their owners; reuse existing bounds.
- No scattered defensive checks; input validation does not bound retained state.
- Keep blocking I/O and heavy CPU work off async executor threads.
- Bound admission before offloading; `spawn_blocking` is neither a queue bound nor running-work cancellation.

### 38. Construct expensive reusable resources once, not per request.

Reuse HTTP/model clients, Wasmtime engines, linkers, compiled components, and
workers at the process or session scope that owns them. Reuse must respect
credential, tenant, concurrency, and lifecycle boundaries; do not turn
request-specific mutable state into a global singleton.

### 39. New public surface needs a real consumer now.

A new production public item, production dependency, config field, or error
variant needs a non-test consumer in the same change. Development dependencies
need an actual test, benchmark, or tooling consumer in that change; they need no
artificial production use. Otherwise keep it private or delete it: parsed but
unread configuration and unreachable variants are not useful scaffolding.
For a library whose consumers ship separately, an explicit supported external
use case and contract tests are the named exception; speculative extensibility
is not.

### 40. Keep one definition per fact; test unavoidable mirrors.

Share the authoritative definition rather than maintaining a second validator
or constant by hand. When a packaging or trust boundary requires a mirror,
carry an equality-pinning or conformance test. A mirror must not accept what
the authority rejects. Sharing a definition is not permission to collapse
otherwise independent security boundaries.

- Validate at trust boundaries; carry validated types and trust invariants internally.
- Newtypes prevent dangerous or confusing mix-ups, not merely wrap strings.
- Validate output at contract/security boundaries, not after every transformation.

### 41. Tests pin behavior and failure causes, not implementation details.

Name tests for the behavior they guarantee and keep them beside the owning
code. Exercise failure paths and assert that the surfaced error or diagnostic
retains the cause, rather than merely asserting failure. Pin stable CLI output
where it is a contract. Use loopback mock peers; never depend on another
application's real credential store.

### 46. Limits are resources, never call sites.

Anything that can be run can be run from anywhere: a user's script, a plugin, a
nested plugin, a background job. Bound memory, time, output and a call budget,
shared by the whole tree of work; never "this works here and not there". Users
of an agent platform are models, and every call-site rule is one they discover
by failing. Authority is not a call site: authorize every effect for the
principal, at any depth. Differences that survive a release are named in its
notes so that nobody discovers them.

- **Receipt, dekopon, 2026-09-28:** a first design carried seven call-site
  rules (per-plugin spawn grants, a child counter, a depth limit, jobs as a
  model-only tool). One mechanism, a plugin handing a script to its caller,
  removed all seven and the grant lists with them.

### 47. One shape per contract; compatibility is a constraint only when someone set it.

A contract that offers a whole answer beside a stream, or a buffered call
beside a streaming one, is a permanent second code path, which is worse than a
shim. Offer the stream; give callers who want a whole value one bounded helper
over it. Before designing around a break, ask who set compatibility as a
constraint and what breaking it would delete. Where one owner controls every
consumer, move them all in one release.

- **Receipt, dekopon, 2026-09-28:** a plan avoided an interface break to spare
  a fleet re-release and paid with a second code path and a manifest opt-in.
  The owner's answer was to break it; nobody had asked for compatibility.

### 48. Telemetry is typed, conventionally named and best effort.

Use the OpenTelemetry semantic-convention name where one exists. Numbers are
numbers. A list is an array under a fixed name, with parallel arrays for pairs;
redaction replaces a value and keeps its position. Data never becomes an
attribute name and a map is never sent: every distinct name is a column in the
store. Nothing long-lived is one span; record a start and an end and link them.
Delivery is best effort: a full queue drops and counts, and nothing in a
serving path waits on an exporter. Depth is the owner's dial, per category, and
the thing being recorded never chooses it.

- **Receipt, rpi OpenObserve, 2026-09-29:** map attributes became one column
  per key; span scalars were stored as strings while log records kept their
  types; a span that started over five hours before it was sent was rejected
  with only a log line.

### Rust-specific applications

- Never hold tracing `Entered`/`EnteredSpan` guards across `.await`; use
  `.instrument(span)` or a synchronous `in_scope` instead.
- No production `.unwrap()` or `.expect()`; both are welcome in tests.
- Propagate causes, handle absence, or encode invariants; no panic or silent-fallback evasions.
- No panics on user input; avoid unnecessary async dependencies.
- `unsafe` requires justification and documented safety invariants.
- Preserve project lints; prefer site-scoped `#[expect(..., reason = "...")]` over `#[allow]` for permitted exceptions.
- Deny `unfulfilled_lint_expectations`; remove stale exceptions.
- No lint exceptions to the production `.unwrap()`/`.expect()` ban.

Source: the snapshot above, **Change guidelines** and **Review checklist**;
subsequent owner clarifications refine these rules.
Do not copy Dekopon's full lint configuration.

