"""The summary card: one LLM call for the words, deterministic rules for everything else."""
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import diff as diffmod
from . import mermaid, scoring, text
from .findings import Finding

SUMMARY_MARKER = "<!-- alex-summary -->"
META_PREFIX = "<!-- alex-meta:"
MAX_DIFF_CHARS = 40000
IMPACTS = ("Low", "Medium", "High")

SYSTEM_PROMPT = """You are Alex, a senior code reviewer. You write the summary card for a pull request review.
The bug hunting is already done: you receive the diff and the list of findings. Do not invent new findings.

Reply with ONE JSON object, no prose, with exactly these keys:
{
  "impact": "Low" | "Medium" | "High",
  "headline": "what the PR does, one line, max 14 words",
  "verdict": "one sentence, max 25 words: merge advice naming the most important finding, if any",
  "summary": ["2 or 3 bullets, max 18 words each, describing WHAT THE PR CHANGES"],
  "files": {"<path>": "what changed in this file, max 8 words"},
  "titles": {"<finding number>": "short title, sentence case, max 8 words, says what breaks"},
  "score": 0-5,
  "score_reason": "one or two sentences",
  "diagram": {"type": "flowchart" | "sequence" | "er" | "class" | "none", "mermaid": "diagram source or empty"}
}

Rules:
- Plain direct English. Never use em dashes or en dashes. No hype.
- summary describes the change itself (new behaviour, moved logic, new config). It must NOT restate,
  explain or hint at the findings: findings are already listed above it and in the verdict.
- Wrap code identifiers in backticks, like `last_msg_id`.
- impact: High if the change touches money, auth, data integrity or the main user path; Low for docs, tests, small refactors.
- score: 5 merge, 4 small fixes, 3 address feedback first, 2 needs rework, 0-1 rethink.
- diagram: choose sequence for calls between services or APIs, er for schema changes, class for class hierarchies,
  flowchart for control flow or business logic. Use none ONLY when the PR changes nothing but docs, comments,
  formatting, renames or dependency versions. Any PR with a finding or a behaviour change gets a diagram.
  Show the changed behaviour, and if a finding breaks the flow, show where it breaks.
  At most 12 nodes. Flowchart must start with "flowchart TD" and every label must be quoted, like A["Store message ID"].
  Sequence must start with "sequenceDiagram". No code fences, no styling, no comments.
"""


@dataclass
class CardData:
    impact: str = "Medium"
    headline: str = ""
    verdict: str = ""
    summary: List[str] = field(default_factory=list)
    files: Dict[str, str] = field(default_factory=dict)
    titles: Dict[int, str] = field(default_factory=dict)
    score: int = 4
    score_reason: str = ""
    diagram_type: str = "none"
    diagram: Optional[str] = None
    diagram_rejected: str = ""
    from_model: bool = False


DIAGRAM_PROMPT = """You draw one Mermaid diagram for a pull request review. Reply with ONE JSON object:
{"type": "flowchart" | "sequence" | "er" | "class", "mermaid": "diagram source"}
Show the changed behaviour and where the most important finding breaks it. At most 12 nodes.
Flowchart must start with "flowchart TD" and every label must be quoted, like A["Store message ID"].
Sequence must start with "sequenceDiagram". No code fences, no styling, no comments, no em or en dashes."""


def build_diagram_messages(title: str, diff_text: str, findings: List[Finding]) -> List[dict]:
    clipped = diff_text[:20000]
    items = [{"priority": f.priority, "location": f.location, "detail": f.content[:600]} for f in findings[:5]]
    user = f"PR title: {title}\n\nFindings:\n{json.dumps(items, ensure_ascii=False)}\n\nDiff:\n{clipped}"
    return [{"role": "system", "content": DIAGRAM_PROMPT}, {"role": "user", "content": user}]


def apply_diagram(card: "CardData", raw: Optional[dict]) -> bool:
    if not raw:
        return False
    kind = str(raw.get("type", "")).strip().lower()
    cleaned = mermaid.validate(kind, str(raw.get("mermaid", "")))
    if cleaned:
        card.diagram_type, card.diagram = kind, cleaned
        return True
    card.diagram_rejected = f"{kind}: {str(raw.get('mermaid', ''))[:1500]}"
    return False


