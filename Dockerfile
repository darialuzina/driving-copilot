# Driving Copilot bot image.
# Python 3.14 slim + uv (frozen lockfile, no dev deps). Runs as a non-root user;
# structlog writes to stdout (see app/logging.py), so container logs go to stdout.
#
# Build:  docker build -t driving-copilot .
# Run:    docker compose up -d   (see docker-compose.yml)

# --- build stage -------------------------------------------------------------
# uv's official image bundles uv and bootstraps a CPython toolchain via python-build-standalone.
# We pin the Python version explicitly so the image's interpreter matches pyproject.toml.
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS build

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install deps first (layer cache: source changes don't invalidate the install).
# --frozen: never touch the lockfile; --no-dev: production deps only.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy the application, migrations, knowledge base and fixtures.
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini ./
COPY knowledge/ knowledge/
COPY fixtures/ fixtures/

# Install the project itself into the now-resolved venv.
RUN uv sync --frozen --no-dev

# --- runtime stage -----------------------------------------------------------
FROM python:3.14-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Europe/Amsterdam \
    PATH="/app/.venv/bin:$PATH"

# A non-root user runs the bot. The app writes nothing to the filesystem except
# logs (stdout) and the router jsonl (mounted or ephemeral); no root needed.
RUN groupadd --system --gid 1001 app && \
    useradd --system --uid 1001 --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app

# tini: a tiny init that reaps zombies and forwards signals so the bot shuts down
# cleanly on `docker stop` (python-telegram-bot's run_polling handles SIGINT/SIGTERM).
# tzdata: the TZ env var above resolves through /usr/share/zoneinfo.
# postgresql-client: NOT installed — the bot talks to Postgres over TCP only.
RUN apt-get update && \
    apt-get install -y --no-install-recommends tini tzdata && \
    rm -rf /var/lib/apt/lists/*

COPY --from=build --chown=app:app /app /app

# The bot writes its router eval log to logs/router.jsonl (see app/config.py).
# Create it owned by the app user so the non-root process can append to it;
# compose mounts a named volume here so eval data survives image rebuilds.
RUN mkdir -p /app/logs && chown -R app:app /app/logs

USER app

# Logs go to stdout (structlog ConsoleRenderer -> stdout, see app/logging.py).
# The entrypoint runs Alembic migrations idempotently, then starts the bot.
COPY --chown=app:app docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/usr/bin/tini", "--", "/app/entrypoint.sh"]
# No CMD: the entrypoint defaults to "migrate + start bot" when no args are
# given, and execs any args directly (compose run bot <cmd>).
