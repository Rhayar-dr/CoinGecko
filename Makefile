# CoinGecko data engineering pipeline — poucos comandos, cada um faz tudo.
#
#   make setup   -> prepara o ambiente local (venv + dependências)
#   make check   -> qualidade: formata, faz lint e roda os testes
#   make up      -> sobe tudo no Docker (PostgreSQL + app, schema pronto)
#   make demo    -> roda a pipeline completa de ponta a ponta (prova que funciona)
#   make down    -> derruba o Docker e limpa
#   make clean   -> remove caches/artefatos

VENV    ?= .venv
PYTHON  := $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python3)
COMPOSE := docker compose

.DEFAULT_GOAL := help

.PHONY: help
help: ## Lista os comandos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-8s\033[0m %s\n", $$1, $$2}'

.PHONY: setup
setup: ## Cria o venv e instala tudo para rodar/testar localmente
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements-dev.txt
	@echo "OK -> ambiente pronto. Copie .env.example para .env se ainda não fez."

.PHONY: check
check: ## Formata, faz lint e roda os testes (gate de qualidade)
	$(PYTHON) -m black app tests
	$(PYTHON) -m ruff check --fix app tests
	$(PYTHON) -m pytest

.PHONY: up
up: ## Sobe PostgreSQL + app no Docker (schema criado automaticamente)
	$(COMPOSE) up -d --build
	@echo "OK -> use: make demo  (ou)  docker compose run --rm app <comando>"

.PHONY: demo
demo: ## Roda a pipeline completa de ponta a ponta no Docker (com banco)
	$(COMPOSE) run --rm app download --coin bitcoin --date yesterday --database
	$(COMPOSE) run --rm app backfill --coin ethereum --start-date 2026-08-10 --end-date 2026-08-14 --workers 5 --database

.PHONY: down
down: ## Derruba o Docker e remove o volume do banco
	$(COMPOSE) down -v

.PHONY: clean
clean: ## Remove caches e artefatos de build
	rm -rf .pytest_cache .ruff_cache *.egg-info build dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
