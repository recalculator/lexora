"""Train sklearn-based clause classifier using sentence-transformers."""
import json
import joblib
from pathlib import Path
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score, classification_report, confusion_matrix
from sentence_transformers import SentenceTransformer
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Clause types (must match backend)
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

# Risk weights (must match backend HIGH_RISK_TYPES)
RISK_WEIGHTS = {
    "Termination": 0.8,
    "Indemnification": 0.9,
    "Liability Cap": 0.7,
    "Confidentiality": 0.5,
    "Insurance": 0.6,
    "Intellectual Property": 0.7,
    "Assignment": 0.5,
    "Governing Law": 0.4,
}


def load_cuad_data(data_path="data/cuad/train.jsonl"):
    """Load CUAD dataset if available."""
    data_path = Path(data_path)
    if not data_path.exists():
        logger.warning(f"CUAD data not found at {data_path}")
        logger.info("To use real data, download CUAD dataset and place at data/cuad/train.jsonl")
        logger.info("For now, creating synthetic training data...")
        return create_synthetic_data()
    
    texts = []
    labels = []
    risk_scores = []
    
    with open(data_path, "r") as f:
        for line in f:
            item = json.loads(line)
            texts.append(item["text"])
            # Assume labels are binary array for 8 types
            if "labels" in item:
                labels.append(item["labels"])
            else:
                # Create dummy label based on text
                label_vec = [0] * len(CLAUSE_TYPES)
                for idx, clause_type in enumerate(CLAUSE_TYPES):
                    if clause_type.lower() in item["text"].lower():
                        label_vec[idx] = 1
                labels.append(label_vec)
            
            # Risk score from data or compute from labels
            if "risk_score" in item:
                risk_scores.append(item["risk_score"] / 100.0)
            else:
                # Compute from labels
                risk = 0.0
                for idx, clause_type in enumerate(CLAUSE_TYPES):
                    if label_vec[idx] == 1:
                        risk += RISK_WEIGHTS[clause_type]
                risk_scores.append(min(risk / len(CLAUSE_TYPES), 1.0))
    
    logger.info(f"Loaded {len(texts)} examples from CUAD")
    return texts, labels, risk_scores


