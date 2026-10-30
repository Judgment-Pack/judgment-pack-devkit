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
cp "$devkit/scripts/dev/changed_checks.py" scripts/dev/changed_checks.py
```

Line 2 of the template, `# from judgment-pack-devkit vX.Y.Z (templates/check.sh)`, records the kit
release the copy came from. A vendored copy keeps that line, so a later reader can tell which release
it is behind. The kit's `scripts/dev/handover_check.sh` similarly vendors `lib/handover_check.sh`
with its release on line 2. Vendor `scripts/dev/check.sh` and `scripts/dev/handover_check.sh`
together, and copy both whole files again when updating them. `jpdev setup` names this pair when
either file is absent. `scripts/dev/changed_checks.py`, the selection code of `--changed`, is
`lib/changed_checks.py` with the release on line 2; vendor it beside `check.sh` and update the two
together (`check.sh --changed` refuses when it is absent, and the CI template uses `--changed` on
pull requests). A runner given an option it does not know names the release on its line 2, and
`jpdev version` prints the installed kit's version with the commit a kit checkout is at.

A repository whose release takes the CI evidence main already produced, instead of running CI
again, also vendors `scripts/dev/release_evidence.py` (`lib/release_evidence.py` with the release on
line 2, updated with the other vendored scripts) and writes `.github/ci-evidence.json` from
`templates/ci-evidence.json`, in its own adoption issue: [the release evidence gate](ci-evidence.md)
describes the contract, the capture step each CI job adds and the release step.

