#!/usr/bin/env python3
"""
Add a publication to the publications section of index.html from BibTeX.

The BibTeX entry is the main input argument.  It can be either the path to a
``.bib`` file or the entry itself, quoted on the command line.  Title, author
list, venue, place, year, and the paper link (``url`` or ``doi``) are derived
from the entry.  Optional arguments add buttons for code, data, a poster, or
slides.

The entry is inserted into the publication list (newer entries first, and new
entries above existing publications from the same year), together with a
copyable ``<pre class="bibtex">`` block used by the BibTeX button.  If a
publication with the same title already exists, it is replaced instead of
added: non-BibTeX buttons (code, data, poster, slides, custom links) are
carried over, and the entry moves if its year changed.

Each entry gets a stable ``id`` (``publication-<citation key>``) so it can be
linked directly.  With ``--add-news``, a news item
"New publication: <title> <venue>" is added to the news section of the same
page, where the title links to the entry.

Usage:
    python add_publication.py paper.bib
    python add_publication.py paper.bib --code https://github.com/me/project
    python add_publication.py paper.bib --code URL --data URL --poster URL
    python add_publication.py paper.bib --add-news
    python add_publication.py '@inproceedings{...}' --dry-run

Run ``python add_publication.py --help`` for all options.
"""

from __future__ import annotations

import argparse
import html as html_lib
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import add_news

# ── Configurable paths ─────────────────────────────────────────────────────────
WEBSITE_ROOT = Path(__file__).resolve().parent
INDEX_HTML = WEBSITE_ROOT / "index.html"

PUBLICATION_LIST_MARKER = '<div class="publication-list">'
PUBLICATION_TAG = '<article class="publication"'  # may carry an id attribute
INDENT = " " * 20  # indentation of <article> elements inside the list

# Author highlighted in bold on the website.  Either a surname ("Maurer") or a
# full name ("Maximilian Maurer"); can be changed with --author.
DEFAULT_AUTHOR = "Maximilian Maurer"


class BibtexError(ValueError):
    """Raised when the BibTeX input cannot be parsed or is incomplete."""


# ── BibTeX parsing ─────────────────────────────────────────────────────────────

@dataclass
class BibEntry:
    """A single parsed BibTeX entry."""

    entry_type: str          # e.g. "inproceedings"
    key: str                 # citation key, e.g. "maurer-etal-2026-promptology"
    fields: dict[str, str]   # lower-cased field names → raw values
    raw: str                 # original entry text, kept verbatim for the site


def _read_balanced(text: str, start: int, open_char: str, close_char: str) -> tuple[str, int]:
    """Read a balanced ``{...}`` or ``(...)`` block, ignoring escaped characters."""
    if open_char == "{":
        depth = 1
        i = start
        while i < len(text):
            char = text[i]
            if char == "\\":
                i += 2
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i], i + 1
            i += 1
    else:
        # Parenthesised entries: braces may contain ")" characters.
        brace_depth = 0
        i = start
        while i < len(text):
            char = text[i]
            if char == "\\":
                i += 2
                continue
            if char == "{":
                brace_depth += 1
            elif char == "}":
                brace_depth = max(0, brace_depth - 1)
            elif char == ")" and brace_depth == 0:
                return text[start:i], i + 1
            i += 1
    raise BibtexError("unbalanced braces: the BibTeX entry is not closed")


def _read_quoted(text: str, start: int) -> tuple[str, int]:
    """Read a double-quoted BibTeX value starting at ``start`` and return the content."""
    depth = 0
    i = start + 1
    out: list[str] = []
    while i < len(text):
        char = text[i]
        if char == "\\" and i + 1 < len(text):
            out.append(text[i:i + 2])
            i += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char == '"' and depth == 0:
            return "".join(out), i + 1
        out.append(char)
        i += 1
    raise BibtexError("unterminated quoted value in BibTeX entry")


def _split_key(body: str) -> tuple[str, str]:
    """Split the citation key from the field list at the first top-level comma."""
    depth = 0
    for i, char in enumerate(body):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char == "," and depth == 0:
            return body[:i].strip(), body[i + 1:]
    return body.strip(), ""


