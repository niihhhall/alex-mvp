"""Build a small, fixed AACR-Bench subset so pilot runs are cheap and repeatable.

Usage:
    python make_subset.py --out pilot.jsonl owner/repo#PR [owner/repo#PR ...]
"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL_DIR = HERE / "aacr-bench" / "evaluation"
RAW = HERE / "aacr-bench" / "dataset" / "positive_samples.json"
FULL = EVAL_DIR / "data" / "aacr_bench_full.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="file name written under evaluation/data/")
    parser.add_argument("prs", nargs="+", help="PRs as owner/repo#number")
    args = parser.parse_args()

    # The converted JSONL drops the PR number, so map PR -> head commit via the raw data.
    wanted = {}
    for item in json.loads(RAW.read_text(encoding="utf-8")):
        slug = item["githubPrUrl"].split("github.com/")[1].replace("/pull/", "#")
        wanted[slug] = item["target_commit"]

    heads = {}
    for pr in args.prs:
        if pr not in wanted:
            raise SystemExit(f"PR not in dataset: {pr}")
        heads[wanted[pr]] = pr

    out_path = EVAL_DIR / "data" / args.out
    kept = []
    with FULL.open(encoding="utf-8") as src:
        for line in src:
            row = json.loads(line)
            if row["head_commit"] in heads:
                kept.append(line)

    out_path.write_text("".join(kept), encoding="utf-8")
    print(f"wrote {len(kept)}/{len(args.prs)} instances -> {out_path}")


if __name__ == "__main__":
    main()
