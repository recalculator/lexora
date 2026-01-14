"""ONNX inference service for ClauseRiskNet."""
import numpy as np
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from app.core.config import settings
from app.core.logging import get_logger
from app.services.sklearn_infer import get_sklearn_service, is_sklearn_available

logger = get_logger()

# Graceful import of onnxruntime - app should not crash if unavailable
try:
    import onnxruntime as ort
    ONNXRUNTIME_AVAILABLE = True
except ImportError:
    ONNXRUNTIME_AVAILABLE = False
    ort = None
    logger.warning("onnxruntime not available - ONNX model inference will be disabled")

# Clause type labels (CUAD dataset categories, subset for MVP)
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

# Risk mapping (which clause types are high risk)
HIGH_RISK_TYPES = {
    "Termination": 0.8,
    "Indemnification": 0.9,
    "Liability Cap": 0.7,
    "Confidentiality": 0.5,
    "Insurance": 0.6,
    "Intellectual Property": 0.7,
    "Assignment": 0.5,
    "Governing Law": 0.4,
}


class ONNXInferenceService:
    """ONNX inference service for ClauseRiskNet."""
    
    def __init__(self, model_path: Optional[str] = None, calibration_path: Optional[str] = None):
        self.model_path = model_path or settings.model_path
        self.calibration_path = calibration_path or settings.calibration_path
        self.session = None
        self.calibration_params = None
        self._load_model()
        self._load_calibration()
    
    def _load_model(self):
        """Load ONNX model."""
        if not ONNXRUNTIME_AVAILABLE:
            logger.warning("onnxruntime not installed - ONNX model inference disabled")
            self.session = None
            return
            
        model_path_obj = Path(self.model_path)
        if not model_path_obj.exists():
            logger.warning(
                "ONNX model not found, using dummy heuristic classifier",
                model_path=self.model_path
            )
            self.session = None
            return
        
        try:
            providers = ['CPUExecutionProvider']
            # Try CUDA if available
            try:
                ort.InferenceSession('', providers=['CUDAExecutionProvider'])
                providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
            except:
                pass
            
            self.session = ort.InferenceSession(
                str(model_path_obj),
                providers=providers
            )
            logger.info("Loaded ONNX model", model_path=self.model_path, providers=providers)
        except Exception as e:
            logger.error("Failed to load ONNX model, using dummy classifier", error=str(e))
            self.session = None
    
    def _load_calibration(self):
        """Load calibration parameters."""
        calib_path_obj = Path(self.calibration_path)
        if calib_path_obj.exists():
            try:
                with open(calib_path_obj, 'r') as f:
                    self.calibration_params = json.load(f)
                logger.info("Loaded calibration parameters", path=self.calibration_path)
            except Exception as e:
                logger.warning("Failed to load calibration params", error=str(e))
                self.calibration_params = None
        else:
            logger.info("No calibration file found, using default")
            self.calibration_params = None
    
    def _dummy_tokenize(self, text: str, max_length: int = 512) -> np.ndarray:
        """Simple tokenization for dummy model (not a real tokenizer, just for shape)."""
        # In real model, this would use the actual tokenizer
        # For dummy, we just create a dummy input
        return np.random.randint(0, 1000, size=(1, min(max_length, len(text) // 4)), dtype=np.int64)
    
    def _dummy_classify(self, text: str) -> Tuple[np.ndarray, float]:
        """
        Dummy classifier using heuristics.
        Returns (type_logits, risk_score)
        """
        text_lower = text.lower()
        
        # Simple keyword matching for clause types
        type_scores = np.zeros(len(CLAUSE_TYPES), dtype=np.float32)
        
        keywords = {
            "Termination": ["terminate", "termination", "end", "expire", "expiration"],
            "Indemnification": ["indemnif", "indemnity", "hold harmless", "defend"],
            "Liability Cap": ["liability cap", "maximum liability", "limit of liability"],
            "Confidentiality": ["confidential", "non-disclosure", "nda", "secret"],
            "Insurance": ["insurance", "insure", "coverage", "policy"],
            "Intellectual Property": ["intellectual property", "ip", "patent", "copyright", "trademark"],
            "Assignment": ["assign", "assignment", "transfer"],
            "Governing Law": ["governing law", "jurisdiction", "law of", "legal system"],
        }
        
        for idx, clause_type in enumerate(CLAUSE_TYPES):
            score = 0.0
            for keyword in keywords.get(clause_type, []):
                if keyword in text_lower:
                    score += 0.3
            type_scores[idx] = min(score, 1.0)
        
        # Normalize (sigmoid-like)
        type_logits = np.log((type_scores + 1e-6) / (1 - type_scores + 1e-6))
        
        # Risk score: average of high-risk type scores, weighted
        risk_score = 0.0
        for idx, clause_type in enumerate(CLAUSE_TYPES):
            if clause_type in HIGH_RISK_TYPES:
                risk_score += type_scores[idx] * HIGH_RISK_TYPES[clause_type]
        
        risk_score = min(risk_score / len(CLAUSE_TYPES) if CLAUSE_TYPES else 0, 1.0) * 100
        
        return type_logits, risk_score
    
    def classify_clause(self, text: str) -> Dict[str, any]:
        """
        Classify a clause and compute risk score.
        
        Args:
            text: Clause text
            
        Returns:
            Dictionary with keys: clause_type, risk_score, confidence, type_probs
        """
        if not ONNXRUNTIME_AVAILABLE or self.session is None:
            # ONNX runtime not available or model not loaded
            # Try sklearn fallback
            sklearn_service = get_sklearn_service()
            if sklearn_service:
                logger.info("Using sklearn classifier (ONNX not available)")
                return sklearn_service.classify_clause(text)
            # Use dummy classifier
            logger.warning("Using dummy classifier (no ONNX or sklearn model available)")
            type_logits, risk_score = self._dummy_classify(text)
        else:
            # Real ONNX inference
            try:
                # Tokenize (in real implementation, use actual tokenizer)
                # For now, assume model expects input_ids
                inputs = self._dummy_tokenize(text)  # Replace with real tokenizer
                
                # Run inference
                input_name = self.session.get_inputs()[0].name
                output_names = [output.name for output in self.session.get_outputs()]
                
                outputs = self.session.run(output_names, {input_name: inputs})
                
                # Assume outputs are [type_logits, risk_logit]
                type_logits = outputs[0][0]  # Shape: (num_types,)
                risk_logit = outputs[1][0] if len(outputs) > 1 else 0.0
                
                # Apply sigmoid to risk logit
                risk_score = 1 / (1 + np.exp(-risk_logit)) * 100
                
            except Exception as e:
                logger.error("ONNX inference failed, trying sklearn fallback", error=str(e))
                sklearn_service = get_sklearn_service()
                if sklearn_service:
                    return sklearn_service.classify_clause(text)
                type_logits, risk_score = self._dummy_classify(text)
        
        # Apply calibration if available
        if self.calibration_params and "temperature" in self.calibration_params:
            temperature = self.calibration_params["temperature"]
            type_logits = type_logits / temperature
        
        # Convert logits to probabilities
        type_probs = 1 / (1 + np.exp(-type_logits))  # Sigmoid
        
        # Get predicted type (highest probability)
        predicted_idx = int(np.argmax(type_probs))
        predicted_type = CLAUSE_TYPES[predicted_idx] if predicted_idx < len(CLAUSE_TYPES) else "Other"
        confidence = float(type_probs[predicted_idx])
        
        # If confidence is low, set type to None
        if confidence < 0.3:
            predicted_type = None
        
        result = {
            "clause_type": predicted_type,
            "risk_score": float(risk_score),
            "confidence": float(confidence),
            "type_probs": {CLAUSE_TYPES[i]: float(type_probs[i]) for i in range(len(CLAUSE_TYPES))},
        }
        
        return result
    
    def get_model_status(self) -> str:
        """Get current model status."""
        if not ONNXRUNTIME_AVAILABLE:
            # If onnxruntime is not installed, skip ONNX check
            if is_sklearn_available():
                return "sklearn"
            else:
                return "dummy"
        elif self.session is not None:
            return "onnx"
        elif is_sklearn_available():
            return "sklearn"
        else:
            return "dummy"


# Global instance
_onnx_service: Optional[ONNXInferenceService] = None


def get_onnx_service() -> ONNXInferenceService:
    """Get global ONNX inference service instance."""
    global _onnx_service
    if _onnx_service is None:
        _onnx_service = ONNXInferenceService()
    return _onnx_service
