# Alex blueprint

Goal: match Greptile's paid (Pro) plan feature by feature. We can match the output format, settings,
triggers and workflow almost one to one. Bug-finding quality depends on the model and is measured by
the lab comparison, not promised. The two hard gaps are TREX (running the app in a sandbox) and a
pre-built codebase index; both are optional late phases.

## Pipeline

Every review runs 5 steps: **trigger -> gate -> engine -> card -> post**.

1. Trigger: a PR event, or a trusted user comments `/alex`
2. Gate: author is trusted, PR is open, filters and budget allow it
3. Engine: find issues with full repo context (open-code-review CLI, reads git objects, never runs PR code)
4. Card: one extra LLM call writes summary, impact, verdict, titles, score and diagram
5. Post: inline comments, the summary card (updated in place), status check, reactions

## The 10 parts

| # | Part | Greptile Pro | Alex | Phase |
|---|---|---|---|---|
| 1 | Triggers | `autoReview` open/push/rebase, drafts skipped, `@greptileai` on demand and questions, tier requests | Same `autoReview` values (default open). `/alex` re-runs. `/alex review this at plus`, `/alex <question>`, explain, tests, diagram on request. Same filter names (labels, authors, branches, keywords, ignorePatterns) | 1 (open + `/alex`), 2 (rest) |
| 2 | Engine and tiers | Base 1 credit, Plus 3, Apex 10, Auto picks | base (0.5M token cap, 1 pass), plus (2M, adds a verify pass), apex (5M, adds a second model and cross-check), auto picks by size and risk; tier rules like "into main = apex" | 1 (base), 2 (tiers) |
| 3 | Summary card | Summary, confidence 0-5, findings list, diagram, files breakdown, footer, section toggles | Same layout, see design system. Score = model judgment inside hard caps. Diagram validated before posting | 1 |
| 4 | Inline comments | Exact line, P0/P1/P2, suggested fix, Fix with AI | Same, GitHub suggestion blocks, dedupe by fingerprint, resolve fixed ones (phase 2), Fix with AI prompt (phase 2) | 1 |
| 5 | `.alex/` config | `.greptile/config.json`, `rules.md`, `files.json`, cascading, read from base branch | Same three files and field names (strictness, commentTypes, effort, autoReview, filters, instructions, rules with id/scope/severity, disabledRules, output sections, statusCheck, context.repos, autoApprove) | 2 |
| 6 | Bot identity | `greptile-apps[bot]`, 👀 then 👍 | Optional GitHub App named like `alex-review`; default `github-actions[bot]`. 👀, 👍, 😕 | 1 |
| 7 | Install anywhere | Install app, tick repos | Way A: 10-line workflow + secret per repo (`alex install <repo>`). Way B: hosted app on Render, no workflow file | 2 (A), 5 (B) |
| 8 | Learning | Reactions, replies, addressed rate, team comments | Weekly job proposes `.alex/learned.md` changes as a PR you approve. Never suppresses P0 or security | 4 |
| 9 | Safety and cost | Managed | Trusted authors only, never runs PR code, rules from base branch, per-PR and monthly caps, secrets never logged, optional merge-blocking status | 1 (core), 2 (monthly cap, base-branch rules) |
| 10 | Quality exam | Public benchmark | Lab cases (10 known bugs) re-run on every Alex change; optional monthly AACR-Bench sample | 1 (manual), 2 (automatic) |

## Extra Greptile Pro features

| Greptile | Alex | Phase |
|---|---|---|
| Status check | `Alex review` commit status, fails on open P0 if enabled | 1 |
| Questions, explain, tests | `/alex ...` thread replies with repo context | 2 |
| Custom rules | `.alex/` rules | 2 |
| Cross-repo context | `context.repos` checked out read-only | 3 |
| Security Check | Opengrep + osv-scanner results merged into the card | 3 |
| Auto-approve | Only 5/5 reviews under a risk ceiling, excluded paths never approved | 3 |
| Analytics | Static page: reviews, bugs caught, addressed rate, reactions | 4 |
| CLI | `alex review` locally | 4 |
| Fix with agent / MCP | Fix prompts first, MCP server later | 4 |
| TREX | Lite: run the repo's tests and attach failing output | 5 |
| Codebase graph | Optional search index for large repos | 5 |

## Phase exit criteria

A phase is done when: unit tests pass, the lab PR shows the new behavior, the Alex vs Greptile notes
are written in `docs/comparisons/phase-N.md`, and the phase table in `.kiro/steering/alex-product.md` is updated.
