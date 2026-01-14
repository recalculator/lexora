"""Redline suggestions generation service."""
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from app.services.llm_client import call_llm_with_schema, log_prompt
from app.services.retrieval import create_retrieval
from app.core.logging import get_logger

logger = get_logger()


class RedlineSuggestion(BaseModel):
    """Redline suggestion for a clause."""
    clause_index: int = Field(description="Index of the clause")
    clause_type: Optional[str] = Field(description="Type of clause")
    original_text: str = Field(description="Original clause text")
    suggested_change: str = Field(description="Suggested redline change")
    rationale: str = Field(description="Reason for the change")
    risk_reduction: str = Field(description="How this reduces risk")
    citation: str = Field(description="Reference to contract section")


class RedlineSuggestions(BaseModel):
    """Redline suggestions output."""
    summary: str = Field(description="Summary of redline suggestions")
    priority_redlines: List[RedlineSuggestion] = Field(description="Priority redline suggestions")
    optional_redlines: List[RedlineSuggestion] = Field(description="Optional redline suggestions")
    general_notes: List[str] = Field(description="General notes about redlining")


def generate_redlines(clauses: List[Dict[str, any]], document_text: str, document_id: Optional[int] = None) -> RedlineSuggestions:
    """
    Generate redline suggestions using LLM with RAG.
    
    Args:
        clauses: List of clause dictionaries with classification results
        document_text: Full document text
        
    Returns:
        RedlineSuggestions instance
    """
    logger.info("Generating redline suggestions", num_clauses=len(clauses))
    
    # Create retrieval index
    retrieval = create_retrieval(clauses)
    
    # Build context from high-risk clauses
    high_risk_clauses = [
        c for c in clauses
        if c.get("risk_score", 0) > 50 and c.get("clause_type") is not None
    ]
    
    context_parts = []
    for clause in high_risk_clauses[:8]:  # Top 8 for redlining
        clause_text = clause.get("text", "")[:800]  # Longer for redlines
        clause_type = clause.get("clause_type", "Unknown")
        risk_score = clause.get("risk_score", 0)
        clause_idx = clause.get("idx", 0)
        context_parts.append(
            f"Clause {clause_idx} ({clause_type}, Risk: {risk_score:.1f}):\n{clause_text}\n"
        )
    
    context = "\n".join(context_parts)
    
    # Build prompt
    prompt = f"""You are a legal contract redlining expert. Analyze the following contract clauses and generate specific redline suggestions.

CONTRACT CLAUSES:
{context[:4000]}  # Truncate to avoid token limits

TASK:
Generate redline suggestions that include:
1. Summary of redline recommendations
2. Priority redlines (high-risk clauses that need changes)
3. Optional redlines (recommended but not critical)
4. General notes about redlining approach

For each redline suggestion, provide:
- Original text
- Suggested change (in track-changes format: [DEL: deleted text] [ADD: new text])
- Rationale
- Risk reduction explanation
- Citation

Focus on clauses with high risk scores. Provide concrete, actionable redline suggestions.

RESPOND WITH VALID JSON matching the schema."""
    
    try:
        redlines = call_llm_with_schema(
            prompt=prompt,
            schema=RedlineSuggestions,
            model=None,  # Use OPENAI_MODEL env var (fine-tuned model)
            temperature=0.2,  # Lower temperature for more consistent redlines
        )
        
        # Log prompt and response
        import json
        log_prompt(
            document_id=document_id,
            kind="redlines",
            prompt=prompt,
            response=json.dumps(redlines.model_dump())
        )
        
        logger.info("Generated redline suggestions", num_priority=len(redlines.priority_redlines))
        return redlines
    except Exception as e:
        logger.error("Failed to generate redlines", error=str(e))
        # Return minimal redlines on error
        return RedlineSuggestions(
            summary="Redline analysis in progress",
            priority_redlines=[],
            optional_redlines=[],
            general_notes=["Review all clauses carefully", "Consult with legal counsel before redlining"],
        )
