"""Turn raw engine comments into Alex findings."""
import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from . import scoring, text


@dataclass
class Finding:
    path: str
    start: int
    end: int
    priority: str
    category: str
    content: str
    suggestion: str = ""
    existing_code: str = ""
    number: int = 0
    title: str = ""
    anchor_start: Optional[int] = None
    anchor_end: Optional[int] = None
    url: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def placeable(self) -> bool:
        return self.anchor_end is not None

    @property
    def fingerprint(self) -> str:
        basis = re.sub(r"\s+", " ", self.existing_code or self.content[:160]).strip()
        raw = f"{self.path}|{self.category.lower()}|{basis}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

    @property
    def location(self) -> str:
        return f"{self.path}:{self.start}" if self.start == self.end else f"{self.path}:{self.start}-{self.end}"


def _int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def from_engine(result: dict, commentable: Dict[str, Set[int]]) -> List[Finding]:
    findings: List[Finding] = []
    for c in result.get("comments") or []:
        path = (c.get("path") or "").strip()
        content = text.clean((c.get("content") or "").strip())
        if not path or not content:
            continue
        start = _int(c.get("start_line"), 0)
        end = _int(c.get("end_line"), start) or start
        if end < start:
            start, end = end, start
        f = Finding(
            path=path,
            start=start,
            end=end,
            priority=scoring.priority(c.get("severity", ""), c.get("category", "")),
            category=(c.get("category") or "issue").strip().lower(),
            content=content,
            suggestion=(c.get("suggestion_code") or "").rstrip("\n"),
            existing_code=(c.get("existing_code") or "").rstrip("\n"),
        )
        lines = commentable.get(path, set())
        if end and end in lines:
            f.anchor_end = end
            if start and start != end and start in lines and all(n in lines for n in range(start, end + 1)):
                f.anchor_start = start
        findings.append(f)

    seen = set()
    unique = []
    for f in findings:
        if f.fingerprint in seen:
            continue
        seen.add(f.fingerprint)
        unique.append(f)
    unique.sort(key=lambda f: (scoring.sort_key(f.priority), f.path, f.start))
    for i, f in enumerate(unique, 1):
        f.number = i
        f.title = text.first_sentence(f.content)
    return unique


def suggestion_applies(f: Finding) -> bool:
    """Only offer one-click fixes when the anchored lines are exactly the replaced code."""
    if not f.suggestion or not f.existing_code or not f.placeable:
        return False
    span_start = f.anchor_start or f.anchor_end
    span = f.anchor_end - span_start + 1
    return span == len(f.existing_code.splitlines()) and span_start == f.start
