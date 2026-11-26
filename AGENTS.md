# Project working agreement

## Product and scope

Read `DesignDoc.md` before implementation. Start with the map-first, personal-use rental/public-transport MVP. Keep provider-specific map and route objects outside scenario data and calculation code. Do not expand into driving, mortgages, accounts, or automated fare billing without an agreed ticket.

## Jira and GitHub

- Jira site: https://tomhickman.atlassian.net
- Jira project: `SCCC` (SydneyCommuteCostCalculator), project ID `10001`. Previous key `KAN` is retained for historical links; use `SCCC` for new work.
- Repository: https://github.com/N11CE1/SydneyCommuteCostCalculator
- Integration branch: `main`. Deliver implementation through pull requests, not direct pushes to `main`.
- Credentials belong in secure local configuration, never source files, PR bodies, or tickets.

### Before starting work

1. Find the relevant existing ticket; do not create duplicates. Create a ticket with scope and acceptance criteria for new agreed work.
2. Read its current requirements and dependencies. Keep work small; split a broad story into delivery tasks when useful.
3. Obtain explicit user authorization before creating branches or making commits. Inspect the working tree and preserve existing user changes.
4. For authorized new work, branch from current `main` and include the ticket key, e.g. `SCCC-6/map-prototype`. Do not reuse a merged branch for new work.
5. Move the ticket from **To Do** to **In Progress** when implementation starts. Query the issue's available transitions rather than guessing transition IDs.

### Ticket assignment

- New SCCC tickets default to Tom Hickman through Jira's native project default assignee (project lead). For editor/MCP creation, omit `assignee` to use that default, unless the user explicitly requests someone else.
- Preserve explicitly chosen assignees. Do not bulk-reassign existing tickets or change site-wide assignment settings.
- Read back the created ticket's assignee. If the default fails, report it rather than claiming success or silently assigning it afterward as proof of automation.
- An omitted assignee is not the same as an explicitly unassigned value. The latter and other creation channels must not be assumed to follow the default.
- Verified on 2026-11-26: SCCC-12 was created via MCP without an assignee argument and independently read back as assigned to Tom. SCCC-11 tracks this convention; see `docs/jira-automation.md` for limits.

### During implementation and review

- Keep changes scoped to the ticket and record material decisions or blockers in Jira.
- Keep generated caches outside the worktree where practical. Never commit `.cache/`, build outputs, dependencies, or secrets. Do not delete unrelated files to clean up generated output.
- Run relevant checks and report actual results. A test file existing is not evidence that a test run passed.
- When authorized to commit/push, use a ticket-prefixed PR title, e.g. `SCCC-6: Add map-first rental prototype`.
- Include the Jira URL, scope, acceptance-criteria coverage, actual validation results, and remaining limitations in the PR body.
- Add the PR URL to Jira and Jira URL to the PR. A manual remote link is useful even when automatic development-panel linking is not configured.
- Draft PRs normally remain **In Progress**. Move to **In Review** when the PR is ready for review, not simply because a draft exists.
- Do not merge PRs unless explicitly requested by the user.

### Completion and reconciliation

1. Read the PR's actual GitHub state. Closed is not necessarily merged.
2. Only transition a ticket to **Done** when its scoped acceptance criteria are satisfied and its implementation is merged into `main`.
3. Add a completion comment with the merged PR link, validation performed, and any separately ticketed follow-up work.
4. For a PR closed without merging, keep the ticket open; return it to **In Progress** or **To Do** as appropriate and explain why.
5. Reconcile Jira after a merge performed outside the editor when asked or when next working on that ticket. No background polling is implied.
6. Do not close a broad story merely because one partial implementation PR merged. Keep remaining work explicit.

## Current integration limits

Authenticated GitHub CLI and Atlassian MCP allow editor-driven ticket creation, linking, comments, and workflow transitions. They do **not** by themselves configure automatic event synchronization.

GitHub Actions PR-event synchronization is deployed on `main`; see `docs/jira-automation.md` for security, setup, and validation evidence. The original KAN lifecycle, including completion reconciliation after merge, was verified under SCCC-10 (then KAN-10). SCCC-key migration is tracked in SCCC-12 and requires deployment and live validation after merge. A green run that reports `skipped` is not proof of a status write.

- Use the exact `SCCC-N:` title prefix for new work. The migrated script also accepts retained `KAN-N:` prefixes for historical PRs, groups both aliases as the same ticket, and recognizes old audit markers to prevent duplicate comments. Draft PRs map to In Progress; ready PRs map to In Review.
- Completion requires a verified merge into `main`, the full ticket scope delivered, and a matching standalone `Completes-Jira: SCCC-N` line in the PR body. For historical `KAN-N:` titles the marker must retain that exact spelling; mixed-prefix completion markers are rejected even for the same ticket number.
- Exclude drafts and closed-unmerged PRs from completion. Handle tickets with multiple PRs explicitly rather than closing on the first merge.
- Record actual workflow runs and Jira status/comments before claiming a lifecycle path is verified.
- GitHub for Atlassian development-panel linking is optional and remains unverified; it is separate from this REST-based synchronization.
- `Closes #123` is GitHub issue syntax; it does not close a Jira ticket.

## Main branch protection

Verified on 2026-11-25: GitHub protection for `main` requires a pull request, applies to administrators, blocks force-pushes and branch deletion, and requires review conversations to be resolved before merging.

This is a solo-maintainer repository: no additional approving review is required, and no CI status checks are required yet. These settings allow the owner to merge their own PR without permitting direct implementation pushes. Add required checks when CI exists; reconsider approval requirements if collaborators join.

Do not weaken or bypass protection to deliver work. Changes to protection require explicit user authorization. Branch protection does not configure Jira synchronization.

## Branch cleanup and Copilot review

Configured and read back on 2026-11-25:

- Automatically delete eligible PR head branches after merge. This does not delete local branches or override protection for `main`.
- An active, additive ruleset requests Copilot review for PRs targeting the default branch, including drafts on creation. Reviews on every new push are disabled to avoid unnecessary usage.
- Copilot reviews depend on account entitlement and available allowance; this setting does not enable paid overages or make AI approval a merge requirement.
- Preserve the existing `main` protection independently of this Copilot-only ruleset.
