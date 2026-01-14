# Lexora Demo Guide

## Quick Start Demo

### 1. Start Services

```bash
# Start all services
make up

# Wait for services to be ready (30-60 seconds)
# Check logs: make logs
```

### 2. Run Migrations

```bash
make migrate
```

### 3. Seed Sample Data (Optional)

```bash
make seed
```

### 4. Access Application

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## Demo Workflow

### Step 1: Upload PDF

1. Open http://localhost:3000
2. Click "Upload" tab (default)
3. Select a PDF contract file
4. Click "Upload and Extract Text"
5. Wait for upload confirmation

### Step 2: Analyze Document

1. After upload, you'll be on the "Analyze" tab
2. Click "Analyze Document" button
3. Wait for analysis to complete (~10-30 seconds)
4. View clauses in the sidebar:
   - Clause type (e.g., "Termination", "Indemnification")
   - Risk score (0-100)
   - Confidence (0-1)
   - Risk heatmap bar

### Step 3: Generate Playbook

1. Still on "Analyze" tab
2. Click "Generate Playbook" button
3. Wait for generation (~30-60 seconds, depends on LLM)
4. Go to "Report" tab
5. View negotiation playbook:
   - Document summary
   - Overall risk assessment
   - Priority clauses with recommendations
   - General negotiation strategies

### Step 4: Generate Redlines

1. On "Analyze" tab
2. Click "Generate Redlines" button
3. Wait for generation (~30-60 seconds)
4. Go to "Report" tab
5. View redline suggestions:
   - Priority redlines with track changes
   - Optional redlines
   - Rationale for each change
   - Risk reduction explanations

## Sample Contract

For testing, you can:

1. **Use seed data**: `make seed` creates a sample text document
2. **Download a public contract**: Use any publicly available contract PDF
3. **Create your own**: Generate a simple contract PDF

## Expected Outputs

### Clause Analysis

- 8 clause types classified
- Risk scores between 0-100
- Confidence scores between 0-1
- Heatmap visualization

### Playbook

- JSON-structured output with:
  - Summary
  - Risk assessment
  - Priority clauses (top 5-10)
  - Recommendations per clause
  - General strategies

### Redlines

- JSON-structured output with:
  - Summary
  - Priority redlines (critical changes)
  - Optional redlines (recommended changes)
  - Track changes format: `[DEL: text] [ADD: new text]`
  - Rationale and citations

## Troubleshooting

### Services won't start

```bash
# Check logs
make logs

# Restart services
make restart

# Clean and rebuild
make clean
make build
make up
```

### PDF extraction fails

- Ensure PDF is not password-protected
- Try a different PDF file
- Check backend logs: `make logs-backend`

### Analysis fails

- Check ONNX model exists: `ls ml/models/clause_risknet.onnx`
- If not, the dummy classifier will be used
- Check backend logs for errors

### LLM generation fails

- Check `OPENAI_API_KEY` is set in `.env`
- Verify API key is valid
- Check API quota/limits
- Review backend logs

### Database errors

```bash
# Reset database
docker-compose down -v
make up
make migrate
```

## Demo Script (Video Storyboard)

1. **Introduction (0:00-0:30)**
   - Show Lexora homepage
   - Explain dual-model architecture
   - Highlight key features

2. **Upload (0:30-1:00)**
   - Select PDF contract
   - Upload and extract text
   - Show upload confirmation

3. **Analysis (1:00-2:00)**
   - Trigger analysis
   - Show clause list with types and risk scores
   - Highlight heatmap visualization
   - Explain risk levels (Low/Medium/High/Critical)

4. **Playbook (2:00-3:00)**
   - Generate playbook
   - Show priority clauses
   - Explain recommendations
   - Highlight negotiation strategies

5. **Redlines (3:00-4:00)**
   - Generate redlines
   - Show track changes format
   - Explain rationale
   - Highlight risk reduction

6. **Summary (4:00-4:30)**
   - Show complete report
   - Recap features
   - Next steps

## Performance Benchmarks

Expected timings (approximate):
- PDF upload: 1-3 seconds
- Text extraction: 1-5 seconds
- Clause analysis: 5-15 seconds
- Playbook generation: 30-60 seconds (depends on LLM)
- Redline generation: 30-60 seconds (depends on LLM)

## Configuration

Edit `.env` for:
- LLM API key
- Model paths
- Database URLs
- Logging levels

See `.env.example` for all options.
