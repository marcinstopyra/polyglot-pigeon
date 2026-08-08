.PHONY: format lint test release db-up migrate

format:
	poetry run ruff format .
	poetry run ruff check --fix .

lint:
	poetry run ruff check .
	poetry run ruff format --check .
	poetry run lint-imports

test:
	# Unit suite only (see pyproject.toml testpaths) — SQLite in-memory,
	# no Docker required. tests/integration_tests/ needs `make db-up` and is
	# run separately: poetry run pytest tests/integration_tests/
	poetry run pytest

db-up:
	docker compose up -d db

migrate:
	poetry run alembic upgrade head

release:
ifndef VERSION
	$(error VERSION is required — usage: make release VERSION=0.2.0)
endif
	poetry run python utilities/release.py $(VERSION)
