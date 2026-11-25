"""Synchronize one trusted GitHub PR with Jira; Python standard library only."""

import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REPOSITORY = "N11CE1/SydneyCommuteCostCalculator"
JIRA_SITE = "https://tomhickman.atlassian.net"
PROJECT = "KAN"
BASE_BRANCH = "main"
EDITABLE_STATUSES = {"To Do", "In Progress", "In Review"}
EVENT_ACTIONS = {
    "opened", "reopened", "ready_for_review", "converted_to_draft",
    "closed", "edited", "synchronize",
}
KEY_PATTERN = r"KAN-[1-9][0-9]*"


class SyncError(Exception):
    pass


def ticket_key(pr):
    match = re.match(rf"^({KEY_PATTERN}):\s+\S", pr.get("title", ""))
    return match.group(1) if match else None


def trusted_pr(pr):
    base = pr.get("base") or {}
    head = pr.get("head") or {}
    return (
        (base.get("repo") or {}).get("full_name") == REPOSITORY
        and (head.get("repo") or {}).get("full_name") == REPOSITORY
        and base.get("ref") == BASE_BRANCH
    )


def completes_ticket(pr, key):
    # A single exact line is deliberate human attestation, not a mention anywhere.
    markers = []
    fence = None
    for line in (pr.get("body") or "").splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            delimiter = stripped[0]
            if fence is None:
                fence = delimiter
            elif fence == delimiter:
                fence = None
            continue
        if fence is None and line.startswith("Completes-Jira:"):
            markers.append(line)
    return markers == [f"Completes-Jira: {key}"]


def desired_status(pr, others):
    key = ticket_key(pr)
    if not key or not trusted_pr(pr):
        return None
    active = [
        other for other in others
        if other.get("number") != pr["number"]
        and trusted_pr(other) and ticket_key(other) == key
        and other.get("state") == "open"
    ]
    if pr.get("state") == "open":
        active.append(pr)
    if active:
        return "In Review" if any(not item.get("draft", True) for item in active) else "In Progress"
    if pr.get("merged") and pr.get("state") == "closed":
        return "Done" if completes_ticket(pr, key) else None
    if pr.get("state") == "closed":
        return "In Progress"
    return None


def eligible_target(issue, target, may_start=True):
    fields = issue.get("fields", {})
    status = fields.get("status", {})
    current = status.get("name")
    if fields.get("project", {}).get("key") != PROJECT:
        raise SyncError("Jira returned an issue outside the allowed project.")
    if status.get("statusCategory", {}).get("key") == "done":
        # Allow recovery of a failed completion comment, never reopen a completed issue.
        return "Done" if current == target == "Done" else None
    if current not in EDITABLE_STATUSES:
        return None
    # An abandoned PR must not start an otherwise untouched To Do ticket.
    if target == "In Progress" and current == "To Do" and not may_start:
        return None
    return target


def transition_id(transitions, target):
    matches = [item for item in transitions if item.get("to", {}).get("name") == target]
    if len(matches) != 1:
        raise SyncError(f"Expected one available transition to {target}; found {len(matches)}.")
    transition = matches[0]
    if any(field.get("required") for field in transition.get("fields", {}).values()):
        raise SyncError(f"Transition to {target} requires fields; manual action needed.")
    return transition["id"]


def comment_marker(number, key, target):
    return f"[jira-pr-sync:v1:{REPOSITORY}:{number}:{key}:{target}]"


def contains_text(value, text):
    if isinstance(value, dict):
        return any(contains_text(item, text) for item in value.values())
    if isinstance(value, list):
        return any(contains_text(item, text) for item in value)
    return isinstance(value, str) and text in value


def comment_body(pr, key, target, marker):
    reason = (
        "Merged into main with an explicit completion marker and no other open PR for this ticket."
        if target == "Done" else
        "Status reconciled against current PR state and other open PRs for this ticket."
    )
    text = (
        f"GitHub PR #{pr['number']}: https://github.com/{REPOSITORY}/pull/{pr['number']}\n"
        f"Jira target: {target}. {reason}\n{marker}"
    )
    return {"body": {"type": "doc", "version": 1, "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": text}]}
    ]}}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward credentials to another URL, including a provider error redirect.
        return None


class API:
    def __init__(self, base_url, authorization, service):
        self.base_url = base_url
        self.authorization = authorization
        self.service = service
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {
            "Authorization": self.authorization,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "SydneyCommute-Jira-Sync/1",
        }
        if self.service == "GitHub":
            headers["X-GitHub-Api-Version"] = "2022-11-28"
            headers["Accept"] = "application/vnd.github+json"
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        for attempt in range(3):
            try:
                with self.opener.open(req, timeout=25) as response:
                    payload = response.read()
                    return json.loads(payload) if payload else None
            except urllib.error.HTTPError as error:
                error.close()
                # Retry only reads. A failed response to a write may already have applied it.
                if method == "GET" and (error.code == 429 or error.code >= 500) and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise SyncError(
                    f"{self.service} {method} failed (HTTP {error.code}). "
                    "Check credentials, scopes, permissions, rate limits and workflow logs."
                ) from None
            except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                raise SyncError(f"{self.service} {method} failed: network or invalid response.") from None


def list_open_prs(github):
    result = []
    page = 1
    while True:
        items = github.request(
            "GET", f"/repos/{REPOSITORY}/pulls?state=open&base={BASE_BRANCH}&per_page=100&page={page}"
        )
        if not isinstance(items, list):
            raise SyncError("GitHub returned an invalid pull-request list.")
        result.extend(items)
        if len(items) < 100:
            return result
        page += 1


