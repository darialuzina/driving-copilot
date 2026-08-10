# Code Review: feature/DRIVE-4-phase2-brain vs main

Branch reviewed: `feature/DRIVE-4-phase2-brain`
Base: `main`
Spec: `driving-copilot-spec.md` v1.7

## Automated checks

| Check | Result |
|-------|--------|
| `uv run ruff check app/services tests` | 0 errors |
| `uv run basedpyright app/services tests` | 0 errors |
| `uv run pytest -q` | 102 passed |

## Focus-area findings

### 1. Spec conformance (Phase 2 scope)

Phase 2 deliverables are present and match the spec:

- Semantic layer (`skill_status`, `pace`, `stale`) implemented in `app/services/semantic.py`.
- Read tools: `get_skill_progress`, `get_gap_analysis`, `get_notes`, `get_pace`.
- Docs stack: `get_cbr_info`, `cbr_search`, `web_search_cbr`.
- Rijprocedure B converted to `knowledge/rijprocedure-b.md` plus four seeded topic files.
- Tavily fallback scoped to `cbr.nl` via `include_domains`.
- Provenance rule #5 is present in `ANSWER_SYSTEM_PROMPT`.
- README and `.env.example` updated for Phase 2.

#### Findings

| # | Severity | Finding | Proposed fix |
|---|----------|---------|--------------|
| 1.1 | **Low** | `ANSWER_SYSTEM_PROMPT` says Daria writes in "Russian, English, and Dutch", but spec v1.7 says she writes Russian/English only and Dutch appears as embedded vocabulary. | Narrow the language rule to "Russian or English (Dutch driving terms may appear embedded in your sentence)". |
| 1.2 | **Low** | `GetGapAnalysisTool` ranks weak before not_started, but the exact "exam weight" ordering is unspecified beyond `exam_relevant` flag + id. | Document the ranking tie-breaker in the spec or add an explicit exam-weight field if future ordering matters. |

### 2. Semantic layer: skill_status / pace / stale

Status: **satisfied**.

- `skill_status`, `pace`, and `is_stale` are defined exactly once in `app/services/semantic.py`.
- Tools call these functions; prompts only describe the definitions for the model.
- No prompt computes status, pace, or stale flags.

No findings.

### 3. Guardrails: containment check & provenance rule #5

Status: **mostly satisfied**.

- `containment_ok` runs on every answer from `_agent_loop`, which now covers `analytics` and `docs` labels.
- `tools_for_label("docs")` returns only docs tools, so the analytics/docs paths share the same guardrail code path.
- Provenance rule #5 is explicitly written into `ANSWER_SYSTEM_PROMPT` rule 5.

#### Findings

| # | Severity | Finding | Proposed fix |
|---|----------|---------|--------------|
| 3.1 | **Medium** | Provenance rule #5 is only enforced by the prompt; the guardrail checks dates/counts/ids but does not verify that a docs answer actually carries one of the three required provenance prefixes. | Add a code-level provenance marker check for answers on the `docs` path (or at minimum assert it in the live smoke / eval suite). |
| 3.2 | **Low** | Unit tests for `containment_ok` exist, but there is no integration test proving the guardrail degrades answers on the new `analytics`/`docs` paths when the model invents a date or count. | Add an integration test in `test_phase2_acceptance.py` where a fake LLM emits a fabricated date/count and assert the reply is retried once then prefixed with `⚠️`. |

### 4. Security: web_search_cbr flow & TAVILY key

Status: **satisfied**.

- `tools_for_label("docs")` exposes only `get_cbr_info`, `cbr_search`, `web_search_cbr`; no write tools are in context.
- `TAVILY_API_KEY` is loaded into `WebSearcher` and sent only in the Tavily request body; it is never inserted into prompts or logs.
- `WebSearchError` messages do not include the key.

No findings.

### 5. Test quality

The new tests generally assert behavior, not just "runs without error":

- `test_semantic.py` checks exact status/pace/stale outcomes.
- `test_tools_phase2.py` verifies tool subsets, schemas, and risk tiers.
- `test_knowledge.py` verifies search hits, sources, and file/heading structure.
- `test_web_search.py` verifies Tavily request scoping, HTTP error handling, and result serialization.
- `test_phase2_acceptance.py` checks gap-analysis picture, routing, provenance prefixes, and docs-path tool exposure.

#### Findings

| # | Severity | Finding | Proposed fix |
|---|----------|---------|--------------|
| 5.1 | **Medium** | `test_gap_analysis_weak_ranked_by_exam_weight` asserts `on_track is False or on_track is True`, which is a tautology and does not verify ranking or pace behavior. | Replace with concrete assertions, e.g. all weak skills are `exam_relevant` and the ordering places exam-relevant skills before non-exam-relevant ones. |
| 5.2 | **Low** | No Phase 2 acceptance test exercises the `stale` flag end-to-end via `get_skill_progress`. | Add a test that loads a backfilled solid skill older than 21 days and asserts `stale` is `True`. |
| 5.3 | **Low** | `test_docs_kb_miss_uses_live_fallback_with_label` checks the provenance prefix but does not assert the answer derives from the fake web result content. | Assert the reply contains text from `FakeWebResult.content`. |

## Verdict

**merge after fixes**

The branch is functionally complete for Phase 2, all automated checks pass, and there are no blocking security or architecture issues. The required changes are small test-hardening items (one tautological assertion, one missing provenance runtime check, and a couple of missing edge-case tests). Address the Medium findings before merge; the Low findings can be fixed in the same follow-up commit.
