# Backend image for the hosted deployment (see docs/exec-plans/active/0017-aws-deployment.md).
# Build for the t4g (arm64) instance: docker buildx build --platform linux/arm64 .
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock .python-version alembic.ini ./
COPY packages/core packages/core
COPY apps/server apps/server
RUN uv sync --frozen --no-dev --package soft-floyd-server

FROM python:3.12-slim-bookworm
RUN useradd --create-home --uid 1000 floyd && mkdir /data && chown floyd /data
WORKDIR /app
COPY --from=build --chown=floyd /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    SOFT_FLOYD_DB_PATH=/data/soft-floyd-accounts.db \
    SOFT_FLOYD_FIT_DIR=/data/fit \
    SOFT_FLOYD_GARMIN_TOKEN_DIR=/data/garmin \
    PYTHONUNBUFFERED=1
USER floyd
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1
CMD ["soft-floyd", "serve", "--host", "0.0.0.0", "--port", "8000"]
