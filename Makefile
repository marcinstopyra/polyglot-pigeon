.PHONY: format lint test test-integration release db-up migrate

format:
	poetry run ruff format .
	poetry run ruff check --fix .

lint:
	poetry run ruff check .
	poetry run ruff format --check .
	poetry run lint-imports

test:
	# Unit suite only — SQLite in-memory, no Docker required. Everything
	# needing a real MySQL carries the "mysql" marker (pyproject.toml) and
	# lives under tests/integration_tests/; `make test-integration` runs it.
	poetry run pytest -m "not mysql"

db-up:
	docker compose up -d db

migrate:
	poetry run alembic upgrade head

test-integration:
	# DB_NAME=polyglot_test — a separate database from development's
	# `polyglot`, so a careless run can never drop a developer's local data
	# (documented alongside `db-up` in the README). Creating it here keeps
	# this a single command with no manual setup beyond a running Docker
	# daemon.
	docker compose up -d --wait db
	docker compose exec -T db mysql -uroot -p"$${DB_ROOT_PASSWORD:-polyglot}" \
		-e "CREATE DATABASE IF NOT EXISTS polyglot_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
	DB_NAME=polyglot_test poetry run alembic upgrade head
	DB_NAME=polyglot_test poetry run pytest tests/integration_tests/ -m mysql

release:
ifndef VERSION
	$(error VERSION is required — usage: make release VERSION=0.2.0)
endif
	poetry run python utilities/release.py $(VERSION)
