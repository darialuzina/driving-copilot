# DRIVE-2 — Spec Compliance Audit

Audit of the current implementation (commit `32891a9` + DRIVE-2 changes) against
`driving-copilot-spec.md` v1.5 (the single canonical spec). Phase 1 scope is
"included"; later phases are checked for completeness of the gap list.

---

## 1. Conforming

Implemented spec items, one line each:

- **§1 Architecture** — pipeline identity → router → tools → answer → guardrail implemented in `app/bot.py`, `app/services/router.py`, `app/services/agent.py`.
- **§1 Architecture** — `log` label routes directly to `log_lesson` tool via the agent loop (same code path as lookup).
- **§2 Tech stack** — Python 3.14, `python-telegram-bot` v22, PostgreSQL via SQLAlchemy + Alembic, OpenRouter via `openai` client.
- **§2 Env vars** — `TELEGRAM_BOT_TOKEN`, `ALLOWED_CHAT_ID`, `LLM_API_KEY` (not `OPENROUTER_API_KEY`), `LLM_BASE_URL`, `ROUTER_MODEL`, `ANSWER_MODEL`, `EXAM_DATE`, `TIMEZONE` all in `app/config.py`.
- **§2 Security rule 1** — credentials only in env, never in code or prompts.
- **§2 Security rule 3** — bot replies only to `ALLOWED_CHAT_ID`; other chats silently ignored via `is_allowed_chat()` in `app/bot.py:124`.
- **§3 Data model** — `sessions`, `skills`, `lesson_notes`, `audit_log` tables match spec fields; `email_uid` unique; `created_at` server-default.
- **§3 Data model** — `audit_log` has `idempotency_key` column (spec calls for idempotency + audit row on every write).
- **§4 CBR skills matrix** — 27 skills across 7 categories seeded in migration `0002_driving_phase1.py` via `app/db/seed.py`.
- **§5 Router** — one LLM call, six labels (`lookup|analytics|log|docs|smalltalk|other`), label-only output requested.
- **§5 Router** — low-confidence fallback: invalid label → retry with `ANSWER_MODEL` → still invalid → `other` (`app/services/router.py:100-104`).
- **§5 Router** — jsonl logging of every `(message, label)` pair to `logs/router.jsonl` (`app/services/router.py:121-135`).
- **§6 Tool registry** — `get_next_lessons` (days_ahead=14), `get_lesson_history` (limit=10), `log_lesson` implemented with Pydantic schemas, validation before DB.
- **§6 Tool registry** — `log_lesson` tier is `write_auto`, writes `audit_log`, idempotency key checked before write.
- **§6 Tool registry** — `log_lesson` fuzzy-matches skill names; unmatched → stored as general note (skill_id=NULL) + flagged in reply.
- **§6 Tool registry** — every returned record includes its `id` (guardrail anchor).
- **§6 Answer-generation rule 1** — "reply in the language of the user's message" is rule #1 in `ANSWER_SYSTEM_PROMPT` (`app/services/prompts.py:35`).
- **§6 Answer-generation rule 2** — "only facts from tool results; if nothing, say so" in `ANSWER_SYSTEM_PROMPT`.
- **§6 Answer-generation rule 3** — "include dates" in `ANSWER_SYSTEM_PROMPT`.
- **§6 Answer-generation rule 4** — "max 6 sentences, Telegram-friendly" in `ANSWER_SYSTEM_PROMPT`.
- **§6 Guardrail** — containment check: every date and count in the answer must appear in tool JSON (`app/services/agent.py:202-211`).
- **§6 Guardrail** — on containment failure: one corrective retry, then send with ⚠️ prefix (`app/services/agent.py:95-118`).
- **§6b Capability map** — `/start` greeting lists available capabilities (`app/bot.py:32-40`).
- **§6b Capability map** — `other` label → honest refusal + what IS available (`app/services/agent.py:53-54`, `REFUSAL_SYSTEM_PROMPT`).
- **§6b Capability map** — `smalltalk` → direct reply, no tools (`app/services/agent.py:53`).
- **§9 Phase 1** — DB + seed skills + backfill (§11) + bot `/start` + router wired + `get_next_lessons`/`get_lesson_history` + `log_lesson` via chat. All acceptance criteria met.
- **§11 Backfill** — `fixtures/backfill.yaml` + idempotent load script (`app/services/backfill.py`), 6 sessions / 9 notes, re-running produces 0/0.
- **§12 LLM_API_KEY naming** — deliberately not named `OPENROUTER_API_KEY` to avoid shell env override.

