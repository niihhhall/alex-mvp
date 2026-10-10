"""Text hygiene applied to everything Alex posts."""
import re

_FENCE = re.compile(r"(```.*?```)", re.S)
_INLINE_CODE = re.compile(r"(`[^`\n]*`)")


def _clean_prose(text: str) -> str:
    text = re.sub(r"(?<=\d)\s*[\u2013\u2014]\s*(?=\d)", "-", text)
    text = re.sub(r"\s+[\u2013\u2014]\s+", ", ", text)
    text = re.sub(r"[\u2013\u2014]", "-", text)
    return text


def no_dashes(text: str) -> str:
    """Replace em and en dashes outside code, per the design system."""
    out = []
    for part in _FENCE.split(text or ""):
        if part.startswith("```"):
            out.append(part)
            continue
        out.extend(p if p.startswith("`") else _clean_prose(p) for p in _INLINE_CODE.split(part))
    return "".join(out)


def clean(text: str) -> str:
    return no_dashes(text)


def first_sentence(text: str, limit: int = 80) -> str:
    """Short title fallback when the card model is unavailable."""
    plain = re.sub(r"`([^`]*)`", r"\1", text or "").strip()
    sentence = re.split(r"(?<=[.!?])\s", plain, maxsplit=1)[0].rstrip(".")
    if len(sentence) > limit:
        sentence = sentence[: limit - 3].rsplit(" ", 1)[0] + "..."
    return sentence[:1].upper() + sentence[1:]
