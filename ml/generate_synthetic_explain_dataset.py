"""Generate synthetic explain dataset for fine-tuning."""
import json
import os
import sys
from pathlib import Path
from openai import OpenAI

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

try:
    from app.core.config import settings
except ImportError:
    # Fallback if app not available
    class Settings:
        openai_api_key = os.getenv("OPENAI_API_KEY", "")
        openai_api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    settings = Settings()

# Sample clauses with gold explanations
SAMPLE_CLAUSES = [
    {
        "clause_text": "This agreement may be terminated by either party with thirty (30) days written notice.",
        "clause_type": "Termination",
        "risk_score": 80.0,
        "confidence": 0.95,
        "gold_explanation": {
            "explanation": "This clause allows termination for convenience with minimal notice, which creates significant business risk. The 30-day notice period is relatively short and provides little protection for the receiving party.",
            "risk_drivers": [
                "Termination for convenience without cause",
                "Short 30-day notice period",
                "No cure period or breach requirement"
            ],
            "suggested_negotiation_moves": [
                "Request longer notice period (60-90 days)",
                "Add requirement for material breach before termination",
                "Include cure period for non-material breaches"
            ],
            "quoted_spans": [
                {
                    "quote": "terminated by either party with thirty (30) days written notice",
                    "reason": "This phrase allows unilateral termination with minimal notice"
                }
            ]
        }
    },
    {
        "clause_text": "Party A agrees to indemnify and hold harmless Party B from any claims arising from Party A's breach of this agreement.",
        "clause_type": "Indemnification",
        "risk_score": 90.0,
        "confidence": 0.98,
        "gold_explanation": {
            "explanation": "This indemnification clause is one-sided and places all liability on Party A. It requires Party A to defend Party B from claims arising from Party A's own breach, which is standard, but the broad language 'any claims' could extend beyond reasonable scope.",
            "risk_drivers": [
                "One-sided indemnification obligation",
                "Broad 'any claims' language",
                "No cap on indemnification liability"
            ],
            "suggested_negotiation_moves": [
                "Request mutual indemnification",
                "Limit indemnification to third-party claims only",
                "Add liability cap for indemnification obligations",
                "Exclude indirect and consequential damages"
            ],
            "quoted_spans": [
                {
                    "quote": "indemnify and hold harmless Party B from any claims",
                    "reason": "This creates unlimited indemnification liability"
                },
                {
                    "quote": "arising from Party A's breach",
                    "reason": "One-sided obligation that only protects Party B"
                }
            ]
        }
    },
    {
        "clause_text": "The maximum liability of either party shall not exceed the total fees paid in the twelve months preceding the claim.",
        "clause_type": "Liability Cap",
        "risk_score": 70.0,
        "confidence": 0.92,
        "gold_explanation": {
            "explanation": "This liability cap is based on fees paid, which may be insufficient for high-value contracts. The 12-month lookback period limits recovery to recent payments, potentially excluding significant historical value.",
            "risk_drivers": [
                "Liability cap tied to fees (may be low)",
                "12-month lookback period limits recovery",
                "No exception for gross negligence or willful misconduct"
            ],
            "suggested_negotiation_moves": [
                "Request fixed dollar cap (e.g., $1M) instead of fee-based",
                "Extend lookback period to contract lifetime",
                "Add exceptions for indemnification and confidentiality breaches"
            ],
            "quoted_spans": [
                {
                    "quote": "maximum liability of either party shall not exceed",
                    "reason": "This caps all liability, including direct damages"
                },
                {
                    "quote": "total fees paid in the twelve months preceding",
                    "reason": "Fee-based cap may be insufficient for high-value contracts"
                }
            ]
        }
    },
]


