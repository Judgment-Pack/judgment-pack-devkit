# Releasing the kit

Only maintainers release this repository. A release is a tag a person pushes on a commit already on
`main`. [`release.yml`](../.github/workflows/release.yml) packages the kit from that commit and
publishes no release until a maintainer approves it.

There is no registry and no Go module. A person installs the attested tarball (see the README).

## What a release is

- `judgment-pack-devkit-<version>.tgz`: `bin/`, `lib/`, `templates/`, `config/`, `scripts/`, `docs/`, `examples/`,
  `README.md`, `LICENSE` and `NOTICE` of the tagged commit, in one directory named
  `judgment-pack-devkit-<version>/`, where `<version>` is the tag without its `v`. The tarball is
  written with `git archive` and `gzip -n`, so the same commit gives the same bytes.
- `checksums.txt`: the SHA-256 of the tarball, in the form `sha256sum` writes.
- A build-provenance attestation whose subjects are both files, each by its own digest, signed by
  GitHub for this workflow at the tagged commit.
- The notes a person wrote, from `docs/releases/<tag>.md`.

## Once, before the first release the workflow makes

Both are done by a maintainer. The workflow reads the first one's reviewer rule and does not read
the second.

1. The `release` environment exists with a required reviewer. The workflow reads the rule before it
   writes anything and refuses a repository without it, because GitHub creates a missing
   environment on first use with no protection. It reads that a reviewer rule exists, not who the
   reviewers are, and it cannot stop an administrator from changing the rule later. With one
   maintainer, the person who pushed the tag is the person who approves: the gate is a pause to read
   the draft, not a second person.

   ```sh
   gh api -X PUT repos/Judgment-Pack/judgment-pack-devkit/environments/release \
     -F 'reviewers[][type]=User' -F "reviewers[][id]=$(gh api user --jq .id)"
   ```

2. **Immutable releases are turned on by the maintainer** in the repository settings (Settings,
   General, Releases). It locks the tag and the assets once a release is published, not before.
   Until it is on, the workflow compares the tag with the commit the run was started for, and a
   published release can still be changed.

## Prepare the release

1. Open a pull request that:
   - sets `JPDEV_VERSION` in `lib/common.sh` to the release's version, and line 2 of
     `templates/check.sh` to `# from judgment-pack-devkit v<version> (templates/check.sh)`, and
     copies the template to `scripts/dev/check.sh`; sets line 2 of
     `scripts/dev/handover_check.sh` to
     `# from judgment-pack-devkit v<version> (lib/handover_check.sh)` and copies the rest from
     `lib/handover_check.sh`; sets line 2 of `scripts/dev/changed_checks.py` to
     `# from judgment-pack-devkit v<version> (lib/changed_checks.py)`, the other lines being those
     of `lib/changed_checks.py`; sets line 2 of `scripts/dev/release_evidence.py` to
     `# from judgment-pack-devkit v<version> (lib/release_evidence.py)`, the other lines being those
     of `lib/release_evidence.py` (tests hold the vendored scripts to their sources and version);
   - writes `docs/releases/<tag>.md`: what the release holds and what it does not. It is the text
     the release page carries, and the first line ends with the tag's name, for example
     `# jpdev v0.2.0`.
2. Run the check list once locally, as `ci.yml` does:

   ```sh
   scripts/dev/check.sh
   ```

3. Merge the pull request, and let main CI at the merge commit complete: its run is the evidence
   the release takes.

## Tag

Tag the merge commit on `main`, signed, and push only that tag:

```sh
git fetch origin
git tag -s <tag> -m "jpdev <tag>" "$(git rev-parse origin/main)"
git push origin <tag>
```

If no signing key is configured, stop and settle the signing policy. Do not replace a signed tag
with an unsigned one. Signing is the maintainer's practice; the workflow does not check it.

