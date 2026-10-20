# Security policy

## Reporting a vulnerability

Do not open a public issue for a vulnerability. Use GitHub's private vulnerability reporting for
this repository (Security -> Report a vulnerability), or open a minimal non-sensitive issue asking
a maintainer to establish a private channel.

Report, for example:

- a way for `jpdev record post` to publish a local path, or a line that matches the name-pattern
  file, which it is meant to refuse;
- a way for a step to run something the repository's `dev.json` does not name, or outside the caps
  its toolchain sets;
- a way for the release workflow to publish files other than the ones the run built from the tagged
  commit, or to publish without the maintainer's approval at the `release` environment;
- a release file whose attestation does not verify against the release workflow and the tag;
- a setting, token or credential of the person running the kit reaching a log, a summary block or
  a posted record.

Include the command, the kit version and a reproduction. We confirm receipt within five working
days.

## Scope

The kit runs the commands a repository's `dev.json` names, as the person who runs it. A manifest
is code: running `jpdev check` or `scripts/dev/check.sh` in a repository you do not trust runs that
repository's commands. The caps limit memory and time, not authority, and are not a sandbox; a
report that only shows a manifest running its own commands is out of scope.
