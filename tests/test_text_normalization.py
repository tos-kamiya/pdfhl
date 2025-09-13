from pdfhl.pdfhl import normalize_char, pattern_from_text, _collapse_hyphen_linebreak


def test_normalize_char_basic():
    # soft hyphen removed
    assert normalize_char("\u00AD") == ""
    # whitespace to single space
    assert normalize_char("\n") == " "
    assert normalize_char("\t") == " "
    # ligature expands via NFKC
    assert normalize_char("ﬁ") == "fi"


def test_pattern_from_text_literal_ws():
    rx = pattern_from_text("Hello  world\nagain", literal_whitespace=True, regex=False, ignore_case=True)
    # literal whitespace: normalized newlines become spaces; pattern matches literal spaces
    assert rx.search("Hello  world again")


def test_pattern_from_text_whitespace_to_s():
    rx = pattern_from_text("Hello  world\nagain", literal_whitespace=False, regex=False, ignore_case=True)
    # whitespace collapsed to \s+
    assert "\\s+world\\s+again" in rx.pattern
    assert rx.search("Hello world again")
    assert rx.search("Hello    world\nagain")


def test_normalize_char_unify_dashes_and_quotes():
    # various dashes -> '-'
    for ch in ["-", "\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212", "\uFE63", "\uFF0D"]:
        assert normalize_char(ch) == "-"
    # curly quotes -> straight
    assert normalize_char("\u2019") == "'"
    assert normalize_char("\u2018") == "'"
    assert normalize_char("\u201C") == '"'
    assert normalize_char("\u201D") == '"'


def test_collapse_hyphenation_linebreak_join():
    # "differ- ent" -> "different"
    chars = list("differ- ent")
    out, _ = _collapse_hyphen_linebreak(chars, None)
    assert "".join(out) == "different"

    # In-word hyphen (no space after) should remain
    chars2 = list("state-of-the-art")
    out2, _ = _collapse_hyphen_linebreak(chars2, None)
    assert "".join(out2) == "state-of-the-art"

    # Line-end compound hyphen should be preserved (token already has hyphen)
    # Simulate: "state-of-" at end of line then "the-art" on next line via bbox y jump
    chars3 = list("state-of-the-art")
    # place hyphen at index of the second '-' (between 'of' and 'the') and simulate a line break there
    # Build bbox: same y for all, except char after that hyphen has larger y
    bboxes = []
    hyphen_pos = chars3.index('-', chars3.index('-') + 1)
    for idx, _c in enumerate(chars3):
        y = 100.0
        if idx == hyphen_pos + 1:
            y = 110.5  # new line
        bboxes.append((0.0, y, 1.0, y + 1.0))
    out3, _ = _collapse_hyphen_linebreak(chars3, bboxes)
    assert "".join(out3) == "state-of-the-art"