def create_synthetic_data():
    """Create synthetic training data for MVP."""
    logger.info("Creating synthetic training data...")
    
    # Curated examples for each clause type
    examples = {
        "Termination": [
            "This agreement may be terminated by either party with thirty (30) days written notice.",
            "Either party may terminate this agreement at any time without cause.",
            "Termination of this agreement shall be effective immediately upon written notice.",
            "This agreement shall terminate upon expiration of the initial term unless renewed.",
            "Termination for convenience is permitted with 90 days advance notice.",
        ],
        "Indemnification": [
            "Party A agrees to indemnify and hold harmless Party B from any claims arising from Party A's breach.",
            "Each party shall indemnify the other against third-party claims related to intellectual property infringement.",
            "The indemnifying party shall defend and indemnify the indemnified party from all losses.",
            "Indemnification obligations shall survive termination of this agreement.",
            "Customer agrees to indemnify Provider from claims arising from Customer Data.",
        ],
        "Liability Cap": [
            "The maximum liability of either party shall not exceed the total fees paid in the twelve months preceding the claim.",
            "Liability is capped at $100,000 regardless of the nature of the claim.",
            "Neither party's liability shall exceed the amount paid under this agreement.",
            "Total liability is limited to direct damages only, excluding indirect or consequential damages.",
            "Liability cap does not apply to breaches of confidentiality or indemnification obligations.",
        ],
        "Confidentiality": [
            "Both parties agree to keep all information confidential and not disclose to third parties.",
            "Confidential information includes all proprietary data, trade secrets, and business plans.",
            "The confidentiality obligations shall survive termination for a period of five years.",
            "Receiving party shall use confidential information solely for the purposes of this agreement.",
            "No party shall disclose confidential information without prior written consent.",
        ],
        "Insurance": [
            "Provider shall maintain general liability insurance of at least $1,000,000.",
            "Each party agrees to maintain adequate insurance coverage for the duration of this agreement.",
            "Insurance policies must name the other party as additional insured.",
            "Proof of insurance must be provided within thirty days of agreement execution.",
            "Insurance coverage shall not be less than the amounts specified in this section.",
        ],
        "Intellectual Property": [
            "All intellectual property rights shall remain with the original creator.",
            "Customer retains all rights to Customer Data and Customer intellectual property.",
            "Provider grants Customer a limited license to use the Services during the term.",
            "Any improvements or modifications to the Services shall be owned by Provider.",
            "Intellectual property disputes shall be resolved through binding arbitration.",
        ],
        "Assignment": [
            "Neither party may assign this agreement without the prior written consent of the other party.",
            "This agreement may be assigned in connection with a merger or acquisition.",
            "Assignment without consent shall be void and of no effect.",
            "Rights and obligations under this agreement are non-transferable.",
            "Assignment to an affiliate is permitted with notice to the other party.",
        ],
        "Governing Law": [
            "This agreement shall be governed by the laws of the State of California.",
            "Any disputes shall be resolved in the courts of New York County, New York.",
            "This agreement is subject to the laws of England and Wales.",
            "Governing law and jurisdiction clauses are binding and enforceable.",
            "Choice of law does not affect the enforceability of arbitration clauses.",
        ],
    }
    
    texts = []
    labels = []
    risk_scores = []
    
    # Create multi-label examples
    for clause_type, examples_list in examples.items():
        for text in examples_list:
            texts.append(text)
            label_vec = [0] * len(CLAUSE_TYPES)
            idx = CLAUSE_TYPES.index(clause_type)
            label_vec[idx] = 1
            labels.append(label_vec)
            risk_scores.append(RISK_WEIGHTS[clause_type])
    
    # Add some multi-label examples (clauses that could be multiple types)
    multi_label_examples = [
        ("Termination and Indemnification", "Termination", "Indemnification",
         "This agreement may be terminated, and upon termination, Party A shall indemnify Party B."),
        ("Confidentiality and IP", "Confidentiality", "Intellectual Property",
         "All confidential information and intellectual property shall remain proprietary."),
    ]
    
    for name, type1, type2, text in multi_label_examples:
        texts.append(text)
        label_vec = [0] * len(CLAUSE_TYPES)
        label_vec[CLAUSE_TYPES.index(type1)] = 1
        label_vec[CLAUSE_TYPES.index(type2)] = 1
        labels.append(label_vec)
        risk_scores.append((RISK_WEIGHTS[type1] + RISK_WEIGHTS[type2]) / 2)
    
    # Repeat examples to get more training data
    texts = texts * 10
    labels = labels * 10
    risk_scores = risk_scores * 10
    
    logger.info(f"Created {len(texts)} synthetic training examples")
    return texts, labels, risk_scores


