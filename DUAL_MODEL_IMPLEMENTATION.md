# Dual-Model Implementation Summary

## Overview

This PR implements a genuine dual-model system for Lexora by:
1. **Replacing dummy classifier** with a real sklearn-based model using sentence-transformers
2. **Adding OpenAI fine-tuning pipeline** for LLM tasks (explain endpoint)

## Files Added

### ML Training & Evaluation
- `ml/train_clause_classifier_sklearn.py` - Trains sklearn classifier with sentence-transformers embeddings
- `ml/eval_classifier.py` - Evaluates classifier and generates report
- `ml/generate_synthetic_explain_dataset.py` - Generates synthetic fine-tuning dataset
- `ml/openai_upload.py` - Uploads JSONL to OpenAI
- `ml/openai_finetune.py` - Creates fine-tuning job
- `ml/openai_check_job.py` - Monitors fine-tuning job status

### Backend Services
- `backend/app/services/sklearn_infer.py` - Sklearn inference service
- `backend/app/scripts/export_finetune_dataset.py` - Exports prompt logs to OpenAI format

### Documentation
- `docs/FINE_TUNING.md` - Complete fine-tuning guide

### Tests
- `backend/tests/test_sklearn_infer.py` - Tests for sklearn inference

## Files Modified

### Backend
- `backend/app/core/config.py` - Added `sklearn_model_dir` setting
- `backend/app/services/onnx_infer.py` - Added fallback logic and `get_model_status()` method
- `backend/app/api/routes.py` - Added `model_status` to analyze and summary responses
- `backend/app/services/llm_client.py` - Added `OPENAI_MODEL` env var support
- `backend/requirements.txt` - Added `sentence-transformers`, `joblib`

### Frontend
- `frontend/lib/api.ts` - Added `model_status` to `AnalyzeResponse` and `ModelInfo` interfaces
- `frontend/components/AnalyzePage.tsx` - Display model status badge
- `frontend/components/ReportView.tsx` - Display model status in report

### ML
- `ml/requirements.txt` - Added `sentence-transformers`, `scikit-learn`, `joblib`

## Commands to Train Sklearn Model

```bash
# Install dependencies
cd ml
pip install -r requirements.txt

# Train classifier (uses synthetic data if CUAD not found)
python train_clause_classifier_sklearn.py

# Evaluate classifier
python eval_classifier.py

# Check results
cat ml/REPORT.md
```

**Model artifacts saved to:**
- `models/sklearn/classifiers.joblib` - Trained classifiers
- `models/sklearn/encoder/` - Sentence transformer encoder
- `models/sklearn/label_map.json` - Label mapping
- `models/sklearn/risk_weights.json` - Risk weight mapping
- `models/sklearn/metadata.json` - Model metadata

## Commands to Run Fine-Tuning

### Option 1: Export from Prompt Logs
```bash
cd backend
python -m app.scripts.export_finetune_dataset
```

### Option 2: Generate Synthetic Dataset
```bash
cd ml
python generate_synthetic_explain_dataset.py
# Or with teacher model:
python generate_synthetic_explain_dataset.py --use-teacher --teacher-model gpt-4o
```

### Upload and Fine-Tune
```bash
# Upload dataset
python openai_upload.py --file finetune_explain.jsonl

# Create fine-tuning job
python openai_finetune.py --model gpt-4o-mini --suffix lexora-explain

# Monitor job
python openai_check_job.py --watch
```

### Use Fine-Tuned Model
```bash
# Set in .env or environment
export OPENAI_MODEL=ft:gpt-4o-mini-org:lexora-explain:abc123...
```

## How to Verify Model Status is Not Dummy

1. **Train sklearn model:**
   ```bash
   cd ml && python train_clause_classifier_sklearn.py
   ```

2. **Copy model to backend:**
   ```bash
   # In Docker, models should be in /app/models/sklearn
   # Or mount volume: -v $(pwd)/ml/models:/app/models
   ```

3. **Check backend logs:**
   - Should see: "Sklearn model loaded successfully"
   - NOT: "Using dummy classifier"

4. **Check API response:**
   ```bash
   curl http://localhost:8000/api/analyze/1
   # Response should include: "model_status": "sklearn"
   ```

5. **Check frontend:**
   - Analyze page should show "Classifier: Sklearn" (blue badge)
   - Report page should show "Sklearn" in document info

## Model Status Priority

1. **ONNX** - If `models/clause_risknet.onnx` exists
2. **Sklearn** - If `models/sklearn/classifiers.joblib` exists
3. **Dummy** - Fallback (emits warning)

## Testing

```bash
# Backend tests
cd backend
pytest tests/test_sklearn_infer.py

# Verify model status
pytest tests/test_sklearn_infer.py::test_model_status_deterministic
```

## Limitations

- Sklearn model uses synthetic data if CUAD not provided
- Fine-tuning requires OpenAI API key
- Model status is determined at startup (restart backend after training)
- Fine-tuned model name must be manually set in environment

## Next Steps

1. Train sklearn model with real CUAD data
2. Fine-tune LLM on production explain logs
3. Add model versioning and A/B testing
4. Add automated evaluation metrics
