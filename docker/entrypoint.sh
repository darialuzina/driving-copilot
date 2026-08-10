#!/usr/bin/env sh
# Bot container entrypoint.
#
# Runs `alembic upgrade head` (idempotent: a no-op when already at head) before
# starting the bot, so every boot brings the schema to the latest revision without
# a separate migrate service. Then execs the bot so it becomes PID 1's child
# under tini and receives SIGTERM cleanly on `docker stop`.
#
# Usage: entrypoint.sh [bot]
set -eu

cd /app

echo "entrypoint: running alembic upgrade head"
alembic upgrade head

echo "entrypoint: starting bot"
exec python -m app.main bot
