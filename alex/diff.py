"""Unified diff parsing: which right-side lines GitHub accepts review comments on."""
import re
from typing import Dict, List, Set

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def commentable_lines(diff_text: str) -> Dict[str, Set[int]]:
    """Map new-file path -> set of line numbers present on the RIGHT side of the diff."""
    result: Dict[str, Set[int]] = {}
    path = None
    line_no = 0
    in_hunk = False
    for raw in diff_text.splitlines():
        if raw.startswith("diff --git "):
            path, in_hunk = None, False
            continue
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            path = None if target == "/dev/null" else re.sub(r"^b/", "", target)
            if path:
                result.setdefault(path, set())
            in_hunk = False
            continue
        if raw.startswith("--- "):
            continue
        m = _HUNK.match(raw)
        if m:
            line_no = int(m.group(1))
            in_hunk = True
            continue
        if not in_hunk or path is None:
            continue
        if raw.startswith("+") or raw.startswith(" "):
            result[path].add(line_no)
            line_no += 1
        elif raw.startswith("-") or raw.startswith("\\"):
            continue
    return result


def file_stats(diff_text: str) -> List[dict]:
    """Per-file added/removed counts, in diff order."""
    stats: List[dict] = []
    current = None
    in_hunk = False
    for raw in diff_text.splitlines():
        if raw.startswith("diff --git "):
            m = re.match(r"diff --git a/(.+?) b/(.+)$", raw)
            current = {"path": m.group(2) if m else raw[11:], "added": 0, "removed": 0}
            stats.append(current)
            in_hunk = False
            continue
        if current is None:
            continue
        if raw.startswith("@@"):
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if raw.startswith("+"):
            current["added"] += 1
        elif raw.startswith("-"):
            current["removed"] += 1
    return stats
