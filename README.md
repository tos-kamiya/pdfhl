# pdfhl

PDF text highlighter with progressive, tolerant phrase matching.

**Designed for AI agents**  (such as codex or gemini-cli):
`pdfhl` was created to be easily used inside LLM-driven workflows. The tool’s robust matching (progressive phrase matching, tolerant normalization) ensures that AI agents can highlight text reliably **without breaking their workflow**.

While you can of course run `pdfhl` manually, its main purpose is to serve as a reliable building block, such as academic paper highlighting and other automated reading tasks.

## Overview

`pdfhl` searches for phrases in a PDF and highlights matches. Its search is robust to common PDF quirks and formatting variations.

- **Progressive Phrase Matching**: Finds phrases even when words are separated by line breaks or other text. It works by matching chunks of words (e.g., 3-word, then 2-word chunks) and chaining them together.
- **mt5-based Segmentation (default)**: Query phrases are split into multilingual SentencePiece subwords using `google/mt5-base`, which significantly improves matching for Japanese and mixed-language text. Minimum coverage defaults to 3 subwords.
- **Tolerant Normalization**: Normalizes ligatures, character width (e.g., `ﬁ` → `f` + `i`), hyphens, and quotes.
- **Selection Control**: Choose to highlight only the most compact (shortest) match in the document or all possible matches.
- **Safe by Design**: Never overwrites the input PDF; always writes to a new file.

## Installation

Install via pipx from GitHub (recommended):

```bash
pipx install git+https://github.com/tos-kamiya/pdfhl@v0.3.0
```

To track the latest main branch instead of the tagged release:

```bash
pipx install --force git+https://github.com/tos-kamiya/pdfhl
```

Requires Python 3.10+. pipx installs into an isolated environment and exposes the `pdfhl` CLI on your PATH. To upgrade later, rerun the same `pipx install` command with `--force`.

`pdfhl` uses `google/mt5-base` for subword segmentation by default. The Python packages `transformers` and `sentencepiece` are declared as dependencies and will be installed automatically. For offline environments, pre-download the model and pass `--mt5-model /path/to/mt5-base` (see below).

## Quick Start

Highlight a single phrase. By default, finds the shortest match, ignoring case.

```bash
pdfhl input.pdf --text "Deep Learning" -o output.pdf
```

Highlight all occurrences of a phrase:

```bash
pdfhl input.pdf --text "Deep Learning" --all-matches -o output.pdf
```

Style the highlight and add a label:

```bash
pdfhl input.pdf --text "evaluation metrics" --color "#FFEE00" --opacity 0.2 --label "Metrics" -o out.pdf
```

Apply multiple highlights in one pass via a JSON recipe:

```bash
pdfhl input.pdf --recipe recipe.json -o out.pdf
```

See more in `examples/`:
- `examples/simple-recipe-array.json`
- `examples/recipe-with-items-object.json`

## Use Case: Academic Paper Highlighting

One key use case of this tool is to **highlight important parts of academic papers** (approach, experiment, threats to validity) for quick review.

We provide helper resources under `extra-utils/`:

* `extra-utils/pdftopages` — splits a PDF into per-page text (Markdown)
* `extra-utils/prompt-paper-highlights.txt` — a prompt that guides the LLM to identify important sentences and apply highlights

### How to Use (Interactive)

Just paste the prompt into your LLM CLI (codex, gemini-cli, etc.), replace the file name, and run interactively.

1. Copy the contents of `extra-utils/prompt-paper-highlights.txt`.
2. Replace the placeholder `{file.pdf}` at the top with the actual filename of your paper.
3. Paste it into codex or gemini-cli.
4. Make sure `pdftopages` is either in a directory on your `$PATH`, **or** adjust the prompt to call it using its full path.

This interactive style lets you “poke” the CLI with the prompt, tweak the filename or script path as needed, and let the LLM guide the process (splitting pages, finding important sentences, applying highlights with `pdfhl`). No additional scripting is required.

### Color Convention

The provided prompt uses three colors:

* **Blue** — Approach
* **Green** — Experiment
* **Red** — Threats to validity

**Examples**

* [docs/icpc-2022-zhu.highlighted.pdf](docs/icpc-2022-zhu.highlighted.pdf)
* [docs/kbse-202405-kamiya.highlighted.pdf](docs/kbse-202405-kamiya.highlighted.pdf) (in Japanese)

## CLI Reference

```
pdfhl PDF [--text TEXT | --recipe JSON] [options]
```

