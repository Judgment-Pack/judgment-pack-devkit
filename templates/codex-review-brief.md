# Review brief: TITLE (pull request or issue #N of OWNER/NAME)

## Role
Act as the reviewer. Read the issue, the repository rules and the complete change at the reviewed
head. Do not continue earlier builder reasoning.

## Read-only rules
Do not change tracked files, create commits, push, post comments or open pull requests. You may
reuse the verified candidate build and check evidence; build once only when that build is
unavailable or invalid. Run focused probes or mutants that leave the tracked tree unchanged.
Confirm the stable integrated batch passed its required full checklist before CI.
Begin only after green CI on the exact reviewed head. Do not repeat verified deterministic suites.

## Review scope
State the contract to review, the relevant files and the accepted design. Check the implementation,
tests and documentation against them. Follow
[Testing in the Devkit policy](https://github.com/Judgment-Pack/judgment-pack-devkit/blob/main/docs/policy.md#testing):
verify artifacts and real consumer paths, identify the candidate product explicitly, and require
safeguard removal to fail the intended assertion rather than setup, compilation or timeout.
Probe uncovered contracts. Reuse the original reviewer for finding-specific fix confirmation;
restart a broad review only for substantive change or new evidence. Whole-release review remains.

## Report
Findings first, ordered by severity, with file and line references. Then state the reviewed head,
the probes run, and any residual risk. End with exactly one of these lines:

merge: yes
merge: after fixes
