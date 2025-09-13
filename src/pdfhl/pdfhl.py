from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple, Any


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
    - Normalize dash-like characters to '-'
    - Normalize curly quotes to straight quotes
    - Convert any whitespace to a single ASCII space ' '
    """
    if c == "\u00AD":  # soft hyphen
        return ""
    s = unicodedata.normalize("NFKC", c)
    out: List[str] = []
    for ch in s:
        if ch == "\u00AD":
            continue
        # unify whitespace
        if ch.isspace():
            out.append(" ")
            continue
        # unify dashes
        if ch in {"\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212", "\uFE63", "\uFF0D"}:
            out.append("-")
            continue
        # unify quotes
        if ch in {"\u2018", "\u2019", "\u2032", "\u275B", "\uFF07"}:  # single quotes family
            out.append("'")
            continue
        if ch in {"\u201C", "\u201D", "\u2033", "\u275D", "\uFF02"}:  # double quotes family
            out.append('"')
            continue
        out.append(ch)
    return "".join(out)


def _collapse_hyphen_linebreak(norm_chars: List[str], bbox_map: List[Rect] | None = None) -> Tuple[List[str], List[Rect] | None]:
    """Collapse hyphenation inserted at line breaks: "differ- ent" -> "different".

    Rule: if we see a hyphen ('-') followed by one or more spaces, and both the
    previous non-space and the next non-space are alphabetic, remove the hyphen
    and the following spaces. This preserves true in-word hyphens (which lack
    trailing whitespace in the character stream).

    If bbox_map is provided, corresponding entries are removed to keep indices
    aligned; returns possibly new bbox_map.
    """
    out_chars: List[str] = []
    out_bbox: List[Rect] | None = [] if bbox_map is not None else None
    i = 0
    n = len(norm_chars)
    while i < n:
        ch = norm_chars[i]
        if ch == '-' and (i + 1) < n:
            # Decide whether this is a line-break hyphenation to be collapsed
            # Gather context: prev non-space, next non-space index, and whether next is on a new line
            j = len(out_chars) - 1
            while j >= 0 and out_chars[j] == ' ':
                j -= 1
            prev_alpha = j >= 0 and out_chars[j].isalpha()

            # Determine next non-space index in input
            k = i + 1
            while k < n and norm_chars[k] == ' ':
                k += 1
            next_alpha = k < n and norm_chars[k].isalpha()

            # Heuristic: check if current token already contains a hyphen -> likely a compound, keep hyphen
            token_has_hyphen = False
            if j >= 0:
                t = j
                while t >= 0 and out_chars[t] != ' ':
                    if out_chars[t] == '-':
                        token_has_hyphen = True
                        break
                    t -= 1

            # Detect explicit line break via bbox y jump if available (no spaces case)
            y_jump_linebreak = False
            if bbox_map is not None and (i + 1) < len(bbox_map):
                try:
                    _, y_h, _, _ = bbox_map[i]
                    _, y_next, _, _ = bbox_map[i + 1]
                    y_jump_linebreak = (y_next - y_h) > 4.0  # points threshold
                except Exception:
                    y_jump_linebreak = False

            should_collapse = False
            if prev_alpha and next_alpha and not token_has_hyphen:
                # Case A: hyphen followed by spaces then letters (common soft wrap)
                if (i + 1) < n and norm_chars[i + 1] == ' ':
                    should_collapse = True
                # Case B: immediate next letter but on a new line per bbox
                elif y_jump_linebreak:
                    should_collapse = True

            if should_collapse:
                # If spaces follow, skip them; otherwise just skip hyphen
                skip_to = i + 1
                while skip_to < n and norm_chars[skip_to] == ' ':
                    skip_to += 1
                i = skip_to
                continue
        # default: keep char
        out_chars.append(ch)
        if out_bbox is not None and bbox_map is not None:
            out_bbox.append(bbox_map[i])
        i += 1
    return out_chars, out_bbox if out_bbox is not None else None


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


def find_sequences_in_text(
    text: str,
    patterns: Sequence[re.Pattern[str]],
    *,
    max_gap_chars: int = 200,
) -> List[Tuple[int, int]]:
    """Find ordered sequences of patterns appearing close together in text.

    Returns a list of (start, end) covering from the first part's start to the
    last part's end for each sequence instance found.

    Strategy:
    - Precompute all matches for each part.
    - Greedily chain matches in order, requiring start(next) - end(prev) <= max_gap_chars.
    - Emit all chains found (could be multiple if overlaps exist).
    """
    if not patterns:
        return []
    parts_matches: List[List[Tuple[int, int]]] = []
    for rx in patterns:
        parts_matches.append([(m.start(), m.end()) for m in rx.finditer(text)])
    if any(len(lst) == 0 for lst in parts_matches):
        return []

    results: List[Tuple[int, int]] = []

    def chain_from(idx_part: int, prev_end: int) -> List[Tuple[int, int]]:
        out: List[Tuple[int, int]] = []
        for s, e in parts_matches[idx_part]:
            if s >= prev_end and (s - prev_end) <= max_gap_chars:
                out.append((s, e))
        return out

    # For each occurrence of first part, try to build a full chain
    for s0, e0 in parts_matches[0]:
        chain = [(s0, e0)]
        ok = True
        prev_end = e0
        for pi in range(1, len(parts_matches)):
            cands = chain_from(pi, prev_end)
            if not cands:
                ok = False
                break
            # choose the earliest valid candidate to keep it simple; still emits multiple sequences by trying all s0
            s, e = cands[0]
            chain.append((s, e))
            prev_end = e
        if ok:
            results.append((chain[0][0], chain[-1][1]))
    return results


def split_text_into_phrases(text: str, phrase_len: int = 3, *, start: int = 0) -> List[str]:
    """Split a long query text into phrases of fixed word length after normalization.

    - Normalizes like search does (NFKC, dash/quote unify, whitespace to single space).
    - Returns non-overlapping groups of words joined by a single space.
    """
    norm = "".join(normalize_char(c) for c in text)
    tokens = [t for t in re.split(r"\s+", norm.strip()) if t]
    if not tokens:
        return []
    if phrase_len <= 1:
        phrase_len = 1
    phrases: List[str] = []
    i = max(0, min(start, max(0, len(tokens) - 1)))
    n = len(tokens)
    while i < n:
        j = min(i + phrase_len, n)
        phrases.append(" ".join(tokens[i:j]))
        i = j
    return phrases


def find_fuzzy_sequence_in_text(
    text: str,
    patterns: Sequence[re.Pattern[str]],
    *,
    max_gap_chars: int = 200,
    min_ratio: float = 0.8,
) -> List[Tuple[int, int]]:
    """Find ordered, near-by subsequences meeting a minimum coverage ratio.

    - Builds a greedy chain across parts in order; parts may be skipped.
    - Accepts if matched_parts / total_parts >= min_ratio.
    - Returns at most one (start, end) range for simplicity.
    """
    if not patterns:
        return []
    parts_matches: List[List[Tuple[int, int]]] = []
    for rx in patterns:
        parts_matches.append([(m.start(), m.end()) for m in rx.finditer(text)])
    total_parts = len(parts_matches)

    # Find earliest starting match among all parts
    start_candidates: List[Tuple[int, int, int]] = []  # (part_index, s, e)
    for pi, lst in enumerate(parts_matches):
        if lst:
            s, e = lst[0]
            start_candidates.append((pi, s, e))
    if not start_candidates:
        return []
    # choose earliest by s
    start_candidates.sort(key=lambda t: t[1])
    start_part, s0, e0 = start_candidates[0]

    matched = 1
    first_s = s0
    prev_e = e0
    # chain subsequent parts after start_part
    for pi in range(start_part + 1, total_parts):
        # find earliest candidate satisfying order and gap
        cand = None
        for s, e in parts_matches[pi]:
            if s >= prev_e and (s - prev_e) <= max_gap_chars:
                cand = (s, e)
                break
        if cand is None:
            continue  # skip this part
        prev_e = cand[1]
        matched += 1

    ratio = matched / float(total_parts)
    if ratio >= min_ratio:
        return [(first_s, prev_e)]
    return []


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
    # Post-process to collapse hyphenation at line breaks
    norm_chars, bbox_map_opt = _collapse_hyphen_linebreak(norm_chars, bbox_map)
    if bbox_map_opt is not None:
        bbox_map = bbox_map_opt
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
    """Deprecated shim: route to process_recipe via a single-item recipe.

    Kept temporarily for compatibility if imported elsewhere.
    """
    item = {
        "text": report_context.get("query") if report_context and report_context.get("query") else rx.pattern,
        "regex": True,  # rx is already a compiled regex
        "ignore_case": bool(rx.flags & re.IGNORECASE),
        "literal_whitespace": False,
        "allow_multiple": bool(allow_multiple),
        "label": label,
        "color": color_rgb,
        "opacity": float(opacity),
    }
    return process_recipe(
        pdf_path,
        out_path,
        [item],
        default_allow_multiple=allow_multiple,
        dry_run=dry_run,
        default_label=label,
        default_color_rgb=color_rgb,
        default_opacity=opacity,
        report=report,
        report_context=report_context,
        compat_single_report=True,
    )


def _parse_color(value: str | Sequence[float]) -> Tuple[float, float, float]:
    """Parse color from name, #RRGGBB, or r,g,b floats (0..1)."""
    if isinstance(value, (list, tuple)) and len(value) == 3:
        r, g, b = value
        return (float(r), float(g), float(b))
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("#") and len(s) == 7:
            try:
                r = int(s[1:3], 16) / 255.0
                g = int(s[3:5], 16) / 255.0
                b = int(s[5:7], 16) / 255.0
                return (r, g, b)
            except Exception:
                pass
        if "," in s:
            parts = [p.strip() for p in s.split(",")]
            if len(parts) == 3:
                try:
                    return (float(parts[0]), float(parts[1]), float(parts[2]))
                except Exception:
                    pass
        return _color_to_rgb(s)
    return _color_to_rgb("yellow")


