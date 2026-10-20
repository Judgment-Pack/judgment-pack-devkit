# Brief: TITLE (issue #N of OWNER/NAME)

## Rules
Read this repository's AGENTS.md and follow it. Work only in the current directory. Start no
sub-agents. Never use a pattern kill (`pkill`, `killall`).

You cannot write `.git` here, so do not run `git commit`, `git push` or `gh`. Edit the files, run
the repository's check list once (`scripts/dev/check.sh`, or `jpdev check`), and write the two
files below. The wrapper that started you (`jpdev codex run`) then commits the changes to tracked
files with a sign-off, pushes the branch and opens the pull request.

## Goal
What the issue asks for, in one or two sentences. Link the accepted design.

## What to build
1. The first change, with the file it belongs in.
2. The next change.

Describe each refusal the code must produce as the input it receives and the exact error, status
or message it returns.

## Tests
A test for every new behaviour. Write vectors by hand. Break the change and watch the test fail
before you rely on it.

## Files you write
Write both in the repository root. They are read, never committed.

- `msg.txt`: the commit message. A subject of at most 72 characters in the imperative, a blank
  line, then a plain, factual body (what changed and why). Leave out `Signed-off-by` and
  `Co-Authored-By` lines: the wrapper adds them.
- `pr.md`: the pull request body. Its first line is `Closes #N.`; then the sections
  `## What it adds`, `## Checks` (paste the summary block that the check list printed) and
  `## Not in this PR`; then a last line saying a Codex session wrote the change.

No machine-local path and no personal name in any file, `msg.txt` or `pr.md`.

## New files
The wrapper commits changes to files that are already tracked. If you create a file, name it in
your final message (one path per line under the heading `New files`) so that it can be passed
with `--add`.

## Report
Your final message is under 10 lines: what changed, the check summary block, the new files, and
anything you left out and why.
