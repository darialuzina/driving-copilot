"""Build knowledge/rijprocedure-b.nl.md verbatim from the official CBR PDF.

The PDF (knowledge/sources/rijprocedure-b.pdf) carries an embedded table of
contents (297 entries) that IS the real section structure of the document.
This script uses that TOC as the authoritative heading tree and slices the
page text verbatim between consecutive headings — no paraphrasing, no
reordering, no invented headings. Within-paragraph line wraps (a PDF layout
artifact) are reflowed into paragraphs; bullet markers and paragraph breaks
are preserved. Page footers/numbers are stripped.

Output: knowledge/rijprocedure-b.nl.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pymupdf

PDF = Path("knowledge/sources/rijprocedure-b.pdf")
OUT = Path("knowledge/rijprocedure-b.nl.md")

FOOTER_RE = re.compile(r"^©CBR\s*-\s*Rijprocedure B\s*–\s*versie\s*-\s*juli\s*2026\s*$")
BULLET_MARKERS = frozenset({"−", "•", "–", "-", "·", "—"})


def clean_page(raw: str) -> str:
    """Strip the recurring footer line and the standalone page-number line."""
    lines = raw.split("\n")
    out: list[str] = []
    skip_next_number = False
    for ln in lines:
        if FOOTER_RE.match(ln.strip()):
            skip_next_number = True
            continue
        if skip_next_number and re.fullmatch(r"\s*\d+\s*", ln):
            skip_next_number = False
            continue
        skip_next_number = False
        out.append(ln)
    return "\n".join(out)


def normalize(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace runs to a single space; map each normalized char
    back to its index in the original text (space maps to the first ws char)."""
    norm_chars: list[str] = []
    orig_pos: list[int] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            j = i
            while j < n and text[j].isspace():
                j += 1
            if norm_chars and norm_chars[-1] != " ":
                norm_chars.append(" ")
                orig_pos.append(i)
            i = j
        else:
            norm_chars.append(c)
            orig_pos.append(i)
            i += 1
    # trim leading/trailing space
    while norm_chars and norm_chars[0] == " ":
        norm_chars.pop(0)
        orig_pos.pop(0)
    while norm_chars and norm_chars[-1] == " ":
        norm_chars.pop()
        orig_pos.pop()
    return "".join(norm_chars), orig_pos


def reflow_body(body: str) -> str:
    """Reflow PDF line wraps into paragraphs; preserve bullet items and
    paragraph breaks. Words and order are unchanged (verbatim)."""
    lines = body.split("\n")
    out: list[str] = []
    para: list[str] = []

    def flush_para() -> None:
        if para:
            out.append(" ".join(para))
            para.clear()

    i = 0
    while i < len(lines):
        ln = lines[i]
        stripped = ln.strip()
        if not stripped:
            flush_para()
            i += 1
            continue
        first = stripped[0]
        # A bullet marker on its own line, or starting a line.
        if first in BULLET_MARKERS:
            flush_para()
            rest = stripped[1:].strip()
            marker = first
            # marker alone on its line -> text continues on following lines
            if not rest:
                text_parts: list[str] = []
                i += 1
                while i < len(lines):
                    nxt = lines[i].strip()
                    if not nxt:
                        break
                    if nxt[0] in BULLET_MARKERS:
                        break
                    text_parts.append(nxt)
                    i += 1
                out.append(f"{marker} " + " ".join(text_parts) if text_parts else marker)
                continue
            # marker + text on same line; gather wrapped continuation
            text_parts = [rest]
            i += 1
            while i < len(lines):
                nxt = lines[i].strip()
                if not nxt or nxt[0] in BULLET_MARKERS:
                    break
                text_parts.append(nxt)
                i += 1
            out.append(f"{marker} " + " ".join(text_parts))
            continue
        # normal paragraph line
        para.append(stripped)
        i += 1
    flush_para()
    return "\n".join(out)


def main() -> int:
    if not PDF.exists():
        print(f"missing {PDF}", file=sys.stderr)
        return 1
    doc = pymupdf.open(PDF)
    toc = doc.get_toc()  # [[level, title, page(1-indexed)], ...]
    pages = [clean_page(doc[i].get_text()) for i in range(doc.page_count)]
    full = "\n".join(pages)
    norm, orig_pos = normalize(full)

    # Starting char offset (in `full`) of each PDF page, 1-indexed by page number.
    page_start: list[int] = [0]
    offset = 0
    for p in pages:
        page_start.append(offset)
        offset += len(p) + 1  # +1 for the "\n" join separator

    def norm_offset_for(orig: int) -> int:
        """Approx normalized index for an original-text offset."""
        # Binary search in orig_pos for the first entry >= orig.
        import bisect

        k = bisect.bisect_left(orig_pos, orig)
        return min(k, len(orig_pos))

    # Find each heading in order within the normalized text, constrained to the
    # heading's own page (so the printed Inhoudsopgave duplicates, which sit on
    # earlier pages, are skipped).
    cursor = 0
    spans: list[tuple[int, int]] = []  # (norm_start, norm_end) per toc entry
    for _lvl, title, page in toc:
        ntitle, _ = normalize(title)
        search_from = max(cursor, norm_offset_for(page_start[page]))
        start = norm.find(ntitle, search_from)
        if start == -1:
            # fall back: try without a trailing period, still page-constrained
            alt = ntitle.rstrip(".").rstrip()
            start = norm.find(alt, search_from)
            if start == -1:
                # last resort: search from cursor (page map may be off by a footer)
                start = norm.find(alt if alt else ntitle, cursor)
                if start == -1:
                    print(f"heading not found: {title!r} (page={page})", file=sys.stderr)
                    return 2
            ntitle = alt
        end = start + len(ntitle)
        spans.append((start, end))
        cursor = end

    # Map normalized span ends back to original indices; slice bodies.
    def orig_index(norm_idx: int) -> int:
        if norm_idx >= len(orig_pos):
            return len(full)
        return orig_pos[norm_idx]

    lines_out: list[str] = [
        "# Rijprocedure B — Personenauto",
        "",
        "> Source: CBR, *Rijprocedure personenauto (B)*, versie juli 2026.",
        "> URL: https://www.cbr.nl/nl/voor-rijscholen/nl/rijprocedures/rijprocedure-b-1",
        "> Verbatim conversion of the official PDF (knowledge/sources/rijprocedure-b.pdf).",
        "> Section structure and numbering follow the document's own table of contents.",
        "",
    ]
    for idx, (lvl, title, _page) in enumerate(toc):
        _nstart, nend = spans[idx]
        body_start = orig_index(nend)
        body_end = orig_index(spans[idx + 1][0]) if idx + 1 < len(spans) else len(full)
        body = full[body_start:body_end]
        body = reflow_body(body).strip()
        heading_level = min(lvl, 6)
        lines_out.append("")
        lines_out.append(f"{'#' * heading_level} {title.strip()}")
        lines_out.append("")
        if body:
            lines_out.append(body)
    OUT.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(toc)} sections)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