The tag must be annotated (`-s` makes it so): the workflow refuses a lightweight tag, reading the
tag's object type. A tag is `vMAJOR.MINOR.PATCH`, in ASCII digits with no leading zeroes, and
nothing after: no prerelease and no build metadata. A tag is never moved or reused. A fix is a new
release.

## What the workflow does

Every job works on the commit the run was started for, by its digest, not on the tag's name.

1. **Admits the tag.** It is in the grammar; it is an annotated tag; it names the commit the run
   was started for; that commit is on `main`; `docs/releases/<tag>.md` exists, is not empty and ends
   its first line with the tag; and the `release` environment has a reviewer rule.
2. **Takes the CI evidence main produced at that commit, or refuses** (`CI evidence at the tag`).
   `scripts/dev/release_evidence.py verify`, the [release evidence gate](ci-evidence.md), reads
   the Actions API for the `CI` runs at the exact commit: the newest applicable attempt (a push to
   main, or a dispatch on main) must be complete and successful, at most 48 hours old, with `lint`
   and `tests` successful on hosted `ubuntu-latest`, their evidence artifacts recording every
   check passed, the commit's input identities and the image and tools this job's runner resolves.
   A newer failed, cancelled or running attempt is never searched past, and the tag must name the
   commit before and after. The decision record, reuse or refusal, is in the log and kept as the
   run's `release-evidence-<attempt>` artifact. `ci.yml` is not run again; a refusal stops the
   release, and the [fresh route](ci-evidence.md#the-fresh-route) is the operator's choice. When the
   hosted image or its tools are all that differ from the evidence's, the gate decides `revalidate`
   instead, and the `Check list on the release runner` job runs every check of `dev.json` at the
   commit before anything is packaged ([revalidation](ci-evidence.md#revalidation)). Main CI
   and pull request CI keep every check and required status.
3. **Packages the kit.** It refuses unless `bin/jpdev --version` prints `jpdev <version>`, line 2 of
   each vendored script names `<tag>`, and each matches its source. Then
   `git archive` of the commit into `judgment-pack-devkit-<version>.tgz`, `checksums.txt` written
   over it and checked, and the unpacked tarball run once (`jpdev --version`, `jpdev env`).
4. **Attests and drafts.** Only if the tag still names the commit and no release exists under the
   tag, both files are attested, each by its own path, and a draft release is created with the
   notes from the commit. The job records the draft's release id for the publish job.
5. **Waits at the `release` gate.** Review the draft on the Releases page: the notes and the two
   assets. Approve the pending deployment on the run.
6. **Compares the draft with the run, and publishes it by its id.** A draft can be changed while it
   waits, by anyone who can write to the repository. After the gate, the tag is compared with the
   commit once more, and the run's own files are held to their checksums. The release the run
   drafted is then read through the releases API by its id, without downloading anything: it must
   still be a draft under the tag, with the title the workflow gave it and the notes the commit
   holds, and the digest the API reports for each of its assets must be the digest of the run's
   file of that name, no asset more or fewer. Any difference refuses. The publish call follows that
   last read at once, addressed to the same release id, not to the tag, and marks the release
   latest.
7. **Reads the published release again.** Immediately after publication the job reads the
   published release's asset digests through the API once more, and fails the step `Require the
   published release to hold what this run wrote`, printing both digest sets, if they differ from
   the run's files. A read that fails is a separate failure, "could not verify the published
   release", and also fails the step.

An approval given more than thirty days after the run finds the run's files gone, and the job
fails: release a new version.

### The window that remains

The API cannot publish a release on condition that its assets are the ones just read, so one
window remains: between the last read of the draft's asset digests and the publish call, a few
moments of the same step. Whoever can write to the repository's releases can act in it, which in
this organisation is a maintainer, the same people the `release` gate asks to approve. Nothing in
the workflow closes that window. A file replaced in it is published, and the read after publication
then fails the run by name; with release immutability on, the published release can no longer be
changed, so the replacement stays visible as a failed release and is not quietly corrected.

No maintainer token and no repository secret is used.

### What exists before the approval

The gate is on the release. Three things exist before it and are not secret:

- the files, as an artifact of the workflow run, downloadable for thirty days by anyone who can read
  the repository's runs;
- the attestation of the tarball and `checksums.txt`, recorded in a public transparency log when it
  is made. It says which workflow built the files, from which commit. It does not say a maintainer
  approved them;
- the draft, visible to those who can write to the repository.

### If a run fails

Fix the cause on `main` and release a new version. Re-running is for a failure that was the hosted
runner's: re-run the failed jobs, not all jobs.

What to do with a draft depends on which job failed:

| The job that failed | The draft | What to do |
| --- | --- | --- |
| `CI evidence at the tag` | none was made | read the refusal (the step's last line, or the `release-evidence-<attempt>` artifact). Take the [fresh route](ci-evidence.md#the-fresh-route) once: re-run all jobs of the main CI run at the commit (or dispatch `ci.yml` on main while main names it), then re-run the failed jobs. A second refusal: fix the cause on `main` and release a new version |
| Any other job before `Attest and draft release` | none was made | re-run the failed jobs; where the version did not match the tag, fix it on `main` and release a new version |
| `Attest and draft release` | may exist, and may lack assets | read it, delete it by hand, then re-run the failed jobs. The job refuses to run while a release under the tag exists, draft or published, and refuses when it cannot find out |
| `Publish release`, before publication | needs looking at: it may be as it was made, changed, incomplete or gone | read why the job failed, and look at the Releases page. **Keep** a draft that is as it was made, and re-run the failed jobs: that job only publishes the release id the run drafted. Do not publish a draft that was changed or is incomplete. Where the draft cannot be published, release a new version |
| `Publish release`, at `Require the published release to hold what this run wrote` | published, holding files this run did not write, or not published after the call | someone who can write to the repository changed the release in the window above. Treat it as an incident: tell the maintainers, point no one at the release, and release a new version from a new tag. Do not re-run |

Delete a draft with `gh release delete <tag> --repo Judgment-Pack/judgment-pack-devkit`, which
leaves the tag. A published release is never deleted to make room for another.

## Verifying a release by hand

Both files are attestation subjects, and `checksums.txt` also names the tarball's digest. With the
release's files downloaded into a directory of their own:

```sh
git clone https://github.com/Judgment-Pack/judgment-pack-devkit.git devkit
commit="$(git -C devkit rev-parse '<tag>^{commit}')"
gh release download <tag> --repo Judgment-Pack/judgment-pack-devkit --dir release-<tag>
cd release-<tag>
for file in judgment-pack-devkit-<version>.tgz checksums.txt; do
  gh attestation verify "${file}" \
    --repo Judgment-Pack/judgment-pack-devkit \
    --signer-workflow Judgment-Pack/judgment-pack-devkit/.github/workflows/release.yml \
    --source-ref refs/tags/<tag> \
    --source-digest "${commit}" \
    --format json
done
sha256sum --check --strict checksums.txt
```

The loop checks each file against the attestation made in this repository, by this workflow, in a
run started for that tag, from that commit; with `--repo` alone it would check the repository and
nothing more. The checksum command checks the tarball against `checksums.txt`, itself an attested
file. `--format json` is for scripts: `gh attestation verify` prints nothing when its output is not
a terminal. On macOS use `shasum -a 256 --check checksums.txt`.

To check that the tarball is what the tagged source packages, build it from the tag and compare.
The packing is reproducible, so the digests are equal:

```sh
git -C devkit archive --format=tar --prefix=judgment-pack-devkit-<version>/ '<tag>^{commit}' \
  bin lib templates config scripts docs examples README.md LICENSE NOTICE | gzip -n -9 > rebuilt.tgz
sha256sum rebuilt.tgz judgment-pack-devkit-<version>.tgz
```

Neither check says a maintainer approved the release, which its being published says.
