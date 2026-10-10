"""Inline review comment bodies."""
import re
from typing import List, Set

from . import scoring, text
from .findings import Finding, suggestion_applies

FINDING_MARKER = re.compile(r"<!-- alex-finding:([0-9a-f]{12}) -->")


def body(f: Finding) -> str:
    parts = [f"{scoring.BADGE[f.priority]} \u00b7 **{f.title}**", "", f.content]
    if suggestion_applies(f):
        parts += ["", "```suggestion", f.suggestion, "```"]
    parts += ["", f"<sub>Alex \u00b7 {f.category}</sub>", f"<!-- alex-finding:{f.fingerprint} -->"]
    return text.clean("\n".join(parts))


def review_comment(f: Finding) -> dict:
    payload = {"path": f.path, "line": f.anchor_end, "side": "RIGHT", "body": body(f)}
    if f.anchor_start and f.anchor_start != f.anchor_end:
        payload["start_line"] = f.anchor_start
        payload["start_side"] = "RIGHT"
    return payload


def existing_fingerprints(comments: List[dict], bot_login: str = "") -> dict:
    """fingerprint -> html_url for Alex comments already on the PR (only this bot's, when given)."""
    found = {}
    for c in comments:
        if bot_login and (c.get("user") or {}).get("login") != bot_login:
            continue
        m = FINDING_MARKER.search(c.get("body") or "")
        if m:
            found[m.group(1)] = c.get("html_url", "")
    return found


def to_post(findings: List[Finding], already: Set[str]) -> List[Finding]:
    return [f for f in findings if f.placeable and f.fingerprint not in already]
