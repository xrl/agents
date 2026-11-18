---
name: browse-flows
description: Drive a web UI from a script, not from model click-read loops. A flow file lists page states. The runner matches the live page to one state, acts, traces every step, and yields a decision packet to the owning agent when a page is unknown or ambiguous, then resumes. Use it to automate sign-ins, consents, admin consoles and app settings in a shared Playwright browser (playwright-cli), on the Mac or in a VM. It is not authority to click consent, payment or permission buttons: those always wait for the human.
---

# browse-flows

`scripts/browse_flow.py` runs a **flow**: a TOML file of page **states**. Each state has a `match` (host, path regex, visible text, required controls by role and name) and a `do` (click, fill or press). The runner loops:
1. fingerprint the page;
2. match exactly one state;
3. act;
4. append a trace step.

It continues until a `done` state or a **yield**. States match on what the page shows, not on step order, so any run resumes from wherever the page is, and an unexpected popup is just a page with no state yet.

Stdlib Python 3.11+ (`tomllib`). It drives an existing `playwright-cli` session through `run-code`; that function is sandboxed, so nothing in it reads files or the environment.

## Run

```sh
BF=$HOME/.claude/skills/browse-flows/scripts/browse_flow.py
python3 -I "$BF" check flows/openai-codex-device.toml
python3 -I "$BF" run flows/openai-codex-device.toml --tab <purpose-tab> --var user_code=ABCD-EFGHI [--dry-run]
```

- **`--tab`:** a purpose controller whose current tab carries `window.name == <tab>`, for example from campaign-trail's `claude-tab.sh <name> <url>`. The runner refuses `dekopon` (the owner's controller) and any tab whose name doesn't match.
- **`--dry-run`:** fingerprint and match only, never acting or navigating. It doubles as the read-only preflight before a live run.
- **Traces** go to `--trace-dir` (default `~/.cache/browse-flows/<flow>-<ts>/`, 0700): `trace.jsonl`, `yield.json`, `decision.json` and `learned.jsonl`.

Exit codes: **0** done, **75** yielded, **3** aborted, **4** owner timeout, **2** usage or flow error.

## Yield and resume

The runner yields when:
- no state matches, or more than one does;
- the host is off the flow's allowlist;
- an action's target isn't unique;
- the page doesn't change after acting twice;
- a `secret` state needs a value;
- or `--max-steps` is reached.

It writes `yield.json`: the reason, the page (host, path, headings, numbered controls `[n, role, name]`) and its signature. Then it exits 75. To wait without blocking, run the command in the background and read `yield.json` when it exits.

The owning agent reads the packet, decides, and answers with one command:

```sh
python3 -I "$BF" decide <run-dir> --click N           # or --fill N --var NAME
python3 -I "$BF" decide <run-dir> --owner --says "approve the prompt in the tab"
python3 -I "$BF" decide <run-dir> --learn state.json  # a new state, applied now and kept for this run
python3 -I "$BF" decide <run-dir> --abort
```

Then it reruns the same `run` command with `--run <run-dir>`. A resumed run never navigates; it picks up on the live page. A decision is bound to the page signature, including control order, so it is ignored if the page has moved on (traced as `decision-stale`).

The runner refuses an agent's `--click` or `--fill` on a page that matches an owner-kind state, or that is off the host allowlist (traced as `decision-refused`), and waits for the owner instead.

**A secret state** yields `secret fill`. Fill the field out of band with your own clipboard helper, then `decide --click <submit>` and resume. Nothing about a secret page's controls or headings is traced.

**Learning:** a `--learn` state lands in `learned.jsonl`. Copy it into the flow file in a reviewed commit, so the next run doesn't yield there. Yields per run is the metric; a flow is settled after several consecutive runs with none.

## Flow file

```toml
name = "openai-codex-device"
hosts = ["auth.openai.com"]          # allowlist: any other host yields
start = "https://auth.openai.com/codex/device"
capture_headings = true              # false where headings can hold secrets (some consoles print passwords)

[vars.user_code]
required = true
pattern = "^[A-Z0-9]{4}-[A-Z0-9]{4,6}$"

[[state]]
id = "code-entry"
kind = "nav"                         # nav | dismiss | consent | payment | permission | owner | secret | done
match = { path = "^/codex/device", controls = [{ role = "textbox" }], text = ["enter code"] }
do = [{ fill = { role = "textbox", var = "user_code" } }, { click = { role = "button", name_re = "^Continue$" } }]
```

- **Controls** are addressed by `role` plus `name` (exact) or `name_re` (regex), and must resolve to exactly one visible control. Roles: `button`, `link`, `textbox`, `password`, `searchbox`, `combobox`, `checkbox`, `radio`, `menuitem`, `menuitemradio`, `option`, `tab`.
- **`text`** holds case-insensitive substrings checked inside the page. Body text never leaves the page.
- **`do`** steps: `click`, `fill` (non-secret `var` only), `press = "Enter"`, `wait = 2`. A `click` or `press` must be the last step: it can change the page, and later steps would address stale controls.
- **One fingerprint per act.** Each act re-checks, in the same `run-code` call, that the control is still the expected role and name and that the tab is still the named one; otherwise it yields. The runner never acts twice on an unchanged page.
- **Browser permission prompts** (notifications, clipboard) are browser UI outside the page, so no fingerprint sees them. Grant or deny them once by hand per site; per-flow permissions are a later slice.

## Policy, enforced by the runner

- **Auto-acting kinds:** only `nav` (moves a form forward) and `dismiss` (banners and tours). Each flow names its own controls.
- **Owner kinds:** `consent`, `payment`, `permission` and `owner` states never act. The runner prints `OWNER: <owner_says>` and waits for the page to change, up to `--owner-timeout`. A flow file that gives one of these a `do` is refused.
- **Secrets never enter page code.** `secret = true` vars are refused, because `playwright-cli` echoes the code it runs. A `secret` state yields, so the agent fills it with its own clipboard helper. A state marked `secret = true` traces roles without names.
- **No snapshots and no downloads.** `run-code` writes neither. Raw `playwright-cli` output stays in memory, and only a first error line reaches stderr.
- **Tab name:** a cross-site sign-in by the owner clears `window.name`. During an owner wait the runner accepts an unnamed tab and stamps it again once it's back on an allowlisted host. Any other name is refused.

## Flows live with their repository

The skill ships the generic runner and one example flow, `flows/openai-codex-device.toml`. Its page map comes from live runs of an earlier helper, and the runner itself was validated live on its account and consent pages on 2026-11-18. Private flows stay in their own repositories: campaign-trail `tools/cloud-env/flows/`, rpi-homelab `skills/*/flows/`. Migrate an existing helper by writing its states, running `--dry-run` on each page, and then running it live with the owner watching.
