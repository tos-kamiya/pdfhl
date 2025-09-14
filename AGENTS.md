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

## Session & Design Log (`dev-notes/`)

- **File:** `dev-notes/session-YYYY-MM-DD.md`
- **Primary Goal:** To create a human-readable log that captures the **"why"** behind key decisions made during a session. Design discussions and their outcomes should be the main focus.
- **Secondary Goal:** To supplement these decisions with the **"how"** by logging relevant command-line transcripts for context, debugging, or reproducibility.

### Logging Format

Entries in the session log should prioritize one of the following two formats, depending on the context.

#### 1. Design Decision (Default)

Use this format as the default way to record the outcome of discussions.

- **Structure:**
  ```markdown
  - **Topic:** {Brief description of the feature or problem}
    - **Decision:** A clear and concise summary of the final decision.
    - **Rationale:** The core reasons *why* this decision was made. Explain the benefits and trade-offs.
    - **Alternatives Considered (Optional):** Briefly mention other options that were discussed and why they were not chosen.
  ```

#### 2. Command Transcript (When Necessary)

Use this format when the specific commands, their sequence, and their output are critical for understanding an action (e.g., troubleshooting, verifying a change).

- **Structure:**
  ```markdown
  - {Time HH:MM} Ran: `{command}`
    Output:
    ```text
    {A concise excerpt of the output}
    ```
    Result: {Brief one-line explanation of the outcome}
  ```

### General Guidance
- Prioritize logging **decisions** over raw transcripts. A log full of commands with no context is not useful.
- Group related command transcripts under a single "Topic" or "Decision" entry when possible.
- Keep outputs concise.

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
