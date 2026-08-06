# Data Engineering Standards

Standard for data-engineering components: ETL applications, Airflow DAGs, Kafka workers, loading data into ClickHouse, exporting from ClickHouse to S3. Supplements the general standards (`python-standards.md`, `error-handling.md`, `logging.md`, `testing.md`, `database.md`), it does not replace them. Wherever data-engineering code diverges from web-service code (FastAPI/async), the divergences are spelled out explicitly below.

The style reference is the already-working ingest application of your ETL monorepo: the pair "CLI application (`docker_apps/<app>/`) + its DAG (`dags/<app>/`)". New components copy its patterns.

***

## §0. When this standard applies

- Batch CLI applications launched by Airflow via `KubernetesPodOperator`.
- Airflow DAGs.
- Kafka workers (consumer/producer).
- Loading data into ClickHouse and exporting from it (incl. to S3/OBS).
- Any code that moves data between sources (S3, Kafka, CH, Postgres) rather than serving HTTP requests.

For HTTP services (FastAPI) — the general `python-standards.md`.

***

## §1. How batch code differs from web-service code (important)

`python-standards.md` is written for an async FastAPI service. Data-engineering batch code deliberately deviates from it on three points:

| Aspect | Web service (python-standards) | Data-engineering batch |
|---|---|---|
| I/O | async (`httpx.AsyncClient`, `AsyncSession`) | **synchronous** (`clickhouse_connect`, `boto3`, `psycopg`) — the pod lives for a single task, no event loop needed |
| Parallelism | `asyncio.TaskGroup` | `multiprocessing` (see `runtime.resolve_workers`) for CPU/IO-bound file processing |
| Logging | `structlog` | stdlib `logging` (`logging.basicConfig` once at startup) |
| Config | `pydantic-settings` | `pydantic-settings` (same) |

**Universal rules always apply** (from `python-standards.md`): type annotations everywhere, `from __future__ import annotations`, no `except Exception: pass`, no mutable defaults, magic numbers extracted to constants, DTO/dataclass instead of `dict` at boundaries, fail-fast on broken configuration, parameterized SQL, no secrets in logs, Google-style docstrings in English (see `AGENTS.md`).

### §1.1 Relationship to existing standards (what does NOT apply to batch)

Some rules in `python-standards.md` / `database.md` / `testing.md` are written for an async FastAPI service with Postgres. They **do not contradict** this standard — they simply belong to a different component type and do not apply to batch code. To avoid ambiguity:

| Rule in existing standards | Where | Applies to batch data-eng? |
|---|---|---|
| Async rule: everything `async def`, `AsyncSession`, no sync `requests`/`psycopg` | python-standards §5 | **No.** It concerns a web service with an event loop. A batch pod lives for a single task — synchronous `clickhouse_connect`/`boto3`/`psycopg` are correct. |
| `structlog` for services | python-standards §13, logging.md | **Partially.** For a long-lived service with request context — `structlog`. For a batch CLI — stdlib `logging` (as in the reference ingest application). The rules "kwargs, not f-strings" and "do not log secrets" apply in both. |
| SQLAlchemy 2.0 async + Alembic, repository pattern, AsyncSession | database.md, python-standards §11 | **No, for ClickHouse/Kafka/S3.** database.md governs the service's Postgres DB. CH access — `clickhouse_connect`, DDL — via separate scripts/migrations, not Alembic. If a batch app touches the service's Postgres, database.md applies there. |
| Tests `async def` + `httpx.AsyncClient` + `ASGITransport` | testing.md | **No.** Batch tests are synchronous (there are no async handlers). The rest of testing.md (pytest, Fakes instead of mocks, no `unittest.TestCase`) — we follow. |
| Toolchain `uv run ruff` + `basedpyright` + pre-commit with ruff | python-standards §5, feature.md | **Per the actual repo.** In legacy ETL repositories pre-commit is usually built on `black`/`isort`/`flake8`/`mypy`/`bandit`/`pycln` (not ruff/basedpyright/uv). Follow the target repo's toolchain, see §11. |

If a real conflict of rules arises (not just separation by component type) — act per `error-handling.md` (Identify → Assess → Communicate); do not stay silent.

***

## §2. Application structure (CLI)

The canon is the reference ingest application. One image, the mode is selected via a CLI argument.

```
docker_apps/<app_name>/
├── __main__.py            # entry point: from <app>.cli import main; main()
├── cli.py                 # argparse, --ingest/--export/--source, dispatch
├── app.py                 # run_<mode>(name): dispatcher over modes
├── settings.py            # pydantic-settings, nested models
├── const.py               # named constants (magic numbers go here)
├── runtime.py             # resolve_workers and other runtime utilities
├── clients/               # clickhouse.py, s3.py, postgres.py — thin factories
├── ingest|export/         # business logic of the modes
├── storage/               # checkpoint/watermark, batch insert, txt sink
├── dto.py                 # frozen dataclasses for boundaries
├── Dockerfile
├── requirements.txt
├── version.txt            # semver, starts at 0.0.1
└── README.md              # what it does, list of ENV vars, how to run
```

