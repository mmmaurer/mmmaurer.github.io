#!/usr/bin/env python3
"""
Add a news item to the news section of index.html.

The news text is the main input argument: either a quoted string or a path to
a ``.txt``/``.md`` file.  The item is dated today by default; use ``--date`` to
pick another day.  Optional flags add link buttons (paper, code, data, poster,
slides) and arbitrary labelled buttons via ``--link``.

Items are ordered newest first.  If an item with the same date and text
already exists, it is replaced (handy for adding a poster or fixing a link);
pass ``--force`` to add a duplicate instead.

The module is also imported by ``convert_post.py`` and ``add_publication.py``,
which pass ``--add-news`` to announce a new blog post or publication here.
Use ``upsert_news_item()`` for that: it accepts pre-built paragraph markup
(e.g. a linked title) and can identify an existing item by the link it
contains, so re-running a script updates its announcement instead of adding
a duplicate.

Usage:
    python add_news.py "I will present our paper at EMNLP 2026!"
    python add_news.py news.txt --date 2026-10-20 --paper https://aclanthology.org/...
    python add_news.py "Invited talk in Bamberg" --slides assets/pdf/slides/talk.pdf

Run ``python add_news.py --help`` for all options.
"""

from __future__ import annotations

import argparse
import html as html_lib
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# ── Configurable paths ─────────────────────────────────────────────────────────
WEBSITE_ROOT = Path(__file__).resolve().parent
INDEX_HTML = WEBSITE_ROOT / "index.html"

NEWS_LIST_MARKER = '<div class="news-list" id="news-list">'
INDENT = " " * 20  # indentation of <article> elements inside the list


class NewsError(ValueError):
    """Raised when the input cannot be turned into a news item."""


# ── Input handling ─────────────────────────────────────────────────────────────

def _load_news_text(source: str) -> str:
    """Read news text from a file path, or return the argument as inline text."""
    path = Path(source).expanduser()
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    except OSError:
        # Long inline text can exceed the filesystem's name limit; treat it as text.
        return source

    if source.lower().endswith((".txt", ".md", ".markdown")):
        raise FileNotFoundError(f"file not found: {path}")
    return source


def _normalize_message(message: str) -> str:
    """Collapse whitespace so the news item fits on one paragraph line."""
    return re.sub(r"\s+", " ", message).strip()


def _validate_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise NewsError(f"invalid date {value!r}; use the YYYY-MM-DD format") from error


def _validate_url(url: str, source: str) -> str:
    """Reject unsafe links; relative asset paths are allowed."""
    url = url.strip().strip("{}").strip()
    # Repair the common "https:/example.org" typo (but leave "https://" alone).
    url = re.sub(r"^(https?):/(?!/)", r"\1://", url, flags=re.IGNORECASE)
    if not url:
        raise NewsError(f"empty URL passed via {source}")
    scheme = re.match(r"^([A-Za-z][A-Za-z0-9+.\-]*):", url)
    if scheme and scheme.group(1).lower() not in {"http", "https", "mailto"}:
        raise NewsError(
            f"unsupported URL scheme {scheme.group(1)!r} in {source}: {url}"
        )
    return url


# ── HTML helpers ───────────────────────────────────────────────────────────────

def _link_html(label: str, url: str) -> str:
    safe_label = html_lib.escape(label, quote=False)
    safe_url = html_lib.escape(url, quote=True)
    return (
        f'<a class="btn" href="{safe_url}" target="_blank" rel="noopener">'
        f'{safe_label}</a>'
    )


def _build_buttons(provided: list[tuple[str, str]],
                   preserved: list[tuple[str, str]]) -> list[str]:
    """Build the optional button row, keeping links from a replaced item."""
    ordered: list[tuple[str, str]] = []
    seen: set[str] = set()
    for label, url in provided:
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append((label, url))

    for label, url in preserved:
        if label.casefold() in seen:
            continue
        seen.add(label.casefold())
        ordered.append((label, url))

    return [_link_html(label, url) for label, url in ordered]


def _extract_buttons(article: str) -> list[tuple[str, str]]:
    """Return ``(label, href)`` for the link buttons of an existing item."""
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


def _news_date(article: str) -> str:
    match = re.search(r'<p class="news-date"><strong>([^<]*)</strong></p>', article)
    return match.group(1).strip() if match else ""


def _news_message(article: str) -> str:
    match = re.search(r"<p>(.*?)</p>", article, re.DOTALL)
    if not match:
        return ""
    return html_lib.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()


