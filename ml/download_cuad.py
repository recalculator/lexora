"""Download CUAD dataset."""
import os
from datasets import load_dataset
from pathlib import Path

def download_cuad():
    """Download CUAD dataset from HuggingFace."""
    print("Downloading CUAD dataset...")
    
    try:
        # Load CUAD dataset from HuggingFace
        dataset = load_dataset("cuad", "full")
        
        print(f"Dataset downloaded successfully!")
        print(f"Train size: {len(dataset['train'])}")
        print(f"Test size: {len(dataset['test'])}")
        
        # Save to local directory
        output_dir = Path("data/cuad")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save train and test splits
        dataset['train'].to_json(str(output_dir / "train.jsonl"))
        dataset['test'].to_json(str(output_dir / "test.jsonl"))
        
        print(f"Dataset saved to {output_dir}")
        return dataset
        
    except Exception as e:
        print(f"Error downloading CUAD dataset: {e}")
        print("Falling back to creating a toy dataset...")
        
        # Create a toy dataset for MVP
        output_dir = Path("data/cuad")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create minimal toy dataset
        toy_data = {
            "train": [
                {
                    "text": "This agreement may be terminated by either party with 30 days written notice. Upon termination, all rights and obligations shall cease immediately.",
                    "labels": [1, 0, 0, 0, 0, 0, 0, 0],  # Termination
                    "risk_score": 80,
                },
                {
                    "text": "Party A agrees to indemnify and hold harmless Party B from any claims arising from Party A's breach of this agreement.",
                    "labels": [0, 1, 0, 0, 0, 0, 0, 0],  # Indemnification
                    "risk_score": 90,
                },
                {
                    "text": "The maximum liability of either party shall not exceed $100,000. This limitation does not apply to intentional misconduct.",
                    "labels": [0, 0, 1, 0, 0, 0, 0, 0],  # Liability Cap
                    "risk_score": 70,
                },
            ] * 10,  # Repeat 10 times for minimal dataset
        }
        
        import json
        with open(output_dir / "train.jsonl", "w") as f:
            for item in toy_data["train"]:
                f.write(json.dumps(item) + "\n")
        
        print(f"Toy dataset created at {output_dir / 'train.jsonl'}")
        return None


if __name__ == "__main__":
    download_cuad()
