# The release evidence gate

A release used to run the CI workflow again at a commit main had already passed. The release
evidence gate lets a release workflow take the CI evidence main already produced at the **exact**
release commit instead, and refuse when that evidence is missing, partial, stale, unreadable or
different. A refusal stops the release; it never becomes a success, and nothing runs CI again on
its own. The fresh route is the operator's choice ([below](#the-fresh-route)).

The gate is `lib/release_evidence.py` (devkit issue #37). A repository vendors it as
`scripts/dev/release_evidence.py`, the library with the kit release on line 2, beside its
configuration `.github/ci-evidence.json` (template: [`templates/ci-evidence.json`](../templates/ci-evidence.json)).
It is python3 with the standard library and `gh`. Each repository adopts it in its own issue,
with its own jobs, matrix legs, pins and fresh checks.

## The contract

Evidence is reused only when all of this holds; anything else refuses.

- **One repository, one commit.** A completed, successful run in this repository (name and
  numeric id, its head repository too, so no fork), at the release commit itself: a
  tree-equivalent commit, a pull request head and a synthetic merge commit are other commits.
- **One workflow.** The workflow resolved by its configured path, with its configured `name:`,
  active; the run, its jobs and its artifacts all bound to that workflow id. Another workflow with
  the same job names is not this one. A commit status or check run, which anyone with write access
  can set under any name, is never read.
- **A trusted trigger.** A `push` to the configured branch, which must be the repository's
  default branch, or a `workflow_dispatch` on it when the configuration lists that event. A run
  associated with a pull request is refused.
- **The newest attempt, never an older green one.** Only a trusted-trigger run is evidence, but
  every run of this repository on the trusted branch at the commit takes part, whatever its
  trigger (a schedule, `workflow_run` or `repository_dispatch` run included): none may be
  unfinished, and none whose latest attempt started after the selected one's may have failed. The
  applicable run whose latest attempt started last is selected, whatever its result: a newer
  failed, cancelled or running attempt is never searched past ([selection](#selection)). Pull
  request and merge queue runs, other branches' runs and runs from another head repository test
  other code or can be started from outside, so they neither count nor block: a fork pull request
  at the release commit cannot hold a release.
- **Every required job and matrix leg,** by display name, each `success` on the configured
  runner labels and a GitHub-hosted runner; jobs that must be skipped (a pull-request-only job)
  are named, and nothing else may be skipped. Each job's check results cover every configured
  check with `PASS`, or `SKIP` only for a named optional skip.
- **The same inputs.** Each job's evidence records the commit's input identities (git object ids
  of the manifest `dev.json`, the configuration, the gate itself, each workflow file and every
  configured pin file) and the runner and tool identity it ran with; the release derives the
  former from its own checkout and the latter from its pins or from its own runner
  ([execution inputs](#execution-inputs)).
- **Fresh enough.** The selected attempt started at most `max_age_hours` (48 at most) before the
  release reads it, and not in the future.
- **Still true at the end.** The run's attempt and the selection are read again after collection,
  every workflow's selection once more after all of them, and the release tag must name the commit
  as an annotated tag, with the same tag object, before and after.

Mutable external state the release workflow checks fresh stays fresh: the tag (grammar, annotated,
naming the commit, on main), the notes, the `release` environment's reviewer rule, the kit version
and vendored copies, the packaged kit run, checksums, attestation, the draft identity and the
published asset digests. The gate decides none of them, and it caches nothing.

## The two commands

```sh
python3 scripts/dev/release_evidence.py capture --workflow KEY --job KEY \
  [--check-log FILE]... [--setup-log FILE]... [--output evidence.json]
python3 scripts/dev/release_evidence.py verify [--output release-evidence.json]
```

Both run from the root of a checkout of the commit (`HEAD` is `GITHUB_SHA`, no tracked file
changed, the configuration and the gate the bytes the commit holds), and both run the same
vendored file, whose path is one of the recorded inputs; `--config` names another configuration
path in the repository.

`capture` runs in a CI job on the trusted branch, after its checks, and writes the job's evidence:
the commit and its input identities, the run id and attempt, the event and ref, the runner image
and tool identity, and the check results read from the runner's summary (`PASS`, `SKIP`, `FAIL`,
`NOT RUN` rows; a log that reports an infrastructure failure refuses). It refuses outside
`refs/heads/<branch>`, for an event the configuration does not list, in another job, and when the
running workflow file (`GITHUB_WORKFLOW_REF`, `GITHUB_WORKFLOW_SHA`) is not the configured one at
the commit. A dispatch that checks out another commit than the run's (an input `sha`) refuses at
the checkout check. The workflow uploads the file as an artifact named
`ci-evidence-<workflow key>-<job key>-<run attempt>`, one per job or matrix leg, with a pinned
`actions/upload-artifact`. Capture is not admission: a local file or a caller's "green" is never
evidence, and `verify` has no input for one.

`verify` runs in the release workflow with `contents: read` and `actions: read`, `GITHUB_SHA` the
release commit and `RELEASE_TAG` its tag. It reads only this repository's REST API through
`gh api` (no other host, no cache), writes the [decision record](#the-decision-record) to standard
output and to `--output`, prints one line, `release-evidence: reuse: ...` or
`release-evidence: refuse: CODE: detail`, and exits 0 only on reuse.

## Configuration

`.github/ci-evidence.json`, schema 2. An unknown or missing member is refused (`config-invalid`,
naming it); `"$comment"` is allowed and ignored in any object whose members are fixed names.

| Member | Meaning |
| --- | --- |
| `schema` | `2` |
| `repository` | `Owner/name`; must be the repository the workflow runs in |
| `branch` | the trusted branch; must be the repository's default branch |
| `max_age_hours` | 1 to 48: the oldest selected attempt start the release takes |
| `inputs` | pin files (repository paths) whose identity the evidence records, beside the manifest, the configuration, the gate and the workflow files, which are always recorded |
| `fresh_at_release` | optional: the checks the release workflow runs itself, tag-sensitive ones among them; carried into the decision record so the log says what the gate does not stand for |
| `profiles.<name>.platform` | `RUNNER_OS`, `RUNNER_ARCH`, optionally `ImageOS`: what the job's runner must report |
| `profiles.<name>.tools` | tool name to the command that prints its identity (`["go", "version"]`); each output is recorded and must not be empty |
| `profiles.<name>.compare` | `release-runner`: the release job resolves the same profile on its own runner, and the evidence must match it exactly (image, version, OS release, every tool); for a leg on the release job's platform. `pins`: the recorded tools must equal `pins` exactly; for a leg the release job cannot resolve itself (another OS or architecture) |
| `profiles.<name>.pins` | tool name to its exact expected output: required for every tool under `pins` (which needs at least one tool), optional under `release-runner`, where it pins a toolchain version on top |
| `workflows.<key>.path`, `.name` | the workflow file under `.github/workflows/` and its `name:` |
| `workflows.<key>.events` | `push`, and `workflow_dispatch` if the fresh route dispatches it |
| `workflows.<key>.skipped_jobs` | optional: display names of jobs that must be present and skipped on the trusted branch |
| `workflows.<key>.jobs.<job key>` | one per job or matrix leg: `name` (the display name the API reports, matrix values included), `job_id` (the key under `jobs:`; legs share it), `labels` (its `runs-on`), `profile`, `checks` (dev.json check names, or `"all"`), optional `optional_skips` and `setup` |

The job key names the artifact, so it is letters, digits, `-` and `_`. The template shows a Linux
job compared with the release runner, a macOS matrix leg held to pins, a pull-request-only skipped
job, a pin file and two tag-sensitive checks.

## Selection

All runs of the workflow at the commit are read (`head_sha` filter, every page of 100, at most
1,000 because GitHub's filtered search stops there; a changed total, a short page, a repeated id
or a missing page refuses). A run is applicable when its branch is the trusted branch and its event
a configured one; only an applicable run is evidence. The scan takes every run at the commit on
the trusted branch, from this repository as head repository, whose event is not a pull request
event (`pull_request`, `pull_request_target`, `pull_request_review`...) or `merge_group`. Then:

1. no applicable run: `run-missing`;
2. any scanned run not `completed` (queued, waiting, in progress, a re-run under way):
   `run-unfinished`;
3. the selected run is the applicable one whose latest attempt started last (`run_started_at`,
   then creation time, then id); a re-run makes its run the newest;
4. any scanned run whose latest attempt started after the selected one's (by start time, not by
   run id: a re-run of an older run is newer) and did not succeed: `run-newer-failed`. A newer
   successful run of another trigger does not block, and is not evidence;
5. the selected run, read again by id, must still be at the attempt listed, `completed` and
   `success`: otherwise `run-race` or `run-result`, the decision record naming the run, attempt and
   result.

Jobs are read from that attempt's own job list, so jobs of another attempt never count; a
failed-jobs-only re-run whose kept jobs belong to an earlier attempt refuses. Artifacts must carry
the selected attempt in their name. An artifact's archive is read, never extracted. Before its
entries are checked, an archive that does not open, a compression other than stored or deflated,
or members declared over 256 KiB is `unavailable-or-malformed`; then the archive must hold exactly
one `evidence.json` (`artifact-entries`); then content over 256 KiB when read, nesting deeper than
16 levels (counted before parsing, so the interpreter's recursion limit plays no part), JSON that
does not parse, or a document that is not an object is `unavailable-or-malformed` too.

## Execution inputs

The same commit alone does not prove the same execution. At one commit the file identities cannot
differ, so the gate records them and compares the captured map with its own derivation: a capture
that read another checkout refuses (`input-identity`). The rest of what a run depends on:

- **Toolchain and image.** Under `release-runner`, a CI image or tool version that is not what the
  release job's runner resolves now refuses (`runtime-identity`, naming what differs): a newer
  hosted image since the CI run means fresh evidence is needed. Under `pins`, the recorded tool
  output must equal the pin, the platform must match, and `ImageOS` when pinned; the image
  version is recorded but not compared.
- **Dependency and integration pins.** A pin file in `inputs` (a lock file, a companion version
  file) is bound by the commit. An input fetched at run time without a pin ("latest") is not
  reproducible and cannot be reused: pin it, or keep that check fresh at release.
- **Tag-sensitive checks.** A check whose result depends on the tag (tag history, a policy tag) is
  not reusable from a run before the tag existed: leave it out of every job's `checks`, keep it in
  the release workflow, and name it in `fresh_at_release`.
- **Runners.** Every required job ran on a GitHub-hosted runner (`runner_group_id` 0, group
  "GitHub Actions") with exactly the configured labels.

## The decision record

`verify` writes one JSON record, decision `reuse` or `refuse`, to standard output (the release
log) and to `--output`; the kit's release keeps the file as the run's `release-evidence-<attempt>`
artifact. It holds:

- `decision`, and `refusal` (`code` and a short `detail`) or `null`;
- `repository`, `repository_id`, `source` (the commit), `tag`, `tag_object`, `branch`,
  `max_age_hours`, `checked_at`, `fresh_at_release`;
- `inputs`: each recorded path's git object id;
- per workflow: `workflow_id`, `path`, `name`, `events`, the number of runs at the commit and of
  applicable ones, the newest runs at the commit, scanned or not (id, attempt, event, branch,
  status, conclusion, start), the
  selected `run_id`, `attempt`, `event`, `status`, `conclusion`, `run_started_at`, `age_hours`,
  and the reusable workflows the run resolved (`referenced_workflows`, each with its commit);
- per job: display name, job id, result, labels, start and end, the artifact (id, name, digest),
  the recorded runtime and check results; and each skipped job's conclusion.

A refusal record holds whatever was established before the refusal. Nothing secret is written:
repository metadata, ids, timestamps and tool versions only; command errors are not printed.

## Refusal classes

| Class | Codes |
| --- | --- |
| wrong commit, tree-equivalent commit | `run-sha`, `evidence-identity`, `job-identity`, `artifact-run`, `run-missing`, `run-identity` |
| wrong repository | `run-repository`, `repository-identity`, `context-repository`, `context-repository-id`, `artifact-run` |
| wrong event or branch (pull request head, synthetic merge, merge queue, another branch) | `run-missing`, `run-trigger`, `branch-default`, `evidence-identity` |
| wrong workflow, mutable status name | `workflow-identity`, `run-workflow`, `job-identity`, `run-missing` |
| missing or failed job, matrix leg or check | `job-coverage`, `job-result`, `artifact-coverage`, `check-coverage` |
| unexpected skip | `job-skipped`, `job-not-skipped`, `check-result` |
| newer failed, cancelled or running attempt | `run-result`, `run-unfinished`, `run-newer-failed`, `run-race`, `attempt-changed`, `latest-changed`, `final-latest-changed` |
| changed inputs | `input-identity`, `runtime-identity`, `job-runner`, `evidence-identity` |
| unavailable or stale evidence | `api-unavailable`, `pagination-*`, `artifact-expired`, `artifact-size`, `artifact-interval`, `artifact-digest`, `artifact-entries`, `run-age`, `timestamp`, `response-size`, `unavailable-or-malformed` |
| tag movement | `tag-syntax`, `tag-annotated`, `tag-commit`, `tag-changed` |
| the release checkout or configuration | `source-sha`, `git-unavailable`, `checkout-root`, `checkout-sha`, `checkout-changed`, `config-source`, `config-invalid`, `helper-source`, `input-missing`, `runner-identity`, `runner-platform`, `tool-identity`, `check-config` |

`capture` refuses with `capture-ref`, `capture-event`, `capture-job`, `capture-workflow`,
`capture-run`, `check-infrastructure`, `check-duplicate`, `check-coverage`, `check-result` and the
checkout and runner codes above.

## The fresh route

A refusal stops that release run. The operator reads the refusal and chooses; no workflow
dispatches or re-runs anything automatically, and no automatic CI is turned off.

1. Make fresh evidence at the same commit, once:
   - re-run **all** jobs of the main CI run at the commit
     (`gh run rerun <run id> --repo <owner/name>`; a failed-jobs-only re-run leaves the other jobs'
     evidence in an earlier attempt and refuses). This also works after main moved on, and is the
     route for `run-age` and a changed hosted image (`runtime-identity`);
   - or, when main still names the commit, dispatch the CI workflow on main
     (`gh workflow run ci.yml --ref main --repo <owner/name>`) where `workflow_dispatch` is a
     configured event.
2. When that run has completed, re-run the release run's failed jobs once
   (`gh run rerun <release run id> --failed`). The gate selects the newest attempt again.
3. If it refuses again, or the evidence cannot be made at that commit (a failure that is the
   code's, main moved on and no run exists at the commit, inputs that stay incompatible), stop:
   fix the cause on main and release a new version from a validated commit under the tag policy.

`run-unfinished` usually means the tag was pushed while main CI at the commit was still running:
wait for it, then step 2. The CI workflow's `workflow_call` trigger is kept, but the release does
not call it: a release-side fallback would need a second trigger on the release workflow, and the
re-run and the dispatch keep the fresh evidence under the trusted-branch identity the gate
verifies.

## The kit's own release

Inventory of the checks at the release commit:

| Check | Main CI (`ci.yml`, push to main) | Release before #38 (v0.6.0, v0.7.0) | Release with the gate |
| --- | --- | --- | --- |
| `diff-check`, `local-paths`, `agent-docs`, `bash-n`, `duplication`, `json`, `shellcheck` | `lint`, run | `CI at the tag / lint`, run again (duplication came after v0.7.0) | taken from `lint`'s evidence |
| `tests` (`tests/run.sh`) | `tests`, run | `CI at the tag / tests`, run again | taken from `tests`' evidence |
| toolchain | ubuntu-latest image, its bash, git, python3, go, shellcheck, rsync | the same image family, not compared | compared with the release runner (`release-runner`) |
| tag, notes, environment reviewer, version and copies, package run, checksums, attestation, draft and published identity | not run | run | run (unchanged) |

No `ci.yml` check depends on the tag: the release-specific checks are in the release workflow
and stay there. The kit has no dependency or integration pins (standard library only).

Measured from the API (job start to completion):

| Release | Path | `verify` | Admit end to package start |
| --- | --- | --- | --- |
| v0.6.0 (run 39844235747) | ci.yml called | lint 9 s, tests 58 s | 63 s |
| v0.7.0 (run 39962449641) | ci.yml called | lint 10 s, tests 57 s | 62 s |
| v0.8.0 (run 40274516108) | evidence gate (#38) | 14 s | 17 s |
| v0.9.0 (run 40351296561) | evidence gate (#38) | 15 s (the gate step itself about 9 s) | 20 s |

Main CI keeps running every check (v0.9.0's main run 40345389159: lint 18 s, tests 102 s). The
gate here reads the same API objects as the #38 gate plus one repository read, so its cost is
expected to be of the same order; it is measured at the next release, not promised. A refusal adds
the fresh route's full CI run and a re-run.

## Limits

- API reads are not a transaction: a run or tag can change after the final read. The release's
  later jobs compare the tag with the commit again before the draft and before publishing, and
  the `release` approval is still required.
- The gate trusts GitHub-hosted runners and the API's reports of them; it is not a package
  provenance system, and a dependency is bound by its source pin and its installer.
- Capture runs only on the trusted branch, so a pull request's CI never exercises it; it is
  observed live on the first main push after a change to it, and `verify` at the next release.
- The tests (`tests/release_evidence_test.py`) run over handwritten API fixtures and a fixture
  repository with a stand-in `gh`; they are not evidence that a remote workflow ran.

GitHub's API contracts: [workflow runs](https://docs.github.com/en/rest/actions/workflow-runs),
[attempt jobs](https://docs.github.com/en/rest/actions/workflow-jobs),
[artifacts](https://docs.github.com/en/rest/actions/artifacts).
