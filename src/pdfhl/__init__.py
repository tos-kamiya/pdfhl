"""Public API surface for pdfhl."""

# SPDX-FileCopyrightText: 2025-present Toshihiro Kamiya <kamiya@mbj.nifty.com>
#
# SPDX-License-Identifier: MIT

from .__about__ import __version__
from .pdfhl import (
    HighlightHit,
    HighlightOutcome,
    MultipleMatchesError,
    PdfHighlighter,
    SelectionMode,
    highlight_text,
)

# Backwards-friendly alias so callers can import either name.
version = __version__

__all__ = [
    "HighlightHit",
    "HighlightOutcome",
    "PdfHighlighter",
    "highlight_text",
    "__version__",
    "version",
    "SelectionMode",
    "MultipleMatchesError",
]