Layers: `cli → app → ingest/export → clients/storage`. No business logic in `cli.py`. Clients (`clients/*.py`) are thin factories (create a client from settings), no logic.

***

## §3. Settings (pydantic-settings)

The canon is the reference application's `settings.py`. **Everything is parameterized, nothing is hardcoded.**

Rules:

1. `pydantic-settings` `BaseSettings`, `env_nested_delimiter="__"`, `case_sensitive=False`, `extra="ignore"`, `env_file=".env"`.
2. Nested models for each source/subsystem: `settings.clickhouse.host` is read from `CLICKHOUSE__HOST`.
3. **An empty string from ENV/GUI = "not set".** Coerce via `BeforeValidator` (the `empty_str_to_none` / `OptionalEnvInt` pattern in the reference). Do not use an empty string as a semantic sentinel — for "all/default" introduce an explicit token (e.g. `__all__`).
4. Secrets (passwords, keys, tokens) — only from ENV (on servers — from a k8s Secret), default `""`/`None`; they do not live in code/config/git (`security.md`).
5. **Fail fast:** if a required value is missing (CH host, S3 creds), crash at startup with a clear message; do not limp along "somehow".
6. Target names of tables/topics/buckets — **in settings**, not in code: they get renamed, and a rename must not require rebuilding the image.
7. Limits (batch size, file size, workers, timeouts) — named settings fields or constants in `const.py`, no magic numbers.

***

## §4. Airflow DAGs

The canon is the reference application's DAG. Rules (a digest of: the monorepo reference + the team's adopted "DAG working rules"):

### §4.1 Naming and structure

- **DAG file name = DAG ID** (or as close as possible — for generated DAGs). Makes searching easier.
- Do **not** put the word "DAG" in the DAG name — its location already makes that clear.
- One DAG — a task per source/entity (`KubernetesPodOperator` with different `--source`/`--ingest`). Dependencies — via `chain()`.

### §4.2 DAG configuration via Pydantic (mandatory)

- **Connection parameters** (host/connection metadata) of each DAG — in **separate variables** (Airflow Variable or k8s Secret depending on the installation), so a host change updates them for all DAGs at once.
- **The DAG's remaining variables** are defined via a **Pydantic config class** in the `dags_conf/` directory.
  - Class name = DAG name + suffix `_conf` (e.g. `aggregate_gamification_data_conf` for `dag_aggregate_gamification_data`).
  - Value storage — Airflow Variable (JSON) **or** k8s Secret + ENV (as in the reference application), depending on the project's Airflow installation.
  - Config initialization — in the first lines of the DAG code, **right after the imports**.
  - New values are added to the Variable/Secret within the task branch's MR.
- If a new DAG's config is Pydantic-based — add comments to the source and a link in the docs.

### §4.3 Keep the DAG top level clean

- **Do not use `Variable.get()` or heavy imports at the top level** of the DAG file.
- All `Variable.get()` calls — inside functions/operators.
- At the top level — only the imports the DAG itself needs. Heavy libraries (`pandas`) and custom modules — **lazy-import inside functions/operators**. Top-level code runs on every scheduler parse of the DAG — it must be lightweight.

### §4.4 Operator parameters

- `KubernetesPodOperator` with `image`, `secrets=[Secret("env", ENV, "<k8s-secret>", key)]`, `env_vars=[V1EnvVar("RUN_ID", "{{ run_id }}")]`, `on_finish_action="delete_pod"`, `in_cluster=True`.
- `max_active_runs=1`, `catchup=False`, an explicit `execution_timeout`.
- `schedule`: `None` if triggered externally; a cron string if interval-based. Sub-minute intervals are unreachable with cron — for frequencies < 1 min, loop inside the pod with a configurable pause.

### §4.5 Evolution

- We deliberately do **not** rewrite existing DAGs. When touching one — also bring its variable/import handling up to this standard.

***

## §5. ClickHouse

