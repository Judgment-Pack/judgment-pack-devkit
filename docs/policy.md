# Operating policy for agent work

This is how work on the Judgment Pack repositories is run when agent sessions build, review
and release it. It applies to every session alike, whichever program runs it. A session is
told its role (builder, reviewer, release reviewer) and its task in its brief; the rules below
are the ones a brief does not repeat.

## Who owns what

- **CI owns everything deterministic.** Formatting, builds, unit tests, schema checks,
  certification suites, whitespace and path checks run in CI on every pull request. A session
  does not re-run them to reassure itself and does not watch CI run.
- **Duplication is where two copies drift:** a repository opts in to the `duplication` check with
  its own token and line thresholds in `jpdev.json`, and marks an intentional copy with an explicit
  ignore block.
- **Define and implement a dependency-ordered coherent batch first.** Name the related issues,
  dependency order and acceptance criteria; write acceptance and regression fixtures by hand
  alongside code. During development, run useful focused checks of changed paths, affected
  contracts, both-language readers and relevant interactions (`jpdev check --only NAME[,NAME]`
  or `scripts/dev/check.sh --only NAME[,NAME]`). Do not run a full suite or CI cycle merely per
  completed issue, intermediate commit or handoff.
- **Run the required full checklist once for the stable integrated candidate before CI.** Use
  `jpdev check` or `scripts/dev/check.sh`. Record scope, exact candidate identity (head and any
  uncommitted diff), commands, actual summary and CI ownership. An intermediate handoff identifies
  who owns the pending stable-batch gate; it does not trigger another full run. A skipped or unrun
  check is not a pass. After failures, group related fixes and rerun affected checks. Repeat broad
  validation only for actual repository requirements, substantive changes or unresolved evidence,
  including unknown affected coverage or changed runner/check-selection semantics.
- **Keep automatic CI enabled.** Every merge candidate still requires its own exact-head checks.
  Full deterministic CI remains required for the integrated candidate, default branch and release
  under the repository's actual gates. Push, report once and stop; do not watch CI.
- **Reviewers reuse verified evidence and the existing candidate build.** Review begins only
  after green exact-head CI. Build once only if the required build is unavailable or invalid for
  that candidate, then run probes of uncovered contracts and meaningful safeguard-removal checks
  (`jpdev mutants` where applicable). Do not repeat suites that CI already verified.
- **Each commit is signed off, no history is rewritten.** Pushes are never forced, and go
  through the `gh` credential helper (`jpdev push`), never a stored credential.

## Testing

- **Verify the world, not the self-report.** Check claims against artifacts: the candidate head
  and diff, files actually included, working directory, executed commands, output and assertions.
  A builder's report alone does not establish that files exist or that a suite ran.
- **Prefer real implementations over mocks.** Use a mock for a dependency that cannot run in CI
  and document that limitation. Test the command, endpoint or exported entry a consumer uses,
  rather than an internal shortcut that bypasses the contract.
- **Resolve the product under test explicitly.** Use the candidate's source/build path and verify
  its identity. Never launch an installed product by a bare name that could silently select a
  different build. Model CLIs and toolchains used as dependencies are allowed; record their
  identity where relevant. This rule prevents testing the wrong product, not using tools.
- **Handwrite acceptance and regression fixtures.** Do not record expected vectors from the
  implementation under test.
- **Break each safeguard once.** Remove the fix or safeguard in scratch and verify that the
  regression test fails at its intended assertion. A setup error, compilation failure or timeout
  does not count. Preserve the failing assertion and restored passing evidence.

Evidence reuse applies only where an actual repository gate implements and validates equivalence.
This policy does not introduce automatic changed-check selection or release-evidence reuse:
Devkit #33 (`--changed`), Devkit #37 and Agent #213 remain separate work. Keep the summary of
what actually ran and what remains required by current CI/release gates.

## Who builds and who reviews

- **A build or a review runs on the model the operator selects by use case**, never by habit:
  the most capable model available at the effort the task needs is the default for building
  and for clean-room reviewing; a cheaper tier is chosen only when the operator says so for a
  narrow, well-specified task (mechanical rows, test-only changes, scans), and never for a
  review of record. The cost that counts is the cost per completed task: a cheaper run that
  needs another round is dearer than one run that finishes.
- **The reviewer is never the builder's own session and never a weaker tier than the builder's.**
  A review record names the vendor and model that reviewed; a same-vendor review says so and
  does not claim to be cross-vendor.
