# Adopting the kit in a repository

A repository adopts the kit with five files and two workflows. None of them depends on the kit
being installed: a contributor or CI runs the two vendored scripts directly, and a machine that
has the kit adds the caps and the lock around the same steps.

## 1. Write `dev.json`

Start from `templates/dev.json` and keep what the repository runs. The manifest names:

- `toolchains`: `node` (`{"version": "22"}`, resolved from nvm), `go` (`{}`, or
  `{"version": "1.26.5"}` to name the Go release the checks are measured on: CI installs it,
  `jpdev` selects an installed Go that matches it and says when none is installed, and the
  workflow falls back to the `go.mod` version when the manifest names none), `python`
  (`{"version": "3.12", "venv": ".venv"}`; the version and the virtual environment are optional;
  the environment path is a non-root relative child of the clone with no `..` segment; setup and
  checks create a missing declared environment with `python3.X` on PATH or the newest matching
  pyenv version, then put its `bin` first on PATH for every step).
- `setup`: steps `jpdev setup` and CI run once after a clone (`npm ci`, the python
  requirements).
- `checks`: the check list, in the order it should run (cheap checks first).
- `notes`: optional short sentences about repository-specific traps. For example,
  `"run every Python command with the venv on the PATH"` and
  `"a change to a file listed in scripts/parity.sh updates its row"`. They are plain text:
  `jpdev codex brief-template` prints them under `## This repository's notes`, and
  `jpdev codex check-brief --build` requires that heading when notes are present; no note is
  executed.
- `mutants`: the command `jpdev mutants` runs; `{rows}` becomes one `--row 'TEXT'` per row.
- `parity`: an optional last check that compares the repository against another one; it names
  the environment variable it needs in `requires_env`, and is skipped, and said to be skipped,
  where the variable is empty. Under CI (`CI` set) such a skip is a failure, so a green run
  never hides a check that did not run: either the CI workflow sets the variable (see the
  commented checkout step in `templates/ci-check.yml`) or the step says `"optional": true`.

The optional `handover` object names `boundary_paths`, where a builder checks that admission and
verdict behavior did not move beyond the issue, and `shared_paths`, which a builder changes by
appending only while a sibling build is open. Its optional `schema_probe` is a command the CI
handover job runs with `JPDEV_HANDOVER_BASE` set to the pull request's base commit, so a repository
can prove that schema changes are carried by vectors. These paths also bound `jpdev codex run
--small`: touching one makes the wrapper refuse the small result. The builder runs the checks
described in AGENTS.md before handover and never fetches, rebases or merges; the coordinator carries
`main`.

A step has a `name` (letters, digits, `.`, `_`, `-`), a `run` (a bash command line), a `cwd`
(relative to the repository root, default `.`), a `toolchain` (`node`, `go`, `python` or
`shell`, default `shell`), a `summary` (a regex: the lines of the output it matches are printed
in the summary block; more than three lines are counted and the last one is shown), a
`timeout` in seconds (default 1200, enforced for every toolchain by both runners) and optionally `requires_env` and `optional`.

`jpdev check` validates the file against `templates/dev.schema.json` before it runs anything.

## 2. Vendor the check scripts

```sh
mkdir -p scripts/dev
devkit=path/to/judgment-pack-devkit
cp "$devkit/templates/check.sh" scripts/dev/check.sh
cp "$devkit/scripts/dev/handover_check.sh" scripts/dev/handover_check.sh
```

Line 2 of the template, `# from judgment-pack-devkit vX.Y.Z (templates/check.sh)`, records the kit
release the copy came from. A vendored copy keeps that line, so a later reader can tell which release
it is behind. The kit's `scripts/dev/handover_check.sh` similarly vendors `lib/handover_check.sh`
with its release on line 2. Vendor `scripts/dev/check.sh` and `scripts/dev/handover_check.sh`
together, and copy both whole files again when updating them. `jpdev setup` names this pair when
either file is absent.