def _find_matches_by_page(doc, rx: re.Pattern[str]) -> Tuple[int, dict[int, List[Tuple[int, int]]]]:
    total = 0
    by_page: dict[int, List[Tuple[int, int]]] = {}
    for pi, page in enumerate(doc):
        norm_text, _ = _build_page_text_and_map(page)
        for m in rx.finditer(norm_text):
            total += 1
            by_page.setdefault(pi, []).append((m.start(), m.end()))
    return total, by_page


def _find_sequence_matches_by_page(
    doc,
    part_patterns: Sequence[re.Pattern[str]],
    *,
    max_gap_chars: int,
) -> Tuple[int, dict[int, List[Tuple[int, int]]]]:
    total = 0
    by_page: dict[int, List[Tuple[int, int]]] = {}
    for pi, page in enumerate(doc):
        norm_text, _ = _build_page_text_and_map(page)
        ranges = find_sequences_in_text(norm_text, part_patterns, max_gap_chars=max_gap_chars)
        if ranges:
            total += len(ranges)
            by_page[pi] = ranges
    return total, by_page


def _find_fuzzy_sequence_matches_by_page(
    doc,
    part_patterns: Sequence[re.Pattern[str]],
    *,
    max_gap_chars: int,
    min_ratio: float,
) -> Tuple[int, dict[int, List[Tuple[int, int]]]]:
    total = 0
    by_page: dict[int, List[Tuple[int, int]]] = {}
    for pi, page in enumerate(doc):
        norm_text, _ = _build_page_text_and_map(page)
        ranges = find_fuzzy_sequence_in_text(
            norm_text,
            part_patterns,
            max_gap_chars=max_gap_chars,
            min_ratio=min_ratio,
        )
        if ranges:
            total += len(ranges)
            by_page[pi] = ranges
    return total, by_page


