#!/usr/bin/env bash
# Send one RPC command. Examples:
#   pi-rpc-send.sh <state-dir> prompt "Start stage 2"           # new turn (fails if streaming)
#   pi-rpc-send.sh <state-dir> steer  "Answer: keep ClientError" # delivered between tool calls
#   pi-rpc-send.sh <state-dir> follow_up "Now open the PR"       # after the current turn ends
#   pi-rpc-send.sh <state-dir> abort
#   pi-rpc-send.sh <state-dir> get_state
#   pi-rpc-send.sh <state-dir> ui <request-id> <value>          # answer a select/input request
#   pi-rpc-send.sh <state-dir> ui <request-id> confirm|deny     # answer a confirm request
set -euo pipefail
DIR=$1; TYPE=$2; MSG=${3:-}
ID="req-$(date +%s)-$RANDOM"
case "$TYPE" in
  prompt)    J=$(python3 -c 'import json,sys;print(json.dumps({"id":sys.argv[1],"type":"prompt","message":sys.argv[2]}))' "$ID" "$MSG");;
  steer)     J=$(python3 -c 'import json,sys;print(json.dumps({"id":sys.argv[1],"type":"prompt","message":sys.argv[2],"streamingBehavior":"steer"}))' "$ID" "$MSG");;
  follow_up) J=$(python3 -c 'import json,sys;print(json.dumps({"id":sys.argv[1],"type":"prompt","message":sys.argv[2],"streamingBehavior":"followUp"}))' "$ID" "$MSG");;
  ui)        REQ=$3; VAL=${4:-}
             J=$(python3 -c 'import json,sys
r,v=sys.argv[1],sys.argv[2]
d={"type":"extension_ui_response","id":r}
if v=="confirm": d["confirmed"]=True
elif v=="deny": d["confirmed"]=False
else: d["value"]=v
print(json.dumps(d))' "$REQ" "$VAL");;
  *)         J=$(python3 -c 'import json,sys;print(json.dumps({"id":sys.argv[1],"type":sys.argv[2]}))' "$ID" "$TYPE");;
esac
printf '%s\n' "$J" > "$DIR/in"
echo "$ID"
