.PHONY: install sync check test test-cov build clean-build help

install: ## Install virtual environment and pre-commit hooks
	@echo "🚀 Creating virtual environment using uv"
	@uv sync --all-groups
	@uv run pre-commit install
	@echo "✅ Setup complete!"

sync: ## Sync virtual environment with pyproject.toml
	@echo "🚀 Syncing virtual environment"
	@uv sync --all-groups

check: ## Run code quality checks
	@echo "🚀 Running code quality checks"
	@uv run pre-commit run --all-files
	@uv run mypy backend/src

test: ## Run tests
	@echo "🧪 Running tests"
	@uv run pytest tests/ -v

test-cov: ## Run tests with coverage
	@echo "🧪 Running tests with coverage"
	@uv run pytest tests/ -v --cov=backend/src --cov-report=term-missing --cov-report=html

test-unit: ## Run only unit tests
	@echo "🧪 Running unit tests"
	@uv run pytest tests/test_*.py -v

test-integration: ## Run only integration tests
	@echo "🧪 Running integration tests"
	@uv run pytest tests/integration/ -v -m integration

build: clean-build ## Build wheel file
	@echo "🚀 Building package"
	@uv build

clean-build: ## Clean build artifacts
	@echo "🧹 Cleaning build artifacts"
	@rm -rf dist/ build/ *.egg-info/ htmlcov/ .coverage
	@find . -type d -name __pycache__ -delete
	@find . -type f -name "*.pyc" -delete

dev: ## Run development server
	@echo "🚀 Starting development server"
	@uv run uvicorn backend.src.main:app --reload --host 0.0.0.0 --port 8000

format: ## Format code
	@echo "✨ Formatting code"
	@uv run ruff format backend/ tests/
	@uv run ruff check backend/ tests/ --fix

help: ## Show help
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
