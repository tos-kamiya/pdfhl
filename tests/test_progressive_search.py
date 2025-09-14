from pdfhl.pdfhl import find_progressive_phrase_segments


def test_progressive_matches_across_missing_spaces():
    # Simulate missing whitespace due to line breaks in PDF extraction
    text = "we configuredMSCCD then something similaritythreshold of 70%"
    query = "we configured MSCCD similarity threshold of 70%"

    segs = find_progressive_phrase_segments(text, query, kmax=3, ignore_case=True, max_segment_gap_chars=200)
    # Should at least find two segments, typically three: [we configuredMSCCD], [similaritythreshold of], [70%]
    assert len(segs) >= 2
    # Verify that the substrings align with intent (allowing missing spaces)
    s0, e0 = segs[0]
    s1, e1 = segs[1]
    assert text[s0:e0].lower().startswith("we configured") and "msccd" in text[s0:e0].lower()
    assert "similarity" in text[s1:e1].lower()
    # If a third segment exists, it should include '%'
    if len(segs) >= 3:
        s2, e2 = segs[2]
        assert "%" in text[s2:e2]


def test_progressive_backoff_to_two_and_one_word():
    text = "alpha betaX gamma deltaX epsilon"
    query = "alpha beta gamma delta epsilon"
    # Here, spaces are missing before X tokens. The algorithm should back off as needed.
    segs = find_progressive_phrase_segments(text, query, kmax=3, ignore_case=True, max_segment_gap_chars=50)
    assert segs  # some segments must be detected
    # Ensure ordering is preserved (monotonic increasing ranges)
    for i in range(1, len(segs)):
        assert segs[i - 1][1] <= segs[i][0]


def test_placeholder_progressive_sanity():
    # Minimal sanity check to keep test module balance after removing
    # _collapse_to_shortest helper. Ensure function returns empty on no tokens.
    segs = find_progressive_phrase_segments("abc", "", kmax=3)
    assert segs == []
