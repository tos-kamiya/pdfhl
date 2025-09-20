"""Public API surface for pdfhl."""

# SPDX-FileCopyrightText: 2025-present Toshihiro Kamiya <kamiya@mbj.nifty.com>
#
# SPDX-License-Identifier: MIT

from .pdfhl import HighlightHit, HighlightOutcome, PdfHighlighter, highlight_text

__all__ = [
    "HighlightHit",
    "HighlightOutcome",
    "PdfHighlighter",
    "highlight_text",
]
