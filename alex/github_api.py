"""Small GitHub REST client (stdlib only)."""
import json
import time
import urllib.error
import urllib.request
from typing import List, Optional


class GitHubError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"GitHub API {status}: {message}")
        self.status = status


class GitHub:
    def __init__(self, token: str, repo: str, api: str = "https://api.github.com"):
        self.token = token
        self.repo = repo
        self.api = api.rstrip("/")

    def request(self, method: str, path: str, payload: Optional[dict] = None, accept: str = "application/vnd.github+json"):
        url = path if path.startswith("http") else f"{self.api}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        for attempt in range(3):
            req = urllib.request.Request(url, data=data, method=method)
            req.add_header("Authorization", f"Bearer {self.token}")
            req.add_header("Accept", accept)
            req.add_header("X-GitHub-Api-Version", "2022-11-28")
            if data is not None:
                req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = resp.read().decode("utf-8")
                    return json.loads(raw) if raw and accept.endswith("json") else raw
            except urllib.error.HTTPError as err:
                detail = err.read().decode("utf-8", "replace")[:500]
                if err.code in (502, 503, 504) or (err.code == 403 and "rate limit" in detail.lower()):
                    time.sleep(5 * (attempt + 1))
                    continue
                raise GitHubError(err.code, detail)
        raise GitHubError(0, f"gave up on {method} {path}")

    def paginate(self, path: str) -> List[dict]:
        items, page = [], 1
        sep = "&" if "?" in path else "?"
        while True:
            batch = self.request("GET", f"{path}{sep}per_page=100&page={page}")
            if not batch:
                return items
            items.extend(batch)
            if len(batch) < 100:
                return items
            page += 1

    # Pull requests
    def pr(self, number: int) -> dict:
        return self.request("GET", f"/repos/{self.repo}/pulls/{number}")

    def pr_diff(self, number: int) -> str:
        return self.request("GET", f"/repos/{self.repo}/pulls/{number}", accept="application/vnd.github.v3.diff")

    def commit(self, sha: str) -> dict:
        return self.request("GET", f"/repos/{self.repo}/commits/{sha}")

    def review_comments(self, number: int) -> List[dict]:
        return self.paginate(f"/repos/{self.repo}/pulls/{number}/comments")

    def create_review(self, number: int, commit_id: str, comments: List[dict]) -> dict:
        return self.request("POST", f"/repos/{self.repo}/pulls/{number}/reviews",
                            {"commit_id": commit_id, "event": "COMMENT", "comments": comments})

    def create_review_comment(self, number: int, commit_id: str, comment: dict) -> dict:
        payload = dict(comment, commit_id=commit_id)
        return self.request("POST", f"/repos/{self.repo}/pulls/{number}/comments", payload)

    # Issue comments and reactions
    def issue_comments(self, number: int) -> List[dict]:
        return self.paginate(f"/repos/{self.repo}/issues/{number}/comments")

    def create_issue_comment(self, number: int, body: str) -> dict:
        return self.request("POST", f"/repos/{self.repo}/issues/{number}/comments", {"body": body})

    def update_issue_comment(self, comment_id: int, body: str) -> dict:
        return self.request("PATCH", f"/repos/{self.repo}/issues/comments/{comment_id}", {"body": body})

    def react_issue(self, number: int, content: str) -> None:
        self.request("POST", f"/repos/{self.repo}/issues/{number}/reactions", {"content": content})

    def react_comment(self, comment_id: int, content: str) -> None:
        self.request("POST", f"/repos/{self.repo}/issues/comments/{comment_id}/reactions", {"content": content})

    # Status
    def set_status(self, sha: str, state: str, description: str, target_url: str = "", context: str = "Alex review") -> None:
        payload = {"state": state, "description": description[:140], "context": context}
        if target_url:
            payload["target_url"] = target_url
        self.request("POST", f"/repos/{self.repo}/statuses/{sha}", payload)
