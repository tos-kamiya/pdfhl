from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple


# Exit codes aligned with discussion spec
EXIT_OK = 0
EXIT_NOT_FOUND = 1
EXIT_MULTIPLE = 2
EXIT_ERROR = 3


Rect = Tuple[float, float, float, float]


def normalize_char(c: str) -> str:
    """Normalize a single character for tolerant matching.

    - NFKC to expand ligatures and normalize width (e.g., ﬁ -> fi)
    - Remove soft hyphen (\u00AD)
    - Convert any whitespace to a single ASCII space ' '
    """
    if c == "\u00AD":  # soft hyphen
        return ""
    s = unicodedata.normalize("NFKC", c)
    out: List[str] = []
    for ch in s:
        if ch == "\u00AD":
            continue
        out.append(" " if ch.isspace() else ch)
    return "".join(out)


def pattern_from_text(
    text: str,
    *,
    literal_whitespace: bool = False,
    regex: bool = False,
    ignore_case: bool = True,
) -> re.Pattern[str]:
    """Compile a regex pattern from a (possibly literal) text.

    - If regex is False (default), the text is escaped for regex.
    - If literal_whitespace is False (default), sequences of whitespace in the
      normalized text become "\\s+" to match across newlines and multiple spaces.
    - Ligatures/width are normalized on the query as well.
    """
    if regex:
        patt = text
    else:
        norm = "".join(normalize_char(c) for c in text)
        if literal_whitespace:
            patt = re.escape(norm)
        else:
            tokens = re.split(r"\s+", norm.strip())
            patt = r"\s+".join(re.escape(tok) for tok in tokens if tok)
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(patt, flags)


def group_bboxes_to_line_rects(bboxes: Sequence[Rect], y_tol: float = 3.0) -> List[Rect]:
    """Group character bounding boxes into line rectangles.

    This is a pure function that does not depend on PyMuPDF types.
    It clusters by similar top Y (within y_tol), then merges into a single
    rectangle per line.
    """
    if not bboxes:
        return []
    sorted_boxes = sorted(bboxes, key=lambda r: (round(r[1], 1), r[0]))
    lines: List[List[Rect]] = []
    cur: List[Rect] = [sorted_boxes[0]]
    for bb in sorted_boxes[1:]:
        prev = cur[-1]
        if abs(bb[1] - prev[1]) <= y_tol:
            cur.append(bb)
        else:
            lines.append(cur)
            cur = [bb]
    lines.append(cur)

    merged: List[Rect] = []
    for line in lines:
        x0 = min(bb[0] for bb in line)
        y0 = min(bb[1] for bb in line)
        x1 = max(bb[2] for bb in line)
        y1 = max(bb[3] for bb in line)
        merged.append((x0, y0, x1, y1))
    return merged


def _build_page_text_and_map(page) -> Tuple[str, List[Rect]]:  # page: fitz.Page
    """Extract normalized text and a map from normalized-char index to bbox.

    Each produced character in the normalized string corresponds to an entry
    in the bbox map. If a source char expands to multiple normalized chars
    (e.g., ﬁ -> f + i), the same bbox is repeated to keep indices aligned.
    """
    # Lazy import to make pure logic testable without PyMuPDF installed
    import fitz  # type: ignore  # noqa: F401

    tp = page.get_textpage()
    rd = tp.extractRAWDICT()
    norm_chars: List[str] = []
    bbox_map: List[Rect] = []
    for blk in rd.get("blocks", []):
        for ln in blk.get("lines", []):
            for sp in ln.get("spans", []):
                for ch in sp.get("chars", []):
                    raw_c = ch.get("c", "")
                    bbox = ch.get("bbox")
                    if not raw_c or bbox is None:
                        continue
                    norm = normalize_char(raw_c)
                    for out in norm:
                        if out == "":
                            continue
                        norm_chars.append(out)
                        bbox_map.append(tuple(bbox))  # type: ignore[arg-type]
    return "".join(norm_chars), bbox_map


def _sanitize_rect(r: Rect, eps: float = 0.25) -> Rect | None:
    x0, y0, x1, y1 = r
    # order coordinates
    if x0 > x1:
        x0, x1 = x1, x0
    if y0 > y1:
        y0, y1 = y1, y0
    # avoid zero / negative extents
    if not (isinstance(x0, (int, float)) and isinstance(y0, (int, float)) and isinstance(x1, (int, float)) and isinstance(y1, (int, float))):
        return None
    if not (x0 < x1 and y0 < y1):
        # expand minimally if degenerate
        x1 = x0 + max(eps, 0.25)
        y1 = y0 + max(eps, 0.25)
    return (float(x0), float(y0), float(x1), float(y1))


