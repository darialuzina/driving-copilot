"""Rebuild the seeded cbr.* topic files as verbatim excerpts of the Rijprocedure B
knowledge base + their DeepL translation, with source URL and fetch date.

This replaces the previous paraphrased English summaries (DRIVE-4b): the
get_cbr_info topics now return verbatim Dutch text from the official CBR PDF
plus the matching English translation, with the cbr.nl source URL and the date
the source was fetched. No paraphrasing.

Each topic maps to one or more real sections of the Rijprocedure B; the excerpt
includes the target section and all of its sub-sections (descendants in the
document's own table of contents).

Output: knowledge/cbr-exam-structure.md, cbr-bijzondere-verrichtingen.md,
cbr-assessment-criteria.md, cbr-self-reflection.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import httpx

KNOWLEDGE = Path("knowledge")
NL_MD = KNOWLEDGE / "rijprocedure-b.nl.md"
EN_MD = KNOWLEDGE / "rijprocedure-b.en.md"
SOURCE_URL = "https://www.cbr.nl/nl/voor-rijscholen/nl/rijprocedures/rijprocedure-b-1"
SOURCE_PDF = "knowledge/sources/rijprocedure-b.pdf"

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _parse_headings(text: str) -> list[tuple[int, str, str]]:
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

# topic -> (filename, english title, [(level, dutch_title), ...])
TOPICS: dict[str, tuple[str, str, list[tuple[int, str]]]] = {
    "exam_structure": (
        "cbr-exam-structure.md",
        "CBR Practical Exam B — Exam Structure",
        [(1, "Inleiding"), (1, "Bijlage 1")],
    ),
    "bijzondere_verrichtingen": (
        "cbr-bijzondere-verrichtingen.md",
        "CBR Bijzondere Verrichtingen (Special Manoeuvres)",
        [(2, "3.7 Bijzondere verrichtingen")],
    ),
    "assessment_criteria": (
        "cbr-assessment-criteria.md",
        "CBR Assessment Criteria — How Errors Are Scored",
        [(1, "Toepassing")],
    ),
    "self_reflection": (
        "cbr-self-reflection.md",
        "CBR Self-Reflection and Independent Driving",
        [(1, "Inleiding"), (1, "2. Op juiste en veilige wijze deelnemen aan het verkeer")],
    ),
}


def fetch_date() -> str:
    """Confirm the cbr.nl source page is reachable and record today's date."""
    try:
        r = httpx.get(SOURCE_URL, timeout=30, follow_redirects=True)
        if r.status_code != 200:
            print(f"warn: cbr.nl source returned {r.status_code}", file=sys.stderr)
    except httpx.HTTPError as exc:
        print(f"warn: cbr.nl fetch failed: {exc}", file=sys.stderr)
    from datetime import date

    return date.today().isoformat()


def find_ranges(
    sections: list[tuple[int, str, str]], targets: list[tuple[int, str]]
) -> list[tuple[int, int]]:
    """Return (start, end) index ranges for each target section + descendants,
    searched in order over the Dutch section list."""
    ranges: list[tuple[int, int]] = []
    i = 0
    n = len(sections)
    for tgt_level, tgt_title in targets:
        while i < n:
            lvl, title, _body = sections[i]
            if lvl == tgt_level and title == tgt_title:
                break
            i += 1
        if i >= n:
            print(f"warn: target section not found: {tgt_title!r}", file=sys.stderr)
            continue
        start = i
        i += 1
        while i < n and sections[i][0] > tgt_level:
            i += 1
        ranges.append((start, i))
    return ranges


def render(sections: list[tuple[int, str, str]], start: int, end: int) -> str:
    out: list[str] = []
    for lvl, title, body in sections[start:end]:
        out.append("")
        out.append(f"{'#' * lvl} {title}")
        out.append("")
        if body:
            out.append(body)
    return "\n".join(out).strip()


def main() -> int:
    if not NL_MD.exists() or not EN_MD.exists():
        print("missing rijprocedure-b.nl.md / .en.md", file=sys.stderr)
        return 1
    nl_secs = _parse_headings(NL_MD.read_text(encoding="utf-8"))[1:]  # drop doc title
    en_secs = _parse_headings(EN_MD.read_text(encoding="utf-8"))[1:]
    fetched = fetch_date()
    for topic, (filename, title_en, targets) in TOPICS.items():
        ranges = find_ranges(nl_secs, targets)
        nl_part = "\n\n".join(render(nl_secs, s, e) for s, e in ranges)
        en_part = "\n\n".join(render(en_secs, s, e) for s, e in ranges)
        content = "\n".join(
            [
                f"# {title_en}",
                "",
                "> Source: CBR, *Rijprocedure personenauto (B)*, versie juli 2026.",
                f"> URL: {SOURCE_URL}",
                f"> Source PDF: {SOURCE_PDF}",
                f"> Fetched: {fetched}",
                "> Verbatim excerpt from the official CBR Rijprocedure B PDF, with a",
                "> DeepL English translation. Section numbering is the document's own.",
                "",
                "## Nederlands (verbatim)",
                "",
                nl_part,
                "",
                "## English (DeepL translation)",
                "",
                en_part,
                "",
            ]
        )
        (KNOWLEDGE / filename).write_text(content, encoding="utf-8")
        print(f"wrote {filename} ({topic})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
