# Working in this repository

This file is read by Codex as `AGENTS.md` and by Claude as `CLAUDE.md`; the two are the same text.
Edit `AGENTS.md` and run `scripts/sync-agent-docs.sh` to regenerate `CLAUDE.md`.

## Before you open a pull request

- Run `scripts/dev/check.sh` (or `jpdev check` where the kit is installed) once. It runs the
  checks listed in `dev.json` in order and prints one summary block.
- Paste that summary block in the pull request body, under a "Checks" heading.
- If a check fails: read its first lines in the block, fix the cause, re-run that one check with
  `--only NAME`, then run the whole list once more. Do not loop on the whole list.
- Start no CI watch. Push, report once, and stop; CI owns everything deterministic.

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
  holds the two together.
- This file is `templates/AGENTS.md` plus this section. Change a shared rule in the template and
  here together, then run `scripts/sync-agent-docs.sh .` for `CLAUDE.md`.
- Machine settings (paths, caps, name lists) never live in this repository. They are read from the
  person's config file and environment (`config/env.example` documents each); a tracked file holds
  no path of any machine.
- Only a maintainer releases (`docs/releasing.md`); a pull request does not change the version or
  write the next version's notes.
