#!/usr/bin/env sh
# Nightly backup loop for the driving-copilot database.
#
# Runs inside the `backup` service (postgres:17 image, so pg_dump's major
# version matches db). Wakes once a day at 03:00 Europe/Amsterdam (the
# container's TZ env var is set in docker-compose.yml), dumps the database
# to /backups, and prunes to the most recent 7 dumps.
#
# Restore procedure: see docker/restore.sh and RUNBOOK.md.
set -eu

BACKUP_DIR=/backups
DB_HOST=db
DB_USER=app
DB_NAME=driving_copilot
KEEP=7

mkdir -p "$BACKUP_DIR"

echo "backup: starting loop; will dump $DB_NAME@$DB_HOST daily at 03:00 $TZ (keep last $KEEP)"

while true; do
    # Seconds until the next 03:00 local (container TZ is Europe/Amsterdam).
    # GNU date (Debian-based postgres image) understands relative specs.
    now=$(date +%s)
    target=$(date -d 'today 03:00' +%s)
    if [ "$target" -le "$now" ]; then
        target=$(date -d 'tomorrow 03:00' +%s)
    fi
    wait_s=$((target - now))
    echo "backup: sleeping ${wait_s}s until next 03:00"
    sleep "$wait_s"

    ts=$(date +%Y%m%d-%H%M%S)
    file="$BACKUP_DIR/driving_copilot-${ts}.sql.gz"
    echo "backup: dumping to $file"
    # --no-owner --no-privileges: restore works on a fresh db without role mismatch.
    pg_dump --host="$DB_HOST" --username="$DB_USER" --no-owner --no-privileges \
        --dbname="$DB_NAME" | gzip >"$file"

    # Keep the newest $KEEP, remove the rest. ls -t sorts by mtime; tail -n +K+1
    # skips the first K lines. xargs -r never runs rm with no input.
    retained=$(ls -1t "$BACKUP_DIR"/driving_copilot-*.sql.gz 2>/dev/null || true)
    if [ -n "$retained" ]; then
        echo "$retained" | tail -n +$((KEEP + 1)) | while IFS= read -r old; do
            [ -n "$old" ] && rm -f "$old" && echo "backup: pruned $old"
        done
    fi
done
