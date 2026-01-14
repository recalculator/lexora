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
