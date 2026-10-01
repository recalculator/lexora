# Lexora - Legal Contract Analysis Platform

Lexora is an end-to-end legal contract analysis platform with a dual-model architecture:

1. **ClauseRiskNet**: A custom lightweight clause classifier and risk scorer trained on CUAD dataset and served via ONNX Runtime
2. **LLM Component**: OpenAI-compatible API (OpenRouter, OpenAI, etc.) for drafting negotiation playbooks and redlines with RAG grounding

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js)                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  Upload  │  │PDF Viewer│  │  Clauses │  │  Report  │    │
│  │   PDF    │  │          │  │  List    │  │          │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Backend API (FastAPI)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ PDF Extract  │  │   Clause     │  │   LLM        │      │
│  │   Service    │  │ Segmentation │  │   Client     │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  ONNX        │  │   TF-IDF     │  │  Playbook    │      │
│  │  Inference   │  │  Retrieval   │  │  Service     │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
         │              │              │
         ▼              ▼              ▼
    ┌─────────┐   ┌─────────┐   ┌─────────┐
    │PostgreSQL│   │  Redis  │   │  ONNX   │
    │          │   │ (Cache) │   │  Model  │
    └─────────┘   └─────────┘   └─────────┘
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Make (optional, for convenience commands)

### Running the Platform

1. **Clone and setup:**
   ```bash
   cd Lexora
   cp .env.example .env
   # Edit .env with your OpenAI API key (or use OpenRouter)
   ```

2. **Start all services:**
   ```bash
   make up
   # or: docker-compose up -d
   ```

3. **Access the application:**
   - Frontend: http://localhost:3002 (or 3000 if available)
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

4. **Run migrations:**
   ```bash
   make migrate
   # or: docker-compose exec backend alembic upgrade head
   ```

5. **Seed sample data (optional):**
   ```bash
   make seed
   ```

### Demo Flow

1. **Click "Load Sample Contract"** - Automatically loads and uploads a sample PDF
2. **Click "Analyze Document"** - Analyzes the contract and extracts clauses
3. **View Top Risks** - See the top 5 highest-risk clauses automatically displayed
4. **Click "Why flagged?"** on any clause - Get AI-powered explanation with risk drivers and negotiation moves
5. **Check Model Info** - View model statistics on the Report tab

### Training ClauseRiskNet Model

If you want to train your own model:

```bash
make train_model
# or manually:
cd ml
python download_cuad.py
python train_clause_risknet.py
python calibrate.py
python export_onnx.py
```

**Note**: For MVP, a dummy ONNX model is included so the platform works without training. Training can take several hours on a GPU.

## Project Structure

```
Lexora/
├── frontend/           # Next.js frontend application
│   ├── app/           # App Router pages
│   ├── components/    # React components
│   ├── lib/          # Utilities
│   └── public/       # Static assets
├── backend/           # FastAPI backend
│   ├── app/          # Application code
│   │   ├── api/      # API routes
│   │   ├── core/     # Config, logging
│   │   ├── db/       # Database models, migrations
│   │   └── services/ # Business logic
│   ├── tests/        # Backend tests
│   └── storage/      # Uploaded PDFs
├── ml/               # ML training and export
│   ├── models/       # Trained models
│   └── scripts/      # Training scripts
├── docs/             # Documentation
├── docker-compose.yml
├── Makefile
└── README.md
```

## API Endpoints

- `POST /api/upload` - Upload a PDF contract
- `POST /api/analyze/{document_id}` - Analyze document and extract clauses
- `POST /api/playbook/{document_id}` - Generate negotiation playbook
- `POST /api/redlines/{document_id}` - Generate redline suggestions
- `GET /api/report/{document_id}` - Get complete analysis report
- `GET /api/document/{document_id}/summary` - Get top risks and model info
- `POST /api/explain/{document_id}/{clause_idx}` - Explain why a clause was flagged
- `GET /api/sample_contract` - Get sample contract PDF for demo

## Key Features

- **PDF Text Extraction**: Robust extraction using pdfplumber with pypdf fallback
- **Clause Segmentation**: Heuristic-based segmentation by headings and paragraphs
- **Clause Classification**: Multi-label classification of 8 common clause types
- **Risk Scoring**: 0-100 risk score per clause with confidence
- **RAG-Powered LLM**: TF-IDF retrieval for grounding LLM responses
- **Structured Outputs**: Pydantic-validated JSON responses
- **Session Management**: Anonymous sessions for MVP

## Configuration

Key environment variables (see `.env.example`):

