---
inclusion: always
---

# Alex: what we are building

Alex is an AI pull request reviewer that matches Greptile's paid (Pro) plan feature by feature:
a summary card with a confidence score and diagram, inline findings with severity badges and
one-click fixes, automatic and on-demand triggers, per-repo config, learning, and safety controls.

- This repo (`Alex-mvp`, GitHub `niihhhall/alex-mvp`) is the **MVP**. We build and test phase by phase.
  Production hardening comes after the MVP proves itself.
- After each phase: open a PR on the lab repo, compare Alex with Greptile side by side, write down
  the gaps, then start the next phase.
- Full blueprint (the 10 parts and extra Greptile features): #[[file:docs/blueprint.md]]
- Design system (how every comment looks): #[[file:docs/design-system.md]]
- Engineering conventions: #[[file:docs/engineering.md]]

## Phase status

| Phase | Scope | Status |
|---|---|---|
| 1 | Triggers (open + `/alex`), summary card, inline comments, safety gate, status check | done (lab PR #1, see docs/comparisons/phase-1.md) |
| 2 | `@alexreview-ai` trigger + org + GitHub App identity, review tiers, `.alex/` config, install on any repo, questions, rerun lab cases 2-8 vs Greptile | planned |
| 3 | Security scan, auto-approve, related-repo context, `files.json` docs | planned |
| 4 | Learning from reactions/replies, analytics, CLI | planned |
| 5 | TREX-lite (run tests), codebase index, hosted app (no workflow file) | optional |

Update this table whenever a phase starts or finishes.

## Key decisions

- The engine that finds bugs is Alibaba's open-code-review CLI. Users never see that name; reviews are signed "Alex".
- Model: Fireworks `accounts/fireworks/models/deepseek-v4p1-flash` for review and card. Judge for benchmarks: `glm-5p3-flash`.
- Phase 1 trigger is `/alex` and the bot posts as `github-actions[bot]`. Never use `@alex`: it notifies a real GitHub user named alex.
- Phase 2 (decided): switch to `@alexreview-ai` like Greptile's `@greptileai`. The user creates a free GitHub
  organization `alexreview-ai` to reserve the name (free as of Oct 2026) and a GitHub App of the same name, so
  comments come from `alexreview-ai[bot]`. Keep `/alex` as an alias, ignore comments from bots, update footer and docs.
- Alex only reads PR code, never runs it. Only OWNER/MEMBER/COLLABORATOR can trigger it.
- Greptile's free Starter plan covers unlimited repos (50 credits/month, 1 developer). We used it for comparison.

## Places

- Lab repo for comparisons: https://github.com/niihhhall/mark-ai-review-lab (public, MIT, old mark.ai snapshots, redacted)
- Lab cases and answer key: `docs/lab-cases.md`
- Benchmark harness: `evals/aacr/`. Lab tooling: `evals/lab/`. Local card previews: `scripts/preview-case.ps1`.
- Engine source (read-only reference): `vendor/review-engine/`.
- Local only, never commit: `workspace/` (private mark.ai source, lab repo, snapshots, results, previews),
  `vendor/`, `evals/aacr/aacr-bench/`, any `.env`.
