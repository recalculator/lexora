# Benchmark image: the backend image (same Python, deps, and baked embedding
# model) plus plotting and test tools. Build via `make bench-image`.
ARG BACKEND_IMAGE=lexora-backend:bench
FROM ${BACKEND_IMAGE}
RUN pip install --no-cache-dir matplotlib==3.9.4 pytest==8.3.4
WORKDIR /repo
