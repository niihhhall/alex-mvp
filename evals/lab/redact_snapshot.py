"""Replace personal phone numbers and the webhook verify token with placeholders, in place.

Applies the exact same substitutions to every snapshot directory given, so the diff between
a case's before/after snapshots is unchanged. Real values are read from the files and never printed.

Usage: python redact_snapshot.py <dir> [<dir> ...]
"""
import re
import sys
from pathlib import Path

FAKE_PERSONAL = "447700900001"   # Ofcom range reserved for fiction/testing
FAKE_BUSINESS = "447700900002"
FAKE_VERIFY_TOKEN = "your-verify-token"


def digits_of(text: str, pattern: str) -> str:
    m = re.search(pattern, text)
    return re.sub(r"\D", "", m.group(1)) if m else ""


def main() -> None:
    roots = [Path(p) for p in sys.argv[1:]]
    first = roots[0]

    personal = digits_of((first / "watch_nihal.bat").read_text(encoding="utf-8"), r"whatsapp:\+(\d{10,15})")
    env_text = (first / ".env.example").read_text(encoding="utf-8")
    business = digits_of(env_text, r"TWILIO_WHATSAPP_NUMBER=whatsapp:\+(\d{10,15})")
    token_m = re.search(r"^WHATSAPP_VERIFY_TOKEN=(.+)$", env_text, re.M)
    token = token_m.group(1).strip() if token_m else ""

    subs = [(v, f) for v, f in ((personal, FAKE_PERSONAL), (business, FAKE_BUSINESS)) if v]
    if token:
        subs.append((token, FAKE_VERIFY_TOKEN))
    print(f"redacting {len(subs)} value(s): personal={'yes' if personal else 'no'}, "
          f"business={'yes' if business else 'no'}, verify_token={'yes' if token else 'no'}")

    for root in roots:
        changed = 0
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            # Work on raw bytes so line endings and encoding stay byte-identical.
            data = path.read_bytes()
            new = data
            for real, fake in subs:
                new = new.replace(real.encode(), fake.encode())
            if new != data:
                path.write_bytes(new)
                changed += 1
        print(f"{root}: {changed} file(s) changed")

    leftovers = sum(
        1
        for root in roots
        for path in root.rglob("*")
        if path.is_file()
        for real, _ in subs
        if real in path.read_text(encoding="utf-8", errors="ignore")
    )
    print("leftover real values:", leftovers)


if __name__ == "__main__":
    main()
