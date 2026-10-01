"""Negotiation playbook generation service."""
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from app.services.llm_client import call_llm_with_schema, log_prompt
from app.services.rag import CITATION_INSTRUCTIONS, build_context, check_grounding, order_priority_clauses
from app.core.logging import get_logger

logger = get_logger()


class ClauseRecommendation(BaseModel):
    """Recommendation for a specific clause."""
    clause_index: int = Field(description="Index of the clause in the document")
    clause_type: Optional[str] = Field(description="Type of clause")
    risk_level: str = Field(description="Risk level: low, medium, high, critical")
    concern: str = Field(description="Main concern with this clause")
    recommendation: str = Field(description="Recommended action")
    negotiation_strategy: str = Field(description="Specific negotiation strategy")
    citation: str = Field(description="Reference to contract section, citing evidence IDs such as C4 or P1043")
    evidence_ids: List[str] = Field(default_factory=list, description="IDs of the evidence relied on, e.g. [\"C4\", \"P1043\"]")


class NegotiationPlaybook(BaseModel):
    """Negotiation playbook output."""
    document_summary: str = Field(description="Brief summary of the contract")
    overall_risk_assessment: str = Field(description="Overall risk level: low, medium, high, critical")
    priority_clauses: List[ClauseRecommendation] = Field(description="List of priority clauses to negotiate")
    general_recommendations: List[str] = Field(description="General negotiation recommendations")
    key_provisions: List[str] = Field(description="Key provisions to highlight")


def generate_playbook(
    clauses: List[Dict[str, any]],
    document_text: str,
    document_id: Optional[int] = None,
    db=None,
) -> NegotiationPlaybook:
    """
    Generate negotiation playbook using LLM with RAG.
    
    Args:
        clauses: List of clause dictionaries with classification results
        document_text: Full document text
        document_id: Document ID (scopes same-contract retrieval)
        db: Database session for vector retrieval (TF-IDF only if None)
        
    Returns:
        NegotiationPlaybook instance
    """
    logger.info("Generating negotiation playbook", num_clauses=len(clauses))
    
    # Top 10 high-risk clauses, highest risk first, each with retrieved
    # same-contract clauses and precedents. Context is capped at 6000 chars
    # (whole evidence blocks only) to avoid token limits.
    priority = order_priority_clauses(clauses, min_risk=60, limit=10)
    evidence = build_context(priority, clauses, session=db, document_id=document_id, clause_chars=500, max_chars=6000)
    
    # Build prompt
    prompt = f"""You are a legal contract negotiation expert. Analyze the following contract clauses and generate a comprehensive negotiation playbook.

CONTRACT CONTEXT:
{evidence.text}

{CITATION_INSTRUCTIONS}

TASK:
Generate a negotiation playbook that includes:
1. Document summary
2. Overall risk assessment
3. Priority clauses with specific recommendations
4. General negotiation recommendations
5. Key provisions to highlight

Focus on clauses with high risk scores. Provide actionable negotiation strategies.

RESPOND WITH VALID JSON matching the schema."""
    
    try:
        playbook = call_llm_with_schema(
            prompt=prompt,
            schema=NegotiationPlaybook,
            model=None,  # Use OPENAI_MODEL env var (fine-tuned model)
            temperature=0.3,
        )
        
        # Log prompt and response
        import json
        log_prompt(
            document_id=document_id,
            kind="playbook",
            prompt=prompt,
            response=json.dumps(playbook.model_dump())
        )
        
        check_grounding(playbook.priority_clauses, evidence, kind="playbook")
        logger.info("Generated negotiation playbook", num_recommendations=len(playbook.priority_clauses))
        return playbook
    except Exception as e:
        logger.error("Failed to generate playbook", error=str(e))
        # Return minimal playbook on error
        return NegotiationPlaybook(
            document_summary="Analysis in progress",
            overall_risk_assessment="medium",
            priority_clauses=[],
            general_recommendations=["Review all clauses carefully", "Consult with legal counsel"],
            key_provisions=[],
        )
