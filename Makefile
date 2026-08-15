# CoinGecko data engineering pipeline — common tasks.
#
# Run `make` or `make help` to list the available targets.

# Use the virtualenv interpreter when it exists, otherwise fall back to python3.
VENV        ?= .venv
PYTHON      := $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python3)
PIP         := $(PYTHON) -m pip
COMPOSE     := docker compose

# Defaults for the run-* helper targets (override on the command line, e.g.
#   make download COIN=ethereum DATE=2026-08-10 DB=--database
COIN        ?= bitcoin
DATE        ?= yesterday
START       ?= 2026-08-01
END         ?= 2026-08-14
WORKERS     ?= 5
DB          ?=

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# --------------------------------------------------------------------------- #
# Environment
# --------------------------------------------------------------------------- #
.PHONY: venv
venv: ## Create the virtualenv in ./$(VENV)
	python3 -m venv $(VENV)

.PHONY: install
install: ## Install runtime dependencies
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

.PHONY: install-dev
install-dev: ## Install runtime + dev dependencies (tests, linters)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt

# --------------------------------------------------------------------------- #
# Quality
# --------------------------------------------------------------------------- #
.PHONY: lint
lint: ## Run ruff
	$(PYTHON) -m ruff check app tests

.PHONY: format
format: ## Auto-format with black + ruff --fix
	$(PYTHON) -m black app tests
	$(PYTHON) -m ruff check --fix app tests

.PHONY: format-check
format-check: ## Check formatting without changing files
	$(PYTHON) -m black --check app tests
	$(PYTHON) -m ruff check app tests

.PHONY: test
test: ## Run the unit test suite (no DB needed)
	$(PYTHON) -m pytest

.PHONY: test-db
test-db: ## Run the PostgreSQL integration tests (needs TEST_DATABASE_URL)
	TEST_DATABASE_URL=$${TEST_DATABASE_URL:-postgresql+psycopg2://crypto_user:change_me@localhost:5432/crypto} \
		$(PYTHON) -m pytest tests/test_repository.py

.PHONY: check
check: format-check test ## Formatting check + tests (CI-style gate)

# --------------------------------------------------------------------------- #
# Run the CLI locally
# --------------------------------------------------------------------------- #
.PHONY: download
download: ## Download one coin/date (COIN=, DATE=, DB=--database)
	$(PYTHON) -m app download --coin $(COIN) --date $(DATE) $(DB)

.PHONY: backfill
backfill: ## Backfill a range (COIN=, START=, END=, WORKERS=, DB=--database)
	$(PYTHON) -m app backfill --coin $(COIN) --start-date $(START) --end-date $(END) --workers $(WORKERS) $(DB)

.PHONY: daily
daily: ## Run the daily job for the default coins (DATE=, DB=--database)
	$(PYTHON) -m app daily --date $(DATE) $(DB)

# --------------------------------------------------------------------------- #
# Docker
# --------------------------------------------------------------------------- #
.PHONY: db-up
db-up: ## Start only PostgreSQL (schema auto-created)
	$(COMPOSE) up -d postgres

.PHONY: docker-build
docker-build: ## Build the app image
	$(COMPOSE) build app

.PHONY: docker-up
docker-up: ## Start the full stack in the background
	$(COMPOSE) up -d

.PHONY: docker-run
docker-run: ## Run a CLI command in a container, e.g. make docker-run ARGS="download --coin bitcoin --date yesterday --database"
	$(COMPOSE) run --rm app $(ARGS)

.PHONY: docker-logs
docker-logs: ## Tail container logs
	$(COMPOSE) logs -f

.PHONY: docker-down
docker-down: ## Stop the stack (keep the DB volume)
	$(COMPOSE) down

.PHONY: docker-clean
docker-clean: ## Stop the stack and drop the DB volume
	$(COMPOSE) down -v

# --------------------------------------------------------------------------- #
# Housekeeping
# --------------------------------------------------------------------------- #
.PHONY: clean
clean: ## Remove caches and build artefacts
	rm -rf .pytest_cache .ruff_cache **/__pycache__ *.egg-info build dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
