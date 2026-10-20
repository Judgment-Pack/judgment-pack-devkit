#!/usr/bin/env bash
# wrap.sh TOOLCHAIN -- command...
# Runs one command under the cap its toolchain needs on a shared machine:
#   node    the resident-memory cap (lib/rsscap.sh); never ulimit -v, which breaks vite and vitest
#   go      the machine lock, ulimit -v, GOFLAGS=-mod=mod, a per-clone GOCACHE, timeout
#   python  ulimit -v and timeout
#   shell   nothing
# JPDEV_STEP_TIMEOUT (seconds) replaces the toolchain's default timeout for this one command.
# JPDEV_NODE_BIN, when set, is put first on PATH; so is <clone>/.venv/bin for python.
set -u
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
. "$here/common.sh"
jpdev_load_config

[ $# -ge 3 ] && [ "$2" = "--" ] || { echo "usage: wrap.sh TOOLCHAIN -- command..." >&2; exit 2; }
toolchain=$1; shift 2
step_timeout=${JPDEV_STEP_TIMEOUT:-}

if [ -n "${JPDEV_NODE_BIN:-}" ]; then PATH=$JPDEV_NODE_BIN:$PATH; fi
clone=${JPDEV_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}
if [ "$toolchain" = python ] && [ -d "$clone/.venv/bin" ]; then PATH=$clone/.venv/bin:$PATH; fi
export PATH

case $toolchain in
  node)
    exec "$here/rsscap.sh" "$JPDEV_NODE_RSS_MB" "${step_timeout:-$JPDEV_NODE_TIMEOUT_S}" -- "$@"
    ;;
  go)
    mkdir -p "$(dirname "$JPDEV_LOCK")" "$JPDEV_SCRATCH/gocache"
    cache=$JPDEV_SCRATCH/gocache/$(jpdev_clone_key "$clone")
    if ! flock -n "$JPDEV_LOCK" true; then jpdev_log "waiting for the machine lock"; fi
    # shellcheck disable=SC2016  # the script is for the inner bash, which expands it
    exec flock "$JPDEV_LOCK" bash -c '
      ulimit -v "$1"; export GOFLAGS=-mod=mod GOCACHE="$2"; tmo=$3; shift 3
      exec timeout -k 10 "$tmo" "$@"' jpdev-go "$JPDEV_GO_ULIMIT_KB" "$cache" "${step_timeout:-$JPDEV_GO_TIMEOUT_S}" "$@"
    ;;
  python)
    exec bash -c 'ulimit -v "$1"; tmo=$2; shift 2; exec timeout -k 10 "$tmo" "$@"' jpdev-py \
      "$JPDEV_PY_ULIMIT_KB" "${step_timeout:-1200}" "$@"
    ;;
  shell)
    exec "$@"
    ;;
  *)
    echo "wrap.sh: unknown toolchain '$toolchain'" >&2; exit 2
    ;;
esac
