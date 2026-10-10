"""Count secret-looking strings across a repo's full git history, printing only masked types.

Usage: python scan_secrets.py <repo_path>
"""
import re
import subprocess
import sys
from collections import Counter, defaultdict

PATTERNS = {
    "OpenRouter key": r"sk-or-v1-[a-f0-9]{20,}",
    "OpenAI/Anthropic-style key": r"sk-(?!or-v1)[A-Za-z0-9_-]{20,}",
    "Fireworks key": r"fw_[A-Za-z0-9]{16,}",
    "JWT (e.g. Supabase key)": r"eyJ[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}",
    "AWS access key": r"AKIA[0-9A-Z]{16}",
    "Meta/WhatsApp token": r"EAA[A-Za-z0-9]{40,}",
    "GitHub token": r"gh[pous]_[A-Za-z0-9]{30,}",
    "Pinecone key": r"pcsk_[A-Za-z0-9_]{20,}",
    "Helicone key": r"sk-helicone-[A-Za-z0-9-]{10,}",
    "Redis/Postgres URL with password": r"(?:rediss?|postgres(?:ql)?)://[^\s:'\"@/]+:[^\s'\"@]{6,}@",
}


def main() -> None:
    repo = sys.argv[1]
    log = subprocess.run(
        ["git", "-C", repo, "log", "-p", "--all", "--no-color", "--format=COMMIT %h"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    ).stdout

    counts = Counter()
    distinct = defaultdict(set)
    commits = defaultdict(set)
    current = "?"
    for line in log.splitlines():
        if line.startswith("COMMIT "):
            current = line.split()[1]
            continue
        if not line.startswith("+"):
            continue
        for name, pat in PATTERNS.items():
            for m in re.findall(pat, line):
                counts[name] += 1
                distinct[name].add(m)
                commits[name].add(current)

    if not counts:
        print("No secret-looking strings found in history.")
        return
    print(f"{'Type':<34}{'distinct values':>16}{'commits':>9}")
    for name in counts:
        print(f"{name:<34}{len(distinct[name]):>16}{len(commits[name]):>9}  e.g. in {sorted(commits[name])[:3]}")


if __name__ == "__main__":
    main()
