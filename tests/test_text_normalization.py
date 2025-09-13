from pdfhl.pdfhl import normalize_char, pattern_from_text


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
    # literal whitespace: normalized newlines become spaces; pattern is literal text
    assert rx.pattern == "Hello  world again"


def test_pattern_from_text_whitespace_to_s():
    rx = pattern_from_text("Hello  world\nagain", literal_whitespace=False, regex=False, ignore_case=True)
    # whitespace collapsed to \s+
    assert "\\s+world\\s+again" in rx.pattern
    assert rx.search("Hello world again")
    assert rx.search("Hello    world\nagain")
