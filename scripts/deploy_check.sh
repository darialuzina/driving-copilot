#!/usr/bin/env sh
# Pre-deploy validation. Run from the repo root before `docker compose up -d`.
#
#   1. Validates the docker-compose config (compose config --quiet).
#   2. Checks that the required .env keys are present and non-empty
#      (delegates to scripts/check_env.sh; names only, values never printed).
#
# Exit non-zero on any failure so it can gate a deploy.
set -eu

cd "$(dirname "$0")/.."

status=0

echo "deploy-check: validating docker-compose config"
if ! docker compose config --quiet; then
    echo "deploy-check: compose config invalid" >&2
    status=1
fi

echo "deploy-check: checking required .env keys"
if ! scripts/check_env.sh; then
    status=1
fi

if [ "$status" -eq 0 ]; then
    echo "deploy-check: OK"
else
    echo "deploy-check: FAILED — fix the issues above before deploying" >&2
fi
exit "$status"
