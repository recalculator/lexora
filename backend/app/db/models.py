"""Database models."""
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, JSON, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship, deferred
from pgvector.sqlalchemy import Vector
from datetime import datetime

EMBEDDING_DIM = 384

Base = declarative_base()


class Document(Base):
    """Document model."""
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    text = relationship("DocumentText", back_populates="document", uselist=False)
    clauses = relationship("Clause", back_populates="document", cascade="all, delete-orphan")
    playbook = relationship("Playbook", back_populates="document", uselist=False, cascade="all, delete-orphan")
    redlines = relationship("Redlines", back_populates="document", uselist=False, cascade="all, delete-orphan")
    prompt_logs = relationship("PromptLog", back_populates="document", cascade="all, delete-orphan")


class DocumentText(Base):
    """Document text content."""
    __tablename__ = "document_texts"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, unique=True)
    text = Column(Text, nullable=False)
    json_chunks = Column(JSON, nullable=True)  # Store segmented chunks as JSON
    
    # Relationships
    document = relationship("Document", back_populates="text")


class Clause(Base):
    """Clause model."""
    __tablename__ = "clauses"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    idx = Column(Integer, nullable=False)  # Clause index within document
    text = Column(Text, nullable=False)
    start_char = Column(Integer, nullable=False)
    end_char = Column(Integer, nullable=False)
    clause_type = Column(String(100), nullable=True)  # e.g., "Termination", "Indemnification"
    risk_score = Column(Float, nullable=True)  # 0-100
    confidence = Column(Float, nullable=True)  # 0-1
    embedding = deferred(Column(Vector(EMBEDDING_DIM), nullable=True))  # Normalized MiniLM embedding

    # Relationships
    document = relationship("Document", back_populates="clauses")


class ReferenceClause(Base):
    """Precedent clause from a reference corpus (e.g. CUAD)."""
    __tablename__ = "reference_clauses"

    id = Column(Integer, primary_key=True)
    source_contract = Column(String(512), nullable=False)
    # All CUAD categories of this text (GIN-indexed varchar[] on Postgres; JSON on SQLite test DBs)
    categories = Column(ARRAY(String(100)).with_variant(JSON(), "sqlite"), nullable=False)
    text = Column(Text, nullable=False)
    embedding = deferred(Column(Vector(EMBEDDING_DIM), nullable=False))


class Playbook(Base):
    """Negotiation playbook."""
    __tablename__ = "playbooks"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, unique=True)
    json_output = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    document = relationship("Document", back_populates="playbook")


class Redlines(Base):
    """Redline suggestions."""
    __tablename__ = "redlines"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, unique=True)
    json_output = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    document = relationship("Document", back_populates="redlines")


class PromptLog(Base):
    """Log of LLM prompts and responses (optional)."""
    __tablename__ = "prompt_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    kind = Column(String(50), nullable=False)  # e.g., "playbook", "redlines"
    prompt = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    document = relationship("Document", back_populates="prompt_logs")


class ClauseExplanation(Base):
    """Cached clause explanations."""
    __tablename__ = "clause_explanations"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    clause_idx = Column(Integer, nullable=False)
    style = Column(String(20), nullable=False)  # "concise" or "detailed"
    json_output = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    document = relationship("Document")