def generate_with_teacher_model(clause_data: dict, teacher_model: str = "gpt-4o") -> dict:
    """Generate explanation using teacher model (for distillation)."""
    client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base,
    )
    
    prompt = f"""You are a legal contract analysis expert. Explain why this clause was flagged as high-risk.

DOCUMENT: Sample Contract
CLAUSE TYPE: {clause_data['clause_type']}
RISK SCORE: {clause_data['risk_score']:.1f}/100
CONFIDENCE: {clause_data['confidence']:.1%}

CLAUSE TEXT:
{clause_data['clause_text']}

TASK:
Provide a comprehensive explanation that:
1. Explains why this clause is flagged (explanation field)
2. Lists specific risk drivers (risk_drivers array)
3. Suggests negotiation moves (suggested_negotiation_moves array)
4. Quotes exact snippets from the clause text with reasons (quoted_spans array)

GROUNDING RULES:
- Only use information from the clause text provided above
- Do not reference external law or regulations
- Must quote exact snippets from the clause text in quoted_spans
- Each quoted_spans entry must have an exact quote from the clause and a reason

Respond with valid JSON matching this schema:
{{
  "explanation": "string",
  "risk_drivers": ["string"],
  "suggested_negotiation_moves": ["string"],
  "quoted_spans": [{{"quote": "string", "reason": "string"}}]
}}"""
    
    try:
        response = client.chat.completions.create(
            model=teacher_model,
            messages=[
                {"role": "system", "content": "You are a legal contract analysis expert. Always respond with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        
        content = response.choices[0].message.content
        # Remove markdown if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        return json.loads(content)
    except Exception as e:
        print(f"Error generating with teacher model: {e}")
        return clause_data.get("gold_explanation", {})


def generate_dataset(output_path: str = "ml/finetune_explain.jsonl", use_teacher: bool = False, teacher_model: str = "gpt-4o"):
    """Generate synthetic explain dataset."""
    examples = []
    
    # Use gold explanations or generate with teacher model
    for clause_data in SAMPLE_CLAUSES:
        if use_teacher:
            explanation = generate_with_teacher_model(clause_data, teacher_model)
        else:
            explanation = clause_data["gold_explanation"]
        
        # Build prompt (same format as explain.py)
        prompt = f"""You are a legal contract analysis expert. Explain why this clause was flagged as high-risk.

DOCUMENT: Sample Contract
CLAUSE TYPE: {clause_data['clause_type']}
RISK SCORE: {clause_data['risk_score']:.1f}/100
CONFIDENCE: {clause_data['confidence']:.1%}

CLAUSE TEXT:
{clause_data['clause_text']}

TASK:
Provide a comprehensive explanation that:
1. Explains why this clause is flagged (explanation field)
2. Lists specific risk drivers (risk_drivers array)
3. Suggests negotiation moves (suggested_negotiation_moves array)
4. Quotes exact snippets from the clause text with reasons (quoted_spans array)

GROUNDING RULES:
- Only use information from the clause text provided above
- Do not reference external law or regulations
- Must quote exact snippets from the clause text in quoted_spans
- Each quoted_spans entry must have an exact quote from the clause and a reason

RESPOND WITH VALID JSON matching the schema."""
        
        # Build messages
        messages = [
            {
                "role": "system",
                "content": "You are a legal contract analysis expert. Always respond with valid JSON matching the schema."
            },
            {
                "role": "user",
                "content": prompt
            },
            {
                "role": "assistant",
                "content": json.dumps(explanation)
            }
        ]
        
        examples.append({"messages": messages})
    
    # Repeat examples to get more training data
    examples = examples * 20  # 3 examples * 20 = 60 examples
    
    # Save to JSONL
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path_obj, "w") as f:
        for example in examples:
            f.write(json.dumps(example) + "\n")
    
    print(f"Generated {len(examples)} examples to {output_path}")
    return examples


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--use-teacher", action="store_true", help="Use teacher model (GPT-4o) to generate examples")
    parser.add_argument("--teacher-model", default="gpt-4o", help="Teacher model name")
    parser.add_argument("--output", default="ml/finetune_explain.jsonl", help="Output path")
    args = parser.parse_args()
    
    generate_dataset(args.output, args.use_teacher, args.teacher_model)
