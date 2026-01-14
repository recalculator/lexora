"""Tests for explain endpoint."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models import Base, Document, Clause, DocumentText, ClauseExplanation
from app.main import app
from app.db.session import get_db
from app.services.explain import ClauseExplanationResponse, QuotedSpan
from datetime import datetime

# Create test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_explain.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db():
    """Create test database."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db):
    """Create test client."""
    def override_get_db():
        try:
            yield db
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_document_with_clause(db):
    """Create sample document with a clause."""
    doc = Document(
        filename="test.pdf",
        original_filename="test.pdf",
        created_at=datetime.utcnow(),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    
    doc_text = DocumentText(
        document_id=doc.id,
        text="Sample contract text",
    )
    db.add(doc_text)
    
    clause = Clause(
        document_id=doc.id,
        idx=0,
        text="This agreement may be terminated by either party with 30 days written notice.",
        start_char=0,
        end_char=80,
        clause_type="Termination",
        risk_score=85.0,
        confidence=0.90,
    )
    db.add(clause)
    db.commit()
    
    return doc, clause


@patch('app.services.explain.call_llm_with_schema')
def test_explain_endpoint_returns_cached_result(mock_llm, client, sample_document_with_clause, db):
    """Test that explain endpoint returns cached result on second call."""
    doc, clause = sample_document_with_clause
    
    # Mock LLM response
    mock_response = ClauseExplanationResponse(
        document_id=doc.id,
        clause_idx=clause.idx,
        clause_type="Termination",
        risk_score=85.0,
        confidence=0.90,
        explanation="This clause allows termination with short notice.",
        risk_drivers=["Short notice period", "Unilateral termination"],
        suggested_negotiation_moves=["Request longer notice period", "Add mutual termination clause"],
        quoted_spans=[
            QuotedSpan(quote="30 days written notice", reason="Short notice period")
        ],
    )
    mock_llm.return_value = mock_response
    
    # First call - should call LLM
    response1 = client.post(
        f"/api/explain/{doc.id}/{clause.idx}",
        json={"style": "concise"}
    )
    
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["explanation"] == "This clause allows termination with short notice."
    assert mock_llm.called
    
    # Reset mock call count
    mock_llm.reset_mock()
    
    # Second call - should return cached result
    response2 = client.post(
        f"/api/explain/{doc.id}/{clause.idx}",
        json={"style": "concise"}
    )
    
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["explanation"] == "This clause allows termination with short notice."
    # LLM should not be called again
    assert not mock_llm.called


@patch('app.services.explain.call_llm_with_schema')
def test_explain_endpoint_different_style_creates_new_cache(mock_llm, client, sample_document_with_clause, db):
    """Test that different style creates new cache entry."""
    doc, clause = sample_document_with_clause
    
    # Mock LLM response for concise
    mock_response_concise = ClauseExplanationResponse(
        document_id=doc.id,
        clause_idx=clause.idx,
        clause_type="Termination",
        risk_score=85.0,
        confidence=0.90,
        explanation="Concise explanation",
        risk_drivers=["Risk 1"],
        suggested_negotiation_moves=["Move 1"],
        quoted_spans=[],
    )
    
    # Mock LLM response for detailed
    mock_response_detailed = ClauseExplanationResponse(
        document_id=doc.id,
        clause_idx=clause.idx,
        clause_type="Termination",
        risk_score=85.0,
        confidence=0.90,
        explanation="Detailed explanation with more context",
        risk_drivers=["Risk 1", "Risk 2"],
        suggested_negotiation_moves=["Move 1", "Move 2"],
        quoted_spans=[],
    )
    
    mock_llm.side_effect = [mock_response_concise, mock_response_detailed]
    
    # First call with concise
    response1 = client.post(
        f"/api/explain/{doc.id}/{clause.idx}",
        json={"style": "concise"}
    )
    assert response1.status_code == 200
    assert response1.json()["explanation"] == "Concise explanation"
    
    # Second call with detailed - should call LLM again
    response2 = client.post(
        f"/api/explain/{doc.id}/{clause.idx}",
        json={"style": "detailed"}
    )
    assert response2.status_code == 200
    assert response2.json()["explanation"] == "Detailed explanation with more context"
    assert mock_llm.call_count == 2


def test_explain_endpoint_not_found(client):
    """Test explain endpoint with non-existent document."""
    response = client.post(
        "/api/explain/99999/0",
        json={"style": "concise"}
    )
    assert response.status_code == 404
