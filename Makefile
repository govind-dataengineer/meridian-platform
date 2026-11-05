.DEFAULT_GOAL := help
RUN := uv run

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

sync: ## Install Python deps into .venv
	uv sync

up: ## Start MySQL + Floci + Adminer and wait until ready
	docker compose up -d mysql floci adminer
	$(RUN) python scripts/wait_for_stack.py

down: ## Stop the stack (keeps data)
	docker compose down

reset: ## Stop and DELETE all local data, then start fresh
	docker compose down -v
	$(MAKE) up

logs: ## Tail stack logs
	docker compose logs -f

trusted-check: ## Count rows in the seeded course database
	$(RUN) meridian trusted-check

upload: ## Upload data/landing to Floci S3
	$(RUN) meridian upload

ingest: ## Ingest the S3 delivery into MySQL
	$(RUN) meridian ingest --source s3://meridian-landing/2026-09-18

generate: ## Generate synthetic test data into data/generated
	$(RUN) meridian generate

ingest-local: ## Ingest straight from data/landing (no S3)
	$(RUN) meridian ingest --source data/landing

lint: ## ruff + format check + mypy
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	$(RUN) mypy

fmt: ## Auto-fix lint and formatting
	$(RUN) ruff check . --fix
	$(RUN) ruff format .

test: ## Unit tests (no Docker)
	$(RUN) pytest --cov=meridian --cov-report=term-missing

test-integration: ## End-to-end tests against the running stack
	$(RUN) pytest -m integration

ci: lint test ## What CI's first job runs

.PHONY: help sync up down reset logs trusted-check upload ingest generate ingest-local lint fmt test test-integration ci
