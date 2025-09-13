from pathlib import Path

import pytest

from pdfhl.pdfhl import _parse_args


def test_single_text_defaults():
    ns = _parse_args(["input.pdf", "--text", "Hello"])
    assert ns.pdf == Path("input.pdf")
    assert ns.text == "Hello"
    assert ns.pattern is None
    assert getattr(ns, "recipe", None) is None
    assert ns.regex is False
    # case handling: code uses not case_sensitive
    assert getattr(ns, "case_sensitive", False) is False
    assert ns.literal_whitespace is False
    assert ns.allow_multiple is False
    assert ns.output is None
    assert ns.label is None
    assert ns.color == "yellow"
    assert float(ns.opacity) == 0.3
    assert getattr(ns, "report", None) is None


def test_case_sensitive_flag():
    ns = _parse_args(["in.pdf", "--text", "x", "--case-sensitive"])
    assert ns.case_sensitive is True
    # effective ignore_case becomes False when case_sensitive is True
    effective_ignore = not getattr(ns, "case_sensitive", False)
    assert effective_ignore is False


def test_recipe_parse():
    ns = _parse_args(["in.pdf", "--recipe", "examples/simple-recipe-array.json"])
    assert ns.recipe == Path("examples/simple-recipe-array.json")
    assert getattr(ns, "text", None) is None
    assert getattr(ns, "pattern", None) is None


def test_mutually_exclusive_text_and_recipe():
    with pytest.raises(SystemExit) as ei:
        _parse_args(["in.pdf", "--text", "x", "--recipe", "foo.json"])
    assert ei.value.code == 2


def test_help_shows_recipe_format(capsys):
    with pytest.raises(SystemExit) as ei:
        _parse_args(["-h"])
    assert ei.value.code == 0
    out = capsys.readouterr().out
    assert "JSON Recipe Format" in out
    # Show that examples/field hints appear
    assert "items" in out
    # Exit codes should be documented as well
    assert "Exit Codes" in out
    assert "0: OK" in out
