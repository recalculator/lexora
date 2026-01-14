# Lexora Architecture

## Overview

Lexora is a dual-model legal contract analysis platform combining:

1. **ClauseRiskNet**: Custom lightweight clause classifier and risk scorer (ONNX-based)
2. **LLM Component**: OpenAI-compatible API for negotiation playbooks and redlines

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Next.js)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  Upload  │  │PDF Viewer│  │  Clauses │  │  Report  │   │
│  │   PDF    │  │          │  │  List    │  │          │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ HTTP/REST
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Backend API (FastAPI)                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │               API Routes Layer                      │   │
│  │  POST /api/upload                                  │   │
│  │  POST /api/analyze/{id}                            │   │
│  │  POST /api/playbook/{id}                           │   │
│  │  POST /api/redlines/{id}                           │   │
│  │  GET  /api/report/{id}                             │   │
│  └─────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Service Layer                          │   │
│  │  • PDF Extraction (pdfplumber/pypdf)               │   │
│  │  • Clause Segmentation (heuristic)                 │   │
│  │  • ONNX Inference (ClauseRiskNet)                  │   │
│  │  • TF-IDF Retrieval (RAG)                          │   │
│  │  • LLM Client (OpenAI-compatible)                  │   │
│  │  • Playbook Generation                             │   │
│  │  • Redline Generation                              │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
    ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
    │Postgres│    │ Redis  │    │  ONNX  │    │  LLM   │
    │   DB   │    │(Cache) │    │ Model  │    │  API   │
    └────────┘    └────────┘    └────────┘    └────────┘
```

## Data Flow

### 1. Document Upload & Text Extraction

```
User uploads PDF
    ↓
Backend saves PDF to storage
    ↓
PDF Extraction Service (pdfplumber/pypdf)
    ↓
Text stored in PostgreSQL (DocumentText table)
```

### 2. Clause Analysis

```
User triggers analysis
    ↓
Clause Segmentation Service
    • Split by headings
    • Fallback to paragraphs
    • Merge small chunks
    ↓
ONNX Inference (ClauseRiskNet)
    • Multi-label classification (8 clause types)
    • Risk scoring (0-100)
    • Confidence calculation
    ↓
Results stored in PostgreSQL (Clause table)
```

### 3. Playbook Generation

```
User triggers playbook generation
    ↓
TF-IDF Retrieval
    • Index high-risk clauses
    • Retrieve relevant context
    ↓
LLM Client (OpenAI-compatible)
    • RAG-grounded prompt
    • Structured JSON output
    • Pydantic validation
    ↓
Results stored in PostgreSQL (Playbook table)
```

### 4. Redline Generation

```
User triggers redline generation
    ↓
TF-IDF Retrieval
    • Index high-risk clauses
    • Retrieve relevant context
    ↓
LLM Client (OpenAI-compatible)
    • RAG-grounded prompt
    • Structured JSON output with track changes
    • Pydantic validation
    ↓
Results stored in PostgreSQL (Redlines table)
```

## Database Schema

### Documents
- **documents**: Document metadata (id, filename, created_at)
- **document_texts**: Extracted text content
- **clauses**: Segmented and classified clauses
- **playbooks**: Generated negotiation playbooks
- **redlines**: Generated redline suggestions
- **prompt_logs**: LLM prompt/response logs (optional)

## ML Model Architecture

### ClauseRiskNet

Based on DistilBERT with:
- **Backbone**: DistilBERT base (lightweight BERT)
- **Classification Head**: Multi-label binary classification (8 clause types)
- **Risk Head**: Regression head for risk scoring (0-100)
- **Calibration**: Temperature scaling on validation set

Clause Types (8 categories):
1. Termination
2. Indemnification
3. Liability Cap
4. Confidentiality
5. Insurance
6. Intellectual Property
7. Assignment
8. Governing Law

## RAG Architecture

- **Retrieval**: TF-IDF vectorization
- **Index**: Document vectors for all clauses
- **Query**: High-risk clauses or user queries
- **Context**: Top-k retrieved clauses passed to LLM

## Security

- File upload size limits (10MB default)
- Filename sanitization
- CORS configuration
- Session management (anonymous for MVP)
- Rate limiting (basic)

## Deployment

All services run in Docker containers:
- Frontend: Next.js (port 3000)
- Backend: FastAPI (port 8000)
- PostgreSQL: Database (port 5432)
- Redis: Cache (port 6379)

Orchestrated via Docker Compose.

## Scaling Considerations

- **Backend**: Horizontal scaling via multiple FastAPI instances
- **Database**: Read replicas for queries
- **Cache**: Redis cluster for distributed caching
- **ML**: ONNX Runtime supports GPU acceleration
- **Storage**: Move to S3/cloud storage for PDFs

## Known Limitations (MVP)

1. Heuristic clause segmentation (not ML-based)
2. TF-IDF retrieval (not semantic embeddings)
3. Anonymous sessions only
4. Local file storage
5. Basic rate limiting

## Future Enhancements

1. Fine-tuned local LLM (Llama, Mistral)
2. Semantic retrieval (sentence-transformers)
3. ML-based clause segmentation
4. User authentication
5. Cloud storage integration
6. Multi-document comparison
