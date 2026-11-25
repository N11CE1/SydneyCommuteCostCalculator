import copy
import io
import json
import unittest
import urllib.error
from unittest.mock import Mock, patch

from scripts import jira_pr_sync as sync


def pr(number=9, **overrides):
    result = {
        "number": number,
        "title": "KAN-9: Automate Jira status",
        "body": "Jira: https://tomhickman.atlassian.net/browse/KAN-9",
        "state": "open",
        "draft": False,
        "merged": False,
        "updated_at": "2026-11-25T10:00:00Z",
        "head": {"sha": "abc123", "repo": {"full_name": sync.REPOSITORY}},
        "base": {"ref": "main", "repo": {"full_name": sync.REPOSITORY}},
    }
    result.update(overrides)
    return result


def issue(status="In Progress", category="indeterminate", project="KAN"):
    return {"fields": {
        "project": {"key": project},
        "status": {"name": status, "statusCategory": {"key": category}},
    }}


class FakeGitHub:
    def __init__(self, current=None, others=None):
        self.current = current if current is not None else pr()
        self.others = others or []
        self.pr_reads = 0
        self.list_reads = 0
        self.change_pr_on_recheck = False
        self.change_others_on_recheck = False

    def request(self, method, path, body=None):
        if method != "GET":
            raise AssertionError("Automation must never write to GitHub")
        if "?state=open" in path:
            self.list_reads += 1
            items = self.others + ([self.current] if self.current["state"] == "open" else [])
            if self.change_others_on_recheck and self.list_reads > 1:
                items.append(pr(10, draft=True))
            return copy.deepcopy(items)
        self.pr_reads += 1
        result = copy.deepcopy(self.current)
        if self.change_pr_on_recheck and self.pr_reads > 1:
            result["draft"] = not result["draft"]
        return result


class FakeJira:
    def __init__(self, current=None):
        self.issue = current or issue()
        self.transitions = [
            {"id": "21", "to": {"name": "In Progress"}},
            {"id": "31", "to": {"name": "In Review"}},
            {"id": "41", "to": {"name": "Done"}},
        ]
        self.comments = []
        self.writes = []
        self.reads = []
        self.change_on_recheck = False
        self.fail_comment_once = False
        self.ignore_transition = False

    def request(self, method, path, body=None):
        if method == "GET":
            self.reads.append(path)
            if "/transitions?" in path:
                return {"transitions": copy.deepcopy(self.transitions)}
            if "/comment?" in path:
                return {"comments": copy.deepcopy(self.comments), "total": len(self.comments)}
            result = copy.deepcopy(self.issue)
            issue_reads = sum("?fields=" in item for item in self.reads)
            if self.change_on_recheck and issue_reads > 1:
                result["fields"]["status"]["name"] = "Blocked"
            return result
        if method != "POST":
            raise AssertionError("Only specific Jira POST operations are expected")
        self.writes.append((path, body))
        if path.endswith("/transitions"):
            target = next(item["to"]["name"] for item in self.transitions if item["id"] == body["transition"]["id"])
            if not self.ignore_transition:
                self.issue = issue(target, "done" if target == "Done" else "indeterminate")
        elif path.endswith("/comment"):
            if self.fail_comment_once:
                self.fail_comment_once = False
                raise sync.SyncError("Comment failed")
            self.comments.append(copy.deepcopy(body))
        else:
            raise AssertionError("Unexpected Jira mutation: " + path)
        return None


