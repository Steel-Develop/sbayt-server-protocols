# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.11.19 AS uv

FROM python:3.14-slim AS builder
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.14-slim
WORKDIR /app
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1
COPY --from=builder /opt/venv /opt/venv
USER 10001:10001
EXPOSE 4840
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import socket; socket.create_connection(('127.0.0.1', 4840), timeout=1).close()"
ENTRYPOINT ["python", "-m", "sbayt_opcua_server"]
