# Operating policy for agent work

This is how work on the Judgment Pack repositories is run when agent sessions build, review
and release it. It applies to every session alike, whichever program runs it. A session is
told its role (builder, reviewer, release reviewer) and its task in its brief; the rules below
are the ones a brief does not repeat.

## Who owns what

- **CI owns everything deterministic.** Formatting, builds, unit tests, schema checks,
  certification suites, whitespace and path checks run in CI on every pull request. A session
  does not re-run them to reassure itself and does not watch CI run.
- **A builder runs the repository's check list once locally before pushing.** `jpdev check`, or
  `scripts/dev/check.sh` where the kit is not installed. The summary block goes in the pull
  request body. If a check fails: fix, re-run the one check, then the whole list once. A builder
  starts no CI watch: it pushes, opens the pull request, reports once and stops.
- **A reviewer builds once and runs probes and mutants only.** The reviewer does not re-run the
  suites CI runs. It reads the diff, builds the change once, runs the probes it writes to test
  a claim, and breaks each safeguard the change adds (`jpdev mutants`) to see that a test
  notices. A safeguard whose test passes with the safeguard removed is a finding.
- **Each commit is signed off, no history is rewritten.** Pushes are never forced, and go
  through the `gh` credential helper (`jpdev push`), never a stored credential.

## Who builds and who reviews

- **Codex builds non-boundary issues** from accepted designs and briefs, and Claude reviews
  them.
- **Claude builds boundary decisions** (the architecture decision records that set a security
  boundary), and Codex reviews them when its quota allows.
- A Codex build runs from a brief with `jpdev codex run`: the model and the effort are always
  passed, the sandbox is `workspace-write` with network access, stdin is closed, and the prompt
  names the repository's `AGENTS.md` as the rules. Codex cannot write `.git` in that sandbox, so
  it does not commit: it writes `msg.txt` and `pr.md` (the brief skeleton from
  `jpdev codex brief-template` says so), and `jpdev codex run` commits the tracked changes with
  a sign-off, pushes through the `gh` credential helper and opens the pull request from those two
  files. `danger-full-access` is chosen explicitly or not at all.
- A brief describes the documented refusal the code must produce (the input, and the exact
  refusal), not the attack the refusal answers: the content filter of the Codex service can
  refuse a brief that names attacks as verbs or nouns. `jpdev codex check-brief` refuses such a
  brief before the run, and `jpdev codex run` runs the same check first.

## Turnaround

Two builds may run in parallel on sibling branches of one repository when their shared paths are
additive. Builders append to the manifest's `handover.shared_paths`; they do not reorder or rewrite
those files, and they never fetch, rebase or merge. The coordinator carries `main` into each branch
after its push.

Before handover, a builder runs the self-checks in AGENTS.md on its own head. It uses `--only` for
touched check steps while iterating and runs the whole check list exactly once at the end. CI must
be green before any review begins. `jpdev codex run` gives Codex clone-local scratch, lock, Go and
npm caches and an XDG cache when those variables are empty, and creates their directories under
the clone.

After a fix round that closed only MEDIUM findings, the review re-read may use the cheaper tier.
After a HIGH finding, the re-read uses the same tier as the review of record. A HIGH is fixed in the
pull request before review, MEDIUMs named by the review of record are fixed in that fix round, a
MEDIUM found only on re-read goes to the pre-release batch, and LOW rides.

## Reviews

- A change to a security boundary (what a model or a caller may reach, what is trusted, what is
  signed or verified) gets a clean-room review per pull request: a reviewer that has not seen
  the builder's reasoning, only the diff and the issue.
- Everything else gets a narrow review: the changed files, the tests that claim to hold them,
  the rows of the mutation table the change touches.
- Before a tag, one release review reads the whole diff since the previous tag. After a batch
  of fixes to its findings, the same reviewer re-reads the fixes; a new reviewer starts over
  and is not asked to.
- One round per pull request. A finding small enough to fix is fixed in the pull request with
  its test; a second round is not opened for it.

## Severity

| Severity | What happens |
| --- | --- |
| HIGH | Fixed in the pull request, by the same builder, before merge. The merge waits for it. |
| MEDIUM | Filed as one issue per batch and fixed in one pre-release batch. |
| LOW | Rides: noted in the record, taken up only when a change touches the same code. |

A LOW finding never starts a session of its own.

## Safeguards and stops

A builder that a safeguard stops (a permission refusal, a failed gate, a command the
environment blocks) reports what stopped it and ends. It is not resumed to try again. A fresh
builder continues from the first one's clone and the report, and does not repeat the blocked
action.

## Records

Every review and every release leaves a record on its pull request or issue: the reviewer's
report verbatim, followed by a disposition table, one row per finding, saying what was done
(fixed in this pull request, filed as an issue, accepted with the reason). Before posting, the
record's local paths are reduced to `<scratch>` and `<home>` and the text is checked for
anything the public text must not carry; `jpdev record post` does both and refuses to post
otherwise.

## Releases

One release per decision line: a release carries one decided change or one decided batch, not
whatever happened to be merged. The release review, the tag and the release notes
(`docs/releases/vX.Y.Z.md`) belong to the same decision. Attested release artifacts are
verified before the release is announced.

## Public text

Tracked files, commit messages, pull request bodies and issue comments carry no
machine-local paths and no personal names. A person is referred to by role or by handle where
a reference is needed. Plain, factual wording: what changed, what was checked, what was not.
