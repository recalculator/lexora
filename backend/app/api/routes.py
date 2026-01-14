"""API routes."""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
from pathlib import Path
import shutil
import uuid
from datetime import datetime

from app.db.session import get_db
from app.db.models import Document, DocumentText, Clause, Playbook, Redlines, PromptLog, ClauseExplanation
from app.services.pdf_extract import extract_text
from app.services.clause_segment import segment_clauses
from app.services.onnx_infer import get_onnx_service, CLAUSE_TYPES
from app.services.playbook import generate_playbook
from app.services.redlines import generate_redlines
from app.services.explain import explain_clause as explain_clause_func, ClauseExplanationResponse
from app.core.config import settings
from app.core.logging import get_logger
from pydantic import BaseModel
from typing import List as TypingList
import os

router = APIRouter(prefix="/api", tags=["api"])
logger = get_logger()


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a PDF document."""
    # Validate file type
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    # Validate file size
    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {settings.max_upload_size} bytes"
        )
    
    # Generate document ID
    doc_id = None
    
    try:
        # Save file
        storage_path = Path(settings.storage_path)
        storage_path.mkdir(parents=True, exist_ok=True)
        
        # Create document record
        doc = Document(
            filename=str(uuid.uuid4()) + ".pdf",
            original_filename=file.filename,
            created_at=datetime.utcnow(),
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        doc_id = doc.id
        
        # Save PDF
        pdf_path = storage_path / f"{doc.id}.pdf"
        with open(pdf_path, "wb") as f:
            f.write(content)
        
        # Extract text
        text, success = extract_text(str(pdf_path))
        
        # Store text
        doc_text = DocumentText(
            document_id=doc.id,
            text=text,
            json_chunks=None,
        )
        db.add(doc_text)
        db.commit()
        
        logger.info("Document uploaded and processed", document_id=doc.id, filename=file.filename)
        
        return JSONResponse(content={
            "document_id": doc.id,
            "filename": file.filename,
            "status": "uploaded",
            "text_length": len(text),
        })
        
    except Exception as e:
        logger.error("Failed to upload document", error=str(e))
        if doc_id:
            # Clean up
            db.delete(db.query(Document).filter(Document.id == doc_id).first())
            db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")


@router.post("/analyze/{document_id}")
async def analyze_document(
    document_id: int,
    db: Session = Depends(get_db),
):
    """Analyze document and extract clauses."""
    # Get document
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Get document text
    doc_text = db.query(DocumentText).filter(DocumentText.document_id == document_id).first()
    if not doc_text:
        raise HTTPException(status_code=404, detail="Document text not found")
    
    # Check if already analyzed
    existing_clauses = db.query(Clause).filter(Clause.document_id == document_id).all()
    if existing_clauses:
        logger.info("Document already analyzed", document_id=document_id)
        return JSONResponse(content={
            "document_id": document_id,
            "status": "already_analyzed",
            "num_clauses": len(existing_clauses),
        })
    
    try:
        # Segment clauses
        clauses = segment_clauses(doc_text.text)
        
        # Classify clauses using ONNX/sklearn/dummy
        onnx_service = get_onnx_service()
        model_status = onnx_service.get_model_status()
        classified_clauses = []
        
        for clause in clauses:
            classification = onnx_service.classify_clause(clause["text"])
            
            db_clause = Clause(
                document_id=document_id,
                idx=clause["idx"],
                text=clause["text"],
                start_char=clause["start_char"],
                end_char=clause["end_char"],
                clause_type=classification["clause_type"],
                risk_score=classification["risk_score"],
                confidence=classification["confidence"],
            )
            db.add(db_clause)
            
            classified_clauses.append({
                **clause,
                **classification,
            })
        
        db.commit()
        
        logger.info("Document analyzed", document_id=document_id, num_clauses=len(classified_clauses), model_status=model_status)
        
        return JSONResponse(content={
            "document_id": document_id,
            "status": "analyzed",
            "num_clauses": len(classified_clauses),
            "clauses": classified_clauses,
            "model_status": model_status,
        })
        
    except Exception as e:
        logger.error("Failed to analyze document", document_id=document_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to analyze document: {str(e)}")


@router.post("/playbook/{document_id}")
async def generate_playbook_endpoint(
    document_id: int,
    db: Session = Depends(get_db),
):
    """Generate negotiation playbook."""
    # Get document
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Get clauses
    clauses = db.query(Clause).filter(Clause.document_id == document_id).order_by(Clause.idx).all()
    if not clauses:
        raise HTTPException(status_code=400, detail="Document must be analyzed first")
    
    # Get document text
    doc_text = db.query(DocumentText).filter(DocumentText.document_id == document_id).first()
    if not doc_text:
        raise HTTPException(status_code=404, detail="Document text not found")
    
    # Check if already generated
    existing_playbook = db.query(Playbook).filter(Playbook.document_id == document_id).first()
    if existing_playbook:
        logger.info("Playbook already generated", document_id=document_id)
        return JSONResponse(content=existing_playbook.json_output)
    
    try:
        # Convert clauses to dict format
        clauses_dict = [
            {
                "idx": c.idx,
                "text": c.text,
                "start_char": c.start_char,
                "end_char": c.end_char,
                "clause_type": c.clause_type,
                "risk_score": c.risk_score,
                "confidence": c.confidence,
            }
            for c in clauses
        ]
        
        # Generate playbook
        playbook = generate_playbook(clauses_dict, doc_text.text, document_id=document_id)
        
        # Store playbook
        db_playbook = Playbook(
            document_id=document_id,
            json_output=playbook.model_dump(),
        )
        db.add(db_playbook)
        db.commit()
        
        logger.info("Playbook generated", document_id=document_id)
        
        return JSONResponse(content=playbook.model_dump())
        
    except Exception as e:
        logger.error("Failed to generate playbook", document_id=document_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to generate playbook: {str(e)}")


@router.post("/redlines/{document_id}")
async def generate_redlines_endpoint(
    document_id: int,
    db: Session = Depends(get_db),
):
    """Generate redline suggestions."""
    # Get document
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Get clauses
    clauses = db.query(Clause).filter(Clause.document_id == document_id).order_by(Clause.idx).all()
    if not clauses:
        raise HTTPException(status_code=400, detail="Document must be analyzed first")
    
    # Get document text
    doc_text = db.query(DocumentText).filter(DocumentText.document_id == document_id).first()
    if not doc_text:
        raise HTTPException(status_code=404, detail="Document text not found")
    
    # Check if already generated
    existing_redlines = db.query(Redlines).filter(Redlines.document_id == document_id).first()
    if existing_redlines:
        logger.info("Redlines already generated", document_id=document_id)
        return JSONResponse(content=existing_redlines.json_output)
    
    try:
        # Convert clauses to dict format
        clauses_dict = [
            {
                "idx": c.idx,
                "text": c.text,
                "start_char": c.start_char,
                "end_char": c.end_char,
                "clause_type": c.clause_type,
                "risk_score": c.risk_score,
                "confidence": c.confidence,
            }
            for c in clauses
        ]
        
        # Generate redlines
        redlines = generate_redlines(clauses_dict, doc_text.text, document_id=document_id)
        
        # Store redlines
        db_redlines = Redlines(
            document_id=document_id,
            json_output=redlines.model_dump(),
        )
        db.add(db_redlines)
        db.commit()
        
        logger.info("Redlines generated", document_id=document_id)
        
        return JSONResponse(content=redlines.model_dump())
        
    except Exception as e:
        logger.error("Failed to generate redlines", document_id=document_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to generate redlines: {str(e)}")


@router.get("/report/{document_id}")
async def get_report(
    document_id: int,
    db: Session = Depends(get_db),
):
    """Get complete analysis report."""
    # Get document
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Get all related data
    doc_text = db.query(DocumentText).filter(DocumentText.document_id == document_id).first()
    clauses = db.query(Clause).filter(Clause.document_id == document_id).order_by(Clause.idx).all()
    playbook = db.query(Playbook).filter(Playbook.document_id == document_id).first()
    redlines = db.query(Redlines).filter(Redlines.document_id == document_id).first()
    
    return JSONResponse(content={
        "document": {
            "id": doc.id,
            "filename": doc.original_filename,
            "created_at": doc.created_at.isoformat(),
        },
        "text": {
            "length": len(doc_text.text) if doc_text else 0,
            "has_text": doc_text is not None,
        },
        "clauses": [
            {
                "idx": c.idx,
                "text": c.text[:200] + "..." if len(c.text) > 200 else c.text,
                "clause_type": c.clause_type,
                "risk_score": c.risk_score,
                "confidence": c.confidence,
            }
            for c in clauses
        ] if clauses else [],
        "playbook": playbook.json_output if playbook else None,
        "redlines": redlines.json_output if redlines else None,
    })


@router.get("/documents")
async def list_documents(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    """List all documents."""
    docs = db.query(Document).offset(skip).limit(limit).all()
    return JSONResponse(content={
        "documents": [
            {
                "id": doc.id,
                "filename": doc.original_filename,
                "created_at": doc.created_at.isoformat(),
            }
            for doc in docs
        ],
        "total": len(docs),
    })


@router.get("/document/{document_id}/pdf")
async def get_pdf(
    document_id: int,
    db: Session = Depends(get_db),
):
    """Get PDF file for a document."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    pdf_path = Path(settings.storage_path) / f"{document_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found")
    
    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=doc.original_filename,
    )


