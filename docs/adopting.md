# Adopting the kit in a repository

A repository adopts the kit with five files and one CI workflow. None of them depends on the
kit being installed: a contributor or CI runs the vendored runner with python3 alone, and a
machine that has the kit adds the caps and the lock around the same steps.

## 1. Write `dev.json`

Start from `templates/dev.json` and keep what the repository runs. The manifest names:

- `toolchains`: `node` (`{"version": "22"}`, resolved from nvm), `go` (`{}`, or
  `{"version": "1.26.5"}` to name the Go release the checks are measured on: CI installs it,
  `jpdev` selects an installed Go that matches it and says when none is installed, and the
  workflow falls back to the `go.mod` version when the manifest names none), `python`
  (`{"version": "3.12", "venv": ".venv"}`; the version and the virtual environment are optional;
  a declared virtual environment is first on PATH for every step).
- `setup`: steps `jpdev setup` and CI run once after a clone (`npm ci`, the python
  requirements).
- `checks`: the check list, in the order it should run (cheap checks first).
- `mutants`: the command `jpdev mutants` runs; `{rows}` becomes one `--row 'TEXT'` per row.
- `parity`: an optional last check that compares the repository against another one; it names
  the environment variable it needs in `requires_env`, and is skipped, and said to be skipped,
  where the variable is empty. Under CI (`CI` set) such a skip is a failure, so a green run
  never hides a check that did not run: either the CI workflow sets the variable (see the
  commented checkout step in `templates/ci-check.yml`) or the step says `"optional": true`.

A step has a `name` (letters, digits, `.`, `_`, `-`), a `run` (a bash command line), a `cwd`
(relative to the repository root, default `.`), a `toolchain` (`node`, `go`, `python` or
`shell`, default `shell`), a `summary` (a regex: the lines of the output it matches are printed
in the summary block; more than three lines are counted and the last one is shown), a
`timeout` in seconds (default 1200, enforced for every toolchain by both runners) and optionally `requires_env` and `optional`.

`jpdev check` validates the file against `templates/dev.schema.json` before it runs anything.

## 2. Vendor the runner

```sh
mkdir -p scripts/dev
cp templates/check.sh scripts/dev/check.sh
```

Line 2 of the template, `# from judgment-pack-devkit vX.Y.Z (templates/check.sh)`, records the kit
release the copy came from. A vendored copy keeps that line, so a later reader can tell which release
it is behind; when you update the copy, copy the whole file again.

`scripts/dev/check.sh [--setup] [--only A,B] [--skip A,B] [--all]` runs the manifest with no
caps and prints the summary block. `jpdev check` uses the vendored copy when it exists and
sets `JPDEV_WRAP` so that each step runs under its toolchain's cap.

## 3. Add the agent instructions

Copy `templates/AGENTS.md` to the repository root and generate `CLAUDE.md` from it with
`scripts/sync-agent-docs.sh DIR` (the root as `DIR`); `--check` makes the same comparison
without writing, for a CI step. Add the repository's own rules below the shared ones in
`AGENTS.md`, not in `CLAUDE.md`.

## 4. Add the CI workflow

Copy `templates/ci-check.yml` to `.github/workflows/dev-check.yml`. It reads the toolchain
versions from `dev.json`, sets the toolchains up, and runs `scripts/dev/check.sh --setup` and
`scripts/dev/check.sh --all`. A repository that already has CI jobs keeps them and uses the
workflow as the list of steps to move its checks into.

## 5. Check it

```sh
jpdev setup . --manifest dev.json
jpdev check --all
```

## Worked example: the agent repository

`examples/judgment-pack-agent.dev.json` is the manifest of `judgment-pack-agent`. Its setup is
`npm ci` and the python requirements in a Python 3.12 virtual environment. Its checks, in order:
`git diff --check`; the python tests; the mutation table's `--check`; the build; the unit tests
(from `packages/harness`); the certification suite once per adapter (`vercel`, `codex`,
`deepagents`); `gofmt`; `go vet`; `go generate ./contract` with no diff; `go test -count=1
./...` (from `go`); and `go run ./cmd/harness-check`, which needs the scripted server and so
node on PATH (the kit puts the manifest's node first on PATH for every step; the server starts
with `--disable-wasm-trap-handler`, which is what lets it run under the Go address-space cap).
Its last check, `parity`, compares the package with a checkout of the Desk and is skipped
unless `JPDEV_DESK` names one; it is marked `optional` because that repository's CI does not
check the Desk out.

To run it against a clone of that repository:

```sh
jpdev setup path/to/clone --manifest examples/judgment-pack-agent.dev.json
cd path/to/clone
JPDEV_DESK=path/to/desk-checkout jpdev check --all --manifest path/to/devkit/examples/judgment-pack-agent.dev.json
```

Copy the example to the repository as `dev.json` when it adopts the kit.
