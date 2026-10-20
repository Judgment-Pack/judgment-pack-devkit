#!/usr/bin/env bash
# Shared functions of the kit: settings, logging, the node toolchain lookup, the machine lock path.
# Sourced by bin/jpdev and lib/wrap.sh. Needs bash 5.

# shellcheck disable=SC2034  # read by bin/jpdev
JPDEV_VERSION=0.1.0

# Every setting jpdev reads. The environment wins over the config file, the config file over the default.
JPDEV_SETTINGS=(JPDEV_SCRATCH JPDEV_LOCK JPDEV_NODE_RSS_MB JPDEV_NODE_TIMEOUT_S JPDEV_GO_ULIMIT_KB
  JPDEV_GO_TIMEOUT_S JPDEV_PY_ULIMIT_KB JPDEV_NVM_DIR JPDEV_NAME_PATTERNS)

jpdev_log() { printf 'jpdev: %s\n' "$*" >&2; }
jpdev_die() { printf 'jpdev: %s\n' "$*" >&2; exit 2; }

# jpdev_config_file prints the path of the config file.
jpdev_config_file() { printf '%s/jpdev/env' "${XDG_CONFIG_HOME:-$HOME/.config}"; }

# jpdev_default NAME prints the default of a setting.
jpdev_default() {
  case $1 in
    JPDEV_SCRATCH) printf '%s/jpdev' "${XDG_STATE_HOME:-$HOME/.local/state}" ;;
    JPDEV_LOCK) printf '%s/harness.lock' "$JPDEV_SCRATCH" ;;
    JPDEV_NODE_RSS_MB) printf 6000 ;;
    JPDEV_NODE_TIMEOUT_S) printf 1200 ;;
    JPDEV_GO_ULIMIT_KB) printf 12000000 ;;
    JPDEV_GO_TIMEOUT_S) printf 3000 ;;
    JPDEV_PY_ULIMIT_KB) printf 4000000 ;;
    JPDEV_NVM_DIR) printf '%s' "${NVM_DIR:-$HOME/.nvm}" ;;
    JPDEV_NAME_PATTERNS) printf '%s/jpdev/name-patterns' "${XDG_CONFIG_HOME:-$HOME/.config}" ;;
  esac
}

# jpdev_load_config sources the config file, lets the environment override it, fills the defaults,
# exports every setting, and records in JPDEV_SOURCE where each value came from.
jpdev_load_config() {
  local v cfg
  # shellcheck disable=SC2034  # read by bin/jpdev env
  declare -gA JPDEV_SOURCE=()
  local -A pre=()
  for v in "${JPDEV_SETTINGS[@]}"; do
    if [ -n "${!v:-}" ]; then pre[$v]=${!v}; fi
  done
  cfg=$(jpdev_config_file)
  if [ -f "$cfg" ]; then
    # shellcheck disable=SC1090
    . "$cfg"
  fi
  for v in "${JPDEV_SETTINGS[@]}"; do
    if [ -n "${pre[$v]:-}" ]; then
      printf -v "$v" '%s' "${pre[$v]}"; JPDEV_SOURCE[$v]=environment
    elif [ -n "${!v:-}" ]; then
      JPDEV_SOURCE[$v]="config file"
    else
      printf -v "$v" '%s' "$(jpdev_default "$v")"; JPDEV_SOURCE[$v]=default
    fi
    export "${v?}"
  done
}

# jpdev_node_bin VERSION prints the bin directory of the newest nvm-installed node whose version
# starts with VERSION (22 matches v22.x.y), or fails.
jpdev_node_bin() {
  local dir entry best=""
  dir=$JPDEV_NVM_DIR/versions/node
  for entry in "$dir"/v"$1"*; do
    case ${entry##*/} in
      v"$1" | v"$1".*) [ -x "$entry/bin/node" ] && best=$(printf '%s\n%s\n' "$best" "$entry" | sort -V | tail -n 1) ;;
    esac
  done
  [ -n "$best" ] || return 1
  printf '%s/bin' "$best"
}

# jpdev_python_bin MAJOR.MINOR prints the path of a working python of that version: python3.N on
# PATH when it runs (a pyenv shim for a version that is not selected does not), else the newest
# one under $PYENV_ROOT/versions (default ~/.pyenv/versions).
jpdev_python_bin() {
  local found entry best=""
  if found=$(command -v "python$1") && "$found" --version > /dev/null 2>&1; then printf '%s' "$found"; return 0; fi
  for entry in "${PYENV_ROOT:-$HOME/.pyenv}"/versions/"$1".*; do
    [ -x "$entry/bin/python$1" ] && best=$(printf '%s\n%s\n' "$best" "$entry" | sort -V | tail -n 1)
  done
  [ -n "$best" ] || return 1
  printf '%s/bin/python%s' "$best" "$1"
}

# jpdev_clone_key ROOT prints a short name for a clone, used for the per-clone Go cache.
jpdev_clone_key() {
  local sum
  sum=$(printf '%s' "$1" | cksum | cut -d' ' -f1)
  printf '%s-%s' "$(basename "$1")" "$sum"
}

# jpdev_kit_dir prints the root of the kit that holds this file.
jpdev_kit_dir() { (cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd); }

# jpdev_manifest_get FILE KEY... prints the value at the path (a string, a number, or the JSON of
# an object) or nothing when it is absent.
jpdev_manifest_get() {
  python3 -I -c '
import json, sys
v = json.load(open(sys.argv[1], encoding="utf-8"))
for key in sys.argv[2:]:
    if not isinstance(v, dict) or key not in v:
        sys.exit(0)
    v = v[key]
print(v if isinstance(v, (str, int, float)) else json.dumps(v))' "$@"
}

# jpdev_git_net ARGS... runs git with the gh credential helper, for fetch and push.
jpdev_git_net() { git -c credential.helper= -c 'credential.helper=!gh auth git-credential' "$@"; }

# jpdev_prepare_run ROOT MANIFEST validates the manifest and exports what lib/wrap.sh and
# templates/check.sh read: JPDEV_ROOT, JPDEV_WRAP and JPDEV_NODE_BIN.
jpdev_prepare_run() {
  local root=$1 manifest=$2 kit nodev
  kit=$(jpdev_kit_dir)
  [ -f "$manifest" ] || jpdev_die "no manifest at $manifest"
  command -v python3 >/dev/null || jpdev_die "python3 is needed to read the manifest"
  python3 "$kit/lib/validate_manifest.py" "$manifest" "$kit/templates/dev.schema.json" || jpdev_die "the manifest is not valid"
  export JPDEV_ROOT=$root JPDEV_WRAP=$kit/lib/wrap.sh
  JPDEV_VENV=$(jpdev_manifest_get "$manifest" toolchains python venv)
  export JPDEV_VENV
  nodev=$(jpdev_manifest_get "$manifest" toolchains node version)
  if [ -n "$nodev" ]; then
    JPDEV_NODE_BIN=$(jpdev_node_bin "$nodev") || jpdev_die "node $nodev is not installed under $JPDEV_NVM_DIR (nvm install $nodev)"
    export JPDEV_NODE_BIN
  else
    unset JPDEV_NODE_BIN
  fi
}
