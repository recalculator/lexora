"""Check OpenAI fine-tuning job status."""
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

def check_job(job_id: str = None):
    """Check fine-tuning job status."""
    # Get job ID
    if job_id is None:
        job_id_path = Path("ml/finetune_job_id.txt")
        if job_id_path.exists():
            with open(job_id_path, "r") as f:
                job_id = f.read().strip()
        else:
            print("ERROR: Job ID not found. Run openai_finetune.py first or provide --job-id")
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
    
    # Check job status
    try:
        job = client.fine_tuning.jobs.retrieve(job_id)
        
        print(f"Fine-tuning Job Status")
        print(f"=" * 60)
        print(f"Job ID: {job.id}")
        print(f"Status: {job.status}")
        print(f"Model: {job.model}")
        print(f"Created: {job.created_at}")
        
        if hasattr(job, "fine_tuned_model") and job.fine_tuned_model:
            print(f"Fine-tuned Model: {job.fine_tuned_model}")
            
            # Save model name
            model_path = Path("ml/finetune_model_name.txt")
            with open(model_path, "w") as f:
                f.write(job.fine_tuned_model)
            print(f"  Model name saved to {model_path}")
        
        if hasattr(job, "error") and job.error:
            print(f"Error: {job.error}")
        
        if hasattr(job, "trained_tokens") and job.trained_tokens:
            print(f"Trained Tokens: {job.trained_tokens}")
        
        # List events if available
        if job.status in ["running", "succeeded", "failed"]:
            try:
                events = client.fine_tuning.jobs.list_events(job_id, limit=10)
                if events.data:
                    print(f"\nRecent Events:")
                    for event in events.data:
                        print(f"  [{event.created_at}] {event.message}")
            except:
                pass
        
        return job
    except Exception as e:
        print(f"ERROR: Failed to retrieve job: {e}")
        return None


if __name__ == "__main__":
    import argparse
    import time
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", help="Fine-tuning job ID (or read from ml/finetune_job_id.txt)")
    parser.add_argument("--watch", action="store_true", help="Watch job status until completion")
    args = parser.parse_args()
    
    if args.watch:
        print("Watching job status (press Ctrl+C to stop)...")
        try:
            while True:
                job = check_job(args.job_id)
                if job and job.status in ["succeeded", "failed", "cancelled"]:
                    break
                time.sleep(30)  # Check every 30 seconds
        except KeyboardInterrupt:
            print("\nStopped watching")
    else:
        check_job(args.job_id)
