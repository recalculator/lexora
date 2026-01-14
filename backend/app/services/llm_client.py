"""LLM client for OpenAI-compatible APIs."""
import json
import os
import time
from typing import Dict, List, Optional, Any
from openai import OpenAI
from pydantic import BaseModel, ValidationError
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger()

# Global client
_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    """Get OpenAI-compatible client."""
    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set")
        
        _client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_api_base,
        )
    return _client


def call_llm_with_schema(
    prompt: str,
    schema: BaseModel,
    model: str = None,
    temperature: float = 0.3,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> BaseModel:
    """
    Call LLM with structured output schema validation.
    
    Args:
        prompt: Prompt text
        schema: Pydantic model for output validation
        model: Model name (defaults to OPENAI_MODEL env var or "gpt-4o-mini")
        temperature: Sampling temperature
        max_retries: Maximum retry attempts
        retry_delay: Delay between retries (seconds)
        
    Returns:
        Validated Pydantic model instance
    """
    # Get model from env or use default
    if model is None:
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    client = get_client()
    
    # Convert Pydantic schema to JSON schema
    json_schema = schema.model_json_schema()
    
    # Add instruction for structured output
    enhanced_prompt = f"""{prompt}

IMPORTANT: You must respond with valid JSON that matches the following schema:
{json.dumps(json_schema, indent=2)}

Respond ONLY with valid JSON, no additional text or markdown formatting."""
    
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a legal contract analysis assistant. Always respond with valid JSON."},
                    {"role": "user", "content": enhanced_prompt}
                ],
                temperature=temperature,
                response_format={"type": "json_object"} if "json" in model.lower() else None,
            )
            
            content = response.choices[0].message.content
            logger.info("LLM response received", attempt=attempt + 1, content_length=len(content))
            
            # Try to parse JSON
            try:
                # Remove markdown code blocks if present
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                
                json_data = json.loads(content)
            except json.JSONDecodeError as e:
                logger.warning("Failed to parse JSON response", attempt=attempt + 1, error=str(e), content_preview=content[:200])
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                raise ValueError(f"Invalid JSON response: {str(e)}")
            
            # Validate with Pydantic
            try:
                validated = schema.model_validate(json_data)
                logger.info("Successfully validated LLM response", attempt=attempt + 1)
                return validated
            except ValidationError as e:
                logger.warning("Validation failed", attempt=attempt + 1, errors=str(e))
                if attempt < max_retries - 1:
                    # Add error feedback to prompt
                    enhanced_prompt = f"""{prompt}

Previous attempt failed validation. Errors: {str(e)}

IMPORTANT: You must respond with valid JSON that matches the following schema:
{json.dumps(json_schema, indent=2)}"""
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                raise ValueError(f"Validation failed: {str(e)}")
                
        except Exception as e:
            logger.error("LLM call failed", attempt=attempt + 1, error=str(e))
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))
                continue
            raise
    
    raise ValueError("Max retries exceeded")


def log_prompt(document_id: Optional[int], kind: str, prompt: str, response: str):
    """Log prompt and response to database (if enabled)."""
    if not settings.enable_prompt_logging:
        return
    
    try:
        from app.db.session import SessionLocal
        from app.db.models import PromptLog
        from datetime import datetime
        
        db = SessionLocal()
        try:
            prompt_log = PromptLog(
                document_id=document_id,
                kind=kind,
                prompt=prompt,
                response=response,
                created_at=datetime.utcnow(),
            )
            db.add(prompt_log)
            db.commit()
            logger.debug("Logged prompt to database", kind=kind, document_id=document_id)
        except Exception as e:
            logger.warning("Failed to log prompt to database", error=str(e), kind=kind)
            db.rollback()
        finally:
            db.close()
    except ImportError:
        # Database not available (e.g., in standalone script)
        logger.debug("Database not available for prompt logging", kind=kind)
    except Exception as e:
        logger.warning("Failed to log prompt", error=str(e), kind=kind)
