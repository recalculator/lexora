"""Tests for summary endpoint."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models import Base, Document, Clause, DocumentText
from app.main import app
from app.db.session import get_db
from datetime import datetime

# Create test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
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
def sample_document(db):
    """Create sample document with clauses."""
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
    
    # Add clauses with different risk scores
    clauses = [
        Clause(
            document_id=doc.id,
            idx=0,
            text="High risk clause text here",
            start_char=0,
            end_char=25,
            clause_type="Indemnification",
            risk_score=90.0,
            confidence=0.95,
        ),
        Clause(
            document_id=doc.id,
            idx=1,
            text="Medium risk clause text",
            start_char=26,
            end_char=50,
            clause_type="Termination",
            risk_score=70.0,
            confidence=0.85,
        ),
        Clause(
            document_id=doc.id,
            idx=2,
            text="Low risk clause text",
            start_char=51,
            end_char=75,
            clause_type="Confidentiality",
            risk_score=30.0,
            confidence=0.75,
        ),
    ]
    
    for clause in clauses:
        db.add(clause)
    
    db.commit()
    return doc


def test_summary_endpoint_returns_top_risks_ordered(client, sample_document):
    """Test that summary endpoint returns top risks correctly ordered."""
    response = client.get(f"/api/document/{sample_document.id}/summary")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "document_id" in data
    assert "top_risks" in data
    assert "model_info" in data
    
    # Check top risks are ordered by risk_score desc
    top_risks = data["top_risks"]
    assert len(top_risks) == 3  # We have 3 clauses
    
    # Verify ordering: highest risk first
    assert top_risks[0]["risk_score"] == 90.0
    assert top_risks[0]["clause_type"] == "Indemnification"
    assert top_risks[1]["risk_score"] == 70.0
    assert top_risks[2]["risk_score"] == 30.0
    
    # Check model info
    model_info = data["model_info"]
    assert model_info["clause_model"] == "ClauseRiskNet"
    assert "version" in model_info
    assert "supported_clause_types" in model_info
    assert "avg_confidence" in model_info
    assert "low_confidence_count" in model_info


def test_summary_endpoint_not_found(client):
    """Test summary endpoint with non-existent document."""
    response = client.get("/api/document/99999/summary")
    assert response.status_code == 404


def test_summary_endpoint_no_clauses(client, db):
    """Test summary endpoint with document that has no clauses."""
    doc = Document(
        filename="empty.pdf",
        original_filename="empty.pdf",
        created_at=datetime.utcnow(),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    
    response = client.get(f"/api/document/{doc.id}/summary")
    assert response.status_code == 400
