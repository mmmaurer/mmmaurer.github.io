#!/usr/bin/env python3
"""
Convert an Obsidian blog entry to an HTML page and register it in blog.html
and blog/tags.html.

Usage:
    python convert_post.py "/path/to/Obsidian Vault/Blog/Post.md"
    python convert_post.py "/path/to/Obsidian Vault/Blog/Post.md" --add-news

Images referenced with Obsidian's ![[file.jpg]] syntax are copied from
the vault's attachments folder into assets/img/blog/.

With ``--add-news`` a news item "New blog post: <title>" is also added to
index.html, where the title links to the new post.
"""

import argparse
import html as html_lib
import json
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

import markdown as md_lib
import yaml

import add_news

# ── Configurable paths ─────────────────────────────────────────────────────────
WEBSITE_ROOT      = Path(__file__).resolve().parent
BLOG_DIR          = WEBSITE_ROOT / "blog"
ASSETS_BLOG_IMG   = WEBSITE_ROOT / "assets" / "img" / "blog"
BLOG_HTML         = WEBSITE_ROOT / "blog.html"
TAGS_HTML         = WEBSITE_ROOT / "blog" / "tags.html"
INDEX_HTML        = WEBSITE_ROOT / "index.html"


# ── Parsing ────────────────────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from body; returns ({}, full_text) if none found."""
    if not text.startswith("---"):
        return {}, text
    try:
        end = text.index("---", 3)
    except ValueError:
        return {}, text
    fm = yaml.safe_load(text[3:end]) or {}
    body = text[end + 3:].lstrip("\n")
    return fm, body


def handle_obsidian_images(body: str) -> tuple[str, list[str]]:
    """
    Replace Obsidian ![[file]] embeds with standard Markdown image syntax
    pointing at the website's blog image asset folder.
    Returns the modified body and a list of referenced filenames.
    """
    found: list[str] = []

    def _replace(m: re.Match) -> str:
        fname = m.group(1)
        found.append(fname)
        return f"![{fname}](../assets/img/blog/{fname})"

    return re.sub(r"!\[\[([^\]]+)\]\]", _replace, body), found


def first_paragraph_text(html: str) -> str:
    """Return the plain text of the first <p> block (used as excerpt)."""
    m = re.search(r"<p>(.*?)</p>", html, re.DOTALL)
    return re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""


_ZOOM_ICON = (
    '<span class="zoom-btn" aria-hidden="true">'
    '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
    '<circle cx="10" cy="10" r="6"/>'
    '<line x1="14.5" y1="14.5" x2="20" y2="20"/>'
    '<line x1="10" y1="7" x2="10" y2="13"/>'
    '<line x1="7" y1="10" x2="13" y2="10"/>'
    '</svg>'
    '</span>'
)


def wrap_images(html: str) -> str:
    """Wrap each <img> with a clickable container and a zoom-in icon overlay."""
    def _lazy(tag: str) -> str:
        """Ask the browser to defer off-screen images without breaking the tag."""
        if "loading=" in tag:
            return tag
        if tag.endswith("/>"):
            return tag[:-2].rstrip() + ' loading="lazy" decoding="async" />'
        return tag[:-1].rstrip() + ' loading="lazy" decoding="async">'

    def _wrap(m: re.Match) -> str:
        return f'<span class="blog-img-wrap">{_lazy(m.group(0))}{_ZOOM_ICON}</span>'
    return re.sub(r"<img\b[^>]*>", _wrap, html)


def _find_attachment(fname: str, src: Path) -> Path | None:
    """
    Locate an attachment by walking up from the source file's directory,
    checking for an 'attachments' subfolder at each level.
    Obsidian typically stores pasted images at the vault root's attachments/.
    """
    directory = src.parent
    while True:
        candidate = directory / "attachments" / fname
        if candidate.exists():
            return candidate
        parent = directory.parent
        if parent == directory:
            return None
        directory = parent


def parse_date(val) -> date:
    """Coerce a YAML date, datetime, or ISO date string to a date."""
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        return datetime.strptime(val, "%Y-%m-%d").date()
    return val


def format_date(val) -> str:
    """Format a date or ISO string to 'Month D, YYYY'."""
    return parse_date(val).strftime("%B %-d, %Y")


# ── HTML generation ────────────────────────────────────────────────────────────

