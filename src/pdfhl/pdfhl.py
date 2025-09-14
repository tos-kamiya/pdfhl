from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import List, Sequence, Tuple, Any

try:
    from .__about__ import __version__
except:
    __version_ = "(unknown)"

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


from .segmentation import split_query_to_tokens


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
        if ch == "-" and (i + 1) < n:
            # Decide whether this is a line-break hyphenation to be collapsed
            # Gather context: prev non-space, next non-space index, and whether next is on a new line
            j = len(out_chars) - 1
            while j >= 0 and out_chars[j] == " ":
                j -= 1
            prev_alpha = j >= 0 and out_chars[j].isalpha()

            # Determine next non-space index in input
            k = i + 1
            while k < n and norm_chars[k] == " ":
                k += 1
            next_alpha = k < n and norm_chars[k].isalpha()

            # Heuristic: check if current token already contains a hyphen -> likely a compound, keep hyphen
            token_has_hyphen = False
            if j >= 0:
                t = j
                while t >= 0 and out_chars[t] != " ":
                    if out_chars[t] == "-":
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
                if (i + 1) < n and norm_chars[i + 1] == " ":
                    should_collapse = True
                # Case B: immediate next letter but on a new line per bbox
                elif y_jump_linebreak:
                    should_collapse = True

            if should_collapse:
                # If spaces follow, skip them; otherwise just skip hyphen
                skip_to = i + 1
                while skip_to < n and norm_chars[skip_to] == " ":
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


def find_progressive_phrase_segments(
    text: str,
    query: str,
    *,
    kmax: int = 3,
    ignore_case: bool = True,
    max_segment_gap_chars: int = 200,
    min_total_words: int = 3,
) -> List[Tuple[int, int]]:
    r"""Progressively find segments from a query with 3→2→1-word backoff.

    - Normalizes the query like the page text (callers should normalize text).
    - Between words in a chunk, allow "\s*" to match across newlines/missing spaces.
    - Chains matches left-to-right; each next search starts from the previous end.
    - After building segments, enforce proximity: each gap <= max_segment_gap_chars.
    - Returns list of (start,end) for the accepted segments; empty if none or gaps too large.
    - Implementation detail: contiguous segments (end == next start) are merged to
      produce intuitively larger spans across missing spaces or subword splits.
    """
    # Tokenize the query into mt5-base subwords (order preserved)
    tokens = [normalize_char(t) for t in split_query_to_tokens(query)]
    if not tokens:
        return []
    if kmax < 1:
        kmax = 1
    n = len(tokens)
    flags = re.IGNORECASE if ignore_case else 0

    def compile_chunk(i0: int, k: int) -> re.Pattern[str]:
        chunk = tokens[i0 : i0 + k]
        patt = r"\s*".join(re.escape(tok) for tok in chunk)
        return re.compile(patt, flags)

    def build_chain(start_i: int, start_pos: int) -> List[Tuple[int, int, int]]:
        segs: List[Tuple[int, int, int]] = []  # (s,e,k_used)
        i = start_i
        prev_end = start_pos
        while i < n:
            k = min(kmax, n - i)
            matched_here = False
            while k > 0:
                rx = compile_chunk(i, k)
                m = rx.search(text, pos=prev_end)
                if m:
                    segs.append((m.start(), m.end(), k))
                    prev_end = m.end()
                    i += k
                    matched_here = True
                    break
                k -= 1
            if not matched_here:
                i += 1
        return segs

    def passes_chain(segs: List[Tuple[int, int, int]]) -> bool:
        if not segs:
            return False
        # Proximity
        for j in range(1, len(segs)):
            if (segs[j][0] - segs[j - 1][1]) > max_segment_gap_chars:
                return False
        # Coverage: ensure enough words matched overall
        total_words = sum(k for (_, _, k) in segs)
        return total_words >= max(1, min_total_words)

    # Try all candidates for the first chunk (k from kmax down to 1) and their occurrences
    for k0 in range(min(kmax, n), 0, -1):
        rx0 = compile_chunk(0, k0)
        for m0 in rx0.finditer(text):
            starter = (m0.start(), m0.end(), k0)
            chain = build_chain(k0, m0.end())
            segs = [starter] + chain
            if passes_chain(segs):
                # Drop k info when returning, then merge contiguous segments to be robust
                # against subword tokenization differences (e.g., MSCCD -> ["ms", "cc", "d"]).
                raw = [(s, e) for (s, e, _) in segs]
                if not raw:
                    return []
                merged: List[Tuple[int, int]] = [raw[0]]
                for (s, e) in raw[1:]:
                    ps, pe = merged[-1]
                    if s == pe:  # contiguous; coalesce
                        merged[-1] = (ps, e)
                    else:
                        merged.append((s, e))
                return merged
    return []