- `OPENAI_API_KEY` - OpenAI or OpenRouter API key
- `OPENAI_API_BASE` - API base URL (defaults to OpenAI)
- `DATABASE_URL` - PostgreSQL connection string (required for production)
- `REDIS_URL` - Redis connection string
- `PORT` - Server port (defaults to 8000, Railway sets this automatically)
- `MODEL_PATH` - Path to ONNX model file

### Production Dependencies

**Production deployments use `requirements.txt`**. It includes `sentence-transformers` and `pgvector` for embedding-based retrieval; the Dockerfile installs a CPU-only `torch` build first (from the PyTorch CPU wheel index) and bakes the `all-MiniLM-L6-v2` weights into the image at a pinned revision.

**ML dependencies** (`requirements-ml.txt`) are for local training/experimentation and include:
- sentence-transformers (for sklearn classifier embeddings)
- torch
- transformers
- onnxruntime

**Note**: The app boots and all endpoints work without ML dependencies. The sklearn classifier requires `sentence-transformers` (in `requirements-ml.txt`), but the app gracefully falls back to ONNX or dummy classifier if unavailable. Retrieval (`RETRIEVER=tfidf|vector|hybrid`, default `hybrid`) falls back to TF-IDF, with a log line, if the embedding model or the pgvector extension is unavailable.

## Development

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
# Core dependencies (required for production)
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**For ML/Training (optional):**
```bash
# Install heavy ML dependencies (torch, sentence-transformers, etc.)
pip install -r requirements-ml.txt
```

**Note**: The app works without ML dependencies. The sklearn classifier requires `sentence-transformers`, but gracefully falls back to ONNX or dummy classifier if unavailable. Retrieval falls back to TF-IDF if embeddings or pgvector are unavailable.

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### ML Training
```bash
cd ml
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python download_cuad.py
python train_clause_risknet.py
```

## Testing

```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm test
```

## Known Limitations (MVP)

1. **Auth**: Anonymous sessions only; no user accounts
2. **Training**: No trained model artifacts are included; the training scripts run on CPU (the DistilBERT script uses CUDA if available)
3. **LLM**: Requires OpenAI/OpenRouter API key
4. **Storage**: PDFs stored on filesystem; no cloud storage
5. **Rate Limiting**: Basic rate limiting only
6. **Clause classifier**: With no trained model artifacts present (the default), clauses are classified by a rule-based keyword heuristic, not a learned model.
7. **ONNX path**: The ONNX inference path feeds placeholder tokenization (`_dummy_tokenize`), not a real tokenizer, so its outputs are not meaningful.
8. **No classifier metrics**: No clause-classification accuracy/F1 numbers are reported for this project. The sklearn trainer's fallback data is synthetic and repeated, so any score it prints is not a valid held-out measurement.
9. **Failing segmenter tests**: `tests/test_clause_segment.py::test_segment_clauses` and `tests/test_clause_segment.py::test_segment_small_text` fail on `main` (the segmenter returns fewer clauses than the tests expect). They are left as-is pending a segmenter rework.
10. **pgvector required (do not deploy yet)**: Migration `003_add_pgvector` runs `CREATE EXTENSION IF NOT EXISTS vector`, and the backend container runs `alembic upgrade head` on start. Deploying this to a Postgres without the pgvector extension available (e.g. a Railway Postgres that lacks it) will fail at startup. Confirm the production database supports pgvector before merging or deploying.

## Next Steps

- [ ] Implement user authentication
- [ ] Add cloud storage for PDFs (S3, etc.)
- [ ] Fine-tune local LLM option (Llama, Mistral)
- [ ] Enhanced clause segmentation with ML
- [ ] Multi-document comparison
- [ ] Export to Word/PDF with tracked changes

## License

MIT

### Third-party data: CUAD

The precedent corpus and retrieval benchmarks use the **Contract Understanding Atticus Dataset (CUAD) v1** by The Atticus Project (Hendrycks et al., "CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review", NeurIPS 2021 Datasets and Benchmarks Track).

- **Source:** Hugging Face dataset `theatticusproject/cuad`, file `CUAD_v1/CUAD_v1.json`, pinned to revision `a3c393f5d103fd0c516374e4fdff676c8176dcb1` (downloaded by `ml/download_cuad.py`; not committed to this repo).
- **License:** Creative Commons Attribution 4.0 (CC BY 4.0), as stated in the dataset's `CUAD_v1_README.txt`. The Atticus Project makes no representations about the license status of the underlying contracts, which are public EDGAR filings.
- **Changes made:** answer spans are extracted as standalone clauses, the metadata categories Document Name, Parties, Agreement Date and Effective Date are excluded, identical spans within a contract are merged into one row carrying all of their categories, and contracts are split into reference/eval sets (see `bench/build_cuad_corpus.py`).
