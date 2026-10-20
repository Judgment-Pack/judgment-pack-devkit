# judgment-pack-devkit

The development kit of the Judgment Pack repositories: one command, `jpdev`, that sets up a
clone, runs a repository's check list under the machine's resource caps, runs its mutation
rows on a scratch copy, and posts review records with local paths and names removed. It is
plain bash (bash 5, python3 standard library for JSON). Nothing in it is specific to one
agent: people, Claude sessions and Codex sessions run the same commands.

A repository describes itself in one file, `dev.json` (the manifest): the toolchains it
needs, its setup steps and its checks. The kit holds the schema, the public runner a
repository vendors, the agent instructions every repository carries, the CI step list and the
operating policy.

## Install

```sh
git clone https://github.com/Judgment-Pack/judgment-pack-devkit
cd judgment-pack-devkit
ln -s "$PWD/bin/jpdev" ~/.local/bin/jpdev
mkdir -p ~/.config/jpdev && cp config/env.example ~/.config/jpdev/env
jpdev env
```

Needs bash 5, git, gh (logged in), python3, rsync and, for Go steps, flock. Node versions are
read from nvm; a python version the manifest names is read from `python3.N` on PATH or from
pyenv.

## Settings

`${XDG_CONFIG_HOME:-$HOME/.config}/jpdev/env` is sourced by bash; an environment variable of
the same name overrides it. `config/env.example` documents each setting with its default:

| Setting | Default | Used for |
| --- | --- | --- |
| `JPDEV_SCRATCH` | `$XDG_STATE_HOME/jpdev` | logs, scratch copies, Go caches |
| `JPDEV_LOCK` | `$JPDEV_SCRATCH/harness.lock` | the machine lock Go steps hold |
| `JPDEV_NODE_RSS_MB`, `JPDEV_NODE_TIMEOUT_S` | 6000, 1200 | the node memory cap and default timeout |
| `JPDEV_GO_ULIMIT_KB`, `JPDEV_GO_TIMEOUT_S` | 12000000, 3000 | the Go address-space cap and timeout |
| `JPDEV_PY_ULIMIT_KB` | 4000000 | the python address-space cap |
| `JPDEV_NVM_DIR` | `$NVM_DIR` or `~/.nvm` | where node versions live |
| `JPDEV_NAME_PATTERNS` | `~/.config/jpdev/name-patterns` | regexes the record gate refuses |

## Commands

- `jpdev setup DIR [--repo OWNER/NAME] [--branch NAME] [--base origin/main] [--manifest FILE]`:
  clones with `gh repo clone` (or reuses `DIR`), makes the branch from the base, selects the
  manifest's toolchains (node by nvm version, go, python and its virtual environment), runs the
  setup steps under the caps and prints one summary block.
- `jpdev check [--only NAME,...] [--skip NAME,...] [--all] [--manifest FILE]`: runs the checks in
  order, each under its toolchain's cap, and stops at the first failure unless `--all`. The
  block names each check, pass or fail, the lines its `summary` regex matched, and the first 40
  lines of a failure. The exit status is the number of failures.
- `jpdev mutants --row TEXT [--row TEXT]...`: runs the manifest's `mutants` command on a scratch
  copy of the clone (`.git` left out, `node_modules` linked) and prints caught or not caught per
  row.
- `jpdev record post (--pr N | --issue N) --file FILE [--repo OWNER/NAME] [--dry-run]`: reduces
  the scratch and home paths to `<scratch>` and `<home>`, refuses to post when any local path
  remains or a line matches the name patterns, and posts with `gh ... comment --body-file`.
- `jpdev env`: the effective settings and where each came from.

## The caps

| Toolchain | Cap |
| --- | --- |
| `node` | `lib/rsscap.sh`: the process group's resident memory and a timeout; never `ulimit -v`, which breaks vite and vitest |
| `go` | `flock` on the machine lock, `ulimit -v`, `GOFLAGS=-mod=mod`, a per-clone `GOCACHE`, `timeout` |
| `python` | `ulimit -v` and `timeout`; the clone's virtual environment first on PATH |
| `shell` | none |

## What is here

- `bin/jpdev`, `lib/`: the command, the caps, the manifest check.
- `templates/dev.json`, `templates/dev.schema.json`: the manifest by example and its JSON Schema.
- `templates/check.sh`: the public runner a repository vendors as `scripts/dev/check.sh`.
- `templates/AGENTS.md`, `templates/CLAUDE.md`: the agent instructions (one text, generated from
  the other by `scripts/sync-agent-docs.sh`).
- `templates/ci-check.yml`: the CI step list.
- `docs/policy.md`: how agent work on these repositories is run. `docs/adopting.md`: how a
  repository adopts the kit. `examples/judgment-pack-agent.dev.json`: a worked manifest.
- `tests/run.sh`: the kit's own tests (`tests/fixture/` holds a manifest of shell echoes and one
  deliberate failure).

Apache-2.0; see `LICENSE`.
