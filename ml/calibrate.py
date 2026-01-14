"""Calibrate model using temperature scaling."""
import torch
import torch.nn as nn
from transformers import DistilBertTokenizer
from pathlib import Path
import json
import numpy as np

from train_clause_risknet import ClauseRiskNet, NUM_LABELS, load_data, create_dummy_dataset


class TemperatureScaling(nn.Module):
    """Temperature scaling for calibration."""
    
    def __init__(self):
        super().__init__()
        self.temperature = nn.Parameter(torch.ones(1))
    
    def forward(self, logits):
        return logits / self.temperature


def calibrate(model_path="models/checkpoints/best", output_path="models/calibration.json"):
    """Calibrate model on validation set."""
    print("Calibrating model...")
    
    # Load model
    model = ClauseRiskNet(num_labels=NUM_LABELS)
    model.load_state_dict(torch.load(Path(model_path) / "pytorch_model.bin", map_location="cpu"))
    model.eval()
    
    tokenizer = DistilBertTokenizer.from_pretrained(model_path)
    
    # Load validation data
    texts, labels, _ = load_data()
    split_idx = int(0.9 * len(texts))
    val_texts = texts[split_idx:]
    val_labels = labels[split_idx:]
    
    # If no data, use dummy
    if not val_texts:
        _, val_labels, _ = create_dummy_dataset()
        val_texts = ["This is a test clause."] * len(val_labels)
    
    # Tokenize
    val_encodings = tokenizer(
        val_texts[:100],  # Use subset for calibration
        truncation=True,
        padding=True,
        max_length=512,
        return_tensors="pt",
    )
    
    # Get logits
    with torch.no_grad():
        outputs = model(
            input_ids=val_encodings["input_ids"],
            attention_mask=val_encodings["attention_mask"],
        )
        logits = outputs["logits"]
    
    # Convert labels to tensor
    val_labels_tensor = torch.tensor(val_labels[:100], dtype=torch.float)
    
    # Initialize temperature scaling
    temp_scaling = TemperatureScaling()
    optimizer = torch.optim.LBFGS([temp_scaling.temperature], lr=0.01, max_iter=50)
    
    # Calibrate
    def eval():
        optimizer.zero_grad()
        calibrated_logits = temp_scaling(logits)
        loss = nn.BCEWithLogitsLoss()(calibrated_logits, val_labels_tensor)
        loss.backward()
        return loss
    
    optimizer.step(eval)
    
    temperature = float(temp_scaling.temperature.item())
    print(f"Calibrated temperature: {temperature:.4f}")
    
    # Save calibration parameters
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path_obj, "w") as f:
        json.dump({"temperature": temperature}, f)
    
    print(f"Calibration parameters saved to {output_path}")
    
    return temperature


if __name__ == "__main__":
    calibrate()
