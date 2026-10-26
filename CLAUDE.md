# Working in this repository

This file is read by Codex as `AGENTS.md` and by Claude as `CLAUDE.md`; the two are the same text.
Edit `AGENTS.md` and run `scripts/sync-agent-docs.sh` to regenerate `CLAUDE.md`.

## Before you open a pull request

- Define the related issues, dependency order and acceptance criteria, then implement a coherent
  batch with handwritten acceptance and regression fixtures alongside the code. Do not run a
  full local suite or CI cycle merely per issue, intermediate commit or handoff.
- During development, run useful focused checks for changed paths, affected contracts and
  relevant interactions, including both readers of shared language vectors. Use
  `scripts/dev/check.sh --only NAME[,NAME]` (or `jpdev check --only NAME[,NAME]`).
- Run the required full checklist once for the stable integrated candidate before CI:
  `scripts/dev/check.sh` (or `jpdev check`). This gate belongs to the coherent batch, not each
  issue or intermediate handoff. Every merge candidate still requires its own exact-head checks.
- Paste the actual summary in the pull request body under "Checks". Record the exact candidate
  identity (head and any uncommitted diff), scope, commands, results and remaining CI ownership.
  A skipped or unrun check is not a pass.
- After failures, group related fixes and rerun affected checks with `--only NAME`. Repeat broad
  validation only when actual repository requirements, substantive changes or unresolved evidence
  warrant it, including unknown affected coverage or changed runner/check-selection semantics.
- Keep automatic CI enabled. Full deterministic validation remains required in CI for the
  integrated candidate, default branch and release under the repository's actual gates. Review
  begins only after green CI on the exact reviewed head. Start no CI watch; report once and stop
  after pushing.
- Push with `jpdev push [BRANCH]`, or where the kit is not installed with
  `git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push -u origin BRANCH`.
  The machine's stored git credential can be another account's, and a plain `git push` is then
  refused; the helper form uses the `gh` login. Never store a credential, never change global git
  configuration, never push with force (`jpdev push` refuses `--force` and `-f`).

## Before you hand over

Run these self-checks on the builder's own head before writing the commit message:

- (a) The boundary paths in `dev.json` (`handover.boundary_paths`) show no admission or verdict
  change unless the issue names one: `git diff origin/main...HEAD -- <paths>` contains additions to
  offer tables or new paths only.
- (b) Every schema member and enum value the change adds is carried by at least one vector: remove
  it from a scratch copy of the schema and a vector fails.
- (c) Where two languages read the same vectors, both readers pass over everything added.
- (d) Every mutation row added is caught, and its twin in the other language is caught by hand.
- (e) Every refusal path added emits an event that validates with a malformed input: empty,
  missing or oversized.
- (f) An interrupted and resumed run carries every new checkpoint member.
- (g) The design's words and the code agree sentence by sentence.

Record applicable self-checks and the stable batch checklist result, or identify the coordinator
who owns that gate when handing off an incomplete batch. Keep heavy checks
serialized under the repository lock and temporary state beneath the session scratch/TMPDIR.
Change the paths in `dev.json` `handover.shared_paths` by appending only, never by reordering or
rewriting, because a sibling build may be open. Never fetch, rebase or merge; the coordinator
carries `main` into the branch after the push.

A HIGH (a path that executes twice, runs without approval, or crosses a boundary the issue did not
open) is fixed in the pull request before review. MEDIUMs named by the review of record are fixed in
the same fix round; a MEDIUM found only on a re-read goes to the pre-release batch. LOW rides.

## Testing

- Verify claims against artifacts: inspect the actual files, candidate identity, working directory,
  command output and assertions. A report alone does not prove files were included or tests ran.
- Prefer real implementations and consumer entry paths (commands, endpoints or exported APIs).
  Use mocks only for dependencies that cannot run in CI, and state that limitation.
- Resolve the product under test to the candidate's explicit source or build path; never let an
  installed product of the same name silently run instead. This does not prohibit model CLIs or
  toolchains used as dependencies; record their identity when relevant.
- Write acceptance/regression vectors and fixtures by hand, not from the implementation's output.
- Remove each new fix or safeguard once in scratch and show its regression test fails at the
  intended assertion. Setup, compilation errors and timeouts do not demonstrate that assertion.

## Rules

- Write test vectors and fixtures by hand. Never record them "from a run" of the code under test.
- Keep machine-local paths and personal names out of tracked files, commit messages and pull
  request bodies. Refer to people by role or handle where a name is needed.
- Sign off every commit (`git commit -s`). Never force-push; never rewrite published history.
- End a process you started by its process id. Never use a pattern kill (`pkill`, `killall`).
- One pull request per issue or batch. State what changed and why in plain, factual wording.
- A change to a public surface (a schema, a contract, a command's output) says so in the pull
  request and changes its vectors and documentation in the same pull request.
- If a safeguard stops you (a permission prompt, a refused command, a failed gate), stop and say
  so in your report. Do not work around it.

## Reports

Your final report is short: the pull request and its head commit, what changed, the check
summary block, and anything you stopped on or chose not to do.

## This repository

- The kit is bash 5 and the python3 standard library. Write for bash 5; `shellcheck` runs on every
  script and a finding is fixed, not silenced, unless the comment above the directive says why.
- `tests/run.sh` is the kit's own test run (no network; it needs git, python3, rsync, flock and go).
  The templates are the product: a change to a file under `templates/`, to `lib/`, to `bin/jpdev` or
  to a setting has its test in `tests/run.sh` in the same pull request. Break the change and watch
  the test fail before you rely on it.
- `scripts/dev/check.sh` is a copy of `templates/check.sh`; after a change to the template, copy
  it again. Line 2 of the template names the kit version (`# from judgment-pack-devkit vX.Y.Z
  (templates/check.sh)`) and moves with `JPDEV_VERSION` in `lib/common.sh` at a release; a test
  holds the two together. `scripts/dev/changed_checks.py` is `lib/changed_checks.py` and
  `scripts/dev/release_evidence.py` is `lib/release_evidence.py`, each with the same version on
  line 2; after a change to a library file, copy it again.
- This file is `templates/AGENTS.md` plus this section. Change a shared rule in the template and
  here together, then run `scripts/sync-agent-docs.sh .` for `CLAUDE.md`.
- Machine settings (paths, caps, name lists) never live in this repository. They are read from the
  person's config file and environment (`config/env.example` documents each); a tracked file holds
  no path of any machine.
- Only a maintainer releases (`docs/releasing.md`); a pull request does not change the version or
  write the next version's notes.
