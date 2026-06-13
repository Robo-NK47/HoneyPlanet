# syntax=docker/dockerfile:1

###############################################################################
# Builder stage — install the package + runtime extras into an isolated venv.
# Kept separate so build toolchains never land in the final image.
###############################################################################
FROM python:3.11-slim AS builder

# Fail fast, no .pyc clutter, unbuffered logs, no pip version chatter.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Self-contained virtualenv we can copy wholesale into the runtime stage.
ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app

# --- Layer-caching: dependency metadata first, source later. -----------------
# Copy ONLY pyproject (+ README, referenced by [project].readme) so the heavy
# dependency-install layer is reused on every build where deps are unchanged.
# A minimal package skeleton lets the build backend resolve without the source.
COPY pyproject.toml README.md ./
RUN mkdir -p src/trip_planner \
    && printf '__version__ = "0.0.0"\n' > src/trip_planner/__init__.py

# Install base deps + the 'llm' extra ONLY.
#   llm -> anthropic, openai, ddgs : on the /chat request path.
#          - openai: hard-imported at module load in chat/agent.py (the AsyncOpenAI
#            client is constructed at import), so the app FAILS TO IMPORT without it.
#          - anthropic: used by agents/shared.py (hotel/transport/budget experts).
#          - ddgs: lazily imported inside the web_search tool.
# Deliberately EXCLUDED to keep the image small — imported only by offline
# data-prep scripts (ingest/, scripts/), never on a request path:
#   ingest -> trafilatura, beautifulsoup4, selectolax
#   geo    -> googlemaps
#   graph  -> graphifyy
#   dev    -> pytest, ruff, mypy
# geoalchemy2 is a BASE dependency, so PostGIS model support ships regardless.
RUN pip install ".[llm]"

# Now copy the real source and (re)install so the installed package matches it.
# This overwrites the 0.0.0 stub __init__.py with the real package.
# Isolated in its own layer => editing code never busts the dependency layer.
COPY src/ ./src/
RUN pip install --no-deps .

###############################################################################
# Runtime stage — slim, non-root, just the venv + app code.
###############################################################################
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Create an unprivileged user/group to run the server as.
RUN groupadd --system app \
    && useradd --system --gid app --no-create-home --home-dir /app app

WORKDIR /app

# Bring over the fully-populated virtualenv from the builder.
COPY --from=builder /opt/venv /opt/venv

# Application code + the migration assets so `alembic upgrade head` can run as
# the Fly [deploy].release_command (NOT in CMD; migrations must not race boot
# or run once per replica).
COPY --chown=app:app src/ ./src/
COPY --chown=app:app migrations/ ./migrations/
COPY --chown=app:app alembic.ini ./alembic.ini

# Make /app (also HOME) writable by the non-root user so anything touching HOME
# or a relative cache dir won't hit EACCES.
RUN chown app:app /app

ENV PYTHONPATH="/app/src" \
    HOME=/app

USER app

EXPOSE 8000

# Liveness probe against the DB-free /health endpoint, using stdlib urllib (the
# slim image has no curl/wget). Any error or non-200 => exit 1 => unhealthy.
# NOTE: Fly.io ignores this and uses [[http_service.checks]]; this helps
# docker/compose and other runtimes.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status==200 else 1)" || exit 1

# Production server: no --reload, bound to all interfaces, fixed port.
CMD ["uvicorn", "trip_planner.main:app", "--host", "0.0.0.0", "--port", "8000"]
