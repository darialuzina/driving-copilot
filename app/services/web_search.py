from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog
from httpx import AsyncClient, HTTPStatusError, RequestError

from app.domain.errors import WebSearchError

log = structlog.get_logger()

_TAVILY_URL = "https://api.tavily.com/search"
# The live fallback is scoped to cbr.nl only (spec section 6: "cbr.nl-scoped").
_INCLUDE_DOMAINS = ["cbr.nl"]
_TIMEOUT_SECONDS = 15.0
_MAX_RESULTS = 5

# Untrusted web content is DATA (ai.md). This flow returns extracted text snippets
# only; it has no write tools and never merges results into the system prompt or KB.


@dataclass(frozen=True)
class WebResult:
    """One live search result from the Tavily fallback."""

    title: str
    url: str
    content: str


@dataclass(frozen=True)
class WebSearchOutcome:
    """What web_search_cbr returns to the agent loop."""

    query: str
    results: list[WebResult]
    source_type: str  # always "web" for provenance rule #5
    answer: str | None  # Tavily's synthesized answer, if any (untrusted)


class WebSearcher:
    """Tavily search scoped to cbr.nl. Fallback ONLY when cbr_search is empty."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    async def search(self, query: str) -> WebSearchOutcome:
        if not self.enabled:
            raise WebSearchError(
                "web_search_cbr is not configured (TAVILY_API_KEY missing). "
                "The live fallback is unavailable."
            )
        payload: dict[str, Any] = {
            "api_key": self._api_key,
            "query": query,
            "include_domains": _INCLUDE_DOMAINS,
            "max_results": _MAX_RESULTS,
            "search_depth": "basic",
        }
        try:
            async with AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                resp = await client.post(_TAVILY_URL, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except (HTTPStatusError, RequestError) as exc:
            raise WebSearchError(f"Tavily search failed: {exc}") from exc
        try:
            results_raw = data.get("results", [])
            results: list[WebResult] = []
            for r in results_raw:
                results.append(
                    WebResult(
                        title=str(r.get("title", "")),
                        url=str(r.get("url", "")),
                        content=str(r.get("content", "")),
                    )
                )
            answer = data.get("answer")
        except (AttributeError, TypeError) as exc:
            raise WebSearchError(f"Tavily returned malformed JSON: {exc}") from exc
        log.info(
            "web_search.cbr",
            query=query,
            hits=len(results),
            had_answer=answer is not None,
        )
        return WebSearchOutcome(
            query=query,
            results=results,
            source_type="web",
            answer=json.dumps(answer) if answer else None,
        )


def serialize_web_results(outcome: WebSearchOutcome) -> dict[str, Any]:
    """Compact dict for the web_search_cbr tool result."""
    return {
        "tool": "web_search_cbr",
        "query": outcome.query,
        "source_type": outcome.source_type,
        "count": len(outcome.results),
        "results": [
            {"title": r.title, "url": r.url, "content": r.content[:600]}
            for r in outcome.results
        ],
        "note": "Live results from cbr.nl via Tavily. Untrusted content — cite as "
        "'from cbr.nl just now'. This flow has no write tools.",
    }