# Nav markup and the theme/lightbox scripts are now shared via ../site.js:
#   - <nav class="sidebar" id="site-nav"></nav>  (rendered by site.js)
#   - <script src="../site.js" defer></script>   (theme, bibtex, news, lightbox)
#
# The theme is applied by an inline script before first paint (no flash), and
# the speculationrules block lets Chrome prerender pages on hover.

THEME_BOOT = """    <!-- Set the theme before the first paint to avoid a light flash. -->
    <script>
        (() => {
            try {
                const stored = localStorage.getItem('theme');
                const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
                document.documentElement.dataset.theme = stored || (dark ? 'dark' : 'light');
            } catch (_) { /* private mode: keep the default theme */ }
        })();
    </script>"""

SPECULATION_RULES = """    <!-- Chrome can prerender pages on hover, making navigation instant. -->
    <script type="speculationrules">
        {
            "prerender": [{
                "source": "document",
                "where": { "selector_matches": "a[href]:not([target]):not([download])" },
                "eagerness": "moderate"
            }]
        }
    </script>"""


def render_post_page(title: str, date_str: str, tags: list[str], content_html: str) -> str:
    tag_links = "\n                            ".join(
        f'<a href="tags.html?tag={t}" class="blog-tag">{t}</a>' for t in tags
    )
    indented_content = "\n".join(
        "                    " + line if line.strip() else line
        for line in content_html.splitlines()
    )
    safe_title = html_lib.escape(title)
    description = html_lib.escape(f"Blog post: {title}")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

{THEME_BOOT}

    <title>{safe_title} — Maximilian Maurer</title>
    <meta name="description" content="{description}">
    <meta name="color-scheme" content="light dark">
    <meta name="theme-color" content="#fbfbfc">

    <link rel="icon" href="../assets/icons/favicon.svg" type="image/svg+xml">
    <link rel="icon" href="../assets/icons/favicon-32.png" type="image/png" sizes="32x32">
    <link rel="apple-touch-icon" href="../assets/icons/apple-touch-icon.png">
    <link rel="stylesheet" href="../styles.css">

{SPECULATION_RULES}
</head>
<body>
    <a class="skip-link" href="#main">Skip to content</a>
    <div class="container">
        <nav class="sidebar" id="site-nav"></nav>

        <main class="content" id="main" tabindex="-1">
            <article class="section blog-post">
                <div class="blog-post-header">
                    <h1>{safe_title}</h1>
                    <div class="blog-post-meta">
                        <span class="blog-date">{date_str}</span>
                        <div class="blog-tags">
                            {tag_links}
                        </div>
                    </div>
                </div>

                <div class="blog-post-content">
{indented_content}
                </div>

                <div class="blog-post-footer">
                    <a href="../blog.html" class="back-to-blog">← Back to Blog</a>
                </div>
            </article>
        </main>
        <div class="lightbox" id="lightbox" role="dialog" aria-modal="true" aria-label="Image viewer" tabindex="-1">
            <img id="lightbox-img" src="" alt="">
        </div>
    </div>
    <script src="../site.js" defer></script>
