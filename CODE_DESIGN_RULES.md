# Code & API design

Read before implementation or code review. **Keep one authority, preserve causes,
bound resources, reuse safely, require real consumers, and test behavior.**

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

### 41. Tests pin behavior and failure causes, not implementation details.

Name tests for the behavior they guarantee and keep them beside the owning
code. Exercise failure paths and assert that the surfaced error or diagnostic
retains the cause, rather than merely asserting failure. Pin stable CLI output
where it is a contract. Use loopback mock peers; never depend on another
application's real credential store.

### Rust-specific applications

- Never hold tracing `Entered`/`EnteredSpan` guards across `.await`; use
  `.instrument(span)` or a synchronous `in_scope` instead.
- Avoid panics on user input, unnecessary async dependencies, and public APIs
  based on `anyhow`; expose errors callers can act on. Avoid `unsafe` unless a
  justified requirement and documented safety invariants warrant it.
- Preserve project lint policy. Any justified allowance is site-scoped and
  explains why it is safe, not widened to a module or crate for convenience.

Source: the snapshot above, **Change guidelines** and **Review checklist**.
Do not copy Dekopon's full lint configuration.

