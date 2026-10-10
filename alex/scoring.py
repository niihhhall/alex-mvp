"""Severity badges and the confidence score caps from docs/design-system.md."""
from typing import Iterable

BADGE = {"P0": "\U0001F534 **P0**", "P1": "\U0001F7E0 **P1**", "P2": "\U0001F7E1 **P2**"}
_SERIOUS_CATEGORIES = {"bug", "security", "performance", "concurrency", "data", "correctness", "logic"}
_RANK = {"P0": 0, "P1": 1, "P2": 2}


def priority(severity: str, category: str = "") -> str:
    sev = (severity or "").strip().lower()
    cat = (category or "").strip().lower()
    if sev in ("critical", "blocker", "p0"):
        return "P0"
    if sev in ("high", "major", "p1"):
        return "P1"
    if sev == "medium" and cat in _SERIOUS_CATEGORIES:
        return "P1"
    return "P2"


def score_cap(priorities: Iterable[str]) -> int:
    ps = list(priorities)
    if "P0" in ps:
        return 2
    p1 = ps.count("P1")
    if p1 >= 2:
        return 3
    if p1 == 1 or ps:
        return 4
    return 5


def final_score(model_score, priorities: Iterable[str]) -> int:
    """Model judgment, clamped so it can never contradict the findings."""
    ps = list(priorities)
    cap = score_cap(ps)
    try:
        score = int(round(float(model_score)))
    except (TypeError, ValueError):
        score = cap
    score = max(0, min(cap, score))
    if not ps:
        score = max(score, 4)
    return score


def dots(score: int) -> str:
    return "\u25CF" * score + "\u25CB" * (5 - score)


def sort_key(priority_label: str) -> int:
    return _RANK.get(priority_label, 3)
