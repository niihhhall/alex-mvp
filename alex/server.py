"""Hosted Alex: GitHub App webhook server with an in-process review queue.

  python -m alex.server                          serve webhooks on $PORT (Render)
  python -m alex.server once --repo o/r --pr 12  review one PR now, as the app (local testing)
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional, Tuple

from . import card as cardmod
from .app_auth import AppAuth
from .github_api import GitHub
from .reviewer import TRUSTED, Settings, log, review_pr, safe

TRIGGERS = ("/alex", "@alexreview-ai")
PR_ACTIONS = {"opened", "reopened", "ready_for_review"}


@dataclass(frozen=True)
class Job:
    repo: str
    number: int
    installation_id: int
    comment_id: Optional[int] = None


# Webhook decisions (pure, unit tested) ------------------------------------------

def verify_signature(secret: str, body: bytes, header: str) -> bool:
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


def is_trigger(text: str) -> bool:
    return (text or "").strip().lower().startswith(TRIGGERS)


def decide(event: str, payload: dict, allowed_accounts: set, review_on_push: bool = False) -> Tuple[Optional[Job], str]:
    """Return (job, reason). job is None when the event should be ignored."""
    installation = payload.get("installation") or {}
    account = ((installation.get("account") or payload.get("repository", {}).get("owner")) or {}).get("login", "")
    if allowed_accounts and account.lower() not in allowed_accounts:
        return None, f"account {account or '?'} is not allowed"
    if not installation.get("id"):
        return None, "no installation"
    repo = (payload.get("repository") or {}).get("full_name", "")

    if event == "pull_request":
        actions = PR_ACTIONS | ({"synchronize"} if review_on_push else set())
        pr = payload.get("pull_request") or {}
        if payload.get("action") not in actions:
            return None, f"pull_request.{payload.get('action')} not reviewed"
        if pr.get("draft"):
            return None, "draft pull request"
        if pr.get("author_association") not in TRUSTED:
            return None, "pull request author is not trusted (comment /alex to review)"
        if (pr.get("user") or {}).get("type") == "Bot":
            return None, "pull request opened by a bot"
        return Job(repo, int(pr["number"]), int(installation["id"])), "review"

    if event == "issue_comment":
        comment = payload.get("comment") or {}
        issue = payload.get("issue") or {}
        if payload.get("action") != "created":
            return None, "comment not created"
        if not issue.get("pull_request"):
            return None, "comment is not on a pull request"
        if (comment.get("user") or {}).get("type") == "Bot":
            return None, "comment from a bot"
        if not is_trigger(comment.get("body", "")):
            return None, "not a trigger"
        if comment.get("author_association") not in TRUSTED:
            return None, "comment author is not trusted"
        return Job(repo, int(issue["number"]), int(installation["id"]), int(comment["id"])), "review"

    return None, f"event {event} ignored"


# Monthly budget ---------------------------------------------------------------------

class Usage:
    def __init__(self, path: Path, monthly_cap: int):
        self.path, self.cap = path, monthly_cap
        self.lock = threading.Lock()

    def _month(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def used(self) -> int:
        return int(self._load().get(self._month(), 0))

    def over_budget(self) -> bool:
        return self.cap > 0 and self.used() >= self.cap

    def add(self, tokens: int) -> None:
        with self.lock:
            data = self._load()
            month = self._month()
            data[month] = int(data.get(month, 0)) + int(tokens)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data), encoding="utf-8")


# Repo cache -------------------------------------------------------------------------

class Repos:
    def __init__(self, root: Path):
        self.root = root
        self.locks = {}
        self.guard = threading.Lock()

    def lock(self, repo: str) -> threading.Lock:
        with self.guard:
            return self.locks.setdefault(repo, threading.Lock())

    @staticmethod
    def _git(token: str, *args: str, cwd: Optional[Path] = None) -> None:
        auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        cmd = ["git", "-c", f"http.extraHeader=AUTHORIZATION: basic {auth}", *args]
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=1800)
        if proc.returncode != 0:
            raise RuntimeError(f"git {args[0]} failed: {proc.stderr.strip()[-300:]}")

    def prepare(self, repo: str, token: str, number: int, base_ref: str, base_sha: str) -> Path:
        path = self.root / repo.replace("/", "__")
        if not (path / ".git").exists():
            shutil.rmtree(path, ignore_errors=True)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._git(token, "clone", "--quiet", "--no-checkout", f"https://github.com/{repo}.git", str(path))
        self._git(token, "fetch", "--quiet", "--no-tags", "origin",
                  f"+refs/heads/{base_ref}:refs/remotes/origin/{base_ref}",
                  f"+refs/pull/{number}/head:refs/alex/pr/{number}", cwd=path)
        subprocess.run(["git", "checkout", "--quiet", "--force", "--detach", base_sha], cwd=path, check=True)
        subprocess.run(["git", "clean", "-fdxq"], cwd=path, check=True)
        return path


# Worker -----------------------------------------------------------------------------

class Alex:
    def __init__(self, auth: AppAuth, settings: Settings, data_dir: Path, monthly_cap: int):
        self.auth, self.settings = auth, settings
        self.repos = Repos(data_dir / "repos")
        self.usage = Usage(data_dir / "usage.json", monthly_cap)
        self.jobs: "queue.Queue[Job]" = queue.Queue()
        self.pending = set()
        self.pending_lock = threading.Lock()

    def submit(self, job: Job) -> bool:
        key = (job.repo, job.number)
        with self.pending_lock:
            if key in self.pending and job.comment_id is None:
                return False
            self.pending.add(key)
        self.jobs.put(job)
        return True

    def worker(self) -> None:
        while True:
            job = self.jobs.get()
            try:
                self.run(job)
            except Exception as err:  # noqa: BLE001 - one bad job must not kill the worker
                log(f"job {job.repo}#{job.number} crashed: {err}")
            finally:
                with self.pending_lock:
                    self.pending.discard((job.repo, job.number))
                self.jobs.task_done()

    def run(self, job: Job) -> None:
        log(f"job: {job.repo}#{job.number}" + (" (comment)" if job.comment_id else ""))
        token = self.auth.installation_token(job.installation_id)
        gh = GitHub(token, job.repo)
        pr = gh.pr(job.number)
        if pr.get("state") != "open":
            log("pull request is not open, skipping")
            return
        if self.usage.over_budget():
            log("monthly budget reached")
            body = (f"{cardmod.SUMMARY_MARKER}\n## Alex review\n\nThe monthly review budget is used up, "
                    f"so Alex skipped this review. It resets next month.")
            safe(gh.create_issue_comment, job.number, body)
            safe(gh.set_status, pr["head"]["sha"], "error", "Alex review skipped: monthly budget reached")
            return
        with self.repos.lock(job.repo):
            path = self.repos.prepare(job.repo, token, job.number, pr["base"]["ref"], pr["base"]["sha"])
            result = review_pr(gh, job.number, self.settings, cwd=str(path), trigger_comment_id=job.comment_id,
                               bot_login=self.auth.bot_login(), pr=pr)
        self.usage.add(result.get("tokens", 0))


# HTTP -------------------------------------------------------------------------------

def make_handler(alex: Alex, secret: str, allowed: set, review_on_push: bool):
    seen = deque(maxlen=2000)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quiet default access log
            return

        def _send(self, code: int, text: str) -> None:
            data = text.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path in ("/", "/healthz"):
                self._send(200, f"ok, queued={alex.jobs.qsize()}")
            else:
                self._send(404, "not found")

        def do_POST(self):
            if self.path not in ("/webhook", "/alex"):
                return self._send(404, "not found")
            length = int(self.headers.get("Content-Length") or 0)
            if length > 25 * 1024 * 1024:
                return self._send(413, "too large")
            body = self.rfile.read(length)
            if not verify_signature(secret, body, self.headers.get("X-Hub-Signature-256", "")):
                log("rejected webhook with a bad signature")
                return self._send(401, "bad signature")
            delivery = self.headers.get("X-GitHub-Delivery", "")
            if delivery and delivery in seen:
                return self._send(200, "duplicate")
            seen.append(delivery)
            event = self.headers.get("X-GitHub-Event", "")
            if event == "ping":
                return self._send(200, "pong")
            try:
                payload = json.loads(body)
            except ValueError:
                return self._send(400, "bad json")
            job, reason = decide(event, payload, allowed, review_on_push)
            if not job:
                return self._send(200, f"ignored: {reason}")
            queued = alex.submit(job)
            log(f"webhook: {event} {job.repo}#{job.number} -> {'queued' if queued else 'already queued'}")
            self._send(202, "queued" if queued else "already queued")

    return Handler


def build_alex() -> Tuple[Alex, set]:
    e = lambda k, d="": os.environ.get(k, d).strip()  # noqa: E731
    key = e("ALEX_APP_PRIVATE_KEY")
    if not key and e("ALEX_APP_PRIVATE_KEY_FILE"):
        key = Path(e("ALEX_APP_PRIVATE_KEY_FILE")).read_text(encoding="utf-8")
    missing = [n for n, v in (("ALEX_APP_ID", e("ALEX_APP_ID")), ("ALEX_APP_PRIVATE_KEY", key),
                              ("ALEX_LLM_API_KEY", e("ALEX_LLM_API_KEY") or e("ALEX_LLM_KEY"))) if not v]
    if missing:
        raise SystemExit(f"missing settings: {', '.join(missing)}")
    allowed = {a.strip().lower() for a in e("ALEX_ALLOWED_ACCOUNTS").split(",") if a.strip()}
    if not allowed:
        raise SystemExit("ALEX_ALLOWED_ACCOUNTS must list the GitHub accounts Alex may serve")
    alex = Alex(AppAuth(e("ALEX_APP_ID"), key), Settings.from_env(),
                Path(e("ALEX_DATA_DIR", "/tmp/alex")), int(e("ALEX_MONTHLY_TOKEN_BUDGET", "0") or 0))
    return alex, allowed


def serve() -> int:
    secret = os.environ.get("ALEX_WEBHOOK_SECRET", "").strip()
    if len(secret) < 20:
        raise SystemExit("ALEX_WEBHOOK_SECRET must be set (at least 20 characters)")
    alex, allowed = build_alex()
    log(f"bot: {alex.auth.bot_login()} | accounts: {', '.join(sorted(allowed))} | model: {alex.settings.model}")
    for _ in range(max(1, int(os.environ.get("ALEX_WORKERS", "1")))):
        threading.Thread(target=alex.worker, daemon=True).start()
    on_push = os.environ.get("ALEX_REVIEW_ON_PUSH", "false").lower() == "true"
    port = int(os.environ.get("PORT", "8080"))
    httpd = ThreadingHTTPServer(("0.0.0.0", port), make_handler(alex, secret, allowed, on_push))
    log(f"listening on :{port}")
    httpd.serve_forever()
    return 0


def once(repo: str, number: int, comment_id: Optional[int]) -> int:
    alex, allowed = build_alex()
    if repo.split("/")[0].lower() not in allowed:
        raise SystemExit(f"{repo} is not in ALEX_ALLOWED_ACCOUNTS")
    job = Job(repo, number, alex.auth.installation_for_repo(repo), comment_id)
    started = time.time()
    alex.run(job)
    log(f"finished in {time.time() - started:.0f}s, month usage {alex.usage.used():,} tokens")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="alex.server")
    sub = parser.add_subparsers(dest="cmd")
    o = sub.add_parser("once")
    o.add_argument("--repo", required=True)
    o.add_argument("--pr", type=int, required=True)
    o.add_argument("--comment-id", type=int)
    args = parser.parse_args(argv)
    return once(args.repo, args.pr, args.comment_id) if args.cmd == "once" else serve()


if __name__ == "__main__":
    sys.exit(main())
