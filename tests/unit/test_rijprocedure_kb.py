"""Mechanical verification of the verbatim Rijprocedure B knowledge base
(DRIVE-4b, spec task point 5). No language judgment — these tests fail if
headings were synthesized, if text was paraphrased/summarized, or if the nl/en
section trees diverge."""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast

import pymupdf
import pytest

from app.services.knowledge import KnowledgeBase

KNOWLEDGE = Path("knowledge")
PDF = KNOWLEDGE / "sources" / "rijprocedure-b.pdf"
NL_MD = KNOWLEDGE / "rijprocedure-b.nl.md"
EN_MD = KNOWLEDGE / "rijprocedure-b.en.md"

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@pytest.fixture(scope="module")
def pdf_text() -> str:
    doc = pymupdf.open(PDF)
    # pymupdf ships no type stubs; page_count/get_text are untyped.
    count = cast(int, doc.page_count)  # pyright: ignore[reportUnknownMemberType]
    pages = [cast(str, doc[i].get_text()) for i in range(count)]  # pyright: ignore[reportUnknownMemberType]
    return "\n".join(pages)


@pytest.fixture(scope="module")
def pdf_norm(pdf_text: str) -> str:
    return _norm(pdf_text)


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return KnowledgeBase(KNOWLEDGE)


# 5a: every heading in rijprocedure-b.nl.md exists as a text string in the PDF
#     extraction (structure fidelity — synthesized headings fail).
def test_5a_every_heading_exists_in_pdf(pdf_norm: str) -> None:
    text = NL_MD.read_text(encoding="utf-8")
    headings = [m.group(2).strip() for m in _HEADING_RE.finditer(text)]
    # Drop the document-title heading (it is the file's H1, not a PDF heading).
    headings = headings[1:]
    assert headings, "expected headings in nl.md"
    missing: list[str] = []
    for h in headings:
        if _norm(h) not in pdf_norm:
            missing.append(h)
    assert not missing, f"headings not found verbatim in PDF: {missing[:5]}"


# 5c: section count identical between .nl.md and .en.md.
def test_5c_section_count_identical_nl_en() -> None:
    nl_headings = _HEADING_RE.findall(NL_MD.read_text(encoding="utf-8"))
    en_headings = _HEADING_RE.findall(EN_MD.read_text(encoding="utf-8"))
    assert len(nl_headings) == len(en_headings), (
        f"heading count mismatch: nl={len(nl_headings)} en={len(en_headings)}"
    )
    # And the levels pair 1:1 (same structure).
    for i, (nl, en) in enumerate(zip(nl_headings, en_headings, strict=True)):
        assert len(nl[0]) == len(en[0]), f"level mismatch at heading {i}: {nl!r} vs {en!r}"


# 5b: per-section length ratio nl vs en within 0.7–1.6 (paraphrase/summarization
#     fails). Dutch and English are comparable in length for faithful MT.
def _split_sections(text: str) -> list[tuple[str, int]]:
    matches = list(_HEADING_RE.finditer(text))
    out: list[tuple[str, int]] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        out.append((m.group(2).strip(), len(body)))
    return out


def test_5b_section_length_ratio_within_bounds() -> None:
    nl_secs = _split_sections(NL_MD.read_text(encoding="utf-8"))
    en_secs = _split_sections(EN_MD.read_text(encoding="utf-8"))
    assert len(nl_secs) == len(en_secs)
    out_of_range: list[str] = []
    # Skip sections whose body is very short (headings, grouping titles) — the
    # ratio is unstable there and not a paraphrase signal.
    for (title, nl_len), (_en_title, en_len) in zip(nl_secs, en_secs, strict=True):
        if nl_len < 120 or en_len < 120:
            continue
        ratio = nl_len / en_len
        if not 0.7 <= ratio <= 1.6:
            out_of_range.append(f"{title!r}: nl={nl_len} en={en_len} ratio={ratio:.2f}")
    assert not out_of_range, f"length-ratio violations: {out_of_range[:5]}"


# get_toc / get_section round-trip: the TOC section count matches the file
# heading count, and get_section returns paired nl+en verbatim text.
def test_get_toc_section_count_matches_files(kb: KnowledgeBase) -> None:
    toc = kb.get_toc()
    nl_headings = _HEADING_RE.findall(NL_MD.read_text(encoding="utf-8"))
    # 297 TOC sections = file headings minus the document-title heading.
    assert toc["section_count"] == len(nl_headings) - 1
    assert toc["section_count"] == 297


def test_get_section_returns_paired_nl_en(kb: KnowledgeBase) -> None:
    sec = kb.get_section("s183")  # 3.7 Bijzondere verrichtingen
    assert str(sec["number"]) == "3.7"
    assert "Bijzondere verrichtingen" in str(sec["title_nl"])
    assert str(sec["body_nl"]).strip() != ""
    assert str(sec["body_en"]).strip() != ""
    assert str(sec["source_url"]).startswith("https://www.cbr.nl")


def test_get_section_unknown_id_returns_structured_error(kb: KnowledgeBase) -> None:
    result = kb.get_section("s999")
    assert "error" in result
    assert "get_toc" in str(result["error"])


def test_get_section_carry_real_numbers(kb: KnowledgeBase) -> None:
    toc = kb.get_toc()
    sections = cast(list[dict[str, object]], toc["sections"])
    by_id = {str(s["id"]): s for s in sections}
    # Numbered sections keep their real number.
    assert str(by_id["s003"]["number"]) == "1"  # "1. Rijklaar maken..."
    assert str(by_id["s040"]["number"]) == "3.1"  # "3.1 Wegrijden"
    assert str(by_id["s183"]["number"]) == "3.7"  # "3.7 Bijzondere verrichtingen"
    # Unnumbered named sections carry an empty number (cite by heading path).
    assert str(by_id["s001"]["number"]) == ""  # Inleiding
