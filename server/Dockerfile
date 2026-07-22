# syntax=docker/dockerfile:1

# ============================================================================
# Client build — the React dashboard, built with bun.
# Follows https://bun.com/docs/guides/ecosystem/docker
# bun only lives in these stages; the runtime image below never ships node/bun.
# ============================================================================
FROM oven/bun:1 AS client-base
WORKDIR /usr/src/client

# install stage: cache dependencies in a temp dir so source edits don't refetch.
FROM client-base AS client-install
RUN mkdir -p /temp/dev
COPY app/client/package.json app/client/bun.lock /temp/dev/
RUN cd /temp/dev && bun install --frozen-lockfile

# build stage: bring in cached node_modules + source, emit the static dist.
FROM client-base AS client-build
COPY --from=client-install /temp/dev/node_modules node_modules
COPY app/client/ .
ENV NODE_ENV=production
RUN bun run build          # -> /usr/src/client/dist


# ============================================================================
# Server runtime — FastAPI, installed with uv.
# Follows https://docs.astral.sh/uv/guides/integration/docker/
# ============================================================================
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    DATABASE=/data/usage.db

WORKDIR /app

# Install dependencies in their own cached layer, using only the lockfiles
# (no project source yet) so code edits don't bust the dependency cache.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# App source, then the pre-built dashboard from the client stage.
COPY . .
COPY --from=client-build /usr/src/client/dist ./app/client/dist

# Install the project itself now that its source is present.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Put the venv on PATH so `fastapi` resolves without `uv run`.
ENV PATH="/app/.venv/bin:$PATH"

# Persist the SQLite DB outside the image layer.
RUN mkdir -p /data
VOLUME /data

EXPOSE 8000

CMD ["fastapi", "run", "app/main.py"]
