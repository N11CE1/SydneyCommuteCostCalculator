# Jira synchronization from GitHub PR events

Tracking: [SCCC-9](https://tomhickman.atlassian.net/browse/SCCC-9) (original automation), [SCCC-11](https://tomhickman.atlassian.net/browse/SCCC-11) (default assignment), and [SCCC-12](https://tomhickman.atlassian.net/browse/SCCC-12) (project-key migration).

## Deployment status

The sync workflow is deployed on `main` through [PR #3](https://github.com/N11CE1/SydneyCommuteCostCalculator/pull/3). Authentication and Jira reads succeeded after the repository credentials were updated. Both original merge reruns intentionally reported `skipped`: neither PR had a completion marker, so KAN-4 and KAN-9 remained In Review.

Dedicated lifecycle validation was completed under KAN-10 (now [SCCC-10](https://tomhickman.atlassian.net/browse/SCCC-10)) and [PR #4](https://github.com/N11CE1/SydneyCommuteCostCalculator/pull/4). Status transitions, audit comments, completion reconciliation and automatic branch deletion were verified as recorded below. Historical keys and audit markers are intentionally preserved in that evidence. Successful reads alone are not proof of writes.

### SCCC migration and rollout

On 2026-11-26 Jira project `10001` was verified with canonical key `SCCC`, previous key `KAN` retained, and Tom Hickman as project lead. The migrated script described here must be merged into `main` before normal PR-event handling can use it. Until then, the deployed KAN-only script skips `SCCC-N:` titles; historical KAN titles may fail its obsolete project-key guard after Jira returns canonical `SCCC`. Do not work around this by executing PR-head code with secrets or weakening the project guard.

The migrated script:

- Accepts exact `SCCC-N:` and retained `KAN-N:` title prefixes. New work uses SCCC.
- Resolves both aliases to `SCCC-N` for Jira API calls, competing-open-PR checks and new audit comments. It verifies Jira's returned project ID `10001` and canonical key `SCCC` before writes.
- Requires a completion marker to match the **literal title key**: a historical `KAN-9:` title needs `Completes-Jira: KAN-9`. `SCCC-9:` needs `Completes-Jira: SCCC-9`. Mixed-prefix, duplicate and conflicting markers never authorize completion, even when aliases identify the same ticket.
- Recognizes both old KAN and new SCCC audit markers for the same repository, PR, ticket number and target status. Historical comments are not rewritten, and retitling a PR does not duplicate its audit comment.

For the migration PR, use a canonical SCCC title and keep the ticket's status reconciled manually while the old script is deployed. Do not include a completion marker while live deployment validation is outstanding. After an approved merge, run `workflow_dispatch` from `main` against that PR to verify canonical Jira reads in read-only mode; inspect `result` and `ticket`, not just a green check. With explicit completion approval, add the exact matching marker and verify the ensuing edited-event reconciliation or rerun the merge-event job. Read back Jira status and comments, confirm no duplicates, and record run URLs before closing SCCC-12. A markerless successful `skipped` run is not live verification of a write.

The automation uses GitHub Actions and Jira REST directly. GitHub for Atlassian is optional for richer development-panel linking; this workflow does not install it or replace its functionality. Existing editor-driven MCP access remains separate.

## Repository configuration

GitHub Settings → Secrets and variables → Actions:

| Kind | Name | Value |
|---|---|---|
| Secret | `JIRA_API_TOKEN` | Atlassian API token; current successful reads use an unscoped token. Never disclose in logs or source |
| Secret | `JIRA_EMAIL` | Email for the account that created the token |
| Variable | `JIRA_BASE_URL` | `https://tomhickman.atlassian.net` (site validation/documentation, not the scoped API endpoint) |
| Variable | `JIRA_CLOUD_ID` | `9dc905e8-9878-4f15-a9bf-6510ec753f4b` |

The implementation's fixed API endpoint is `https://api.atlassian.com/ex/jira/<cloud-id>/rest/api/3/...`, authenticated with the email/token pair. The token account needs Browse projects, Transition issues and Add comments permissions in SCCC, plus visibility of the relevant issues. Token scopes cannot grant permissions the account lacks. A dedicated, project-limited account is preferable to a personal administrator token.

GitHub Actions must be enabled, including permission to use the pinned `actions/checkout` action. The workflow itself requests only read access to repository contents and PRs. No GitHub write token is needed for synchronization.

### Granular Jira scopes

Least-privilege scoped-token authentication remains a hardening follow-up, not a verified configuration. Initial scoped-token runs returned HTTP 401; reads succeeded after both the email and token were replaced, so the failing credential was not isolated. Do not change endpoints or broaden permissions speculatively, and never log secret values.

The documented dependencies for the issue read, transition read/write, and comment read/write endpoints are:

```text
read:issue:jira
read:issue-meta:jira
read:issue-security-level:jira
read:issue.vote:jira
read:issue.changelog:jira
read:issue.transition:jira
read:status:jira
read:field-configuration:jira
write:issue:jira
write:issue.property:jira
read:comment:jira
read:comment.property:jira
write:comment:jira
read:group:jira
read:project:jira
read:project-role:jira
read:user:jira
read:avatar:jira
```

No delete, Jira administration, Confluence, user-management or webhook-management scopes are required. Check the current [issue/transition](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/) and [comment](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-comments/) documentation when rotating scopes or expanding functionality.

## Ticket and completion conventions

Use a title beginning with an exact key and colon, for example:

```text
SCCC-9: Synchronize Jira from GitHub events
```

The workflow links only that one title ticket. It does not collect arbitrary keys mentioned in descriptions, dependency lists, review comments, or code. Continue to include a Jira URL in the description and ticket key in the branch name.

To attest that the PR delivers the ticket's **entire** scope, add one standalone line to the PR body, outside code fences and quotations:

```text
Completes-Jira: SCCC-9
```

The key must match the title key. Duplicate/conflicting markers, extra text on the line, trailing spaces, and quoted/fenced examples do not authorize completion. Omit the line for partial work. The marker is a human assertion, not a machine check of acceptance criteria. In particular, SCCC-12 should not be marked complete until its deployment and live validation are recorded.

## Event behaviour

Only same-repository PRs in `N11CE1/SydneyCommuteCostCalculator` targeting `main` are eligible. Fork PRs, other bases and malformed/missing title prefixes are skipped.

| Current GitHub state | Result for eligible Jira statuses |
|---|---|
| Open and ready for review | In Review |
| Open and draft | In Progress, unless another ready PR for that ticket is open |
| Closed without merging | Never Done; return In Review to In Progress only if no other ready PR remains; do not start an untouched To Do ticket |
| Merged into main, no completion marker | Leave open; no completion transition |
| Merged with matching completion marker, no other open PR for ticket | Done |
| Another PR for that ticket is open | In Review if any eligible open PR is ready, otherwise In Progress; do not complete |
| Already completed or in a custom state such as Blocked | Preserve state; a failed completion comment can be retried on an already-Done ticket |

Opening, reopening, readiness/draft changes, closing, editing and head updates trigger reconciliation. The script re-fetches current PR state, so a stale event payload cannot blindly move a ticket backwards. It lists other open PRs before planning and rechecks GitHub/Jira immediately before writes. Cross-service changes are not transactional: if the state changes during reconciliation, the run fails closed and should be rerun after inspecting current state. A narrow race after the final check cannot be eliminated by REST calls alone.

After the final PR for a multi-PR ticket merges, that final PR must carry the completion marker if the scope is complete. A marker on an earlier merge that was blocked by another open PR is not an instruction to complete the ticket later regardless of the final PR.

## Security and reliability

- Secret-bearing runs use `pull_request_target`, not a PR-head test runner.
- Checkout is explicitly the trusted default branch, with persisted Git credentials disabled. Never change it to a PR head/merge ref or download/execute PR artifacts in this job.
- No untrusted PR text is interpolated into a shell command. Python treats event data as data; ticket keys and PR numbers are validated.
- External API hosts are fixed; redirects are refused and error response bodies are not logged.
- A repository-wide concurrency group serializes sync runs. `queue: max` retains up to 100 queued runs instead of replacing the previous pending run. Queue overflow, disabled Actions, missed events and expired tokens still require operator attention; this is not a durable event bus.
- GET requests have bounded retries. POSTs are not automatically retried because an ambiguous response may already have applied a mutation.
- Comments carry a stable PR/ticket/target marker. Repeated deliveries do not create duplicate status comments, including recovery if a transition succeeded but its comment failed. Later returns to the same PR/status reuse the existing audit comment rather than adding another.
- Transition IDs are looked up by destination status; missing, ambiguous or required-field transitions stop the run for manual intervention. After a transition, read-back must confirm the requested status before posting a success comment.
- Missing secrets/variables, authentication failures and unexpected responses fail visibly. Do not add debug output that prints headers, environment variables or response bodies.
- Dispatch is restricted to `main`; normal read-only preview runs cannot mutate Jira. Rerunning a mutating PR-event run re-evaluates current state rather than replaying old status instructions.

The separate `Automation tests` workflow executes proposed code with no Jira secrets, a read-only GitHub token and no persisted checkout credentials. Both workflows pin checkout to a verified commit. Review action updates like other dependencies.

## Validation

### Live evidence — 2026-11-25

The original non-merge tests used the dedicated KAN-10 ticket and docs-only PR #4, not application tickets. PR #4 was subsequently merged by the owner and completion was separately authorized, as recorded below.

| Event | Observed result | Actions run |
|---|---|---|
| Draft opened | To Do → In Progress, PR-link comment 10007 added | [45599806766](https://github.com/N11CE1/SydneyCommuteCostCalculator/actions/runs/45599806766) |
| Mark ready | In Progress → In Review, comment 10008 added | [45599975988](https://github.com/N11CE1/SydneyCommuteCostCalculator/actions/runs/45599975988) |
| Convert to draft | In Review → In Progress, existing comment reused | [45600047369](https://github.com/N11CE1/SydneyCommuteCostCalculator/actions/runs/45600047369) |
| Mark ready again | In Progress → In Review | [45600119734 attempt 1](https://github.com/N11CE1/SydneyCommuteCostCalculator/actions/runs/45600119734/attempts/1) |
| Rerun same event | `unchanged`, still exactly two automation comments | [45600119734 attempt 2](https://github.com/N11CE1/SydneyCommuteCostCalculator/actions/runs/45600119734/attempts/2) |
| Close without merge | In Review → In Progress, never Done; read back from Jira | [45600383985](https://github.com/N11CE1/SydneyCommuteCostCalculator/actions/runs/45600383985) |
| Reopen ready PR | In Progress → In Review | [45600549407](https://github.com/N11CE1/SydneyCommuteCostCalculator/actions/runs/45600549407) |

GitHub's PR timeline recorded automatic `review_requested` for Copilot and `copilot_work_started`. Copilot submitted its completed review at 10:58:51 UTC on the initial docs commit, with no active issues. This verifies the automatic request and execution, not approval of subsequent commits.

PR #4 was merged into `main` at `2026-11-25T11:04:44Z` (commit `302a12ad63631f39256a2a281d711247ba83d748`). GitHub recorded `head_ref_deleted` at `11:04:46Z`, verifying remote branch cleanup. The initial merge job [45601030374 attempt 1](https://github.com/N11CE1/SydneyCommuteCostCalculator/actions/runs/45601030374/attempts/1) intentionally skipped because the body lacked a completion marker.

With explicit owner approval, adding `Completes-Jira: KAN-10` triggered [45601442106](https://github.com/N11CE1/SydneyCommuteCostCalculator/actions/runs/45601442106), which reported In Review → Done and created completion comment 10012. The requested [merge-job rerun, attempt 2](https://github.com/N11CE1/SydneyCommuteCostCalculator/actions/runs/45601030374/attempts/2) reported `unchanged` at Done without duplicating the comment. Jira read-back independently confirmed Done. This verifies completion reconciliation after a post-merge marker edit, not a separate marker-present-at-merge event.

These historical KAN runs do not establish live SCCC-key support. SCCC-12 requires post-deployment validation. Multiple-concurrent-PR live behavior and least-privilege scoped-token authentication also remain unverified. Unit coverage is not a substitute for those live checks.

### Local tests (no credentials or live Jira writes)

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

### After this workflow is merged into main

1. Run a read-only preview against an eligible PR:

   ```sh
   gh workflow run jira-pr-sync.yml --ref main -f pr_number=2
   gh run list --workflow jira-pr-sync.yml --limit 5
   ```

   Alternatively, use Actions → Jira PR sync → Run workflow. Manual dispatch is always read-only. Inspect the run for issue/status, available-transition and comment-read success. A preview verifies read authentication/scopes, not write permissions.

2. With approval, create a dedicated SCCC test ticket and same-repository test PR targeting main. Use that key in the title. Opening a draft should move the ticket to In Progress. Marking ready should move it to In Review and add a PR-link comment.
3. Toggle back to draft and ready, and rerun a completed event run. Verify state reconciliation and no duplicate same-status comments. Do not involve real delivery tickets in destructive experiments.
4. Close the test PR without merging. Verify the test ticket stays open, and check another-ready-PR handling if testing multiple PRs.
5. Test completion only through a separately approved, genuinely complete PR merged into main with a matching marker. Verify Done and its audit comment. Never merge a PR simply to exercise automation without approval.
6. Record run URLs and observed Jira status/comments in the tracking ticket (SCCC-12 for this migration). Only then claim synchronization has been verified and resolve the automation ticket when its scope is complete.

Adding a workflow does not guarantee its own initial merge produces a successful sync run. Reconcile the tracking ticket manually if necessary after successful deployment/testing. This workflow does not add a required CI status check to branch protection automatically.

## Default ticket assignment (SCCC-11)

The owner configured Jira's native project default assignee as the project lead, Tom Hickman. No GitHub code, issue-created automation rule, global assignment setting or bulk reassignment is needed. Editor/MCP creates should **omit** `assignee` unless another person is explicitly requested; preserve that explicit choice.

Live check on 2026-11-26: created genuine migration task [SCCC-12](https://tomhickman.atlassian.net/browse/SCCC-12) through `createJiraIssue` with `projectKey: SCCC` and **no assignee argument**. Independent `getJiraIssue` read-back returned Tom Hickman. The ticket was not manually reassigned afterward to manufacture a passing result. The earlier SCCC-11 ticket was explicitly assigned at creation, so it is not evidence for the default.

Verification is limited to editor/MCP creation with an omitted assignee. An explicitly unassigned payload can bypass a default; UI, imports and other integrations may send explicit values and must be checked separately. Assignment to a different person has not been live-tested; do not claim a custom overwrite rule is preserving it. No such rule was installed, and the native default should leave explicit choices intact. Read back every created ticket; if it is unexpectedly unassigned, report the failure rather than silently assigning it and claiming default automation worked.

This assignment convention is independent of PR-status synchronization and does not automatically assign existing unassigned tickets. Keep SCCC-11 open until its documentation is merged and its scoped acceptance criteria are reconciled.

## Repository review and cleanup settings

Configured on 2026-11-25 with user authorization:

- `delete_branch_on_merge: true` removes eligible remote head branches after merge, not local branches. Live deletion was verified after PR #4 merged; see the timeline evidence above.
- Active repository ruleset **Automatic Copilot review** targets `~DEFAULT_BRANCH`, with `review_draft_pull_requests: true` and `review_on_push: false`. This requests review at PR creation, including drafts, without requesting another review on every push.
- Copilot execution depends on the author's entitlement and available allowance. No paid-overage setting was changed. A configured rule is not evidence that a review completed.
- Existing classic protection for `main` is retained: PR required including admins, conversations resolved, no force pushes or branch deletion, and no extra approving review required for the solo maintainer.

## Failure recovery

Inspect Actions → Jira PR sync, correct configuration/permissions or resolve a concurrent edit, then rerun the failed event job. For a read-only diagnostic use manual dispatch. Repeatedly failing actions must not be treated as successful Jira updates. If a ticket is not eligible because of a custom or completed state, update it manually through the editor instead of weakening the guardrails.

No repository-local build caches are needed by this automation. Python bytecode generation is disabled in documented test commands and Actions.
