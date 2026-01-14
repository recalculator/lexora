"""Tests for clause segmentation."""
import pytest
from app.services.clause_segment import segment_clauses, is_heading


def test_is_heading():
    """Test heading detection."""
    assert is_heading("TERMINATION") == True
    assert is_heading("SECTION 1. INTRODUCTION") == True
    assert is_heading("1. Introduction") == True
    assert is_heading("This is a normal paragraph.") == False


def test_segment_clauses():
    """Test clause segmentation."""
    text = """TERMINATION
This agreement may be terminated by either party.

INDEMNIFICATION
Party A agrees to indemnify Party B."""
    
    clauses = segment_clauses(text)
    
    assert len(clauses) >= 2
    assert all("idx" in c for c in clauses)
    assert all("text" in c for c in clauses)
    assert all("start_char" in c for c in clauses)
    assert all("end_char" in c for c in clauses)


def test_segment_small_text():
    """Test segmentation with small text."""
    text = "Short text."
    clauses = segment_clauses(text)
    assert len(clauses) >= 1