def find_progressive_candidates(
    text: str,
    query: str,
    *,
    kmax: int = 3,
    ignore_case: bool = True,
    max_segment_gap_chars: int = 200,
    min_total_words: int = 3,
) -> List[List[Tuple[int, int, int]]]:
    """Return all passing progressive candidates as lists of segments (s,e,k).

    Each candidate is a list of segments where each segment is (start, end, k_used).
    A candidate passes if its segments obey the gap constraint and total matched
    words >= min_total_words.
    """
    # Tokenize the query into mt5-base subwords (order preserved)
    tokens = [normalize_char(t) for t in split_query_to_tokens(query)]
    if not tokens:
        return []
    if kmax < 1:
        kmax = 1
    n = len(tokens)
    flags = re.IGNORECASE if ignore_case else 0

    def compile_chunk(i0: int, k: int) -> re.Pattern[str]:
        chunk = tokens[i0 : i0 + k]
        patt = r"\s*".join(re.escape(tok) for tok in chunk)
        return re.compile(patt, flags)

    def build_chain(start_i: int, start_pos: int) -> List[Tuple[int, int, int]]:
        segs: List[Tuple[int, int, int]] = []  # (s,e,k)
        i = start_i
        prev_end = start_pos
        while i < n:
            k = min(kmax, n - i)
            matched_here = False
            while k > 0:
                rx = compile_chunk(i, k)
                m = rx.search(text, pos=prev_end)
                if m:
                    segs.append((m.start(), m.end(), k))
                    prev_end = m.end()
                    i += k
                    matched_here = True
                    break
                k -= 1
            if not matched_here:
                i += 1
        return segs

    def passes_chain(segs: List[Tuple[int, int, int]]) -> bool:
        if not segs:
            return False
        # Proximity
        for j in range(1, len(segs)):
            if (segs[j][0] - segs[j - 1][1]) > max_segment_gap_chars:
                return False
        # Coverage: ensure enough words matched overall
        total_words = sum(k for (_, _, k) in segs)
        return total_words >= max(1, min_total_words)

    cands: List[List[Tuple[int, int, int]]] = []
    for k0 in range(min(kmax, n), 0, -1):
        rx0 = compile_chunk(0, k0)
        for m0 in rx0.finditer(text):
            starter = (m0.start(), m0.end(), k0)
            chain = build_chain(k0, m0.end())
            segs = [starter] + chain
            if passes_chain(segs):
                cands.append(segs)
    return cands


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


def _add_highlight_for_range(
    page, rects: Sequence[Rect], label: str | None = None, color_rgb: Tuple[float, float, float] | None = None, opacity: float | None = None
) -> bool:
    """Add a highlight annotation for the provided line rectangles.

    Converts rects into quads and adds a highlight.
    """
    import fitz  # type: ignore

    if not rects:
        return False
    # Convert each rect to a sanitized 8-tuple quad
    quads = []
    for x0, y0, x1, y1 in rects:
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
        for x0, y0, x1, y1 in rects:
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


def _highlight_match(page, bbox_map: Sequence[Rect], start: int, end: int, *, label: str | None, color_rgb: Tuple[float, float, float], opacity: float) -> bool:
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


 


def _find_progressive_matches_by_page(
    doc,
    query: str,
    *,
    kmax: int,
    ignore_case: bool,
    max_segment_gap_chars: int,
    select_shortest: bool,
) -> Tuple[int, dict[int, List[Tuple[int, int]]]]:
    """Run progressive phrase search per page and select ranges.

    If select_shortest is True, choose the best-scoring single candidate per page.
    Otherwise, return all candidate ranges per page.
    """
    total = 0
    by_page: dict[int, List[Tuple[int, int]]] = {}
    # For global-best selection, track the overall best across pages
    best_global: Tuple[float, int, int, int] | None = None  # (score, pi, s0, eN)
    for pi, page in enumerate(doc):
        norm_text, _ = _build_page_text_and_map(page)
        cands = find_progressive_candidates(
            norm_text,
            query,
            kmax=kmax,
            ignore_case=ignore_case,
            max_segment_gap_chars=max_segment_gap_chars,
        )
        if not cands:
            continue

        def score(segs: List[Tuple[int, int, int]]) -> float:
            # Compute coverage and penalties
            if not segs:
                return -1e9
            s0, eN = segs[0][0], segs[-1][1]
            length = max(1, eN - s0)
            matched_chars = sum(e - s for (s, e, _) in segs)
            gaps = 0
            for j in range(1, len(segs)):
                d = segs[j][0] - segs[j - 1][1]
                if d > 0:
                    gaps += d
            # Total tokens refers to mt5-based subwords
            total_tokens = len(split_query_to_tokens(query))
            matched_words = sum(k for (_, _, k) in segs)
            word_cov = matched_words / max(1, total_tokens)
            char_cov = matched_chars / float(length)
            gap_pen = gaps / float(length)
            length_pen = min(1.0, length / 800.0)  # gentle penalty up to ~800 chars
            return (2.0 * word_cov) + (1.0 * char_cov) - (0.5 * gap_pen) - (0.25 * length_pen)

        if select_shortest:
            # Choose best by score across ALL pages; tie-break by shorter length, then earlier
            for segs in cands:
                sc = score(segs)
                s0, eN = segs[0][0], segs[-1][1]
                length = eN - s0
                key = (sc, -length, -s0)
                if best_global is None or key > (best_global[0], -(best_global[3] - best_global[2]), -best_global[2]):
                    best_global = (sc, pi, s0, eN)
        else:
            # Return all ranges
            ranges = []
            for segs in cands:
                s0, eN = segs[0][0], segs[-1][1]
                ranges.append((s0, eN))
            if ranges:
                total += len(ranges)
                by_page[pi] = ranges
    if select_shortest:
        if best_global is None:
            return 0, {}
        _, pi, s0, eN = best_global
        return 1, {pi: [(s0, eN)]}
    return total, by_page


