#!/usr/bin/env sh
# Restore a backup into the driving-copilot database.
#
# Usage:
#   docker compose exec backup sh /restore.sh /backups/driving_copilot-20260811-030000.sql.gz
#
# Or from the host (the db is reachable on the published port):
#   gunzip -c /backups/driving_copilot-*.sql.gz | \
#     PGPASSWORD=app psql -h localhost -p 5433 -U app driving_copilot
#
# This script is intended to run inside the `backup` container (it has psql
# and PGPASSWORD set). It drops and recreates the public schema, then loads
# the dump. It is destructive — only run it against the target you intend to
# overwrite. Practice the restore on a scratch db first (see RUNBOOK.md).
set -eu

DB_HOST=db
DB_USER=app
DB_NAME=driving_copilot

if [ "$#" -lt 1 ]; then
    echo "usage: $0 <backup-file.sql.gz>" >&2
    exit 2
fi

file=$1
if [ ! -f "$file" ]; then
    echo "restore: file not found: $file" >&2
    exit 1
fi

echo "restore: dropping and recreating schema in $DB_NAME from $file"
echo "restore: THIS IS DESTRUCTIVE — Ctrl-C now to abort"; sleep 3

# Drop and recreate the public schema so the restore is a clean overwrite.
# --no-owner --no-privileges in backup.sh makes this safe across roles.
psql --host="$DB_HOST" --username="$DB_USER" --dbname="$DB_NAME" \
    --command="DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

gunzip -c "$file" | psql --host="$DB_HOST" --username="$DB_USER" --dbname="$DB_NAME" -v ON_ERROR_STOP=1

echo "restore: done. Run 'alembic upgrade head' (the bot entrypoint does this on boot)"
echo "restore: then restart the bot: docker compose restart bot"
