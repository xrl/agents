# Claude Code CLI as the MCP client on a PR site

The MCP proof is the CLI a human will use, a browser password login, and the real consent page. A
server-minted Devise session with a preset org passed overnight and hid that every human token acted as
Backoffice 175 (0 rows for the first real tester). mcporter (`~/code/assaydepot/overnight-20261105/mcp-harness/`)
is allowed only to cross-check raw tool JSON, never as the proof.

`S=~/.claude/skills/rx-pr-site/scripts`, `N` = PR number, server name `reveal-pr-$N`,
URL `https://reveal.pr-$N.pull-requests.scientist.com/mcp`.

## 0. Pre-flight

```sh
curl -s https://reveal.pr-$N.pull-requests.scientist.com/.well-known/oauth-protected-resource | python3 -I -m json.tool
```

Both `resource` and `authorization_servers` must name `pr-$N`. If they name `backoffice.scientist.com`, the
site has no `RX_DOMAIN` (rx#43421) and the client would do OAuth against production: stop.

## 1. Scratch config, one per persona

```sh
T=$(mktemp -d); chmod 700 $T; mkdir $T/cfg $T/proj
security dump-keychain 2>/dev/null | grep -o '"Claude Code-credentials-[0-9a-f]*"' | sort -u > $T/keychain.before
cd $T/proj && CLAUDE_CONFIG_DIR=$T/cfg claude mcp add --transport http --scope local reveal-pr-$N https://reveal.pr-$N.pull-requests.scientist.com/mcp
```

`--scope local` binds the server to `$T/proj`, so every later command runs from there.

## 2. Login under a pty, consent in playwright

```sh
python3 -I $S/mcp_login_pty.py --server reveal-pr-$N --config-dir $T/cfg --cwd $T/proj \
  --log $T/login.out --url-file $T/authorize.url --timeout 900      # run_in_background
```

`claude mcp login` refuses without a TTY, `script -q` with a fifo stdin dies silently, and a `nohup`'d
login dies when the Bash call ends (the consent redirect then hits chrome-error). The driver keeps it alive
and writes the authorize URL as soon as the CLI prints it.

In the persona's playwright session (rx-browser registry slot, already logged in on
`backoffice.pr-$N.pull-requests.scientist.com` as that persona): open `$(cat $T/authorize.url)`, check the
page names the persona and the acting org, click Authorize. The CLI's localhost callback finishes the login;
the driver prints `{"exit":0,...}`. A refusal page (viewer, org admin without Reveal, masquerading) is the
expected result for those roles: capture it as the check's evidence.

## 3. Prompts

The scratch dir has MCP auth but no model login ("Not logged in"). Run the model on Bedrock, restricted to
the one server, and keep every transcript:

```sh
cd $T/proj && CLAUDE_CONFIG_DIR=$T/cfg CLAUDE_CODE_USE_BEDROCK=1 AWS_PROFILE=scientist AWS_REGION=us-east-1 \
  timeout 400 claude -p "<prompt>" --tools '' --allowedTools mcp__reveal-pr-$N --max-turns 12 \
  --output-format stream-json --verbose < /dev/null > <evidence>/<check>.jsonl 2> <evidence>/<check>.stderr
```

Write the exact command (with `<scratch>` for the dir) beside each transcript as `<check>.prompt.txt`.
Prompts ask in plain words, as the role would ("how many rows per month does bz_a have in
reveal_customer_daily_metrics?"); the pass condition is the rows **and** the org the answer says it acted as.
A tool result over the CLI's inline cap is saved to a file an MCP-only client cannot open: record that as a
product gap, not a pass (an unpaged `list_dashboards` of 500 rows is ~49 KB).

Claude Code 2.1.318 probes `MCP-Protocol-Version: 2026-07-28`; the server answers 400 and the client falls
back to 2025-11-25. Harmless.

## 4. Switch persona

Never reuse a config across personas. `claude mcp logout`, then a new scratch dir and a fresh browser
session (or log the old persona out of Backoffice first). Consent acts as whoever the browser is logged in as.

## 5. Clean up (every scratch dir)

```sh
cd $T/proj && CLAUDE_CONFIG_DIR=$T/cfg claude mcp logout reveal-pr-$N; CLAUDE_CONFIG_DIR=$T/cfg claude mcp remove reveal-pr-$N
security dump-keychain 2>/dev/null | grep -o '"Claude Code-credentials-[0-9a-f]*"' | sort -u | comm -13 $T/keychain.before - \
  | tr -d '"' | while read -r s; do security delete-generic-password -s "$s" >/dev/null; done
rm -rf $T
```

The consent's Doorkeeper token stays on the PR site until its expiry; that is fine on a clone that will be
torn down, and worth one journal line.
