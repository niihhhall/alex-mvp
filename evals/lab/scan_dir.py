"""Scan a directory snapshot for secret-looking strings and phone numbers; print masked results only.

Usage: python scan_dir.py <dir>
Exit code 1 if anything secret-looking is found.
"""
import re
import sys
from pathlib import Path

from scan_secrets import PATTERNS

# Generic "KEY=value" assignments whose value looks real (not a placeholder).
ASSIGN = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASS|AUTH)[A-Z0-9_]*)\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+=]{16,})"
)
PLACEHOLDER = re.compile(r"(?i)your|xxx|example|placeholder|changeme|<|\.\.\.|^sk-\.\.\.|settings\.|os\.getenv|environ")
PHONE = re.compile(r"(?<![\w.])\+?(?:971|44|91|1|61)[ -]?\d{2,4}[ -]?\d{3,4}[ -]?\d{3,4}(?!\w)")


def main() -> None:
    root = Path(sys.argv[1])
    found = False
    phones = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(root)
        for name, pat in PATTERNS.items():
            for m in re.findall(pat, text):
                found = True
                print(f"SECRET {name}: {rel} ({m[:6]}...)")
        for m in ASSIGN.finditer(text):
            value = m.group(2)
            if not PLACEHOLDER.search(value) and not PLACEHOLDER.search(m.group(0)):
                found = True
                print(f"POSSIBLE {m.group(1)} in {rel} ({value[:4]}...)")
        phones += len(PHONE.findall(text))
    print(f"phone-number-like strings: {phones}")
    print("RESULT:", "REVIEW NEEDED" if found else "clean")
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()
