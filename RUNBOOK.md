# RUNBOOK — Driving Copilot on Google Cloud (e2-micro, always-free tier)

Production deployment for the Driving Copilot Telegram bot on a single Google Cloud
`e2-micro` VM. The bot uses **long polling** (`python-telegram-bot` v22,
`Application.run_polling`): it opens an outbound HTTPS connection to Telegram and
polls. **There are no inbound ports, no firewall rules to open, no domain, and no
TLS.** Outbound only.

Three services run under docker compose: `db` (PostgreSQL 17), `bot` (the app),
and `backup` (a nightly `pg_dump` sidecar). The 1 GB RAM VM is the binding
constraint: Postgres keeps its modest default config, and no other services are
added.

---

## 0. Preflight checklist (always-free tier)

Before creating the VM, confirm each line:

- [ ] **Machine type:** `e2-micro` (the only always-free-eligible type).
- [ ] **Region:** `us-central1` (or `us-west1` / `us-east1` — all three are
      always-free-eligible). Pick the one closest to Telegram's edge; latency
      only affects long-poll responsiveness, not correctness.
- [ ] **Boot disk:** Debian 12, **standard (not premium SSD)** persistent disk,
      **≤ 30 GB** (always-free disk cap). 10 GB is plenty for the OS + docker +
      Postgres + a week of small backups.
- [ ] **External IP:** **ephemeral** — do NOT provision a reserved static IP
      (that is a billable resource). An ephemeral IP is fine because the bot
      makes outbound connections; nothing dials in.
- [ ] **No load balancer.** No Cloud Load Balancing, no HTTP(S) LB, no
      forwarding rules. The bot has no published port.
- [ ] **No inbound firewall rules.** Default VPC default is fine; do not open
      any port for the bot. (The only open port you'll see is the VM's SSH/22,
      which Google manages.)
- [ ] **Always-free quota:** stay within the monthly `e2-micro` hours (the
      always-free tier covers one `e2-micro` in `us-central1`/`us-west1`/
      `us-east1` running 24/7). Check the billing budget alert at
      https://console.cloud.google.com/billing to avoid surprises.

**Note on the network path:** the bot connects *out* to `api.telegram.org` and
to `openrouter.ai`. The VM has a default route to the internet; no NAT gateway
needs to be configured on a default VPC. No inbound rules, no domain, no TLS.

---

## 1. Provision the VM