- Client — `clickhouse_connect` (`clients/clickhouse.py`, `get_client(**client_params)`).
- **SQL is parameterized only** (`{name:Type}`), no f-strings with values (`security.md`, python-standards §11). Identifiers (table names from trusted config) may be interpolated via f-string; values — never.
- **Read large result sets as a stream** (`query_row_block_stream` / block iteration). Do not load millions of rows into a list — the pod's memory is limited, and the CH server has a memory limit.
- **Insert in batches** (`client.insert(table, data, column_names)`), batch size from settings (`batch_size`, default 100k). Accumulate a batch → flush → clear.
- Source-read idempotency: either a file checkpoint (by `object_key`) or a time watermark (by window time). Advance the cursor **only after** the result has been written successfully.
- **Time for CH is aware-UTC, not naive.** `clickhouse_connect` treats a **naive** `datetime` (in `{x:DateTime}` parameters and in `client.insert`) as the pod's local time and converts to UTC; `DateTime` columns are read/written as naive UTC. On a pod not in UTC this produces a shift (e.g. MSK → −3 h) — window/watermark filters on `uploaded_time` silently miss the data. Therefore: `datetime.now(timezone.utc)`, when reading from CH convert naive→aware (`dt.replace(tzinfo=timezone.utc)`), pass aware-UTC into parameters/insert (or `'YYYY-MM-DD HH:MM:SS'` strings). Applies to any range/window logic.
- Partitioning/skip-index: window queries on a non-key column (`uploaded_time`) require a skip index, otherwise a full partition scan. The index is a launch precondition (pre-flight), not application code.
- DDL and partition cleanup — as separate steps/scripts, not from the application "on the fly".

***

## §6. S3 / OBS

- Client — `boto3` (`clients/s3.py`). `addressing_style` — **a setting, not hardcoded**: for OBS it must be `virtual` (bucket requests do not work without it), for local MinIO on localhost — `path` (`virtual` does not resolve there and breaks the local emulation from §10). boto3 timeouts/retry counts (`read_timeout`, `connect_timeout`, `max_attempts`) — from settings too.
- Large exports — split into parts by N records/bytes (a setting), upload from a tempfile as a stream (`put_object` with a file-like body), do not keep everything in RAM.
- Retries with exponential backoff (settings `max_retries`, `retry_backoff`).
- S3 keys — per the agreed convention (source/date/run_id/part). The bucket — from settings, and it must be one of the buckets the consumer reads.

***

## §7. Kafka