class PlanningTests(unittest.TestCase):
    def test_title_requires_exact_project_prefix(self):
        for title in ["KAN-9: Title", "KAN-123: Another title"]:
            self.assertIsNotNone(sync.ticket_key(pr(title=title)))
        for title in ["Fix KAN-9", "OTHER-9: Title", "KAN-0: Title", "KAN-09: Title", "KAN-9:", "KAN-9:x", "KAN-9 / Title", "KAN-9\n: Title"]:
            with self.subTest(title=title):
                self.assertIsNone(sync.ticket_key(pr(title=title)))

    def test_completion_marker_is_explicit_and_unambiguous(self):
        self.assertTrue(sync.completes_ticket(pr(body="Context\nCompletes-Jira: KAN-9\n"), "KAN-9"))
        for body in [
            None, "Mentions KAN-9", "Closes KAN-9", "Completes-Jira: KAN-8",
            "Completes-Jira: KAN-9, KAN-10", "Completes-Jira: KAN-9 extra",
            " Completes-Jira: KAN-9", "Completes-Jira: KAN-9 ",
            "> Completes-Jira: KAN-9", "Completes-Jira: KAN-9\nCompletes-Jira: KAN-9",
            "Completes-Jira: KAN-9\nCompletes-Jira: KAN-10",
            "```text\nCompletes-Jira: KAN-9\n```", "~~~\nCompletes-Jira: KAN-9\n~~~",
        ]:
            with self.subTest(body=body):
                self.assertFalse(sync.completes_ticket(pr(body=body), "KAN-9"))

    def test_ready_and_draft(self):
        self.assertEqual(sync.desired_status(pr(), []), "In Review")
        self.assertEqual(sync.desired_status(pr(draft=True), []), "In Progress")

    def test_only_explicit_merged_completion_is_done(self):
        self.assertEqual(sync.desired_status(pr(state="closed", merged=True, body="Completes-Jira: KAN-9"), []), "Done")
        self.assertIsNone(sync.desired_status(pr(state="closed", merged=True), []))
        self.assertEqual(sync.desired_status(pr(state="closed", body="Completes-Jira: KAN-9"), []), "In Progress")

    def test_other_open_prs_take_precedence(self):
        closed = pr(state="closed", merged=True, body="Completes-Jira: KAN-9")
        self.assertEqual(sync.desired_status(closed, [pr(10)]), "In Review")
        self.assertEqual(sync.desired_status(closed, [pr(10, draft=True)]), "In Progress")
        self.assertEqual(sync.desired_status(pr(draft=True), [pr(10)]), "In Review")
        self.assertEqual(sync.desired_status(pr(draft=True), [pr(10, title="KAN-10: Other")]), "In Progress")

    def test_irrelevant_or_foreign_prs_are_ignored(self):
        cases = [
            pr(title="No ticket"),
            pr(base={"ref": "develop", "repo": {"full_name": sync.REPOSITORY}}),
            pr(head={"repo": {"full_name": "outsider/fork"}}),
            pr(base={"ref": "main", "repo": {"full_name": "other/repo"}}),
        ]
        for candidate in cases:
            self.assertIsNone(sync.desired_status(candidate, []))
        # A foreign PR must not block a legitimate completion either.
        merged = pr(state="closed", merged=True, body="Completes-Jira: KAN-9")
        self.assertEqual(sync.desired_status(merged, [pr(10, head={"repo": {"full_name": "outsider/fork"}})]), "Done")

    def test_preserve_completed_and_custom_states(self):
        for target in ["In Progress", "In Review", None]:
            self.assertIsNone(sync.eligible_target(issue("Done", "done"), target))
        self.assertEqual(sync.eligible_target(issue("Done", "done"), "Done"), "Done")
        self.assertIsNone(sync.eligible_target(issue("Closed", "done"), "Done"))
        self.assertIsNone(sync.eligible_target(issue("Blocked"), "In Review"))
        self.assertIsNone(sync.eligible_target(issue("To Do"), "In Progress", may_start=False))
        self.assertEqual(sync.eligible_target(issue("To Do"), "In Progress"), "In Progress")
        with self.assertRaises(sync.SyncError):
            sync.eligible_target(issue(project="OTHER"), "Done")

    def test_transition_uses_destination_not_transition_name(self):
        options = [{"id": "99", "name": "Submit for review", "to": {"name": "In Review"}}]
        self.assertEqual(sync.transition_id(options, "In Review"), "99")
        for transitions in [[], options * 2, [{**options[0], "fields": {"reason": {"required": True}}}]]:
            with self.assertRaises(sync.SyncError):
                sync.transition_id(transitions, "In Review")