def render_news_item(date_str: str, message: str, buttons: list[str],
                     message_html: str | None = None) -> str:
    """Render a fully indented <article class="news-item"> block.

    ``message_html`` lets callers such as the ``--add-news`` option of the
    blog/publication scripts supply ready-made paragraph markup (for example
    a clickable title).  Without it, ``message`` is HTML-escaped.
    """
    body = html_lib.escape(message, quote=False) if message_html is None else message_html
    lines = [
        '<article class="news-item">',
        f'    <p class="news-date"><strong>{html_lib.escape(date_str)}</strong></p>',
        f'    <p>{body}</p>',
    ]
    if buttons:
        lines.append('    <div class="pub-buttons">')
        lines.extend(f'        {button}' for button in buttons)
        lines.append('    </div>')
    lines.append('</article>')
    return "\n".join(INDENT + line for line in lines)


# ── Finding and inserting items ────────────────────────────────────────────────

NEWS_ITEM_RE = re.compile(
    r'[ \t]*<article class="news-item">.*?</article>', re.DOTALL
)


def find_news_item(text: str, date_str: str, message: str,
                   match_href: str | None = None) -> re.Match | None:
    """Find the news item that a new one should replace, if any.

    With ``match_href``, items are identified by the link they contain, which
    keeps a repeated ``--add-news`` run from duplicating an announcement even
    when its text or date changed.  Otherwise items are matched by date and
    text (case/whitespace insensitive).
    """
    if match_href:
        needle = f'href="{html_lib.escape(match_href, quote=True)}"'
        for match in NEWS_ITEM_RE.finditer(text):
            if needle in match.group(0):
                return match
        return None

    target = _normalize_message(message).casefold()
    for match in NEWS_ITEM_RE.finditer(text):
        block = match.group(0)
        if _news_date(block) != date_str:
            continue
        if _normalize_message(_news_message(block)).casefold() == target:
            return match
    return None


def insert_news_item(text: str, block: str, date_str: str) -> tuple[str, int]:
    """Insert an indented news block, newest first, and return (html, position)."""
    marker_index = text.find(NEWS_LIST_MARKER)
    if marker_index == -1:
        raise ValueError(f'could not find {NEWS_LIST_MARKER!r} in the HTML file')
    region_start = marker_index + len(NEWS_LIST_MARKER)

    items = list(NEWS_ITEM_RE.finditer(text[region_start:]))
    if not items:
        return text[:region_start] + "\n" + block + text[region_start:], 1

    insert_before = None
    ordinal = 1
    for index, item in enumerate(items, start=1):
        absolute_start = region_start + item.start()
        # ISO dates sort lexicographically, so string comparison is enough.
        if _news_date(item.group(0)) <= date_str:
            insert_before = absolute_start
            ordinal = index
            break

    if insert_before is not None:
        # Insert at line start so the new item gets standard indentation even
        # if the existing item it precedes is misindented.
        line_start = text.rfind("\n", 0, insert_before) + 1
        existing_indent = text[line_start:insert_before]
        if existing_indent.strip():
            line_start, existing_indent = insert_before, INDENT
        return (
            text[:line_start] + block + "\n" + existing_indent + text[line_start:],
            ordinal,
        )

    # Older than everything currently listed: append at the end of the list.
    last_end = region_start + items[-1].end()
    return text[:last_end] + "\n" + block + text[last_end:], len(items) + 1


def replace_news_item(text: str, match: re.Match, block: str,
                      date_str: str) -> tuple[str, int]:
    """Replace an existing news item in place and return (html, position).

    If the date changed, the old item is removed and the new one inserted at
    the position matching its date, so the list stays ordered.
    """
    if _news_date(match.group(0)) == date_str:
        position = text[:match.start()].count('<article class="news-item">') + 1
        return text[:match.start()] + block + text[match.end():], position

    end = match.end()
    if text[end:end + 1] == "\n":
        end += 1
    return insert_news_item(text[:match.start()] + text[end:], block, date_str)


@dataclass
class NewsResult:
    """Outcome of :func:`upsert_news_item`."""

    html: str       # the updated HTML document
    block: str      # the rendered <article class="news-item"> block
    position: int   # 1-based position of the item in the list
    total: int      # number of items after the update
    replaced: bool  # True if an existing item was updated instead of added


