# Alex design system

How every Alex comment looks and why. The goal is Greptile parity: a reader should get the verdict
in 5 seconds from the card, and the exact fix in 30 seconds from the inline comment.

## Voice

- Name: **Alex**. Never mention the engine or model in comments.
- Plain, direct English. Say what breaks and for whom ("replies stop for every user"), then the fix.
- No em dashes or en dashes anywhere (enforced in code by `alex.text.no_dashes`, outside code blocks).
- No hype, no apologies, no "great job". One idea per sentence.

## Severity badges

| Badge | Meaning | Engine severity mapped from |
|---|---|---|
| 🔴 **P0** | Must fix before merge: crash on a main path, security hole, data loss | critical |
| 🟠 **P1** | Should fix: bug, wrong behavior, broken edge case | high; medium when category is bug/security/performance/concurrency/data |
| 🟡 **P2** | Consider: quality, maintainability, style | medium (other categories), low, info |

Emoji badges render everywhere without loading images.

## Confidence score (0 to 5)

Same meaning as Greptile: 5 merge, 4 small fixes, 3 address feedback first, 2 rework, 0-1 rethink.

The score is the model's judgment **inside hard caps**, so it can never contradict the findings:

| Findings | Highest score allowed |
|---|---|
| any P0 | 2 |
| two or more P1 | 3 |
| exactly one P1 | 4 |
| only P2 | 4 |
| none | 5 (and never below 4) |

Shown as `Confidence 4/5 ●●●●○` in the card header and in the status check title.

## Summary card (one per PR, updated in place)

Order, top to bottom:

1. Header: `## Alex review · Confidence N/5 ●●●○○` (plus tier name in phase 2)
2. Impact and headline: `**[Medium impact]** what the PR does, in one line`
3. Verdict: one sentence of merge advice
4. **Findings**: numbered, badge + short title + link to the inline comment + `path:line`.
   Findings Alex could not place on a diff line appear here with "not on a changed line".
5. **Summary**: up to 4 bullets on what changed and why it matters
6. **Files changed** (collapsed): table of file, change, issues
7. **Diagram** (open): one Mermaid diagram, type chosen by the change
8. **Why this score** (collapsed): one or two sentences
9. Footer: `Reviews (N) · Last reviewed commit: sha message · Comment /alex to re-run`

Hidden markers: `<!-- alex-summary -->` identifies the card; `<!-- alex-meta:{...} -->` stores the review count.

## Inline comment

```
🟠 **P1 · Short title in sentence case**

What breaks, why (with the proof: file and line), and the fix in words.

```suggestion
replacement lines
```

<sub>Alex · bug</sub>
<!-- alex-finding:<fingerprint> -->
```

- A `suggestion` block is added only when the comment covers exactly the lines being replaced.
- Fingerprint = file + category + the original code, so a re-review never posts the same finding twice.

## Diagrams

| Type | When |
|---|---|
| flowchart | control flow or business logic changes (default) |
| sequence | calls between services, APIs, queues |
| er | database schema or data model changes |
| class | class or interface hierarchy changes |
| none | docs, config, renames, trivial changes |

Rules: at most 12 nodes, labels are short plain words, every flowchart label is quoted (`A["label"]`).
Alex validates diagrams before posting and drops a diagram rather than post a broken one.
Phase 2 adds a real render check.

## Reactions

👀 when Alex starts, 👍 when the review is posted, 😕 when it fails (then `/alex` retries).

## Status check

Name `Alex review`. Title `Confidence 4/5 · 1 P1`. Conclusion `failure` when any P0 is open and
`fail_on_p0` is on, otherwise `success`.