@router.get("/document/{document_id}/summary")
async def get_document_summary(
    document_id: int,
    db: Session = Depends(get_db),
):
    """Get document summary with top risks and model info."""
    # Get document
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Get clauses
    clauses = db.query(Clause).filter(Clause.document_id == document_id).all()
    
    if not clauses:
        raise HTTPException(status_code=400, detail="Document must be analyzed first")
    
    # Compute top risks (top 5 by risk_score desc, then confidence desc)
    top_risks_clauses = sorted(
        clauses,
        key=lambda c: (c.risk_score or 0, c.confidence or 0),
        reverse=True
    )[:5]
    
    top_risks = [
        {
            "idx": c.idx,
            "clause_type": c.clause_type,
            "risk_score": c.risk_score,
            "confidence": c.confidence,
            "preview": c.text[:160] + "..." if len(c.text) > 160 else c.text,
        }
        for c in top_risks_clauses
    ]
    
    # Compute model info
    confidences = [c.confidence for c in clauses if c.confidence is not None]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    low_conf_threshold = 0.3
    low_confidence_count = sum(1 for c in confidences if c < low_conf_threshold)
    
    # Get model status
    onnx_service = get_onnx_service()
    model_status = onnx_service.get_model_status()
    
    model_info = {
        "clause_model": "ClauseRiskNet",
        "version": os.getenv("MODEL_VERSION", "v0.1"),
        "supported_clause_types": CLAUSE_TYPES,
        "avg_confidence": round(avg_confidence, 3),
        "low_confidence_count": low_confidence_count,
        "low_conf_threshold": low_conf_threshold,
        "model_status": model_status,
    }
    
    return JSONResponse(content={
        "document_id": document_id,
        "top_risks": top_risks,
        "model_info": model_info,
    })


