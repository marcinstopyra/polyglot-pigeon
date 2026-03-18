.PHONY: format lint release

format:
	poetry run ruff format .
	poetry run ruff check --fix .

lint:
	poetry run ruff check .
	poetry run ruff format --check .

release:
ifndef VERSION
	$(error VERSION is required — usage: make release VERSION=0.2.0)
endif
	poetry run python utilities/release.py $(VERSION)