def _parse_fields(body: str) -> dict[str, str]:
    """Parse ``name = value`` pairs from an entry body.

    Supports braced values, quoted values, bare values, and ``#`` concatenation.
    """
    fields: dict[str, str] = {}
    i = 0
    length = len(body)

    while i < length:
        while i < length and body[i] in " \t\r\n,":
            i += 1
        if i >= length:
            break

        match = re.match(r"([A-Za-z][A-Za-z0-9_.:\-]*)\s*=", body[i:])
        if not match:
            snippet = body[i:i + 40].replace("\n", " ")
            raise BibtexError(f"cannot parse BibTeX field near: {snippet!r}")
        name = match.group(1).lower()
        i += match.end()

        parts: list[str] = []
        while True:
            while i < length and body[i] in " \t\r\n":
                i += 1
            if i >= length:
                break

            if body[i] == "{":
                value, i = _read_balanced(body, i + 1, "{", "}")
            elif body[i] == '"':
                value, i = _read_quoted(body, i)
            else:
                bare = re.match(r"[^,\s]+", body[i:])
                if not bare:
                    raise BibtexError(f"missing value for BibTeX field {name!r}")
                value = bare.group(0)
                i += bare.end()
            parts.append(value)

            while i < length and body[i] in " \t\r\n":
                i += 1
            if i < length and body[i] == "#":  # BibTeX string concatenation
                i += 1
                continue
            break

        fields[name] = "".join(parts)

    return fields


def parse_bibtex(text: str) -> list[BibEntry]:
    """Parse every non-@string/@comment/@preamble entry in a BibTeX string."""
    entries: list[BibEntry] = []
    i = 0

    while True:
        at = text.find("@", i)
        if at == -1:
            break

        header = re.match(r"@\s*([A-Za-z][\w\-]*)\s*([{(])", text[at:])
        if not header:
            i = at + 1
            continue

        entry_type = header.group(1).lower()
        open_char = header.group(2)
        close_char = "}" if open_char == "{" else ")"
        body, next_i = _read_balanced(text, at + header.end(), open_char, close_char)

        if entry_type not in {"comment", "preamble", "string"}:
            key, rest = _split_key(body)
            if not key:
                raise BibtexError("BibTeX entry without a citation key")
            entries.append(BibEntry(entry_type, key, _parse_fields(rest), text[at:next_i]))

        i = next_i

    if not entries:
        raise BibtexError("no BibTeX entry found in the input")
    return entries


# ── LaTeX → plain text ─────────────────────────────────────────────────────────

_ACCENTS = {
    '"': "\u0308",  # diaeresis
    "'": "\u0301",  # acute
    "`": "\u0300",  # grave
    "^": "\u0302",  # circumflex
    "~": "\u0303",  # tilde
    "=": "\u0304",  # macron
    ".": "\u0307",  # dot above
}

_LETTER_ACCENTS = {
    "c": "\u0327",  # cedilla
    "v": "\u030c",  # caron
    "u": "\u0306",  # breve
    "H": "\u030b",  # double acute
    "k": "\u0328",  # ogonek
    "r": "\u030a",  # ring above
    "d": "\u0323",  # dot below
    "b": "\u0331",  # macron below
}

_SPECIAL_CHARS = {
    "ss": "ß", "ae": "æ", "AE": "Æ", "oe": "œ", "OE": "Œ",
    "o": "ø", "O": "Ø", "aa": "å", "AA": "Å", "l": "ł", "L": "Ł",
    "i": "ı", "j": "ȷ", "LaTeX": "LaTeX", "TeX": "TeX", "BibTeX": "BibTeX",
}

_FORMATTING_COMMANDS = (
    "textit|emph|textbf|texttt|textsc|textrm|textsf|textsl|underline|"
    "textsuperscript|textsubscript|mathrm|mathbf|mathit|mathsf|mathtt|"
    "mbox|url|path"
)


def latex_to_text(value: str) -> str:
    """Convert a BibTeX/LaTeX string to readable Unicode text.

    Handles protective braces (``{AI}``), accented characters (``{\\"o}``),
    formatting commands, escaped characters, and common special characters.
    """
    text = value

    # Escaped literal characters: \& \% \$ \# \_ \{ \}
    text = re.sub(r"\\([&%$#_{}])", r"\1", text)

    # Accents written as \"o, \"{o}, {\"o}, or even {\\'o} (seen in ACL BibTeX).
    def _accent(match: re.Match) -> str:
        mark = _ACCENTS[match.group(1)]
        return unicodedata.normalize("NFC", match.group(2) + mark)

    text = re.sub(r"\\+([\"'`^~=.])\s*\{?\s*([A-Za-z])\s*\}?", _accent, text)
    # Shorthand accent without a backslash, e.g. D{"o}nmez from ACL Anthology.
    text = re.sub(r"\{([\"'`^~=.])\s*([A-Za-z])\s*\}", _accent, text)

    # Letter accents such as \c{c}, \v{s}, \u{g}, \H{o}, \k{a}.
    def _letter_accent(match: re.Match) -> str:
        mark = _LETTER_ACCENTS.get(match.group(1))
        if not mark:
            return match.group(2)
        return unicodedata.normalize("NFC", match.group(2) + mark)

    text = re.sub(r"\\+([cvuHkrdb])\s*\{\s*([A-Za-z])\s*\}", _letter_accent, text)

    # \href{url}{label} → label
    text = re.sub(r"\\href\s*\{[^{}]*\}\s*\{([^{}]*)\}", r"\1", text)
    # Formatting commands: keep their argument.
    text = re.sub(rf"\\(?:{_FORMATTING_COMMANDS})\s*\{{([^{{}}]*)\}}", r"\1", text)

    # Special characters such as {\ss}, \o, \AE; unknown commands are dropped.
    def _special(match: re.Match) -> str:
        return _SPECIAL_CHARS.get(match.group(1), "")

    text = re.sub(r"\\+([A-Za-z]+)\s*(?=\{\})?", _special, text)

    # Drop any remaining commands and braces.
    text = re.sub(r"\\[A-Za-z]+\s*", "", text)
    text = re.sub(r"[{}]", "", text)

    # Typography and whitespace cleanup.
    text = text.replace("~", " ")
    text = text.replace("---", "—").replace("--", "–")
    text = text.replace("$", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ── Author handling ────────────────────────────────────────────────────────────

def split_authors(field: str) -> list[str]:
    """Split a BibTeX author field on top-level ``and`` separators."""
    authors: list[str] = []
    buffer: list[str] = []
    depth = 0
    i = 0

    while i < len(field):
        char = field[i]
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)

        if depth == 0:
            separator = re.match(r"\s+and\s+", field[i:], re.IGNORECASE)
            if separator:
                authors.append("".join(buffer).strip())
                buffer = []
                i += separator.end()
                continue

        buffer.append(char)
        i += 1

    authors.append("".join(buffer).strip())
    return [author for author in authors if author]


