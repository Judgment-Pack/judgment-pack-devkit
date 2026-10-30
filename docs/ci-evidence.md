# The release evidence gate

A release used to run the CI workflow again at a commit main had already passed. The release
evidence gate lets a release workflow take the CI evidence main already produced at the **exact**
release commit instead, and refuse when that evidence is missing, partial, stale, unreadable or
different. A refusal stops the release; it never becomes a success, and nothing runs CI again on
its own. The fresh route is the operator's choice ([below](#the-fresh-route)). One refusal alone, a
hosted image rolled since the CI run, can instead send the release through a strict fresh run of
its check list on its own runner, where the repository opts in ([revalidation](#revalidation)).

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
  Where a workflow opts in, a branch job may take some of its tree-only checks from the merged
  pull request's newest run; the release admits that evidence again under its own contract
  ([pull-request-to-branch reuse](#pull-request-to-branch-reuse)), never on tree equality alone.
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
  ([execution inputs](#execution-inputs)). Where the repository configures the
  [runner identity](#runner-identity) policy, each job also records the image identity its runner
  reports, held to that policy per variant and profile.
- **Fresh enough.** The selected attempt started at most `max_age_hours` (48 at most) before the
  release reads it, and not in the future.
- **Still true at the end.** The run's attempt and the selection are read again after collection,
  every workflow's selection once more after all of them, and the release tag must name the commit
  as an annotated tag, with the same tag object, before and after.
- **A publication is held to its tag.** The tag follows the configured grammar: `vMAJOR.MINOR.PATCH`,
  and a SemVer prerelease only where `tag.prerelease` allows one
  ([tags and dispatch runs](#prerelease-tags-and-dispatch-runs)). A `workflow_dispatch` run of the
  release workflow is refused, or, where `dispatch.validates` is `branch-tip`, validates the branch's
  tip with a decision that is never a publication's.

Mutable external state the release workflow checks fresh stays fresh: the tag (grammar, annotated,
naming the commit, on main), the notes, the `release` environment's reviewer rule, the kit version
and vendored copies, the packaged kit run, checksums, attestation, the draft identity and the
published asset digests. The gate decides none of them, and it caches nothing.

## The two commands

```sh
python3 scripts/dev/release_evidence.py capture --workflow KEY --job KEY \
  [--check-log FILE]... [--setup-log FILE]... [--reuse-plan FILE] [--output evidence.json]
python3 scripts/dev/release_evidence.py verify [--output release-evidence.json]
```

A third, `reuse`, plans a branch job's reuse of its merged pull request's checks where a workflow
opts in ([pull-request-to-branch reuse](#pull-request-to-branch-reuse)); `--reuse-plan` passes its
plan to `capture`.

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
output and to `--output`, prints one line, `release-evidence: reuse: ...`,
`release-evidence: validated, validation-only and never a publication decision: ...`,
`release-evidence: revalidate: JOB: differs from this runner in [...]; ...` or
`release-evidence: refuse: CODE: detail`, and exits 0 on reuse, validated or revalidate, 1
otherwise. Where `GITHUB_OUTPUT` is set it also writes the step outputs `decision` (`reuse`,
`revalidate`, `validated` or `refuse`) and `mode` (`publication`, `validation-only`, or empty when
refused before the mode was known): a job that packages or publishes proceeds on `decision` `reuse`,
or on `revalidate` once the check list has passed strictly on the release runner, never on the
step's exit status.

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
| `tag.prerelease` | optional, default `false` (`tag` absent): `false` admits `vMAJOR.MINOR.PATCH` only; `true` also admits a SemVer prerelease suffix ([below](#prerelease-tags-and-dispatch-runs)) |
| `dispatch.validates` | optional, default `none` (`dispatch` absent): a `workflow_dispatch` run of the release workflow does not use the gate and is refused; `branch-tip`: it validates the trusted branch's tip, validation-only ([below](#prerelease-tags-and-dispatch-runs)) |
| `revalidation.allowed` | optional, default `false` (`revalidation` absent): a release runner whose image or tools differ from the evidence's refuses (`runtime-identity`); `true`: a publication refused for that alone decides `revalidate`, and the release workflow runs the check list `dev.json` declares itself, strictly ([below](#revalidation)) |
| `identity` | optional: the [runner identity](#runner-identity) policy, `manifest` (the vendored manifest's repository path, recorded as an input) and `sha256` (the SHA-256 of its exact bytes). Absent, nothing below about a variant applies |
| `profiles.<name>.platform` | `RUNNER_OS`, `RUNNER_ARCH`, optionally `ImageOS`: what the job's runner must report; under `identity`, `ImageOS` is required |
| `profiles.<name>.variant` | under `identity` only, and required there: the manifest variant (`linux-x64`, `macos-arm64`...) whose OS and architecture are the profile's platform |
| `profiles.<name>.tools` | tool name to the command that prints its identity (`["go", "version"]`); each output is recorded and must not be empty |
| `profiles.<name>.compare` | `release-runner`: the release job resolves the same profile on its own runner, and the evidence must match it exactly (image, version, OS release, every tool); for a leg on the release job's platform. `pins`: the recorded tools must equal `pins` exactly; for a leg the release job cannot resolve itself (another OS or architecture) |
| `profiles.<name>.pins` | tool name to its exact expected output: required for every tool under `pins` (which needs at least one tool), optional under `release-runner`, where it pins a toolchain version on top |
| `workflows.<key>.path`, `.name` | the workflow file under `.github/workflows/` and its `name:` |
| `workflows.<key>.events` | `push`, and `workflow_dispatch` if the fresh route dispatches it |
| `workflows.<key>.skipped_jobs` | optional: display names of jobs that must be present and skipped on the trusted branch |
| `workflows.<key>.pull_request_reuse` | optional: `checks`, the tree-only checks of this workflow a merged pull request's run may cover for a branch job, and optional `environment`, the variables whose values both runs must have had ([pull-request-to-branch reuse](#pull-request-to-branch-reuse)); `events` must hold `push` |
| `workflows.<key>.jobs.<job key>` | one per job or matrix leg: `name` (the display name the API reports, matrix values included), `job_id` (the key under `jobs:`; legs share it), `labels` (its `runs-on`), `profile`, `checks` (dev.json check names, or `"all"`), optional `optional_skips` and `setup` |

The job key names the artifact, so it is letters, digits, `-` and `_`. The template shows a Linux
job compared with the release runner, a macOS matrix leg held to pins, a pull-request-only skipped
job, a pin file and two tag-sensitive checks.

## Prerelease tags and dispatch runs

**The tag grammar.** By default the release tag is `vMAJOR.MINOR.PATCH` in ASCII digits with no
leading zeroes, and nothing before or after it (`tag-syntax` otherwise). With
`"tag": {"prerelease": true}` a SemVer prerelease suffix is admitted as well:
`-<identifier>(.<identifier>)*`, each identifier ASCII letters, digits and hyphens, none empty, a
numeric identifier without leading zeroes (`v0.22.0-alpha.1`, `v1.2.3-rc.1`, `v1.2.3-0`). Nothing
else is: not `v1.2.3-`, `v1.2.3-01`, `v1.2.3-alpha..1`, an underscore or a non-ASCII letter, and
never build metadata (`v1.2.3+build`, `v1.2.3-rc.1+build`). The grammar is the only difference: a
prerelease tag must be annotated, must name the exact release commit, and is read again at the end
like any other (`tag-annotated`, `tag-commit`, `tag-changed`). The release workflow's own tag
admission (its trigger filter and syntax step) must admit the same grammar; the gate does not
widen it.

**What the run decides.** `verify` reads `GITHUB_EVENT_NAME` and `GITHUB_REF`:

- every run but a `workflow_dispatch` one is a **publication** (`mode` `publication`): held to
  `RELEASE_TAG` as above, and its passing decision is `reuse`;
- a `workflow_dispatch` run, under the default `"dispatch": {"validates": "none"}`, does not use the
  gate: it refuses (`dispatch-not-gated`) before any API read;
- under `"dispatch": {"validates": "branch-tip"}`, a `workflow_dispatch` run on the trusted branch
  (`GITHUB_REF` `refs/heads/<branch>`, else `dispatch-ref`) is **validation-only** (`mode`
  `validation-only`). It validates the commit the dispatch ran for, `GITHUB_SHA`, the branch's tip
  when it was dispatched, which the job must check out (`ref: ${{ github.sha }}`; another checkout
  refuses with `checkout-sha`). It reads no tag (the record's `tag` is `null`), holds that commit's
  evidence to every other check of the contract, and its passing decision is `validated`.

`validated` is never a publication decision. The gate decides `reuse` only in mode `publication`,
and a release workflow that has a dispatch trigger conditions every packaging and publishing job on
the `decision` output being `reuse`, as the kit's own release does in its package job (which every
later job needs): the exit status 0 of a validation run is not enough. A validation-only run is a
check of the tip before tagging it; publishing still takes a tag push and its own run.

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
  hosted image since the CI run means fresh evidence is needed, or, where the configuration allows
  it, a fresh run of the check list on the release runner ([revalidation](#revalidation)). Under
  `pins`, the recorded tool output must equal the pin, the platform must match, and `ImageOS` when
  pinned; the image version is recorded but not compared with the release runner (under the
  [runner identity](#runner-identity) policy, the legs of one variant and profile must agree on
  it).
- **Dependency and integration pins.** A pin file in `inputs` (a lock file, a companion version
  file) is bound by the commit. An input fetched at run time without a pin ("latest") is not
  reproducible and cannot be reused: pin it, or keep that check fresh at release.
- **Tag-sensitive checks.** A check whose result depends on the tag (tag history, a policy tag) is
  not reusable from a run before the tag existed: leave it out of every job's `checks`, keep it in
  the release workflow, and name it in `fresh_at_release`.
- **Runners.** Every required job ran on a GitHub-hosted runner (`runner_group_id` 0, group
  "GitHub Actions") with exactly the configured labels.

## Runner identity

A standard GitHub-hosted runner is chosen by a label (`ubuntu-latest`, `ubuntu-24.04`,
`macos-15`), and GitHub moves each label to newer images on its own schedule. A label is an
address, not an identity, and a standard runner cannot be pinned to an image version. Where a
repository configures `identity`, the gate holds every job's evidence to the image identity its
runner **reports**: what the runner says about itself, compared between runners. This is a
reported image identity, **not a pinned VM image**: nothing here chooses, holds or attests the
machine a job runs on, and a recorded version only says which image the runner reported.

**The manifest.** [`templates/runner-identity.json`](../templates/runner-identity.json), version 1,
revision `1`, is the shared policy. An adopting repository vendors it unchanged (as
`.github/runner-identity.json`) and pins it in its configuration:

```json
"identity": {
  "manifest": ".github/runner-identity.json",
  "sha256": "333c3ffe1f5d93a863298133ad15717c384146797c0cc88f2463a361e1e358da"
}
```

The gate reads the manifest from the commit, refuses bytes whose SHA-256 is not the pinned one,
and takes only a revision it ships itself (`IDENTITY_REVISIONS`): a locally edited copy is not the
shared policy (`identity-config`). The manifest is bounded JSON with no repeated member; its
`identity` is `"reported"`, the only kind there is. It names what each job records and the gate
compares, per variant:

| Field | What the runner reports |
| --- | --- |
| `ImageOS`, `ImageVersion` | the runner image name and version, as the runner's environment reports them (`ubuntu24`, `20261026.180.1`); the version must have that form: `latest`, a wildcard or anything else is not a reported version |
| `RUNNER_OS`, `RUNNER_ARCH` | the OS and architecture; they must be the variant's |
| `os_release` | the SHA-256 of the variant's OS-release file: `/etc/os-release` on Linux, `/System/Library/CoreServices/SystemVersion.plist` on macOS; the Windows variant has none, and records none |
| tools | each command of the profile's `tools`, resolved on the runner (at least one under the policy), and each pin as before |
| actions | every `uses:` of the job's workflow file at the commit, local actions and local reusable workflows followed: a local path, a full commit id, or a container image by `sha256` digest; a tag, a branch, an expression or a container tag refuses. So does any line that may spell the `uses` key other than as a plain block-style `uses:` key of its own line: a quoted key (`"uses":`, `'uses':`), a space before the colon (`uses :`), an explicit key (`? uses`), a flow mapping (`{uses: ...}`), and a double-quoted key written with an escape. A line of a `run:` script that contains such text refuses too |

The variants are `linux-x64`, `linux-arm64`, `macos-arm64`, `macos-x64` and `windows-x64`. Each
profile names its variant and pins `ImageOS`; its `RUNNER_OS` and `RUNNER_ARCH` must be the
variant's (`identity-config`).

**What the actions rule does not cover.** It reads the `uses:` of the workflow files and of local
actions and local reusable workflows at the commit, and nothing else. These are admitted unread:

- the `uses:` inside a remote composite action and inside a remote reusable workflow, even when
  the outer reference is pinned to a full commit (their own references may be tags);
- the images of a job's `container:` and `services:` (`node:20`, `postgres:latest`);
- the `image:` of a local Docker action's `action.yml` (`docker://alpine:latest`, or a
  `Dockerfile` whose `FROM` names a tag).

A repository that needs them bound pins them itself, and reviews them as it reviews any input;
the identity record does not stand for them.

**What a job records.** `capture` records the runner fields above in `runtime.runner`, the tools in
`runtime.tools`, and an `identity` member: the manifest path, its SHA-256, the revision, the kind,
the variant and the sorted actions. It refuses a runner whose `ImageOS` is not the profile's
(`runner-platform`), whose `ImageVersion` has another form (`identity-unexpected`), whose
OS-release file cannot be read (`identity-missing`), and a workflow with an unpinned action
(`identity-unexpected`).

**What the release compares.** Identity is compared per variant and profile, never across unlike
OSes or profiles. For each job, before its runtime is compared, the gate refuses:

- `identity-missing`: no `identity` member, one without every field, or a runtime record without a
  field the variant has, or without tools (evidence captured before the policy is such evidence);
- `identity-unexpected`: an `identity` member other than the commit's (another manifest, revision,
  variant or set of actions), an `ImageOS` other than the profile's, another OS or architecture than
  the variant's, an `ImageVersion` not of the reported form, an `os_release` that is not a digest,
  or a runner field the variant does not have.

Neither is a drift: each refuses even where revalidation is allowed. Then:

- a `release-runner` profile's jobs must report exactly what the release runner reports, image
  version and OS-release digest included. Otherwise the identity changed: `runtime-identity`, or,
  where the configuration allows it, the existing fresh route on the release runner
  ([revalidation](#revalidation)), raised after every other check as before;
- a `pins` profile's jobs (a leg the release runner cannot resolve, such as macOS) must have
  reported one identity between them, image version and OS-release digest included:
  `identity-changed` otherwise, which is never revalidated (the release runner cannot run that
  leg).

The release workflow's own `uses:` must be pinned the same way (`identity-unexpected`; read from
`GITHUB_WORKFLOW_REF` at the commit). The decision record's `identity` holds the manifest record,
the statement that it is a reported identity and not a pinned VM image, the release workflow's
actions, and per variant and profile the jobs and the identity they reported.

**When the hosted image rolls.** It rolls often, and this is the case the policy is built for:

1. *Between the CI run and the release* (the common case): the release runner reports a newer
   `ImageVersion` (and maybe other tools or OS-release digest) than the `release-runner` jobs'
   evidence. The identity changed, so the evidence is not reused: the release refuses
   (`runtime-identity`), or decides `revalidate` where the repository allows it and runs its check
   list strictly on the release runner. `pins` legs are not compared with the release runner.
2. *During the CI run*: two jobs of one variant and profile ran on different images. Under
   `release-runner` at least one differs from the release runner: the same as 1. Under `pins`:
   `identity-changed`. The fresh route is to re-run all jobs of the CI run at the commit; no older
   run is searched for, and no version is normalized to another.
3. *The label moves to another OS release* (`ubuntu-latest` from `ubuntu24` to `ubuntu26`):
   capture refuses on the next main run (`runner-platform`), and a release whose runner reports
   the new name refuses (`runner-platform`), with no revalidation. Moving the profile's `ImageOS`
   pin, or the label, is a reviewed configuration change at a new commit with its own CI.
4. *A new manifest revision*: a kit release ships it beside a gate that accepts it. Adopting it is
   re-vendoring both and changing `identity.sha256` in one reviewed change; evidence is per commit,
   so no evidence of the old revision is taken for the new one.

GitHub patches and retires hosted images; the policy freezes none and cannot: it only requires that
the evidence and its consumer report one identity, so a security update costs a fresh run, never a
held image. The route that pins a complete VM image is a GitHub larger runner with a custom image
version, which the [assessment](ci-release-environment-assessment.md) keeps as the direction if the
organization's plan changes; this policy does not claim that guarantee.

## The decision record

`verify` writes one JSON record, whatever the decision, to standard output (the release log) and
to `--output`; the kit's release keeps the file as the run's `release-evidence-<attempt>` artifact.
It holds:

- `decision` (`reuse`, `revalidate`, `validated` or `refuse`), and `refusal` (`code` and a short
  `detail`) or `null`;
- `revalidation`: on a `revalidate` decision, `reason` (each job whose recorded runtime differs
  from the release runner's, and the keys that differ), `differences` (per such job, its workflow
  and job key and, for each differing runner key and tool, the `recorded` value and the
  `release_runner` value) and `jobs` (the job keys whose profile compares with the release
  runner); `null` otherwise;
- `identity`: under the [runner identity](#runner-identity) policy, the manifest record (path,
  digest, revision, kind), the statement that it is a reported identity and not a pinned VM image,
  the release workflow's actions, and per variant and profile the jobs and the identity they
  reported; `null` otherwise;
- `mode` (`publication`, `validation-only`, or `null` when refused before it was known), `event`
  (the run's `GITHUB_EVENT_NAME`), `tag_prerelease`, `dispatch` and `revalidation_allowed` (the
  configured rules);
- `repository`, `repository_id`, `source` (the commit), `tag` (`null` in a validation-only run),
  `tag_object` (a publication only), `branch`, `max_age_hours`, `checked_at`, `fresh_at_release`;
- `inputs`: each recorded path's git object id;
- per workflow: `workflow_id`, `path`, `name`, `events`, the number of runs at the commit and of
  applicable ones, the newest runs at the commit, scanned or not (id, attempt, event, branch,
  status, conclusion, start), the
  selected `run_id`, `attempt`, `event`, `status`, `conclusion`, `run_started_at`, `age_hours`,
  and the reusable workflows the run resolved (`referenced_workflows`, each with its commit);
- per job: display name, job id, result, labels, start and end, the artifact (id, name, digest),
  the recorded runtime and check results, and, under `pull_request_reuse`, `reused` (what the job
  took from its pull request's run, with that run's start, or `null`); and each skipped job's
  conclusion.

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
| missing, unexpected or changed runner identity | `identity-config`, `identity-missing`, `identity-unexpected`, `identity-changed`, `runtime-identity` |
| a check reused from a pull request run, admitted again ([reuse](#pull-request-to-branch-reuse)) | `reuse-event`, `reuse-pull-request`, `reuse-run-missing`, `reuse-unfinished`, `reuse-result`, `reuse-job`, `reuse-artifact`, `reuse-evidence`, `reuse-tree`, `reuse-base`, `reuse-inputs`, `reuse-runtime`, `reuse-environment`, `reuse-coverage`, `reuse-age`, `reuse-race`, `reuse-unavailable`, `reuse-changed` |
| unavailable or stale evidence | `api-unavailable`, `pagination-*`, `artifact-expired`, `artifact-size`, `artifact-interval`, `artifact-digest`, `artifact-entries`, `run-age`, `timestamp`, `response-size`, `unavailable-or-malformed` |
| tag movement | `tag-syntax`, `tag-annotated`, `tag-commit`, `tag-changed` |
| the release run's event | `dispatch-not-gated`, `dispatch-ref`, `mode-unknown` |
| the release checkout or configuration | `source-sha`, `git-unavailable`, `checkout-root`, `checkout-sha`, `checkout-changed`, `config-source`, `config-invalid`, `helper-source`, `input-missing`, `runner-identity`, `runner-platform`, `tool-identity`, `check-config` |

`capture` refuses with `capture-ref`, `capture-event`, `capture-job`, `capture-workflow`,
`capture-run`, `check-infrastructure`, `check-duplicate`, `check-coverage`, `check-result` and the
checkout and runner codes above; under the identity policy also `identity-config`,
`identity-missing` and `identity-unexpected`; with a reuse plan or on a pull request, also
`capture-plan` and `capture-merge`.

## Revalidation

GitHub rolls a hosted image under the same label, so a runner minutes after the CI run can resolve
another `ImageVersion`, and other tool versions with it; under `release-runner` that difference
refuses (`runtime-identity`) though nothing at the commit changed. With
`"revalidation": {"allowed": true}` a publication refused for that alone decides `revalidate`, and
the release workflow runs the repository's check list itself before anything is packaged. The kit's
own release job has this shape:

```yaml
jobs:
  verify:
    # ... the gate step, id: gate, as above
    outputs:
      decision: ${{ steps.gate.outputs.decision }}

  revalidate:
    needs: verify
    if: ${{ needs.verify.outputs.decision == 'revalidate' }}
    runs-on: ubuntu-latest  # the platform of the release-runner profiles
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@<pinned commit>
        with:
          fetch-depth: 0
          persist-credentials: false
          ref: ${{ github.sha }}
      - run: scripts/dev/check.sh --setup --strict
      - run: scripts/dev/check.sh --all --strict
      # No continue-on-error, no shell option or command that hides a failed step.

  package:
    needs: [verify, revalidate]
    # revalidate is skipped on reuse: this job, and every later job, states its condition.
    if: ${{ !cancelled() && needs.verify.result == 'success' && (needs.revalidate.result == 'success' || needs.revalidate.result == 'skipped') }}
    steps:
      - env:
          DECISION: ${{ needs.verify.outputs.decision }}
          REVALIDATED: ${{ needs.revalidate.result }}
        run: |
          case "${DECISION}/${REVALIDATED}" in
            reuse/skipped | revalidate/success) ;;
            *) echo "no publication decision: ${DECISION}/${REVALIDATED}" >&2; exit 1 ;;
          esac
  # A later publishing job: if: ${{ !cancelled() && needs.package.result == 'success' }}
```

**The bound.** The route admits one thing: a publication whose every other check of the contract
has passed, in order (repository, branch, tag, workflow, selection, the run's result, age, jobs,
artifacts, inputs, coverage, the attempt and selection read again, every workflow's final
selection and the tag read at the end), and whose evidence differs only in a `release-runner`
profile's recorded runner image or tool identity from what the release runner resolves; the
runtime identity is each job's last check, and that difference is raised after the final reads,
so any other refusal wins. It never admits a pin that does not match (under `pins`, or a
`release-runner` profile's own pin, in the evidence or on the release runner), a runtime record of
another shape or platform, another refusal code, or a validation-only dispatch run (each refuses
as before), and it is off unless the configuration says `true`. The decision artifact records the
drift: `revalidation.reason` names each job and the keys that differ, `revalidation.differences`
holds each of those keys' recorded value and the release runner's, `revalidation.jobs` lists the
jobs whose evidence is bound to the release runner, and `refusal` is `null`. The evidence of those
jobs is not taken. The fresh run is the check list `dev.json` declares, its setup steps and every
check, run strictly (`scripts/dev/check.sh --setup --strict`, then `--all --strict`: a step
skipped for an empty `requires_env` fails, `optional: true` or not), on a release runner, and a
publishing job proceeds only on that run's success. Work a CI job does outside the check list (a
step of its own, a matrix leg whose `checks` are empty) is not covered by the fresh run: a
repository whose evidence jobs do such work either runs it in the release workflow and names it in
`fresh_at_release`, or does not opt in. A `pins` leg (another OS or architecture) is not run
again; its evidence has passed every check, its pins included.

## Pull-request-to-branch reuse

A pull request's CI runs a check at its merge commit; after the merge, the push to the branch runs
it again on the same tree. Where a workflow configures `pull_request_reuse`, a branch job may take
a check from the merged pull request's newest run instead. This is opt-in per workflow and per
check, and **tree equality alone never qualifies a result**. Without the member nothing here
applies, nothing of a pull request is read, and the exact-commit main-to-release reuse above is
unchanged.

```json
"pull_request_reuse": {
  "checks": ["diff-check", "json", "unit"],
  "environment": ["GOFLAGS"]
}
```

**What may be reused.** Only the checks `checks` lists, and of those only the ones the pull
request's job ran and passed (`PASS`). A check its scoped selection (`check.sh --changed`) did not
run, a permitted `SKIP`, a `FAIL` or a `NOT RUN` covers nothing, and the branch job runs it. List
only checks whose result depends on the tree and the recorded inputs. A check that reads the
commit, its history, a ref or a tag (embedded version metadata, signatures, tag history, branch
protection), creates or publishes an artifact, or reads mutable external state (an advisory
database, a live service) is never listed: it runs on the branch, and a tag-sensitive one at the
release, as before.

**The inputs bound.** The branch job's commit (M) must be the merge of exactly one pull request,
and each of these must hold, or nothing is reused:

| Input | Bound by |
| --- | --- |
| the trusted relationship | records that survive the merge and that the pull request's code cannot write, read through the API: one pull request of this repository (not a fork, base repository this one) merged into the trusted branch with M as its merge commit; its head branch's listing (`pulls?head=owner:branch&state=all`, every page to an empty one, ten at most) shows exactly that one pull request ever, from this repository; its timeline (every page) has no base-change event of any kind (`base_ref_changed`, `automatic_base_change_succeeded`, `automatic_base_change_failed`, and any event whose name contains `base_change` or `base_ref`); the newest `pull_request` run of the same workflow is at its final head, from this repository, on its head branch, and was created after the pull request was opened. The run's own `pull_requests`, which GitHub clears once a pull request merges, must name exactly that pull request into the trusted branch when it is not empty. Anything of this that cannot be read refuses (`reuse-pull-request`) |
| exact source and tree | the merge commit the pull request job checked out (S), read through the API: its parents are M's first parent and the pull request's head, and its tree is M's tree |
| the base relationship | S was made on M's first parent: a change set tested on another base is not M's, even with the same tree (a rebase merge of several commits therefore never qualifies) |
| workflow, configuration and dependency digests | the pull request job's input identities (the manifest, the configuration, the gate, the workflow files, every pin file) equal M's |
| tools, image and OS | the pull request job's runtime record (image name and version, OS, architecture, OS-release digest, every tool) equals the branch job's, and under the [runner identity](#runner-identity) policy its identity record is the commit's |
| flags and environment | the `environment:` line `check.sh` prints in the checks step's own log when `JPDEV_BIND_ENV` names the configured variables: the SHA-256 of the manifest it read, which must be the committed `dev.json` (so `--manifest` cannot point elsewhere), and of each variable's value (`null` when unset) as the checks ran, step-level and event-selected values included (a `-short` set only on pull requests differs, and refuses `reuse-environment`). Only variables the configuration lists are bound: a flag a check reads from any other variable, or a check that branches on the event itself, is not tree-only and must not be listed in `checks`. Only `PASS` rows are reused, so `check.sh`'s own skip options change nothing that is reused |
| the selected matrix coverage | the same job key and display name, labels and hosted runner; a leg only covers its own checks, and the job's other checks run on the branch |

**Fail closed.** The decision is `fresh`, and the branch job runs its whole list, on any of these:
the workflow does not opt in (`reuse-off`); a dispatch or a re-run attempt (`reuse-event`, below);
no single merged pull request of this repository (`reuse-pull-request`); no `pull_request` run at
its head (`reuse-run-missing`); a run still going (`reuse-unfinished`); a newest attempt or job
that failed, was cancelled or skipped (`reuse-result`); no single such job (`reuse-job`) or
artifact (`reuse-artifact`); evidence of another shape, run, job, event or merge ref, or a merge
commit the API does not confirm (`reuse-evidence`); another tree (`reuse-tree`) or base
(`reuse-base`); other inputs (`reuse-inputs`), runtime or identity (`reuse-runtime`) or
environment (`reuse-environment`); nothing reusable passed, or a scoped record with a failed or
unexpected check (`reuse-coverage`); a run older than `max_age_hours` or in the future
(`reuse-age`); a run that changed while it was read (`reuse-race`); an API error, an expired,
oversized or malformed artifact (`reuse-unavailable`). The newest attempt is selected whatever its
result, with every page read: a newer failed or cancelled attempt is never searched past for an
older green one.

**The commands.** A pull request job records its evidence with `capture`, as a branch job does: on
a `pull_request` event of a workflow that opts in, into the trusted branch (`GITHUB_BASE_REF`), at
`refs/pull/<number>/merge`, the checkout being that merge commit with both parents (`fetch-depth`
2 or more). Its record holds only the checks its selection ran (`PASS` or a permitted `SKIP`), the
pull request number, the merge commit's base, head and tree, and the environment digests from the
log's `environment:` line. It refuses with `capture-ref`, `capture-workflow`, `capture-merge` (no
merge commit with two parents), `check-result` (a `FAIL` or `NOT RUN` row), `check-coverage` (a
check the job does not run) and `check-environment` (a log without exactly one `environment:`
line, logs that differ, another manifest, or another set of variables); it is never evidence for a
release by itself. A capture on a `pull_request` event of a workflow that does not opt in refuses
`capture-event`; before this change the same capture refused `capture-ref`, as one on any other
ref still does. Either way it records nothing.

A branch job plans before its checks:

```sh
python3 scripts/dev/release_evidence.py reuse --workflow KEY --job KEY [--output reuse-plan.json]
```

It writes the plan (`decision` `reuse` or `fresh`, the `refusal` of a fresh one, the `covered`
checks and the `reused` provenance: pull request, head, merge commit, base, tree, run, attempt, job
id and artifact id, name and digest) to standard output and the file, and the step outputs
`decision` and `covered` (a comma-separated list, empty when fresh). It exits 0 on either decision:
a fresh decision is the route, not a failure. The job then skips the covered checks and runs the
rest, and records with `capture ... --reuse-plan reuse-plan.json`: each covered check is `REUSED`
in its coverage, beside its `environment` (from its own checks log, as above) and `reused` record.
A covered check that also ran, or a plan of another commit, workflow, job or attempt, refuses
(`check-coverage`, `capture-plan`). The plan compares the pull request's checks environment with
its own step's, a first filter; the release compares it with the branch job's checks environment.

```yaml
      - name: Plan reuse from the merged pull request
        id: plan
        if: github.event_name != 'pull_request'
        run: python3 scripts/dev/release_evidence.py reuse --workflow ci --job check --output "${{ runner.temp }}/reuse-plan.json"
      - name: The checks
        env:
          COVERED: ${{ steps.plan.outputs.covered }}
          # The variables pull_request_reuse.environment names, comma-separated: check.sh prints
          # their digests, and the manifest's, in its summary block.
          JPDEV_BIND_ENV: GOFLAGS
        run: |
          set -o pipefail
          skip=()
          if [ -n "$COVERED" ]; then skip=(--skip "$COVERED"); fi
          scripts/dev/check.sh --all "${skip[@]}" | tee "${{ runner.temp }}/checks.log"
      - name: Record exact CI inputs and coverage
        if: github.ref == 'refs/heads/main' && github.event_name != 'pull_request'
        run: >-
          python3 scripts/dev/release_evidence.py capture --workflow ci --job check
          --check-log "${{ runner.temp }}/checks.log" --reuse-plan "${{ runner.temp }}/reuse-plan.json"
          --output "${{ runner.temp }}/evidence.json"
```

The plan step runs on every branch event: on a dispatch it decides `fresh` and still writes the
plan the capture step reads. A job with skips of its own adds the covered checks to its `--skip`
list. The pull request job adds the same capture step without `--reuse-plan`, under
`if: github.event_name == 'pull_request'`, and uploads `ci-evidence-<workflow key>-<job key>-<attempt>`
as the branch job does. Its job needs no write permission. The branch job's reuse step and the
release read the API with `contents: read`, `actions: read` and `pull-requests: read`.

**At the release.** A branch job's evidence that reused a check is taken only if that pull request
evidence is admitted again, now, under every rule above: the same pull request, run, attempt, job
and artifact digest (`reuse-changed` otherwise: a newer attempt, even a green one, is not the one
reused), still the newest attempt, still within `max_age_hours` of the release, still covering each
`REUSED` check, with the branch job's own recorded runtime and environment. Only the first attempt
of a `push` run may carry a reuse (`reuse-event`). A reused check the configuration does not list,
a `REUSED` row the job did not record as reused, or a missing `reused` member refuses
(`reuse-coverage`, `check-result`, `evidence-identity`). These refusals come before the runtime
comparison: none of them is a drift, and none is revalidated.

**The bounded fresh route.** A dispatch on the branch and a re-run of a branch run never reuse:
their plan is `fresh` (`reuse-event`) and the job runs its whole list. So a release refused for
reuse takes the existing [fresh route](#the-fresh-route): re-run all jobs of the branch run at the
commit, or dispatch the CI workflow on the branch, then re-run the release's failed jobs. No route
searches for an older run of either the pull request or the branch.

**Trust.** A `pull_request` run executes the workflow file and the code at its own pull request's
merge commit, and its artifact is that code's report. The gate binds the run through records the
pull request's code cannot write and that survive the merge: the API's pull request merged as M;
the head branch's pull requests, which must be that one only, ever, so no other pull request (and
so no other base's workflow file) can have produced a run at that head; that pull request's
timeline, which must hold no base change of any kind, manual or automatic, so its base was the
trusted branch for its whole life; and the run's head, repository, event and creation time (after
the pull request was opened). Together they leave the merged pull request, on the trusted base, as
the only one the run can belong to. GitHub clears a run's `pull_requests` once its pull request
merges, so an empty association is not a refusal; a non-empty one must name exactly that pull
request into the trusted branch. Then the run's branch, workflow, attempt, jobs, results, runner
and artifact digest, and the reported merge commit's parents and tree, are read through the API. A
run of another pull request on the same head branch, or one made while the base was another
branch, therefore refuses. What
remains the job's own report is everything inside the artifact: which merge commit it checked out,
its input identities, runtime, identity record, environment line and check results. Through the
merged pull request's own run, that report is written by the merged pull request's own reviewed
code on the tree M has, the same trust the branch's own run gets; nothing above makes it more. A
fork's pull request is never reused. Nothing of a pull request run is executed, and no credential
reaches it.

**Savings.** The kit's own workflows do not adopt this, and no timing was measured: this section
claims no saving. A repository that adopts it records the executed checks and their timings before
and after, on its own runs.

## The fresh route

A refusal stops that release run. The operator reads the refusal and chooses; no workflow
dispatches or re-runs anything automatically, and no automatic CI is turned off.

1. Make fresh evidence at the same commit, once:
   - re-run **all** jobs of the main CI run at the commit
     (`gh run rerun <run id> --repo <owner/name>`; a failed-jobs-only re-run leaves the other jobs'
     evidence in an earlier attempt and refuses). This also works after main moved on, and is the
     route for `run-age` and a changed hosted image (`runtime-identity`), which a repository that
     allows [revalidation](#revalidation) does not need for the image alone;
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
| toolchain | ubuntu-latest image, its bash, git, python3, go, shellcheck, rsync | the same image family, not compared | compared with the release runner (`release-runner`); a difference alone is revalidated: every check runs strictly on a release runner |
| tag, notes, environment reviewer, version and copies, package run, checksums, attestation, draft and published identity | not run | run | run (unchanged) |

The kit's tags stay `vMAJOR.MINOR.PATCH` (no `tag` member) and its release workflow has no
dispatch trigger (no `dispatch` member). It allows revalidation: on a `revalidate` decision its
`Check list on the release runner` job runs `scripts/dev/check.sh --setup --strict` and
`scripts/dev/check.sh --all --strict` at the commit (the kit's `dev.json` has no setup steps and no
`requires_env` step, and its two CI jobs run nothing outside the list). Its package job begins by
requiring the gate's `decision` output to be `reuse`, or `revalidate` with that job's success.

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
