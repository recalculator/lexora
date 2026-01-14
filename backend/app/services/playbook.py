"""Negotiation playbook generation service."""
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from app.services.llm_client import call_llm_with_schema, log_prompt
from app.services.retrieval import create_retrieval
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
    citation: str = Field(description="Reference to contract section")


class NegotiationPlaybook(BaseModel):
    """Negotiation playbook output."""
    document_summary: str = Field(description="Brief summary of the contract")
    overall_risk_assessment: str = Field(description="Overall risk level: low, medium, high, critical")
    priority_clauses: List[ClauseRecommendation] = Field(description="List of priority clauses to negotiate")
    general_recommendations: List[str] = Field(description="General negotiation recommendations")
    key_provisions: List[str] = Field(description="Key provisions to highlight")


def generate_playbook(clauses: List[Dict[str, any]], document_text: str, document_id: Optional[int] = None) -> NegotiationPlaybook:
    """
    Generate negotiation playbook using LLM with RAG.
    
    Args:
        clauses: List of clause dictionaries with classification results
        document_text: Full document text
        
    Returns:
        NegotiationPlaybook instance
    """
    logger.info("Generating negotiation playbook", num_clauses=len(clauses))
    
    # Create retrieval index
    retrieval = create_retrieval(clauses)
    
    # Build context from high-risk clauses
    high_risk_clauses = [
        c for c in clauses
        if c.get("risk_score", 0) > 60
    ]
    
    context_parts = []
    for clause in high_risk_clauses[:10]:  # Top 10 high-risk clauses
        clause_text = clause.get("text", "")[:500]  # Truncate
        clause_type = clause.get("clause_type", "Unknown")
        risk_score = clause.get("risk_score", 0)
        context_parts.append(
            f"Clause {clause.get('idx', 0)} ({clause_type}, Risk: {risk_score:.1f}):\n{clause_text}\n"
        )
    
    context = "\n".join(context_parts)
    
    # Build prompt
    prompt = f"""You are a legal contract negotiation expert. Analyze the following contract clauses and generate a comprehensive negotiation playbook.

CONTRACT CONTEXT:
{context[:3000]}  # Truncate to avoid token limits

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