def split_name(name: str) -> tuple[str, str]:
    """Return ``(first_name, last_name)`` for a BibTeX name.

    Handles the "Last, First" and "First Last" forms.  Particles such as
    "Schulte im Walde" are preserved because they appear before the comma.
    """
    depth = 0
    comma = -1
    for i, char in enumerate(name):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char == "," and depth == 0:
            comma = i
            break

    if comma != -1:
        last = name[:comma]
        rest = name[comma + 1:]
        first = rest.split(",")[0]
    else:
        tokens = name.split()
        last = tokens[-1] if tokens else name
        first = " ".join(tokens[:-1])

    return latex_to_text(first).strip(), latex_to_text(last).strip()


def _normalize_name(value: str) -> str:
    """Lower-case and strip accents/markers so names can be compared."""
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z ]", "", ascii_only.lower()).strip()


def _initials_match(author_first: str, target_first: str) -> bool:
    """True if both first names share at least their first given name."""
    if not target_first:
        return True
    author_tokens = author_first.split()
    target_tokens = target_first.split()
    if not author_tokens or not target_tokens:
        return True
    return _normalize_name(author_tokens[0]) == _normalize_name(target_tokens[0])


def _author_markup(last_name: str, highlight: bool) -> str:
    """Return an escaped surname, optionally bold, keeping ``*`` markers outside."""
    match = re.match(r"^(.*?)([*†‡§¶]*)$", last_name)
    base = match.group(1) if match else last_name
    marks = match.group(2) if match else ""
    safe_base = html_lib.escape(base, quote=False)
    if highlight:
        safe_base = f"<strong>{safe_base}</strong>"
    return safe_base + html_lib.escape(marks, quote=False)


def format_authors(field: str, target_author: str) -> str:
    """Build the surname-only author list shown above each publication."""
    names = split_authors(field)
    if not names:
        return ""

    et_al = any(name.strip().lower() == "others" for name in names)
    names = [name for name in names if name.strip().lower() != "others"]

    target_first, target_last = split_name(target_author)
    target_last_norm = _normalize_name(target_last)

    rendered: list[str] = []
    for name in names:
        first, last = split_name(name)
        highlight = (
            bool(target_last_norm)
            and _normalize_name(last) == target_last_norm
            and _initials_match(first, target_first)
        )
        rendered.append(_author_markup(last, highlight))

    if not rendered:
        return ""

    if len(rendered) == 1:
        text = rendered[0]
    elif len(rendered) == 2:
        text = f"{rendered[0]} and {rendered[1]}"
    else:
        text = ", ".join(rendered[:-1]) + f", and {rendered[-1]}"

    if et_al:
        text += ", et al."
    return text


# ── Venue formatting ───────────────────────────────────────────────────────────

