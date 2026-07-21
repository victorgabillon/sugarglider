FROM ghcr.io/astral-sh/uv:0.9.26 AS uv
FROM python:3.13-slim

COPY --from=uv /uv /uvx /bin/
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY scripts/migrate_plan_json.py ./scripts/migrate_plan_json.py
COPY src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "sugarglider.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
