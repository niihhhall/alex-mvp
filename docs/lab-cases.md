# Lab cases (answer key)

Real bugs from mark.ai history, replayed as PRs on https://github.com/niihhhall/mark-ai-review-lab.
For each case, lab `main` = mark.ai at the parent of the "introduced" commit, redacted with
`evals/lab/redact_snapshot.py` and scanned with `evals/lab/scan_dir.py` before pushing.

| # | Introduced (mark.ai) | Change | Known bug | Fixed in | Size |
|---|---|---|---|---|---|
| 1 | `04982b3` | Blue ticks (read receipts) | `.decode()` on a Redis value that is already `str` (decode_responses=True) | `1e33dba` | 4 lines |
| 2 | `27759b3` | Logging in conversation.py | uses `settings` without importing it | `d750d31` | 13 lines |
| 3 | `f9f6add` | Supabase retry logic | uses `asyncio` in tracker.py without importing it | `e896382` | 36 lines |
| 4 | `db84f78` | Typing timing overhaul | `lead_id` used before assignment | `6995651` | 48 lines |
| 5 | `8efc2f5` | Human-like timing sequence | `process_conversation` defined twice | `ca0d31f` | 227 lines |
| 6 | `013a91d` | Master Improvement Plan | calls `redis_client.lrange`, which does not exist | `86791a3` | 506 lines |
| 7 | `0a91fa7` | Supabase tracking + Calendly | duplicate bookings (no idempotency on event id); float score into int column; None `lead_id` in HTTP headers | `804c0e0`, `1033609`, `2eae639` | 607 lines |
| 8 | `29060b6` | Messaging provider router | `logger.error` used but `logger` never defined in llm.py | `09be0e1` | ~1,100 lines |

## Results so far

| Case | Greptile | Alex (raw engine output) |
|---|---|---|
| 1 | Caught, line 267, P1, confidence 4/5 | Caught, line 267, P0, confidence 2/5, same fix, ~$0.015 (phase 1 action, see `docs/comparisons/phase-1.md`) |