Google Cloud Console (https://console.cloud.google.com) → **Compute Engine →
VM instances → Create**.

- **Name:** `driving-copilot`
- **Region:** `us-central1` (zone `us-central1-a` is fine)
- **Machine type:** `e2-micro` (2 shared vCPU, 1 GB RAM)
- **Boot disk:** Debian 12 (bookworm), Standard persistent disk, 10 GB
- **Identity and API access → Access scopes:** allow default
- **Firewall:** leave both "Allow HTTP/HTTPS traffic" **unchecked** (we don't
  serve anything inbound)
- **External IP:** ephemeral (default)

Create the VM. Note the external IP for the SSH step.

Equivalent `gcloud`:

```bash
gcloud compute instances create driving-copilot \
    --zone=us-central1-a \
    --machine-type=e2-micro \
    --image-family=debian-12 \
    --image-project=debian-cloud \
    --boot-disk-size=10GB \
    --boot-disk-type=pd-standard \
    --no-service-account --no-scopes
```

SSH in from the Console (SSH button) or with `gcloud compute ssh driving-copilot`.

---

## 2. Install Docker and the compose plugin

Debian 12's docker.io is fine; the official repo gives a newer engine. Either
works. Using the official docker repo:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/debian bookworm stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add your user to the docker group so you don't need sudo for every command:
sudo usermod -aG docker $USER
newgrp docker

docker version
docker compose version
```

Confirm both `docker version` and `docker compose version` print.

---

## 3. Clone the (private) GitHub repo on the VM

The repo is private. Use a **deploy key** (read-only), not a personal access
token — a deploy key scopes access to one repo and is revocable.

On your laptop:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/driving-copilot-deploy -C "driving-copilot-deploy"
# Print the public key, add it to the GitHub repo: Settings → Deploy keys →
# Add deploy key (tick "Allow write access" only if the VM must push; it does not):
cat ~/.ssh/driving-copilot-deploy.pub
# Copy the private key to the VM (next step):
scp ~/.ssh/driving-copilot-deploy <user>@<VM-IP>:~/.ssh/driving-copilot-deploy
```

On the VM:

```bash
chmod 600 ~/.ssh/driving-copilot-deploy

cat >> ~/.ssh/config <<'EOF'
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/driving-copilot-deploy
  IdentitiesOnly yes
EOF

# Verify the deploy key authenticates:
ssh -T git@github.com   # expect: "Hi <org>/<repo>! You've successfully authenticated..."

git clone git@github.com:<org>/driving-copilot.git ~/driving-copilot
cd ~/driving-copilot
```

(If you used HTTPS with a PAT instead, `git clone
https://github.com/<org>/driving-copilot.git` and cache the PAT in the git
credential helper. A deploy key is preferred.)

---

## 4. Put `.env` on the VM

The `.env` file is **not** in the repo (`gitignore`'d). Transfer it from your
laptop with `scp`:

```bash
scp .env <user>@<VM-IP>:~/driving-copilot/.env
```

Required keys (see `.env.example`):

```
TELEGRAM_BOT_TOKEN=        # from BotFather
ALLOWED_CHAT_ID=           # your Telegram chat id (the only chat the bot answers)
LLM_API_KEY=               # the app's OWN OpenRouter key (NOT the env OPENROUTER_API_KEY)
LLM_BASE_URL=https://openrouter.ai/api/v1
ROUTER_MODEL=openai/gpt-4.1-mini
ANSWER_MODEL=mistralai/mistral-large-2512
EXAM_DATE=                 # YYYY-MM-DD, optional
TIMEZONE=Europe/Amsterdam
TAVILY_API_KEY=            # for the cbr.nl live web fallback (optional but recommended)
```

`DATABASE_URL` is **set by docker-compose.yml** (`db:5432`) and overrides
whatever `.env` ships for local dev. Don't set `DATABASE_URL` in `.env` on the
VM; the compose override is authoritative.

On the VM, verify the file is readable only by you:

```bash
chmod 600 .env
```

---

## 5. Build and start

```bash
cd ~/driving-copilot

# Validate: compose config + required .env keys present (names only).
make deploy-check           # or: scripts/deploy_check.sh

# Build the bot image and start all three services detached.
docker compose up -d --build
```

The first build pulls `python:3.14-slim` and `postgres:17` and installs the
deps via `uv sync --frozen`. On an e2-micro it takes a few minutes; subsequent
builds are cached.

The bot's entrypoint runs `alembic upgrade head` (idempotent — a no-op when
already at head) before starting `python -m app.main bot`. So every boot brings
the schema to the latest revision without a manual migrate step.

---

## 6. Verify the bot is up

```bash
# All three services should be Up:
docker compose ps

# Bot logs (structlog → stdout):
docker compose logs -f bot
```

You should see the bot start, connect to Telegram, and idle on long polling.

Then, **from your Telegram account** (the `ALLOWED_CHAT_ID`), send the bot
`/start`. It should reply with the welcome text. If it does not reply:

- `docker compose logs bot | grep -i ignored` — if you see
  `bot.ignored_foreign_chat`, the chat id in `.env` is wrong; the actual chat
  id is in that log line. Update `ALLOWED_CHAT_ID`, `docker compose restart bot`.
- If `LLM_API_KEY` is wrong, the first router call fails with 401 — check
  `docker compose logs bot`.

---

## 7. Update to a new version

```bash
cd ~/driving-copilot
git pull --ff-only
# Rebuild the image with the new code and recreate containers:
docker compose up -d --build

# If a migration was added, the bot's entrypoint runs `alembic upgrade head`
# on boot, so it applies automatically. To run migrations explicitly:
docker compose exec bot alembic upgrade head
```

The `alembic upgrade head` in the entrypoint is idempotent, so restarting the
bot at any time is safe.

---

## 8. Backups

The `backup` service is a sidecar (same `postgres:17` image as `db`) that wakes
once a day at **03:00 Europe/Amsterdam** (the container's `TZ`) and dumps the
database to a named volume `backups` mounted at `/backups`, keeping the last
7. The script is `docker/backup.sh`.

List the backups (from the host, via the backup container):

```bash
docker compose exec backup ls -lt /backups
```

Copy a backup to the host:

```bash
docker compose cp backup:/backups/driving-copilot-YYYYMMDD-030000.sql.gz ./
```

### Restore procedure

Restoring **overwrites** the live database. Practice on a scratch database
first (see "Test the restore" below).

1. Stop the bot so nothing writes while you restore:

   ```bash
   docker compose stop bot
   ```

2. Restore from inside the `backup` container (it has `psql` and
   `PGPASSWORD=app`):

   ```bash
   docker compose run --rm backup sh /restore.sh /backups/driving-copilot-YYYYMMDD-030000.sql.gz
   ```

   `docker/restore.sh` drops and recreates the `public` schema, then loads the
   dump with `ON_ERROR_STOP=1`. The bot's entrypoint runs `alembic upgrade head`
   on the next boot, so the restored schema is reconciled to the latest
   migration automatically.

3. Restart the bot:

   ```bash
   docker compose start bot
   docker compose logs -f bot
   ```

### From the host (without the backup container)

```bash
gunzip -c /path/to/driving_copilot-YYYYMMDD-030000.sql.gz | \
  PGPASSWORD=app psql -h localhost -p 5433 -U app driving_copilot
```

(`psql` must be installed on the host; on the VM: `sudo apt-get install -y
postgresql-client`.)

### Test the restore (against a scratch database)

Before relying on a restore, verify the round-trip on a scratch database. From
the repo root on your laptop (or the VM):

```bash
# 1. Create a scratch database on the same Postgres instance.
docker compose exec db psql -U app -d postgres -c 'CREATE DATABASE driving_copilot_restore_test;'

# 2. Restore the backup into the scratch db (override the target db name).
docker compose cp backup:/backups/driving_copilot-YYYYMMDD-030000.sql.gz /tmp/
gunzip -c /tmp/driving_copilot-YYYYMMDD-030000.sql.gz | \
  docker compose exec -T db psql -U app -d driving_copilot_restore_test

# 3. Spot-check: the sessions, skills, and lesson_notes counts should match.
docker compose exec db psql -U app -d driving_copilot_restore_test \
  -c 'select count(*) from sessions; select count(*) from skills; select count(*) from lesson_notes;'

# 4. Drop the scratch db.
docker compose exec db psql -U app -d postgres -c 'DROP DATABASE driving_copilot_restore_test;'
```

The automated test `tests/integration/test_backup_restore.py` exercises the same
round-trip against the test database: it dumps, restores into a scratch
database, and asserts the row counts match. Run it with the rest of the suite:

```bash
uv run pytest -q tests/integration/test_backup_restore.py
```

---

## 9. Reading logs

The bot uses `structlog` and writes to **stdout** (see `app/logging.py`). All
logs go through docker:

```bash
# Follow the bot's logs:
docker compose logs -f bot

# Last 200 lines, no follow:
docker compose logs --tail=200 bot

# Only warnings and above (structlog level field):
docker compose logs bot | grep -iE 'warning|error'

# The router eval log (jsonl, also mounted on the host at ./logs/):
docker compose exec bot tail -f /app/logs/router.jsonl
```

The `db` and `backup` services also log to stdout:

```bash
docker compose logs -f db
docker compose logs -f backup
```

---

## 10. Stop / restart / tear down

```bash
docker compose stop            # stop containers, keep data volumes
docker compose start            # start them again
docker compose restart bot      # just the bot (re-runs migrations on boot)
docker compose down             # stop + remove containers, KEEP volumes
docker compose down -v          # stop + remove containers AND pgdata/backups
                                # (NEVER run -v on the production box unless
                                #  you have a backup you have tested a restore from)
```

---

## 11. Common issues

| Symptom | Check |
|---|---|
| Bot starts, doesn't reply to `/start` | `docker compose logs bot \| grep ignored` → wrong `ALLOWED_CHAT_ID` |
| Router calls fail with 401 | `LLM_API_KEY` wrong or out of credit; check OpenRouter |
| `alembic upgrade head` fails on boot | usually `db` not healthy yet; `depends_on: service_healthy` should prevent this — check `docker compose ps db` |
| Backups not appearing | `docker compose logs backup` — the loop logs sleep + dump events; check the `backups` volume with `docker compose exec backup ls /backups` |
| VM out of memory | `docker stats`; the e2-micro has 1 GB — Postgres default config is modest; if the bot OOMs, check `docker compose logs bot` for MemoryError |
| Ephemeral IP changed after restart | expected; the bot's long-poll connection reconnects automatically. If a static hostname is needed, use a dynamic DNS updater — not required for the bot itself |
