from pdfhl.pdfhl import group_bboxes_to_line_rects


def test_group_bboxes_to_line_rects_merges_lines():
    # Two lines of three characters each
    line1 = [
        (10.0, 10.0, 12.0, 14.0),
        (13.0, 10.2, 15.0, 14.1),
        (16.0, 10.1, 18.0, 14.2),
    ]
    line2 = [
        (10.0, 30.0, 12.0, 34.0),
        (13.0, 30.1, 15.0, 34.2),
        (16.0, 29.9, 18.0, 34.1),
    ]
    rects = group_bboxes_to_line_rects(line1 + line2, y_tol=3.0)
    assert len(rects) == 2
    # Check merged extents roughly match
    (x0a, y0a, x1a, y1a) = rects[0]
    (x0b, y0b, x1b, y1b) = rects[1]
    assert x0a == 10.0 and x1a == 18.0
    assert x0b == 10.0 and x1b == 18.0
    assert y0a <= 10.2 and y1a >= 14.0
    assert y0b <= 30.1 and y1b >= 34.0
