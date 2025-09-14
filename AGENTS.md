# Repository Guidelines

## Project Structure & Module Organization
- `src/pdfhl/`: Main package. Put CLI entry in `src/pdfhl/pdfhl.py`.
- `tests/`: Add `test_*.py` here.
- Root: `pyproject.toml`, `uv.lock`, `README.md`.

## Coding Style & Naming Conventions
- Python 3.10+. Follow PEP 8 with 4‑space indentation; add type hints where practical.
- Names: modules/files `snake_case.py`; functions/variables `snake_case`; classes `CamelCase`; constants `UPPER_SNAKE`.

## Testing Guidelines
- Framework: pytest. Focus on pure logic (coordinate transforms, projections, phase angle math).
- Location & names: put tests in `tests/` as `test_*.py`.
- Rendering: skip or mock PyQt5 UI code. Run `pytest` or use the coverage command above.

## Commit & Pull Request Guidelines
- Commits: use Conventional Commits (e.g., `feat:`, `fix:`, `docs:`, `chore:`).
- Pull requests: include a clear description and rationale; reference issues (e.g., `Closes #123`); add repro/validation steps and screenshots or short clips for UI changes; keep scope small and focused.

### Commit Message Format
- Subject: a single line using Conventional Commits (imperative, concise). Example:
  - `feat: improve robust PDF text matching`
- Body: optional, a few short lines separated by a blank line from the subject. Use bullets for specifics; wrap at ~72 chars.
  - Example:
    - `- Normalize dashes/quotes; collapse line-break hyphenation`
    - `- Add auto phrase-split fallback (order, gap, ratio)`
    - `- Add tests; help epilog`
- Tips:
  - No trailing period in the subject; keep it ≤ 50 chars when possible.
  - Use present tense, active voice ("add", "fix", "update").
  - Reference issues in the body (e.g., `Closes #123`).
  - One logical change per commit; split unrelated changes.

## Session Logging (Raw‑ish Notes in `dev-notes/`)
- Goal: Leave a human‑readable, raw‑ish session record under `dev-notes/session-YYYY-MM-DD.md` (not a full transcript, but close).
- When starting work:
  - Create `dev-notes/session-YYYY-MM-DD.md` and add a short header (date, scope).
- While working (for each meaningful action):
  - Append a small block capturing what was done with a transcript feel:
    - Time (HH:MM)
    - Ran: the exact command (in backticks)
    - Output (excerpt) as a fenced block, keep raw lines; truncate if too long
    - Optional: Why / Result / Next (1–2 lines each)
  - Example snippet to append:
    
    ```
    - 10:22 Ran: `git log --oneline -n 3`
      Output:
      ```text
      abcd123 feat: add X
      efgh456 fix: Y
      ....
      ```
      Why: Inspect recent commits
      Result: Verified last change
    ```

- Group related commands under a short heading when it helps scanability.
- Redact sensitive info (tokens, secrets, private paths) if they appear in output.
- Prefer brevity for rationale; keep the output raw‑ish.
- At the end, add a short summary (commits, tags, pushes, follow‑ups).
- Optional: If you also capture a full terminal log (`script`, `tee`, etc.), reference the file at the top of the markdown and paste only key excerpts.

Notes:
- Historical session logs may exist under `docs/` (e.g., `docs/session-YYYY-MM-DD.md`). New logs should go to `dev-notes/`.

## Decision Safeguards (Strong Stop)
- When a requested change is risky, ambiguous, or conflicts with this guide, the agent must issue a prominent HARD STOP warning with emojis and pause work until explicit confirmation.
- Trigger examples:
  - Ambiguity in requirements or library choice (e.g., sentence vs token segmentation)
  - Irreversible/destructive actions (history rewrites, large deletes)
  - Large refactors without tests or clear rollback
  - Security-sensitive or dependency changes without validation
  - Cross‑cutting API changes impacting many files
  - Conflicts with testing conventions or this AGENTS.md
- Process:
  - Post a stop message that summarizes the risk and proposes safer options.
  - Request explicit approval keywords: APPROVE / ADJUST / SPLIT / SKIP.
  - Prefer incremental changes with minimal tests and/or feature flags.
  - Log the decision point and commands in `dev-notes/session-YYYY-MM-DD.md`.
- Example warning:
  
  ```text
  ⛔️ HARD STOP — Risky/ambiguous change detected
  - Issue: Library mismatch (sentence vs token segmentation) could cause a broad revert.
  - Risk: High scope + unclear intent; potential breakage across components.
  - Proposal: Clarify target behavior, add a minimal test, then proceed incrementally.
  Please reply with:
  - APPROVE to proceed as-is,
  - ADJUST with clarified constraints,
  - SPLIT to stage into smaller PRs, or
  - SKIP to avoid this change.
  ```
- Scope: Applies to the entire repository. More-nested AGENTS.md files may refine but not weaken these safeguards.