def train_classifier():
    """Train sklearn-based clause classifier."""
    logger.info("Starting sklearn classifier training...")
    
    # Load data
    texts, labels, risk_scores = load_cuad_data()
    
    # Load sentence transformer
    logger.info("Loading sentence transformer model...")
    model_name = "sentence-transformers/all-MiniLM-L6-v2"
    encoder = SentenceTransformer(model_name)
    
    # Generate embeddings
    logger.info(f"Generating embeddings for {len(texts)} texts...")
    embeddings = encoder.encode(texts, show_progress_bar=True, batch_size=32)
    logger.info(f"Embeddings shape: {embeddings.shape}")
    
    # Convert labels to numpy array
    labels_array = np.array(labels)
    
    # Train/test split - save indices for consistent evaluation
    # Create model dir first so we can save test indices
    model_dir = Path("models/sklearn")
    model_dir.mkdir(parents=True, exist_ok=True)
    
    train_indices, test_indices = train_test_split(
        np.arange(len(embeddings)), test_size=0.2, random_state=42
    )
    
    X_train = embeddings[train_indices]
    X_test = embeddings[test_indices]
    y_train = labels_array[train_indices]
    y_test = labels_array[test_indices]
    risk_train = np.array(risk_scores)[train_indices]
    risk_test = np.array(risk_scores)[test_indices]
    
    logger.info(f"Train set: {len(X_train)}, Test set: {len(X_test)}")
    
    # Save test set indices for evaluation script (held-out set)
    test_indices_path = model_dir / "test_indices.json"
    with open(test_indices_path, "w") as f:
        json.dump({"test_indices": test_indices.tolist(), "random_state": 42, "test_size": 0.2}, f, indent=2)
    logger.info(f"Saved test set indices to {test_indices_path} (held-out for evaluation)")
    
    # Train one-vs-rest logistic regression for each clause type
    classifiers = []
    for idx, clause_type in enumerate(CLAUSE_TYPES):
        logger.info(f"Training classifier for {clause_type}...")
        y_binary = y_train[:, idx]
        
        # Skip if no positive examples
        if np.sum(y_binary) == 0:
            logger.warning(f"No positive examples for {clause_type}, using dummy classifier")
            clf = LogisticRegression(random_state=42, max_iter=1000)
            clf.fit(X_train, np.zeros(len(X_train)))  # Dummy fit
        else:
            clf = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
            clf.fit(X_train, y_binary)
        
        # Calibrate probabilities
        calibrated_clf = CalibratedClassifierCV(clf, method='isotonic', cv=3)
        calibrated_clf.fit(X_train, y_binary)
        classifiers.append(calibrated_clf)
    
    # Evaluate
    logger.info("Evaluating classifiers...")
    y_pred_proba = np.zeros((len(X_test), len(CLAUSE_TYPES)))
    for idx, clf in enumerate(classifiers):
        y_pred_proba[:, idx] = clf.predict_proba(X_test)[:, 1]
    
    # Threshold at 0.5 for binary predictions
    y_pred = (y_pred_proba >= 0.5).astype(int)
    
    # Per-label F1
    f1_scores = f1_score(y_test, y_pred, average=None, zero_division=0)
    logger.info("Per-label F1 scores:")
    for clause_type, f1 in zip(CLAUSE_TYPES, f1_scores):
        logger.info(f"  {clause_type}: {f1:.3f}")
    
    macro_f1 = f1_score(y_test, y_pred, average='macro', zero_division=0)
    logger.info(f"Macro F1: {macro_f1:.3f}")
    
    # Save model artifacts (model_dir already created above)
    # Save classifier ensemble
    joblib.dump(classifiers, model_dir / "classifiers.joblib")
    logger.info(f"Saved classifiers to {model_dir / 'classifiers.joblib'}")
    
    # Save encoder (we'll need to load it in inference)
    encoder.save(str(model_dir / "encoder"))
    logger.info(f"Saved encoder to {model_dir / 'encoder'}")
    
    # Save label map
    label_map = {i: clause_type for i, clause_type in enumerate(CLAUSE_TYPES)}
    with open(model_dir / "label_map.json", "w") as f:
        json.dump(label_map, f, indent=2)
    logger.info(f"Saved label_map to {model_dir / 'label_map.json'}")
    
    # Save risk weights
    with open(model_dir / "risk_weights.json", "w") as f:
        json.dump(RISK_WEIGHTS, f, indent=2)
    logger.info(f"Saved risk_weights to {model_dir / 'risk_weights.json'}")
    
    # Save metadata
    metadata = {
        "model_type": "sklearn",
        "encoder": model_name,
        "num_classes": len(CLAUSE_TYPES),
        "classes": CLAUSE_TYPES,
        "macro_f1": float(macro_f1),
        "per_label_f1": {clause_type: float(f1) for clause_type, f1 in zip(CLAUSE_TYPES, f1_scores)},
    }
    with open(model_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"Saved metadata to {model_dir / 'metadata.json'}")
    
    logger.info("Training complete!")
    return classifiers, encoder, label_map, RISK_WEIGHTS


if __name__ == "__main__":
    train_classifier()