def _collapse_to_shortest(by_page: dict[int, List[Tuple[int, int]]]) -> Tuple[int, dict[int, List[Tuple[int, int]]]]:
    """Select the shortest (end-start) range across all pages and ranges.

    Tie-breakers: lowest page index, then lowest start.
    Returns (1, {best_page: [(s,e)]}) if any, otherwise (0, {}).
    """
    best: Tuple[int, int, int] | None = None  # (pi, s, e)
    for pi, ranges in by_page.items():
        for s, e in ranges:
            if best is None:
                best = (pi, s, e)
                continue
            bs, be = best[1], best[2]
            cur_len = e - s
            best_len = be - bs
            if cur_len < best_len or (cur_len == best_len and (pi < best[0] or (pi == best[0] and s < bs))):
                best = (pi, s, e)
    if best is None:
        return 0, {}
    pi, s, e = best
    return 1, {pi: [(s, e)]}


def process_recipe(
    pdf_path: Path,
    out_path: Path | None,
    recipe_items: Sequence[dict[str, Any]],
    *,
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
        if not text:
            print(f"[INFO] recipe item {idx}: missing 'text'/'pattern' field; skipping", file=sys.stderr)
            aggregate["items"].append({"index": idx, "matches": 0, "skipped": True})
            continue
        # Progressive-only search: ignore regex/literal whitespace; do not block on multiples
        regex = False
        ignore_case = bool(item.get("ignore_case", True))
        literal_ws = False
        allow_multiple = True
        label = item.get("label", default_label)
        color_val = item.get("color", None)
        color_rgb = _parse_color(color_val) if color_val is not None else default_color_rgb
        opacity = float(item.get("opacity", default_opacity))
        # Progressive search options (always used)
        progressive_search = True
        progressive_kmax = int(item.get("progressive_kmax", 3))
        progressive_gap = int(item.get("progressive_max_gap_chars", 200))
        select_shortest = bool(item.get("select_shortest", True))

        # Progressive search only
        rx = None
        total = 0
        by_page: dict[int, List[Tuple[int, int]]] = {}
        prog_used = True
        t2, bp2 = _find_progressive_matches_by_page(
            doc,
            str(text),
            kmax=progressive_kmax,
            ignore_case=ignore_case,
            max_segment_gap_chars=progressive_gap,
            select_shortest=select_shortest,
        )
        if t2 > 0:
            total, by_page = t2, bp2

        # Selection to single best is handled inside _find_progressive_matches_by_page

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
        else:
            # Apply highlights unless dry-run
            if not dry_run:
                for pi, ranges in by_page.items():
                    page = doc[pi]
                    _, bbox_map = _build_page_text_and_map(page)
                    for s, e in ranges:
                        _highlight_match(page, bbox_map, s, e, label=label, color_rgb=color_rgb, opacity=opacity)

        aggregate_item = {
            "index": idx,
            "query": str(text),
            "pattern": (rx.pattern if rx is not None else None),
            "regex": regex,
            "ignore_case": ignore_case,
            "literal_whitespace": literal_ws,
            "matches": total,
            "allow_multiple": True,
            "hits": report_hits,
        }
        if prog_used:
            aggregate_item.update(
                {
                    "progressive_search": True,
                    "progressive_kmax": progressive_kmax,
                    "progressive_max_gap_chars": progressive_gap,
                }
            )
        if select_shortest:
            aggregate_item["select_shortest"] = True
        aggregate["items"].append(aggregate_item)

    # Emit report if requested
    if report:
        # If requested, emit a single-item compatible report format for CLI single mode
        if compat_single_report and len(aggregate["items"]) == 1:
            it = aggregate["items"][0]
            m = it.get("matches", 0)
            allow_multiple = True
            exit_code_preview = EXIT_NOT_FOUND if m == 0 else EXIT_OK
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
            '    {"text": "Introduction", "color": "mint"},\\n'
            '    {"text": "Threats", "color": "red"}\\n'
            "  ]\n"
            "\n"
            "Example (object):\n"
            "  {\\n"
            '    "items": [\\n'
            '      { "text": "Experiment", "color": "green", "label": "Experiment" },\\n'
            '      { "text": "Conclusion", "color": "violet", "opacity": 0.25 }\\n'
            "    ]\\n"
            "  }\n"
            "\n"
            "Per-item fields:\n"
            "- text or pattern (string)\n"
            "- ignore_case (bool, default true)\n"
            "- select_shortest (bool, default true; false = highlight all matches)\n"
            "- label (string | null)\n"
            "- color (name|#RRGGBB|r,g,b 0..1)\n"
            "- opacity (float 0..1, default falls back to CLI)\n"
            "\n"
            "Progressive search is always used (3→2→1-word backoff, allowing missing spaces with \\s*).\n"
            "Advanced tuning: progressive_kmax (int, default 3), progressive_max_gap_chars (int, default 200)\n"
            "\n"
            "Exit Codes\n"
            "- 0: OK\n"
            "- 1: Not found (any item had zero matches)\n"
            "- 2: (unused)\n"
            "- 3: Error (I/O failures, invalid paths, overwrite refusal, etc.)\n"
        ),
    )
    p.add_argument("pdf", type=Path, help="Input PDF file path")
    mode = p.add_mutually_exclusive_group(required=False)
    mode.add_argument("--text", dest="text", type=str, default=None, help="Search text (progressive search)")
    mode.add_argument("--pattern", dest="pattern", type=str, default=None, help="Alias of --text")
    mode.add_argument(
        "--recipe",
        type=Path,
        help=("JSON recipe path for multiple highlights (list of items).\n" "See 'JSON Recipe Format' in --help below."),
    )
    # Progressive-only: no regex mode

    case = p.add_mutually_exclusive_group()
    case.add_argument("--ignore-case", dest="ignore_case", action="store_true", default=True, help="Case-insensitive search (default)")
    case.add_argument("--case-sensitive", dest="case_sensitive", action="store_true", help="Case-sensitive search")

    # Selection mode: shortest vs all (mutually exclusive; default shortest)
    sel = p.add_mutually_exclusive_group()
    sel.add_argument("--shortest", dest="shortest", action="store_true", help="Select the shortest matching range (default)")
    sel.add_argument("--all-matches", dest="all_matches", action="store_true", help="Highlight all matching ranges")
    p.add_argument("--dry-run", action="store_true", help="Search only; do not write output")

    # Output policy: always write to a new file
    p.add_argument("--output", "-o", type=Path, help="Output PDF path (default: <input>.highlighted.pdf)")

    # Minimal color/label controls (RGB 0..1)
    p.add_argument("--label", type=str, default=None, help="Annotation title/content label")
    p.add_argument("--color", type=str, default="yellow", help="Highlight color: name|#RRGGBB|r,g,b (0..1)")
    p.add_argument("--opacity", type=float, default=0.3, help="Highlight opacity (0..1)")
    p.add_argument("--report", choices=["json"], help="Emit report to stdout (json)")

    # mt5 segmentation controls
    p.add_argument("--mt5-model", type=str, default=None, help="mt5 tokenizer model id or local path (default: google/mt5-base)")
    p.add_argument("--no-mt5", action="store_true", help="Disable mt5-based segmentation (fallback to single-token)")

    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

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
    # Configure segmenter based on CLI
    try:
        from .segmentation import configure_segmenter

        configure_segmenter(use_mt5=(not getattr(ns, "no_mt5", False)), model_id=getattr(ns, "mt5_model", None))
    except Exception:
        # If segmentation module cannot be configured, proceed; runtime will warn/fallback as needed
        pass
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
            "ignore_case": not getattr(ns, "case_sensitive", False),
            "label": ns.label,
            "color": ns.color,
            "opacity": float(ns.opacity),
            "select_shortest": (False if getattr(ns, "all_matches", False) else True),
        }
    ]

    # Also prepare context info similar to previous single-mode report
    ignore_case = not getattr(ns, "case_sensitive", False)
    context = {
        "query": query,
        "ignore_case": ignore_case,
        "selection": ("all" if getattr(ns, "all_matches", False) else "shortest"),
    }

    return process_recipe(
        ns.pdf,
        ns.output,
        items,
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
