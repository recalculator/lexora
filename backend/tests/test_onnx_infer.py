"""Tests for ONNX inference."""
import pytest
from app.services.onnx_infer import ONNXInferenceService, get_onnx_service


def test_classify_clause():
    """Test clause classification."""
    service = get_onnx_service()
    
    # Test with termination clause
    result = service.classify_clause(
        "This agreement may be terminated by either party with 30 days written notice."
    )
    
    assert "clause_type" in result
    assert "risk_score" in result
    assert "confidence" in result
    assert "type_probs" in result
    assert 0 <= result["risk_score"] <= 100
    assert 0 <= result["confidence"] <= 1


def test_classify_empty():
    """Test classification with empty text."""
    service = get_onnx_service()
    result = service.classify_clause("")
    assert "clause_type" in result