# Most specific rules first.  Phrase rules are matched as substrings; short
# acronyms are matched on word boundaries.
_VENUE_RULES: list[tuple[tuple[str, ...], str]] = [
    (("ijcnlp", "aacl"), "IJCNLP-AACL"),
    (("ijcnlp",), "IJCNLP"),
    (("aacl",), "AACL"),
    (("empirical methods in natural language processing", "emnlp"), "EMNLP"),
    (("nations of the americas chapter", "north american chapter", "naacl"), "NAACL"),
    (("european chapter", "eacl"), "EACL"),
    (("workshop on argument mining", "argmining"), "ArgMining"),
    (("konvens",), "KONVENS"),
    (("international conference on computational linguistics", "coling"), "COLING"),
    (("language resources and evaluation", "lrec"), "LREC"),
    (("conference on language modeling", "colm"), "COLM"),
    (("learning representations", "iclr"), "ICLR"),
    (("neural information processing systems", "neurips"), "NeurIPS"),
    (("international conference on machine learning", "icml"), "ICML"),
    (("transactions of the association for computational linguistics", "tacl"), "TACL"),
    (("association for computational linguistics",), "ACL"),
]

_IGNORED_PARENTHETICALS = re.compile(
    r"volume|papers|demonstrations|track|long|short|findings|proceedings", re.IGNORECASE
)


def _matches_venue(text: str, needles: tuple[str, ...]) -> bool:
    for needle in needles:
        if " " in needle:
            if needle in text:
                return True
        elif re.search(rf"\b{re.escape(needle)}\b", text):
            return True
    return False


def _parenthetical_acronym(venue: str) -> str | None:
    """Use an explicit acronym such as "(KONVENS 2023)" or "(ArgMining 2024)"."""
    for group in reversed(re.findall(r"\(([^()]*)\)", venue)):
        group = group.strip()
        if not group or _IGNORED_PARENTHETICALS.search(group):
            continue
        match = re.match(r"^([A-Za-z][A-Za-z0-9&+\-]*)\s*(?:\d{4})?$", group)
        if match and match.group(1)[:1].isupper():
            return match.group(1)
    return None


def short_venue(entry: BibEntry, year: int) -> str:
    """Derive a short venue name such as ``EMNLP 2026`` from the entry.

    Known conferences are abbreviated; unknown venues keep their full name.
    ``Findings of`` is preserved as a prefix, and system-demonstration tracks
    get a suffix after the year ("EACL 2026 (System Demonstrations)").
    """
    fields = entry.fields
    venue = (
        fields.get("booktitle")
        or fields.get("journal")
        or fields.get("publisher")
        or fields.get("howpublished")
        or ""
    )
    if not venue and fields.get("eprint"):
        # Preprint entries (arXiv and friends) often have no booktitle/journal.
        venue = fields.get("archiveprefix") or "arXiv"
    venue = latex_to_text(venue)
    if not venue:
        return ""

    lower = venue.lower()
    findings = lower.startswith("findings") or "findings of" in lower
    demonstration = (
        "system demonstrations" in lower
        or "demo track" in lower
        or "(demo" in lower
    )

    acronym = None
    for needles, candidate in _VENUE_RULES:
        if _matches_venue(lower, needles):
            acronym = candidate
            break

    if acronym is None:
        acronym = _parenthetical_acronym(venue)

    if acronym is None:
        # Fall back to the full name, minus a leading "Proceedings of ...".
        acronym = re.sub(
            r"^proceedings of (the )?(\d+(?:st|nd|rd|th) )?",
            "",
            venue,
            flags=re.IGNORECASE,
        ).strip()
        if re.search(r"\b(?:19|20)\d{2}\b", acronym):
            return acronym
        return f"{acronym} {year}".strip()

    prefix = "Findings of " if findings and acronym not in {"TACL"} else ""
    suffix = " (System Demonstrations)" if demonstration else ""
    return f"{prefix}{acronym} {year}{suffix}"


def publication_venue(entry: BibEntry, year: int, venue_override: str | None = None) -> str:
    """Return the venue shown for an entry, honouring ``--venue``.

    The year is appended to an override that does not mention one; entries
    without a usable venue fall back to the year alone.
    """
    if venue_override:
        venue = latex_to_text(venue_override)
        if venue and not re.search(r"\b(?:19|20)\d{2}\b", venue):
            venue += f" {year}"
        return venue or str(year)
    return short_venue(entry, year) or str(year)


def publication_year(entry: BibEntry) -> int:
    """Read the publication year from ``year``, ``date``, or the citation key."""
    for field in ("year", "date"):
        value = entry.fields.get(field, "")
        match = re.search(r"(?:19|20)\d{2}", value)
        if match:
            return int(match.group(0))
    match = re.search(r"(?:19|20)\d{2}", entry.key)
    if match:
        return int(match.group(0))
    raise BibtexError(
        f"cannot determine the publication year of {entry.key!r}; add a year field"
    )


def publication_place(entry: BibEntry) -> str:
    """Return the conference location, if the entry has one."""
    return latex_to_text(entry.fields.get("address") or entry.fields.get("location") or "")


