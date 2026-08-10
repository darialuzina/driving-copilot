"""Build knowledge/rijprocedure-b.en.md from the verbatim .nl.md via the DeepL API.

Machine translation only — no LLM in the translation path. Translates section by
section (heading + body lines in one DeepL call per section), preserving the
exact section structure of rijprocedure-b.nl.md so the two files pair by index.

Official Dutch manoeuvre proper-names are forced via a DeepL glossary for
consistency, and the first occurrence of each glossary term in the English
output is annotated with the Dutch term in parentheses, e.g.
"special manoeuvres (bijzondere verrichtingen)".

DeepL free endpoint, EN-GB target. If DEEPL_API_KEY is missing or the API fails
on the first request, the script exits non-zero and prints nothing invented.

Output: knowledge/rijprocedure-b.en.md
"""

from __future__ import annotations

import contextlib
import os
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

NL_MD = Path("knowledge/rijprocedure-b.nl.md")
EN_MD = Path("knowledge/rijprocedure-b.en.md")
FREE = "https://api-free.deepl.com/v2"

# Dutch term -> canonical English (forced via glossary). Proper-name manoeuvres
# only: unambiguous, not context-dependent. The English form is reused for the
# first-use parenthetical annotation in the output.
GLOSSARY: list[tuple[str, str]] = [
    ("bijzondere verrichtingen", "special manoeuvres"),
    ("fileparkeren", "parallel parking"),
    ("parkeren in een haaks of schuin vak", "parking in a perpendicular or diagonal bay"),
    ("achteruit rijden van een bocht", "reversing in a curve"),
    ("in rechte lijn achteruit rijden", "reversing in a straight line"),
    ("omkeren door te steken", "turning around by crossing"),
    ("omkeren door een halve draai", "turning around by a half turn"),
    ("hellingproef", "hill start"),
    ("stopopdracht", "stopping assignment"),
]

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _entries_tsv() -> str:
    seen: set[str] = set()
    rows: list[str] = []
    for nl, en in GLOSSARY:
        if nl in seen:
            continue
        seen.add(nl)
        rows.append(f"{nl}\t{en}")
    return "\n".join(rows) + "\n"


def create_glossary(client: httpx.Client, key: str) -> str:
    r = client.post(
        f"{FREE}/glossaries",
        headers={"Authorization": f"DeepL-Auth-Key {key}"},
        data={
            "name": "driving-copilot-rijprocedure-b",
            "source_lang": "NL",
            "target_lang": "EN",
            "entries": _entries_tsv(),
            "entries_format": "tsv",
        },
        timeout=30,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"glossary create failed: {r.status_code} {r.text}")
    return r.json()["glossary_id"]


def delete_glossary(client: httpx.Client, key: str, gid: str) -> None:
    with contextlib.suppress(httpx.HTTPError):
        client.delete(
            f"{FREE}/glossaries/{gid}",
            headers={"Authorization": f"DeepL-Auth-Key {key}"},
            timeout=30,
        )


def translate_lines(
    client: httpx.Client, key: str, gid: str, lines: list[str]
) -> list[str]:
    """Translate a batch of non-empty lines in one DeepL call."""
    if not lines:
        return []
    data = {
        "text": lines,
        "source_lang": "NL",
        "target_lang": "EN-GB",
        "glossary_id": gid,
        "split_sentences": "1",
    }
    for attempt in range(4):
        r = client.post(
            f"{FREE}/translate",
            headers={"Authorization": f"DeepL-Auth-Key {key}"},
            data=data,
            timeout=60,
        )
        if r.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        if r.status_code != 200:
            raise RuntimeError(f"translate failed: {r.status_code} {r.text[:300]}")
        return [t["text"] for t in r.json()["translations"]]
    raise RuntimeError("translate failed: repeated 429")


def parse_sections(text: str) -> tuple[list[str], list[tuple[int, str, list[str]]]]:
    """Return (front_matter_lines, sections) where each section is
    (level, title, body_lines). The front matter is everything before the
    first TOC heading '# Inleiding'."""
    lines = text.split("\n")
    front: list[str] = []
    i = 0
    # skip until the first '# Inleiding' heading
    while i < len(lines):
        if lines[i].startswith("# Inleiding"):
            break
        front.append(lines[i])
        i += 1
    sections: list[tuple[int, str, list[str]]] = []
    cur: tuple[int, str, list[str]] | None = None
    while i < len(lines):
        ln = lines[i]
        m = HEADING_RE.match(ln)
        if m:
            if cur is not None:
                sections.append(cur)
            cur = (len(m.group(1)), m.group(2).strip(), [])
        else:
            if cur is not None:
                cur[2].append(ln)
        i += 1
    if cur is not None:
        sections.append(cur)
    return front, sections


def annotate_first_use(english_text: str) -> str:
    """On first document occurrence of each glossary English term, append the
    Dutch term in parentheses. Deterministic, code-only."""
    out = english_text
    for nl, en in GLOSSARY:
        idx = out.lower().find(en.lower())
        if idx == -1:
            continue
        # find the exact-cased occurrence window
        window = out[idx : idx + len(en)]
        annotated = f"{window} ({nl})"
        out = out[:idx] + annotated + out[idx + len(en) :]
    return out


def main() -> int:
    load_dotenv()
    key = os.environ.get("DEEPL_API_KEY", "")
    if not key:
        print("DEEPL_API_KEY missing — not translating.", file=sys.stderr)
        return 1
    if not NL_MD.exists():
        print(f"missing {NL_MD}", file=sys.stderr)
        return 1
    nl_text = NL_MD.read_text(encoding="utf-8")
    front, sections = parse_sections(nl_text)
    if not sections:
        print("no sections parsed from nl.md", file=sys.stderr)
        return 1

    client = httpx.Client()
    gid = ""
    try:
        # one connectivity check + glossary creation
        gid = create_glossary(client, key)
        out_lines: list[str] = list(front)
        # translate the document title line if present in front matter
        title_idx = next((k for k, v in enumerate(front) if v.startswith("# ")), None)
        if title_idx is not None:
            t = front[title_idx][2:].strip()
            en_t = translate_lines(client, key, gid, [t])[0] if t else ""
            out_lines[title_idx] = f"# {en_t}"

        n = len(sections)
        for i, (level, title, body) in enumerate(sections):
            # collect non-empty body lines to translate; keep blank-line structure
            to_translate: list[str] = [title] + [b for b in body if b.strip()]
            translated = translate_lines(client, key, gid, to_translate)
            en_title = translated[0]
            body_iter = iter(translated[1:])
            out_lines.append("")
            out_lines.append(f"{'#' * level} {en_title}")
            out_lines.append("")
            for b in body:
                if b.strip():
                    out_lines.append(next(body_iter, b))
                else:
                    out_lines.append("")
            if (i + 1) % 25 == 0:
                print(f"  translated {i + 1}/{n} sections", file=sys.stderr)
        en_text = "\n".join(out_lines) + "\n"
        en_text = annotate_first_use(en_text)
        EN_MD.write_text(en_text, encoding="utf-8")
        print(f"wrote {EN_MD} ({n} sections)")
        return 0
    finally:
        if gid:
            delete_glossary(client, key, gid)
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
