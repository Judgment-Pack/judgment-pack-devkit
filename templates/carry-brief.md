# Brief: carry pull request #{{PR}}

## Rules
Read this repository's AGENTS.md and follow it. Resolve only the merge conflicts already present
on branch `{{BRANCH}}`. Do not fetch, rebase, start another merge or change unrelated files.

## Goal
Carry base commit `{{BASE_COMMIT}}` into this branch. Keep both decisions whole, with main's additions
first where ordering is meaningful. Regenerate derived files with the repository's
documented command after resolving their sources; do not hand-edit generated output.

## Conflicts
{{CONFLICTS}}

## Before you write msg.txt
Run only the checks that cover the resolved files, then follow AGENTS.md's handover rules. Confirm
that the index has no unresolved entry and that the merge keeps both the base and branch decisions.

## Files you write
Write `msg.txt` with the signed merge commit's subject and factual body. The wrapper pushes this
branch and does not open another pull request. Do not run `git commit`, `git push` or `gh`.