- **Boundary decisions** (the architecture decision records that set a security boundary) are
  built and reviewed at the highest tier the operator has.
- **Codex is one way to run a build**, chosen by the operator per run, not the default. A Codex
  build runs from a brief with `jpdev codex run`: the model and the effort are always passed,
  the sandbox is `workspace-write` with network access, stdin is closed, and the prompt names
  the repository's `AGENTS.md` as the rules. Codex cannot write `.git` in that sandbox, so it
  does not commit: it writes `msg.txt` and `pr.md` (the brief skeleton from
  `jpdev codex brief-template` says so), and `jpdev codex run` commits the tracked changes with
  a sign-off, pushes through the `gh` credential helper and opens the pull request from those
  two files. `danger-full-access` is chosen explicitly or not at all.
- A brief describes the documented refusal the code must produce (the input, and the exact
  refusal), not the attack the refusal answers: a provider's content filter can refuse a brief
  that names attacks as verbs or nouns. `jpdev codex check-brief` refuses such a brief before
  the run, and `jpdev codex run` runs the same check first.

## Turnaround

Two builds may run in parallel on sibling branches of one repository when their shared paths are
additive. Builders append to the manifest's `handover.shared_paths`; they do not reorder or rewrite
those files, and they never fetch, rebase or merge. The coordinator carries `main` into each branch
after its push.

Before handover, a builder applies the self-checks in AGENTS.md to its own candidate and records
what ran locally and any pending stable-batch checklist/CI ownership at an intermediate handoff.
Run the full checklist on the stable integrated candidate before CI as described above; serialize heavy checks under the repository lock. CI must be green on the exact
reviewed head before review begins. `jpdev codex run` gives Codex clone-local scratch, lock, Go and
npm caches and an XDG cache when those variables are empty, and creates their directories under
the clone. Builder `TMPDIR` is always created under its effective scratch, including when an
external temporary directory was inherited.

After a fix round that closed only MEDIUM findings, the review re-read may use the cheaper tier.
After a HIGH finding, the re-read uses the same tier as the review of record. A HIGH is fixed in the
pull request before review, MEDIUMs named by the review of record are fixed in that fix round, a
MEDIUM found only on re-read goes to the pre-release batch, and LOW rides.

`jpdev codex run --small` is for a bounded fix on an existing branch. It tells the builder to run
only the touched check-list steps; CI runs the whole list. The wrapper refuses the result after the
run if it changed a manifest `handover.shared_paths` or `handover.boundary_paths` entry, or if its
added and removed lines exceed `JPDEV_SMALL_MAX_LINES` (80 by default). The size/path guard is
unchanged by the batch workflow. A relevant CI failure gets a focused fix and rerun; reuse the builder unless the safeguard-stop rule below requires a fresh session.

Use `jpdev codex run --resume THREAD` only for the fix round after review on the same branch. Every
thread id the CLI reports is recorded in `.jpdev/output/thread`. Never resume a builder that a safeguard stopped;
the fresh-builder rule under Safeguards and stops still applies.

For sibling work, `jpdev codex run --worktree BASE` and `jpdev worktree add|list|remove` keep the git
objects in one base clone. Go, npm and XDG caches are shared under `BASE/.jpdev-shared`; the lock and
other scratch state stay in each worktree. npm `node_modules` may be linked from the base when both
worktrees use the same platform, Node release and lockfile. Where lifecycle scripts, native modules
or package-manager behavior make that unsafe, leave it unlinked and run `npm ci` in the worktree.

The update-branches workflow normally carries the default branch without an agent. When it applies
the `carry needed` label, `jpdev carry --pr N` starts from a generated conflict brief and uses the
normal no-new-pull-request Codex path; a carry with no conflicts is signed and pushed directly.

## Reviews

- A change to a security boundary (what a model or a caller may reach, what is trusted, what is
  signed or verified) gets a clean-room review per pull request: a reviewer that has not seen
  the builder's reasoning, only the diff and the issue.
- Everything else gets a narrow review: the changed files, the tests that claim to hold them,
  the rows of the mutation table the change touches.
- Before a tag, one release review reads the whole diff since the previous tag. After a batch
  of fixes to its findings, the same reviewer re-reads the fixes; a new reviewer starts over
  and is not asked to.
- One independent review per material pull request, with depth matched to risk. Reuse the builder
  for corrections and the original reviewer for finding-specific confirmation after green
  exact-head CI. Do not restart a broad review without substantive change or new evidence; the
  whole-release review remains required.

