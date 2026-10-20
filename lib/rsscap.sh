#!/usr/bin/env bash
# rsscap.sh MAX_MB TIMEOUT_S -- command...
# Runs the command in its own process group and stops the whole group when the
# group's resident memory passes MAX_MB or the run passes TIMEOUT_S.
# For programs an address-space cap (ulimit -v) breaks, such as vite and vitest.
# Exit: the command's own status; 137 when stopped for memory; 124 for time.
set -u
[ $# -ge 4 ] && [ "$3" = "--" ] || { echo "usage: rsscap.sh MAX_MB TIMEOUT_S -- command..." >&2; exit 2; }
max_mb=$1; tmo=$2; shift 3
setsid "$@" &
pid=$!
start=$(date +%s)
peak=0
while kill -0 "$pid" 2>/dev/null; do
  rss_mb=$(ps -eo pgid=,rss= | awk -v g="$pid" '$1==g {s+=$2} END {printf "%d", s/1024}')
  [ "$rss_mb" -gt "$peak" ] && peak=$rss_mb
  if [ "$rss_mb" -gt "$max_mb" ]; then
    echo "rsscap: STOPPED for memory: the group held ${rss_mb} MB, over the ${max_mb} MB limit" >&2
    kill -KILL -- "-$pid" 2>/dev/null; wait "$pid" 2>/dev/null; exit 137
  fi
  if [ $(( $(date +%s) - start )) -gt "$tmo" ]; then
    echo "rsscap: STOPPED for time: over ${tmo} s (peak ${peak} MB)" >&2
    kill -KILL -- "-$pid" 2>/dev/null; wait "$pid" 2>/dev/null; exit 124
  fi
  sleep 0.5
done
wait "$pid"; status=$?
echo "rsscap: exit ${status}, peak ${peak} MB" >&2
exit $status
