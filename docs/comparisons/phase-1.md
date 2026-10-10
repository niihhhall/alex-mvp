# Phase 1 comparison: Alex vs Greptile

Lab PR: https://github.com/niihhhall/mark-ai-review-lab/pull/1 (case 1, blue ticks, 4 lines)
Known bug: `.decode()` on a Redis value that is already `str`, so every message stops getting a reply.

Alex run: https://github.com/niihhhall/mark-ai-review-lab/actions/runs/38048497701 (triggered with `/alex`).

## Result

| | Greptile (free Starter) | Alex phase 1 |
|---|---|---|
| Caught the known bug | Yes, `app/webhook.py:267` | Yes, `app/webhook.py:267` |
| Suggested fix | `last_msg_id = last_msg_id_bytes or ""` | Same, as a one-click suggestion |
| False alarms | 0 | 0 |
| Severity | P1 | P0 |
| Confidence | 4/5 | 2/5 |
| Impact label | Medium | High |
| Summary bullets | 1 | 4 |
| Diagram | Flowchart, 7 nodes | Flowchart, 8 nodes with a yes/no branch |
| Files table | No (small PR) | Yes, collapsed |
| Score explanation | No | Yes, collapsed |
| Status check | None posted | `Alex review` failure: `Confidence 2/5 · 1 P0` |
| Reactions | 👀 then review | 👀 then 👍 on the trigger comment |
| Bot identity | `greptile-apps[bot]` | `github-actions[bot]` (own app in phase 2) |
| Trigger | `@greptileai` | `/alex` (`@alexreview-ai` in phase 2) |
| Time | about 2 min | 1 min 53 s end to end (engine 1 min 29 s) |
| Cost | 1 free credit | about $0.015 (162,913 engine tokens + card call) |

## Notes

- Same finding, same line, same fix. Case 1 is the easiest case, so a tie on detection was expected.
- Alex is stricter: P0 and 2/5 versus P1 and 4/5. The bug stops replies for every incoming message
  on the main path, which matches our P0 definition ("crash on a main path"). We keep this.
- Greptile's summary is tighter. Alex's 4 bullets repeat the finding.

## Gaps to close in phase 2

1. Summary: 2 or 3 bullets about what the PR does; do not restate the finding (prompt change).
2. Bot identity and `@alexreview-ai` trigger (org + GitHub App).
3. Footer: add a one-click re-run link like Greptile's "Retrigger" badge.
4. Diagram: real Mermaid render check before posting.
5. Run cases 2-8, where the bigger and subtler bugs will separate the two reviewers.
