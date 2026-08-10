# InsightKit — production image (on-prem, single binary container)
FROM python:3.11-slim AS build

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

# ---- runtime (slim, non-root) ----
FROM python:3.11-slim

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1

COPY --from=build /app/.venv ./.venv
COPY --from=build /app/src ./src
COPY --from=build /app/pyproject.toml ./pyproject.toml

# meta store location (mount a volume here to persist audit/cache/schema)
ENV INSIGHTKIT_STORAGE__PATH=/data
RUN mkdir -p /data && useradd -r -u 1001 insightkit && chown insightkit /data

USER insightkit
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)" || exit 1

CMD ["insightkit", "serve"]
