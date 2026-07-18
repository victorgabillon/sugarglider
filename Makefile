.PHONY: install format lint typecheck test check download-osm nature-index up down logs smoke report generate generate-all-pois

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

nature-index:
	./scripts/build_nature_index.sh

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

generate-all-pois:
	./scripts/generate_marly_all_pois.sh
