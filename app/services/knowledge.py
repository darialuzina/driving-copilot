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
#
# The Rijprocedure B knowledge base is a verbatim conversion of the official CBR
# PDF (knowledge/sources/rijprocedure-b.pdf) into knowledge/rijprocedure-b.nl.md,
# with a faithful DeepL translation in knowledge/rijprocedure-b.en.md. The two
# files share the document's real section structure (297 sections, taken from the
# PDF's own table of contents) and pair by index. get_toc / get_section expose
# that structure for agentic navigation; cbr_search remains keyword search.

_CB_RIJPROCEDURE_URL = (
    "https://www.cbr.nl/nl/voor-rijscholen/nl/rijprocedures/rijprocedure-b-1"
)
_RIJPROCEDURE_NL = "rijprocedure-b.nl.md"
_RIJPROCEDURE_EN = "rijprocedure-b.en.md"
# Source PDF the verbatim conversion was made from.
_RIJPROCEDURE_SOURCE_PDF = "knowledge/sources/rijprocedure-b.pdf"


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


@dataclass(frozen=True)
class RijprocedureSection:
    """One section of the verbatim Rijprocedure B, paired across nl/en.

    `number` is the REAL section number from the document when the heading
    carries one (e.g. "1", "3.1", "Bijlage 1"); empty string for the many
    unnumbered named sub-sections. Citations use `number` when present, else
    the heading path (e.g. "Toepassing hoofdstuk 1 — Bediening koppeling").
    """

    id: str
    level: int
    number: str
    title_nl: str
    title_en: str
    body_nl: str
    body_en: str


_NUM_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+")


def _section_number(title_nl: str) -> str:
    """Extract the real section number from a Dutch heading, if present."""
    if title_nl.lower().startswith("bijlage"):
        return title_nl.strip()
    m = _NUM_RE.match(title_nl)
    return m.group(1) if m else ""


def _parse_headings(text: str) -> list[tuple[int, str, str]]:
    """Split markdown into (level, title, body) sections in reading order.
    The body is the text between this heading and the next heading."""
    lines = text.split("\n")
    out: list[tuple[int, str, list[str]]] = []
    cur: tuple[int, str, list[str]] | None = None
    for ln in lines:
        m = _HEADING_RE.match(ln)
        if m:
            if cur is not None:
                out.append(cur)
            cur = (len(m.group(1)), m.group(2).strip(), [])
        elif cur is not None:
            cur[2].append(ln)
    if cur is not None:
        out.append(cur)
    return [(lvl, title, "\n".join(body).strip()) for lvl, title, body in out]


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
        self._rijprocedure: list[RijprocedureSection] | None = None

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
        """Return the full seeded content for a get_cbr_info topic (enum).

        The topic files are verbatim excerpts of the Rijprocedure B PDF plus a
        DeepL English translation, with the cbr.nl source URL and the fetch date
        recorded in their header.
        """
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
        fetch_match = re.search(r"^>\s*Fetched:\s*(.+)$", body, re.MULTILINE)
        return {
            "topic": key.value,
            "title": title,
            "source_url": source,
            "source_pdf": _RIJPROCEDURE_SOURCE_PDF,
            "fetch_date": fetch_match.group(1).strip() if fetch_match else None,
            "source_type": "kb",
            "content": body,
        }

    def _ensure_rijprocedure(self) -> list[RijprocedureSection]:
        """Parse and cache the paired nl/en Rijprocedure B sections.

        The first heading in each file is the document title (not a TOC section)
        and is dropped; the remaining 297 sections pair by index.
        """
        if self._rijprocedure is not None:
            return self._rijprocedure
        nl_path = self._dir / _RIJPROCEDURE_NL
        en_path = self._dir / _RIJPROCEDURE_EN
        if not nl_path.exists() or not en_path.exists():
            self._rijprocedure = []
            return self._rijprocedure
        nl_secs = _parse_headings(nl_path.read_text(encoding="utf-8"))
        en_secs = _parse_headings(en_path.read_text(encoding="utf-8"))
        # Drop the document-title heading (first in each file).
        nl_secs = nl_secs[1:]
        en_secs = en_secs[1:]
        paired: list[RijprocedureSection] = []
        n = min(len(nl_secs), len(en_secs))
        for i in range(n):
            lvl_nl, title_nl, body_nl = nl_secs[i]
            _lvl_en, title_en, body_en = en_secs[i]
            paired.append(
                RijprocedureSection(
                    id=f"s{i + 1:03d}",
                    level=lvl_nl,
                    number=_section_number(title_nl),
                    title_nl=title_nl,
                    title_en=title_en,
                    body_nl=body_nl,
                    body_en=body_en,
                )
            )
        self._rijprocedure = paired
        return paired

    def get_toc(self) -> dict[str, object]:
        """The full section tree of the Rijprocedure B: ids + titles (en + nl)
        + real section number, in document order."""
        sections = self._ensure_rijprocedure()
        return {
            "source_url": _CB_RIJPROCEDURE_URL,
            "source_pdf": _RIJPROCEDURE_SOURCE_PDF,
            "section_count": len(sections),
            "sections": [
                {
                    "id": s.id,
                    "level": s.level,
                    "number": s.number,
                    "title_nl": s.title_nl,
                    "title_en": s.title_en,
                }
                for s in sections
            ],
        }

    def get_section(self, section_id: str) -> dict[str, object]:
        """Return one section's verbatim en + nl text + real section number."""
        sections = self._ensure_rijprocedure()
        for s in sections:
            if s.id == section_id:
                return {
                    "id": s.id,
                    "level": s.level,
                    "number": s.number,
                    "title_nl": s.title_nl,
                    "title_en": s.title_en,
                    "body_nl": s.body_nl,
                    "body_en": s.body_en,
                    "source_url": _CB_RIJPROCEDURE_URL,
                    "source_pdf": _RIJPROCEDURE_SOURCE_PDF,
                    "source_type": "kb",
                }
        return {
            "error": (
                f"unknown section_id '{section_id}'. Use get_toc() for the list "
                "of ids (s001..s" + f"{len(sections):03d}" + ")."
            )
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
