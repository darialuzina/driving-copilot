# Database rules

## Stack

- **PostgreSQL** runs via Docker Compose.
- **SQLAlchemy 2.0 async stack**: `AsyncSession`, `async_sessionmaker`, `create_async_engine`. Driver — `psycopg` (psycopg3, supports async natively).
- **Every DB access is `async def` + `await`**. No synchronous `Session.execute(...)` — only `await session.execute(...)`.
- Repository methods are all `async def`. Service methods are all `async def`. FastAPI handlers are `async def` + `await service.method()`.

## Migrations

- Any DB schema change requires an Alembic migration. No exceptions.
- Never change table structure without a migration (even if "it works locally").
- All migrations must be reproducible (running them on a clean DB on any machine must give the same result).
- Using `alembic revision --autogenerate` is allowed, but the migration **must be reviewed by eye**: autogenerate sometimes adds `op.drop_*` for untouched columns or gets types wrong.
- Our Alembic runs in **async mode** — `alembic/env.py` runs migrations via `asyncio.run(run_migrations_online())` with `async_engine_from_config`.

## Repository pattern

- The service does not reach into `AsyncSession` directly — only through `LinkRepository`.
- The repository takes `AsyncSession` in `__init__`.
- All repository methods are `async def` + `await session.execute(...)` / `await session.get(...)` / `await session.commit()`.
- `expire_on_commit=False` in `async_sessionmaker` — otherwise after commit any attribute access triggers a refresh, which in async requires an await and breaks easily.

## What to check

- All changes to DB logic are covered by integration tests against a real PostgreSQL (not SQLite in-memory).
- Integration tests use an autouse table-cleanup fixture via `await session.execute(text("DELETE FROM links"))`.
