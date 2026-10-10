"""Lightweight Mermaid checks. We drop a diagram rather than post a broken one."""
import re
from typing import Optional

_HEADERS = {
    "flowchart": re.compile(r"^(flowchart|graph)\s+(TD|TB|BT|LR|RL)\b"),
    "sequence": re.compile(r"^sequenceDiagram\b"),
    "er": re.compile(r"^erDiagram\b"),
    "class": re.compile(r"^classDiagram\b"),
}
MAX_LINES = 30
MAX_NODES = 14


def _balanced(text: str) -> bool:
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack = []
    in_quote = False
    for ch in text:
        if ch == '"':
            in_quote = not in_quote
            continue
        if in_quote:
            continue
        if ch in pairs:
            stack.append(pairs[ch])
        elif ch in pairs.values():
            if not stack or stack.pop() != ch:
                return False
    return not stack and not in_quote


def validate(kind: str, source: str) -> Optional[str]:
    """Return cleaned Mermaid source, or None if it should not be posted."""
    if not source or kind not in _HEADERS:
        return None
    body = source.strip()
    body = re.sub(r"^```(?:mermaid)?\s*|\s*```$", "", body).strip()
    lines = [ln.rstrip() for ln in body.splitlines() if ln.strip()]
    if not lines or len(lines) > MAX_LINES:
        return None
    if not _HEADERS[kind].match(lines[0].strip()):
        return None
    if "```" in body or "<script" in body.lower():
        return None
    for ln in lines[1:]:
        if not _balanced(ln):
            return None
    if kind == "flowchart":
        nodes = set(re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)\s*[\[\(\{]", body))
        if len(nodes) > MAX_NODES:
            return None
        # Unquoted labels with parentheses or colons break the parser.
        if re.search(r"\[[^\"\]]*[():;][^\]]*\]", body):
            return None
    return "\n".join(lines)
