# Facify service image.
#
# One container serves the API (codexplan.md §4 — one deployable service, internal
# modules, not seven microservices). Runtime sizing is M49's concern: the default
# small memory allocation will not survive image processing plus two local ONNX
# models, so the deployment must request more than the platform default.

FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /build

# Dependency layer — cached until the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Application layer.
COPY app ./app
COPY migrations ./migrations
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.12-slim-bookworm AS runtime

# Non-root: the process never needs to write outside its own tmp.
RUN groupadd --system --gid 1001 facify \
    && useradd --system --uid 1001 --gid facify --create-home facify

WORKDIR /srv

COPY --from=builder --chown=facify:facify /build/.venv /srv/.venv
COPY --from=builder --chown=facify:facify /build/app /srv/app
COPY --from=builder --chown=facify:facify /build/migrations /srv/migrations

ENV PATH="/srv/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER facify

EXPOSE 8080

# Liveness is dependency-free by design (app/api/health.py): a provider outage must
# never make the platform think the container is dead.
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
