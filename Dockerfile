# OVERRIDE — multi-stage container image (v6 plan task 3.1)
#
# Single image, two stages: a Node builder for the React/Vite UI, a Python
# runtime serving the FastAPI API + the built UI as static files at :8000.
# One image means `podman compose up` brings up exactly one OVERRIDE service
# without the proxy/static-server complexity of an API+UI split.
#
# Build conventions:
#   * docker.io/* image refs are mandatory under rootless Podman (gotcha #7);
#     unprefixed `node:20-alpine` fails to resolve outside Docker Desktop.
#   * Stage 2 starts from python:3.12-slim (gotcha #5 — slim lacks
#     gcc/g++/headers needed for pyarrow/docling wheels; the build-essential
#     install below covers that, then we apt clean to keep the layer small).
#   * No SECRETS in build args. WATSONX_API_KEY, OVERRIDE_OLLAMA_BASE_URL,
#     OVERRIDE_LLM_RUNTIME come from .env at runtime via `env_file:` in
#     docker-compose.yml, never baked into a layer.

# ──────────────────────────────────────────────────────────────────────────────
# Stage 1 — UI build (Node 20 alpine, small)
# ──────────────────────────────────────────────────────────────────────────────

FROM docker.io/node:20-alpine AS ui-builder

WORKDIR /build

# Copy ONLY the dependency manifests first so Docker/Podman can cache the
# `npm ci` layer when sources change but deps don't.
COPY ui/package.json ui/package-lock.json ./
RUN npm ci --no-audit --no-fund

# Copy fixture JSONs the UI imports via the @fixtures Vite alias.
# vite.config.ts has `@fixtures → path.resolve(__dirname, "..", "tests",
# "fixtures")` so `ui/src/api/client.ts` resolves `@fixtures/*.json` to
# `tests/fixtures/*.json` at the REPO root — that path is outside the
# `ui/` subtree and needs an explicit COPY into the build stage. The
# image-internal layout matches the repo layout so the alias keeps
# working: ui/ at WORKDIR's depth, tests/fixtures/ one up. tsbuildinfo
# is sensitive to file mtime; copying after package.json keeps the
# layer-cache hit ratio high.
WORKDIR /
COPY tests/fixtures/ ./tests/fixtures/
WORKDIR /build

# Now copy the rest of the UI source + build.
COPY ui/ ./
# Vite reads .env.production by default during `vite build`; we don't ship
# one — the runtime serves /api/* paths to the same origin so no API target
# rewriting is needed.
RUN npm run build


# ──────────────────────────────────────────────────────────────────────────────
# Stage 2 — Python runtime (FastAPI + uvicorn + static UI)
# ──────────────────────────────────────────────────────────────────────────────

FROM docker.io/python:3.12-slim AS runtime

# Install build deps for pyarrow / docling / other native-extension wheels
# that don't ship as manylinux on Python 3.12 yet. Clean apt cache in the
# same layer to keep image size down.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Same dep-cache pattern as Stage 1: copy requirements first.
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Application source. Keep this ordered by likelihood-of-change (rarely
# touched files first) for layer-cache friendliness.
COPY models.json ./
COPY core/ ./core/
COPY ingest/ ./ingest/
COPY analysis/ ./analysis/
COPY copilot/ ./copilot/
COPY api/ ./api/
COPY torcs_driver_profiles.py ./
COPY config/torcs_driver_profiles/ ./config/torcs_driver_profiles/
COPY RaceYourCode/gym_torcs/driver_config_contract.py ./RaceYourCode/gym_torcs/driver_config_contract.py
COPY prompts/ ./prompts/
COPY guardian/ ./guardian/
COPY data/regs/extracted_chunks.sample.json ./data/regs/extracted_chunks.sample.json

# Built UI from Stage 1.
COPY --from=ui-builder /build/dist ./ui/dist

# Runtime config — DOES NOT bake any secret. SESSIONS_DIR points inside the
# image; compose mounts a host volume on top via `volumes:` so sessions
# persist across container restarts.
ENV SESSIONS_DIR=/app/data/sessions \
    OVERRIDE_CHUNKS_PATH=/app/data/regs/extracted_chunks.sample.json \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Healthcheck per docs/04-api.md §8 — container marked healthy once
# uvicorn serves /api/health.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

EXPOSE 8000

# uvicorn binds 0.0.0.0 inside the container; compose maps host :8000 → 8000.
# api/main.py mounts ui/dist via StaticFiles so /api/* and /assets/*
# coexist on the same origin without a separate proxy.
ENTRYPOINT ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
