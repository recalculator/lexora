"""Clause explanation service using LLM."""
from typing import Dict, Optional, List
from pydantic import BaseModel, Field
from app.services.llm_client import call_llm_with_schema, log_prompt
from app.core.logging import get_logger

logger = get_logger()


class QuotedSpan(BaseModel):
    """Quoted span from clause text."""
    quote: str = Field(description="Exact snippet from clause text")
    reason: str = Field(description="Why this snippet matters")


class ClauseExplanationResponse(BaseModel):
    """Clause explanation response."""
    document_id: int = Field(description="Document ID")
    clause_idx: int = Field(description="Clause index")
    clause_type: Optional[str] = Field(description="Type of clause")
    risk_score: float = Field(description="Risk score 0-100")
    confidence: float = Field(description="Confidence 0-1")
    explanation: str = Field(description="Short paragraph explaining why flagged")
    risk_drivers: List[str] = Field(description="List of risk drivers")
    suggested_negotiation_moves: List[str] = Field(description="Suggested negotiation moves")
    quoted_spans: List[QuotedSpan] = Field(description="Quoted spans from clause text")


def explain_clause(
    clause_text: str,
    clause_type: Optional[str],
    risk_score: float,
    confidence: float,
    document_id: int,
    clause_idx: int,
    document_title: str = "Contract",
    style: str = "concise",
) -> ClauseExplanationResponse:
    """
    Generate explanation for why a clause was flagged.
    
    Args:
        clause_text: Full clause text
        clause_type: Detected clause type
        risk_score: Risk score (0-100)
        confidence: Confidence (0-1)
        document_id: Document ID
        clause_idx: Clause index
        document_title: Document title for context
        style: "concise" or "detailed"
        
    Returns:
        ClauseExplanationResponse
    """
    logger.info("Generating clause explanation", clause_type=clause_type, risk_score=risk_score, style=style)
    
    # Build prompt
    detail_level = "brief and focused" if style == "concise" else "comprehensive and detailed"
    
    prompt = f"""You are a legal contract analysis expert. Explain why this clause was flagged as high-risk.

DOCUMENT: {document_title}
CLAUSE TYPE: {clause_type or "Unknown"}
RISK SCORE: {risk_score:.1f}/100
CONFIDENCE: {confidence:.1%}

CLAUSE TEXT:
{clause_text}

TASK:
Provide a {detail_level} explanation that:
1. Explains why this clause is flagged (explanation field)
2. Lists specific risk drivers (risk_drivers array)
3. Suggests negotiation moves (suggested_negotiation_moves array)
4. Quotes exact snippets from the clause text with reasons (quoted_spans array)

GROUNDING RULES:
- Only use information from the clause text provided above
- Do not reference external law or regulations
- Must quote exact snippets from the clause text in quoted_spans
- If the clause text is insufficient, state "Insufficient context in clause text" in the explanation
- Each quoted_spans entry must have an exact quote from the clause and a reason

RESPOND WITH VALID JSON matching the schema."""
    
    try:
        # Call LLM with a schema that doesn't require document_id/clause_idx
        # We'll construct the full response with those fields after
        class TempExplanation(BaseModel):
            explanation: str = Field(description="Short paragraph explaining why flagged")
            risk_drivers: List[str] = Field(description="List of risk drivers")
            suggested_negotiation_moves: List[str] = Field(description="Suggested negotiation moves")
            quoted_spans: List[QuotedSpan] = Field(description="Quoted spans from clause text")
        
        temp_response = call_llm_with_schema(
            prompt=prompt,
            schema=TempExplanation,
            model=None,  # Use OPENAI_MODEL env var (fine-tuned model)
            temperature=0.2,
            max_retries=2,
        )
        
        # Construct full response with all required fields
        response = ClauseExplanationResponse(
            document_id=document_id,
            clause_idx=clause_idx,
            clause_type=clause_type,
            risk_score=risk_score,
            confidence=confidence,
            explanation=temp_response.explanation,
            risk_drivers=temp_response.risk_drivers,
            suggested_negotiation_moves=temp_response.suggested_negotiation_moves,
            quoted_spans=temp_response.quoted_spans,
        )
        
        # Log prompt and response
        import json
        log_prompt(
            document_id=document_id,
            kind="explain",
            prompt=prompt,
            response=json.dumps(response.model_dump())
        )
        
        logger.info("Generated clause explanation", clause_type=clause_type)
        return response
        
    except Exception as e:
        logger.error("Failed to generate explanation", error=str(e))
        # Return minimal explanation on error
        return ClauseExplanationResponse(
            document_id=document_id,
            clause_idx=clause_idx,
            clause_type=clause_type,
            risk_score=risk_score,
            confidence=confidence,
            explanation="Unable to generate explanation. Please review the clause manually.",
            risk_drivers=["High risk score indicates potential concerns"],
            suggested_negotiation_moves=["Review clause with legal counsel", "Request modifications"],
            quoted_spans=[],
        )
