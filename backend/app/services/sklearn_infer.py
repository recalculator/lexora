"""Sklearn-based clause classification inference service."""
import joblib
import json
import numpy as np
from pathlib import Path
from typing import Dict, Optional, List
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger()

# Lazy import to avoid crashing if sentence-transformers not installed
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None

# Clause types (must match training)
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


class SklearnInferenceService:
    """Sklearn-based inference service for clause classification."""
    
    def __init__(self, model_dir: Optional[str] = None):
        self.model_dir = Path(model_dir or settings.sklearn_model_dir)
        self.classifiers = None
        self.encoder = None
        self.label_map = None
        self.risk_weights = None
        self._load_model()
    
    def _load_model(self):
        """Load sklearn model artifacts."""
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            logger.warning("sentence-transformers not available, sklearn model cannot be loaded")
            return
        
        classifiers_path = self.model_dir / "classifiers.joblib"
        encoder_path = self.model_dir / "encoder"
        label_map_path = self.model_dir / "label_map.json"
        risk_weights_path = self.model_dir / "risk_weights.json"
        
        if not classifiers_path.exists():
            logger.warning("Sklearn model not found", model_dir=str(self.model_dir))
            return
        
        try:
            logger.info("Loading sklearn model artifacts...")
            self.classifiers = joblib.load(classifiers_path)
            self.encoder = SentenceTransformer(str(encoder_path))
            
            with open(label_map_path, "r") as f:
                self.label_map = json.load(f)
            
            with open(risk_weights_path, "r") as f:
                self.risk_weights = json.load(f)
            
            logger.info("Sklearn model loaded successfully", num_classifiers=len(self.classifiers))
        except Exception as e:
            logger.error("Failed to load sklearn model", error=str(e))
            self.classifiers = None
            self.encoder = None
    
    def classify_clause(self, text: str) -> Dict[str, any]:
        """
        Classify a clause and compute risk score.
        
        Args:
            text: Clause text
            
        Returns:
            Dictionary with keys: clause_type, risk_score, confidence, type_probs
        """
        if self.classifiers is None or self.encoder is None:
            raise ValueError("Sklearn model not loaded")
        
        # Generate embedding
        embedding = self.encoder.encode([text], show_progress_bar=False)
        
        # Predict probabilities for each clause type
        type_probs = np.zeros(len(CLAUSE_TYPES))
        for idx, clf in enumerate(self.classifiers):
            prob = clf.predict_proba(embedding)[0, 1]  # Probability of positive class
            type_probs[idx] = prob
        
        # Get predicted type (highest probability)
        predicted_idx = int(np.argmax(type_probs))
        predicted_type = CLAUSE_TYPES[predicted_idx] if predicted_idx < len(CLAUSE_TYPES) else "Other"
        confidence = float(type_probs[predicted_idx])
        
        # If confidence is low, set type to None
        if confidence < 0.3:
            predicted_type = None
        
        # Compute risk score: weighted sum of type probabilities
        risk_score = 0.0
        for idx, clause_type in enumerate(CLAUSE_TYPES):
            if clause_type in self.risk_weights:
                risk_score += type_probs[idx] * self.risk_weights[clause_type]
        
        # Normalize and scale to 0-100
        risk_score = min(risk_score / len(CLAUSE_TYPES) if CLAUSE_TYPES else 0, 1.0) * 100
        
        result = {
            "clause_type": predicted_type,
            "risk_score": float(risk_score),
            "confidence": float(confidence),
            "type_probs": {CLAUSE_TYPES[i]: float(type_probs[i]) for i in range(len(CLAUSE_TYPES))},
        }
        
        return result


# Global instance
_sklearn_service: Optional[SklearnInferenceService] = None


def get_sklearn_service() -> Optional[SklearnInferenceService]:
    """Get global sklearn inference service instance."""
    global _sklearn_service
    if _sklearn_service is None:
        try:
            _sklearn_service = SklearnInferenceService()
            if _sklearn_service.classifiers is None:
                _sklearn_service = None
        except Exception as e:
            logger.warning("Failed to initialize sklearn service", error=str(e))
            _sklearn_service = None
    return _sklearn_service


def is_sklearn_available() -> bool:
    """Check if sklearn model is available."""
    service = get_sklearn_service()
    return service is not None and service.classifiers is not None