def upsert_news_item(text: str, *, message: str, date_str: str,
                     links: list[tuple[str, str]] | None = None,
                     message_html: str | None = None,
                     match_href: str | None = None,
                     force: bool = False) -> NewsResult:
    """Add a news item to ``text`` (or update an existing one) and return it.

    ``message`` is the plain-text version used for matching and printed
    output; ``message_html`` optionally provides the paragraph markup, e.g. a
    clickable title.  ``links`` are ``(label, url)`` button pairs.  See
    :func:`find_news_item` for the meaning of ``match_href``.
    """
    existing = None if force else find_news_item(
        text, date_str, message, match_href=match_href
    )
    preserved = _extract_buttons(existing.group(0)) if existing else []
    buttons = _build_buttons(links or [], preserved)
    block = render_news_item(date_str, message, buttons, message_html)

    existing_count = len(NEWS_ITEM_RE.findall(text))
    if existing:
        updated, position = replace_news_item(text, existing, block, date_str)
        return NewsResult(updated, block, position, existing_count, True)

    updated, position = insert_news_item(text, block, date_str)
    return NewsResult(updated, block, position, existing_count + 1, False)


# ── Entry point ────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Add a news item to the news section of index.html.",
        epilog=(
            "Examples:\n"
            "  %(prog)s \"I will present our paper at EMNLP 2026!\"\n"
            "  %(prog)s news.txt --date 2026-10-20 --paper https://aclanthology.org/...\n"
            "  %(prog)s \"Talk in Bamberg\" --slides assets/pdf/slides/talk.pdf\n"
            "  %(prog)s \"New dataset released\" --link \"Dataset=https://huggingface.co/...\"\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "text",
        metavar="TEXT",
        help="news text, or a path to a .txt/.md file containing it",
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="date to display (default: today)",
    )
    parser.add_argument("--paper", metavar="URL", help="add a Paper button")
    parser.add_argument("--code", metavar="URL", help="add a Code button")
    parser.add_argument("--data", metavar="URL", help="add a Data button")
    parser.add_argument("--poster", metavar="URL", help="add a Poster button")
    parser.add_argument("--slides", metavar="URL", help="add a Slides button")
    parser.add_argument(
        "--link",
        metavar="LABEL=URL",
        action="append",
        default=[],
        help="add a custom button (repeatable)",
    )
    parser.add_argument(
        "--html",
        metavar="FILE",
        type=Path,
        default=INDEX_HTML,
        help="HTML file to update (default: index.html next to this script)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="add a duplicate instead of replacing an item with the same date and text",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the generated HTML instead of modifying the file",
    )
    args = parser.parse_args(argv)

    try:
        message = _normalize_message(_load_news_text(args.text))
        if not message:
            raise NewsError("the news text is empty")

        news_date = _validate_date(args.date) if args.date else date.today()
        date_str = news_date.isoformat()

        paper = _validate_url(args.paper, "--paper") if args.paper else None
        code = _validate_url(args.code, "--code") if args.code else None
        data = _validate_url(args.data, "--data") if args.data else None
        poster = _validate_url(args.poster, "--poster") if args.poster else None
        slides = _validate_url(args.slides, "--slides") if args.slides else None

        custom_links: list[tuple[str, str]] = []
        for spec in args.link:
            if "=" not in spec:
                raise NewsError(f"--link expects LABEL=URL, got {spec!r}")
            label, url = spec.split("=", 1)
            label = label.strip()
            if not label:
                raise NewsError(f"--link has an empty label in {spec!r}")
            custom_links.append((label, _validate_url(url, "--link")))

        links: list[tuple[str, str]] = []
        for label, url in (
            ("Paper", paper),
            ("Code", code),
            ("Data", data),
            ("Poster", poster),
            ("Slides", slides),
        ):
            if url:
                links.append((label, url))
        links.extend(custom_links)
    except (NewsError, FileNotFoundError) as error:
        sys.exit(f"Error: {error}")

    html_path = args.html.expanduser()
    if not html_path.exists():
        sys.exit(f"Error: HTML file not found: {html_path}")

    text = html_path.read_text(encoding="utf-8")

    try:
        result = upsert_news_item(
            text,
            message=message,
            date_str=date_str,
            links=links,
            force=args.force,
        )
    except ValueError as error:
        sys.exit(f"Error: {error}")

    block, position, total = result.block, result.position, result.total
    existing = result.replaced

    action = "Replaced" if existing else "Added"

    if args.dry_run:
        print("Generated news item (not written):\n")
        print(block)
        verb = "replace the existing news item" if existing else "insert a new news item"
        print(f"\nWould {verb} at position {position} of {total} in {html_path}.")
        return

    html_path.write_text(result.html, encoding="utf-8")

    print(f"{action} news item:")
    print(f"  Date:   {date_str}")
    print(f"  Text:   {message}")
    labels = [label for label, _ in _extract_buttons(block)]
    print(f"  Links:  {', '.join(labels) or '(none)'}")
    print(f"  File:   {html_path} (position {position} of {total})")


if __name__ == "__main__":
    main()
