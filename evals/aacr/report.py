"""Print an English scorecard for one benchmark run, including estimated dollar cost.

Usage:
    python report.py <benchmark> <run_id>          e.g. python report.py pilot pilot-deepseek
    python report.py <benchmark> <run_id> --price-in 0.22 --price-cached 0.007 --price-out 0.66

Default prices are Fireworks' DeepSeek V4.1 Flash list rates (USD per 1M tokens) as of Sept 2026.
"""
import argparse
import json
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent / "aacr-bench" / "evaluation"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("benchmark")
    parser.add_argument("run_id")
    parser.add_argument("--reviewer", default="ocr")
    parser.add_argument("--price-in", type=float, default=0.22)
    parser.add_argument("--price-cached", type=float, default=0.007)
    parser.add_argument("--price-out", type=float, default=0.66)
    parser.add_argument("--project-to", type=int, default=185, help="extrapolate cost to N PRs")
    args = parser.parse_args()

    results_dir = EVAL_DIR / "results" / args.benchmark / args.reviewer / args.run_id
    metrics_dir = EVAL_DIR / "metrics" / args.benchmark / args.reviewer / args.run_id
    metrics_files = sorted(metrics_dir.glob("metrics_*.json"), key=lambda p: p.stat().st_mtime)
    if not metrics_files:
        raise SystemExit(f"no metrics in {metrics_dir}; run the eval stage first")
    summary = json.loads(metrics_files[-1].read_text(encoding="utf-8"))["summary"]

    rows = []
    for path in sorted(results_dir.glob("*.json")):
        if path.name.startswith("summary_"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        review = data.get("review") if isinstance(data.get("review"), dict) else {}
        s = review.get("summary") or {}
        inp, cached, out = s.get("input_tokens", 0), s.get("cache_read_tokens", 0), s.get("output_tokens", 0)
        # OCR reports cache reads as a subset of input tokens.
        cost = ((inp - cached) * args.price_in + cached * args.price_cached + out * args.price_out) / 1e6
        rows.append((data["instance_id"], s.get("files_reviewed", 0), s.get("comments", 0),
                     inp + out, data.get("duration_seconds", 0), cost))

    print(f"\n=== {args.reviewer} | {args.benchmark} | run '{args.run_id}' ===")
    print(f"PRs graded: {summary['evaluated_instances']} of {summary['total_instances']} "
          f"(skipped/failed: {summary['missing_instances']})")
    print(f"Real issues in answer key: {summary['expected_notes']} | Findings produced: {summary['generated_notes']}")
    print(f"Correct findings (judge-confirmed): {summary['matched_semantic_notes']}")
    print()
    print(f"{'Metric':<28}{'Semantic':>10}{'Line-only':>11}")
    print(f"{'Precision (no false alarms)':<28}{summary['semantic_match_rate']:>10.3f}{summary['line_match_rate']:>11.3f}")
    print(f"{'Recall (bugs caught)':<28}{summary['semantic_recall_rate']:>10.3f}{summary['line_recall_rate']:>11.3f}")
    print(f"{'F1 (overall grade)':<28}{summary['semantic_f1']:>10.3f}{summary['line_f1']:>11.3f}")
    print()
    print(f"{'PR':<38}{'files':>6}{'finds':>6}{'tokens':>12}{'mins':>7}{'cost $':>9}")
    for pr, files, finds, tokens, secs, cost in rows:
        print(f"{pr:<38}{files:>6}{finds:>6}{tokens:>12,}{secs / 60:>7.1f}{cost:>9.3f}")

    if rows:
        total = sum(r[5] for r in rows)
        avg = total / len(rows)
        print(f"\nTotal cost: ${total:.2f} | avg per PR: ${avg:.2f} | "
              f"projected for {args.project_to} PRs: ~${avg * args.project_to:.0f}")


if __name__ == "__main__":
    main()