@router.post("/explain/{document_id}/{clause_idx}")
async def explain_clause_endpoint(
    document_id: int,
    clause_idx: int,
    body: dict,
    db: Session = Depends(get_db),
):
    """Explain why a clause was flagged."""
    # Get document
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Get clause
    clause = db.query(Clause).filter(
        Clause.document_id == document_id,
        Clause.idx == clause_idx
    ).first()
    
    if not clause:
        raise HTTPException(status_code=404, detail="Clause not found")
    
    # Get style from body
    style = body.get("style", "concise")
    if style not in ["concise", "detailed"]:
        style = "concise"
    
    # Check cache
    cached = db.query(ClauseExplanation).filter(
        ClauseExplanation.document_id == document_id,
        ClauseExplanation.clause_idx == clause_idx,
        ClauseExplanation.style == style,
    ).first()
    
    if cached:
        logger.info("Returning cached explanation", document_id=document_id, clause_idx=clause_idx)
        return JSONResponse(content=cached.json_output)
    
    try:
        # Generate explanation
        explanation = explain_clause_func(
            clause_text=clause.text,
            clause_type=clause.clause_type,
            risk_score=clause.risk_score or 0,
            confidence=clause.confidence or 0,
            document_id=document_id,
            clause_idx=clause_idx,
            document_title=doc.original_filename,
            style=style,
        )
        
        # Convert to dict
        explanation_dict = explanation.model_dump()
        
        # Cache it
        db_explanation = ClauseExplanation(
            document_id=document_id,
            clause_idx=clause_idx,
            style=style,
            json_output=explanation_dict,
        )
        db.add(db_explanation)
        db.commit()
        
        logger.info("Generated and cached explanation", document_id=document_id, clause_idx=clause_idx)
        
        return JSONResponse(content=explanation_dict)
        
    except Exception as e:
        logger.error("Failed to generate explanation", document_id=document_id, clause_idx=clause_idx, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to generate explanation: {str(e)}")


@router.get("/sample_contract")
async def get_sample_contract():
    """Get sample contract PDF for demo."""
    sample_path = Path(__file__).parent.parent / "static" / "sample_contract.pdf"
    
    if not sample_path.exists():
        raise HTTPException(status_code=404, detail="Sample contract not found")
    
    return FileResponse(
        str(sample_path),
        media_type="application/pdf",
        filename="sample_contract.pdf",
    )