---

## 2. Deviations

Implementation differs from spec:

### High severity

1. **§5 Router prompt: missing 2 examples per label** — the spec requires "2 examples each (include one Russian and one Dutch example)". The prompt has 1–2 examples per label but not consistently 2, and `analytics` has no Dutch example, `smalltalk` has no Dutch example, `log` has no Dutch example, `other` has no Dutch example.
   *Fix:* add a second example (one ru, one nl) for every label in `ROUTER_SYSTEM_PROMPT`.

2. **§6 Answer-generation rule 5: provenance labels missing** — spec v1.5 adds rule 5 (provenance labels: KB cite section, live web prefix "from cbr.nl just now", general knowledge prefix "not from the CBR docs"). The `ANSWER_SYSTEM_PROMPT` has a rule 5 about booking/cancelling instead.
   *Fix:* add the provenance rule to the answer prompt (Phase 2, when `get_cbr_info`/`cbr_search`/`web_search_cbr` land).

3. **§6 Guardrail: IDs not checked** — spec says "every date and **number** in the generated answer must exist in the collected tool JSON". The containment check checks dates and standalone integers, but does not check skill IDs or note IDs. The spec says "IDs, dates, and numbers" (ai.md §Guardrails).
   *Fix:* extend `containment_ok` to also check that any `id`-like number in the answer appears in the tool JSON (or document why integer checking is sufficient for Phase 1).

### Medium severity

4. **§3 Data model: `date` column type** — spec shows `date TEXT NOT NULL` (ISO date as text); implementation uses `sa.Date()`. This is a deliberate, justified deviation (Postgres `DATE` is stricter), but the spec was not updated.
   *Fix:* no code change needed; note in the spec that `Date` replaces `TEXT` per the Postgres decision.

5. **§3 Data model: `exam_relevant` type** — spec shows `exam_relevant INTEGER DEFAULT 1`; implementation uses `Boolean`. Same justified deviation.
   *Fix:* no code change needed; note in the spec.

6. **§3 Data model: `payload` type** — spec shows `payload TEXT NOT NULL` (JSON as text); implementation uses `JSONB`. Same justified deviation.
   *Fix:* no code change needed; note in the spec.

7. **§6 Tool registry: `get_lesson_history` returns** — spec says "past sessions + **note counts**"; implementation returns the full notes (not just counts). This is a richer return, but differs from the spec.
   *Fix:* either add a `note_count` field to the session serialization, or update the spec to reflect the richer return.

8. **§5 Router: structured output** — spec says "answer with the label only"; the router requests `json_mode=True` and parses `{"label": "..."}`. The spec implies plain text, not JSON. The implementation degrades gracefully (plain text falls through), but the JSON request is an undocumented deviation.
   *Fix:* either document that the router uses JSON mode, or switch to plain text mode. JSON mode is more robust; keep it and document it.

9. **§6 Answer-generation: analytics/docs hardcoded to Phase 2 pending message** — `AgentService.handle()` returns `PHASE2_PENDING_MESSAGE` for `analytics` and `docs` labels instead of routing them through the agent loop. The spec (§6b) routes analytics to tools. This is a Phase 1 shortcut.
   *Fix:* remove the shortcut in Phase 2 when the analytics tools are implemented.

### Low severity

