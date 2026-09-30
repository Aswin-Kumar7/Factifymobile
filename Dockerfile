# Factify service image.
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
# With the `models` extra: the detectors, readers and speech-to-text that run on our
# own server (PyTorch CPU wheels only, see [tool.uv.sources]). Their weights are not
# in the image; they are mounted at /srv/models (docs/deployment-azure.md).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --extra models

# Application layer.
COPY app ./app
COPY migrations ./migrations
# The feed registry is data, not code: load_registry() reads /srv/data/feeds.json
# and raises without it, so omitting this directory makes the container crash on
# the first ingestion tick rather than at build time.
COPY data ./data
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra models


FROM python:3.12-slim-bookworm AS runtime

# ffmpeg for the video keyframe path (M35). Without it KeyframeExtractor reports
# itself unavailable and every video abstains — honest, but silently useless.
# --no-install-recommends keeps this to the codecs rather than a desktop stack.
# libgl1 and libglib2.0-0: OpenCV (face finding, text in pictures) links against them.
RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Non-root: the process never needs to write outside its own tmp.
# /srv/.models is created here because /srv belongs to root: the pre-warm below runs
# as factify and could not create it (the step is allowed to fail, so the image was
# built without the weights and the first request fell over on the same error).
RUN groupadd --system --gid 1001 factify \
    && useradd --system --uid 1001 --gid factify --create-home factify \
    && mkdir -p /srv/.models && chown factify:factify /srv/.models

WORKDIR /srv

COPY --from=builder --chown=factify:factify /build/.venv /srv/.venv
COPY --from=builder --chown=factify:factify /build/app /srv/app
COPY --from=builder --chown=factify:factify /build/migrations /srv/migrations

ENV PATH="/srv/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FACTIFY_LOCAL__DIRECTORY=/srv/models

COPY --from=builder --chown=factify:factify /build/data /srv/data

USER factify

# Local model weights, baked in at build time rather than downloaded on first use.
#
# fastembed fetches ~21s of text weights and ~15s of image weights the first time
# it runs. On a scale-to-zero container that lands on the first user request, which
# collides directly with the 3-8 second latency target — the one request most likely
# to be a judge's. Paying it here makes the image larger and the cold start honest.
ENV FASTEMBED_CACHE_PATH=/srv/.models
RUN python -c "from fastembed import TextEmbedding, ImageEmbedding; TextEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', cache_dir='/srv/.models'); ImageEmbedding('Qdrant/clip-ViT-B-32-vision', cache_dir='/srv/.models')"     || echo "model pre-warm skipped; first request will pay the download"

EXPOSE 8080

# Liveness is dependency-free by design (app/api/health.py): a provider outage must
# never make the platform think the container is dead.
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).status==200 else 1)"

# Idle connections kept 75 s (uvicorn: 5): the app reuses its connection.
# `python -m`: the venv was built in /build, so its uvicorn script's first line
# names /build/.venv/bin/python, which this image does not have.
CMD ["python", "-m", "uvicorn","app.main:app", "--host", "0.0.0.0", "--port", "8080", "--timeout-keep-alive", "75"]
