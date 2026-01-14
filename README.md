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
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `MODEL_PATH` - Path to ONNX model file

## Development

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

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
2. **Training**: Model training requires GPU and takes hours; dummy model included
3. **LLM**: Requires OpenAI/OpenRouter API key
4. **Storage**: PDFs stored on filesystem; no cloud storage
5. **Rate Limiting**: Basic rate limiting only

## Next Steps

- [ ] Implement user authentication
- [ ] Add cloud storage for PDFs (S3, etc.)
- [ ] Fine-tune local LLM option (Llama, Mistral)
- [ ] Enhanced clause segmentation with ML
- [ ] Multi-document comparison
- [ ] Export to Word/PDF with tracked changes

## License

MIT
