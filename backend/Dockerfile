FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# Note: Some packages may need gcc/g++ for building Python extensions
# If Debian mirrors are out of sync, this may fail temporarily
RUN apt-get update && \
    apt-get install -y --fix-broken && \
    apt-get install -y gcc g++ || echo "Warning: gcc/g++ installation failed, continuing..." && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
# Railway: Use requirements.txt (includes onnxruntime)
# For local dev with smaller image, use requirements-prod.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/storage /app/models

# Expose port (Railway sets PORT env var)
EXPOSE ${PORT:-8000}

# Start command: run migrations then start server
# Railway sets PORT env var automatically
# Using shell form to support env var substitution and multiple commands
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
