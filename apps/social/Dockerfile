# Base manifests pinned on 2026-09-11; update deliberately with the lockfile audit.
FROM ghcr.io/astral-sh/uv:0.9.26@sha256:9a23023be68b2ed09750ae636228e903a54a05ea56ed03a934d00fe9fbeded4b AS uv
FROM python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285 AS build
COPY --from=uv /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable --compile-bytecode

FROM python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285
RUN groupadd --gid 10001 sugarglider && useradd --uid 10001 --gid 10001 --no-create-home sugarglider
RUN mkdir /data /backups && chown 10001:10001 /data /backups && chmod 700 /data /backups
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
WORKDIR /app
EXPOSE 8000
CMD ["python", "-m", "sugarglider.social_server", "serve", "--host", "0.0.0.0", "--trust-proxy"]
