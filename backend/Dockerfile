FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# Note: Some packages may need gcc/g++ for building Python extensions
# If Debian mirrors are out of sync, this may fail temporarily
RUN apt-get update && \
    apt-get install -y --fix-broken && \
    apt-get install -y gcc g++ libgomp1 && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
# Railway: Use requirements.txt (includes onnxruntime)
# For local dev with smaller image, use requirements-prod.txt
# torch is installed from the CPU-only index first so sentence-transformers
# doesn't pull the much larger CUDA build
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 && \
    pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image at a pinned revision (keep in sync
# with EMBEDDING_MODEL_REVISION in app/core/config.py). HF_HOME lives outside
# /app because docker-compose bind-mounts the source over /app.
ENV HF_HOME=/opt/hf_cache
ARG EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
ARG EMBEDDING_MODEL_REVISION=1110a243fdf4706b3f48f1d95db1a4f5529b4d41
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}', revision='${EMBEDDING_MODEL_REVISION}', device='cpu')"
# Serve the baked weights without network lookups; a different model at
# runtime would fail to load and retrieval falls back to TF-IDF (logged).
ENV HF_HUB_OFFLINE=1

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/storage /app/models

# Expose port (Railway sets PORT env var)
EXPOSE ${PORT:-8000}

# Start command: run migrations then start server
# Railway sets PORT env var automatically
# Using shell form to support env var substitution and multiple commands
# Note: ${PORT:-8080} expands PORT env var, defaults to 8080 if not set
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
