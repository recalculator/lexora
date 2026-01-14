"""Train ClauseRiskNet model."""
import torch
import torch.nn as nn
from transformers import DistilBertForSequenceClassification, DistilBertTokenizer, Trainer, TrainingArguments
from datasets import load_dataset
import json
from pathlib import Path
import numpy as np
from sklearn.metrics import f1_score, accuracy_score
import os

# Clause types
CLAUSE_TYPES = [
    "Termination",
    "Indemnification",
    "Liability Cap",
    "Confidentiality",
    "Insurance",
    "Intellectual Property",
    "Assignment",
    "Governing Law",
]

NUM_LABELS = len(CLAUSE_TYPES)


class ClauseRiskNet(nn.Module):
    """ClauseRiskNet model with clause classification and risk scoring."""
    
    def __init__(self, num_labels=NUM_LABELS):
        super().__init__()
        self.backbone = DistilBertForSequenceClassification.from_pretrained(
            "distilbert-base-uncased",
            num_labels=num_labels,
            problem_type="multi_label_classification",
        )
        # Risk head: takes pooled output and predicts risk score
        hidden_size = self.backbone.config.dim
        self.risk_head = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_size // 2, 1),
            nn.Sigmoid(),  # Output 0-1, scale to 0-100 later
        )
    
    def forward(self, input_ids, attention_mask, labels=None):
        outputs = self.backbone(
            input_ids=input_ids,
            attention_mask=attention_mask,
            labels=labels,
        )
        
        # Get pooled output for risk head
        pooled_output = outputs.logits.mean(dim=1)  # Simple pooling
        risk_score = self.risk_head(pooled_output)
        
        return {
            "logits": outputs.logits,
            "risk_score": risk_score,
            "loss": outputs.loss if labels is not None else None,
        }


def load_data(data_path="data/cuad/train.jsonl"):
    """Load training data."""
    data_path = Path(data_path)
    
    if not data_path.exists():
        print(f"Data file not found: {data_path}")
        print("Using dummy data for MVP...")
        return create_dummy_dataset()
    
    texts = []
    labels = []
    risk_scores = []
    
    with open(data_path, "r") as f:
        for line in f:
            item = json.loads(line)
            texts.append(item["text"])
            labels.append(item.get("labels", [0] * NUM_LABELS))
            risk_scores.append(item.get("risk_score", 50) / 100.0)  # Normalize to 0-1
    
    return texts, labels, risk_scores


def create_dummy_dataset():
    """Create dummy dataset for MVP."""
    print("Creating dummy dataset for MVP...")
    
    texts = [
        "This agreement may be terminated by either party with 30 days written notice.",
        "Party A agrees to indemnify and hold harmless Party B from any claims.",
        "The maximum liability of either party shall not exceed $100,000.",
        "Both parties agree to keep all information confidential.",
        "All intellectual property rights shall remain with the original creator.",
        "This agreement shall be governed by the laws of California.",
    ] * 50  # Repeat 50 times
    
    labels = [
        [1, 0, 0, 0, 0, 0, 0, 0],  # Termination
        [0, 1, 0, 0, 0, 0, 0, 0],  # Indemnification
        [0, 0, 1, 0, 0, 0, 0, 0],  # Liability Cap
        [0, 0, 0, 1, 0, 0, 0, 0],  # Confidentiality
        [0, 0, 0, 0, 0, 1, 0, 0],  # IP
        [0, 0, 0, 0, 0, 0, 0, 1],  # Governing Law
    ] * 50
    
    risk_scores = [0.8, 0.9, 0.7, 0.5, 0.7, 0.4] * 50
    
    return texts, labels, risk_scores


def train():
    """Train the model."""
    print("Starting training...")
    
    # Load data
    texts, labels, risk_scores = load_data()
    
    # Tokenize
    tokenizer = DistilBertTokenizer.from_pretrained("distilbert-base-uncased")
    
    print(f"Loaded {len(texts)} training examples")
    
    # Simple train/val split
    split_idx = int(0.9 * len(texts))
    train_texts = texts[:split_idx]
    train_labels = labels[:split_idx]
    train_risks = risk_scores[:split_idx]
    
    val_texts = texts[split_idx:]
    val_labels = labels[split_idx:]
    val_risks = risk_scores[split_idx:]
    
    # Tokenize
    train_encodings = tokenizer(
        train_texts,
        truncation=True,
        padding=True,
        max_length=512,
        return_tensors="pt",
    )
    
    val_encodings = tokenizer(
        val_texts,
        truncation=True,
        padding=True,
        max_length=512,
        return_tensors="pt",
    )
    
    # Create dataset
    class ClauseDataset(torch.utils.data.Dataset):
        def __init__(self, encodings, labels, risk_scores):
            self.encodings = encodings
            self.labels = torch.tensor(labels, dtype=torch.float)
            self.risk_scores = torch.tensor(risk_scores, dtype=torch.float).unsqueeze(1)
        
        def __getitem__(self, idx):
            return {
                "input_ids": self.encodings["input_ids"][idx],
                "attention_mask": self.encodings["attention_mask"][idx],
                "labels": self.labels[idx],
                "risk_score": self.risk_scores[idx],
            }
        
        def __len__(self):
            return len(self.labels)
    
    train_dataset = ClauseDataset(train_encodings, train_labels, train_risks)
    val_dataset = ClauseDataset(val_encodings, val_labels, val_risks)
    
    # Initialize model
    model = ClauseRiskNet(num_labels=NUM_LABELS)
    
    # Training arguments
    training_args = TrainingArguments(
        output_dir="./models/checkpoints",
        num_train_epochs=3,
        per_device_train_batch_size=8,
        per_device_eval_batch_size=8,
        warmup_steps=100,
        weight_decay=0.01,
        logging_dir="./logs",
        logging_steps=10,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
    )
    
    # Custom trainer with risk loss
    class CustomTrainer(Trainer):
        def compute_loss(self, model, inputs, return_outputs=False):
            labels = inputs.pop("labels")
            risk_targets = inputs.pop("risk_score")
            
            outputs = model(**inputs)
            logits = outputs["logits"]
            risk_preds = outputs["risk_score"]
            
            # Classification loss (BCE with logits)
            bce_loss = nn.BCEWithLogitsLoss()
            class_loss = bce_loss(logits, labels)
            
            # Risk loss (MSE)
            mse_loss = nn.MSELoss()
            risk_loss = mse_loss(risk_preds, risk_targets)
            
            # Combined loss
            total_loss = class_loss + 0.1 * risk_loss
            
            return (total_loss, outputs) if return_outputs else total_loss
    
    trainer = CustomTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
    )
    
    # Train
    print("Training model...")
    trainer.train()
    
    # Save model
    model_dir = Path("models/checkpoints")
    model_dir.mkdir(parents=True, exist_ok=True)
    
    trainer.save_model(str(model_dir / "best"))
    tokenizer.save_pretrained(str(model_dir / "best"))
    
    print(f"Model saved to {model_dir / 'best'}")
    
    # Evaluate
    print("Evaluating...")
    predictions = trainer.predict(val_dataset)
    
    # Calculate metrics
    pred_labels = (torch.sigmoid(torch.tensor(predictions.predictions[0])) > 0.5).numpy()
    true_labels = np.array(val_labels)
    
    f1 = f1_score(true_labels, pred_labels, average="macro")
    acc = accuracy_score(true_labels, pred_labels)
    
    print(f"Validation F1: {f1:.4f}")
    print(f"Validation Accuracy: {acc:.4f}")
    
    return model, tokenizer


if __name__ == "__main__":
    # Set device
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    train()
