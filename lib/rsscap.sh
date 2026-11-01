#!/usr/bin/env bash
# rsscap.sh MAX_MB TIMEOUT_S -- command...
# Sample resident memory across the command's new session, including nested process
# groups (for example GNU timeout). A descendant that creates a new session escapes
# this cooperative guard; it is not a security boundary or an instantaneous limit.
# Exit: command status; 137 for memory; 124 for time; 2 for invalid/unreadable input.
set -uo pipefail
if ! { [ $# -ge 4 ] && [ "$3" = "--" ] && [[ "$1" =~ ^[1-9][0-9]{0,8}$ ]] && [[ "$2" =~ ^[1-9][0-9]{0,8}$ ]]; }; then
  echo "usage: rsscap.sh MAX_MB TIMEOUT_S -- command... (positive integers, at most nine digits)" >&2
  exit 2
fi
max_mb=$1; tmo=$2; shift 3
# No job-control process group for the background child: setsid keeps this PID as SID.
set +m
setsid "$@" &
pid=$!
start=$SECONDS
peak=0

session_rows() {
  ps -eo sid=,pgid=,stat=,rss= | awk -v session="$pid" '$1 == session && $3 !~ /^Z/ {print $2, $4}'
}

# Invoked by the EXIT trap, including signal and limit exits.
# shellcheck disable=SC2329
cleanup() {
  local rows groups group round
  trap '' HUP INT TERM
  # The launcher may not have entered its session yet. Stop it as well as every
  # observed group; never select by process name or another session's ancestry.
  if jobs -pr | grep -qx "$pid"; then kill -KILL "$pid" 2>/dev/null || true; fi
  for ((round=0; round<10; round++)); do
    rows=$(session_rows) || { echo 'rsscap: could not read session during cleanup' >&2; exit 2; }
    [ -n "$rows" ] || break
    groups=$(awk '{print $1}' <<< "$rows" | sort -u)
    while read -r group; do
      kill -KILL -- "-$group" 2>/dev/null || true
    done <<< "$groups"
    sleep 0.05
  done
  rows=$(session_rows) || { echo 'rsscap: could not verify session cleanup' >&2; exit 2; }
  if [ -n "$rows" ]; then echo 'rsscap: session cleanup did not finish' >&2; exit 2; fi
  wait "$pid" 2>/dev/null || true
}
trap 'cleanup' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

while :; do
  rows=$(session_rows) || { echo 'rsscap: could not read session memory' >&2; exit 2; }
  # Keep watching after the leader exits: a background child still belongs to the
  # session, even after reparenting or moving to a different process group.
  if [ -z "$rows" ] && ! kill -0 "$pid" 2>/dev/null; then break; fi
  rss_kb=$(awk '{s += $2} END {printf "%.0f", s}' <<< "$rows")
  rss_mb=$(( (rss_kb + 1023) / 1024 ))
  [ "$rss_mb" -gt "$peak" ] && peak=$rss_mb
  if [ "$rss_kb" -gt $(( max_mb * 1024 )) ]; then
    echo "rsscap: STOPPED for memory: the session held ${rss_mb} MB, over the ${max_mb} MB limit" >&2
    exit 137
  fi
  if [ $(( SECONDS - start )) -ge "$tmo" ]; then
    echo "rsscap: STOPPED for time: over ${tmo} s (peak ${peak} MB)" >&2
    exit 124
  fi
  sleep 0.5
done
wait "$pid"; status=$?
echo "rsscap: exit ${status}, peak ${peak} MB" >&2
exit "$status"
