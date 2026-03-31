"""Tests for bill analyzer (placeholder for Phase 2)."""

from ingestion.statutes import extract_references


def test_extract_rs_references():
    """Should extract R.S. citations from text."""
    text = "This bill amends R.S. 30:4(A)(1) and R.S. 22:1892 to require..."
    refs = extract_references(text)
    assert len(refs) == 2
    assert refs[0]["citation"] == "R.S. 30:4(A)(1)"
    assert refs[0]["title"] == "30"
    assert refs[1]["citation"] == "R.S. 22:1892"


def test_extract_civil_code_references():
    """Should extract Civil Code article citations."""
    text = "as provided in La. C.C. Art. 2315 and C.C. Art. 2316"
    refs = extract_references(text)
    cc_refs = [r for r in refs if r["type"] == "CC"]
    assert len(cc_refs) == 2


def test_no_duplicates():
    """Same citation appearing twice should only be returned once."""
    text = "See R.S. 30:4 as amended. Again, R.S. 30:4 applies here."
    refs = extract_references(text)
    rs_refs = [r for r in refs if r["citation"] == "R.S. 30:4"]
    assert len(rs_refs) == 1