def build_messages(title: str, body: str, diff_text: str, findings: List[Finding]) -> List[dict]:
    clipped = diff_text if len(diff_text) <= MAX_DIFF_CHARS else diff_text[:MAX_DIFF_CHARS] + "\n[diff truncated]"
    items = [
        {"number": f.number, "priority": f.priority, "category": f.category, "location": f.location, "detail": f.content}
        for f in findings
    ]
    user = (
        f"PR title: {title}\n\nPR description:\n{(body or '(none)')[:2000]}\n\n"
        f"Findings ({len(items)}):\n{json.dumps(items, ensure_ascii=False, indent=1)}\n\n"
        f"Diff:\n{clipped}"
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def _s(value, limit: int) -> str:
    return text.clean(str(value or "").strip())[:limit]


def normalize(raw: Optional[dict], findings: List[Finding]) -> CardData:
    """Validate model output; anything missing or broken falls back to safe defaults."""
    priorities = [f.priority for f in findings]
    data = CardData(score=scoring.score_cap(priorities))
    if not raw:
        data.headline = "Changes reviewed."
        data.verdict = _default_verdict(findings)
        return data
    data.from_model = True
    impact = str(raw.get("impact", "")).strip().capitalize()
    data.impact = impact if impact in IMPACTS else "Medium"
    data.headline = _s(raw.get("headline"), 160) or "Changes reviewed."
    data.verdict = _s(raw.get("verdict"), 300) or _default_verdict(findings)
    summary = raw.get("summary") if isinstance(raw.get("summary"), list) else []
    data.summary = [_s(b, 200) for b in summary if str(b).strip()][:3]
    files = raw.get("files") if isinstance(raw.get("files"), dict) else {}
    data.files = {str(k): _s(v, 80) for k, v in files.items()}
    titles = raw.get("titles") if isinstance(raw.get("titles"), dict) else {}
    for k, v in titles.items():
        try:
            data.titles[int(k)] = _s(v, 80)
        except (TypeError, ValueError):
            continue
    data.score = scoring.final_score(raw.get("score"), priorities)
    data.score_reason = _s(raw.get("score_reason"), 400)
    diagram = raw.get("diagram") if isinstance(raw.get("diagram"), dict) else {}
    kind = str(diagram.get("type", "none")).strip().lower()
    if kind != "none":
        source = str(diagram.get("mermaid", ""))
        cleaned = mermaid.validate(kind, source)
        if cleaned:
            data.diagram_type, data.diagram = kind, cleaned
        else:
            data.diagram_rejected = f"{kind}: {source[:1500]}"
    return data


def _default_verdict(findings: List[Finding]) -> str:
    if not findings:
        return "No issues found. Safe to merge."
    top = findings[0]
    if top.priority == "P0":
        return f"Fix the {top.priority} issue in `{top.path}` before merging."
    if top.priority == "P1":
        return f"Address the {top.priority} issue in `{top.path}` before merging."
    return "Only minor suggestions. Fine to merge after a quick look."


def apply_titles(card: CardData, findings: List[Finding]) -> None:
    for f in findings:
        if card.titles.get(f.number):
            f.title = card.titles[f.number]


def read_meta(body: str) -> dict:
    start = (body or "").find(META_PREFIX)
    if start == -1:
        return {}
    end = body.find("-->", start)
    try:
        return json.loads(body[start + len(META_PREFIX):end].strip())
    except ValueError:
        return {}


def render(card: CardData, findings: List[Finding], *, diff_text: str, review_count: int,
           head_sha: str, head_message: str, commit_url: str) -> str:
    out = [SUMMARY_MARKER, f"## Alex review \u00b7 Confidence {card.score}/5 {scoring.dots(card.score)}", ""]
    out.append(f"**[{card.impact} impact]** {card.headline}")
    out.append("")
    out.append(card.verdict)
    out.append("")

    out.append("### Findings")
    if not findings:
        out.append("No issues found.")
    for f in findings:
        link = f" [\u25b6]({f.url})" if f.url else ""
        line = f"{f.number}. {scoring.BADGE[f.priority]} \u00b7 **{f.title}**{link} `{f.location}`"
        if not f.placeable:
            line += " (not on a changed line)"
        out.append(line)
        if not f.placeable:
            out.extend(f"   > {ln}" for ln in f.content.splitlines() if ln.strip())
    out.append("")

    if card.summary:
        out.append("### Summary")
        out.extend(f"- {b}" for b in card.summary)
        out.append("")

    stats = diffmod.file_stats(diff_text)
    if stats:
        per_file: Dict[str, List[str]] = {}
        for f in findings:
            per_file.setdefault(f.path, []).append(f.priority)
        out.append(f"<details><summary><b>Files changed ({len(stats)})</b></summary>")
        out.append("")
        out.append("| File | Change | Issues |")
        out.append("|---|---|---|")
        for s in stats:
            issues = per_file.get(s["path"], [])
            counts = ", ".join(f"{issues.count(p)} {p}" for p in ("P0", "P1", "P2") if issues.count(p)) or "none"
            change = card.files.get(s["path"]) or "updated"
            out.append(f"| `{s['path']}` | +{s['added']} -{s['removed']}, {change} | {counts} |")
        out.append("")
        out.append("</details>")
        out.append("")

    if card.diagram:
        out.append(f"<details open><summary><b>Diagram ({card.diagram_type})</b></summary>")
        out.append("")
        out.append("```mermaid")
        out.append(card.diagram)
        out.append("```")
        out.append("")
        out.append("</details>")
        out.append("")

    if card.score_reason:
        out.append("<details><summary><b>Why this score</b></summary>")
        out.append("")
        out.append(card.score_reason)
        out.append("")
        out.append("</details>")
        out.append("")

    short = head_message.splitlines()[0][:60] if head_message else ""
    commit = f"[{head_sha[:7]} {short}]({commit_url})" if commit_url else head_sha[:7]
    out.append(f"<sub>Reviews ({review_count}) \u00b7 Last reviewed commit: {commit} \u00b7 "
               f"Pushed fixes? Comment `/alex` to review again</sub>")
    out.append(f"{META_PREFIX} {json.dumps({'reviews': review_count, 'head': head_sha})} -->")
    return text.clean("\n".join(out))
