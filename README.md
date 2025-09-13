# pdfhl

PDF text highlighter with tolerant matching (line breaks, ligatures, flexible whitespace).

[![PyPI - Version](https://img.shields.io/pypi/v/pdfhl.svg)](https://pypi.org/project/pdfhl)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pdfhl.svg)](https://pypi.org/project/pdfhl)

---

## Overview

`pdfhl` searches for text in a PDF and highlights matches. It is robust to common PDF quirks:
- Normalizes ligatures/width (e.g., ﬁ → f + i)
- Matches across newlines and multiple spaces (configurable)
- Supports literal or regex-based queries
- Never overwrites the input PDF; always writes a new file

## Installation

```bash
pip install pdfhl
```

Requires Python 3.10+ and [PyMuPDF](https://pypi.org/project/PyMuPDF/) (installed automatically as a dependency).

## Quick Start

Highlight a single phrase (case-insensitive by default; whitespace is flexible):

```bash
pdfhl input.pdf --text "Deep Learning" -o output.pdf
```

Use a regular expression (matches across whitespace by yourself):

```bash
pdfhl input.pdf --text "Deep\s+Learning" --regex -o output.pdf
```

Literal whitespace (don’t collapse to `\s+`):

```bash
pdfhl input.pdf --pattern "alpha  beta" --literal-whitespace -o out.pdf
```

Style and report:

```bash
pdfhl input.pdf --text "method" --color "#FFEE00" --opacity 0.2 --label "Method" --report json -o out.pdf
```

Apply multiple highlights in one pass via JSON recipe:

```bash
pdfhl input.pdf --recipe recipe.json -o out.pdf
```

See more in `examples/`:
- `examples/simple-recipe-array.json`
- `examples/recipe-with-items-object.json`

## CLI Reference

Entry point: `pdfhl = pdfhl.pdfhl:main`

```
pdfhl PDF [--text TEXT | --pattern TEXT | --recipe JSON] [options]
```

Modes
- Single-item mode (default)
  - `--text TEXT` or `--pattern TEXT` (alias)
  - `--regex` to treat the text as a regular expression
- Recipe mode
  - `--recipe path/to/recipe.json`

Common options
- `--ignore-case` / `--case-sensitive`
  - Default: ignore case
- `--literal-whitespace`
  - Default: flexible whitespace; when not set, sequences of whitespace in the query are compiled to `\s+`
- `--allow-multiple`
  - Default: single match required; without this flag, multiple matches will not be highlighted and exit code becomes 2
- `--dry-run`
  - Search only; do not write output
- `-o, --output PATH`
  - Output PDF path; default is `<input>.highlighted.pdf`
- `--label STR`
  - Annotation title/content label
- `--color VAL`
  - Color by name (`yellow|mint|violet|red|green|blue`), hex `#RRGGBB`, or `r,g,b` (each 0..1)
- `--opacity FLOAT`
  - Highlight opacity (0..1), default `0.3`
- `--report json`
  - Emit a JSON report to stdout

Output policy
- The input PDF is never modified. The tool refuses to overwrite the input path; specify a different `-o/--output`.

Exit codes
- `0`: OK
- `1`: Not found (e.g., any recipe item had zero matches)
- `2`: Multiple matches (blocked because `--allow-multiple` was not set)
- `3`: Error (open/save failures, invalid paths, overwrite refusal, etc.)

## JSON Recipe Format (`--recipe`)

You can pass either a top-level array of items or an object with `items: [...]`.

Top-level array example:

```json
[
  {"text": "Introduction", "color": "mint"},
  {"text": "Threats", "color": "red", "allow_multiple": true}
]
```

Object with `items` example:

```json
{
  "items": [
    {"text": "Experiment", "color": "green", "label": "Experiment"},
    {"text": "Conclusion", "color": "violet", "opacity": 0.25}
  ]
}
```

Per-item fields
- `text` or `pattern` (string, required)
- `regex` (bool, default `false`)
- `ignore_case` (bool, default `true`)
- `literal_whitespace` (bool, default `false`)
- `allow_multiple` (bool, default falls back to CLI `--allow-multiple`)
- `label` (string | null)
- `color` (string | null)
  - Color names: `yellow|mint|violet|red|green|blue`
  - Hex: `#RRGGBB`
  - CSV floats: `r,g,b` each in `[0.0 .. 1.0]`
- `opacity` (float, default falls back to CLI `--opacity`)

Behavior
- Matching is tolerant by default: query whitespace is compiled to `\s+` to match across newlines/multiple spaces. Use `literal_whitespace: true` to disable this.
- If a recipe item has zero matches, the overall exit code becomes `1`.
- If a recipe item has multiple matches and `allow_multiple` is not set (effective `false`), that item will not be highlighted and the overall exit code becomes `2`.

## JSON Report (`--report json`)

Single-item mode output

```json
{
  "input": "input.pdf",
  "output": "output.pdf",
  "matches": 1,
  "exit_code": 0,
  "allow_multiple": false,
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
    "pattern": "...",
    "regex": false,
    "ignore_case": true,
    "literal_whitespace": false
  }
}
```

Recipe mode output (aggregate)

```json
{
  "input": "input.pdf",
  "output": "output.pdf",
  "items": [
    {
      "index": 0,
      "query": "Introduction",
      "pattern": "...compiled...",
      "regex": false,
      "ignore_case": true,
      "literal_whitespace": false,
      "matches": 1,
      "allow_multiple": false,
      "hits": [
        {"page_index": 0, "page_number": 1, "start": 10, "end": 22, "rects": [[...]]}
      ]
    }
  ]
}
```

Notes
- `page_index` is zero-based; `page_number` is one-based.
- `start`/`end` are indices into the normalized text stream; `rects` contains merged line rectangles for each match.

## Development

Run tests:

```bash
pytest -q
```

## License

`pdfhl` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
