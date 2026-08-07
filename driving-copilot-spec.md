# Driving Copilot — Build Specification v1

A Telegram-based AI copilot for Daria's driving-exam preparation. It tracks lessons (parsed from On My Way booking emails + quick notes after each lesson), maps progress against the official CBR exam requirements (gap analysis), sends a pre-lesson digest with focus recommendations, and answers questions in chat. One auto-approved write action (logging), architecture mirrors a production agent system: small-model router → typed tools → deterministic code → guardrails → evals.

**Design principle (applies everywhere):** the model chooses and phrases; code computes. The LLM never calculates progress, never invents lesson data, never sees credentials. Every fact in an answer must come from a tool result.

---

## 1. Architecture

```
Telegram (chat + digest push)
      │
      ▼
  bot.py ── identity check (single allowed chat_id)
      │
      ▼
  router (ROUTER_MODEL, 1 call, one label)
      │
      ├─ lookup/analytics ──► agent loop (ANSWER_MODEL + typed tools) ──► answer + guardrail check
      ├─ log ──────────────► log_lesson tool (auto-approved write, echo confirmation)
      ├─ docs ─────────────► CBR knowledge lookup (local seeded content, cited)
      ├─ smalltalk ────────► direct reply, no tools
      └─ unknown/refuse ───► honest "I don't track that" + nearest capability

  background jobs (scheduler):
      • email_ingest: IMAP poll every 15 min → LLM extraction (strict schema) → upsert sessions
      • digest: morning of each lesson day at 07:30 + weekly Sunday 18:00
```

## 2. Tech stack

