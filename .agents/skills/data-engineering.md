# Skill: Data Engineering

## Algorithm for a data-engineering task

> Apply to ETL applications, Airflow DAGs, Kafka workers, loading into
> ClickHouse, and exporting from CH to S3. The (declarative) rules are in
> `.agents/agents/data-engineering.md`. This skill is the step-by-step algorithm.
> Reference implementation: `data-platform/etl/docker_apps/etl_ingest/`.

### 1. Preparation
- Clarify which component it is: ETL app / DAG / Kafka worker / CH load / CH→S3.
- Find the Jira ticket, create a branch off dev: name = ticket ID.
- Read `.agents/agents/data-engineering.md` and, if the task is large (≥ 1 day),
  write an architecture document per `.agents/skills/architecture.md`.
- Find the nearby reference (`etl_ingest`) and copy its structure — do not invent your own.

### 2. Study
- Understand the data source and sink, their format and volume.
- Determine the state model: file-checkpoint (by objects) or time-watermark (by time).
- Check the naming (DB = source; topic = source→contour→entity) and the
  table/topic registry — do not create duplicates.
- Align with the repo's toolchain (`.pre-commit-config.yaml`): which linters are actually installed.

### 3. Implementation (structure like the reference)
1. `settings.py` — `pydantic-settings`, nested models per source,
   `env_nested_delimiter="__"`, empty string → `None` (`BeforeValidator`),
   secrets from ENV, target table/bucket/topic names go into settings, not code.
2. `cli.py` / `app.py` — argparse + dispatch by mode, no business logic.
3. `clients/` — thin factories: `clickhouse_connect`, `boto3` (virtual addressing),
   `psycopg`. Synchronous (this is batch, not an async service — see §1.1 of the standard).
4. Business logic in `ingest/`/`export/`: CH reads **streamed**, inserts **batched**,
   SQL **parameterized only**, S3 — split into parts + stream from a tempfile.
5. `storage/` — checkpoint/watermark and batch log. Move the cursor **after** the data
   is written; side steps (notification) are best-effort (catch, log as `error`,
   do not roll back the cursor).
6. Magic numbers → `const.py`. All functions with annotations and docstrings in English.

### 4. DAG (if any)
- DAG file name = DAG ID; do not put the word "DAG" in the name.
- DAG config — a Pydantic class `<dag_id>_conf` (in `dags_conf/` or as
  `pydantic-settings` from ENV, per the Airflow setup in the repo); initialized in the first
  lines after the imports; values in an Airflow Variable (JSON) or a k8s Secret.
- **Clean DAG top level:** no `Variable.get()` and no heavy imports (`pandas`,
  custom modules) at the top level — lazy-import inside functions/operators only.
- `KubernetesPodOperator`: `max_active_runs=1`, `catchup=False`, `execution_timeout`,
  `on_finish_action="delete_pod"`, secrets via `Secret("env", ...)`.
- Do not rewrite existing DAGs without need.

### 5. Testing — LOCALLY WITH EMULATION (mandatory)
This is the key step. The agent **itself** brings up the emulation and actually runs
the pipeline, rather than stopping at unit tests.

1. Bring up `docker-compose` with the needed services: **ClickHouse**, **MinIO**
   (`minioadmin`/`minioadmin`), **Kafka**, **Postgres** — whatever the component needs.
   For DAG tasks — also **local Airflow** (`airflow standalone`) to run the DAG itself.
   If the local Python is too new for Airflow (Airflow ≤ 3.12, and the machine has, say,
   3.14 — `pip install apache-airflow` will not install): run Airflow **in the Docker image**
   `apache/airflow:<v>`, not in a venv. It "doesn't fit" by Python version, not by memory.
2. Run the application against the local services on a small volume
   (`TEST_INGEST=true`, `TEST_INGEST_LIMIT`, `TEST_INGEST_ROW_LIMIT`, or `dry_run`).
3. Verify the result: rows appeared in local CH / objects in MinIO,
   the cursor/checkpoint moved as expected.
4. **Local load test:** at volume, confirm there is no memory leak and throughput
   is within expected bounds (for streamed exports — that we do not load everything into RAM).
5. DAG: confirm it parses (`python <dag>.py` without errors), the top level is clean,
   the task runs locally. A practical venv-free approach: mount the repo into
   `apache/airflow:<v>` and run `airflow db migrate && airflow dags list-import-errors
   && airflow dags test <dag_id> <date>` (install the app's deps with `pip install` in the same
   container). Caveat: `KubernetesPodOperator` requires k8s for a **real** run —
   locally without a cluster, keep a **local copy of the DAG** with `BashOperator`/`DockerOperator`
   calling the same `python -m <app>` (the same code that runs in the pod), and verify the prod
   DAG with KPO for **parsing** only. That gives a green end-to-end Airflow→app→S3/CH run
   without k8s, without touching the prod DAG.
6. Unit tests (`pytest`, Fake clients `FakeClickHouse`/`FakeS3`/`FakeKafka`, not mocks):
   a test for every new method, structure `test_<dir>/test_<name>.py`, `Test<Class>`.

### 6. Final check (repo toolchain)
- Run the linters/formatters installed in the repo. For `data-platform/etl`:
  `pre-commit run --all-files` (pycln, isort, black, flake8, mypy, bandit).
  For FastAPI repos — `uv run ruff check . && uv run basedpyright && uv run pytest -q`.
- All tests green, including the run against the local emulation.
- On a non-trivial failure — `.agents/agents/error-handling.md`
  (Identify → Assess → Communicate → Solutions); do not slap on a workaround.

### 7. Documentation and DoD
Go through the DoD in `.agents/agents/data-engineering.md` §10.4:
- ETL: DAG verified locally, variables created in Airflow, DAG described in the docs,
  Pydantic config commented + linked from the docs.
- Kafka worker: verified locally, tests, worker docs.
- DB task: verified locally, tests, indexes if needed + CH partition cleanup.
- "Kafka → CH": fields added to the DDL script, partition cleanup if needed.
- New table/topic added to the registry. Docs updated.

### 8. Commit and review
- Commit: prefix — the ticket ID; do not include submodule folders.
  Format and language — per `.agents/AGENTS.md` (tag and description in English).
- Cross code review: once tests are green, ping the reviewers of your group (for
  data engineers — their own group), approval by quorum.