class ReconciliationTests(unittest.TestCase):
    def test_ready_pr_updates_and_comments(self):
        github, jira = FakeGitHub(), FakeJira()
        result = sync.sync(github, jira, 9)
        self.assertEqual(result["target"], "In Review")
        self.assertEqual(len(jira.writes), 2)
        self.assertEqual(jira.writes[0][1], {"transition": {"id": "31"}})
        self.assertTrue(sync.contains_text(jira.comments, "https://github.com/" + sync.REPOSITORY + "/pull/9"))

    def test_duplicate_deliveries_do_not_duplicate_writes(self):
        github, jira = FakeGitHub(), FakeJira()
        sync.sync(github, jira, 9)
        jira.writes.clear()
        self.assertEqual(sync.sync(github, jira, 9)["result"], "unchanged")
        self.assertEqual(jira.writes, [])

    def test_dry_run_checks_all_reads_but_never_writes(self):
        github, jira = FakeGitHub(), FakeJira()
        result = sync.sync(github, jira, 9, dry_run=True)
        self.assertEqual(result["result"], "preview")
        self.assertEqual(result["target"], "In Review")
        self.assertEqual(jira.writes, [])
        self.assertEqual(len(jira.reads), 3)

    def test_draft_moves_review_back_but_other_ready_pr_prevents_regression(self):
        jira = FakeJira(issue("In Review"))
        sync.sync(FakeGitHub(pr(draft=True)), jira, 9)
        self.assertEqual(jira.issue["fields"]["status"]["name"], "In Progress")
        jira = FakeJira(issue("In Review"))
        sync.sync(FakeGitHub(pr(draft=True), [pr(10)]), jira, 9)
        self.assertEqual(jira.issue["fields"]["status"]["name"], "In Review")
        self.assertFalse(any(path.endswith("/transitions") for path, _ in jira.writes))

    def test_draft_starts_to_do_ticket(self):
        jira = FakeJira(issue("To Do", "new"))
        sync.sync(FakeGitHub(pr(draft=True)), jira, 9)
        self.assertEqual(jira.issue["fields"]["status"]["name"], "In Progress")

    def test_closed_unmerged_preserves_to_do_and_never_finishes(self):
        for status in ["To Do", "In Progress", "In Review"]:
            jira = FakeJira(issue(status))
            sync.sync(FakeGitHub(pr(state="closed", body="Completes-Jira: KAN-9")), jira, 9)
            self.assertNotEqual(jira.issue["fields"]["status"]["name"], "Done")
            if status == "To Do":
                self.assertEqual(jira.writes, [])

    def test_merged_completion_and_retry_after_comment_failure(self):
        github = FakeGitHub(pr(state="closed", merged=True, body="Completes-Jira: KAN-9"))
        jira = FakeJira(issue("In Review"))
        jira.fail_comment_once = True
        with self.assertRaises(sync.SyncError):
            sync.sync(github, jira, 9)
        self.assertEqual(jira.issue["fields"]["status"]["name"], "Done")
        jira.writes.clear()
        sync.sync(github, jira, 9)
        self.assertEqual(len(jira.writes), 1)
        self.assertTrue(jira.writes[0][0].endswith("/comment"))
        jira.writes.clear()
        self.assertEqual(sync.sync(github, jira, 9)["result"], "unchanged")
        self.assertEqual(jira.writes, [])

    def test_unexpected_transition_result_is_not_reported_as_success(self):
        jira = FakeJira()
        jira.ignore_transition = True
        with self.assertRaisesRegex(sync.SyncError, "did not reach"):
            sync.sync(FakeGitHub(), jira, 9)
        self.assertEqual(jira.comments, [])

    def test_partial_merge_never_finishes_ticket(self):
        jira = FakeJira(issue("In Review"))
        result = sync.sync(FakeGitHub(pr(state="closed", merged=True)), jira, 9)
        self.assertIsNone(result["target"])
        self.assertEqual(jira.writes, [])

    def test_other_open_pr_blocks_completion(self):
        github = FakeGitHub(pr(state="closed", merged=True, body="Completes-Jira: KAN-9"), [pr(10)])
        jira = FakeJira(issue("In Review"))
        self.assertEqual(sync.sync(github, jira, 9)["target"], "In Review")
        self.assertFalse(any(path.endswith("/transitions") for path, _ in jira.writes))

    def test_done_ticket_is_not_reopened(self):
        jira = FakeJira(issue("Done", "done"))
        self.assertEqual(sync.sync(FakeGitHub(), jira, 9)["result"], "skipped")
        self.assertEqual(jira.writes, [])

    def test_malformed_or_fork_pr_does_not_touch_jira(self):
        for current in [pr(title="No ticket"), pr(head={"repo": None})]:
            jira = FakeJira()
            self.assertEqual(sync.sync(FakeGitHub(current), jira, 9)["result"], "skipped")
            self.assertEqual(jira.reads + jira.writes, [])

    def test_concurrent_github_changes_fail_closed(self):
        for change in ["change_pr_on_recheck", "change_others_on_recheck"]:
            github, jira = FakeGitHub(), FakeJira()
            setattr(github, change, True)
            with self.assertRaisesRegex(sync.SyncError, "PR state changed"):
                sync.sync(github, jira, 9)
            self.assertEqual(jira.writes, [])

    def test_concurrent_jira_changes_fail_closed(self):
        jira = FakeJira()
        jira.change_on_recheck = True
        with self.assertRaisesRegex(sync.SyncError, "Jira state changed"):
            sync.sync(FakeGitHub(), jira, 9)
        self.assertEqual(jira.writes, [])

    def test_missing_transition_fails_before_comment(self):
        jira = FakeJira()
        jira.transitions = []
        with self.assertRaises(sync.SyncError):
            sync.sync(FakeGitHub(), jira, 9)
        self.assertEqual(jira.writes, [])

    def test_pagination_is_not_silently_truncated(self):
        github = Mock()
        github.request.side_effect = [[pr(i) for i in range(100)], [pr(101)]]
        self.assertEqual(len(sync.list_open_prs(github)), 101)
        jira = Mock()
        jira.request.side_effect = [
            {"comments": [{"body": "unrelated"}], "total": 2},
            {"comments": [{"body": "marker"}], "total": 2},
        ]
        self.assertTrue(sync.comments_contain(jira, "KAN-9", "marker"))
        jira.request.side_effect = [{"comments": [], "total": 1}]
        with self.assertRaises(sync.SyncError):
            sync.comments_contain(jira, "KAN-9", "marker")


