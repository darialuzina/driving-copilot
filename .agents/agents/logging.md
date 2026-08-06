# Logging rules

## Stack

- **Service** — `structlog` (structured logs).
- **Library** — standard `logging` (do not force a format on the consumer).
- Serializer — `structlog.processors.JSONRenderer()`: it works out of the box on stdlib `json` and needs no extra dependencies. `orjson` (`JSONRenderer(serializer=orjson.dumps)`) is an optional speedup for prod: it needs `uv add orjson`, and it returns `bytes` — the logger factory accounts for this.
- Configuration — once at startup, in `configure_logging()` from `app/logging.py`.

## Rules

- **Never `print()`** for logging. Debugging — `breakpoint()`; writing to the stream — `logger.info(...)`.
- **kwargs, not f-strings** in the message. The event string is stable, parameters go separately:

  ```python
  # ❌
  logger.info(f"order {order_id} processed in {duration}s")

  # ✅
  logger.info("order processed", order_id=order_id, duration_s=duration)
  ```

  Otherwise `count by event` grouping is impossible in Loki / ELK — every message is unique.

- **Do not log secrets in kwargs.** Passwords, tokens, Authorization, cookies, PII — never. As the last line of defense there is a recursive `redact_secrets` processor (see `app/logging.py`), but that is insurance; a field named `password` / `token` / `secret` in `logger.info(..., password=p)` is already **a code-style bug**.
- **Do not log in hot loops.** A log in a hot path under load → I/O bottleneck. Log the loop's summary or sample (one in N).
- **Request context — via `bind_contextvars`.** Middleware binds `request_id` (or picks up `X-Request-ID`) at the start of the request and clears it at the end. All logs within the request automatically get this field — `grep request_id=...` shows the whole pipeline.

## Levels

| Level | When | Example |
|---|---|---|
| `debug` | Local debugging; disabled in prod | `log.debug("repo query plan", plan=plan)` |
| `info` | Significant events: startup, business operation | `log.info("link created", code=code)` |
| `warning` | Abnormal but handled (retry, fallback) | `log.warning("agentplatform retry", attempt=2)` |
| `error` | Operation failed, needs attention | `log.error("db connection failed", url=...)` |
| `critical` | Service is inoperable | `log.critical("config missing", key="DB_URL")` |

In prod the level is `info` and above; `debug` is enabled locally via ENV (`LOG_LEVEL=DEBUG`).

## Format

- **prod** — JSON lines (`JSONRenderer()`, optionally with `serializer=orjson.dumps`), one line = one event. This is a Loki / ELK / Datadog requirement.
- **dev** (`APP_ENV=local`) — `ConsoleRenderer` with color, readable tracebacks.
- The `message` field is a renamed `event` (for compatibility with Loki, where `message` is the standard name).
- The `request_id` field is added automatically in middleware (see `app/middleware/request_id.py`).
- The `module` / `func_name` / `lineno` fields are added automatically via `CallsiteParameterAdder`.

## Integration with stdlib logging

Logs from `uvicorn` / `sqlalchemy` / `fastapi` / `httpx` go through standard `logging`. So that they **also** pass through redact_secrets and land in the single JSON stream, `configure_logging()` sets up `structlog.stdlib.ProcessorFormatter` + `foreign_pre_chain`. Without this, SQL queries from SQLAlchemy and uvicorn's HTTP logs fly through raw and can leak parameters in plaintext.

## Forbidden (blocks merge)

- `print()` in `app/` for logging.
- `logger.info(f"... {var} ...")` — an f-string in the message.
- The fields `password` / `token` / `secret` / `authorization` / `cookie` / `api_key` in logger kwargs.
- Your own `logging.basicConfig(...)` bypassing `configure_logging()`.