def publication_url(entry: BibEntry, override: str | None = None) -> str | None:
    """Return the paper link from --paper, the url field, or the DOI."""
    if override:
        return _validate_url(override, "--paper")
    url = entry.fields.get("url", "").strip()
    if url:
        return _validate_url(url, "url")
    doi = entry.fields.get("doi", "").strip()
    if doi:
        doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", doi, flags=re.IGNORECASE)
        return f"https://doi.org/{doi}"
    return None


def _validate_url(url: str, source: str) -> str:
    """Reject obviously unsafe or malformed links; relative paths are allowed."""
    # URLs are not LaTeX: only strip the protective braces some .bib files use.
    url = url.strip().strip("{}").strip()
    # Repair the common "https:/example.org" typo (but leave "https://" alone).
    url = re.sub(r"^(https?):/(?!/)", r"\1://", url, flags=re.IGNORECASE)
    if not url:
        raise BibtexError(f"empty URL passed via {source}")
    scheme = re.match(r"^([A-Za-z][A-Za-z0-9+.\-]*):", url)
    if scheme and scheme.group(1).lower() not in {"http", "https", "mailto"}:
        raise BibtexError(
            f"unsupported URL scheme {scheme.group(1)!r} in {source}: {url}"
        )
    return url


# ── HTML generation ────────────────────────────────────────────────────────────

def _split_top_level_commas(text: str) -> list[str]:
    """Split on commas that are outside braces and quotes."""
    parts: list[str] = []
    buffer: list[str] = []
    depth = 0
    in_quotes = False
    i = 0
    while i < len(text):
        char = text[i]
        if char == "\\" and i + 1 < len(text):
            buffer.append(text[i:i + 2])
            i += 2
            continue
        if char == '"':
            in_quotes = not in_quotes
        elif not in_quotes:
            if char == "{":
                depth += 1
            elif char == "}":
                depth = max(0, depth - 1)
            elif char == "," and depth == 0:
                parts.append("".join(buffer))
                buffer = []
                i += 1
                continue
        buffer.append(char)
        i += 1
    parts.append("".join(buffer))
    return parts


def _format_single_line_entry(raw: str) -> str:
    """Split a one-line BibTeX entry into the usual multi-line layout."""
    stripped = raw.strip()
    header = re.match(r"@\s*[A-Za-z]+\s*\{", stripped)
    if not header:
        return stripped
    body = stripped[header.end():]
    if body.endswith("}"):
        body = body[:-1]

    parts = [part.strip() for part in _split_top_level_commas(body)]
    if len(parts) < 2:
        return stripped

    out = [stripped[:header.end()] + parts[0] + ","]
    fields = [part for part in parts[1:] if part]
    for index, field in enumerate(fields):
        out.append("    " + field + ("," if index < len(fields) - 1 else ""))
    out.append("}")
    return "\n".join(out)


def format_bibtex_block(raw: str) -> str:
    """Normalise indentation of a raw BibTeX entry for the copyable <pre> block.

    The fields end up indented by four spaces, matching the existing entries.
    Continuation lines keep their relative indentation.
    """
    lines = raw.strip().splitlines()
    if len(lines) <= 1:
        return _format_single_line_entry(raw)

    body = lines[1:]
    # The final closing brace is intentionally not indented; exclude it when
    # determining the common indentation of the fields.
    indents = [
        len(line) - len(line.lstrip())
        for line in body
        if line.strip() and line.strip() != "}"
    ]
    common = min(indents) if indents else 0

    out = [lines[0].strip()]
    for line in body:
        if not line.strip():
            continue
        if line.strip() == "}":
            out.append("}")
            continue
        stripped = line[common:] if len(line) - len(line.lstrip()) >= common else line.lstrip()
        out.append("    " + stripped)
    return "\n".join(out)


def _buttons(paper: str | None, code: str | None, data: str | None,
             poster: str | None, slides: str | None, bib_id: str,
             extra_buttons: list[tuple[str, str]] | None = None) -> list[str]:
    """Build the button row: Paper, BibTeX, Code, Data, Poster, Slides.

    ``extra_buttons`` keeps custom buttons (and Code/Data/Poster/Slides links
    not overridden on the command line) from an entry that is being replaced.
    """
    buttons: list[str] = []
    used_labels: set[str] = set()

    def add_link(label: str, url: str) -> None:
        href = html_lib.escape(url, quote=True)
        safe_label = html_lib.escape(label, quote=False)
        buttons.append(
            f'<a class="btn" href="{href}" target="_blank" rel="noopener">{safe_label}</a>'
        )
        used_labels.add(label.casefold())

    if paper:
        add_link("Paper", paper)
    buttons.append(
        f'<button class="btn bib-btn" data-bib-id="{bib_id}">BibTeX</button>'
    )
    used_labels.add("bibtex")

    for label, url in (("Code", code), ("Data", data), ("Poster", poster), ("Slides", slides)):
        if url:
            add_link(label, url)

    for label, url in extra_buttons or []:
        if label.casefold() in used_labels:
            continue
        add_link(label, url)

    return buttons


