"""The review flow shared by the GitHub Action and the hosted server."""
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from . import card as cardmod
from . import diff as diffmod
from . import inline, llm
from .findings import Finding, from_engine
from .github_api import GitHub, GitHubError

TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}
DEFAULT_LLM_URL = "https://api.fireworks.ai/inference/v1"


def log(msg: str) -> None:
    print(f"[alex] {msg}", flush=True)


@dataclass
class Settings:
    llm_url: str = DEFAULT_LLM_URL
    llm_key: str = ""
    model: str = ""
    card_model: str = ""
    token_budget: int = 1500000
    timeout_minutes: int = 20
    fail_on_p0: bool = True
    engine_cmd: str = "ocr"

    @classmethod
    def from_env(cls) -> "Settings":
        e = lambda k, d="": os.environ.get(k, d).strip()  # noqa: E731
        return cls(
            llm_url=e("ALEX_LLM_URL", DEFAULT_LLM_URL),
            llm_key=e("ALEX_LLM_KEY") or e("ALEX_LLM_API_KEY"),
            model=e("ALEX_MODEL") or "accounts/fireworks/models/deepseek-v4p1-flash",
            card_model=e("ALEX_CARD_MODEL"),
            token_budget=int(e("ALEX_TOKEN_BUDGET", "1500000") or 0),
            timeout_minutes=int(e("ALEX_TIMEOUT_MINUTES", "20") or 20),
            fail_on_p0=e("ALEX_FAIL_ON_P0", "true").lower() == "true",
            engine_cmd=e("ALEX_ENGINE_CMD", "ocr"),
        )

    def engine_env(self) -> dict:
        env = dict(os.environ)
        env.update({"OCR_LLM_URL": self.llm_url, "OCR_LLM_TOKEN": self.llm_key,
                    "OCR_LLM_MODEL": self.model, "OCR_USE_ANTHROPIC": "false"})
        return env


def git(*args: str, cwd: Optional[str] = None) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True, cwd=cwd).stdout.strip()


def run_engine(base: str, head: str, s: Settings, cwd: Optional[str] = None) -> dict:
    out = Path(tempfile.mkdtemp()) / "engine.json"
    args = [s.engine_cmd, "review", "--from", base, "--to", head, "--format", "json", "--audience", "agent",
            "--output", str(out), "--timeout", str(s.timeout_minutes)]
    if s.token_budget > 0:
        args += ["--max-tokens-budget", str(s.token_budget)]
    log(f"engine: reviewing {base[:7]}..{head[:7]}")
    proc = subprocess.run(args, capture_output=True, text=True, cwd=cwd, env=s.engine_env(),
                          timeout=s.timeout_minutes * 60 + 300)
    if not out.exists():
        tail = (proc.stderr or proc.stdout or "")[-600:]
        raise RuntimeError(f"engine produced no result (exit {proc.returncode}): {tail}")
    result = json.loads(out.read_text(encoding="utf-8"))
    summary = result.get("summary", {})
    log(f"engine: {result.get('status')} | {summary.get('comments')} finding(s) | "
        f"{summary.get('total_tokens')} tokens | {summary.get('elapsed')}")
    return result


def build_card(s: Settings, title: str, body: str, diff_text: str, findings: List[Finding]) -> cardmod.CardData:
    raw = None
    model = s.card_model or s.model
    if s.llm_key and model:
        try:
            resp = llm.chat(cardmod.build_messages(title, body, diff_text, findings),
                            url=s.llm_url, api_key=s.llm_key, model=model)
            raw = llm.parse_json(resp["content"])
            if raw is None:
                log("card: model reply was not JSON, using fallback card")
        except llm.LLMError as err:
            log(f"card: model call failed ({err}), using fallback card")
    card = cardmod.normalize(raw, findings)
    cardmod.apply_titles(card, findings)
    if findings and not card.diagram and s.llm_key and model:
        try:
            resp = llm.chat(cardmod.build_diagram_messages(title, diff_text, findings),
                            url=s.llm_url, api_key=s.llm_key, model=model, max_tokens=1500)
            if cardmod.apply_diagram(card, llm.parse_json(resp["content"])):
                log(f"card: diagram added on retry ({card.diagram_type})")
        except llm.LLMError as err:
            log(f"card: diagram retry failed ({err})")
    if card.diagram_rejected and not card.diagram:
        log("card: diagram dropped by the validator: " + card.diagram_rejected.replace("\n", " | "))
    return card


