# Brief: TITLE (issue #N of OWNER/NAME)

## Rules
Read this repository's AGENTS.md and follow it. Work only in the current directory. Start no
sub-agents. Temporary files belong beneath `$JPDEV_SCRATCH` (including `$TMPDIR`),
never loose in the system temporary directory. Give temporary directories a session prefix.
Never use a pattern kill (`pkill`, `killall`).

You cannot write `.git` here, so do not run `git commit`, `git push` or `gh`. Define the related
issues, dependency order and acceptance criteria, then implement the coherent batch with
handwritten fixtures. Use useful focused checks during development. Run the required full checklist once
for the stable integrated candidate before CI (`scripts/dev/check.sh`, or `jpdev check`).
Do not run a full suite or CI cycle merely per issue, intermediate commit or handoff. For an
incomplete batch, identify who owns the pending stable-batch gate. The wrapper that started you
(`jpdev codex run`) then commits tracked changes with a sign-off, pushes and opens the pull request.

## Goal
What the issue asks for, in one or two sentences. Link the accepted design.

## What to build
1. The first change, with the file it belongs in.
2. The next change.

Describe each refusal the code must produce as the input it receives and the exact error, status
or message it returns.

## Tests
Follow [Testing in the Devkit policy](https://github.com/Judgment-Pack/judgment-pack-devkit/blob/main/docs/policy.md#testing).
Add handwritten acceptance/regression fixtures alongside each new behaviour. Verify artifacts,
real implementations and consumer entry paths; resolve the candidate product explicitly so an
installed binary cannot silently replace it. Remove each safeguard once in scratch and require
the intended assertion to fail, not setup, compilation or timeout. Preserve the evidence.

## Before you write msg.txt
Use AGENTS.md "Before you hand over" for the full self-check text.
- (a) Confirm the boundary-path diff changes no admission or verdict unless the issue names it.
- (b) Confirm every new schema member and enum value is carried by a vector.
- (c) Confirm both language readers pass over every shared vector added.
- (d) Confirm every new mutation row and its hand-written twin are caught.
- (e) Confirm every new refusal event validates with empty, missing and oversized input.
- (f) Confirm interrupted and resumed runs carry every new checkpoint member.
- (g) Confirm the design's words and the code agree sentence by sentence.
Use useful focused checks during development for changed paths, both-language readers and affected
interactions, then run the required full checklist on the stable integrated batch before CI.
Record exact candidate identity, commands, scope, results and remaining gate ownership; unrun checks
are not passes. Group related fixes after failures and rerun affected checks. Repeat broad validation
only for actual repository requirements, substantive changes or unresolved evidence. Keep automatic
CI enabled; every merge candidate still requires its own exact-head checks.
Append only to `handover.shared_paths`; never fetch, rebase or merge as the builder.

## Files you write
Write both in the repository root. They are read, never committed.

- `msg.txt`: the commit message. A subject of at most 72 characters in the imperative, a blank
  line, then a plain, factual body (what changed and why). Leave out `Signed-off-by` and
  `Co-Authored-By` lines: the wrapper adds them.
- `pr.md`: the pull request body. Its first line is `Closes #N.`; then the sections
  `## What it adds`, `## Checks` (actual summary, candidate identity, scope and deferred CI) and
  `## Not in this PR`; then a last line saying a Codex session wrote the change.

No machine-local path and no personal name in any file, `msg.txt` or `pr.md`.

## New files
The wrapper commits changes to files that are already tracked. If you create a file, name it in
your final message (one path per line under the heading `New files`) so that it can be passed
with `--add`.

## Report
Your final message is under 10 lines: what changed, the check summary block, the new files, and
anything you left out and why.
