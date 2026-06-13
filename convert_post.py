#!/usr/bin/env python3
"""
Convert an Obsidian blog entry to an HTML page and register it in blog.html
and blog/tags.html.

Usage:
    python convert_post.py "/path/to/Obsidian Vault/Blog/Post.md"

Images referenced with Obsidian's ![[file.jpg]] syntax are copied from
the vault's attachments folder into assets/img/blog/.
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import markdown as md_lib
import yaml

# ── Configurable paths ─────────────────────────────────────────────────────────
WEBSITE_ROOT      = Path(__file__).resolve().parent
BLOG_DIR          = WEBSITE_ROOT / "blog"
ASSETS_BLOG_IMG   = WEBSITE_ROOT / "assets" / "img" / "blog"
BLOG_HTML         = WEBSITE_ROOT / "blog.html"
TAGS_HTML         = WEBSITE_ROOT / "blog" / "tags.html"


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
    def _wrap(m: re.Match) -> str:
        return f'<span class="blog-img-wrap">{m.group(0)}{_ZOOM_ICON}</span>'
    return re.sub(r"<img\b[^>]*>", _wrap, html)


def format_date(val) -> str:
    """Format a date or ISO string to 'Month D, YYYY'."""
    if isinstance(val, str):
        val = datetime.strptime(val, "%Y-%m-%d").date()
    return val.strftime("%B %-d, %Y")


# ── HTML generation ────────────────────────────────────────────────────────────

_NAV = """\
        <nav class="sidebar">
            <div class="nav-content">
                <ul class="nav-list">
                    <li><a href="../index.html#about" class="nav-link">About</a></li>
                    <li><a href="../index.html#publications" class="nav-link">Publications</a></li>
                    <li><a href="../blog.html" class="nav-link">Blog</a></li>
                    <li><a href="../index.html#contact" class="nav-link">Contact</a></li>
                </ul>
                <div class="nav-right">
                    <div class="social-icons">
                        <a href="https://scholar.google.com/citations?user=gKqjcwEAAAAJ" class="social-link" title="Google Scholar">
                            <img src="../assets/icons/gsch.svg" alt="Google Scholar">
                        </a>
                        <a href="https://github.com/mmmaurer" class="social-link" title="GitHub">
                            <img src="../assets/icons/github.svg" alt="GitHub">
                        </a>
                        <a href="https://bsky.app/profile/mmmaurer.bsky.social" class="social-link" title="Bluesky">
                            <img src="../assets/icons/bsky.svg" alt="Bluesky">
                        </a>
                        <a href="https://www.linkedin.com/in/maximilian-martin-maurer-217591268/" class="social-link" title="LinkedIn">
                            <img src="../assets/icons/linkedin.svg" alt="LinkedIn">
                        </a>
                    </div>
                    <button id="theme-toggle" class="theme-toggle" title="Toggle dark mode" aria-label="Toggle dark mode">
                        <span class="toggle-circle">
                            <img src="../assets/icons/sun.svg" alt="Light mode" class="theme-icon theme-icon-sun">
                            <img src="../assets/icons/moon.svg" alt="Dark mode" class="theme-icon theme-icon-moon">
                        </span>
                    </button>
                </div>
            </div>
        </nav>"""

_SCRIPTS = """\
    <script>
        // Theme toggle
        const themeToggle = document.getElementById('theme-toggle');
        const html = document.documentElement;
        html.setAttribute('data-theme', localStorage.getItem('theme') || 'light');
        themeToggle.addEventListener('click', () => {
            const next = html.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
            html.setAttribute('data-theme', next);
            localStorage.setItem('theme', next);
        });

        // Lightbox
        const lightbox    = document.getElementById('lightbox');
        const lightboxImg = document.getElementById('lightbox-img');

        document.querySelectorAll('.blog-img-wrap').forEach(wrap => {
            wrap.addEventListener('click', () => {
                const img = wrap.querySelector('img');
                lightboxImg.src = img.src;
                lightboxImg.alt = img.alt;
                lightbox.classList.add('open');
                document.body.style.overflow = 'hidden';
            });
        });

        lightbox.addEventListener('click', () => {
            lightbox.classList.remove('open');
            document.body.style.overflow = '';
        });

        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') {
                lightbox.classList.remove('open');
                document.body.style.overflow = '';
            }
        });
    </script>"""


def render_post_page(title: str, date_str: str, tags: list[str], content_html: str) -> str:
    tag_links = "\n                            ".join(
        f'<a href="tags.html?tag={t}" class="blog-tag">{t}</a>' for t in tags
    )
    indented_content = "\n".join(
        "                    " + line if line.strip() else line
        for line in content_html.splitlines()
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Maximilian Maurer's Website</title>
    <link rel="stylesheet" href="../styles.css">
</head>
<body>
    <div class="container">
{_NAV}

        <main class="content">
            <article class="section blog-post">
                <div class="blog-post-header">
                    <h1>{title}</h1>
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
        <div class="lightbox" id="lightbox" role="dialog" aria-modal="true" aria-label="Image viewer">
            <img id="lightbox-img" src="" alt="">
        </div>
    </div>
{_SCRIPTS}
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
    new_entry = (
        f'                    <article class="blog-entry">\n'
        f'                        <h3><a href="blog/{filename}">{title}</a></h3>\n'
        f'                        <div class="blog-meta">\n'
        f'                            <span class="blog-date">{date_str}</span>\n'
        f'                            <span class="blog-tags">\n'
        f'                                {tag_links}\n'
        f'                            </span>\n'
        f'                        </div>\n'
        f'                        <p class="blog-excerpt">{excerpt}</p>\n'
        f'                        <a href="blog/{filename}" class="read-more">Read more →</a>\n'
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
    args = parser.parse_args()

    # vault_attachments is ../attachments relative to the blog post,
    # so we need to resolve it against the input file's parent directory
    vault_attachments = (Path(args.input).parent / "attachments").expanduser().resolve()

    src = Path(args.input).expanduser().resolve()
    if not src.exists():
        sys.exit(f"Error: file not found: {src}")

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
            src_img = vault_attachments / fname
            if src_img.exists():
                shutil.copy2(src_img, ASSETS_BLOG_IMG / fname)
                print(f"  Copied: {fname}")
            else:
                print(f"  Warning: attachment not found: {src_img}", file=sys.stderr)

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

    print(f"\nDone — post live at blog/{post_filename}")


if __name__ == "__main__":
    main()
