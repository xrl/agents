#!/usr/bin/env bash
# Start a long-lived pi in RPC mode behind a FIFO. Commands are JSON lines appended to $DIR/in;
# events stream to $DIR/events.jsonl. Watch that file for "agent_settled" to know a turn is over.
#
#   pi-rpc-start.sh <workdir> <state-dir> <session-id> <model[:thinking]>
set -euo pipefail
WORKDIR=$1; DIR=$2; SESSION=$3; MODEL=$4
mkdir -p "$DIR"; [ -p "$DIR/in" ] || mkfifo "$DIR/in"
cd "$WORKDIR"
# A writer held open on the FIFO keeps pi's stdin alive between commands.
( exec 3>"$DIR/in"; while [ -e "$DIR/keepalive" ]; do sleep 5; done ) &
touch "$DIR/keepalive"; echo $! > "$DIR/keepalive.pid"
nohup pi --approve --mode rpc --session-id "$SESSION" --model "$MODEL" < "$DIR/in" >> "$DIR/events.jsonl" 2>> "$DIR/pi.err" &
echo $! > "$DIR/pi.pid"
echo "pi rpc pid $(cat "$DIR/pi.pid"); commands -> $DIR/in; events -> $DIR/events.jsonl"
