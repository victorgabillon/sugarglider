.PHONY: install format lint typecheck test check download-osm up down logs smoke report generate

install:
	uv sync

format:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff format --check .
	uv run ruff check .

typecheck:
	uv run mypy src tests

test:
	uv run pytest -m "not integration"

check: lint typecheck test

download-osm:
	./scripts/download_osm.sh

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs --follow

smoke:
	./scripts/smoke_marly.sh

report:
	./scripts/report_marly.sh

generate:
	./scripts/generate_marly.sh
