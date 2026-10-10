"""Alex entry point.

  python -m alex.main review    run inside GitHub Actions (see action.yml)
  python -m alex.main preview   render a card locally from saved engine output, no GitHub calls
  python -m alex.server         run the hosted webhook server (see render.yaml)
"""
import argparse
import json
import os
import sys
from pathlib import Path

from . import card as cardmod
from . import diff as diffmod
from . import inline
from .findings import from_engine
from .github_api import GitHub
from .reviewer import TRUSTED, Settings, build_card, log, review_pr


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def load_event() -> dict:
    path = env("GITHUB_EVENT_PATH")
    return json.loads(Path(path).read_text(encoding="utf-8")) if path and Path(path).exists() else {}


def review() -> int:
    """GitHub Action mode: the workflow already checked out base and fetched the PR head."""
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
        if comment.get("author_association") not in TRUSTED or (comment.get("user") or {}).get("type") == "Bot":
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

    result = review_pr(gh, number, Settings.from_env(), trigger_comment_id=trigger_comment,
                       run_url=env("ALEX_RUN_URL"), pr=pr)
    return 0 if result["ok"] else 1


def preview(args) -> int:
    result = json.loads(Path(args.ocr_json).read_text(encoding="utf-8"))
    diff_text = Path(args.diff).read_text(encoding="utf-8")
    findings = from_engine(result, diffmod.commentable_lines(diff_text))
    if args.no_llm:
        card = cardmod.normalize(None, findings)
        cardmod.apply_titles(card, findings)
    else:
        card = build_card(Settings.from_env(), args.title, args.body, diff_text, findings)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    md = cardmod.render(card, findings, diff_text=diff_text, review_count=1,
                        head_sha=args.head or "0000000", head_message=args.title, commit_url="")
    (out / "card.md").write_text(md, encoding="utf-8")
    payloads = [inline.review_comment(f) for f in findings if f.placeable]
    (out / "inline.json").write_text(json.dumps(payloads, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "inline.md").write_text("\n\n---\n\n".join(f"`{p['path']}:{p['line']}`\n\n{p['body']}" for p in payloads),
                                   encoding="utf-8")
    log(f"card: model={'yes' if card.from_model else 'fallback'} score={card.score} diagram={card.diagram_type}")
    log(f"wrote {out / 'card.md'}, {out / 'inline.md'} ({len(payloads)} inline, "
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
