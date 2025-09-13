from pdfhl.pdfhl import pattern_from_text, find_sequences_in_text, find_fuzzy_sequence_in_text


def test_find_sequences_basic_order_and_gap():
    text = "We propose MSCCD and converted into token bags then detects similar subsequences"
    p1 = pattern_from_text("propose MSCCD", regex=False, literal_whitespace=False, ignore_case=True)
    p2 = pattern_from_text("converted into token bags", regex=False, literal_whitespace=False, ignore_case=True)
    parts = [p1, p2]
    seqs = find_sequences_in_text(text, parts, max_gap_chars=50)
    assert len(seqs) >= 1
    s, e = seqs[0]
    assert text[s:e].startswith("propose") and text[s:e].endswith("bags")


def test_find_sequences_respects_order():
    text = "baz ... foo ..."
    p1 = pattern_from_text("foo", regex=False, literal_whitespace=False, ignore_case=True)
    p2 = pattern_from_text("baz", regex=False, literal_whitespace=False, ignore_case=True)
    parts = [p1, p2]
    # order foo->baz should not match since baz comes first
    seqs = find_sequences_in_text(text, parts, max_gap_chars=100)
    assert seqs == []


def test_find_sequences_gap_limit():
    text = "foo " + ("x" * 300) + " bar"
    p1 = pattern_from_text("foo", regex=False, literal_whitespace=False, ignore_case=True)
    p2 = pattern_from_text("bar", regex=False, literal_whitespace=False, ignore_case=True)
    parts = [p1, p2]
    # large gap prevents matching
    assert find_sequences_in_text(text, parts, max_gap_chars=100) == []
    # relaxed gap allows matching
    assert find_sequences_in_text(text, parts, max_gap_chars=400)


def test_find_fuzzy_sequence_with_missing_part_ratio():
    # three parts, middle one will be missing but ratio 2/3 >= 0.66 < 0.8 so not accepted
    text = "foo ... " + ("x" * 50) + " ... baz"
    p1 = pattern_from_text("foo", regex=False, literal_whitespace=False, ignore_case=True)
    p2 = pattern_from_text("bar", regex=False, literal_whitespace=False, ignore_case=True)
    p3 = pattern_from_text("baz", regex=False, literal_whitespace=False, ignore_case=True)
    parts = [p1, p2, p3]
    assert find_fuzzy_sequence_in_text(text, parts, max_gap_chars=200, min_ratio=0.8) == []
    # With lower ratio threshold it should be accepted
    assert find_fuzzy_sequence_in_text(text, parts, max_gap_chars=200, min_ratio=0.66)
