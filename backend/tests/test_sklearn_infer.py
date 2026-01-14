"""Tests for sklearn inference."""
import pytest
from app.services.sklearn_infer import SklearnInferenceService, is_sklearn_available, get_sklearn_service
from pathlib import Path


def test_sklearn_service_initialization():
    """Test sklearn service initialization."""
    service = SklearnInferenceService()
    
    # If model exists, should load; if not, should be None
    if Path("models/sklearn/classifiers.joblib").exists():
        assert service.classifiers is not None
        assert service.encoder is not None
    else:
        # Service should still initialize but classifiers will be None
        assert service.classifiers is None or service.encoder is None


def test_classify_clause_if_available():
    """Test clause classification if sklearn model is available."""
    if not is_sklearn_available():
        pytest.skip("Sklearn model not available")
    
    service = get_sklearn_service()
    assert service is not None
    
    result = service.classify_clause(
        "This agreement may be terminated by either party with 30 days written notice."
    )
    
    assert "clause_type" in result
    assert "risk_score" in result
    assert "confidence" in result
    assert "type_probs" in result
    assert 0 <= result["risk_score"] <= 100
    assert 0 <= result["confidence"] <= 1
    assert isinstance(result["type_probs"], dict)
    assert len(result["type_probs"]) == 8  # 8 clause types


def test_classify_empty_text():
    """Test classification with empty text."""
    if not is_sklearn_available():
        pytest.skip("Sklearn model not available")
    
    service = get_sklearn_service()
    result = service.classify_clause("")
    assert "clause_type" in result
    assert "risk_score" in result
    assert "confidence" in result


def test_model_status_deterministic():
    """Test that model status is deterministic."""
    from app.services.onnx_infer import get_onnx_service
    
    onnx_service = get_onnx_service()
    status = onnx_service.get_model_status()
    
    assert status in ["onnx", "sklearn", "dummy"]
    
    # Status should be consistent
    status2 = onnx_service.get_model_status()
    assert status == status2
