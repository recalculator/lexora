"""Redline suggestions generation service."""
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from app.services.llm_client import call_llm_with_schema, log_prompt
from app.services.rag import CITATION_INSTRUCTIONS, build_context, check_grounding, order_priority_clauses
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
    citation: str = Field(description="Reference to contract section, citing evidence IDs such as C4 or P1043")
    evidence_ids: List[str] = Field(default_factory=list, description="IDs of the evidence relied on, e.g. [\"C4\", \"P1043\"]")


class RedlineSuggestions(BaseModel):
    """Redline suggestions output."""
    summary: str = Field(description="Summary of redline suggestions")
    priority_redlines: List[RedlineSuggestion] = Field(description="Priority redline suggestions")
    optional_redlines: List[RedlineSuggestion] = Field(description="Optional redline suggestions")
    general_notes: List[str] = Field(description="General notes about redlining")


def generate_redlines(
    clauses: List[Dict[str, any]],
    document_text: str,
    document_id: Optional[int] = None,
    db=None,
) -> RedlineSuggestions:
    """
    Generate redline suggestions using LLM with RAG.
    
    Args:
        clauses: List of clause dictionaries with classification results
        document_text: Full document text
        document_id: Document ID (scopes same-contract retrieval)
        db: Database session for vector retrieval (TF-IDF only if None)
        
    Returns:
        RedlineSuggestions instance
    """
    logger.info("Generating redline suggestions", num_clauses=len(clauses))
    
    # Top 8 typed high-risk clauses, highest risk first, with longer clause
    # text for redlining plus retrieved same-contract clauses and precedents.
    # Context is capped at 8000 chars (whole evidence blocks only).
    priority = order_priority_clauses(clauses, min_risk=50, limit=8, require_type=True)
    evidence = build_context(priority, clauses, session=db, document_id=document_id, clause_chars=800, max_chars=8000)
    
    # Build prompt
    prompt = f"""You are a legal contract redlining expert. Analyze the following contract clauses and generate specific redline suggestions.

CONTRACT CLAUSES:
{evidence.text}

{CITATION_INSTRUCTIONS}

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
        
        check_grounding(redlines.priority_redlines + redlines.optional_redlines, evidence, kind="redlines")
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
