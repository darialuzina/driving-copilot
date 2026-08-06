# Agent: Docs

## When to update documentation

- **A public function / class / method was added or changed** → update / write the docstring.
- **An endpoint, ENV variable, dependency, or launch command was added / changed** → update README.md.
- **A decision was made that affects multiple modules or changes a public contract** → create an ADR in `docs/adr/` (see below: ADR-lite vs ADR-full).
- **Any user-facing change (new endpoint, breaking change, bug fix, new configuration)** → add an entry to `CHANGELOG.md` under `[Unreleased]`.

## Docstrings

- Format — Google-style. Sections: a one-line summary, then (as needed) `Args:`, `Returns:`, `Raises:`.
- **Docstrings are written in English.** Parameter names stay as they are in the code; descriptions are in English.
- Private functions (starting with `_`) may be documented at your discretion if they are trivial.
- Forbidden: a docstring that repeats the function name (`def get_user(): """Get user."""`). Either explain why the function exists, or write nothing at all.
- Usage examples in a docstring — only when the behavior is non-obvious.

## CHANGELOG.md

- Standard — [Keep a Changelog](https://keepachangelog.com/).
- `[Unreleased]` sections: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`.
- One entry = one user-facing change, not one commit. Refactoring with no behavior change **does not go** into the CHANGELOG.
- Jira ticket references go in parentheses at the end of the entry: `- Added PATCH /links/{id} to update target_url (PROJ-101)`.

## ADR

An ADR (Architecture Decision Record) records a significant technical decision.
Two formats by complexity: **ADR-lite** (quick record) and **ADR-full**
(full options analysis with an evaluation matrix). Choose by the triggers below.

### When ADR-full is needed

At least one of these triggers fires:

- The decision is **expensive to roll back** — data migration, changing the DB / framework / language / authentication scheme.
- The decision **affects > 1 repository** (in our case — across `service-a-scraper`, `service-a-api`, `harvest_api`).
- The decision **affects NFRs** — p99 latency, infrastructure cost, security / compliance.
- The decision **contradicts a previously accepted ADR** — then the new ADR marks the old one as `Superseded by NNNN`.
- There is **an ongoing dispute** in the team with at least two people holding different preferences.
- There are **≥ 3** options to choose from.

### When ADR-lite is enough

- A fork with 2 options that do not differ much.
- The decision is inside a single repository and rolls back with one commit.
- It does not affect the public API / DB / NFRs.

ADR-lite examples: "logging via `structlog` with `ConsoleRenderer` in dev and `JSONRenderer` in prod", "route names in the plural", "migrations — autogenerate + manual review".

ADR-full examples: "storage for scraping-job statuses: PostgreSQL JSONB vs Redis vs in-memory + dump", "worker parallelism: `asyncio.Semaphore` vs `multiprocessing` vs Celery", "JWT vs session-based auth".

### Path and general rules

- Path: `docs/adr/NNNN-short-name.md`, where `NNNN` is the next free number.
- Never delete an ADR. Obsolete ones are marked `Superseded by NNNN` but stay in the repository — this is the history of decisions.
- Every ADR (either format) is added to `docs/adr/INDEX.md` as a line: `NNNN | short-name | Status | date | author | tags`.

### ADR-lite template

```markdown
# NNNN — <short decision name>

## Status

Accepted

## Context

<What is the problem? What constraints, requirements, and forces bore on the decision?>

## Decision

<What exactly was decided. One or two crisp sentences.>

## Consequences

<What gets better? What gets worse? Which risks remain accepted?>

## Alternatives considered

- <Alternative 1>: why it was not chosen.
- <Alternative 2>: why it was not chosen.
```

### ADR-full template

```markdown
# NNNN — <short decision name>

## Status

Proposed | Accepted | Superseded by NNNN | Deprecated

## Y-statement

In the context of `<scenario>`, facing `<driver>`, we decided for
`<option>` over `<alternatives>`, to achieve `<quality>`, accepting
`<trade-off>`.

> Example: "In the context of the scraping worker, facing the requirement
> to process ≥ 200 jobs/min at p99 < 5s, we decided to use
> `asyncio.Semaphore(50)` over `multiprocessing.Pool(8)`, to keep
> everything in a single async process and reuse the httpx connection pool,
> accepting the risk of head-of-line blocking on heavy CPU operations in
> handlers."

## Context

<2–5 paragraphs: what forced this decision, what facts are at hand,
what the constraints are. Numbers, metrics, links to Jira / experiments.>

## Decision drivers

Every driver is **measurable** or has an explicit "how we will know it is
met" criterion. Not "we need performance" but "p99 < 200ms at 100 RPS".
Not "we need simplicity" but "a new developer on the team gets up to speed
within 1 hour of reading the code".

1. <Driver 1, measurable>
2. <Driver 2, measurable>
3. <...>

## Considered options

- **Option A** — `<name>`. <1–2 sentences on what it is.>
- **Option B** — `<name>`. <...>
- **Option C** — `<name>`. <...>

## Decision

**Option `<letter>`** is chosen.

### Y-rationale

<1 paragraph: why exactly this option is optimal across the drivers combined.>

## Pros and cons of options

### Option A — <name>
- ✅ <pro against a specific driver>
- ✅ <pro>
- ❌ <con against a specific driver>
- ❌ <con>

### Option B — <name>
- ✅ <...>
- ❌ <...>

### Option C — <name>
- ✅ <...>
- ❌ <...>

## Evaluation matrix

> **Criteria weights were locked on `<YYYY-MM-DD>` BEFORE scoring the options.**
> This rule is insurance against fitting the answer. If after the calculation
> you want to change the weights — that is a signal you need more data
> or a PoC, not weight editing.

| Criterion | Weight | Option A | Option B | Option C |
|---|---|---|---|---|
| <Driver 1> | 0.3 | 5 | 3 | 4 |
| <Driver 2> | 0.25 | 4 | 5 | 2 |
| <Driver 3> | 0.25 | 3 | 4 | 5 |
| <Operational simplicity> | 0.1 | 4 | 5 | 3 |
| <Cost> | 0.1 | 5 | 3 | 4 |
| **Total (weighted)** | | **4.05** | 3.95 | 3.55 |

Scoring scale: 1 = poor, 5 = excellent. Do not round to whole numbers "out of
laziness" — 4.05 vs 3.95 is a meaningful difference; it signals that the choice
is not obvious and a Sensitivity check is needed.

## Sensitivity check

> **Mandatory section. Without it the ADR stays in `Proposed` status.**

Question: if the criteria weights change by ±20%, does the winner change?

- If **no** → the decision is robust; move to `Accepted`.
- If **yes** → the options are too close, there is no real justification for
  the choice yet. Do not approve the ADR. Do a minimal PoC (≤ 1 day) on the
  contested options, bring the data back here, recompute the matrix.

Specifically for this decision:
<"Re-checked with driver 1's weight in the 0.2–0.4 range — the winner does not
change, Option A stays first" / "PoC done, see
`Tasks/<key>/poc-results.md`, numbers plugged into the matrix above".>

## Consequences

- ✅ <what gets better — concretely, not "maintainability improves">
- ⚠️ <what gets harder, which risks remain accepted>
- 🔄 <what needs to be done in code / infrastructure to implement the decision>

## Validation

How we will know the decision works (1–3 months after implementation):
- <Metric 1, expected value>
- <Metric 2, expected value>
- <Which event triggers revisiting the ADR>

## Links

- Jira: `<JIRA-KEY>`
- Task artifacts: `Tasks/<JIRA-KEY>/` (if there is an architecture document — `<JIRA-KEY>-architecture.md`)
- Related ADRs: NNNN (...), MMMM (...)
- External sources: <links to articles / documentation, if relied upon>
```

### Rules for ADR-full

- **Criteria weights are locked BEFORE scoring the options.** This is the main
  defense against confirmation bias. Write down the weights, then assign scores.
  Not the other way around.
- **The Sensitivity check is mandatory.** An empty section = the ADR is not
  accepted, status `Proposed`. This rule is iron.
- **Drivers must be measurable.** "We need performance" is not a
  driver. "p99 < 200ms at load X" is a driver.
- **No more than one author and one reviewer per ADR.** If you want
  more — the decision is contentious, and you must first reach consensus
  by voice / in chat; the ADR only records the result.

## README.md

- Sections (minimum): Overview, Quickstart, Configuration (ENV), Running (dev / tests / migrations), Architecture (a short layer diagram), API (link to `/schema/swagger`).
- Updated in the same commit that changes the corresponding behavior. A stale README is a merge blocker.

## Forbidden (blocks merge)

- Committing a public API without a docstring.
- A new endpoint / breaking change without a CHANGELOG entry.
- An architectural decision without an ADR (if in doubt — create an ADR-lite; it is easier than arguing over whether one is needed).
- Deleting an ADR. Obsolete ADRs are marked `Superseded by NNNN` but never deleted — the decision history is preserved.
- Auto-generated docstrings in the "Does the thing" style — no docstring is better than a junk one.
- An ADR-full with an **empty** Sensitivity check (the status stays `Proposed`; the ADR is not considered accepted).