- Python 3.11+, `python-telegram-bot` **v22+** (async, has JobQueue; v21 crashes on Python 3.14's asyncio — learned in Phase 1)
- PostgreSQL — the repo's docker-compose db — via SQLAlchemy models + Alembic migrations, per `.agents/agents/database.md` (repo rules win over any SQLite mention below)
- LLM: OpenRouter, OpenAI-compatible client. Two models via env:
  - `ROUTER_MODEL` (default `openai/gpt-4.1-mini`) — routing + email extraction
  - `ANSWER_MODEL` (default `mistralai/mistral-large-2512`) — tool-calling agent loop + digest composition
- IMAP: `imaplib` + `email` stdlib (Gmail, app password, READ-ONLY)
- No web framework needed in v1.

### Env vars (.env)

```
TELEGRAM_BOT_TOKEN=
ALLOWED_CHAT_ID=            # only this chat may talk to the bot
LLM_API_KEY=                # the app's OWN OpenRouter key (separate key named "driving-copilot",
                            # with a credit cap). Deliberately NOT named OPENROUTER_API_KEY:
                            # that name is exported globally in the shell for the coding agents,
                            # and pydantic-settings lets real env vars override .env — the app
                            # would silently run on the wrong key.
LLM_BASE_URL=https://openrouter.ai/api/v1
ROUTER_MODEL=openai/gpt-4.1-mini
ANSWER_MODEL=mistralai/mistral-large-2512
GMAIL_ADDRESS=
GMAIL_APP_PASSWORD=         # read-only IMAP; never logged, never in prompts
OMW_SENDER_FILTER=          # e.g. @omw.nl — set after seeing a real email
EXAM_DATE=                  # YYYY-MM-DD, optional until known
TIMEZONE=Europe/Amsterdam
```

**Security rules (non-negotiable):**
1. Credentials only in env; never in code, prompts, or logs.
2. The LLM has no login tool and never sees GMAIL_* values.
3. Bot replies only to ALLOWED_CHAT_ID; ignore all other chats silently.
4. Email text is UNTRUSTED content: the extraction call has exactly one job (produce the schema below) and no tools. Extracted text fields are stored, never executed or treated as instructions.

## 3. Data model (PostgreSQL — the SQL below is illustrative; implement as SQLAlchemy models + one Alembic migration)

```sql
CREATE TABLE sessions (              -- driving lessons, from emails or manual
  id INTEGER PRIMARY KEY,
  date TEXT NOT NULL,                -- ISO date
  start_time TEXT,                   -- HH:MM, nullable
  end_time TEXT,
  instructor TEXT,
  lesson_type TEXT NOT NULL DEFAULT 'rijles',  -- rijles | proefles | exam
  status TEXT NOT NULL DEFAULT 'scheduled',  -- scheduled|completed|cancelled
  source TEXT NOT NULL DEFAULT 'manual',     -- email|manual
  email_uid TEXT UNIQUE,             -- IMAP UID for idempotent upsert
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE skills (                -- the CBR competency matrix (seeded)
  id INTEGER PRIMARY KEY,
  category TEXT NOT NULL,            -- see seed below
  name TEXT NOT NULL,
  name_nl TEXT,                      -- Dutch term (CBR vocabulary)
  exam_relevant INTEGER DEFAULT 1
);

CREATE TABLE lesson_notes (          -- Daria's observations, linked to skills
  id INTEGER PRIMARY KEY,
  session_id INTEGER REFERENCES sessions(id),
  skill_id INTEGER REFERENCES skills(id),   -- nullable: general notes allowed
  note TEXT NOT NULL,
  assessment TEXT,                   -- good|ok|needs_attention|not_practiced
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE audit_log (             -- every write, who/what/when
  id INTEGER PRIMARY KEY,
  action TEXT NOT NULL,
  payload TEXT NOT NULL,             -- JSON
  created_at TEXT DEFAULT (datetime('now'))
);
```

**Semantic layer — definitions live in code (one function each, never computed by the LLM):**

- `skill_status(skill)`: derived from the last 2 assessments of that skill:
  no notes ever → `not_started`; latest is needs_attention → `weak`;
  last two are good → `solid`; otherwise → `in_progress`.
- `pace()`: lessons remaining before EXAM_DATE vs count of skills not `solid`.
  Returns lessons_left, weak_or_missing_count, on_track boolean
  (on_track = lessons_left >= weak_or_missing_count).
- `stale(skill)`: `solid` but not practiced in 21+ days → flag for refresh.

These are the only definitions of these words in the system. Tools call these functions; answers repeat their output.

## 4. CBR skills matrix (seed data)

Source: CBR practical exam structure (cbr.nl) + Rijprocedure B. Verify/extend against
https://www.cbr.nl/nl/voor-rijscholen/nl/rijprocedures/rijprocedure-b-1 during build.

Categories and skills (name_nl in parentheses):

1. **Vehicle control** (bediening): pulling away & stopping (wegrijden/stoppen), gear use & clutch control (schakelen), steering technique (stuurtechniek), dashboard & controls knowledge (voertuigkennis)
2. **Observation** (kijkgedrag): mirror routine (spiegels), blind spot checks (dode hoek), scanning at speed (kijktechniek)
3. **Intersections** (kruispunten): priority rules (voorrang), roundabouts (rotondes), left turns (linksaf), traffic lights (verkeerslichten)
4. **Highway** (in-/uitvoegen): merging (invoegen), exiting (uitvoegen), lane changes & overtaking (inhalen/wisselen), speed adaptation (snelheid aanpassen)
5. **Special maneuvers** (bijzondere verrichtingen — examiner picks ~2): parallel parking (fileparkeren), bay parking forward/reverse (parkeervak), turning around / three-point turn (omkeren), reversing in a curve (achteruit bocht), hill start (hellingproef), stopping assignment (stopopdracht)
6. **Independent driving** (zelfstandig rijden): navigation-led driving, route signs (borden volgen), cluster assignments
7. **Attitude & environment** (rijstijl): eco driving (milieubewust), anticipating other road users (anticiperen), special road sections (bijzondere weggedeelten: bus lanes, tram, crossings)

## 5. Router

One call to ROUTER_MODEL. Output: exactly one label. Labels:

- `lookup` — single fact: "when is my next lesson?", "how many lessons left?"
- `analytics` — progress/aggregation: "how am I doing on parking?", "what are my weak areas?"
- `log` — user is reporting lesson content: "today we did roundabouts, went well, still hesitant turning left"
- `docs` — CBR/exam knowledge: "what do they check on bijzondere verrichtingen?"
- `smalltalk` — greetings/thanks
- `other` — everything else → honest refusal path

Router prompt requirements: closed label list with one-line definitions and 2 examples each (include one Russian and one Dutch example — Daria writes in ru/en/nl); answer with the label only. Log every (message, label) pair to a jsonl file — this becomes eval data.

Low-confidence fallback: if the returned label is not exactly one of the six strings, retry once with ANSWER_MODEL; if still invalid → `other`.

## 6. Tool registry (typed, all read except log_lesson)

Implement as OpenAI function-calling tools. Every tool validates params before touching the DB and returns compact JSON. Every returned record includes its id (guardrail anchor).

| Tool | Params | Returns | Notes |
|---|---|---|---|
| get_next_lessons | days_ahead int=14 | upcoming sessions | |
| get_lesson_history | limit int=10 | past sessions + note counts | |
| get_skill_progress | category str? (enum of 7) | per-skill: status, last note, last practiced | uses skill_status() |
| get_gap_analysis | — | weak + not_started skills ranked by exam weight; pace() output | the star tool |
| get_notes | skill str? , query str? | matching notes with dates | substring match ok in v1 |
| get_pace | — | pace() output | |
| get_cbr_info | topic str (enum: exam_structure, bijzondere_verrichtingen, assessment_criteria, self_reflection) | seeded CBR content with source url | content seeded at build time from cbr.nl; RAG-lite, no vectors needed in v1 |
| cbr_search | query str | matching sections from knowledge/ with heading + source | Phase 2. Keyword/heading search over the converted Rijprocedure B + seeded pages. No embeddings unless the corpus outgrows keyword search. |
| web_search_cbr | query str | live results, cbr.nl-scoped (Tavily) | Phase 2, fallback ONLY when cbr_search returns nothing (fees, waiting times — things that change). Untrusted content: this flow gets no write tools. |
| log_lesson | date str=today, skills list[{skill,assessment,note}], general_note str? | created note ids | WRITE, tier: auto-approve. Skill names fuzzy-matched against skills table; unmatched → stored as general note + flagged in reply. Writes audit_log. |
| trigger_email_check | — | new/changed sessions found | Phase 3. Runs the email-ingest job on demand ("check my mail for new bookings") instead of waiting for the 15-min cron. Read-side, auto-approve. |
| check_slots | instructor str?, days_ahead int=7 | open slots matching filters | STRETCH (feature flag, after the app-API investigation). Same watcher code exposed two ways: background push on new matching slots AND this on-demand tool. Response pairs slots with a recommendation from get_gap_analysis + get_pace. Never books. |

Answer-generation rules (system prompt of the agent loop):
1. Reply in the language of the user's message.
2. Only facts from tool results; if a tool returned nothing, say so — never improvise lesson data.
3. When mentioning lessons or notes, include their dates so the user can verify.
4. Max 6 sentences unless asked for detail; Telegram-friendly formatting.
5. Provenance labels on knowledge answers: from the KB → cite the section ("Rijprocedure B, §…");
   from the live web fallback → prefix "from cbr.nl just now:"; from the model's general knowledge
   (traffic law etc., not in any source) → prefix "not from the CBR docs — general knowledge,
   verify in your theory book:". Never present an unsourced claim as a sourced one.

Guardrail (code, after generation): every date and count in the answer must appear in the collected tool JSON (simple string/number containment check). On failure: one retry with a corrective note, then send with a ⚠️ prefix.

### 6b. Capability map (what the assistant handles — reference for router examples and the golden set)

One entry point, intent-routed, each capability = tools. Adding a capability later = one tool + router example + eval cases; the skeleton never changes.

| User says | Router label | Tool(s) | Answer shape |
|---|---|---|---|
| "what do they check on bijzondere verrichtingen?" | docs | get_cbr_info | CBR content + source |
| "when is my next lesson?" | lookup | get_next_lessons | date/time/instructor |
| "what did we do last time?" | lookup | get_lesson_history | session + notes |
| "how is my parking going?" | analytics | get_skill_progress | per-skill status from notes |
| "am I ready? what should I focus on?" | analytics | get_gap_analysis + get_pace | ranked gaps + pace verdict |
| "what did I write about highways?" | lookup | get_notes | own notes, dated |
| "today we did roundabouts, still shaky left turns" | log | log_lesson | "logged ✓" + matched skills |
| "check my mail for new bookings" | lookup | trigger_email_check | new sessions found |
| "any slots with Desevio this week?" | lookup | check_slots (stretch) | slots + recommendation |
| "what car should I buy?" | other | none | honest refusal + what IS available |
| "hoi!" / "спасибо" | smalltalk | none | plain reply, no tools |

Mixed messages ("log today: parking ok. When's next lesson?") need no special machinery: the tool-calling loop calls log_lesson then get_next_lessons in one turn. The router's coarse job is path safety (write vs read vs no-tools), not fine-grained dispatch.

## 7. Email ingestion (background job, every 15 min)

1. IMAP: search UNSEEN from OMW_SENDER_FILTER (READ-ONLY: use BODY.PEEK, do not mark seen; track processed UIDs in sessions.email_uid).
2. For each new email: one LLM call (ROUTER_MODEL) with the raw text →
   strict JSON schema:
   `{action: booked|changed|cancelled, date: YYYY-MM-DD, start_time: HH:MM|null, end_time: HH:MM|null, instructor: str|null}`
   Validate with pydantic; on failure retry once with the validation error appended; on second failure → store raw email id in a dead-letter table and notify Daria ("couldn't parse a booking email — forward me the details?").
3. Upsert into sessions keyed on email_uid (idempotent: re-running never duplicates).
4. Telegram notification on success: "📅 Lesson added: Thu 15:00 with Sandra."
5. NOTE: the parser is written against real On My Way emails Daria provides. Until then, implement + test against a fixture file `fixtures/omw_samples/`.

## 8. Digests (scheduler)

**Pre-lesson digest** — 07:30 on any day with a scheduled session:
- Data (all code, no LLM): today's session; top-3 items from get_gap_analysis; last lesson's needs_attention notes; pace().
- One ANSWER_MODEL call composes it (≤5 sentences, motivating, in Daria's preferred language).
- Guardrail: same containment check as chat answers.

**Weekly digest** — Sunday 18:00: lessons completed this week, skills that moved status, pace() verdict, suggested focus for next week. Same compose+check pattern.

**KB freshness watchdog** (piggybacks on the weekly digest job): re-fetch the seeded cbr.nl source pages, compare content hashes; on change, add one line to the digest: "CBR page <name> changed — review knowledge/ update." Updating the KB stays a human decision — a site redesign must not silently rewrite the knowledge base.

Digest facts must come only from the assembled JSON. If no data (no lessons this week), send the short honest version, not filler.

## 9. Build phases (each ends runnable; acceptance criteria included)

**Phase 1 — skeleton (evening 1):** DB + seed skills + backfill (section 11) + bot answering /start + router wired + get_next_lessons/get_lesson_history + log_lesson via chat. ✔ Accept: "сегодня делали парковку, все ок" creates a note linked to the parking skill; "when is my next lesson" answers from DB; "what did we do on July 30?" returns the backfilled notes.

**Phase 2 — brain (evening 2):** remaining read tools + gap analysis + semantic-layer functions + answer guardrail + the docs stack: get_cbr_info seeded, Rijprocedure B converted to `knowledge/rijprocedure-b.md` (source: cbr.nl "Rijprocedure B" — Daria's PDF-conversion territory), cbr_search over knowledge/, web_search_cbr fallback (Tavily, cbr.nl-scoped, no write tools in that flow), provenance rule #5 active. ✔ Accept: "what are my weak areas?" returns ranked gaps consistent with notes; "can I fail for stalling?" answers from the Rijprocedure with a section citation; a KB-miss question (e.g. exam fees) uses the live fallback WITH the "from cbr.nl just now" label; a traffic-law question gets the "general knowledge" label; out-of-scope ("what tires should I buy?") still refuses honestly.

**Phase 3 — ingestion (evening 3):** email poller + extraction + fixtures + dead-letter path + Telegram notify. ✔ Accept: dropping a fixture email into the test inbox creates a session exactly once even if the job runs twice.

**Phase 4 — proactive:** both digests on JobQueue. ✔ Accept: forced-run digest contains only facts present in DB.

**Phase 5 — evals:** run golden set (below) via a simple runner (or promptfoo): router accuracy table + tool-choice checks, 3 rolls per question. ✔ Accept: router ≥ 90% on the set; all refusal cases refuse.

**Stretch (separate module, feature flag SLOT_WATCHER=off):** On My Way slot watcher — investigate app API via mitmproxy first; poll ≤ every 10 min; read-only; notify with recommendation (uses get_gap_analysis + pace). Never auto-book. Credentials in env only, used by deterministic code, no LLM access.

## 10. Golden set (starter — extend to ~25; store as evals/golden.yaml)

Router cases (message → expected label): "when is my next lesson?" → lookup · "когда у меня следующий урок?" → lookup · "how is my parking?" → analytics · "wat zijn mijn zwakke punten?" → analytics · "today we practiced merging, went fine" → log · "сегодня тренировали парковку, пока плохо" → log · "what do they check in the exam?" → docs · "hi!" → smalltalk · "what tires should I buy?" → other · "book me a lesson tomorrow" → other (v1 cannot book; answer must say so and mention the app).

End-to-end cases (question + DB fixture → answer must contain / must not contain): weak-areas question → must name the skill with two needs_attention notes, must not name skills without notes; next-lesson question with empty DB → must say no lessons found, must not invent a date.

Backfill-based cases (run against section 11 data): "what are my weak areas?" → must include roundabouts and speed adaptation (both have repeated needs_attention), must NOT claim anything about parking (no evidence); "how is my clutch?" → must reflect improvement (latest = good on 6 Aug), citing dates; "who is my instructor?" → Desevio (most recent sessions), may mention Rob historically.

## 11. Backfill seed data (Daria's real history — load in Phase 1)

Car is manual ("schakel"). No exam date yet. Ship as `fixtures/backfill.yaml` + a load script (or direct seed in migrations for dev); loading must be idempotent.

```yaml
sessions:
  - {date: 2026-06-19, start: "09:00", end: "10:00", instructor: Rob,     lesson_type: proefles, status: completed}
  - {date: 2026-07-06, start: "12:40", end: "13:30", instructor: Rob,     lesson_type: rijles,   status: completed}
  - {date: 2026-07-20, start: "09:00", end: "10:00", instructor: Desevio, lesson_type: rijles,   status: completed}
  - {date: 2026-07-23, start: "15:15", end: "16:15", instructor: Desevio, lesson_type: rijles,   status: completed}
  - {date: 2026-07-30, start: "14:30", end: "15:30", instructor: Desevio, lesson_type: rijles,   status: completed}
  - {date: 2026-08-06, start: "16:05", end: "17:05", instructor: Desevio, lesson_type: rijles,   status: completed}

notes:
  - session_date: 2026-07-30
    items:
      - {skill: "speed adaptation",   assessment: needs_attention, note: "Speed — need to go faster"}
      - {skill: "mirror routine",     assessment: needs_attention, note: "Look at the left mirror more often"}
      - {skill: "gear use & clutch control", assessment: ok, note: "Starting the car: no gas needed — release the clutch a bit, feel it engage, hold it there"}
      - {skill: "roundabouts",        assessment: needs_attention, note: "Roundabouts practiced — still difficult"}
  - session_date: 2026-08-06
    items:
      - {skill: "roundabouts",        assessment: needs_attention, note: "Roundabout was not good again"}
      - {skill: "gear use & clutch control", assessment: good, note: "Clutch better"}
      - {skill: "steering technique", assessment: good, note: "Staying in the middle of the lane — better"}
      - {skill: "speed adaptation",   assessment: needs_attention, note: "Challenge: speeding up quickly"}
      - {skill: "anticipating other road users", assessment: needs_attention, note: "Thinking too much in difficult situations — need to think ahead"}
```

Derived starting picture the gap analysis should reproduce: weak = roundabouts (2× needs_attention), speed adaptation (2×), mirror routine, anticipating; improving = clutch (ok → good), steering (good); everything else = not_started (lessons 1–4 have no notes — that is honest data, not a bug).

## 12. What Daria provides (blockers marked ⛔)

- ⛔ TELEGRAM_BOT_TOKEN (BotFather) + first message to the bot (chat id)
- ⛔ LLM_API_KEY (the app's own OpenRouter key — see env vars note in section 2)
- ⛔ 1–2 real On My Way emails (raw text) → fixtures + OMW_SENDER_FILTER
- Gmail app password (Phase 3 only)
- EXAM_DATE when known
- (done — section 11) lesson history + notes backfill
