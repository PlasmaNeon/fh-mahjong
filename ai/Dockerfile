# Python policy server (serve_policy.py) for the private-room RL agent.
#
# IMPORTANT: the model checkpoint is NOT baked into this image — the manifest in
# the repo only references training-box paths. Provide a real .pt file at runtime
# via a mounted volume and pass --checkpoint (see docker-compose.yml).
#
# Build context is the repo root: `docker build -f ai/Dockerfile .`
FROM python:3.12-slim

# uv for reproducible installs straight from ai/uv.lock.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/ai/.venv

WORKDIR /app/ai

# Dependency layer first (cached until pyproject/lock change). --no-install-project
# installs third-party deps (torch, numpy, protobuf, mlflow) without the package.
COPY ai/pyproject.toml ai/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Project source (code, generated proto bindings, checkpoint manifest).
COPY ai/ ./
RUN uv sync --frozen --no-dev

EXPOSE 8765

# --host/--port are fixed here; --manifest and --checkpoint are supplied by the
# compose `command:` so the served weights come from the mounted volume.
ENTRYPOINT ["uv", "run", "--no-sync", "fh-mj-serve-policy", "--host", "0.0.0.0", "--port", "8765"]