def find_card(comments: List[dict], bot_login: Optional[str] = None) -> Optional[dict]:
    for c in comments:
        user = c.get("user") or {}
        if cardmod.SUMMARY_MARKER not in (c.get("body") or ""):
            continue
        if bot_login and user.get("login") != bot_login:
            continue
        if user.get("type") == "Bot":
            return c
    return None


def post_inline(gh: GitHub, number: int, head: str, findings: List[Finding]) -> None:
    if not findings:
        return
    payloads = [inline.review_comment(f) for f in findings]
    try:
        gh.create_review(number, head, payloads)
        return
    except GitHubError as err:
        if err.status != 422:
            raise
        log("inline: batch rejected, posting one by one")
    for f, payload in zip(findings, payloads):
        try:
            gh.create_review_comment(number, head, payload)
        except GitHubError as err:
            log(f"inline: {f.location} not accepted ({err.status}), moving it to the card")
            f.anchor_start = f.anchor_end = None


def safe(fn: Callable, *args) -> None:
    try:
        fn(*args)
    except Exception as err:  # noqa: BLE001 - reactions and statuses are best effort
        log(f"warning: {getattr(fn, '__name__', 'call')} failed: {err}")


def review_pr(gh: GitHub, number: int, s: Settings, *, cwd: Optional[str] = None,
              trigger_comment_id: Optional[int] = None, bot_login: Optional[str] = None,
              run_url: str = "", pr: Optional[dict] = None) -> dict:
    """Review one open PR. The repo at `cwd` must already contain the base and head commits."""
    pr = pr or gh.pr(number)
    head, base = pr["head"]["sha"], pr["base"]["sha"]

    if trigger_comment_id:
        react = lambda c: gh.react_comment(trigger_comment_id, c)  # noqa: E731
    else:
        react = lambda c: gh.react_issue(number, c)  # noqa: E731
    safe(react, "eyes")
    safe(gh.set_status, head, "pending", "Alex is reviewing", run_url)

    existing = find_card(gh.issue_comments(number), bot_login)
    previous = cardmod.read_meta(existing["body"]) if existing else {}
    try:
        diff_text = gh.pr_diff(number)
        merge_base = git("merge-base", base, head, cwd=cwd)
        result = run_engine(merge_base, head, s, cwd=cwd)
        if result.get("status") not in ("complete", "partial", "skipped"):
            raise RuntimeError(f"engine status {result.get('status')}: {result.get('message')}")

        findings = from_engine(result, diffmod.commentable_lines(diff_text))
        card = build_card(s, pr.get("title", ""), pr.get("body") or "", diff_text, findings)

        already = inline.existing_fingerprints(gh.review_comments(number), bot_login or "")
        post_inline(gh, number, head, inline.to_post(findings, set(already)))
        urls = inline.existing_fingerprints(gh.review_comments(number), bot_login or "")
        for f in findings:
            f.url = urls.get(f.fingerprint, "")

        commit = gh.commit(head)
        body = cardmod.render(card, findings, diff_text=diff_text,
                              review_count=int(previous.get("reviews", 0)) + 1,
                              head_sha=head, head_message=commit.get("commit", {}).get("message", ""),
                              commit_url=commit.get("html_url", ""))
        if existing:
            gh.update_issue_comment(existing["id"], body)
        else:
            gh.create_issue_comment(number, body)

        priorities = [f.priority for f in findings]
        counts = ", ".join(f"{priorities.count(p)} {p}" for p in ("P0", "P1", "P2") if priorities.count(p)) or "no issues"
        failing = "P0" in priorities and s.fail_on_p0
        gh.set_status(head, "failure" if failing else "success", f"Confidence {card.score}/5 \u00b7 {counts}", run_url)
        safe(react, "+1")
        log(f"done: #{number} confidence {card.score}/5, {counts}")
        return {"ok": True, "score": card.score, "tokens": int(result.get("summary", {}).get("total_tokens") or 0)}
    except Exception as err:  # noqa: BLE001 - report every failure on the PR
        log(f"review failed: {err}")
        note = (f"{cardmod.SUMMARY_MARKER}\n## Alex review\n\nAlex could not finish this review. "
                f"Comment `/alex` to retry.\n\n<sub>{type(err).__name__}</sub>")
        if previous:
            note += f"\n{cardmod.META_PREFIX} {json.dumps(previous)} -->"
        if existing:
            safe(gh.update_issue_comment, existing["id"], note)
        else:
            safe(gh.create_issue_comment, number, note)
        safe(gh.set_status, head, "error", "Alex review failed", run_url)
        safe(react, "confused")
        return {"ok": False, "error": str(err), "tokens": 0}
