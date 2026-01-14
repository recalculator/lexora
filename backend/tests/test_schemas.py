"""Tests for Pydantic schemas."""
import pytest
from app.services.playbook import NegotiationPlaybook, ClauseRecommendation
from app.services.redlines import RedlineSuggestions, RedlineSuggestion


def test_playbook_schema():
    """Test playbook schema validation."""
    playbook = NegotiationPlaybook(
        document_summary="Test summary",
        overall_risk_assessment="medium",
        priority_clauses=[],
        general_recommendations=["Test recommendation"],
        key_provisions=["Test provision"],
    )
    
    assert playbook.document_summary == "Test summary"
    assert playbook.overall_risk_assessment == "medium"


def test_redline_schema():
    """Test redline schema validation."""
    redlines = RedlineSuggestions(
        summary="Test summary",
        priority_redlines=[],
        optional_redlines=[],
        general_notes=["Test note"],
    )
    
    assert redlines.summary == "Test summary"
    assert len(redlines.general_notes) == 1
