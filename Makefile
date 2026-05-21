.PHONY: help install lint format test test-cov run docker-build docker-up docker-down clean

PYTHON := python3
PIP := $(PYTHON) -m pip
VENV := .venv

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies (creates venv)
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -e ".[dev]"

install-airflow:  ## Install with Airflow extras
	$(VENV)/bin/pip install -e ".[dev,airflow]"

lint:  ## Run ruff + mypy
	$(VENV)/bin/ruff check src tests
	$(VENV)/bin/mypy src

format:  ## Format with black + ruff
	$(VENV)/bin/black src tests
	$(VENV)/bin/ruff check --fix src tests

test:  ## Run pytest
	$(VENV)/bin/pytest -v

test-cov:  ## Run pytest with coverage
	$(VENV)/bin/pytest --cov=src/finance_etl --cov-report=html --cov-report=term

run:  ## Run the pipeline against sample data
	$(VENV)/bin/python -m finance_etl.main run --source sample --date today

run-fraud:  ## Run only the fraud scoring step
	$(VENV)/bin/python -m finance_etl.main fraud-scan --input data/sample/transactions.csv

docker-build:  ## Build Docker image
	docker compose build

docker-up:  ## Start local infra (PG, Redis, MinIO)
	docker compose up -d postgres redis minio

docker-down:  ## Stop and remove containers
	docker compose down -v

clean:  ## Remove build artifacts & caches
	rm -rf build dist *.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	rm -rf htmlcov .coverage
