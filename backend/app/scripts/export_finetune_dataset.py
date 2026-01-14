"""Export prompt logs to OpenAI fine-tuning format."""
import json
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models import PromptLog
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger()


def export_finetune_dataset(output_path: str = "ml/finetune_explain.jsonl"):
    """Export explain endpoint prompts/responses to OpenAI fine-tuning format."""
    # Connect to database
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        # Get all explain-related prompt logs
        logs = db.query(PromptLog).filter(PromptLog.kind == "explain").all()
        
        if not logs:
            logger.warning("No explain prompt logs found in database")
            logger.info("Run the explain endpoint on some clauses to generate logs, or use generate_synthetic_explain_dataset.py")
            return []
        
        logger.info(f"Found {len(logs)} explain prompt logs")
        
        # Convert to OpenAI format
        examples = []
        for log in logs:
            try:
                # Parse prompt and response
                prompt_data = json.loads(log.prompt) if isinstance(log.prompt, str) else log.prompt
                response_data = json.loads(log.response) if isinstance(log.response, str) else log.response
                
                # Build messages
                messages = [
                    {
                        "role": "system",
                        "content": "You are a legal contract analysis expert. Always respond with valid JSON matching the schema."
                    },
                    {
                        "role": "user",
                        "content": prompt_data.get("prompt", log.prompt) if isinstance(prompt_data, dict) else log.prompt
                    },
                    {
                        "role": "assistant",
                        "content": json.dumps(response_data) if isinstance(response_data, dict) else log.response
                    }
                ]
                
                examples.append({"messages": messages})
            except Exception as e:
                logger.warning(f"Failed to process log {log.id}", error=str(e))
                continue
        
        # Save to JSONL
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path_obj, "w") as f:
            for example in examples:
                f.write(json.dumps(example) + "\n")
        
        logger.info(f"Exported {len(examples)} examples to {output_path}")
        return examples
        
    finally:
        db.close()


if __name__ == "__main__":
    export_finetune_dataset()
