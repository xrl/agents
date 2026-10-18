#!/usr/bin/env bash
# PreToolUse hook for the lanes' Bash tool. Permission rules match the unparsed command text, so a
# git command spelled with a quote, backslash, $, backtick or brace could hide `--output` from the
# deny; such a command is refused, and the lanes' git reads never need one.
cmd=$(jq -r '.tool_input.command // empty')
if [[ $cmd =~ (^|[^[:alnum:]_./-])git([[:space:]]|$) && $cmd == *[\'\"\\\$\`\{]* ]]; then
  echo "refused: write git commands without quotes, backslashes, \$, backticks or braces" >&2
  exit 2
fi
exit 0