10. **§2 Tech stack: `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `OMW_SENDER_FILTER`** — spec lists these env vars; they are not in `Settings` yet.
    *Fix:* add to `Settings` in Phase 3 (email ingestion).

11. **§6 Tool registry: `log_lesson` idempotency key** — the key is `f"log:{int(time.time() * 1000)}"` generated per call in `AgentService._execute()`. This means two identical `log_lesson` calls in the same millisecond would share a key (unlikely but not impossible). The spec says "idempotency key" without specifying the source.
    *Fix:* use a UUID or a hash of the arguments for the idempotency key to guarantee uniqueness per distinct call.

12. **§5 Router: `elapsed_ms` logged but not `model`/`tokens`** — ai.md says "log every LLM call (model, latency, tokens, tool calls made)". The router logs `label`, `message`, `elapsed_ms` but not model or tokens.
    *Fix:* add `model` and (if available) token counts to the jsonl record.

---

## 3. Gaps

Spec items absent from the code:

### Due in a later phase (name the phase)

- **§6 `get_skill_progress` tool** — Phase 2.
- **§6 `get_gap_analysis` tool** — Phase 2.
- **§6 `get_notes` tool** — Phase 2.
- **§6 `get_pace` tool** — Phase 2.
- **§6 `get_cbr_info` tool** — Phase 2.
- **§6 `cbr_search` tool** — Phase 2.
- **§6 `web_search_cbr` tool** — Phase 2.
- **§3 Semantic layer: `skill_status()`, `pace()`, `stale()`** — Phase 2.
- **§6 Answer-generation rule 5: provenance labels** — Phase 2 (needs the docs stack).
- **§7 Email ingestion** — Phase 3 (IMAP poller, extraction, fixtures, dead-letter, Telegram notify).
- **§6 `trigger_email_check` tool** — Phase 3.
- **§8 Digests (pre-lesson + weekly)** — Phase 4.
- **§8 KB freshness watchdog** — Phase 4.
- **§6 `check_slots` tool** — Stretch (feature flag `SLOT_WATCHER=off`).
- **§9 Phase 5: evals** — `evals/golden.yaml` not yet in the repo. Spec says "lives in the repo from Phase 1".
- **§10 Golden set** — not yet stored as `evals/golden.yaml`.

### Should already exist but missing

1. **§9 Phase 5 / ai.md: `evals/golden.yaml`** — ai.md says "evals/golden.yaml lives in the repo **from Phase 1** and grows from real traffic". It does not exist.
   *Severity: Medium.* *Fix:* create `evals/golden.yaml` with the 10 router cases from §10.

2. **§5 Router: structured logging of every LLM call** — ai.md requires logging "every LLM call (model, latency, tokens, tool calls made) as structured logs". Only the router logs to jsonl; the agent loop logs `agent.answer` (turns, tool count) but not model, tokens, or latency.
   *Severity: Medium.* *Fix:* add model/latency/tokens to the `agent.answer` structlog call and optionally to a separate jsonl.

3. **§2 Security rule 4: untrusted content handling** — the rule exists but there is no untrusted content flow yet (no email ingestion). No code gap for Phase 1, but the rule should be enforced when Phase 3 lands.
   *Severity: Low.* *Fix:* enforce in Phase 3 when the extraction flow is built.

4. **§6b: `/start` capability greeting mentions Phase 2 features as future** — the greeting says "(from Phase 2 on) gap analysis and CBR exam info". The spec §6b doesn't say the greeting should mention phases; it should list current capabilities.
   *Severity: Low.* *Fix:* reword to say what the bot can do now, not what phase it's in.

5. **ai.md: "Definition of Done — AI feature" item 1** — "Router labels + tools have eval cases; suite green at 3 rolls." No eval suite exists yet.
   *Severity: Medium.* *Fix:* create the eval runner + golden.yaml (Phase 5, but the golden.yaml file should exist from Phase 1 per ai.md).

6. **§5 Router prompt: "include one Russian and one Dutch example"** — the prompt has Russian examples for `lookup` and `log` and `smalltalk`, and Dutch examples for `analytics` and `docs`, but not every label has both. The spec says "include one Russian and one Dutch example — Daria writes in ru/en/nl", meaning the example set overall should cover ru/en/nl, which it does.
   *Severity: Low.* *Fix:* add at least one Dutch example for `log`, `smalltalk`, and `other` for completeness.