**Mode**
- **Single-item mode**:
  - `--text TEXT` or `--pattern TEXT` (alias for `--text`)
- **Recipe mode**:
  - `--recipe path/to/recipe.json`

**Common Options**
- `--ignore-case` / `--case-sensitive`
  - Default: ignore case.
- `--shortest` / `--all-matches`
  - Controls selection. Default is `--shortest`, which finds the single best-scoring (most compact) match in the entire document. `--all-matches` highlights every valid match found.
- `--dry-run`
  - Search only; do not write an output file.
- `-o, --output PATH`
  - Output PDF path. Default is `<input>.highlighted.pdf`.
- `--label STR`
  - Annotation title/content label.
- `--color VAL`
  - Color by name (`yellow|mint|violet|red|green|blue`), hex `#RRGGBB`, or `r,g,b` (each 0..1).
- `--opacity FLOAT`
  - Highlight opacity (0..1), default `0.3`.
- `--report json`
  - Emit a JSON report to stdout.

**Segmentation (mt5) Options**
- `--mt5-model PATH_OR_ID`
  - mt5 tokenizer model path or hub ID. Default: `google/mt5-base`. Can also set env `PDFHL_MT5_MODEL`.
- `--no-mt5`
  - Disable mt5-based segmentation. Fallback uses a simple whitespace split. You can also set env `PDFHL_USE_MT5=0`.

Notes
- By default, queries are segmented into mt5 subwords and then matched with `\s*` between subwords to tolerate missing spaces/line breaks.
- Minimum coverage is 3 subwords; tune chunking via `progressive_kmax` (default 3) in recipes.

**Output Policy**
- The input PDF is never modified. The tool refuses to overwrite the input path; specify a different `-o/--output`.

**Exit Codes**
- `0`: OK
- `1`: Not found (any recipe item had zero matches)
- `2`: (Unused)
- `3`: Error (open/save failures, invalid paths, overwrite refusal, etc.)

## JSON Recipe Format (`--recipe`)

You can pass either a top-level array of items or an object with an `items: [...]` key. All searches use the progressive matching algorithm.

**Top-level array example:**
```json
[
  {"text": "Introduction", "color": "mint"},
  {"text": "Threats to Validity", "color": "red", "select_shortest": false}
]
```

**Object with `items` example:**
```json
{
  "items": [
    {"text": "Experiment", "color": "green", "label": "Experiment"},
    {"text": "Conclusion", "color": "violet", "opacity": 0.25}
  ]
}
```

**Per-item fields:**
- `text` or `pattern` (string, required): The phrase to search for.
- `ignore_case` (bool, default `true`): Whether to perform a case-insensitive search.
- `select_shortest` (bool, default `true`): If `true`, highlights only the single best match. If `false`, highlights all found matches (equivalent to `--all-matches`).
- `label` (string | null): Annotation label.
- `color` (string | null): Color name, hex, or `r,g,b` float values.
- `opacity` (float | null): Highlight opacity (0..1). Falls back to the CLI default if not set.
- `progressive_kmax` (int, default `3`): (Advanced) Max words in a search chunk.
- `progressive_max_gap_chars` (int, default `200`): (Advanced) Max characters allowed in a gap between matched chunks.

Additional notes
- Query tokenization uses mt5 subwords. Coverage checks are in subwords; default minimum is 3.

## JSON Report (`--report json`)

**Single-item mode output:**
```json
{
  "input": "input.pdf",
  "output": "output.pdf",
  "matches": 1,
  "exit_code": 0,
  "dry_run": false,
  "hits": [
    {
      "page_index": 0,
      "page_number": 1,
      "start": 123,
      "end": 135,
      "rects": [[x0, y0, x1, y1], ...]
    }
  ],
  "context": {
    "query": "...",
    "ignore_case": true,
    "selection": "shortest"
  }
}
```

**Recipe mode output (aggregate):**
```json
{
  "input": "input.pdf",
  "output": "output.pdf",
  "items": [
    {
      "index": 0,
      "query": "Introduction",
      "matches": 1,
      "hits": [
        {"page_index": 0, "page_number": 1, "start": 10, "end": 22, "rects": [[...]]}
      ],
      "progressive_search": true,
      "progressive_kmax": 3,
      "progressive_max_gap_chars": 200,
      "select_shortest": true
    }
  ]
}
```

**Notes**
- `page_index` is zero-based; `page_number` is one-based.
- `start`/`end` are indices into the normalized text stream of a page.