- The worker is also tested locally before the MR (see §10).
- Topics are named: **source → environment → entity** (the team's adopted convention). After creation the topic is added to the topic catalog (registry).
- Messages are validated at the boundary (Pydantic); broken ones go to the DLQ, not silently dropped.

***

## §8. Data naming (DBs, tables, topics)

The team's adopted naming convention (not in the general standards):

- **DB name = source name** the data originally comes from (e.g. `crm` = data from the CRM).
- Environment suffixes in the DB name where adopted (`crm_prod`, `crm_stage`).
- **Kafka topic: source → environment → entity.**
- Any new table/view/topic — **added to the registry** (table catalog / topic catalog), so that the data layer stays documented.

***

## §9. State and idempotency

- Pipeline state (what has already been processed) is stored explicitly: a checkpoint table (per files) or a watermark table (per time).
- **Commit order:** data written to the sink (CH/S3) → **then** advance the cursor → then optional side actions (consumer notification).
- Side actions (notifying an external service) — **best-effort**: wrap them; on unavailability log `error` and continue, do not roll back the cursor. A failed side step must not cause the window to be reprocessed.
- For recoverability — write the side step's success flag to a log table (e.g. `notified UInt8`), so missed ones can be retried via a query.

***

## §10. Testing — locally and with emulation (MANDATORY)

The core team DoD rule: **"before creating an MR, verify functionality locally and run the tests."** For data-engineering components this means the agent/developer must **spin up the local emulation and actually run the pipeline**, not stop at unit tests.

### §10.1 Local emulation (spin up and run)

- Bring up dependencies locally via `docker-compose`: **ClickHouse**, **MinIO** (S3-compatible, creds `minioadmin`/`minioadmin`), **Kafka** and **Postgres** — whichever the component needs. For DAG components — also a **local Airflow** (`airflow standalone` or docker-compose), so the DAG itself is actually parsed and run, not just the dependencies.
- Two common traps of local CH: (1) newer `clickhouse-server` images **disable network access** for `default` without a password — set `CLICKHOUSE_USER`/`CLICKHOUSE_PASSWORD` in the compose file (the password is local, not a secret); (2) `clickhouse_connect` uses the **HTTP port** (usually `8123`), not the native `9000` — put the HTTP port in the local `.env`. For MinIO on localhost — `addressing_style=path` (see §6).
- Run the application in `--ingest`/`--export`/`--source` mode against the local services on a small volume.
- Use the test limits from settings: `TEST_INGEST=true`, `TEST_INGEST_LIMIT`, `TEST_INGEST_ROW_LIMIT` (as in the reference application), or `dry_run`.
- Verify that data actually appeared in the local sink (rows in CH / objects in MinIO) and the cursor/checkpoint advanced.
- **Local load testing** (a DoD item): on a real volume verify that there is **no memory leak** and throughput is within expectations. For streaming exports — that we are not loading everything into RAM.

### §10.2 DAG locally

- Verify that the DAG **parses** (`python <dag_file>.py` without errors, or `airflow dags list`/local standalone).
- If the local Python cannot run Airflow (version too new / missing) — parse via a Docker image: `docker run --rm -v "$PWD":/opt/airflow/repo -e AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/repo/dags apache/airflow:<v> bash -c "airflow db migrate >/dev/null 2>&1 && airflow dags list-import-errors && airflow dags list"`. `list-import-errors` must be empty. A real run of a KPO task requires k8s — verify the business logic by running the CLI against local CH/MinIO (it is the same code that runs in the pod).
- Verify there are no top-level `Variable.get()` calls or heavy imports (§4.3).
- Run the DAG's task locally against the local emulation.

### §10.3 Unit tests (per testing.md + team DoD)

- `pytest`, `from __future__ import annotations`, no `unittest.TestCase`.
- **A test for every new method.** The structure mirrors the code: the test lives in a `test_<dir>/` folder, file `test_<name>.py`; for a method in a class — a `Test<Name>` class with `test_<method>`.
- Fake clients instead of mocks: `FakeClickHouse` (returns predefined blocks), `FakeS3` (writes to memory), `FakeKafka`, `FakeNotifier` (can raise an exception). Not `MagicMock`.
- Cover: happy path; empty window/file; partial volume; side-step unavailability (no crash, cursor as expected); SQL parameterization.

### §10.4 Definition of Done (data-eng)

The task is not closed without this (digest of the team DoD):

- [ ] Emulation brought up locally, pipeline actually run, result verified.
- [ ] Local load testing: no memory leak, throughput OK.
- [ ] For ETL: **a local DAG run through Airflow is mandatory** — not just parsing, but a green `airflow dags test <dag_id> <date>` (with an incompatible local Python, run Airflow in the `apache/airflow:<v>` Docker image, see §10.2 — a Python version is no excuse to skip the step); new variables created in the right Airflow; the DAG documented in the docs; the Pydantic config commented + a link in the docs.
- [ ] For a Kafka worker: worker verified locally; tests exist; docs for the worker exist.
- [ ] For a DB task: verified locally; tests; where needed — indexes and cleanup of old partitions in CH.
- [ ] For "Kafka → CH": fields added to the DDL script; partition cleanup where needed.
- [ ] Repo linter green (toolchain per §11), tests green.
- [ ] Docs updated; new table/topic added to the registry.

***

## §11. Linter and formatting

- **Toolchain — per the actual target repo; do not impose one.** In legacy ETL repositories pre-commit is usually configured with `pycln` + `isort` + `black` + `flake8` + `mypy` + `bandit` (see their `.pre-commit-config.yaml`). In FastAPI services (`python-standards.md`) — `ruff` + `basedpyright` via `uv`. Use whatever is set up in the repo you are committing to.
- Ruff is introduced into legacy projects iteratively: do not block work; file tasks for the accumulated findings.
- Pre-commit hook **or** linter in the IDE (Black/Ruff on save) — per the project's convention; some use pre-commit, some use IDE linters without a hook. What matters is that the code passes the repo's linter before the MR.

***

## §12. Documentation and review

- Every component/DAG/worker gets docs: what it does, how it does it, main settings, working URLs. So that its operation can be understood without reading the code (`docs.md` + the team's docs rule). Diagrams — `draw.io`/Mermaid; any diagram beats none, but no perfectionism.
- Cross code review: after the MR and green tests, ping reviewers from your own group (data engineers/ETL have their own group), review within a reasonable SLA, approval by quorum.
- Commits: prefix — the task ID; do not include submodule folders in the commit.

***

## §13. Self-check checklist before the MR (data-eng)

- [ ] Settings via `pydantic-settings`, secrets from ENV, target names in settings, empty string → None.
- [ ] DAG: file name = id, config via Pydantic `<dag_id>_conf`, no top-level `Variable.get()`/heavy imports.
- [ ] CH: parameterized SQL, streamed reads, batched inserts; **time is aware-UTC** (naive shifts by the pod TZ, §5).
- [ ] S3: split into parts, stream from a tempfile, retries; `addressing_style` from settings (OBS=virtual, MinIO=path).
- [ ] State: the cursor advances after the data is written; side steps are best-effort.
- [ ] **Brought up the emulation locally (CH/MinIO/Kafka), ran the pipeline, verified the result, load-tested for leaks/throughput.**
- [ ] Unit tests with Fake clients; a test for every new method.
- [ ] DB/table/topic naming per §8, new ones added to the registry.
- [ ] Repo linter green (§11); types annotated; docstrings in English.
- [ ] Docs updated; DoD §10.4 passed.
