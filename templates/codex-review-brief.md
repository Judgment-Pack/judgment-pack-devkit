# Review brief: TITLE (pull request or issue #N of OWNER/NAME)

## Role
Act as the reviewer. Read the issue, the repository rules and the complete change at the reviewed
head. Do not continue earlier builder reasoning.

## Read-only rules
Do not change tracked files, create commits, push, post comments or open pull requests. You may
build once and run focused probes or mutants that leave the tracked tree unchanged.

## Review scope
State the contract to review, the relevant files and the accepted design. Check the implementation,
tests and documentation against them.

## Report
Findings first, ordered by severity, with file and line references. Then state the reviewed head,
the probes run, and any residual risk. End with exactly one of these lines:

merge: yes | after fixes
