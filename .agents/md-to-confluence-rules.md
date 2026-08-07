# Markdown → Confluence Wiki — rules and pitfalls

> Cheat-sheet for converting Markdown documents to Confluence Wiki Markup format (aka Jira format) using `pandoc` + post-processing.
>
> Context: a project with many `.md` files (documentation, ADRs, onboarding docs) that need to be imported into Confluence via the Markup macro. Learned the hard way — every pattern in the tables below actually broke the import of at least one page.
>
> Applies to Confluence Data Center / Server (legacy editor with the Markup macro). In Confluence Cloud the Markup macro is **deprecated as of April 2026** — there, it is better to use the `/markdown` slash command directly with the original `.md`.

## Contents

- [Pipeline overview](#pipeline-overview)
- [Pandoc-jira command](#pandoc-jira-command)
- [The main rule: what Confluence parses inside inline code](#the-main-rule-what-confluence-parses-inside-inline-code)
- [Replacement table — pair markers](#replacement-table--pair-markers)
- [Replacement table — macro symbols and HTML](#replacement-table--macro-symbols-and-html)
- [Anti-patterns in source .md](#anti-patterns-in-source-md)
- [Mermaid diagrams](#mermaid-diagrams)
- [Full pipeline script](#full-pipeline-script)
- [Anti-patterns (do not do this)](#anti-patterns-do-not-do-this)
- [Checklist: .md readiness for import](#checklist-md-readiness-for-import)

## Pipeline overview

```
.md  →  preprocess (mermaid → text)  →  pandoc -t jira  →  sed (theme)  →  clean-escapes.py  →  .txt
        │                                │                  │              │
        │                                │                  │              ├── inside {{...}}: pair-marker Unicode replacement
        │                                │                  │              ├── inside {{...}}: { } → entities
        │                                │                  │              ├── inside {{...}}: < > → ⟨ ⟩
        │                                │                  │              ├── inside {code}: strip \\X
        │                                │                  │              └── outside: remove redundant \\X
        │                                │                  │
        │                                │                  └── set the syntax-highlighting theme (Eclipse / Confluence)
        │                                │
        │                                └── markdown → Jira wiki markup
        │
        └── ```mermaid → ```text (so pandoc does not try to parse it as Java)
```

## Pandoc-jira command

Base invocation:

```bash
pandoc input.md -t jira --wrap=none
```

**The key flag is `--wrap=none`** — without it pandoc inserts line breaks every 72 characters, and Jira renders them as real `<br/>`. The text breaks.

The remaining steps are pre-process and post-process. Post-process is critical (see tables below).

## The main rule: what Confluence parses inside inline code

In Markdown, a ``single backtick`` is turned by pandoc into `{{...}}` (Jira inline code).

**A common misconception:** "Confluence does not parse anything inside inline code."

**The truth:** the Confluence wiki parser **keeps looking for pair markers** of markup even inside `{{...}}` — `*bold*`, `_italic_`, `-strikethrough-`, and so on. And these pairs can **cross the boundaries** of different `{{...}}` blocks!

Example of a broken case:

```
* Getters use {{get_*}}, setters use {{set_*}}.
```

The parser sees the first `*` in `{{get_*}}` as opening bold → the text between them → the second `*` in `{{set_*}}` as closing bold. The `*...*` pair formed across the boundaries of `{{...}}` blocks. The rendering breaks.

In Markdown, triple backticks (a ` ``` ` block) become `{code:...}{code}` — there Confluence **really** does not parse anything. The content is rendered literally. That is why Python code with `<`, `*`, `_` inside triple backticks **works** without problems.

**Conclusion:** all pre-processing rules apply **only inside `{{...}}`**, not inside `{code}` blocks.

## Replacement table — pair markers

Confluence Wiki interprets these characters as paired markup. Inside `{{...}}`, replace them with Unicode equivalents — they look almost identical, but the parser does not interpret them.

| Wiki character | Meaning in Confluence | Unicode replacement | Codepoint |
|---|---|---|---|
| `*bold*` | bold | `∗` | U+2217 ASTERISK OPERATOR |
| `_italic_` | italic | (rewrite the pattern in the `.md`) | — |
| `-strikethrough-` | strikethrough | `−` | U+2212 MINUS SIGN |
| `+underline+` | underline | `＋` | U+FF0B FULLWIDTH PLUS SIGN |
| `~subscript~` | subscript | `∼` | U+223C TILDE OPERATOR |
| `^superscript^` | superscript | `ˆ` | U+02C6 MODIFIER LETTER CIRCUMFLEX |

### Why `_italic_` cannot be replaced automatically

The underscore is used inside identifiers (`snake_case`, `crawl_tasks`, `user_id`). If you replace all `_` with Unicode, copy-paste from the documentation will no longer work as Python code.

**Solution:** manually rewrite the dangerous patterns in the source `.md`:

- ❌ `<a>_<b>_links` (inline backtick) — `_⟨b⟩_` creates an italic pair
- ✅ `tableA_tableB_links` — camelCase placeholders, no underscores between placeholders

This only concerns **placeholders of the form `<X>_<Y>`** inside single backticks. Real Python identifiers (`crawl_tasks`) are safe — there is no pair around a short word.

## Replacement table — macro symbols and HTML

Confluence interprets these characters as macros or HTML tags — even **inside inline code `{{...}}`**.

| Character | Meaning in Confluence | Replacement inside `{{...}}` | Why |
|---|---|---|---|
| `<X>` | HTML tag (`<a>`, `<b>`, `<i>`, etc.) | `⟨X⟩` (Unicode U+27E8 / U+27E9) | Confluence normalizes `&lt;X&gt;` HTML entities **back** into `<X>` before parsing — so entities do not help. Only Unicode |
| `{Y}` | macro invocation | `&#123;Y&#125;` (HTML entities) | For curly braces, entities are **not** normalized back — this trick works |
| `\` (backslash) before an ordinary character | redundant escape from pandoc | remove the backslash | pandoc-jira escapes `\\(`, `\\)`, `\\-`, `\\!`, etc. just in case — Confluence chokes on it |

### Pandoc escape patterns that MUST be stripped

Pandoc-jira adds a backslash before:

- `\\(` `\\)` — parentheses (not reactive in Confluence wiki) → strip
- `\\-` — hyphen → strip
- `\\+` — plus → strip
- `\\&` — ampersand → strip
- `\\.` — period → strip

### Named HTML entities pandoc generates for special chars

Pandoc-jira converts a **literal backslash** (when the `.md` contains `\\` to produce a single `\`) into the HTML entity `&bsol;`. This is a valid HTML5 entity. **Confluence interprets it back**, which is usually OK for a single one, but **two in a row `&bsol;&bsol;`** break the parser (common in regex patterns with `\\.`, `\\d`, `\\s`).

| What pandoc generates | Replace with | Codepoint | When it appears |
|---|---|---|---|
| `&bsol;` | `⧵` Unicode | U+29F5 REVERSE SOLIDUS OPERATOR | regex patterns (`\\.`, `\\d`, `\\w`), Python f-strings, any literal `\` |
| `&sol;` | `/` literal | — | rare, slash escape |
| `&num;` | `#` literal | — | rare, hash escape |

### Pandoc escape patterns that must NOT be stripped (needed outside code)

- `\\_` — underscore (so it does not become italic)
- `\\[` `\\]` — square brackets (so they do not become a link)
- `\\{` `\\}` — curly braces (so they do not become a macro)
- `\\*` — asterisk (so it does not become bold)
- `\\!` — exclamation mark (so it does not become an image)
- `\\|` — pipe (so it does not split a table)
- `\\^` `\\~` — for superscript/subscript

### Inside `{{...}}` and `{code}` strip ALL backslash escapes

Inside monospace blocks escapes are not needed (in theory the parser should not interpret markup there, but it still interprets pair markers — see above). All `\\X` → `X`.

## Anti-patterns in source .md

Avoid these patterns in the source `.md` from the start — it will save you some of the manual fixes after conversion.

### 1. Pattern `<X>_<Y>_...` inside single backticks

❌ Bad:

```markdown
Template: `<a>_<b>_links`
```

After pandoc: `{{<a>_<b>_links}}`. After replacing `<>` with Unicode: `{{⟨a⟩_⟨b⟩_links}}`. Between the Unicode brackets and the letter `b` there is an outer `_..._` — Confluence makes an italic pair out of `_⟨b⟩_`.

✅ Good:

```markdown
Template: `tableA_tableB_links`
```

Or even:

```markdown
Template:

```
<a>_<b>_links
```
```

Inside triple backticks everything is literal — any placeholders can live there.

### 2. F-string with `{...}` inside a single backtick

❌ May break:

```markdown
We receive the message: `f"got: {message}"`
```

After replacement: `{{f"got: &#123;message&#125;"}}` — usually works, but in edge cases (long blocks, deep nesting) the parser may get confused.

✅ Good — multi-line code block:

````markdown
```python
f"got: {message}"
```
````

### 3. Regex with double backslash `\\.\\d\\s` inline

❌ Dangerous (pandoc turns each `\\` into the HTML entity `&bsol;`, and two in a row break Confluence):

```markdown
Alert regex: `rabbitmq_queue_messages_ready{queue=~".*\\.dlx"} > 0`
```

After pandoc + clean this becomes `&bsol;&bsol;.dlx` — two HTML entities in a row, the parser breaks.

✅ Solution: either the updated `clean-jira-escapes.py` (it automatically replaces `&bsol;` → `⧵`), or move the regex into triple backticks:

````markdown
Alert regex:

```promql
rabbitmq_queue_messages_ready{queue=~".*\\.dlx"} > 0
```
````

### 4. Patterns `->`, `=>` inline

`->` after conversion becomes `-⟩` (minus + Unicode right angle bracket). The minus inside can create a strikethrough pair with another `-` in a neighboring `{{...}}`.

❌ May break:

```markdown
If the function returns `None` — `-> None`. If nothing — also `-> None`.
```

✅ Good:

````markdown
If the function returns `None`:

```python
def f() -> None:
    ...
```
````

Or use a Unicode arrow directly in the `.md`:

```markdown
If the function returns `None` — `→ None`. If nothing — also `→ None`.
```

`→` (U+2192) is not interpreted by Confluence.

### 5. HTML tag names inline (`<a>`, `<b>`, `<i>`, `<span>`, `<div>`)

These letters are distinct HTML tags to the parser. After replacement with `⟨a⟩` it looks similar, and the semantics are preserved.

❌ Dangerous: `<a>`, `<b>`, `<i>`, `<span>`, `<table>`, `<form>` in single backticks.

✅ Safe: use other placeholder names (`first`, `second`, `T1`, `T2`, `varA`, `varB`).

## Mermaid diagrams

Pandoc-jira cannot render Mermaid. Options:

### Option A — insert as images

1. Convert each Mermaid block to PNG via `mmdc` (mermaid-cli).
2. In Confluence, insert via `+ → Image`.

Automation script:

```bash
#!/usr/bin/env bash
# Extracts all ```mermaid``` blocks from .md, renders to PNG
mmdc -i diagram.mmd -o diagram.png -w 2000
```

### Option B — Mermaid macro in Confluence

If you have a Confluence Mermaid plugin installed (Stiltsoft / etc):

1. Delete the `{code:...}java\n...\n{code}` block from the page.
2. In its place, use the `/mermaid` slash command → paste the content of the original `\`\`\`mermaid` block.

### Pitfall — `mmdc` requires Chrome

`mermaid-cli` uses puppeteer, which needs Chrome/Chromium. On macOS:

- `brew install --cask google-chrome`
- In the puppeteer config, specify the path: `{"executablePath": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "args": ["--no-sandbox"]}`

This fixes the `Could not find Chrome (ver. X.Y.Z)` problem on first run.

### Mermaid syntax — what breaks rendering

- Parentheses `(...)` inside labels — quotes are required: `["text (with parens)"]`
- Subgraph titles with parentheses — quotes are required: `subgraph X ["title (note)"]`

## Full pipeline script

### convert-md-to-confluence.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-.}"
CODE_THEME="${2:-Eclipse}"   # Confluence | Eclipse | Solarized | FadeToGrey | Emacs | Midnight

# 1. pre-process: ```mermaid → ```text (so pandoc does not parse Gantt colons as markup)
# 2. pandoc -t jira --wrap=none
# 3. sed: swap in the code-block theme
# 4. python3 clean-jira-escapes.py — pair-marker replacements

find "$TARGET" -type f -name "*.md" -not -path "*/mermaid-rendered/*" | while read MDFILE; do
    TXTFILE="${MDFILE%.md}.txt"

    PREPROC=$(mktemp)
    sed 's/^```mermaid$/```text/' "$MDFILE" > "$PREPROC"

    pandoc "$PREPROC" -t jira --wrap=none \
        | sed "s/{code:/{code:theme=${CODE_THEME}|/g" \
        | python3 "$SCRIPT_DIR/clean-jira-escapes.py" \
        > "$TXTFILE"

    rm -f "$PREPROC"
done
```

### clean-jira-escapes.py

```python
#!/usr/bin/env python3
"""Post-process pandoc-jira output for Confluence Wiki."""

import re
import sys


CHARS_NEVER_ESCAPE = "()-+&."  # these pandoc escapes are redundant


def fix_inline_code(match: re.Match) -> str:
    """Inside {{...}}: strip backslashes + replace pair markers with Unicode."""
    inner = match.group(0)

    # 1. Strip all backslash escapes
    inner = re.sub(r"\\(.)", r"\1", inner)

    open_, close_ = "{{", "}}"
    if not (inner.startswith(open_) and inner.endswith(close_)):
        return inner

    body = inner[len(open_) : -len(close_)]

    # 2. { } → HTML entities (Confluence does NOT normalize them back)
    body = body.replace("{", "&#123;").replace("}", "&#125;")

    # 3. < > → Unicode angles (Confluence normalizes &lt; &gt; back — hence Unicode)
    body = body.replace("<", "⟨").replace(">", "⟩")
    body = body.replace("&lt;", "⟨").replace("&gt;", "⟩")  # migration

    # 4. Markup pair markers → Unicode counterparts
    body = body.replace("*", "∗")  # bold → asterisk operator
    body = body.replace("-", "−")  # strikethrough → minus sign
    body = body.replace("+", "＋")  # underline → fullwidth plus
    body = body.replace("~", "∼")  # subscript → tilde operator
    body = body.replace("^", "ˆ")  # superscript → modifier circumflex

    # 5. Named HTML entities — pandoc generates them for literal backslash etc.
    body = body.replace("&bsol;", "⧵")  # backslash → REVERSE SOLIDUS OPERATOR (U+29F5)
    body = body.replace("&sol;", "/")  # forward slash → literal
    body = body.replace("&num;", "#")  # number sign → literal

    return open_ + body + close_


def fix_code_block(match: re.Match) -> str:
    """Inside {code:...}{code}: only strip backslashes. Leave pair markers alone — the parser does not interpret them there."""
    return re.sub(r"\\(.)", r"\1", match.group(0))


def main() -> None:
    content = sys.stdin.read()

    # Inside {{...}}
    inline_pat = re.compile(r"{{.*?}}(?!})", re.DOTALL)
    for _ in range(5):
        new = inline_pat.sub(fix_inline_code, content)
        if new == content:
            break
        content = new

    # Inside {code:...}{code}
    content = re.sub(
        r"{code[^}]*}.*?{code}",
        fix_code_block,
        content,
        flags=re.DOTALL,
    )

    # Outside — remove escapes that are known to be redundant
    for ch in CHARS_NEVER_ESCAPE:
        content = content.replace("\\" + ch, ch)

    sys.stdout.write(content)


if __name__ == "__main__":
    main()
```

## Anti-patterns (do not do this)

### 1. Do not replace `_` with Unicode inside `{{...}}`

It breaks copy-paste of Python code. Solve it by rewriting the pattern in the `.md`.

### 2. Do not use HTML entities for `<` `>`

Confluence Cloud / DC **normalizes HTML entities back** before parsing wiki markup. That is, `&lt;a&gt;` becomes `<a>` again and Confluence treats it as an HTML tag.

Exception: curly braces. For them, entities **work** — `&#123;` and `&#125;` are not normalized back.

### 3. Do not leave Mermaid blocks as code

That produces a code block with the Mermaid source text, not a diagram. Convert to PNG or use the Mermaid macro.

### 4. Do not draw a bidirectional arrow where the relationship is one-way

The bidirectional dotted arrow `<-.->` is valid Mermaid syntax (verified on 11.16.0); it is not forbidden. But do not use it "just in case": it hides the real direction of flow. If the relationship is one-way — draw `-.->`.

### 5. Do not use `(...)` in Mermaid labels without quotes

`[node (note)]` → must be `["node (note)"]`.

## Checklist: .md readiness for import

Before the .md → .txt conversion:

- [ ] Patterns `<X>_<Y>` in single backticks removed or rewritten (use camelCase or a multi-line block)
- [ ] Mermaid blocks are in triple backticks (` ```mermaid `), not single ones
- [ ] Mermaid: arrow directions match the real flow (bidirectional — only where the relationship really is two-way)
- [ ] Mermaid: parentheses in labels wrapped in quotes (`["text (note)"]`)
- [ ] Pandoc 2.0+ installed (`pandoc --version`)
- [ ] `clean-jira-escapes.py` in the same folder as the conversion script

After the conversion — verify:

- [ ] All `<X>` placeholders in single backticks → became `⟨X⟩` Unicode (inside `{{...}}`)
- [ ] All `*`, `-`, `+`, `~`, `^` inside `{{...}}` → became their Unicode counterparts
- [ ] No `\\(`, `\\)`, `\\-` outside code (removed)
- [ ] Mermaid blocks are marked ⚠ in the script log (they must be inserted separately via the `/mermaid` macro or as PNG)

## Related documents

- [Confluence Wiki Markup spec (Data Center)](https://confluence.atlassian.com/doc/confluence-wiki-markup-251003035.html) — official syntax documentation
- [Pandoc `jira` writer](https://pandoc.org/MANUAL.html#jira) — official writer documentation
- [mermaid-cli](https://github.com/mermaid-js/mermaid-cli) — rendering Mermaid to PNG/SVG

## License and usage

This document is the result of empirically working out the problems of converting a large documentation base (45+ Markdown files) to Confluence Wiki. All patterns in the tables have been tested on real cases. If you find another pattern that breaks the import — add it to the table.
