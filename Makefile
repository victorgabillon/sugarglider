.PHONY: install format lint typecheck test check brand-assets download-osm nature-index poi-index benchmark-pois up down logs smoke report generate generate-all-pois generate-auto-tour

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

brand-assets:
	uv run python scripts/sync_web_brand_assets.py

download-osm:
	./scripts/download_osm.sh

nature-index:
	./scripts/build_nature_index.sh

poi-index:
	./scripts/build_poi_index.sh

benchmark-pois:
	uv run python scripts/benchmark_poi_index.py

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

generate-auto-tour:
	./scripts/generate_marly_auto_tour.sh