`jpdev codex review` runs a checked review brief with an explicit model and effort, closes stdin,
and writes the final report to a file without committing, pushing or posting. The default sandbox
is `workspace-write` because read-only prevents shell probes from making temporary files; the brief
has no network unless the caller passes `--network`, forbids Git writes, and the command refuses
the result if HEAD or a tracked file changed. The command itself never posts. A Codex review of a
Codex build is the same vendor (OpenAI), not a cross-vendor claim.

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

## Scratch and cleanup

A session removes only state it created. Use `jpdev clean` after the pull request it built or
reviewed merges, after release, and when disk use exceeds 85%. Never remove another session's
data, a live checkout, or an operator reserve. Operator approval authorizes one narrow
`jpdev clean --root DIR --older-than DURATION --yes` invocation; all tool checks still apply.
Inspect the dry run first. Approval does not transfer ownership of existing state.

Before creating disposable state, initialize an empty, session-created root with
`jpdev clean init --root DIR --session TOKEN`. TOKEN is 8–80 letters, digits, underscores or
hyphens, beginning with a letter or digit; choose a unique session prefix. Init creates DIR
if its parent exists, and refuses a nonempty directory. Put the session's clone, worktrees,
review rooms, logs and scratch beneath it. Configure `JPDEV_SCRATCH` and other output locations
there as needed. The wrapper creates builder `TMPDIR` beneath its effective scratch, replacing
an inherited temporary directory. Temporary files stay in scratch, never loose in the system
temporary directory; temporary directories carry the session prefix.

After the session finishes writing a disposable path, explicitly attest its ownership and
contents with `jpdev clean seal --root DIR --session TOKEN --path REL --kind KIND`. This is an
operator/session assertion that every included file, including untracked, ignored and review
evidence, was created by this session and is disposable at the requested milestone. Never seal
someone else's files. Sealing historical unmarked directories is forbidden; init cannot adopt
their nonempty root. Tools do not automatically seal or infer ownership from a name or UID.
A changed path needs a new explicit seal after its evidence has been assessed.

Kinds are `worktree`, `review` (including reviewer clones), `transcript` (a log directory
or an individual regular log/transcript file), `scratch`, and `cache`. Scratch for a removed
worktree also requires `--base BASE --removed-worktree OLD`; shared base caches require
`--base BASE`. BASE and OLD are absolute in the stored seal; supply all relevant roots explicitly
to cleanup. A whole worktree seal may include its own scratch, locks and caches. Seal separate
scratch/lock/cache directories with `scratch` when they outlive that worktree. Base
`.jpdev-shared` contents are eligible only once no linked worktree directory remains. Unknown,
inaccessible, symlinked or out-of-root worktree registration evidence causes refusal. Stale Git
registration entries for verified absent paths beneath authorized, traversable parents are
retained and do not count as active users. Cleanup does not prune Git administrative records or
remove branch refs: a broad prune could affect another session.

`jpdev clean [--root DIR]... [--older-than DURATION] [--min-transcript-bytes N] [--yes]` discovers only disposal seals,
never recursively guesses candidates from directory names. There are no implicit roots; no flags
means no deletion. Missing roots are reported safely. It defaults to a dry run and seven days;
DURATION is a nonnegative integer followed by `s`, `m`, `h`, `d` or `w`. Age is measured from the
newest seal timestamp, candidate directory/file mtime and inventoried content mtime. Thus a new
seal must age even if its logs are old. Transcripts/logs require at least 10485760 bytes (10 MiB)
by default. `--min-transcript-bytes N` sets an inclusive, nonnegative integer floor; `0` disables
it. The floor applies only to the `transcript` kind and counts logical regular-file bytes,
summing all regular files for a directory; directory sizes do not count. Other kinds are unaffected.
Paths are root-relative, exact, and cannot contain empty, dot or parent components.
Overlapping candidate seals are refused. The ownership metadata and keep file are protected.

Place exact root-relative reserves in `DIR/.jpdev-clean-keep`, one per line; blank lines and
`#` comments are allowed. A reserve protects itself, descendants, and any candidate containing it.
Invalid or symlinked keep files cause refusal. Roots, the invoking checkout, home, base checkouts
and any candidate containing an explicitly authorized root are protected. Keep all live checkouts
and operator reserves in this file even when their names look disposable.

