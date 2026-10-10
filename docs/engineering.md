# Engineering conventions

- **Python 3.10+, standard library only** in `alex/`. No pip install on the runner, nothing to break.
- Layout:

  | Path | What | Committed |
  |---|---|---|
  | `action.yml` | The GitHub Action other repos call | yes |
  | `alex/` | Review logic: card, scoring, inline comments, GitHub client | yes |
  | `tests/` | Unit tests | yes |
  | `examples/workflows/` | Workflow file users copy into their repo | yes |
  | `docs/` | Blueprint, design system, lab cases, phase comparisons, assets | yes |
  | `evals/aacr/` | AACR-Bench harness (the benchmark clone itself is local only) | scripts only |
  | `evals/lab/` | Lab tooling: run engine on a case, redact and scan snapshots | yes |
  | `scripts/` | Developer helpers, like local card previews | yes |
  | `vendor/review-engine/` | Local clone of the engine, for reading its source | no |
  | `workspace/` | Private source, lab snapshots, results, previews | no |
- Tests: `python -m unittest discover -s tests -v`. Every module in `alex/` has tests for its pure logic.
- Local dry run: `python -m alex.main preview --ocr-json <file> --diff <file> --title "..." --out <dir>`
  renders the card and inline comments without touching GitHub.
- Text rules: no em or en dashes in any output (`alex.text.no_dashes` runs on every posted body), LF line endings.
- Secrets: only via environment variables or GitHub secrets. Never print a key. `.env` files are gitignored.
- The engine is pinned (`ocr_version` input) so a new engine release cannot change reviews without us noticing.
- Every change to prompts or scoring: re-run the lab cases and note the result in `docs/comparisons/`.
