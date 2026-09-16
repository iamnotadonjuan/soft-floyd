.PHONY: setup dev dev-server dev-web lint lint-py lint-web test check docs-schema

setup:
	uv sync
	cd apps/web && pnpm install

dev:
	@echo "Run in two terminals: make dev-server / make dev-web"

dev-server:
	uv run soft-floyd serve --reload

dev-web:
	cd apps/web && pnpm dev

lint: lint-py lint-web

lint-py:
	uv run ruff check .
	uv run ruff format --check .

lint-web:
	cd apps/web && pnpm run typecheck

test:
	uv run pytest

check: lint test

docs-schema:
	uv run python scripts/gen_db_schema.py
