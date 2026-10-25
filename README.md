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

## Public

This repository is public. It is for the people and agent sessions who work on the Judgment Pack
repositories, and for anyone who wants the same pattern in their own: a repository lists its checks
in one manifest, anyone can run them with one vendored script and python3 alone, and a machine that
installs the kit adds resource caps and a lock around the same steps. Machine settings never live in
the kit: paths, caps and the list of names a posted record must not carry are read from the
person's own config file and environment (`config/env.example` documents each), and a tracked file
holds no path of any machine. See [CONTRIBUTING.md](CONTRIBUTING.md) to help,
[SECURITY.md](SECURITY.md) to report a vulnerability, and [docs/policy.md](docs/policy.md) for how
agent work on these repositories is run.

## Install

From a release, after verifying it (the commands are in [docs/releasing.md](docs/releasing.md)):

```sh
gh release download vX.Y.Z --repo Judgment-Pack/judgment-pack-devkit --dir release
sha256sum --check --strict release/checksums.txt
tar -xzf release/judgment-pack-devkit-X.Y.Z.tgz
ln -s "$PWD/judgment-pack-devkit-X.Y.Z/bin/jpdev" ~/.local/bin/jpdev
```

From a clone:

```sh
git clone https://github.com/Judgment-Pack/judgment-pack-devkit
cd judgment-pack-devkit
ln -s "$PWD/bin/jpdev" ~/.local/bin/jpdev
```

Then the settings, which are optional:

```sh
mkdir -p ~/.config/jpdev && cp config/env.example ~/.config/jpdev/env
jpdev env
```

## Releases

Each release is a tarball and its `checksums.txt`, built by
[`release.yml`](.github/workflows/release.yml) from a signed tag on `main`, attested with a
build-provenance attestation, and published only after a maintainer approves it.
`gh attestation verify` checks a file against the workflow and the tag; the exact command, and what
the workflow does at each step, are in [docs/releasing.md](docs/releasing.md).

Needs bash 5, git, gh (logged in), python3, rsync and, for Go steps, flock. Node versions are
read from nvm; a python version the manifest names is read from `python3.N` on PATH or from
pyenv; a Go version the manifest names is the go on PATH when it matches, else one under
`JPDEV_GO_SDK_DIR`, and `jpdev` says so when none does.

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
| `JPDEV_GO_SDK_DIR` | `~/sdk` | where a Go release the manifest names is looked for, when the go on PATH is another (`sdk/go1.26.5/bin/go`) |
| `JPDEV_NAME_PATTERNS` | `~/.config/jpdev/name-patterns` | regexes the record gate refuses |
| `JPDEV_CODEX_MODEL_DEFAULT` | none (the model is always passed) | the model `jpdev codex run` uses when `--model` is not given |
| `JPDEV_CODEX_SANDBOX` | `workspace-write` | the sandbox mode of `jpdev codex run` |
| `JPDEV_CODEX_WORDS` | `~/.config/jpdev/codex-words.txt` | extra terms for `jpdev codex check-brief` |
| `JPDEV_SMALL_MAX_LINES` | `80` | maximum added and removed lines for `jpdev codex run --small` |

## Commands

- `jpdev setup DIR [--repo OWNER/NAME] [--branch NAME] [--base origin/main] [--manifest FILE]`:
  clones with `gh repo clone` (or reuses `DIR`), makes the branch from the base, selects the
  manifest's toolchains (node by nvm version, go by its version when the manifest names one,
  and Python by `python3.X` on PATH or the newest matching pyenv version), creates the declared
  Python virtual environment, runs the setup steps in it under the caps, and prints one summary
  block. `jpdev check` creates a missing declared environment before it runs checks too.
- `jpdev check [--only NAME,...] [--skip NAME,...] [--all] [--manifest FILE]`: runs the checks in
  order, each under its toolchain's cap, and stops at the first failure unless `--all`. The
  block names each check, pass or fail, the lines its `summary` regex matched, and the first 40
  lines of a failure. The exit status is the number of failures.
