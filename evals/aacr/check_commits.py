"""Report which AACR-Bench PRs still have both commits reachable on GitHub.

PR authors sometimes force-push after the benchmark snapshot, which deletes the
reviewed commit; those PRs cannot be replayed and should be excluded from runs.
Uses the GitHub REST API (unauthenticated: 60 requests/hour; set GITHUB_TOKEN to raise it).

Usage:
    python check_commits.py [--write-clean aacr_bench_clean.jsonl]
"""
import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "aacr-bench" / "evaluation" / "data"
FULL = DATA_DIR / "aacr_bench_full.jsonl"
CACHE = HERE / "commit_check_cache.json"


def commit_exists(repo: str, sha: str, token: str) -> bool:
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/commits/{sha}")
    req.add_header("Accept", "application/vnd.github+json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30):
                return True
        except urllib.error.HTTPError as err:
            if err.code in (404, 422):
                return False
            if err.code == 403 and attempt < 2:
                time.sleep(30)
                continue
            raise
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-clean", help="write reachable instances to this file under data/")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "")
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    rows = [json.loads(line) for line in FULL.open(encoding="utf-8")]

    good, bad = [], []
    for row in rows:
        ok = True
        for sha in (row["base_commit"], row["head_commit"]):
            key = f"{row['repo']}@{sha}"
            if key not in cache:
                cache[key] = commit_exists(row["repo"], sha, token)
                CACHE.write_text(json.dumps(cache, indent=1))
            ok = ok and cache[key]
        (good if ok else bad).append(row)

    print(f"reachable: {len(good)}/{len(rows)}  unreachable: {len(bad)}")
    for row in bad:
        print("  missing:", row["instance_id"])

    if args.write_clean:
        out = DATA_DIR / args.write_clean
        out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in good), encoding="utf-8")
        refs = sum(len(r["reference_comments"]) for r in good)
        print(f"wrote {len(good)} instances ({refs} reference issues) -> {out}")


if __name__ == "__main__":
    main()
