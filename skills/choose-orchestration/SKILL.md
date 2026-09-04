---
name: choose-orchestration
description: Choose direct execution, pi-subagents, or Dynamic Workflows using task shape, supervision needs, tooling, and recovery requirements. Use when comparing the engines, recommending one for a task, or deciding how to delegate when the choice is unclear. Not for managing an existing run, and not permission to launch agents.
compatibility: Pi with pi-subagents and/or @quintinshaw/pi-dynamic-workflows. Verify installed capabilities before execution.
metadata:
  version: "1.0.0"
---

# Choose an orchestration engine

**Default:** stay direct for focused work; prefer **pi-subagents for supervised coding delegation** and **Dynamic Workflows for repeatable analysis pipelines**. These are preferences, not exclusive capabilities.

## 1. Separate selection from execution

- Answer questions, comparisons, and requests for a recommendation directly. Loading this skill does not itself authorize a run. A request to recommend an engine is not a request to execute the example task.
- Skip delegation for a small edit, a straightforward investigation, or work without useful independent assignments. Task size alone does not justify a fleet.
- Honor an explicit engine preference when it fits the task and available capabilities. If it cannot do the job, explain the mismatch rather than silently changing engines.
- **Dynamic Workflows requires explicit user opt-in:** workflow-trigger arming, `/workflows run`, or an unambiguous request such as "run a workflow" or "fan this out." Arming permits execution; it does not force it for questions or trivial tasks. Without opt-in, offer it with a rough cost implication instead of calling `workflow`. Do not use another engine to evade a user's restriction on delegation.
- Keep one engine responsible for each logical job. Do not nest orchestration engines by default. For an existing job, use its owning engine's status/control interface rather than starting a replacement.

## 2. Decision matrix

Apply authorization and capability requirements first, then choose by the strongest task requirement.

| Task or decisive requirement | Prefer | Reason / condition |
| --- | --- | --- |
| Explain something, make a small edit, or follow one narrow investigation | Direct | Delegation would add handoff overhead without independent evidence. |
| Get a bounded second opinion or ask a named scout/reviewer/oracle | pi-subagents | A focused specialist handoff does not need a full pipeline. |
| Implement, validate, get fresh reviews, then revise | pi-subagents | Parent-supervised worker/reviewer cycles suit evolving implementation work. |
| Use the conversation so far, or deliberately choose fresh versus forked context | pi-subagents | Explicit child-context controls. Prefer fresh context for independent review. |
| Redirect a running child or let it ask the parent for a decision | pi-subagents | Live steering and the native supervisor channel. |
| Use extension/MCP/browser tools or a supported external CLI agent | pi-subagents | Configurable integrations; verify providers, allowlists, and runner support first. |
| Audit many independent surfaces, cross-check findings, and deliver one report | Dynamic Workflows | Fan-out, verification, and synthesis form a clear bounded pipeline. Requires opt-in. |
| Research distinct approaches or perspectives and synthesize the evidence | Dynamic Workflows | Independent evidence streams and a shared synthesis step; confirm research tools exist. Requires opt-in. |
| Reuse verification, judging, bounded discovery loops, or curated audit/research patterns | Dynamic Workflows | Packaged quality helpers and saved workflows avoid rebuilding the process. Requires opt-in. |
| Resume an expensive pipeline without rerunning its unchanged completed prefix | Dynamic Workflows | Journaled replay, including edit-and-resume for a changed tail. Requires opt-in. |
| Run a few parallel reviewers with different angles | Either; default pi-subagents | Choose Dynamic Workflows if its curated review pattern or replay is specifically useful and authorized. |

When signals conflict, required tools and supervision needs outweigh the broad "coding versus research" preference. For example, browser-dependent research may fit pi-subagents better; a read-only codebase audit may fit Dynamic Workflows better.

## 3. Understand the actual differences

These are **independent engines**, not a workflow layer backed by the pi-subagents extension. Both support JavaScript orchestration, parallel and sequential work, model selection, background execution, structured results, and Git worktree isolation. None of those features alone decides the choice.

### Dynamic Workflows: process-oriented

- Uses `agent()`, `parallel()`, and `pipeline()`, with phases, model tiers, saved workflows, and helpers such as `verify()` and `judgePanel()`.
- Journal replay is positional: keep earlier good `agent()` calls unchanged and in the same order. Editing/inserting/reordering a call invalidates reuse from that point onward; it is not arbitrary per-step caching.
- Cached results do not roll back file edits or prove external state is unchanged. Revalidate state-sensitive evidence before trusting replay.
- Background runs are managed in the Pi process; process exit uses the pause/journal recovery path rather than detached execution.

### pi-subagents: specialist- and supervision-oriented

- Uses `{ agent, task }` for one child; `workflowScript` with `runs.run()`, `runs.all()`, or staged `runs.lanes()` for orchestration.
- Provides configurable agent profiles, fresh/forked context, individual child inspection and continuation, steering, supervisor questions, and implementation acceptance checks.
- Async native children run in a detached runner process. Foreground native children run inside the parent process.
- Supported external CLI agents have their own runner contracts; native Pi model/context/tool/schema options are not automatically supported by them.

### Tool availability can decide the route

Capability baseline: Dynamic Workflows **3.10.1**, pi-subagents **0.65.0**. Treat the installed tool schemas and documentation as authoritative after upgrades.

- Dynamic Workflows uses extension-free child resource loading. Host-extension tools, including ambient MCP/browser tools, do not automatically carry over. Its coding tools and explicitly supplied toolsets remain available.
- pi-subagents supports configured child extensions and tool allowlists. Background children can load ambient extensions; foreground children do not. MCP and provider-extension agents require background execution in this baseline.
- Listing a tool name does not load its provider. Verify both availability and permission before choosing a route that depends on it. An engine label is not a capability or security guarantee.

Neither engine is inherently cheaper. Agent count, duplicated context, model choice, and repeated investigation dominate cost; journal replay can avoid paying again for completed work.

## 4. Hand off to the selected engine's instructions

Do not reproduce a full orchestration runtime here. Once execution is requested and the route is selected:

- **Direct:** do the work with ordinary tools. Do not launch a scout merely to justify staying direct.
- **pi-subagents:** load the installed `pi-subagents` skill and its relevant references. Before execution, call `subagent({ action: "list", capabilities: true })`; select only executable, non-disabled agents. External CLI agents also require `runner.available === true`, which is a passive executable check, not proof of authentication or successful launch. Use one direct child call for a bounded handoff. For multi-step/parallel work, make one top-level `workflowScript` call with `async: true` and launch children inside it.
- **Dynamic Workflows:** confirm opt-in. Load `workflow-patterns` for a built-in pattern; for a custom script, load `workflow-authoring` and `workflow-spawn-guardrails` when available. Use `workflow` for execution and `workflow_control` for lifecycle management. Do not invent agent types or model identifiers.

For either engine, establish the final deliverable, independent assignments, required tools, edit boundaries, and stopping evidence. Keep one writer per cwd/worktree and preserve existing dirty work. Use the smallest useful fan-out; do not invent token/spend caps that the user did not request. Follow the selected engine's current async completion and recovery rules.

## 5. Keep the routing explanation short

For a recommendation, return:

- **Choice:** Direct, pi-subagents, or Dynamic Workflows.
- **Why:** the one or two decisive requirements.
- **Next:** the direct action, bounded delegation shape, or missing opt-in/capability. Do not launch work just to answer the recommendation.

For an already-authorized task, one sentence explaining the route is enough before proceeding. Do not repeat the entire matrix every time.