def publication_anchor(entry: BibEntry) -> str:
    """Return the HTML id that links directly to a publication entry."""
    return "publication-" + re.sub(r"[^A-Za-z0-9_.:\-]", "-", entry.key)


def render_publication(entry: BibEntry, *, paper: str | None, code: str | None,
                       data: str | None, poster: str | None, slides: str | None,
                       venue_override: str | None, year_override: int | None,
                       target_author: str,
                       preserved_buttons: list[tuple[str, str]] | None = None
                       ) -> tuple[str, int]:
    """Render a fully indented <article> block and return it with its year."""
    title = latex_to_text(entry.fields.get("title", ""))
    if not title:
        raise BibtexError(f"BibTeX entry {entry.key!r} has no title")
    safe_title = html_lib.escape(title, quote=False)

    authors_field = entry.fields.get("author", "")
    authors = format_authors(authors_field, target_author)
    if not authors:
        raise BibtexError(f"BibTeX entry {entry.key!r} has no author list")

    year = year_override if year_override is not None else publication_year(entry)
    venue = publication_venue(entry, year, venue_override)
    place = publication_place(entry)

    meta = f"{authors}. {venue}"
    if place:
        meta += f", {place}"
    meta += "."

    bib_id = "bib-" + re.sub(r"[^A-Za-z0-9_.:\-]", "-", entry.key)
    block = format_bibtex_block(entry.raw)
    safe_block = html_lib.escape(block, quote=False)

    title_html = (
        f'<a href="{html_lib.escape(paper, quote=True)}">{safe_title}</a>'
        if paper else safe_title
    )
    buttons = _buttons(
        paper, code, data, poster, slides, bib_id, preserved_buttons
    )

    lines = [
        f'<article class="publication" id="{publication_anchor(entry)}">',
        f'    <h3>{title_html}</h3>',
        f'    <p class="publication-meta">{meta}</p>',
        '    <div class="pub-buttons">',
        *[f'        {button}' for button in buttons],
        '    </div>',
    ]
    head = "\n".join(lines)

    # The BibTeX block is deliberately not re-indented: <pre> shows whitespace,
    # and keeping the entry at its natural indentation makes copying pleasant.
    block_html = (
        f'\n{INDENT}    <pre class="bibtex" id="{bib_id}" style="display:none">{safe_block}\n'
        f'</pre>\n{INDENT}</article>'
    )

    indented_head = "\n".join(INDENT + line for line in head.splitlines())
    return indented_head + block_html, year


def insert_publication(text: str, block: str, year: int) -> tuple[str, int]:
    """Insert an indented publication block, newest first, and return (html, index)."""
    marker_index = text.find(PUBLICATION_LIST_MARKER)
    if marker_index == -1:
        raise ValueError(
            f'could not find {PUBLICATION_LIST_MARKER!r} in the HTML file'
        )
    region_start = marker_index + len(PUBLICATION_LIST_MARKER)

    articles = list(re.finditer(
        rf'{PUBLICATION_TAG}[^>]*>.*?</article>', text[region_start:], re.DOTALL
    ))
    if not articles:
        position = region_start
        return text[:position] + "\n" + block + text[position:], 1

    insert_before = None
    ordinal = 1
    for index, article in enumerate(articles, start=1):
        absolute_start = region_start + article.start()
        block_text = article.group(0)
        year_match = re.search(r'year\s*=\s*["{]?\s*((?:19|20)\d{2})', block_text)
        article_year = int(year_match.group(1)) if year_match else 0
        if article_year <= year:
            insert_before = absolute_start
            ordinal = index
            break

    if insert_before is not None:
        # Insert at the start of the line so the new entry gets the standard
        # indentation even if the existing entry it precedes is misindented.
        line_start = text.rfind("\n", 0, insert_before) + 1
        existing_indent = text[line_start:insert_before]
        if existing_indent.strip():
            line_start, existing_indent = insert_before, INDENT
        return (
            text[:line_start] + block + "\n" + existing_indent + text[line_start:],
            ordinal,
        )

    # Older than everything currently listed: append at the end of the list.
    last_end = region_start + articles[-1].end()
    return text[:last_end] + "\n" + block + text[last_end:], len(articles) + 1


ARTICLE_RE = re.compile(rf'[ \t]*{PUBLICATION_TAG}[^>]*>.*?</article>', re.DOTALL)


def article_year(article: str) -> int:
    """Read the year from the BibTeX block of an existing publication."""
    match = re.search(r'year\s*=\s*["{]?\s*((?:19|20)\d{2})', article)
    return int(match.group(1)) if match else 0


