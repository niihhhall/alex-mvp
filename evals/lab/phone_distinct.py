"""List distinct phone-like numbers in a snapshot, showing only the last 4 digits and a count.

Usage: python phone_distinct.py <dir>
"""
import re
import sys
from collections import Counter
from pathlib import Path

from scan_dir import PHONE

FAKES = {"447700900001", "447700900002"}


def main() -> None:
    seen = Counter()
    where = {}
    for path in Path(sys.argv[1]).rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for hit in PHONE.findall(text):
            d = re.sub(r"\D", "", hit)
            seen[d] += 1
            where.setdefault(d, path.name)
    for d, n in seen.most_common():
        tag = "FAKE" if d in FAKES else ""
        print(f"len={len(d):>2} ...{d[-4:]}  x{n:<3} first in {where[d]:<32} {tag}")


if __name__ == "__main__":
    main()
