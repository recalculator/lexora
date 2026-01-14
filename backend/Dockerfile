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
COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/storage /app/models

# Expose port
EXPOSE 8000

# Default command (will be overridden by docker-compose)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
