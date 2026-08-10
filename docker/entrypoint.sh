#!/usr/bin/env sh
# Bot container entrypoint.
#
# Default (no args): runs `alembic upgrade head` (idempotent: a no-op when
# already at head) before starting the bot, so every boot brings the schema to
# the latest revision without a separate migrate service. Then execs the bot so
# it becomes PID 1's child under tini and receives SIGTERM cleanly on
# `docker stop`.
#
# With args (e.g. `compose run bot sh`, `compose run bot alembic downgrade -1`):
# execs the given command directly. This is why a one-off command must NOT also
# start the bot polling loop — two pollers hit Telegram's 409 conflict.
#
# Usage: entrypoint.sh            # default: migrate + start bot
#        entrypoint.sh <cmd> ...  # exec <cmd> (migrations NOT run)
set -eu

cd /app

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

echo "entrypoint: running alembic upgrade head"
alembic upgrade head

echo "entrypoint: starting bot"
exec python -m app.main bot