def _heading_text(article: str) -> str:
    """Plain-text title of an existing publication entry."""
    heading = re.search(r"<h3>(?:<a[^>]*>)?(.*?)(?:</a>)?</h3>", article, re.DOTALL)
    if not heading:
        return ""
    return html_lib.unescape(re.sub(r"<[^>]+>", "", heading.group(1)))


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().casefold()


def find_publication(text: str, title: str) -> re.Match | None:
    """Return the <article> match whose title matches ``title``, if any."""
    target = normalize_title(title)
    for match in ARTICLE_RE.finditer(text):
        if normalize_title(_heading_text(match.group(0))) == target:
            return match
    return None


def existing_buttons(article: str) -> list[tuple[str, str]]:
    """Extract ``(label, href)`` for the link buttons of an existing entry."""
    row = re.search(r'<div class="pub-buttons">(.*?)</div>', article, re.DOTALL)
    if not row:
        return []

    buttons: list[tuple[str, str]] = []
    seen: set[str] = set()
    for href, label_html in re.findall(
        r'<a class="btn" href="([^"]*)"[^>]*>(.*?)</a>', row.group(1), re.DOTALL
    ):
        label = html_lib.unescape(re.sub(r"<[^>]+>", "", label_html)).strip()
        href = html_lib.unescape(href).strip()
        key = label.casefold()
        if not label or not href or key in seen:
            continue
        seen.add(key)
        buttons.append((label, href))
    return buttons


def replace_publication(text: str, match: re.Match, block: str,
                        year: int) -> tuple[str, int]:
    """Replace an existing publication, keeping its slot when the year is unchanged."""
    position = text[:match.start()].count(PUBLICATION_TAG) + 1

    if article_year(match.group(0)) == year:
        return text[:match.start()] + block + text[match.end():], position

    # The year changed: remove the old entry and insert the new one at the
    # position matching its new year.
    end = match.end()
    if text[end:end + 1] == "\n":
        end += 1
    return insert_publication(text[:match.start()] + text[end:], block, year)


# ── Entry point ────────────────────────────────────────────────────────────────

