# Small, reproducible image: deps from uv.lock, non-root user.
FROM python:3.15-slim AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app

# Dependencies first so this layer is cached when only code changes.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY data ./data
RUN uv sync --frozen --no-dev

RUN useradd --create-home meridian
USER meridian
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT []
CMD ["meridian", "--help"]