## Library API

`pdfhl` now exposes a lightweight importable API for scripting.

Highlight a single phrase and save in one call:

```python
from pathlib import Path
from pdfhl import highlight_text

outcome = highlight_text(
    Path("paper.pdf"),
    "threats to validity",
    output=Path("paper.marked.pdf"),
    color="#ffeb3b",
    label="Important",
)
print(outcome.matches, outcome.saved_path)
```

For batch scenarios, open a document once and apply multiple queries:

```python
from pdfhl import PdfHighlighter

with PdfHighlighter.open("paper.pdf") as hl:
    hl.highlight_text("introduction", color="mint")
    hl.highlight_text("findings", color="violet", progressive_select_shortest=False)
    summary = hl.save("paper.highlighted.pdf")

print(summary.matches)
```

Context managers are optional. You can manage the lifecycle explicitly if you prefer:

```python
from pdfhl import PdfHighlighter

hl = PdfHighlighter.open("paper.pdf")
try:
    hl.highlight_text("abstract", color="#ff9800", label="Abstract")
    hl.highlight_text("future work", allow_multiple=False)
    outcome = hl.save("paper.highlighted.pdf")
finally:
    hl.close()

print(outcome.matches)
```

### `highlight_text` arguments

`pdfhl.highlight_text()` returns a `HighlightOutcome` and accepts the following top-level parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pdf_path` | `str | Path` | — | Source PDF to read. |
| `text` | `str` | — | Query to search and highlight. |
| `output` | `Path | None` | `None` | Destination PDF; defaults to `<input>.highlighted.pdf` when omitted. |
| `dry_run` | `bool` | `False` | Return matches without modifying or saving the PDF. |

`PdfHighlighter.highlight_text()` shares the same keyword arguments below; the standalone function forwards them as `**kwargs`.

| Keyword | Type | Default | Description |
|---------|------|---------|-------------|
| `color` | `str | Sequence[float] | None` | `"#ffeb3b"` | Highlight color. Accepts named presets (`yellow`, `mint`, `violet`, `red`, `green`, `blue`), `#RRGGBB`, or three floats in 0..1 (tuple/list or comma string). |
| `label` | `str | None` | `None` | Annotation title/content shown by PDF viewers; leave `None` to omit. |
| `allow_multiple` | `bool` | `True` | If `False`, only the first match is highlighted. |
| `ignore_case` | `bool` | `True` | Case-insensitive matching when `True`. |
| `literal_whitespace` | `bool` | `False` | Treat the query’s whitespace literally when building regex patterns. |
| `regex` | `bool` | `False` | Interpret `text` as a regex pattern instead of a literal phrase. |
| `progressive` | `bool` | `True` | Use tolerant progressive search (`True`) or literal regex search (`False`). |
| `progressive_kmax` | `int` | `3` | Maximum subword chunk size for progressive search. |
| `progressive_max_gap_chars` | `int` | `200` | Max allowed character gap between progressive segments. |
| `progressive_min_total_words` | `int` | `3` | Minimum matched subwords required when using progressive search. |
| `progressive_select_shortest` | `bool` | `True` | Select global best match per query (`True`) or keep all ranges (`False`). |
| `opacity` | `float` | `0.3` | Highlight opacity (0..1). |
| `dry_run` | `bool` | `False` | Inspect matches without applying annotations (same effect as the top-level flag on the free function). |
| `page_filter` | `Callable[[PageInfo], bool] | None` | `None` | Optional filter to restrict search to specific pages. |

## Development

### Running Tests

You can run the test suite without installing the package itself. Choose either uv or plain venv/pip.

Option A — uv (recommended):
```bash
# Create and activate a virtualenv in .venv/
uv venv
source .venv/bin/activate

# Install pytest only (tests avoid heavy deps)
uv pip install pytest

# Run tests
pytest -q
```

Option B — Python built-in venv/pip:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip pytest
pytest -q
```

Notes
- Tests focus on pure logic and do not require PyMuPDF or transformers. You may see harmless warnings if those libraries are not installed.
- If you prefer, you can run without activating the venv by using the full path, e.g. `.venv/bin/pytest -q`.

For offline use of mt5, pre-download the model directory (e.g., with `transformers-cli` or by copying from a machine with cache) and run:

```bash
pdfhl input.pdf --text "..." --mt5-model /path/to/google/mt5-base
```

## License

`pdfhl` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
