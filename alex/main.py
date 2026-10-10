"""Alex entry point.

  python -m alex.main review    run inside GitHub Actions (see action.yml)
  python -m alex.main preview   render a card locally from saved engine output, no GitHub calls
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from . import card as cardmod
from . import diff as diffmod
from . import inline, llm, scoring
from .findings import Finding, from_engine
from .github_api import GitHub, GitHubError

TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}
DEFAULT_LLM_URL = "https://api.fireworks.ai/inference/v1"


def log(msg: str) -> None:
    print(f"[alex] {msg}", flush=True)


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# Engine ---------------------------------------------------------------------

def run_engine(base: str, head: str, budget: int, timeout_min: int) -> dict:
    cmd = env("ALEX_ENGINE_CMD", "ocr")
    out = Path(tempfile.mkdtemp()) / "engine.json"
    args = [cmd, "review", "--from", base, "--to", head, "--format", "json", "--audience", "agent",
            "--output", str(out), "--timeout", str(timeout_min)]
    if budget > 0:
        args += ["--max-tokens-budget", str(budget)]
    log(f"engine: reviewing {base[:7]}..{head[:7]}")
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout_min * 60 + 300)
    if not out.exists():
        tail = (proc.stderr or proc.stdout or "")[-600:]
        raise RuntimeError(f"engine produced no result (exit {proc.returncode}): {tail}")
    result = json.loads(out.read_text(encoding="utf-8"))
    summary = result.get("summary", {})
    log(f"engine: {result.get('status')} | {summary.get('comments')} finding(s) | "
        f"{summary.get('total_tokens')} tokens | {summary.get('elapsed')}")
    return result


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


# Card -----------------------------------------------------------------------

def build_card(title: str, body: str, diff_text: str, findings: List[Finding]) -> cardmod.CardData:
    key = env("ALEX_LLM_KEY")
    model = env("ALEX_CARD_MODEL") or env("ALEX_MODEL")
    raw = None
    if key and model:
        try:
            resp = llm.chat(cardmod.build_messages(title, body, diff_text, findings),
                            url=env("ALEX_LLM_URL", DEFAULT_LLM_URL), api_key=key, model=model)
            raw = llm.parse_json(resp["content"])
            if raw is None:
                log("card: model reply was not JSON, using fallback card")
        except llm.LLMError as err:
            log(f"card: model call failed ({err}), using fallback card")
    card = cardmod.normalize(raw, findings)
    cardmod.apply_titles(card, findings)
    return card


# GitHub review ----------------------------------------------------------------

def load_event() -> dict:
    path = env("GITHUB_EVENT_PATH")
    return json.loads(Path(path).read_text(encoding="utf-8")) if path and Path(path).exists() else {}


def find_card(comments: List[dict]) -> Optional[dict]:
    for c in comments:
        if cardmod.SUMMARY_MARKER in (c.get("body") or "") and (c.get("user") or {}).get("type") == "Bot":
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


def review() -> int:
    event = load_event()
    trigger_comment = None
    if "comment" in event:
        comment = event["comment"]
        if not (event.get("issue") or {}).get("pull_request"):
            log("comment is not on a pull request, skipping")
            return 0
        if not (comment.get("body") or "").strip().lower().startswith("/alex"):
            log("comment does not start with /alex, skipping")
            return 0
        if comment.get("author_association") not in TRUSTED:
            log("comment author is not trusted, skipping")
            return 0
        trigger_comment = comment["id"]
        number = int(event["issue"]["number"])
    else:
        number = int(env("ALEX_PR_NUMBER") or event.get("pull_request", {}).get("number") or 0)
    if not number:
        log("no pull request number found")
        return 1

    gh = GitHub(env("ALEX_GITHUB_TOKEN") or env("GITHUB_TOKEN"), env("GITHUB_REPOSITORY"))
    pr = gh.pr(number)
    if pr.get("state") != "open":
        log("pull request is not open, skipping")
        return 0
    if pr.get("draft") and trigger_comment is None:
        log("draft pull request, skipping (comment /alex to review it)")
        return 0
    if trigger_comment is None and pr.get("author_association") not in TRUSTED:
        log("pull request author is not trusted, skipping")
        return 0

    head, base = pr["head"]["sha"], pr["base"]["sha"]
    run_url = env("ALEX_RUN_URL")
    react = (lambda c: gh.react_comment(trigger_comment, c)) if trigger_comment else (lambda c: gh.react_issue(number, c))
    _safe(react, "eyes")
    _safe(gh.set_status, head, "pending", "Alex is reviewing", run_url)

    comments = gh.issue_comments(number)
    existing_card = find_card(comments)
    previous = cardmod.read_meta(existing_card["body"]) if existing_card else {}

    try:
        diff_text = gh.pr_diff(number)
        merge_base = git("merge-base", base, head)
        result = run_engine(merge_base, head, int(env("ALEX_TOKEN_BUDGET") or 0), int(env("ALEX_TIMEOUT_MINUTES") or 20))
        if result.get("status") not in ("complete", "partial", "skipped"):
            raise RuntimeError(f"engine status {result.get('status')}: {result.get('message')}")

        findings = from_engine(result, diffmod.commentable_lines(diff_text))
        card = build_card(pr.get("title", ""), pr.get("body") or "", diff_text, findings)

        already = inline.existing_fingerprints(gh.review_comments(number))
        post_inline(gh, number, head, inline.to_post(findings, set(already)))
        urls = inline.existing_fingerprints(gh.review_comments(number))
        for f in findings:
            f.url = urls.get(f.fingerprint, "")

        commit = gh.commit(head)
        body = cardmod.render(card, findings, diff_text=diff_text,
                              review_count=int(previous.get("reviews", 0)) + 1,
                              head_sha=head, head_message=commit.get("commit", {}).get("message", ""),
                              commit_url=commit.get("html_url", ""))
        if existing_card:
            gh.update_issue_comment(existing_card["id"], body)
        else:
            gh.create_issue_comment(number, body)

        priorities = [f.priority for f in findings]
        counts = ", ".join(f"{priorities.count(p)} {p}" for p in ("P0", "P1", "P2") if priorities.count(p)) or "no issues"
        failing = "P0" in priorities and env("ALEX_FAIL_ON_P0", "true").lower() == "true"
        gh.set_status(head, "failure" if failing else "success", f"Confidence {card.score}/5 \u00b7 {counts}", run_url)
        _safe(react, "+1")
        log(f"done: confidence {card.score}/5, {counts}")
        return 0
    except Exception as err:  # noqa: BLE001 - report every failure on the PR, then fail the job
        log(f"review failed: {err}")
        note = (f"{cardmod.SUMMARY_MARKER}\n## Alex review\n\nAlex could not finish this review. "
                f"Comment `/alex` to retry.\n\n<sub>{type(err).__name__}</sub>")
        if previous:
            note += f"\n{cardmod.META_PREFIX} {json.dumps(previous)} -->"
        _safe(gh.update_issue_comment, existing_card["id"], note) if existing_card else _safe(gh.create_issue_comment, number, note)
        _safe(gh.set_status, head, "error", "Alex review failed", run_url)
        _safe(react, "confused")
        return 1


def _safe(fn, *args) -> None:
    try:
        fn(*args)
    except Exception as err:  # noqa: BLE001 - reactions and statuses are best effort
        log(f"warning: {getattr(fn, '__name__', 'call')} failed: {err}")


# Local preview ----------------------------------------------------------------

def preview(args) -> int:
    result = json.loads(Path(args.ocr_json).read_text(encoding="utf-8"))
    diff_text = Path(args.diff).read_text(encoding="utf-8")
    findings = from_engine(result, diffmod.commentable_lines(diff_text))
    if args.no_llm:
        card = cardmod.normalize(None, findings)
        cardmod.apply_titles(card, findings)
    else:
        card = build_card(args.title, args.body, diff_text, findings)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    md = cardmod.render(card, findings, diff_text=diff_text, review_count=1,
                        head_sha=args.head or "0000000", head_message=args.title, commit_url="")
    (out / "card.md").write_text(md, encoding="utf-8")
    inline_payloads = [inline.review_comment(f) for f in findings if f.placeable]
    (out / "inline.json").write_text(json.dumps(inline_payloads, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "inline.md").write_text("\n\n---\n\n".join(f"`{p['path']}:{p['line']}`\n\n{p['body']}" for p in inline_payloads),
                                   encoding="utf-8")
    log(f"card: model={'yes' if card.from_model else 'fallback'} score={card.score} diagram={card.diagram_type}")
    log(f"wrote {out / 'card.md'}, {out / 'inline.md'} ({len(inline_payloads)} inline, "
        f"{sum(1 for f in findings if not f.placeable)} on card only)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="alex")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("review")
    p = sub.add_parser("preview")
    p.add_argument("--ocr-json", required=True)
    p.add_argument("--diff", required=True)
    p.add_argument("--title", default="Preview")
    p.add_argument("--body", default="")
    p.add_argument("--head", default="")
    p.add_argument("--out", default="out")
    p.add_argument("--no-llm", action="store_true")
    args = parser.parse_args(argv)
    return review() if args.cmd == "review" else preview(args)


if __name__ == "__main__":
    sys.exit(main())
