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
| 2 | GitHub App `alexreview-ai` (no org), Render hosting (install by ticking repos), security locks, phase 1 gaps (shorter summary, re-run link, diagram check), review tiers, `.alex/` config, questions, rerun lab cases 2-8 vs Greptile | planned |
| 3 | Security scan, auto-approve, related-repo context, `files.json` docs | planned |
| 4 | Learning from reactions/replies, analytics, CLI | planned |
| 5 | TREX-lite (run tests), codebase index, hosted app (no workflow file) | optional |

Update this table whenever a phase starts or finishes.

## Key decisions

- The engine that finds bugs is Alibaba's open-code-review CLI. Users never see that name; reviews are signed "Alex".
- Model: Fireworks `accounts/fireworks/models/deepseek-v4p1-flash` for review and card. Judge for benchmarks: `glm-5p3-flash`.
- Phase 1 trigger is `/alex` and the bot posts as `github-actions[bot]`. Never use `@alex`: it notifies a real GitHub user named alex.
- Phase 2 identity (decided): **no GitHub organization**. Only a GitHub App named `alexreview-ai` under the
  personal account, set to "Only on this account", so comments come from `alexreview-ai[bot]`.
  Main trigger stays `/alex`; also accept `@alexreview-ai` as plain text (drop it if a stranger ever registers
  that username). Ignore comments from bots so Alex never triggers itself.
- Phase 2 hosting (decided): **Render** (user has $500 credits and a Pro workspace). Greptile-style install:
  tick repos in the app, no workflow file or secrets per repo. Services via `render.yaml`: Web Service
  (webhook receiver, Starter), Key Value (queue), Background Worker (reviewer, Standard). Roughly $40/month.
  The Phase 1 Action stays in the repo as a fallback. Make `alex-mvp` private once Render deploy works.
- Security locks (required in phase 2): app installable only on this account; server allowlist of account
  `niihhhall`; verify GitHub webhook signatures; trusted authors only (OWNER/MEMBER/COLLABORATOR); skip PRs from
  outsiders unless an owner comments `/alex`; minimal app permissions (contents read; pull requests, issues,
  statuses write; never write code); keys only in Render secrets; per-review and monthly token caps
  (post "budget reached" instead of reviewing); never run PR code.
- Auto-approve (phase 3): approving is not merging; Alex never merges. Off by default; never for outsider PRs;
  only 5/5 with zero findings at Low risk; never for sensitive paths (auth, payments, migrations,
  `.github/workflows`, secrets); rules read from the base branch; dismiss approval on new commits.
  Same model as Greptile's auto-approve, plus the outsider rule Greptile leaves to the user.
- Alex only reads PR code, never runs it. Only OWNER/MEMBER/COLLABORATOR can trigger it.
- Greptile's free Starter plan covers unlimited repos (50 credits/month, 1 developer). We used it for comparison.

## Places

- Lab repo for comparisons: https://github.com/niihhhall/mark-ai-review-lab (public, MIT, old mark.ai snapshots, redacted)
- Lab cases and answer key: `docs/lab-cases.md`
- Benchmark harness: `evals/aacr/`. Lab tooling: `evals/lab/`. Local card previews: `scripts/preview-case.ps1`.
- Engine source (read-only reference): `vendor/review-engine/`.
- Local only, never commit: `workspace/` (private mark.ai source, lab repo, snapshots, results, previews),
  `vendor/`, `evals/aacr/aacr-bench/`, any `.env`.