def _add_highlight_for_range(page, rects: Sequence[Rect], label: str | None = None,
                             color_rgb: Tuple[float, float, float] | None = None,
                             opacity: float | None = None) -> bool:
    """Add a highlight annotation for the provided line rectangles.

    Converts rects into quads and adds a highlight.
    """
    import fitz  # type: ignore

    if not rects:
        return False
    # Convert each rect to a sanitized 8-tuple quad
    quads = []
    for (x0, y0, x1, y1) in rects:
        r = _sanitize_rect((x0, y0, x1, y1))
        if r is None:
            continue
        rx0, ry0, rx1, ry1 = r
        # Order: ul, ur, ll, lr (expected by PyMuPDF)
        quads.append((float(rx0), float(ry0), float(rx1), float(ry0), float(rx0), float(ry1), float(rx1), float(ry1)))
    if not quads:
        return False
    try:
        annot = page.add_highlight_annot(quads=quads)
    except Exception:
        # Fallback: draw semi-transparent rectangles if highlight fails
        for (x0, y0, x1, y1) in rects:
            r = _sanitize_rect((x0, y0, x1, y1))
            if r is None:
                continue
            rx0, ry0, rx1, ry1 = r
            rect_annot = page.add_rect_annot((rx0, ry0, rx1, ry1))
            if color_rgb is not None:
                rect_annot.set_colors(stroke=color_rgb, fill=color_rgb)
            if opacity is not None:
                rect_annot.set_opacity(opacity)
            if label:
                rect_annot.set_info(title=label, content=label)
            rect_annot.update()
        return True
    if color_rgb is not None:
        annot.set_colors(stroke=color_rgb, fill=color_rgb)
    if opacity is not None:
        annot.set_opacity(opacity)
    if label:
        annot.set_info(title=label, content=label)
    annot.update()
    return True


def _highlight_match(page, bbox_map: Sequence[Rect], start: int, end: int,
                     *, label: str | None, color_rgb: Tuple[float, float, float], opacity: float) -> bool:
    if start >= end or start < 0 or end > len(bbox_map):
        return False
    rects = group_bboxes_to_line_rects(bbox_map[start:end])
    return _add_highlight_for_range(page, rects, label=label, color_rgb=color_rgb, opacity=opacity)


