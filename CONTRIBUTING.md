# Contributing

Thank you for helping. This repository is the development kit of the Judgment Pack repositories:
the `jpdev` command, the manifest schema, the runner and agent instructions a repository vendors,
and the policy for agent work. It is plain bash 5 with the python3 standard library.

## Working on an issue

Say on the issue that you are taking it. Keep a pull request to one issue. A change to a public
surface (a command's output or options, `templates/dev.schema.json`, a template, a setting) says
so in the pull request and changes its tests and documentation in the same pull request. The
templates are what other repositories vendor, so a change to a template has its test in
`tests/run.sh`.

## Local checks

Run the repository's own check list once before you open a pull request, and paste its summary
block in the pull request body:

```sh
scripts/dev/check.sh
```

It runs the steps of [`dev.json`](dev.json) in order: `git diff --check`, no machine-local paths in
tracked text, `CLAUDE.md` generated from `AGENTS.md`, `bash -n` over every script, the JSON
documents parse, `shellcheck`, and `tests/run.sh`. CI runs the same list through the same runner.
To run one step again, `scripts/dev/check.sh --only NAME`.

Each tool by itself:

```sh
tests/run.sh
shellcheck -x -P ".:SCRIPTDIR" bin/* lib/*.sh templates/*.sh scripts/*.sh scripts/dev/*.sh tests/*.sh tests/fixture/*.sh
```

`tests/run.sh` needs bash 5, git, python3, rsync, flock and go, and no network. `shellcheck` is the
native program (`apt install shellcheck`, or a release from its repository), not an npm package.

## Agent instructions

`AGENTS.md` and `CLAUDE.md` are one text: edit `AGENTS.md` and run `scripts/sync-agent-docs.sh .`
to regenerate `CLAUDE.md`. The shared rules come from `templates/AGENTS.md`; change them there and
in the root copy together. The repository's own rules sit under "This repository" in `AGENTS.md`.

## Developer Certificate of Origin

Every commit is signed off (`git commit -s`) under the
[Developer Certificate of Origin](https://developercertificate.org/). The sign-off name and email
must match the commit's author.

## Licence

Contributions are accepted under Apache-2.0, the repository's licence.

## Releases

Only maintainers release; see [docs/releasing.md](docs/releasing.md).

## Conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
