#!/usr/bin/env sh
# Check that required .env keys are present and non-empty.
#
# Prints key NAMES only — never values. Exits non-zero if any required key is
# missing or empty. Used by scripts/deploy_check.sh and safe to run on its own.
#
#   scripts/check_env.sh [path/to/.env]
set -eu

cd "$(dirname "$0")/.."

ENV_FILE="${1:-.env}"

# Keys the bot cannot run without. Keys with safe defaults are not listed.
REQUIRED_ENV_KEYS="TELEGRAM_BOT_TOKEN ALLOWED_CHAT_ID LLM_API_KEY"

status=0

if [ ! -f "$ENV_FILE" ]; then
    echo "check-env: $ENV_FILE not found (copy .env.example and fill it in)" >&2
    exit 1
fi

echo "check-env: checking required keys in $ENV_FILE (names only, values never printed)"
for key in $REQUIRED_ENV_KEYS; do
    # A non-comment, non-empty assignment. We match the key name and require a
    # non-whitespace value; we never print the value, only the key name.
    if grep -Eq "^[[:space:]]*${key}[[:space:]]*=[[:space:]]*[^[:space:]]" "$ENV_FILE"; then
        echo "check-env: ${key} present"
    else
        echo "check-env: ${key} MISSING or empty" >&2
        status=1
    fi
done

if [ "$status" -eq 0 ]; then
    echo "check-env: OK"
else
    echo "check-env: FAILED — fill in the missing keys above" >&2
fi
exit "$status"