def process_file(
    pdf_path: Path,
    out_path: Path | None,
    rx: re.Pattern[str],
    *,
    allow_multiple: bool,
    dry_run: bool,
    label: str | None,
    color_rgb: Tuple[float, float, float],
    opacity: float,
    report: bool,
    report_context: dict | None = None,
) -> int:
    import fitz  # type: ignore

    try:
        doc = fitz.open(pdf_path.as_posix())
    except Exception as e:  # pragma: no cover - I/O
        print(f"[ERROR] failed to open PDF: {e}", file=sys.stderr)
        return EXIT_ERROR

    matches: List[Tuple[int, int, int]] = []
    total = 0

    # First pass: collect all matches across pages
    for pi, page in enumerate(doc):
        norm_text, bbox_map = _build_page_text_and_map(page)
        for m in rx.finditer(norm_text):
            total += 1
            matches.append((pi, m.start(), m.end()))

    # Prepare effective output path (even if we may not write) for reporting
    effective_out = out_path or pdf_path.with_suffix(".highlighted.pdf")

    # Build report hits with rects (requires bbox maps), but avoid mutating PDF if dry_run
    report_hits: List[dict] = []
    if total > 0:
        by_page: dict[int, List[Tuple[int, int]]] = {}
        for pi, s, e in matches:
            by_page.setdefault(pi, []).append((s, e))

        for pi, ranges in by_page.items():
            page = doc[pi]
            norm_text, bbox_map = _build_page_text_and_map(page)
            for s, e in ranges:
                rects = group_bboxes_to_line_rects(bbox_map[s:e])
                report_hits.append(
                    {
                        "page_index": pi,
                        "page_number": pi + 1,
                        "start": s,
                        "end": e,
                        "rects": [(x0, y0, x1, y1) for (x0, y0, x1, y1) in rects],
                    }
                )

    # If requested, emit JSON report to stdout (do this before annotating / early returns)
    exit_code_preview = (
        EXIT_NOT_FOUND if total == 0 else EXIT_OK if total == 1 else EXIT_MULTIPLE
    )
    if report:
        payload = {
            "input": pdf_path.as_posix(),
            "output": effective_out.as_posix(),
            "matches": total,
            "exit_code": exit_code_preview,
            "allow_multiple": allow_multiple,
            "dry_run": dry_run,
            "hits": report_hits,
        }
        if report_context:
            payload["context"] = report_context
        print(json.dumps(payload, ensure_ascii=False))

    # Handle cardinality policy and dry-run early exits
    if total == 0:
        print("[INFO] no matches found", file=sys.stderr)
        return EXIT_NOT_FOUND

    if total > 1 and not allow_multiple:
        print(f"[INFO] multiple matches found ({total}). Use --allow-multiple to highlight anyway.", file=sys.stderr)
        return EXIT_MULTIPLE

    if dry_run:
        return EXIT_OK if total == 1 else EXIT_MULTIPLE

    # Add highlights, page by page
    by_page_apply: dict[int, List[Tuple[int, int]]] = {}
    for pi, s, e in matches:
        by_page_apply.setdefault(pi, []).append((s, e))

    for pi, ranges in by_page_apply.items():
        page = doc[pi]
        norm_text, bbox_map = _build_page_text_and_map(page)
        for s, e in ranges:
            _highlight_match(page, bbox_map, s, e, label=label, color_rgb=color_rgb, opacity=opacity)

    try:
        if out_path is None:
            out_path = pdf_path.with_suffix(".highlighted.pdf")
        doc.save(out_path.as_posix(), garbage=4, deflate=True)
        print(f"[OK] saved: {out_path}", file=sys.stderr)
    except Exception as e:  # pragma: no cover - I/O
        print(f"[ERROR] failed to save PDF: {e}", file=sys.stderr)
        return EXIT_ERROR
    finally:
        doc.close()

    return EXIT_OK if total == 1 else EXIT_MULTIPLE


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="pdfhl",
        description="Highlight a phrase in a PDF with tolerant matching (line breaks/ligatures).",
    )
    p.add_argument("pdf", type=Path, help="Input PDF file path")
    p.add_argument("--text", dest="text", type=str, default=None, help="Search text (literal). Use --regex for regex mode.")
    p.add_argument("--pattern", dest="pattern", type=str, default=None, help="Alias of --text")
    p.add_argument("--regex", action="store_true", help="Treat the text as a regular expression")

    case = p.add_mutually_exclusive_group()
    case.add_argument("--ignore-case", dest="ignore_case", action="store_true", default=True, help="Case-insensitive search (default)")
    case.add_argument("--case-sensitive", dest="case_sensitive", action="store_true", help="Case-sensitive search")

    p.add_argument("--literal-whitespace", action="store_true", help="Do not convert spaces to \\s+ (default converts for robust matching)")
    p.add_argument("--allow-multiple", action="store_true", help="If multiple matches, still highlight and write output (exit 2)")
    p.add_argument("--dry-run", action="store_true", help="Search only; do not write output")
    p.add_argument("--output", "-o", type=Path, help="Output PDF path (default: <input>.highlighted.pdf)")

    # Minimal color/label controls (RGB 0..1)
    p.add_argument("--label", type=str, default=None, help="Annotation title/content label")
    p.add_argument("--color", type=str, default="yellow", help="Highlight color name: yellow|mint|violet|red|green|blue")
    p.add_argument("--opacity", type=float, default=0.3, help="Highlight opacity (0..1)")
    p.add_argument("--report", choices=["json"], help="Emit report to stdout (json)")
    return p.parse_args(argv)


def _color_to_rgb(name: str) -> Tuple[float, float, float]:
    name = name.lower()
    table = {
        "yellow": (1.0, 0.97, 0.0),
        "mint": (0.31, 0.86, 0.71),
        "violet": (0.55, 0.47, 1.0),
        "red": (1.0, 0.2, 0.2),
        "green": (0.2, 0.8, 0.2),
        "blue": (0.2, 0.5, 1.0),
    }
    return table.get(name, table["yellow"])


def main(argv: Sequence[str] | None = None) -> int:
    ns = _parse_args(sys.argv[1:] if argv is None else argv)
    query = ns.text or ns.pattern
    if not query:
        print("[ERROR] --text or --pattern is required.", file=sys.stderr)
        return EXIT_ERROR

    ignore_case = not getattr(ns, "case_sensitive", False)
    rx = pattern_from_text(
        query,
        literal_whitespace=ns.literal_whitespace,
        regex=ns.regex,
        ignore_case=ignore_case,
    )

    code = process_file(
        ns.pdf,
        ns.output,
        rx,
        allow_multiple=ns.allow_multiple,
        dry_run=ns.dry_run,
        label=ns.label,
        color_rgb=_color_to_rgb(ns.color),
        opacity=float(ns.opacity),
        report=(ns.report == "json"),
        report_context={
            "query": query,
            "pattern": rx.pattern,
            "regex": bool(ns.regex),
            "ignore_case": not getattr(ns, "case_sensitive", False),
            "literal_whitespace": bool(ns.literal_whitespace),
        },
    )
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