def comments_contain(jira, key, marker):
    start = 0
    while True:
        page = jira.request("GET", f"/rest/api/3/issue/{key}/comment?startAt={start}&maxResults=100")
        items = page.get("comments", [])
        if any(contains_text(item.get("body"), marker) for item in items):
            return True
        start += len(items)
        if start >= page["total"]:
            return False
        if not items:
            raise SyncError("Jira comment pagination made no progress.")


def snapshot(pr):
    return tuple(pr.get(field) for field in (
        "number", "title", "body", "state", "draft", "merged", "updated_at"
    )) + (pr.get("head", {}).get("sha"), pr.get("base", {}).get("ref"), trusted_pr(pr))


def active_snapshot(prs, key):
    return sorted(
        (pr["number"], pr.get("draft", True), pr.get("updated_at"))
        for pr in prs if trusted_pr(pr) and ticket_key(pr) == key and pr.get("state") == "open"
    )


def sync(github, jira, number, dry_run=False):
    pr_path = f"/repos/{REPOSITORY}/pulls/{number}"
    pr = github.request("GET", pr_path)
    key = ticket_key(pr)
    if not trusted_pr(pr) or not key:
        return {"result": "skipped", "reason": "PR must be same-repository, target main, and start with KAN-N: in its title."}
    others = list_open_prs(github)
    desired = desired_status(pr, others)
    issue_path = f"/rest/api/3/issue/{key}"
    issue = jira.request("GET", issue_path + "?fields=status,project")
    may_start = pr.get("state") == "open" or bool(active_snapshot(others, key))
    target = eligible_target(issue, desired, may_start)
    current = issue["fields"]["status"]["name"]
    # Dry-run also checks read scopes even if no transition is currently needed.
    transitions = jira.request("GET", issue_path + "/transitions?expand=transitions.fields")["transitions"]
    marker = comment_marker(number, key, target) if target else "[jira-pr-sync:validation]"
    already_commented = comments_contain(jira, key, marker)
    result = {"ticket": key, "current": current, "target": target, "dry_run": dry_run}
    if not target:
        return dict(result, result="skipped", reason="No eligible transition or explicit completion marker; completed/custom states are preserved.")
    selected_transition = transition_id(transitions, target) if current != target else None
    if dry_run:
        return dict(result, result="preview", comment_needed=not already_commented)
    # Fail closed on concurrent edits; the newer PR event can reconcile current state.
    latest = github.request("GET", pr_path)
    latest_others = list_open_prs(github)
    if snapshot(pr) != snapshot(latest) or active_snapshot(others, key) != active_snapshot(latest_others, key):
        raise SyncError("PR state changed during reconciliation; rerun with current state.")
    latest_issue = jira.request("GET", issue_path + "?fields=status,project")
    if latest_issue["fields"]["status"] != issue["fields"]["status"] or eligible_target(latest_issue, target, may_start) != target:
        raise SyncError("Jira state changed during reconciliation; rerun with current state.")
    if selected_transition:
        jira.request("POST", issue_path + "/transitions", {"transition": {"id": selected_transition}})
        confirmed = jira.request("GET", issue_path + "?fields=status,project")
        if confirmed["fields"]["status"]["name"] != target:
            raise SyncError("Jira did not reach the expected status; inspect the ticket before retrying.")
    # Retry after a comment failure is safe even if the transition already succeeded.
    if not already_commented:
        jira.request("POST", issue_path + "/comment", comment_body(pr, key, target, marker))
    return dict(result, result="updated" if selected_transition or not already_commented else "unchanged")


def event_number(event_name, event):
    if event.get("repository", {}).get("full_name") != REPOSITORY:
        raise SyncError("Event repository is not allowed.")
    if event_name == "workflow_dispatch":
        number = event.get("inputs", {}).get("pr_number", "")
        dry_run = True  # Manual validation cannot mutate Jira.
    elif event_name == "pull_request_target" and event.get("action") in EVENT_ACTIONS:
        number = event.get("number")
        dry_run = False
    else:
        raise SyncError("Unsupported event or action.")
    if not re.fullmatch(r"[1-9][0-9]*", str(number)):
        raise SyncError("Invalid PR number.")
    return int(number), dry_run


def clients(env):
    required = ("GITHUB_TOKEN", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_CLOUD_ID", "JIRA_BASE_URL")
    missing = [name for name in required if not env.get(name)]
    if missing:
        raise SyncError("Missing configuration: " + ", ".join(missing))
    if env["JIRA_BASE_URL"].rstrip("/") != JIRA_SITE:
        raise SyncError("JIRA_BASE_URL does not match this project's Jira site.")
    try:
        cloud_id = str(uuid.UUID(env["JIRA_CLOUD_ID"]))
    except ValueError:
        raise SyncError("JIRA_CLOUD_ID must be a UUID, not a site URL.") from None
    auth = base64.b64encode((env["JIRA_EMAIL"] + ":" + env["JIRA_API_TOKEN"]).encode()).decode()
    return (
        API("https://api.github.com", "Bearer " + env["GITHUB_TOKEN"], "GitHub"),
        API("https://api.atlassian.com/ex/jira/" + cloud_id, "Basic " + auth, "Jira"),
    )


def main():
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        number, dry_run = event_number(os.environ["GITHUB_EVENT_NAME"], event)
        github, jira = clients(os.environ)
        print(json.dumps(sync(github, jira, number, dry_run), sort_keys=True))
    except SyncError as error:
        print(f"Jira sync failed: {error}", file=sys.stderr)
        return 1
    except Exception:
        # Avoid response bodies, credentials or untrusted event text in error logs.
        print("Jira sync failed: unexpected response or invalid configuration; see tests/setup guide.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
