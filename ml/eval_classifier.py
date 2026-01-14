"""Evaluate sklearn classifier on test set."""
import json
import joblib
from pathlib import Path
import numpy as np
from sklearn.metrics import f1_score, classification_report, confusion_matrix
from sentence_transformers import SentenceTransformer
from train_clause_classifier_sklearn import load_cuad_data, create_synthetic_data, CLAUSE_TYPES
from sklearn.model_selection import train_test_split

def evaluate():
    """Evaluate classifier on held-out test set."""
    print("Loading data...")
    try:
        texts, labels, risk_scores = load_cuad_data()
    except:
        texts, labels, risk_scores = create_synthetic_data()
    
    # Load model
    model_dir = Path("models/sklearn")
    if not (model_dir / "classifiers.joblib").exists():
        print(f"ERROR: Model not found at {model_dir}")
        print("Run train_clause_classifier_sklearn.py first")
        return
    
    # Load test set indices (must match training split)
    test_indices_path = model_dir / "test_indices.json"
    if not test_indices_path.exists():
        print(f"WARNING: Test indices not found at {test_indices_path}")
        print("This means the model was trained before test set saving was implemented.")
        print("Creating new split (results may not match training evaluation)...")
        use_saved_split = False
    else:
        with open(test_indices_path, "r") as f:
            split_info = json.load(f)
        test_indices = np.array(split_info["test_indices"])
        use_saved_split = True
        print(f"Loaded test set indices: {len(test_indices)} examples (held-out from training)")
    
    print("Loading model...")
    classifiers = joblib.load(model_dir / "classifiers.joblib")
    encoder = SentenceTransformer(str(model_dir / "encoder"))
    
    # Generate embeddings for all data
    print("Generating embeddings...")
    embeddings = encoder.encode(texts, show_progress_bar=True, batch_size=32)
    labels_array = np.array(labels)
    
    # Use saved test set OR create new split
    if use_saved_split:
        # Only evaluate on held-out test set
        X_test = embeddings[test_indices]
        y_test = labels_array[test_indices]
        print(f"Evaluating on held-out test set: {len(X_test)} examples (never seen during training)")
    else:
        # Fallback: create new split (not ideal, but better than nothing)
        X_train, X_test, y_train, y_test, _, _ = train_test_split(
            embeddings, labels_array, risk_scores, test_size=0.2, random_state=42
        )
        print(f"WARNING: Using new split. Test set size: {len(X_test)}")
    
    print(f"Test set size: {len(X_test)}")
    
    # Predict
    print("Running predictions...")
    y_pred_proba = np.zeros((len(X_test), len(CLAUSE_TYPES)))
    for idx, clf in enumerate(classifiers):
        y_pred_proba[:, idx] = clf.predict_proba(X_test)[:, 1]
    
    y_pred = (y_pred_proba >= 0.5).astype(int)
    
    # Metrics
    print("\n" + "="*60)
    print("EVALUATION RESULTS")
    print("="*60)
    
    # Per-label F1
    f1_scores = f1_score(y_test, y_pred, average=None, zero_division=0)
    print("\nPer-label F1 scores:")
    for clause_type, f1 in zip(CLAUSE_TYPES, f1_scores):
        print(f"  {clause_type:25s}: {f1:.3f}")
    
    macro_f1 = f1_score(y_test, y_pred, average='macro', zero_division=0)
    micro_f1 = f1_score(y_test, y_pred, average='micro', zero_division=0)
    
    print(f"\nMacro F1: {macro_f1:.3f}")
    print(f"Micro F1: {micro_f1:.3f}")
    
    # Classification report
    print("\n" + "-"*60)
    print("Classification Report:")
    print("-"*60)
    print(classification_report(y_test, y_pred, target_names=CLAUSE_TYPES, zero_division=0))
    
    # Confusion matrix summary (for multi-label, show per-label)
    print("\n" + "-"*60)
    print("Per-label Confusion Matrix Summary:")
    print("-"*60)
    for idx, clause_type in enumerate(CLAUSE_TYPES):
        tn = np.sum((y_test[:, idx] == 0) & (y_pred[:, idx] == 0))
        fp = np.sum((y_test[:, idx] == 0) & (y_pred[:, idx] == 1))
        fn = np.sum((y_test[:, idx] == 1) & (y_pred[:, idx] == 0))
        tp = np.sum((y_test[:, idx] == 1) & (y_pred[:, idx] == 1))
        print(f"{clause_type:25s}: TP={tp:3d} FP={fp:3d} FN={fn:3d} TN={tn:3d}")
    
    # Save report
    report_path = Path("ml/REPORT.md")
    with open(report_path, "w") as f:
        f.write("# Classifier Evaluation Report\n\n")
        f.write(f"**Test Set Size:** {len(X_test)}\n\n")
        f.write("## Per-Label F1 Scores\n\n")
        for clause_type, f1 in zip(CLAUSE_TYPES, f1_scores):
            f.write(f"- {clause_type}: {f1:.3f}\n")
        f.write(f"\n**Macro F1:** {macro_f1:.3f}\n")
        f.write(f"**Micro F1:** {micro_f1:.3f}\n\n")
        f.write("## Classification Report\n\n")
        f.write("```\n")
        f.write(classification_report(y_test, y_pred, target_names=CLAUSE_TYPES, zero_division=0))
        f.write("```\n")
    
    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    evaluate()
