from __future__ import annotations

import os
import sys
from typing import List, Optional
import re


_SEGMENTER_USE_MT5: bool = True
_SEGMENTER_MODEL_ID: Optional[str] = None  # default resolved lazily
_MT5_TOKENIZER = None  # cached tokenizer instance


def configure_segmenter(*, use_mt5: Optional[bool] = None, model_id: Optional[str] = None) -> None:
    """Configure global segmentation behavior.

    - use_mt5: when True (default), attempt to use mt5-base tokenizer.
    - model_id: optional model path or ID; defaults to env PDFHL_MT5_MODEL or
      'google/mt5-base'.
    """
    global _SEGMENTER_USE_MT5, _SEGMENTER_MODEL_ID
    if use_mt5 is not None:
        _SEGMENTER_USE_MT5 = bool(use_mt5)
    if model_id is not None:
        _SEGMENTER_MODEL_ID = model_id


def _resolve_model_id() -> str:
    mid = _SEGMENTER_MODEL_ID or os.environ.get("PDFHL_MT5_MODEL")
    return mid or "google/mt5-base"


def get_mt5_tokenizer():  # -> PreTrainedTokenizerBase (typed lazily to avoid hard dep)
    """Load and cache the mt5 tokenizer lazily.

    Falls back by raising a RuntimeError when transformers/sentencepiece are missing
    or the model cannot be loaded.
    """
    global _MT5_TOKENIZER
    if _MT5_TOKENIZER is not None:
        return _MT5_TOKENIZER
    try:
        from transformers import AutoTokenizer  # type: ignore
    except Exception as e:  # pragma: no cover - depends on external install
        raise RuntimeError("transformers is required for mt5 tokenization") from e
    model_id = _resolve_model_id()
    try:
        tok = AutoTokenizer.from_pretrained(model_id, legacy=True, use_fast=False)
    except Exception as e:  # pragma: no cover - depends on model availability
        raise RuntimeError(f"failed to load mt5 tokenizer: {model_id}") from e
    _MT5_TOKENIZER = tok
    return tok


def split_to_subwords(text: str) -> List[str]:
    """Return SentencePiece subwords for text using mt5-base, preserving order.

    - Strips the U+2581 (\u2581) leading marker from each piece.
    - Drops empty strings after stripping.
    - Does not deduplicate; preserves token order.
    """
    tok = get_mt5_tokenizer()
    pieces = tok.tokenize(text)
    out: List[str] = []
    for p in pieces:
        core = p.lstrip("\u2581")
        if core:
            out.append(core)
    return out


def split_query_to_tokens(query: str) -> List[str]:
    """Split the query into tokens for progressive search.

    Default is mt5 subwords. If mt5 is disabled or unavailable, fall back to a single
    normalized token (entire query as one token) to preserve functionality.
    """
    use_mt5 = _SEGMENTER_USE_MT5
    # Allow env override: PDFHL_USE_MT5=0/1
    env_use = os.environ.get("PDFHL_USE_MT5")
    if env_use is not None:
        use_mt5 = env_use not in ("0", "false", "False", "no")

    if use_mt5:
        try:
            subs = split_to_subwords(query)
            return [s for s in subs if s]
        except Exception as e:
            print(
                f"[WARN] mt5 tokenizer unavailable ({e}); falling back to single-token segmentation",
                file=sys.stderr,
            )
            # fall through to single-token behavior below

    # Fallback: simple whitespace-based tokenization to preserve behavior when mt5 is unavailable
    s = (query or "").strip()
    if not s:
        return []
    return [t for t in re.split(r"\s+", s) if t]
