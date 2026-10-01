.PHONY: up down build migrate seed train_model clean test

up:
	docker-compose up -d
	@echo "Services starting... Wait a few seconds, then run 'make migrate'"

down:
	docker-compose down

build:
	docker-compose build

migrate:
	docker-compose exec backend alembic upgrade head

migrate-create:
	docker-compose exec backend alembic revision --autogenerate -m "$(name)"

seed:
	docker-compose exec backend python -m app.scripts.seed_data

train_model:
	cd ml && python download_cuad.py && python train_clause_risknet.py && python calibrate.py && python export_onnx.py

logs:
	docker-compose logs -f

logs-backend:
	docker-compose logs -f backend

logs-frontend:
	docker-compose logs -f frontend

test:
	docker-compose exec backend pytest
	cd frontend && npm test

clean:
	docker-compose down -v
	docker-compose rm -f
	rm -rf backend/storage/*
	rm -rf frontend/.next
	rm -rf frontend/node_modules

restart:
	docker-compose restart

shell-backend:
	docker-compose exec backend /bin/bash

shell-frontend:
	docker-compose exec frontend /bin/sh

status:
	docker-compose ps

# ---------------------------------------------------------------------------
# Retrieval corpus and benchmarks (see bench/PREREGISTRATION.md)
#   make corpus                 download CUAD + build corpus/split (local files)
#   make load-corpus ENV=...    load reference split into reference_clauses (REPLACE=1 to reload)
#   make bench ENV=local|azure  full benchmark -> bench/results/<ts>_<env>.json + .md + plots
#   make bench-dry ENV=...      small-subset dry run into the scratch dir (not for reporting)
# ENV=azure uses DATABASE_URL from your shell environment (never written to files).
# ---------------------------------------------------------------------------
ENV ?= local
BENCH_IMAGE ?= lexora-bench
LOCAL_DATABASE_URL ?= postgresql://lexora:lexora123@postgres:5432/lexora?sslmode=disable
DRY_OUT ?= /tmp/lexora-bench-dry

ifeq ($(ENV),local)
BENCH_NET := --network lexora_network
BENCH_DB := -e DATABASE_URL=$(LOCAL_DATABASE_URL)
else
BENCH_NET :=
BENCH_DB := -e DATABASE_URL
endif

GIT_INFO = -e GIT_COMMIT="$$(git rev-parse HEAD)" \
	-e GIT_DIRTY_FILES="$$(git status --porcelain | wc -l | tr -d ' ')" \
	-e GIT_DIFF_SHA="$$(git diff HEAD | shasum -a 256 | cut -d' ' -f1)"
CLIENT_INFO = -e BENCH_CLIENT_CPU="$$(sysctl -n machdep.cpu.brand_string 2>/dev/null || grep -m1 'model name' /proc/cpuinfo | cut -d: -f2)" \
	-e BENCH_DOCKER_RESOURCES="$$(docker info --format '{{.NCPU}} CPUs, {{.MemTotal}} bytes memory')" \
	-e BENCH_AZURE_SKU -e BENCH_HOST_DESC

.PHONY: bench bench-dry bench-image bench-test corpus load-corpus check-db-url

check-db-url:
	@if [ "$(ENV)" != "local" ] && [ -z "$$DATABASE_URL" ]; then echo "DATABASE_URL must be set for ENV=$(ENV)"; exit 1; fi

bench-image:
	docker build -t lexora-backend:bench ./backend
	docker build -t $(BENCH_IMAGE) --build-arg BACKEND_IMAGE=lexora-backend:bench -f bench/Dockerfile bench

corpus: bench-image
	docker run --rm -e HF_HUB_OFFLINE=0 -v "$(CURDIR):/repo" -w /repo/ml $(BENCH_IMAGE) python download_cuad.py
	docker run --rm -v "$(CURDIR):/repo" -w /repo $(BENCH_IMAGE) python bench/build_cuad_corpus.py

load-corpus: check-db-url bench-image
	docker run --rm $(BENCH_NET) $(BENCH_DB) -v "$(CURDIR):/repo" -w /repo/backend $(BENCH_IMAGE) \
		python -m app.scripts.load_reference_corpus --corpus /repo/bench/data/cuad_corpus.jsonl \
		--env $(ENV) --record /repo/bench/results/load_$$(date -u +%Y%m%dT%H%M%SZ)_$(ENV).json $(if $(REPLACE),--replace,)

bench-test: bench-image
	docker run --rm -v "$(CURDIR):/repo" -w /repo $(BENCH_IMAGE) python -m pytest -q -p no:cacheprovider bench/tests

bench: check-db-url bench-image
	docker run --rm $(BENCH_NET) $(BENCH_DB) $(GIT_INFO) $(CLIENT_INFO) \
		-v "$(CURDIR):/repo" -w /repo $(BENCH_IMAGE) python bench/run_bench.py --env $(ENV)

bench-dry: check-db-url bench-image
	mkdir -p $(DRY_OUT)
	docker run --rm $(BENCH_NET) $(BENCH_DB) $(GIT_INFO) $(CLIENT_INFO) -v "$(CURDIR):/repo" \
		-v "$(DRY_OUT):/dry" -w /repo $(BENCH_IMAGE) python bench/run_bench.py --env $(ENV) --dry-run --out-dir /dry