`scripts/dev/check.sh [--setup] [--only A,B | --changed [BASE]] [--skip A,B] [--all] [--strict]` runs
the manifest with no caps and prints the summary block. `--strict` counts a step skipped for an
empty `requires_env` as a failure, `optional: true` or not: the form a release's fresh run of the
list takes ([revalidation](ci-evidence.md#revalidation)). `--changed` selects the checks as
`jpdev check --changed` does (see [changed-path check selection](#changed-path-check-selection)),
with the same rules and the same report, through the vendored `scripts/dev/changed_checks.py`. Before a setup or check run, it creates a missing declared
Python environment with `python3.X` on PATH, then the newest
`~/.pyenv/versions/3.X.*/bin/python3`; it refuses before any step when neither exists. Every step
runs with that environment's `bin` first on PATH, so the manifest's Python setup step installs its
requirements into the environment. A summary row names the interpreter for a Python step or any
step that invokes `python3`. `jpdev check` uses the vendored copy when it exists and sets
`JPDEV_WRAP` so that each step runs under its toolchain's cap. `jpdev env` shows the interpreter
selected for the current repository's manifest.

`jpdev check` stores each step's complete step output (stdout and stderr combined) at
`$JPDEV_SCRATCH/logs/<repository>-<timestamp>/<step>.log`. If that output cannot be persisted, the
summary keeps the completed step's result and reports the persistence failure separately, naming
the intended log target. Remaining steps are marked not run. If any selected step is left not run,
the runner exits nonzero even when every completed step passed; the completed PASS/FAIL rows and
failed-check count remain unchanged. When all selected steps completed, the infrastructure failure does
not change the check-derived exit status, including a passing single-step run. No command is replayed
automatically, and no log path is advertised unless a complete log exists.

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
versions from `dev.json`, sets the toolchains up, and runs `scripts/dev/check.sh --setup` and the
checks: on a pull request `scripts/dev/check.sh --all --changed origin/<base branch>`, on a push to
the default branch and on a dispatch `scripts/dev/check.sh --all`. The pull request runs the checks
`jpdev.json` maps its changed paths to, and the whole list when a path is unmapped, when the
mapping, the manifest or the runner changed, or when there is no mapping, so a repository without
a `changed` mapping runs the whole list on every pull request as before. The default branch always
runs the whole list, and only that run is the evidence a release takes (see
[the release evidence gate](ci-evidence.md)); a check a pull request did not select did not pass there,
and the default-branch run is where a mapping that missed an effect shows. This is the
[policy](policy.md#testing)'s split: CI owns every deterministic check, the scoped run is allowed on
pull requests, and the full list is required on the default branch and before a release. The check
job checks out the whole history so that the merge base with the base branch is found. When the
base cannot be resolved (a missing or empty base branch name, or no merge base in the history),
the pull-request job fails with the refusal before any check runs rather than falling back to the
whole list; a push to the default branch runs the whole list whatever the mapping says. Any
untracked path that is not ignored and that a workflow step creates inside the clone (a checkout of
another repository for a parity step, a download, a build output) is a changed path to `--changed`:
unless a rule maps it, every pull request runs the whole list. Such a path must live outside the
clone or be listed in `.gitignore`; the template's commented parity example checks the other
repository out and moves it under the runner's temporary directory before any check runs, and the
selection report names such a path as untracked and not mapped. Its handover job rejects removals from boundary paths unless the pull
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
check the Desk out. A repository whose CI does check the other repository out keeps that checkout
outside the clone (see [step 4](#4-add-the-ci-workflow)), or `--changed` runs the whole list on
every pull request.

To run it against a clone of that repository:

```sh
jpdev setup path/to/clone --manifest examples/judgment-pack-agent.dev.json
cd path/to/clone
JPDEV_DESK=path/to/desk-checkout jpdev check --all --manifest path/to/devkit/examples/judgment-pack-agent.dev.json
```

Copy the example to the repository as `dev.json` when it adopts the kit.

## Duplication check

The `duplication` step is opt-in. Vendor `lib/duplication.py` as `scripts/dev/duplication.py`, keep
the `duplication` step of `templates/dev.json` in the check list, and declare the repository's
languages and its token and line thresholds in the `duplication` member of `jpdev.json`
(`generators` may be left out when `duplication` is present). Until the member is present the step
passes and its summary line says `duplication: off`. Choose thresholds the current tree passes, or
remove or mark the copies the first run names. When `jpdev.json` also maps changed paths
(`changed`), list `duplication` in every rule whose globs can match a file of a declared language,
or `jpdev check --changed` does not run the step for those changes.
[The duplication check](../README.md#the-duplication-check) describes the member, the ignore block
and the report.

## Generated reference documents

Keep `dev.json` as the checklist manifest. Repositories with checked-in generated documents add
an explicit version1 `jpdev.json` generator declaration and vendor `lib/generated_docs.py` as
`scripts/dev/generated_docs.py`. Add the `generated-docs` check to `dev.json`; the same check then
runs locally and in existing CI. See [generated documents](generated-docs.md) for the declaration,
scratch copy/dependency rules, output validation and stale-document diagnostics. Existing reference
and generator regression checks remain useful and should be preserved.

## Changed-path check selection

`jpdev check --changed [BASE]` runs only the checks a change can affect. The changed paths are those
that differ from the merge base of `BASE` (default: the default branch) and `HEAD` in `HEAD`, in the
index or in the working tree, submodules included whatever their `ignore` setting, plus untracked
files that are not ignored. The repository says which checks they affect in the `changed` member of
`jpdev.json`, the version1 file that also declares generated documents (`generators` may be left
out when `changed` is present):

```json
{
  "version": 1,
  "changed": [
    {"paths": ["docs/**", "*.md"], "checks": ["docs-lint", "diff-check"]},
    {"paths": ["**/*.go", "go.mod", "go.sum"], "checks": ["go-vet", "go-test", "diff-check"]}
  ]
}
```

A rule names path globs and the `dev.json` checks (`parity` included) that a changed path matching
one of them selects; a path that matches several rules selects the checks of each. A glob matches
the whole repository-relative path: `*` and `?` stay within one path segment, a `**` segment matches
any number of segments (`docs/**`, `**/*.go`), and every other character is literal; `*` also
matches a name that starts with a dot (`*.yml` matches `.golangci.yml`). A glob holding
`[`, `]`, `{`, `}` or `\`, a glob that starts with `/` or has an empty, `.` or `..` segment, a check
the manifest does not list, an empty or repeated list and an unknown member are refused, with a
message that names the member or rule at fault, before any check runs.
`templates/jpdev.schema.json` documents the same shape and `templates/jpdev.json` holds an example.

The whole list runs when a changed path matches no rule, when `jpdev.json`, the manifest (as named
or as a symlink resolves), `scripts/dev/check.sh` or `scripts/dev/changed_checks.py` changed, when nothing changed, and when there is
no mapping (no `jpdev.json`, or one without `changed`). Map only paths whose effect on the checks is
known, and put the checks that read every file (whitespace, path and name checks) in every rule.
Selection sees only what git reports in this clone: an edit hidden by assume-unchanged or
skip-worktree, an ignored file and a path outside the clone are not seen, and the full list remains
the guard for them. Conversely, any untracked path that is not ignored is seen, including one a CI
workflow creates inside the clone: unless a rule maps it, it defeats `--changed` on every run, so a
path a workflow creates belongs outside the clone or in `.gitignore`. The report names an unmapped
untracked path as `untracked path PATH is not mapped; a workflow-created path belongs outside the
clone or in .gitignore: whole list`. The [policy](policy.md#testing) says where a scoped run is allowed and where the
full list is required.

## Release evidence: the runner identity policy

A repository that has adopted [the release evidence gate](ci-evidence.md) can hold its evidence to
the [runner identity](ci-evidence.md#runner-identity) policy, the shared policy for standard
GitHub-hosted runners. It is a reported image identity, not a pinned VM image: the gate compares
what each runner reports about its image and refuses on a difference; it pins no image. Adopt it in
the repository's own reviewed change:

1. Vendor `scripts/dev/release_evidence.py` from the kit release that carries the policy (the gate
   holds the manifest revisions it accepts), and copy `templates/runner-identity.json` unchanged to
   `.github/runner-identity.json`.
2. In `.github/ci-evidence.json`, add the pin (its SHA-256 is `sha256sum .github/runner-identity.json`,
   which must be a revision the gate ships):

   ```json
   "identity": {"manifest": ".github/runner-identity.json", "sha256": "<the SHA-256>"}
   ```

3. Give every profile its `variant` (`linux-x64`, `linux-arm64`, `macos-arm64`, `macos-x64`,
   `windows-x64`; its `RUNNER_OS` and `RUNNER_ARCH` must be the variant's), its `platform.ImageOS`
   (the image name its runners report: `ubuntu24`, `macos15`), and at least one tool. A profile of
   the release job's platform keeps `compare: release-runner`; a leg of another OS or architecture
   keeps `compare: pins`, and its legs must agree among themselves.
4. Pin every `uses:` of the CI workflows, of the local actions and reusable workflows they call, and
   of the release workflow to a full commit id (a container image to a `sha256` digest). Write each
   `uses:` as a block-style key on its own line.
5. Decide the image-roll route: with `"revalidation": {"allowed": true}` and the
   [revalidation job](ci-evidence.md#revalidation), a release whose runner reports another image
   than the evidence runs the check list on the release runner; without it, it refuses and the
   operator re-runs all jobs of the main CI run ([the fresh route](ci-evidence.md#the-fresh-route)).

Nothing else in the workflows changes: `capture` and `verify` read the policy from the
configuration. The first main run after the change records the identity; until then a release at
an older commit holds its evidence to that commit's own configuration. A repository with its own
evidence verifier (judgment-pack-agent's `scripts/dev/ci_evidence.py`) keeps it until its own
reviewed compatibility work moves it to the shared policy.

## Release evidence: pull-request-to-branch reuse

A repository that has adopted the gate can let a branch job take some tree-only checks from the
merged pull request's newest run ([pull-request-to-branch reuse](ci-evidence.md#pull-request-to-branch-reuse)).
It is opt-in per workflow and per check; tree equality alone never qualifies a result, and every
refusal is a fresh run of the job's whole list. Adopt it in the repository's own reviewed change:

1. Vendor `scripts/dev/release_evidence.py` from the kit release that carries `reuse` (it is the
   same file for `capture`, `verify` and `reuse`).
2. In `.github/ci-evidence.json`, add to the workflow:

   ```json
   "pull_request_reuse": {"checks": ["<tree-only check>", "..."], "environment": ["<VARIABLE>", "..."]}
   ```

   `checks` lists only checks whose result depends on the tree and the recorded inputs; never a
   commit-, history-, ref- or tag-sensitive check, an artifact-producing one, or one that reads
   mutable external state. `environment` names every variable a reusable check reads as a flag
   (`GOFLAGS`, `NODE_OPTIONS`, a test-selection variable); never a secret (only its SHA-256 is
   recorded, but a secret is not a flag). The workflow's `events` must hold `push`.
3. In each pull request job: check out the merge commit with its parents (`fetch-depth: 2` or
   more; the kit's `fetch-depth: 0` qualifies), then after the checks run
   `python3 scripts/dev/release_evidence.py capture --workflow KEY --job KEY --check-log LOG --output FILE`
   under `if: github.event_name == 'pull_request'`, and upload the file as
   `ci-evidence-<workflow key>-<job key>-${{ github.run_attempt }}`, the same name a branch job uses.
4. In each branch job: run `python3 scripts/dev/release_evidence.py reuse --workflow KEY --job KEY
   --output PLAN` before the checks on every branch event, add its `covered` step output to the
   job's `--skip` list, and pass `--reuse-plan PLAN` to the job's `capture`
   ([the workflow shape](ci-evidence.md#pull-request-to-branch-reuse)). Give the job
   `actions: read` and `pull-requests: read` beside `contents: read`.
5. Give the release job's gate step `pull-requests: read` too: the release admits each reused
   check again.

Required status names, the matrix, the release workflow's fresh checks and its publication gates
do not change. Measure before claiming a saving: record the executed checks and their timings on
the repository's own runs before and after. A repository with its own evidence verifier
(judgment-pack-agent's `scripts/dev/ci_evidence.py`) adopts this through its own reviewed
compatibility work, not by replacing that verifier with the kit's.