Cleanup requires the recorded inode identities and complete SHA-256/stat inventory to match,
including all ignored and untracked files. A clean tracked diff is insufficient. Git worktrees
must have no tracked or staged changes and no unpublished commits reachable from HEAD or any
local ref, including tags, stashes and other branches. Git metadata must lie beneath an explicitly
authorized root. Publication is checked against current `git ls-remote --refs origin`, without
fetching. Locally unavailable remote objects cause refusal. Attached branches require a verified
origin upstream containing HEAD and a GitHub PR with matching branch and HEAD in CLOSED or
MERGED state. Detached worktrees and detached reviewer clones use verified remote reachability
without a PR. Reviewer clones with attached branches use the same upstream and PR checks.
A reviewer clone with any registered linked worktree remains protected. Bare repositories and
saved Git metadata directories at the candidate root or nested within it are unsupported and
refused, including partial HEAD/index/commondir layouts. Only a verified candidate's canonical
`.git` metadata directory is allowed. Assume-unchanged and skip-worktree index flags are refused,
even with an explicit disposal seal: they can hide changed tracked contents.

Inherited `GIT_*` settings are refused except `GIT_OPTIONAL_LOCKS`, `GIT_TERMINAL_PROMPT`,
`GIT_PAGER` and `GIT_CEILING_DIRECTORIES`. Cleanup forces noninteractive, read-only Git commands
and disables the pager; the ceiling only bounds discovery. Index, repository, object, namespace,
shallow-history, executable and config redirection are therefore refused, including unknown
Git settings. System/global Git config and replacement objects are disabled for verification;
external diff and text conversion are disabled for tracked-diff evidence. Authentication that
depends on ambient Git config can consequently be unavailable and cause refusal. Git, remote and PR
evidence must remain available; an unavailable tool, network or
authentication causes refusal. `gh` is needed only for attached branches.

Deletion requires Linux procfs with the initial host PID namespace (Linux initial namespace inode
4026531836), the host mount namespace and root view, and readable process evidence for every
visible process. Processes in another mount namespace or root view cause refusal because path
aliases cannot establish inactivity. A container, sandbox, PID namespace, hidden process view or permission restriction
cannot establish host inactivity and is refused. Process cwd, root, executable, open descriptors,
mappings, command arguments and declared scratch/cache environment paths are checked. Live
processes are reported by PID and never stopped. Symlinks, special files, nested repositories,
mount crossings and changed ownership are refused. The tool requires directory descriptors,
`O_NOFOLLOW` and POSIX locking; unsupported platforms fail closed.

Before removal the tool repeats inspection, moves the candidate to a private sibling quarantine
name, and rechecks its full inventory, Git state, keeps, root and parent identities and process
activity. Cache worktree users and scratch associated-worktree absence are rechecked after
quarantine and before each removal, including the candidate directory itself. Removal uses directory
descriptors, never recursive path-following deletion. Each
entry's identity and inventory is checked during removal. External linked-worktree refs, HEAD
and index are rechecked during removal as well. Changes or failures stop that candidate;
remaining content is restored to its original name when vacant, otherwise retained under
`.jpdev-clean-removing-<token>` for operator inspection. A refusal can leave a partially removed
candidate; the remaining evidence is retained and requires assessment before another seal.
These checks address ordinary concurrent activity; they do not isolate a malicious process with
the same user identity, which can edit the tool or its ownership records.

Cleanup prints JSON Lines: candidate records contain `root`, root-relative `path`, logical `bytes`,
`reason` and `outcome`; `--yes` adds per-path `removed` or `refused` outcomes. The final record gives
`candidates`, logical `bytes`, `removed`, `refused` and `mode`. Totals count inspected candidates,
including candidates later refused during removal; they do not estimate physical reclaimed space.
No candidate or root failure is silently skipped. Exit 0 means no refusal (including a no-op or
absent root), 1 means cleanup reported a refusal/removal failure, and 2 means invalid arguments or
init/seal refusal. Init and seal print a short confirmation, rather than cleanup JSON Lines.

On-disk metadata is version 1 JSON in `DIR/.jpdev-clean`: `owner.json` records session token and
root device/inode; each seal is named by SHA-256 of its relative path and records version, session,
path, kind, candidate device/inode, seal time, content inventory, and optional base/removed paths.
Inventory keys are relative paths (empty for a standalone transcript file); values hold device,
inode, mode, logical size, nanosecond mtime/ctime, and SHA-256 for regular files. Records must be
regular, session-user-owned files, not writable by group/other, and at most 16 MiB. Root ownership
records and reserves are retained. They are local session evidence, never repository content.
