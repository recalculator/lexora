"""Create OpenAI fine-tuning job."""
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

def create_finetune_job(file_id: str = None, model: str = "gpt-4o-mini", suffix: str = "lexora-explain"):
    """Create OpenAI fine-tuning job."""
    # Get file ID
    if file_id is None:
        file_id_path = Path("ml/finetune_file_id.txt")
        if file_id_path.exists():
            with open(file_id_path, "r") as f:
                file_id = f.read().strip()
        else:
            print("ERROR: File ID not found. Run openai_upload.py first or provide --file-id")
            return None
    
    # Initialize client
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set")
        return None
    
    base_url = settings.openai_api_base or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )
    
    # Create fine-tuning job
    print(f"Creating fine-tuning job...")
    print(f"  Base model: {model}")
    print(f"  Training file: {file_id}")
    print(f"  Suffix: {suffix}")
    
    try:
        job = client.fine_tuning.jobs.create(
            training_file=file_id,
            model=model,
            suffix=suffix,
        )
        
        print(f"✓ Fine-tuning job created!")
        print(f"  Job ID: {job.id}")
        print(f"  Status: {job.status}")
        
        # Save job ID
        job_id_path = Path("ml/finetune_job_id.txt")
        with open(job_id_path, "w") as f:
            f.write(job.id)
        print(f"  Job ID saved to {job_id_path}")
        print(f"\nTo check job status, run: python ml/openai_check_job.py")
        
        return job.id
    except Exception as e:
        print(f"ERROR: Failed to create fine-tuning job: {e}")
        return None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--file-id", help="OpenAI file ID (or read from ml/finetune_file_id.txt)")
    parser.add_argument("--model", default="gpt-4o-mini", help="Base model to fine-tune")
    parser.add_argument("--suffix", default="lexora-explain", help="Suffix for fine-tuned model name")
    args = parser.parse_args()
    
    create_finetune_job(args.file_id, args.model, args.suffix)
