# Assessment: version-pinned CI and release environments

Status: proposed infrastructure decision; documentation only. Tracks [#59](https://github.com/Judgment-Pack/judgment-pack-devkit/issues/59).

This assessment selects a conditional direction for Linux and Windows: GitHub-hosted
larger runners configured with a specific custom-image version, with a separate
variant per OS and architecture. It does not provision runners, build images,
change a verifier, adopt the kit in another repository, or change a release version.
The organization cannot currently use that direction: the read-only assessment
reported a Free plan and the hosted-runner endpoint returned unsupported (404).
Runner-group inspection returned 403 for the available identity. Existing group
membership, custom-image policy, budgets and administrator permissions are therefore
unverified, not absent. An organization administrator owns entitlement and access;
the judgment-pack-devkit maintainer owns the common contract and promotion proposal;
each repository's release maintainer owns adoption and release decisions.

The scope is the 2026-10-29 work lane. The source inventory below records immutable
commits collected during the assessment. No release is authorized by this document.

## Evidence inventory

Each repository link names the inspected commit. Workflow names below are relative
to `.github/workflows/`; the evidence configuration and verifier at that same commit
are the source of the identity comparisons. Required job names must remain stable,
or their protection and evidence configurations must change together in adoption.

| Repository and inspected commit | Producers, consumers and platforms | Existing evidence admission |
| --- | --- | --- |
| [judgment-pack-agent `eba2ad6051c4`](https://github.com/Judgment-Pack/judgment-pack-agent/tree/eba2ad6051c482e07e0b677545c5cb356a70549c) | `ci.yml`: contract, check; `mutation.yml`: rows-apply and four full shards; `release.yml`: verify, package. Linux x64. | `scripts/dev/ci_evidence.py`, schema 1. Every admitted job compares image, OS, architecture, OS-release digest and profile tools with the release verifier. The v0.11.0-only two-image exception expires 2026-11-07T00:00:00Z; it is not a migration policy. |
| [judgment-pack-runtime `57c854abb9ac`](https://github.com/Judgment-Pack/judgment-pack-runtime/tree/57c854abb9ace8a91013a75ab688bd70d063797c) | `ci.yml`: Linux stable and Go 1.24 compatibility, macOS stable, Windows stable; Linux check. `release.yml`: Linux packaging, native Linux x64/arm64, macOS arm64 and Windows x64 smoke; Linux image publication/smoke. | No `.github/ci-evidence.json` or shared evidence verifier at this commit. Release runs vet, tests, bundled conformance and `tools/check-release` afresh; introducing reuse is a separate adoption decision. |
| [judgment-pack-runner `85cbcfc83e58`](https://github.com/Judgment-Pack/judgment-pack-runner/tree/85cbcfc83e589904fa165e908f6fd0e08f71fe9c) | `ci.yml`: Runner Linux x64 and macOS arm64, Release contents Linux x64. `release.yml`: verify/package and native Linux x64/arm64, macOS arm64 smoke. | `scripts/dev/release_evidence.py`, schema 2. Both Linux producers compare against the release runner. macOS uses platform/family and Go pins; its recorded ImageVersion is not an exact-image equality gate. |
| [judgment-pack-gateway `167ff6d6284d`](https://github.com/Judgment-Pack/judgment-pack-gateway/tree/167ff6d6284d24f9ad0922de2ff8820211e5b359) | `ci.yml`: check Linux x64; go Linux x64, macOS arm64, Windows x64. `release.yml`: verify/package and native Linux x64/arm64, macOS arm64, Windows x64 smoke. | `scripts/dev/release_evidence.py`, schema 2. Linux check and go profiles compare against the release runner; macOS and Windows compare platform/tool pins. Preserve the difference between pinned tools and a complete machine identity. |
| [judgment-pack-spec `6b67106bf833`](https://github.com/Judgment-Pack/judgment-pack-spec/tree/6b67106bf833992daa86ad1fb00e35e60f469965) | `conformance.yml`: repository-conformance Linux x64. `release.yml`: evidence and release. `deploy.yml`: published-site deployment, separate from reusable conformance. | `scripts/dev/release_evidence.py`, schema 2. Linux conformance compares against the release evidence job, including resolved Python packages and format support. Non-final tags retain their fresh-suite route. |
| [judgment-pack-desk `605630a535a2`](https://github.com/Judgment-Pack/judgment-pack-desk/tree/605630a535a25292a40926ba72e269de03b951e7) | `ci.yml`: Linux Go/web/integration jobs; development bundles Linux x64, macOS arm64 and Intel; local-gateway Linux/macOS. `release-build.yml`: archive Linux x64, macOS arm64 and x64. `release.yml` calls CI and archive workflows. | No shared `.github/ci-evidence.json` or shared evidence verifier at this commit. Release reruns compatibility and archive checks. Mutable action tags and broad tool versions remain adoption work; do not claim an exact-image gate already exists. |
| [judgment-pack-exchange `4fc303651498`](https://github.com/Judgment-Pack/judgment-pack-exchange/tree/4fc303651498a9a01810c2fcccfe484d4b0f78bd) | `ci.yml`: entries Linux x64. `release.yml`: evidence, fresh entries verification, package. | `scripts/dev/release_evidence.py`, schema 2. Tree-only checks compare with the release evidence runner; tag/history-sensitive entry checks run again at the tag and cannot be replaced by main evidence. |

The judgment-pack-devkit baseline is
[`d362e3f45b6f481ff3f5bd948c18184201b66e77`](https://github.com/Judgment-Pack/judgment-pack-devkit/tree/d362e3f45b6f481ff3f5bd948c18184201b66e77):
Linux lint/tests produce schema-2 evidence; release can explicitly revalidate after
an image-only mismatch. That opt-in fresh route is not silent evidence reuse.
The common verifier is `lib/release_evidence.py`; adoption does not replace the
specialized judgment-pack-agent verifier without its own reviewed compatibility work.

Identity equality is per environment variant and profile, not across unlike OSes.
For an adopted exact-image profile, all its reusable CI producers and release
consumers must name the same approved manifest digest, VM image version, platform
and resolved toolchain. In particular, judgment-pack-agent contract/check/mutation
and release verification must agree; judgment-pack-runner Linux check/Release
contents and release verification must agree; judgment-pack-gateway Linux check/go
and release verification must agree. The judgment-pack-spec conformance/evidence
pair, judgment-pack-exchange tree-check/evidence pair and judgment-pack-devkit
lint/tests/release pair each require the same within-repository agreement.
Packaging jobs must also use their declared variant, even when they do not consume
cached checks. Native smoke jobs keep their native architecture. A Linux result
cannot replace a macOS, Windows or arm64 result.

Maintenance workflows (branch updates, acknowledgments and freshness reports),
optional dependency audits and manual smoke runs are not reusable release evidence
merely because they use the same label. judgment-pack-desk mutation jobs likewise
remain outside its current release gate. Changing evidence coverage needs an
explicit adoption change; this document does not expand or reduce it.

## Infrastructure choice and feasibility

GitHub documents custom images for Linux x64/arm64 and Windows x64, with Team or
Enterprise Cloud entitlement and custom-image/runner administration permissions.
A consuming runner can select a specific image version; selecting Latest remains
mutable. Its disk must accommodate the image. Image generation belongs in a
dedicated, restricted runner group. These are prerequisites for the proposed
choice, not verified organization capabilities.
[GitHub custom-image documentation](https://docs.github.com/en/actions/how-tos/manage-runners/larger-runners/use-custom-images)

An OS label, container digest or repository-generated version file cannot alone
identify the complete VM. The proposal pins the provider image ID/version and
binds the job's actual runner to that configuration through trusted provider
metadata. The adoption prototype must demonstrate that association and detect
runner reconfiguration between capture and admission. A label that an administrator
can repoint is an address, not an immutable identity. If the provider cannot supply
sufficient independent evidence, exact-image reuse stays disabled for that variant.
Do not invent a purported provider attestation from an environment variable.

| Option | Assessment and decision |
| --- | --- |
| GitHub larger runners with explicit custom versions | Proposed Linux/Windows route after entitlement, permission, identity and budget checks. Start with an isolated pilot; no billing or infrastructure change in this PR. |
| Standard hosted OS labels | Retain existing workflows until adoption; rolling images can legitimately refuse reuse. Do not call the label a complete-image pin. |
| Container-only jobs | Useful for dependencies but do not bind the host kernel, VM or runtime. Not a substitute for the requested machine identity. |
| Self-hosted disposable VMs | A possible separately reviewed alternative if hosted entitlement or identity cannot meet requirements. Requires patching, isolation, destruction and capacity ownership; not an implicit fallback. |
| macOS custom images | GitHub's documented custom-image feature is limited to Linux/Windows. Preserve native macOS arm64/x64 checks and existing fresh or explicitly pinned-profile semantics. Exact-image reuse for macOS remains unimplemented until a reviewed provider/ephemeral-VM design proves its guarantee. |

The macOS limitation follows the documented platform capabilities, not an inference
that macOS CI may be dropped.
[GitHub larger-runner capabilities](https://docs.github.com/en/actions/concepts/runners/larger-runners)
Windows arm64 is not in the selected custom-image platform set; do not add support
by relabeling an x64 runner. Existing matrices remain the minimum required coverage.

Proposed pilot sizing: Linux x64 four cores for general checks, an eight-core
candidate for measured heavy integration/image work, Linux arm64 four cores for
native smoke, and Windows x64 four cores. These are starting hypotheses, not
capacity measurements. Before choosing a SKU, record peak memory/disk, wall time,
queue time and concurrency for representative main jobs; build the image on storage
that every intended consuming size can support. Cap pilot concurrency at one per
variant, then budget against measured demand. Keep runtime and compatibility-floor
toolchains as separate exact tool profiles, including judgment-pack-runtime's
Go 1.24 compatibility coverage.

At the referenced published rates, Linux x64 four/eight cores cost $0.012/$0.022
per minute, Linux arm64 four cores $0.008, and Windows x64 four cores $0.022.
For an illustrative 1,000 rounded job-minutes in each of those four sizes, compute
is $64. This is arithmetic, not a usage forecast. Include image-generation minutes,
reruns, storage and any plan upgrade separately; obtain a billing-owner cap before
provisioning. Prices must be rechecked when selecting infrastructure.
[GitHub runner pricing](https://docs.github.com/en/billing/reference/actions-runner-pricing)

## Proposed shared manifest, version 1

This is a design for a future schema, not a currently accepted configuration file.
A reviewed judgment-pack-devkit release would carry one versioned manifest and
schema. Each adopting repository pins their exact bytes and records that digest
among verifier inputs; no consumer tracks a branch or a mutable latest version.
No manifest file or vendored library changes in this assessment PR.

| Field | Required meaning and refusal |
| --- | --- |
| `manifestVersion` | Literal `1`; unknown versions refuse. |
| `revision` | Immutable policy revision, distinct from a provider image version. A changed mapping creates a new revision/digest. |
| `ownerRole`, `approvalRecord` | Accountable infrastructure role and permanent promotion/review record. Neither a personal credential nor a source of execution authority. |
| `variants` | Closed map of explicit OS/architecture variants. Missing required variants refuse; no fallback to another architecture. |
| `variants.*.provider`, `imageId`, `imageVersion` | Exact provider and complete VM image coordinates. Missing identity, wildcards and Latest refuse. A container digest cannot satisfy these fields. |
| `variants.*.platform`, `runnerGroupId`, `runnerId` | OS/architecture and approved runner placement. Names may be explanatory; immutable IDs and actual job association control admission. |
| `variants.*.identityEvidence` | How trusted provider records bind the actual job runner to the approved image and configuration revision. Record API/job-log provenance and collection time; a workload-controlled file is insufficient. |
| `variants.*.toolProfiles` | Exact resolved versions and installation/archive identities, including interpreter/package sets and compiler variants. `stable`, `1.26.x`, or `22` alone are insufficient. |
| `actions` | Complete commit SHAs for image generation, setup, evidence transfer and publication actions, with reviewed sources. Tags are documentation only. |
| `generation` | Image-build repository/workflow/commit/run/attempt, base-image identity, build inputs, dependency inventory and scan evidence. |
| `validity` | Creation, promotion, expiration and retirement state. Expired, revoked or unpromoted images refuse new reuse and publication. |

The first implementation must define canonical manifest bytes, size bounds, duplicate
member rejection and unknown-field handling in a schema with handwritten vectors.
Do not prefill unavailable provider IDs or exact package versions with plausible
values. Populate them from the trusted pilot's measured outputs and approve them
before any consumer activates the revision.

Reusable workflow guidance: resolve a committed variant/profile key to its pinned
runner placement; select the exact source commit; set up only the pinned tools;
verify actual image/tool identity before running the required checks; capture it
with the manifest digest and full workflow/run/attempt/job provenance. Upload an
immutable evidence artifact. The release resolves the same manifest and compares
it with independently obtained provider/job records. Merely copying a generation
manifest onto the runner proves nothing about the current VM. A pinned action must
not fetch an unpinned installer or package transitively.

## Trust and admission

Image generation and promotion are trusted administrative operations. Use a
separate private control repository and restricted generation group, selected by
the organization administrator in the adoption record; do not grant a public
consumer access to that group. Only protected, reviewed generation revisions may
run there. Do not put long-lived credentials, repository workspaces or PR artifacts
in an image. Scan its contents and prove that consumer execution cannot publish a
new image or modify a promoted version.

Consumer PR jobs run with minimal read-only permissions in disposable instances
of a separate group. Fork jobs get no release credentials, promotion permission or
private-network access. Treat caches and artifacts from PR jobs as untrusted; a
trusted main job must not promote an image or release evidence from them. Separate
publication jobs retain the repository's protected environment and maintainer gate.
The identity-checking code and configuration must themselves be pinned to trusted
source; PR code cannot approve its own environment.

An adopter must preserve repository/commit equality, trusted default-branch event,
workflow ID, exact jobs and matrix coverage, latest-attempt selection, evidence age,
input identities, artifact provenance, platform/tool checks and final tag checks.
Add the approved complete-image identity to these predicates rather than replacing
them. Refuse missing, unexpected, mutable, stale, revoked or unauthorized identities;
refuse a runner switched to another image after evidence was captured. Refuse an
older green attempt when the selected attempt failed or remains incomplete. Never
normalize different image versions or extend the judgment-pack-agent exception.

Existing explicit fresh-check routes may remain only with their existing conditions
and an honest fresh-validation decision. New exact-image reuse cannot be obtained
by silently entering one. If a candidate's image expires or is revoked before
publication, abort the window, select a reviewed replacement revision and collect
new required evidence; an expired successful run cannot authorize publication.

## Promotion, patching, rollback and retirement

Proposed lifecycle: build candidate, scan and inventory, validate, independently
review, promote by manifest revision, adopt, retire. Generate patch candidates
weekly; triage urgent vulnerabilities within one working day and promote a tested
fix within 72 hours or suspend the affected release route. Those are proposed
operational targets for the owner to accept, not claims of an existing service.
Validate required native platforms, clean boot, tool identity, evidence refusal
vectors and representative integrations before promotion.

Reserve an immutable environment revision for the entire candidate CI/release
window; admission still respects each repository's at-most-48-hour evidence age.
Set a proposed maximum approved image age of 30 days, and reserve enough lifetime
for the planned window before starting. Account for provider/base-image expiration;
a local manifest cannot extend provider retention. Do not mutate an active runner
to a new image mid-window. Create a new placement/revision and validate it first.

Rollback selects a previous *still approved, unexpired, unrevoked* revision through
a reviewed manifest change. It collects new evidence for the candidate and never
searches for an older green run. Keep at most the active revision, an eligible
rollback revision and a bounded candidate during the pilot, subject to retention
and storage budgets. Retire unused images after all windows and artifact-retention
obligations close; record deletion and revoke their admission. Retain manifests,
inventories and review records for audit without keeping executable images forever.

## Validation and adoption sequence

The implementation will need these handwritten scenarios in each relevant verifier
and its shared reader. This documentation PR adds no executable test fixtures.

| Scenario | Required outcome and safeguard-removal control |
| --- | --- |
| Exact source, approved image, tools, variant and required jobs | Reuse only that selected successful attempt. |
| Same label, different image; missing version; forged workload file | Refuse. Remove the independent image-identity comparison and the test must fail at admission. |
| Wrong OS/architecture, missing matrix leg or wrong runner group | Refuse. Remove the corresponding identity/coverage check and catch each separately. |
| Changed manifest/tool/action pin after capture | Refuse. Remove input binding and demonstrate a false acceptance is caught. |
| Newer failed/incomplete attempt with older green evidence | Refuse. Remove latest-attempt selection and catch the older-green fallback. |
| Expired, revoked or unpromoted image; mutable Latest | Refuse. Remove lifecycle admission and catch each case. |
| Fork PR requests generation/promotion or supplies a trusted cache | Access denied; no promoted image/evidence produced. Exercise the real runner-group/workflow boundary in a controlled pilot. |
| Image mismatch on an explicitly opted-in fresh route | Record fresh validation under that existing contract; never report reuse. Remove the route distinction and catch the incorrect decision. |
| Native macOS or arm64 leg missing | Refuse release coverage; a cross-compiled executable alone does not supply native execution. |

Sequence: confirm entitlement/owner/budget and identity capabilities; review the
shared schema and pilot threat model; provision the isolated pilot in separately
authorized infrastructure work; validate and promote one revision; implement common
capture/admission support; adopt in dependency order per repository; run each stable
integrated candidate once through its required full CI and independent review.
A green result from a different head is never transferred. Keep focused checks during
implementation and required automatic CI enabled; avoid one full cycle per substep.

| Adoption issue | Required local decision |
| --- | --- |
| [judgment-pack-agent #239](https://github.com/Judgment-Pack/judgment-pack-agent/issues/239) | Replace the temporary exception with demonstrated identity guarantees; preserve specialized verifier predicates. |
| [judgment-pack-runtime #339](https://github.com/Judgment-Pack/judgment-pack-runtime/issues/339) | Preserve native release/image smoke and compatibility floor; decide fresh versus reusable checks explicitly. |
| [judgment-pack-runner #185](https://github.com/Judgment-Pack/judgment-pack-runner/issues/185) | Bind Linux producers/consumer; keep macOS limitation explicit. |
| [judgment-pack-gateway #344](https://github.com/Judgment-Pack/judgment-pack-gateway/issues/344) | Bind both Linux CI producers, packaging and native smoke variants; retain required job names. |
| [judgment-pack-spec #276](https://github.com/Judgment-Pack/judgment-pack-spec/issues/276) | Preserve conformance/package-set checks and tag-specific fresh routes; this lane makes no changes before v0.3.0. |
| [judgment-pack-desk #674](https://github.com/Judgment-Pack/judgment-pack-desk/issues/674) | Preserve Linux and both macOS archive architectures; pin mutable action/tool choices before claiming exact reuse. |
| [judgment-pack-exchange #48](https://github.com/Judgment-Pack/judgment-pack-exchange/issues/48) | Keep tag/history-sensitive checks fresh and pin the reusable tree-check environment. |

Milestones in those issues belong to their repository owners and may change; an
adoption milestone denotes its release tag. This assessment does not move one,
re-vendor judgment-pack-devkit, cut a release, or waive a native test or review.
Open decisions before provisioning are the plan/budget owner approval, runner-group
permissions and placement, independently verifiable image identity, macOS strategy,
measured SKU selection, exact tool inventory and operational ownership acceptance.
