"""Upload fine-tuning dataset to OpenAI."""
import os
import sys
import json
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

def upload_dataset(file_path: str = "ml/finetune_explain.jsonl"):
    """Upload JSONL file to OpenAI for fine-tuning."""
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        print(f"ERROR: File not found: {file_path}")
        return None
    
    # Check file size and format
    file_size = file_path_obj.stat().st_size
    print(f"File size: {file_size / 1024:.2f} KB")
    
    # Validate JSONL format
    with open(file_path_obj, "r") as f:
        lines = f.readlines()
        print(f"Number of examples: {len(lines)}")
        
        # Validate first few lines
        for i, line in enumerate(lines[:3]):
            try:
                data = json.loads(line)
                if "messages" not in data:
                    print(f"ERROR: Line {i+1} missing 'messages' key")
                    return None
            except json.JSONDecodeError as e:
                print(f"ERROR: Invalid JSON on line {i+1}: {e}")
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
    
    # Upload file
    print(f"Uploading {file_path} to OpenAI...")
    try:
        with open(file_path_obj, "rb") as f:
            file = client.files.create(
                file=f,
                purpose="fine-tune"
            )
        
        print(f"✓ File uploaded successfully!")
        print(f"  File ID: {file.id}")
        print(f"  File size: {file.bytes} bytes")
        print(f"  Status: {file.status}")
        
        # Save file ID for reference
        file_id_path = Path("ml/finetune_file_id.txt")
        with open(file_id_path, "w") as f:
            f.write(file.id)
        print(f"  File ID saved to {file_id_path}")
        
        return file.id
    except Exception as e:
        print(f"ERROR: Upload failed: {e}")
        return None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="ml/finetune_explain.jsonl", help="Path to JSONL file")
    args = parser.parse_args()
    
    upload_dataset(args.file)
