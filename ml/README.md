# ML Training Scripts

This directory contains scripts for training ClauseRiskNet model.

## Setup

```bash
cd ml
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Training Pipeline

1. **Download CUAD dataset:**
   ```bash
   python download_cuad.py
   ```

2. **Train model:**
   ```bash
   python train_clause_risknet.py
   ```

3. **Calibrate model:**
   ```bash
   python calibrate.py
   ```

4. **Export to ONNX:**
   ```bash
   python export_onnx.py
   ```

## Model Architecture

ClauseRiskNet is based on DistilBERT with:
- Multi-label classification head for clause types (8 classes)
- Risk scoring head for 0-100 risk scores
- Temperature scaling for calibration

## Output

- Trained model: `models/checkpoints/best/`
- ONNX model: `models/clause_risknet.onnx`
- Calibration: `models/calibration.json`

## Notes

- For MVP, a dummy ONNX model is included so the platform works without training
- Training requires GPU for reasonable performance
- CUAD dataset download may take time