`scripts/dev/check.sh [--setup] [--only A,B] [--skip A,B] [--all]` runs the manifest with no
caps and prints the summary block. Before a setup or check run, it creates a missing declared
Python environment with `python3.X` on PATH, then the newest
`~/.pyenv/versions/3.X.*/bin/python3`; it refuses before any step when neither exists. Every step
runs with that environment's `bin` first on PATH, so the manifest's Python setup step installs its
requirements into the environment. A summary row names the interpreter for a Python step or any
step that invokes `python3`. `jpdev check` uses the vendored copy when it exists and sets
`JPDEV_WRAP` so that each step runs under its toolchain's cap. `jpdev env` shows the interpreter
selected for the current repository's manifest.

## 3. Add the agent instructions

Copy `templates/AGENTS.md` to the repository root and generate `CLAUDE.md` from it with
`scripts/sync-agent-docs.sh DIR` (the root as `DIR`); `--check` makes the same comparison
without writing, for a CI step. Add the repository's own rules below the shared ones in
`AGENTS.md`, not in `CLAUDE.md`.

The shared rules state how to push: with the `gh` credential helper and never with force, because
the machine's stored git credential can be another account's and a plain `git push` is then
refused. Where the kit is installed, `jpdev push [BRANCH]` runs exactly that form
(`git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push -u origin BRANCH`)
and refuses `--force` and `-f`; the instructions give the full command for where it is not. The
kit changes no global git configuration. A repository that adopted an earlier copy of the
instructions copies `templates/AGENTS.md` again (keeping its own rules below the shared ones) and
regenerates `CLAUDE.md`.

## 4. Add the CI workflow

Copy `templates/ci-check.yml` to `.github/workflows/ci.yml`. It reads the toolchain
versions from `dev.json`, sets the toolchains up, and runs `scripts/dev/check.sh --setup` and
`scripts/dev/check.sh --all`. Its handover job rejects removals from boundary paths unless the pull
request body contains `Boundary change: yes`, then runs `handover.schema_probe` when present through
the vendored `scripts/dev/handover_check.sh`. Copy
`templates/update-branches.yml` to `.github/workflows/update-branches.yml` to update open branches
after a default-branch push and label conflict cases `carry needed`.

Set the optional `UPDATE_BRANCHES_TOKEN` secret to a fine-grained personal access token or GitHub
App installation token with repository contents and pull-requests write access. An update made with
that token starts CI through the resulting push. When the secret is absent, the workflow uses its
`GITHUB_TOKEN` and explicitly dispatches `ci.yml` for the updated pull-request branch, passing the
pull-request number so the `handover` job can read its base and body. The workflow's `actions: write`
permission permits that fallback dispatch. After adopting the workflows, check that an automatically
updated pull request shows the `check` and `handover` CI checks on its new head. A repository that
already has CI jobs keeps their required names and uses the template as the list of steps to move
into its `ci.yml`. The dispatch passes the updated head SHA, which `ci.yml` names in the run title
and checks out for both jobs.

The fallback cannot dispatch a fork's short branch name in the base repository. For an updated fork
pull request it comments that checks must be started by a push from the fork, then fails visibly;
the contributor must push from the fork to start the checks on that head.

## 5. Check it

```sh
jpdev setup . --manifest dev.json
jpdev check --all
```

For a saved Codex review, start from the review skeleton and keep the clone's tracked tree
unchanged:

```sh
jpdev codex brief-template --review > review-brief.md
jpdev codex review --brief review-brief.md --model MODEL --effort medium --dir . --pr NUMBER --repo OWNER/NAME
jpdev record post --pr NUMBER --repo OWNER/NAME --file .jpdev/output/review.md
```

The review command defaults to `workspace-write` so focused probes can create temporary files,
with no network access unless the caller passes `--network`. Its prompt forbids Git writes and it
refuses the result if HEAD or a tracked file changed. It closes stdin, writes only the final
message to the record, prints the reviewed SHA, and never posts.

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