def process_recipe(
    pdf_path: Path,
    out_path: Path | None,
    recipe_items: Sequence[dict[str, Any]],
    *,
    default_allow_multiple: bool,
    dry_run: bool,
    default_label: str | None,
    default_color_rgb: Tuple[float, float, float],
    default_opacity: float,
    report: bool,
    report_context: dict | None = None,
    compat_single_report: bool = False,
) -> int:
    """Apply multiple highlights described in a JSON recipe in one pass."""
    import fitz  # type: ignore

    try:
        doc = fitz.open(pdf_path.as_posix())
    except Exception as e:  # pragma: no cover - I/O
        print(f"[ERROR] failed to open PDF: {e}", file=sys.stderr)
        return EXIT_ERROR

    # Determine effective output path for reporting
    effective_out = (out_path or pdf_path.with_suffix(".highlighted.pdf")).as_posix()

    aggregate: dict[str, Any] = {
        "input": pdf_path.as_posix(),
        "output": effective_out,
        "items": [],
    }
    if report_context:
        aggregate["context"] = report_context

    overall_not_found = False
    overall_multiple_blocked = False

    for idx, item in enumerate(recipe_items):
        text = item.get("text") or item.get("pattern")
        seq_parts = item.get("sequence")
        if not text and not seq_parts:
            print(f"[INFO] recipe item {idx}: missing 'text'/'pattern' or 'sequence' field; skipping", file=sys.stderr)
            aggregate["items"].append({"index": idx, "matches": 0, "skipped": True})
            continue
        regex = bool(item.get("regex", False))
        ignore_case = bool(item.get("ignore_case", True))
        literal_ws = bool(item.get("literal_whitespace", False))
        allow_multiple = bool(item.get("allow_multiple", default_allow_multiple))
        label = item.get("label", default_label)
        color_val = item.get("color", None)
        color_rgb = _parse_color(color_val) if color_val is not None else default_color_rgb
        opacity = float(item.get("opacity", default_opacity))

        is_sequence = isinstance(seq_parts, list) and len(seq_parts) > 0
        if is_sequence:
            try:
                part_patterns = [
                    pattern_from_text(
                        str(p),
                        literal_whitespace=literal_ws,
                        regex=regex,
                        ignore_case=ignore_case,
                    )
                    for p in seq_parts
                ]
            except Exception as e:
                print(f"[ERROR] recipe item {idx}: invalid sequence parts: {e}", file=sys.stderr)
                aggregate["items"].append({"index": idx, "matches": 0, "error": True})
                continue
            max_gap_chars = int(item.get("max_gap_chars", 200))
            total, by_page = _find_sequence_matches_by_page(doc, part_patterns, max_gap_chars=max_gap_chars)
        else:
            rx = pattern_from_text(
                str(text),
                literal_whitespace=literal_ws,
                regex=regex,
                ignore_case=ignore_case,
            )
            total, by_page = _find_matches_by_page(doc, rx)
            # Fallback: if no direct match and not regex, try auto phrase-split fuzzy sequence
            auto_seq_used = False
            auto_seq_params: dict[str, Any] | None = None
            if total == 0 and not regex:
                phrase_len = int(item.get("sequence_phrase_len", 3))
                max_gap_chars = int(item.get("sequence_max_gap_chars", 300))
                min_ratio = float(item.get("sequence_min_ratio", 0.75))
                norm_q = "".join(normalize_char(c) for c in str(text))
                word_count = len([t for t in re.split(r"\s+", norm_q.strip()) if t])
                # Try multiple offsets for robustness
                def try_phrase_len(pl: int) -> Tuple[int, dict[int, List[Tuple[int,int]]]]:
                    for offset in range(max(1, pl)):
                        parts = split_text_into_phrases(norm_q, phrase_len=pl, start=offset)
                        part_patterns = [
                            pattern_from_text(
                                p,
                                literal_whitespace=literal_ws,
                                regex=False,
                                ignore_case=ignore_case,
                            )
                            for p in parts
                        ]
                        t, bp = _find_fuzzy_sequence_matches_by_page(
                            doc,
                            part_patterns,
                            max_gap_chars=max_gap_chars,
                            min_ratio=min_ratio,
                        )
                        if t > 0:
                            return t, bp
                    return 0, {}

                total, by_page = try_phrase_len(phrase_len)
                # Fallback to phrase_len=2 if still no match and there are at least two words
                if total == 0 and word_count >= 2:
                    total, by_page = try_phrase_len(2)
                auto_seq_used = total > 0
                if auto_seq_used:
                    auto_seq_params = {
                        "auto_sequence": True,
                        "sequence_phrase_len": phrase_len,
                        "sequence_min_ratio": min_ratio,
                        "sequence_max_gap_chars": max_gap_chars,
                    }

        report_hits: List[dict] = []
        if total > 0:
            for pi, ranges in by_page.items():
                page = doc[pi]
                _, bbox_map = _build_page_text_and_map(page)
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

        if total == 0:
            overall_not_found = True
            print(f"[INFO] recipe item {idx}: no matches found", file=sys.stderr)
        elif total > 1 and not allow_multiple:
            overall_multiple_blocked = True
            print(f"[INFO] recipe item {idx}: multiple matches found ({total}). Use allow_multiple to highlight anyway.", file=sys.stderr)
        else:
            # Apply highlights unless dry-run
            if not dry_run:
                for pi, ranges in by_page.items():
                    page = doc[pi]
                    _, bbox_map = _build_page_text_and_map(page)
                    for s, e in ranges:
                        _highlight_match(page, bbox_map, s, e, label=label, color_rgb=color_rgb, opacity=opacity)

        aggregate_item = (
            {
                "index": idx,
                **(
                    {
                        "query": str(text),
                        "pattern": (rx.pattern if (not is_sequence and 'rx' in locals()) else None),
                    }
                    if not is_sequence
                    else {
                        "sequence": [str(p) for p in seq_parts],
                        "max_gap_chars": int(item.get("max_gap_chars", 200)),
                    }
                ),
                "regex": regex,
                "ignore_case": ignore_case,
                "literal_whitespace": literal_ws,
                "matches": total,
                "allow_multiple": allow_multiple,
                "hits": report_hits,
            }
        )
        if not is_sequence and 'auto_seq_params' in locals() and auto_seq_params:
            aggregate_item.update(auto_seq_params)
        aggregate["items"].append(aggregate_item)

    # Emit report if requested
    if report:
        # If requested, emit a single-item compatible report format for CLI single mode
        if compat_single_report and len(aggregate["items"]) == 1:
            it = aggregate["items"][0]
            m = it.get("matches", 0)
            allow_multiple = bool(it.get("allow_multiple", default_allow_multiple))
            exit_code_preview = EXIT_NOT_FOUND if m == 0 else (EXIT_OK if m == 1 else EXIT_MULTIPLE)
            payload = {
                "input": aggregate["input"],
                "output": aggregate["output"],
                "matches": m,
                "exit_code": exit_code_preview,
                "allow_multiple": allow_multiple,
                "dry_run": bool(dry_run),
                "hits": it.get("hits", []),
            }
            if report_context:
                payload["context"] = report_context
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(json.dumps(aggregate, ensure_ascii=False))

    # Save if not dry_run
    try:
        if not dry_run:
            if out_path is None:
                out_path = pdf_path.with_suffix(".highlighted.pdf")
            try:
                same_target = out_path.resolve() == pdf_path.resolve()
            except Exception:
                same_target = out_path.as_posix() == pdf_path.as_posix()
            if same_target:
                print(
                    "[ERROR] refusing to overwrite input. Always write to a new file. Specify a different -o/--output.",
                    file=sys.stderr,
                )
                return EXIT_ERROR
            doc.save(out_path.as_posix(), garbage=4, deflate=True)
            print(f"[OK] saved: {out_path}", file=sys.stderr)
    except Exception as e:  # pragma: no cover - I/O
        print(f"[ERROR] failed to save PDF: {e}", file=sys.stderr)
        return EXIT_ERROR
    finally:
        doc.close()

    if overall_not_found:
        return EXIT_NOT_FOUND
    if overall_multiple_blocked:
        return EXIT_MULTIPLE
    return EXIT_OK


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="pdfhl",
        description=(
            "Highlight a phrase in a PDF with tolerant matching (line breaks/ligatures). "
            "Always writes a new PDF; never modifies the input. Use -o/--output to choose the output path."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "JSON Recipe Format (for --recipe)\n"
            "\n"
            "- Accepts either a top-level array or an object with an 'items' array.\n"
            "\n"
            "Example (array):\n"
            "  [\\n"
            "    {\"text\": \"Introduction\", \"color\": \"mint\"},\\n"
            "    {\"text\": \"Threats\", \"color\": \"red\", \"allow_multiple\": true}\\n"
            "  ]\n"
            "\n"
            "Example (object):\n"
            "  {\\n"
            "    \"items\": [\\n"
            "      { \"text\": \"Experiment\", \"color\": \"green\", \"label\": \"Experiment\" },\\n"
            "      { \"text\": \"Conclusion\", \"color\": \"violet\", \"opacity\": 0.25 }\\n"
            "    ]\\n"
            "  }\n"
            "\n"
            "Per-item fields:\n"
            "- text or pattern (string) OR sequence (list of strings)\n"
            "- regex (bool, default false)\n"
            "- ignore_case (bool, default true)\n"
            "- literal_whitespace (bool, default false)\n"
            "- allow_multiple (bool, default falls back to CLI)\n"
            "- label (string | null)\n"
            "- color (name|#RRGGBB|r,g,b 0..1)\n"
            "- opacity (float 0..1, default falls back to CLI)\n"
            "- For sequence: max_gap_chars (int, default 200)\n"
            "\n"
            "Optional fields for auto-splitting long 'text' when direct match fails:\n"
            "- sequence_phrase_len (int, default 3)\n"
            "- sequence_min_ratio (float, default 0.8)\n"
            "- sequence_max_gap_chars (int, default 200)\n"
            "\n"
            "Exit Codes\n"
            "- 0: OK\n"
            "- 1: Not found (any item had zero matches)\n"
            "- 2: Multiple matches (blocked; use --allow-multiple to permit highlighting)\n"
            "- 3: Error (I/O failures, invalid paths, overwrite refusal, etc.)\n"
        ),
    )
    p.add_argument("pdf", type=Path, help="Input PDF file path")
    mode = p.add_mutually_exclusive_group(required=False)
    mode.add_argument("--text", dest="text", type=str, default=None, help="Search text (literal). Use --regex for regex mode.")
    mode.add_argument("--pattern", dest="pattern", type=str, default=None, help="Alias of --text")
    mode.add_argument(
        "--recipe",
        type=Path,
        help=(
            "JSON recipe path for multiple highlights (list of items).\n"
            "See 'JSON Recipe Format' in --help below."
        ),
    )
    p.add_argument("--regex", action="store_true", help="Treat the text as a regular expression (single-item mode)")

    case = p.add_mutually_exclusive_group()
    case.add_argument("--ignore-case", dest="ignore_case", action="store_true", default=True, help="Case-insensitive search (default)")
    case.add_argument("--case-sensitive", dest="case_sensitive", action="store_true", help="Case-sensitive search")

    p.add_argument("--literal-whitespace", action="store_true", help="Do not convert spaces to \\s+ (default converts for robust matching)")
    p.add_argument("--allow-multiple", action="store_true", help="If multiple matches, still highlight and write output (exit 2)")
    p.add_argument("--dry-run", action="store_true", help="Search only; do not write output")

    # Output policy: always write to a new file
    p.add_argument("--output", "-o", type=Path, help="Output PDF path (default: <input>.highlighted.pdf)")

    # Minimal color/label controls (RGB 0..1)
    p.add_argument("--label", type=str, default=None, help="Annotation title/content label")
    p.add_argument("--color", type=str, default="yellow", help="Highlight color: name|#RRGGBB|r,g,b (0..1)")
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
    # Recipe mode
    if getattr(ns, "recipe", None):
        try:
            data = json.loads(Path(ns.recipe).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[ERROR] failed to read recipe: {e}", file=sys.stderr)
            return EXIT_ERROR
        if isinstance(data, dict) and "items" in data:
            items = data.get("items")
        else:
            items = data
        if not isinstance(items, list):
            print("[ERROR] recipe must be a list of items or an object with 'items' array", file=sys.stderr)
            return EXIT_ERROR
        return process_recipe(
            ns.pdf,
            ns.output,
            items,  # type: ignore[arg-type]
            default_allow_multiple=ns.allow_multiple,
            dry_run=ns.dry_run,
            default_label=ns.label,
            default_color_rgb=_parse_color(ns.color),
            default_opacity=float(ns.opacity),
            report=(ns.report == "json"),
            report_context=None,
            compat_single_report=False,
        )

    # Single-item mode
    query = ns.text or ns.pattern
    if not query:
        print("[ERROR] --text/--pattern or --recipe is required.", file=sys.stderr)
        return EXIT_ERROR

    # Build a single-item recipe from CLI args and run through the common path
    items = [
        {
            "text": query,
            "regex": bool(ns.regex),
            "ignore_case": not getattr(ns, "case_sensitive", False),
            "literal_whitespace": bool(ns.literal_whitespace),
            "allow_multiple": bool(ns.allow_multiple),
            "label": ns.label,
            "color": ns.color,
            "opacity": float(ns.opacity),
        }
    ]

    # Also prepare context info similar to previous single-mode report
    ignore_case = not getattr(ns, "case_sensitive", False)
    rx = pattern_from_text(query, literal_whitespace=ns.literal_whitespace, regex=ns.regex, ignore_case=ignore_case)
    context = {
        "query": query,
        "pattern": rx.pattern,
        "regex": bool(ns.regex),
        "ignore_case": ignore_case,
        "literal_whitespace": bool(ns.literal_whitespace),
    }

    return process_recipe(
        ns.pdf,
        ns.output,
        items,
        default_allow_multiple=ns.allow_multiple,
        dry_run=ns.dry_run,
        default_label=ns.label,
        default_color_rgb=_parse_color(ns.color),
        default_opacity=float(ns.opacity),
        report=(ns.report == "json"),
        report_context=context,
        compat_single_report=True,
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