class ConfigurationAndHTTPTests(unittest.TestCase):
    def test_event_allowlist_and_manual_preview(self):
        event = {"repository": {"full_name": sync.REPOSITORY}, "number": 9}
        for action in sync.EVENT_ACTIONS:
            self.assertEqual(sync.event_number("pull_request_target", {**event, "action": action}), (9, False))
        self.assertEqual(sync.event_number("workflow_dispatch", {**event, "inputs": {"pr_number": "9", "dry_run": "false"}}), (9, True))
        for name, candidate in [
            ("pull_request", {**event, "action": "opened"}),
            ("pull_request_target", {**event, "action": "unknown"}),
            ("pull_request_target", {**event, "action": "opened", "repository": {"full_name": "other/repo"}}),
            ("workflow_dispatch", {**event, "inputs": {"pr_number": "9; echo unsafe"}}),
        ]:
            with self.assertRaises(sync.SyncError):
                sync.event_number(name, candidate)

    def test_credentials_use_scoped_gateway_and_fixed_hosts(self):
        env = {
            "GITHUB_TOKEN": "not-a-real-github-token", "JIRA_EMAIL": "automation@example.com",
            "JIRA_API_TOKEN": "not-a-real-jira-token", "JIRA_BASE_URL": sync.JIRA_SITE,
            "JIRA_CLOUD_ID": "9dc905e8-9878-4f15-a9bf-6510ec753f4b",
        }
        github, jira = sync.clients(env)
        self.assertEqual(github.base_url, "https://api.github.com")
        self.assertEqual(jira.base_url, "https://api.atlassian.com/ex/jira/" + env["JIRA_CLOUD_ID"])
        self.assertTrue(jira.authorization.startswith("Basic "))
        for key in env:
            with self.subTest(missing=key), self.assertRaises(sync.SyncError):
                sync.clients({k: v for k, v in env.items() if k != key})
        for key, value in [("JIRA_BASE_URL", "https://evil.example"), ("JIRA_CLOUD_ID", "../../other")]:
            with self.assertRaises(sync.SyncError):
                sync.clients({**env, key: value})

    def test_http_errors_hide_response_bodies_and_credentials(self):
        api = sync.API("https://api.atlassian.com", "secret-authorization", "Jira")
        for code in [301, 401, 403, 404, 429, 500]:
            api.opener = Mock()
            api.opener.open.side_effect = urllib.error.HTTPError(
                api.base_url, code, "contains-secret", {}, io.BytesIO(b"private-error-body")
            )
            with patch.object(sync.time, "sleep"), self.assertRaises(sync.SyncError) as caught:
                api.request("GET", "/test")
            message = str(caught.exception)
            self.assertIn(str(code), message)
            self.assertNotIn("contains-secret", message)
            self.assertNotIn("private-error-body", message)
            self.assertNotIn("secret-authorization", message)
            self.assertEqual(api.opener.open.call_count, 3 if code in [429, 500] else 1)

    def test_writes_are_never_automatically_retried(self):
        api = sync.API("https://api.atlassian.com", "secret", "Jira")
        api.opener = Mock()
        api.opener.open.side_effect = urllib.error.HTTPError(api.base_url, 500, "error", {}, io.BytesIO())
        with self.assertRaises(sync.SyncError):
            api.request("POST", "/test", {"value": "body"})
        self.assertEqual(api.opener.open.call_count, 1)

    def test_network_errors_are_sanitized(self):
        api = sync.API("https://api.atlassian.com", "secret", "Jira")
        api.opener = Mock()
        api.opener.open.side_effect = urllib.error.URLError("private-details")
        with self.assertRaises(sync.SyncError) as caught:
            api.request("GET", "/test")
        self.assertNotIn("private-details", str(caught.exception))

    def test_redirects_are_refused(self):
        self.assertIsNone(sync.NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://evil.example"))

    def test_workflow_keeps_secrets_separate_from_pr_code(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/jira-pr-sync.yml").read_text()
        checks = (root / ".github/workflows/automation-tests.yml").read_text()
        self.assertIn("pull_request_target:", workflow)
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("queue: max", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertNotIn("github.event.pull_request.head.sha", workflow)
        self.assertNotIn("secrets.", checks)
        self.assertIn("contents: read", checks)
        self.assertNotIn("pull_request_target:", checks)


if __name__ == "__main__":
    unittest.main()
