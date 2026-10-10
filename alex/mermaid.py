"""Mermaid checks. Every line must match the grammar we allow, so a broken diagram is dropped, never posted."""
import re
from typing import Optional

MAX_LINES = 30
MAX_NODES = 14

_HEADERS = {
    "flowchart": re.compile(r"^(flowchart|graph)\s+(TD|TB|BT|LR|RL)$"),
    "sequence": re.compile(r"^sequenceDiagram$"),
    "er": re.compile(r"^erDiagram$"),
    "class": re.compile(r"^classDiagram$"),
}

# Flowchart -------------------------------------------------------------------------
_LABEL = r'(?:"[^"\n]*"|[A-Za-z0-9 _.,\'/+-]+)'
_SHAPE = (rf"(?:\[\[{_LABEL}\]\]|\(\({_LABEL}\)\)|\(\[{_LABEL}\]\)|\[\({_LABEL}\)\]|"
          rf"\[{_LABEL}\]|\({_LABEL}\)|\{{\{{{_LABEL}\}}\}}|\{{{_LABEL}\}}|>{_LABEL}\])")
_NODE = rf"[A-Za-z][A-Za-z0-9_]*(?:{_SHAPE})?"
_ARROW = r"(?:-->|---|-\.->|-\.-|==>|===|--x|--o|<-->)"
_EDGE_LABEL = rf"(?:\|{_LABEL}\|)?"
_FLOW_LINE = re.compile(rf"^{_NODE}(?:\s*{_ARROW}\s*{_EDGE_LABEL}\s*{_NODE})*\s*;?$")
_FLOW_OTHER = re.compile(r'^(subgraph\s+[A-Za-z0-9_]+(?:\s*\["[^"\n]*"\])?|end|direction\s+(TD|TB|BT|LR|RL))$')

# Sequence --------------------------------------------------------------------------
_ACTOR = r"[A-Za-z][A-Za-z0-9_]*"
_SEQ_LINES = [
    re.compile(rf"^(participant|actor)\s+{_ACTOR}(\s+as\s+[^\n:]+)?$"),
    re.compile(rf"^{_ACTOR}\s*(->>|-->>|->|-->|-x|--x|-\)|--\))\s*[+-]?{_ACTOR}\s*:\s*[^\n]+$"),
    re.compile(rf"^Note\s+(left of|right of|over)\s+{_ACTOR}(\s*,\s*{_ACTOR})?\s*:\s*[^\n]+$"),
    re.compile(r"^(alt|else|opt|loop|par|and|critical|break)(\s+[^\n]*)?$"),
    re.compile(rf"^(activate|deactivate)\s+{_ACTOR}$"),
    re.compile(r"^(end|autonumber)$"),
]

# ER and class: lenient, structure only -------------------------------------------------
_ER_LINES = [
    re.compile(r'^[A-Za-z][\w-]*\s+[|o}{]{2}(--|\.\.)[|o}{]{2}\s+[A-Za-z][\w-]*\s*:\s*("[^"\n]*"|[\w-]+)$'),
    re.compile(r"^[A-Za-z][\w-]*\s*\{$"),
    re.compile(r'^[A-Za-z][\w()\[\]]*\s+[A-Za-z_][\w]*(\s+(PK|FK|UK)(\s*,\s*(PK|FK|UK))*)?(\s+"[^"\n]*")?$'),
    re.compile(r"^\}$"),
]
_CLASS_LINES = [
    re.compile(r"^class\s+[A-Za-z][\w]*(~[\w,]+~)?(\s*\{)?$"),
    re.compile(r"^[A-Za-z][\w]*\s*(<\|--|--\|>|\*--|--\*|o--|--o|-->|<--|\.\.>|<\.\.|\.\.\|>|<\|\.\.|--|\.\.)\s*"
               r"[A-Za-z][\w]*(\s*:\s*[^\n]+)?$"),
    re.compile(r"^[A-Za-z][\w]*\s*:\s*[^\n]+$"),
    re.compile(r"^[+\-#~]?[A-Za-z_][\w<>,\[\] ]*(\([^)\n]*\))?[$*]?(\s*[\w<>\[\]]+)?$"),
    re.compile(r"^\}$"),
]


def _balanced(text: str) -> bool:
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack, in_quote = [], False
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


def _line_ok(kind: str, line: str) -> bool:
    if kind == "flowchart":
        return bool(_FLOW_LINE.match(line) or _FLOW_OTHER.match(line))
    if kind == "sequence":
        return any(p.match(line) for p in _SEQ_LINES)
    if kind == "er":
        return any(p.match(line) for p in _ER_LINES)
    return any(p.match(line) for p in _CLASS_LINES)


def validate(kind: str, source: str) -> Optional[str]:
    """Return cleaned Mermaid source, or None if it should not be posted."""
    if not source or kind not in _HEADERS:
        return None
    body = re.sub(r"^```(?:mermaid)?\s*|\s*```$", "", source.strip()).strip()
    lines = [ln.strip() for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("%%")]
    if len(lines) < 2 or len(lines) > MAX_LINES:
        return None
    if not _HEADERS[kind].match(lines[0]):
        return None
    if "```" in body or "<script" in body.lower():
        return None
    depth = 0
    for ln in lines[1:]:
        if not _line_ok(kind, ln):
            return None
        if kind in ("flowchart", "sequence"):
            if not _balanced(ln):
                return None
            continue
        # ER and class open a block on one line and close it on a later one.
        if ln.endswith("{"):
            depth += 1
        elif ln == "}":
            depth -= 1
            if depth < 0:
                return None
    if depth:
        return None
    if kind == "flowchart":
        nodes = set(re.findall(r"(?:^|-->|---|==>|-\.->|\s)\s*([A-Za-z][A-Za-z0-9_]*)\s*[\[\(\{>]", "\n".join(lines[1:])))
        if len(nodes) > MAX_NODES:
            return None
    return "\n".join([lines[0]] + ["  " + ln for ln in lines[1:]])