def _load_bibtex(source: str) -> str:
    """Read BibTeX from a file path, or return the argument as inline BibTeX."""
    # Detect inline entries first.  A pasted entry can easily exceed the
    # filesystem's name limit, and Path.is_file() would then raise OSError
    # (ENAMETOOLONG) instead of letting us parse the BibTeX.
    if source.lstrip().startswith("@") or "\n" in source:
        return source

    path = Path(source).expanduser()
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    except OSError as error:
        if "@" in source:
            return source
        raise FileNotFoundError(f"cannot access {path} as a file: {error}") from error

    if source.lower().endswith((".bib", ".bibtex")):
        raise FileNotFoundError(f"file not found: {path}")
    return source


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Add a publication from a BibTeX entry to the publications section "
            "of index.html."
        ),
        epilog=(
            "Examples:\n"
            "  %(prog)s paper.bib\n"
            "  %(prog)s paper.bib --code https://github.com/me/project --data https://doi.org/...\n"
            "  %(prog)s paper.bib --poster assets/pdf/posters/paper.pdf --slides assets/pdf/slides/talk.pdf\n"
            "  %(prog)s '@inproceedings{key, title={...}, author={...}, year={2025}}' --dry-run\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "bibtex",
        metavar="BIBTEX",
        help="path to a .bib file, or the BibTeX entry itself",
    )
    parser.add_argument(
        "--code", metavar="URL", help="add a Code button linking to this URL"
    )
    parser.add_argument(
        "--data", metavar="URL", help="add a Data button linking to this URL"
    )
    parser.add_argument(
        "--poster", metavar="URL", help="add a Poster button linking to this URL"
    )
    parser.add_argument(
        "--slides", metavar="URL", help="add a Slides button linking to this URL"
    )
    parser.add_argument(
        "--paper", metavar="URL",
        help="override the paper link (default: url or doi field)",
    )
    parser.add_argument(
        "--venue", metavar="VENUE",
        help="override the automatically detected venue",
    )
    parser.add_argument(
        "--year", metavar="YEAR", type=int,
        help="override the year from the BibTeX entry",
    )
    parser.add_argument(
        "--author", metavar="NAME", default=DEFAULT_AUTHOR,
        help=(
            "name to highlight in bold in the author list (default: %(default)s); "
            "use a surname alone to match any author with that surname"
        ),
    )
    parser.add_argument(
        "--key", metavar="KEY",
        help="citation key to pick when the input contains multiple entries",
    )
    parser.add_argument(
        "--html", metavar="FILE", type=Path, default=INDEX_HTML,
        help="HTML file to update (default: index.html next to this script)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="add a duplicate instead of replacing an entry with the same title",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print the generated HTML instead of modifying the file",
    )
    parser.add_argument(
        "--add-news", action="store_true",
        help=(
            'also add the news item "New publication: <title> <venue>", with the '
            "title linking to the publication entry"
        ),
    )
    args = parser.parse_args(argv)

    try:
        raw = _load_bibtex(args.bibtex)
        entries = parse_bibtex(raw)

        if args.key:
            selected = [entry for entry in entries if entry.key == args.key]
            if not selected:
                keys = ", ".join(entry.key for entry in entries)
                raise BibtexError(f"citation key {args.key!r} not found (available: {keys})")
            entry = selected[0]
        elif len(entries) > 1:
            keys = ", ".join(entry.key for entry in entries)
            raise BibtexError(
                f"input contains {len(entries)} entries; pass --key to choose one ({keys})"
            )
        else:
            entry = entries[0]

        paper = publication_url(entry, args.paper)
        code = _validate_url(args.code, "--code") if args.code else None
        data = _validate_url(args.data, "--data") if args.data else None
        poster = _validate_url(args.poster, "--poster") if args.poster else None
        slides = _validate_url(args.slides, "--slides") if args.slides else None
        year = args.year if args.year is not None else publication_year(entry)
    except (BibtexError, FileNotFoundError) as error:
        sys.exit(f"Error: {error}")

    html_path = args.html.expanduser()
    if not html_path.exists():
        sys.exit(f"Error: HTML file not found: {html_path}")

    text = html_path.read_text(encoding="utf-8")
    title = latex_to_text(entry.fields.get("title", ""))

    existing = None if args.force else find_publication(text, title)
    preserved: list[tuple[str, str]] = []
    if existing:
        preserved = existing_buttons(existing.group(0))
        for index, (label, url) in enumerate(preserved):
            if label.casefold() != "paper":
                continue
            # The paper button is rendered separately; keep the old link only
            # if the new entry does not provide one.
            if paper is None:
                paper = url
            preserved.pop(index)
            break

        # A button given on the command line replaces the old one of that name.
        overridden = {
            "code": code is not None,
            "data": data is not None,
            "poster": poster is not None,
            "slides": slides is not None,
        }
        preserved = [
            (label, url) for label, url in preserved
            if not overridden.get(label.casefold(), False)
        ]

    try:
        block, year = render_publication(
            entry,
            paper=paper,
            code=code,
            data=data,
            poster=poster,
            slides=slides,
            venue_override=args.venue,
            year_override=args.year,
            target_author=args.author,
            preserved_buttons=preserved,
        )
    except BibtexError as error:
        sys.exit(f"Error: {error}")

    existing_count = len(re.findall(PUBLICATION_TAG, text))
    try:
        if existing:
            updated, position = replace_publication(text, existing, block, year)
            total = existing_count
        else:
            updated, position = insert_publication(text, block, year)
            total = existing_count + 1
    except ValueError as error:
        sys.exit(f"Error: {error}")

    news: add_news.NewsResult | None = None
    news_text = ""
    if args.add_news:
        anchor = publication_anchor(entry)
        venue = publication_venue(entry, year, args.venue)
        news_text = f"New publication: {title} {venue}".strip()
        news_html = (
            f'New publication: <a href="#{anchor}">'
            f'{html_lib.escape(title, quote=False)}</a> '
            f'{html_lib.escape(venue, quote=False)}'
        ).rstrip()
        try:
            news = add_news.upsert_news_item(
                updated,
                message=news_text,
                date_str=date.today().isoformat(),
                message_html=news_html,
                match_href=f"#{anchor}",
            )
        except ValueError as error:
            sys.exit(f"Error: could not add the news item: {error}")
        updated = news.html

    action = "Replaced" if existing else "Added"

    if args.dry_run:
        print("Generated publication entry (not written):\n")
        print(block)
        verb = "replace the existing publication" if existing else "insert a new publication"
        print(f"\nWould {verb} at position {position} of {total} in {html_path}.")
        if news:
            nverb = "replace the existing news item" if news.replaced else "insert a new news item"
            print("\nGenerated news item (not written):\n")
            print(news.block)
            print(f"\nWould {nverb} at position {news.position} of {news.total} in {html_path}.")
        return

    html_path.write_text(updated, encoding="utf-8")

    print(f"{action} publication:")
    print(f"  Title:  {title}")
    print(f"  Venue:  {publication_venue(entry, year, args.venue)}")
    print(f"  Year:   {year}")
    print(f"  Paper:  {paper or '(no url/doi in the BibTeX entry)'}")
    print(f"  Key:    {entry.key}")
    if existing:
        kept = ", ".join(label for label, _ in preserved)
        print(f"  Kept:   {kept or '(no extra buttons)'}")
    print(f"  File:   {html_path} (position {position} of {total})")
    if news:
        print(
            f"  News:   {news_text} "
            f"(position {news.position} of {news.total})"
        )


if __name__ == "__main__":
    main()
