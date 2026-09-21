#!/usr/bin/env bash
# Stop the RPC pi and its FIFO keepalive.   pi-rpc-stop.sh <state-dir>
set -uo pipefail
DIR=$1
rm -f "$DIR/keepalive"
[ -f "$DIR/pi.pid" ] && kill "$(cat "$DIR/pi.pid")" 2>/dev/null
[ -f "$DIR/keepalive.pid" ] && kill "$(cat "$DIR/keepalive.pid")" 2>/dev/null
echo stopped