- `jpdev check --changed [BASE] [--skip NAME,...] [--all] [--manifest FILE]`: runs only the checks
  that the `changed` rules of `jpdev.json` map the changed paths to (see
  [changed-path check selection](docs/adopting.md#changed-path-check-selection)). The changed paths
  are those that differ from the merge base of `BASE` and `HEAD` in `HEAD`, in the index or in the
  working tree (deletions, both sides of a rename, and submodules whatever their `ignore` setting),
  plus untracked files that are not ignored. `BASE` defaults to the default branch: `origin/HEAD`,
  else `origin/main`, else `origin/master`. The whole list runs when a changed path matches no rule,
  when `jpdev.json`, the manifest or `scripts/dev/check.sh` changed, when nothing changed, or when
  there is no mapping. A block before the summary names each check selected with the globs that
  selected it and each check not selected, or why the whole list runs. An invalid mapping, a `BASE` that names no commit, a missing
  default branch or merge base, and `--changed` with `--only` are refused with exit 2 before any
  check runs.
- `jpdev mutants --row TEXT [--row TEXT]...`: runs the manifest's `mutants` command on a scratch
  copy of the clone (`.git` left out, `node_modules` linked) and prints caught or not caught per
  row. Clone-local scratch, temporary storage and the copy destination are excluded; their source
  parents and siblings are retained.
- `jpdev record post (--pr N | --issue N) --file FILE [--repo OWNER/NAME] [--dry-run]`: reduces
  the scratch and home paths to `<scratch>` and `<home>`, refuses to post when any local path
  remains, a line matches the name patterns, or the name-pattern file is missing or holds a
  pattern `grep -E` cannot compile, and posts with `gh ... comment --body-file`. A post that
  should go without the name check says `--no-name-check`.
- `jpdev push [BRANCH]`: pushes BRANCH (default: the current branch) to `origin` with exactly
  `git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push -u origin BRANCH`,
  so the push uses the `gh` login and no stored credential. It refuses `--force`, `-f` and a
  `+` refspec.
- `jpdev clean [--root DIR]... [--older-than DURATION] [--min-transcript-bytes N] [--yes]`: dry-run cleanup of explicit
  session disposal seals; no roots means no deletion. Enroll an empty session root with
  `jpdev clean init --root DIR --session TOKEN`, then attest completed disposable paths with
  `jpdev clean seal --root DIR --session TOKEN --path REL --kind KIND` (worktree, review, scratch,
  transcript or cache). Scratch also needs `--base BASE --removed-worktree OLD`; shared caches need
  `--base BASE`. The default age is seven days (`7d`); durations use integer s/m/h/d/w units.
  Transcripts require at least 10485760 logical regular-file bytes (10 MiB); use
  `--min-transcript-bytes N` to change this inclusive, transcript-only floor, or `0` to disable it.
  Bare or saved Git directories and inherited Git evidence redirection are refused.
  `.jpdev-clean-keep` holds exact relative reserves. JSON Lines reports candidates, sizes, reasons,
  outcomes and totals; refusals exit nonzero. Linux host process visibility, disposal inventory,
  Git/remote/PR evidence and all deletion checks remain mandatory with `--yes`. See
  [Scratch and cleanup](docs/policy.md#scratch-and-cleanup) for setup, formats and limitations.
- `jpdev worktree add BASE BRANCH [DIR]`, `jpdev worktree list BASE`, and `jpdev worktree remove
  DIR [--force]`: manage sibling worktrees. Removal refuses dirty or unpushed work unless forced.
- `jpdev carry --pr N --model M --effort low|medium|high [--dir CLONE] [--worktree BASE]`: clone
  or worktree the pull-request branch and merge the current base into it. A clean carry is signed
  and pushed; conflicts start Codex through the normal `--no-pr` path with a generated brief.
- `jpdev codex run --brief FILE --model M --effort low|medium|high [--dir CLONE] [--repo OWNER/NAME]
  [--base main] [--add PATH]... [--no-commit] [--no-push] [--no-pr] [--sandbox
  workspace-write|danger-full-access] [--log FILE] [--worktree BASE] [--branch NAME] [--small]
  [--resume THREAD]`: checks the brief, then runs `codex exec` in
  CLONE (a clone on a work branch that holds an `AGENTS.md`) with `-m`,
  `-c model_reasoning_effort=`, `--sandbox` (network access on for `workspace-write`), stdin from
  `/dev/null`, and a prompt of one line naming the repository's `AGENTS.md` as the rules followed
  by the brief's text. The transcript goes to the log (default under `JPDEV_SCRATCH/logs`); the
  command prints the final message and the exit code. The model is always passed: `--model`, or
  `JPDEV_CODEX_MODEL_DEFAULT` from the config file.

  Codex in `workspace-write` cannot write `.git`, so it does not commit. It writes `msg.txt` (the
  commit message) and `pr.md` (the pull request body) in the clone, and after `codex exec` returns
  the command does the git part: it stages the changes to tracked files (`git add -u`, plus the
  paths named with `--add`; no other untracked file, and never `msg.txt` or `pr.md`), commits with
  `-s` and the message of `msg.txt` with the `Co-Authored-By: Codex <noreply@openai.com>` trailer
  added when `msg.txt` lacks it, pushes as `jpdev push` does, and opens the pull request with
  `gh pr create --repo OWNER/NAME --base BASE --head BRANCH`, the subject of `msg.txt` as the
  title and `pr.md` as the body. `--no-push` stops after the commit, `--no-pr` after the push and
  `--no-commit` runs Codex alone. It stops with exit 1 and commits nothing when Codex changed no
  tracked file or wrote no `msg.txt` (or no `pr.md`, when a pull request is to be opened), and
  refuses a clone on `main`. The exit status is Codex's own when it fails, else 0 when every step
  asked for was done. `--sandbox danger-full-access` is an explicit option only. Worktree runs
  share caches below `BASE/.jpdev-shared`; `--small` enforces the manifest handover paths and line
  bound after the run; `--resume` continues the named thread. Every detected thread id is written
  to `.jpdev/output/thread`. The builder always receives an existing `TMPDIR` beneath its effective
  `JPDEV_SCRATCH`, replacing any inherited temporary directory. A directory passed to `--add` adds every non-ignored file below it,
  except the handover files and caches, and is refused with its path when nothing remains to add.
- `jpdev codex review --brief FILE --model M --effort E --dir CLONE [--pr N | --issue N]
  [--repo OWNER/NAME] [--out FILE] [--sandbox read-only|workspace-write] [--network]`: checks the brief and
  runs `codex exec` with the model, effort and sandbox explicit and stdin closed. It writes the
  final message to `--out` (default `.jpdev/output/review.md`), refuses the result if HEAD or a
  tracked file changed, and prints the reviewed SHA. The default `workspace-write` sandbox lets
  review probes use temporary files. It has no network unless the caller passes `--network`, the
  prompt and post-run gate forbid Git writes, and it never posts. Use `jpdev record post` to post
  the saved report.
- `jpdev codex brief-template [--review]`: prints `templates/codex-brief.md`, a brief skeleton that tells
  Codex to write `msg.txt` and `pr.md` and not to commit.
  `--review` prints the reviewer skeleton with its read-only rules and findings-first report.
- `jpdev codex check-brief FILE`: exits 1 and names the neutral phrasing for each word of
  [`config/codex-words.txt`](config/codex-words.txt) (and of the file `JPDEV_CODEX_WORDS` names)
  that the brief holds. A word inside backticks is treated as part of an identifier, path or
  command and is ignored; the product term “adversarial” is not in the base list. `codex run` runs
  the same check first and does not start the run on a refusal.
- `jpdev env`: the effective settings and where each came from.

## The caps

| Toolchain | Cap |
| --- | --- |
| `node` | `lib/rsscap.sh`: the process group's resident memory and a timeout; never `ulimit -v`, which breaks vite and vitest |
| `go` | `flock` on the machine lock, `ulimit -v`, `GOFLAGS=-mod=readonly` (a step never rewrites `go.mod`), a per-clone `GOCACHE`, `timeout` |
| `python` | `ulimit -v` and `timeout` |
| `shell` | `timeout` only |

When the manifest declares a virtual environment, its path must be a non-root relative child of
the clone with no `..` segment, and setup and checks create it when it is missing.
They use `python3.X` on PATH first, then the newest `~/.pyenv/versions/3.X.*/bin/python3`, and
refuse before any step if the declared release is unavailable. Its `bin` is first on PATH for
every step, whatever the step's toolchain (the toolchain still decides the cap), so a node or Go
step that runs a Python script uses the environment's interpreter and packages. Summary rows for
Python steps, and for other steps that invoke `python3`, name the interpreter used.

## What is here

- `bin/jpdev`, `lib/`: the command, the caps, the manifest check, the brief check, the changed-path
  check selection.
- `config/env.example`, `config/codex-words.txt`: the settings by example, and the base word list of
  `jpdev codex check-brief`.
- `templates/dev.json`, `templates/dev.schema.json`: the manifest by example and its JSON Schema.
- `templates/jpdev.json`, `templates/jpdev.schema.json`: the generated-document declaration and the
  changed-path mapping by example, and their JSON Schema.
- `templates/check.sh` and `lib/handover_check.sh`: the public checks a repository vendors as
  `scripts/dev/check.sh` and `scripts/dev/handover_check.sh`.
- `templates/codex-brief.md`, `templates/codex-review-brief.md`: the build and review brief
  skeletons `jpdev codex brief-template` prints.
- `templates/AGENTS.md`, `templates/CLAUDE.md`: the agent instructions (one text, generated from
  the other by `scripts/sync-agent-docs.sh`).
- `templates/ci-check.yml`: the CI step list.
- `docs/policy.md`: how agent work on these repositories is run. `docs/adopting.md`: how a
  repository adopts the kit. `examples/judgment-pack-agent.dev.json`: a worked manifest.
- `tests/run.sh`: the kit's own tests (`tests/fixture/` holds a manifest of shell echoes and one
  deliberate failure, and the manifest and mapping of the `jpdev check --changed` fixture clones).
- `dev.json`, `jpdev.json`, `scripts/dev/check.sh`, `scripts/dev/handover_check.sh`, `AGENTS.md`,
  `CLAUDE.md`: the kit on itself, the list of checks CI runs, its changed-path mapping, and the
  handover guard. `CONTRIBUTING.md`, `SECURITY.md`, `docs/releasing.md`: contributing, reporting
  and releasing.

Apache-2.0; see `LICENSE`.
