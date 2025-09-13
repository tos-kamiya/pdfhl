# pdfhl

PDF text highlighter with progressive, tolerant phrase matching.

## Overview

`pdfhl` searches for phrases in a PDF and highlights matches. Its search is robust to common PDF quirks and formatting variations.

- **Progressive Phrase Matching**: Finds phrases even when words are separated by line breaks or other text. It works by matching chunks of words (e.g., 3-word, then 2-word chunks) and chaining them together.
- **Tolerant Normalization**: Normalizes ligatures, character width (e.g., `ﬁ` → `f` + `i`), hyphens, and quotes.
- **Selection Control**: Choose to highlight only the most compact (shortest) match in the document or all possible matches.
- **Safe by Design**: Never overwrites the input PDF; always writes to a new file.

## Installation

```bash
pip install pdfhl
```

Requires Python 3.10+ and [PyMuPDF](https://pypi.org/project/PyMuPDF/) (installed automatically as a dependency).

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

## Development

Run tests:
```bash
pytest -q
```

## License

`pdfhl` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.