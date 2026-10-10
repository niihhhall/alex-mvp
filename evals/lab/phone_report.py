"""Show where phone-number-like strings appear in a snapshot, with digits masked.

Usage: python phone_report.py <dir>
"""
import re
import sys
from collections import Counter
from pathlib import Path

from scan_dir import PHONE


def mask(s: str) -> str:
    return re.sub(r"\d(?=\d{2})", "#", s)


def main() -> None:
    root = Path(sys.argv[1])
    per_file = Counter()
    samples = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for no, line in enumerate(lines, 1):
            hits = PHONE.findall(line)
            if hits:
                per_file[str(path.relative_to(root))] += len(hits)
                if len(samples) < 12:
                    samples.append(f"{path.name}:{no}: {mask(line.strip())[:110]}")
    for name, n in per_file.most_common():
        print(f"{n:>4}  {name}")
    print("--- samples (masked) ---")
    print("\n".join(samples))
    env = root / ".env.example"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "VERIFY_TOKEN" in line:
                key, _, val = line.partition("=")
                print(f"--- .env.example: {key}={val[:4]}**** (length {len(val)})")


if __name__ == "__main__":
    main()