</body>
</html>
"""


# ── Registry updates ───────────────────────────────────────────────────────────

def update_blog_html(title: str, date_str: str, tags: list[str], excerpt: str, filename: str) -> None:
    """Prepend a new <article> entry to the blog-list in blog.html."""
    text = BLOG_HTML.read_text(encoding="utf-8")
    tag_links = "\n                                ".join(
        f'<a href="blog/tags.html?tag={t}" class="blog-tag">{t}</a>' for t in tags
    )
    safe_title = html_lib.escape(title)
    safe_excerpt = html_lib.escape(excerpt)
    new_entry = (
        f'                    <article class="blog-entry">\n'
        f'                        <h3><a href="blog/{filename}">{safe_title}</a></h3>\n'
        f'                        <div class="blog-meta">\n'
        f'                            <span class="blog-date">{date_str}</span>\n'
        f'                            <span class="blog-tags">\n'
        f'                                {tag_links}\n'
        f'                            </span>\n'
        f'                        </div>\n'
        f'                        <p class="blog-excerpt">{safe_excerpt}</p>\n'
        f'                        <a href="blog/{filename}" class="read-more">Read more</a>\n'
        f'                    </article>'
    )
    marker = '<div class="blog-list">'
    idx = text.index(marker) + len(marker)
    BLOG_HTML.write_text(text[:idx] + "\n" + new_entry + "\n" + text[idx:], encoding="utf-8")


def update_tags_html(title: str, date_str: str, tags: list[str], excerpt: str, filename: str) -> None:
    """Prepend a new entry to the POSTS array in blog/tags.html."""
    text = TAGS_HTML.read_text(encoding="utf-8")
    new_entry = (
        "            {\n"
        f"                title: {json.dumps(title)},\n"
        f"                url: {json.dumps(filename)},\n"
        f"                date: {json.dumps(date_str)},\n"
        f"                tags: {json.dumps(tags)},\n"
        f"                excerpt: {json.dumps(excerpt)},\n"
        "            },"
    )
    marker = "const POSTS = ["
    idx = text.index(marker) + len(marker)
    TAGS_HTML.write_text(text[:idx] + "\n" + new_entry + "\n" + text[idx:], encoding="utf-8")


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert an Obsidian blog entry to an HTML page."
    )
    parser.add_argument("input", help="Path to the Obsidian Markdown file")
    parser.add_argument(
        "--add-news",
        action="store_true",
        help=(
            'also add the news item "New blog post: <title>" to index.html, '
            "linking to the new post"
        ),
    )
    args = parser.parse_args()

    src = Path(args.input).expanduser().resolve()
    if not src.exists():
        sys.exit(f"Error: file not found: {src}")

    # Read the news page up front so a broken index.html is reported before
    # any files are written.
    news_page = ""
    if args.add_news:
        if not INDEX_HTML.exists():
            sys.exit(f"Error: news page not found: {INDEX_HTML}")
        news_page = INDEX_HTML.read_text(encoding="utf-8")
        if add_news.NEWS_LIST_MARKER not in news_page:
            sys.exit(f"Error: no news list found in {INDEX_HTML}")

    raw = src.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(raw)

    title    = fm.get("title", src.stem)
    date_val = fm.get("date", datetime.today().date())
    tags     = fm.get("tags") or []
    date_str = format_date(date_val)

    # Resolve Obsidian image embeds → standard Markdown + copy files
    body, image_files = handle_obsidian_images(body)
    if image_files:
        ASSETS_BLOG_IMG.mkdir(parents=True, exist_ok=True)
        for fname in image_files:
            src_img = _find_attachment(fname, src)
            if src_img is not None:
                shutil.copy2(src_img, ASSETS_BLOG_IMG / fname)
                print(f"  Copied: {fname}")
            else:
                print(f"  Warning: attachment not found: {fname}", file=sys.stderr)

    # Convert Markdown → HTML
    converter = md_lib.Markdown(extensions=["extra", "smarty"])
    content_html = converter.convert(body)
    content_html = wrap_images(content_html)
    excerpt = first_paragraph_text(content_html)

    # Write post HTML
    timestamp    = datetime.now().strftime("%Y%m%d%H%M%S")
    post_filename = f"{timestamp}.html"
    out_path     = BLOG_DIR / post_filename
    out_path.write_text(
        render_post_page(title, date_str, tags, content_html),
        encoding="utf-8",
    )
    print(f"  Created:  blog/{post_filename}")

    # Update registries
    update_blog_html(title, date_str, tags, excerpt, post_filename)
    print(f"  Updated:  blog.html")
    update_tags_html(title, date_str, tags, excerpt, post_filename)
    print(f"  Updated:  blog/tags.html")

    # Announce the post in the news section of index.html
    if args.add_news:
        post_url = f"blog/{post_filename}"
        news_text = f"New blog post: {title}"
        news_html = (
            f'New blog post: <a href="{post_url}">'
            f'{html_lib.escape(title, quote=False)}</a>'
        )
        try:
            result = add_news.upsert_news_item(
                news_page,
                message=news_text,
                date_str=parse_date(date_val).isoformat(),
                message_html=news_html,
                match_href=post_url,
            )
        except ValueError as error:
            sys.exit(f"Error: could not add the news item: {error}")
        INDEX_HTML.write_text(result.html, encoding="utf-8")
        print(
            f"  Updated:  index.html "
            f"(news item at position {result.position} of {result.total})"
        )

    print(f"\nDone — post live at blog/{post_filename}")


if __name__ == "__main__":
    main()
