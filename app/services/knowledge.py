from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

# Knowledge base for the docs stack (spec section 6 / section 9 Phase 2).
#
# Content is seeded at build time from cbr.nl into knowledge/*.md. No vectors:
# the corpus is small, so keyword/heading search is enough (spec: "RAG-lite,
# no vectors needed in v1"). Untrusted web results are a separate, fallback-only
# flow (web_search_cbr) and never merge into this KB.

_CB_RIJPROCEDURE_URL = (
    "https://www.cbr.nl/nl/voor-rijscholen/nl/rijprocedures/rijprocedure-b-1"
)


class CbrTopic(StrEnum):
    """Closed set of get_cbr_info topics (spec section 6 tool registry)."""

    EXAM_STRUCTURE = "exam_structure"
    BIJZONDERE_VERRICHTINGEN = "bijzondere_verrichtingen"
    ASSESSMENT_CRITERIA = "assessment_criteria"
    SELF_REFLECTION = "self_reflection"


# topic -> (filename, title, source url)
_TOPIC_FILES: dict[CbrTopic, tuple[str, str, str]] = {
    CbrTopic.EXAM_STRUCTURE: (
        "cbr-exam-structure.md",
        "CBR Praktijkexamen B — Exam Structure",
        _CB_RIJPROCEDURE_URL,
    ),
    CbrTopic.BIJZONDERE_VERRICHTINGEN: (
        "cbr-bijzondere-verrichtingen.md",
        "CBR Bijzondere Verrichtingen (Special Manoeuvres)",
        _CB_RIJPROCEDURE_URL,
    ),
    CbrTopic.ASSESSMENT_CRITERIA: (
        "cbr-assessment-criteria.md",
        "CBR Assessment Criteria — How Errors Are Scored",
        _CB_RIJPROCEDURE_URL,
    ),
    CbrTopic.SELF_REFLECTION: (
        "cbr-self-reflection.md",
        "CBR Self-Reflection and Independent Driving",
        _CB_RIJPROCEDURE_URL,
    ),
}

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
_BLOCKQUOTE_RE = re.compile(r"^>\s?", re.MULTILINE)
# Words shorter than 3 chars and common stop words are not search tokens.
_STOPWORDS = frozenset(
    {
        "the", "and", "for", "you", "can", "not", "but", "are", "with", "this",
        "that", "how", "what", "when", "where", "who", "why", "have", "has",
        "een", "het", "de", "van", "en", "met", "voor", "dat", "die", "is",
    }
    | {"cb", "nl"}
)


@dataclass(frozen=True)
class KbSection:
    """A heading-anchored chunk of a knowledge file."""

    file: str
    title: str
    source: str
    heading: str
    level: int
    body: str


@dataclass(frozen=True)
class KbMatch:
    """A search hit returned by cbr_search."""

    file: str
    heading: str
    source: str
    snippet: str


def _tokenize(query: str) -> list[str]:
    out: list[str] = []
    for raw in re.findall(r"[A-Za-z0-9\u00C0-\u024F]+", query.lower()):
        if len(raw) < 3 or raw in _STOPWORDS:
            continue
        out.append(raw)
    return out


def _split_sections(text: str, file: str, source: str) -> list[KbSection]:
    """Split a markdown file into heading-anchored sections.

    The content before the first heading is attached as a level-0 'intro' section
    so that file-level context is searchable too.
    """
    matches = list(_HEADING_RE.finditer(text))
    sections: list[KbSection] = []
    if not matches:
        sections.append(
            KbSection(file=file, title=file, source=source, heading="", level=0, body=text)
        )
        return sections
    if matches[0].start() > 0:
        intro = text[: matches[0].start()].strip()
        if intro:
            sections.append(
                KbSection(file=file, title=file, source=source, heading="", level=0, body=intro)
            )
    title = Path(file).stem
    for i, m in enumerate(matches):
        level = len(m.group(1))
        heading = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections.append(
            KbSection(
                file=file, title=title, source=source,
                heading=heading, level=level, body=body,
            )
        )
    return sections


class KnowledgeBase:
    """Loads and searches the seeded knowledge/ markdown files."""

    def __init__(self, knowledge_dir: Path) -> None:
        self._dir = knowledge_dir
        self._sections: list[KbSection] | None = None
        self._files: dict[str, str] | None = None

    @classmethod
    def default(cls) -> KnowledgeBase:
        from app.config import get_settings

        return cls(get_settings().knowledge_dir)

    def _ensure_loaded(self) -> list[KbSection]:
        if self._sections is not None:
            return self._sections
        sections: list[KbSection] = []
        files: dict[str, str] = {}
        if self._dir.is_dir():
            for path in sorted(self._dir.glob("*.md")):
                raw = path.read_text(encoding="utf-8")
                files[path.name] = raw
                sections.extend(_split_sections(raw, path.name, _CB_RIJPROCEDURE_URL))
        self._sections = sections
        self._files = files
        return sections

    def get_topic(self, topic: str) -> dict[str, object]:
        """Return the full seeded content for a get_cbr_info topic (enum)."""
        try:
            key = CbrTopic(topic)
        except ValueError:
            return {
                "error": (
                    f"unknown topic '{topic}'. Valid: "
                    + ", ".join(t.value for t in CbrTopic)
                )
            }
        filename, title, source = _TOPIC_FILES[key]
        self._ensure_loaded()
        files = self._files or {}
        body = files.get(filename, "")
        return {
            "topic": key.value,
            "title": title,
            "source_url": source,
            "source_type": "kb",
            "content": body,
        }

    def search(self, query: str, limit: int = 5) -> list[KbMatch]:
        """Keyword/heading search over all knowledge files.

        Ranks sections by the number of query tokens they contain (heading hits
        weighted higher). Returns the top `limit` matches with a snippet.
        """
        tokens = _tokenize(query)
        if not tokens:
            return []
        sections = self._ensure_loaded()
        scored: list[tuple[int, KbSection]] = []
        for sec in sections:
            heading_low = sec.heading.lower()
            body_low = sec.body.lower()
            score = 0
            for tok in tokens:
                if tok in heading_low:
                    score += 3
                if tok in body_low:
                    score += 1
            if score > 0:
                scored.append((score, sec))
        scored.sort(key=lambda x: (-x[0], x[1].file, x[1].heading))
        out: list[KbMatch] = []
        for _, sec in scored[:limit]:
            snippet = _strip_quotes(sec.body)[:300]
            out.append(
                KbMatch(
                    file=sec.file,
                    heading=sec.heading or sec.title,
                    source=sec.source,
                    snippet=snippet,
                )
            )
        return out


def _strip_quotes(text: str) -> str:
    return _BLOCKQUOTE_RE.sub("", text).strip()
