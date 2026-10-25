FROM ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv
FROM python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && test -s /etc/ssl/certs/ca-certificates.crt
COPY --from=uv /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY app ./app
RUN uv sync --frozen --no-dev --no-editable \
    && groupadd --gid 10001 ledger \
    && useradd --uid 10001 --gid 10001 --no-create-home ledger
COPY alembic.ini ./
COPY alembic ./alembic
ENV PATH="/app/.venv/bin:$PATH"
USER ledger
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8080') + '/actuator/health/readiness', timeout=4)"
CMD ["python", "-m", "app.start"]
