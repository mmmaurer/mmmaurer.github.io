# mmmaurer.github.io

Source of [mmmaurer.github.io](https://mmmaurer.github.io) — a static personal
website (plain HTML, CSS, and a little JavaScript) with a home page, news and
publication lists, and a small blog.

## Contents

- `index.html` — home page (about, news, publications, contact)
- `blog.html` — blog index; posts live in `blog/`
- `blog/tags.html` — client-side tag filter for the blog
- `styles.css`, `site.js` — shared styling and behaviour (theme toggle, nav,
  BibTeX copy, lightbox, news “show more”)
- `assets/` — icons, images, posters, slides, and PDFs
- `add_publication.py` — add a paper to the publication list from BibTeX
- `add_news.py` — add an item to the news section
- `convert_post.py` — convert an Obsidian note into a blog post

## Requirements

- Python 3.12+
- Dependencies are declared in `pyproject.toml` (`markdown` and `pyyaml`) and
  managed with [uv](https://docs.astral.sh/uv/):

  ```sh
  uv sync
  ```

  Without uv, a plain virtual environment works too:

  ```sh
  python -m venv .venv
  source .venv/bin/activate
  pip install markdown pyyaml
  ```

Commands below use `.venv/bin/python`; with the virtual environment activated,
`python` is equivalent.

## Local preview

Serve the repository root, then open <http://localhost:8000>:

```sh
python -m http.server 8000
```

---

## Adding a publication — `add_publication.py`

`add_publication.py` reads a BibTeX entry and inserts a new
`<article class="publication">` block into the publications section of
`index.html`. It derives the title, author list, venue, place, year, and paper
link from the entry, and adds the BibTeX block used by the “BibTeX” copy
button.

### Basic usage

The first argument is the BibTeX input. It can be a `.bib` file:

```sh
.venv/bin/python add_publication.py paper.bib
```

or the BibTeX entry itself, quoted:

```sh
.venv/bin/python add_publication.py '@inproceedings{maurer-2025-example,
  title = {An Example Paper},
  author = {Maurer, Maximilian and Doe, Jane},
  booktitle = {Proceedings of EMNLP 2025},
  year = {2025},
  address = {Suzhou, China},
  url = {https://aclanthology.org/2025.emnlp-main.000/}
}'
```

Add buttons for code and data with the optional flags:

```sh
.venv/bin/python add_publication.py paper.bib \
  --code https://github.com/mmmaurer/project \
  --data https://huggingface.co/datasets/mmmaurer/project
```

Preview the generated HTML without touching `index.html`:

```sh
.venv/bin/python add_publication.py paper.bib --dry-run
```

### Announcing the paper in the news section

Add `--add-news` to also create a news item for the paper:

```sh
.venv/bin/python add_publication.py paper.bib --add-news
```

The item reads “New publication: *title* *venue*” and is dated today. The title
is a link to the entry in the publication list
(`index.html#publication-<citation key>`), which scrolls straight to it. Every
entry the script writes carries this stable `id`, so the target of the link
always exists.

If the announcement already exists, it is updated rather than duplicated —
even when the venue or the date changed — which keeps repeated runs (for
example after fixing metadata) from stacking up news items.

### Updating an existing publication

Run the script again with the updated BibTeX entry, keeping the title
unchanged. If a publication with the same title is already listed, it is
replaced instead of added — useful for fixing metadata or turning an arXiv
preprint into the peer-reviewed version:

```sh
.venv/bin/python add_publication.py camera_ready.bib
```

The title match ignores case and whitespace differences, but the title text
itself must be the same.

- If the year is unchanged, the entry stays in its current position. If the
  year changes, it moves to the correct place in the year-sorted list.
- Non-BibTeX buttons from the old entry (**Code**, **Data**, **Poster**,
  **Slides**, and custom buttons such as “Raw results”) are carried over.
  Values passed with `--code`, `--data`, `--poster`, or `--slides` replace the
  old link of that name.
- If the new entry has no `url` or `doi`, the old **Paper** link is kept.
- Use `--force` to deliberately add a second entry with the same title.

### What is extracted

| Website element | Source in the BibTeX entry |
| --- | --- |
| Title | `title` (LaTeX markup such as `{AI}` and `{\"o}` is converted to Unicode) |
| Author list | `author` — surnames only, with the site owner in bold; `*` markers are preserved |
| Venue | `booktitle` or `journal`, or `archivePrefix`/`eprint` for preprints (shown as `arXiv 2026`); abbreviated for common venues (e.g. `EMNLP 2025`, `Findings of ACL 2025`, `EACL 2026 (System Demonstrations)`) |
| Place | `address` (or `location`) |
| Year | `year`, then `date`, then the citation key |
| Paper link | `url`, or `doi` as `https://doi.org/…`; used for the title and the “Paper” button |
| BibTeX block | The entry is copied into the copyable `<pre class="bibtex">` block (indentation normalised, single-line entries expanded) |

Unknown venues fall back to their full name (without a leading “Proceedings
of …”); use `--venue` to shorten one manually.

### Options

| Option | Description |
| --- | --- |
| `--code URL` | Add a **Code** button |
| `--data URL` | Add a **Data** button |
| `--poster URL` | Add a **Poster** button |
| `--slides URL` | Add a **Slides** button |
| `--paper URL` | Override the paper link (default: `url`/`doi` from the entry) |
| `--venue VENUE` | Override the detected venue |
| `--year YEAR` | Override the year |
| `--author NAME` | Name to bold in the author list (default: `Maximilian Maurer`; a surname alone matches any author with it) |
| `--key KEY` | Choose an entry by citation key when the `.bib` file has several |
| `--html FILE` | Update another HTML file (default: `index.html`) — useful for testing |
| `--force` | Add a second entry even if a publication with the same title exists (default: replace the existing entry) |
| `--dry-run` | Print the generated HTML instead of writing the file |
| `--add-news` | Also add the news item “New publication: *title* *venue*”, with the title linking to the entry |

### Behaviour

- Entries are ordered newest first. New entries are inserted above existing
  publications from the same year; replaced entries keep their position when
  the year is unchanged.
- If a publication with the same title is already listed, it is replaced by
  default. `--force` adds a duplicate instead.
- Button order is **Paper**, **BibTeX**, **Code**, **Data**, **Poster**,
  **Slides**; a Paper link is omitted if the entry has neither `url` nor `doi`.
- Every written entry gets a stable `id` (`publication-<citation key>`), so
  news items (and other pages) can link to it directly.
- With `--add-news`, the news item is inserted in date order like any other
  item; a second run updates the existing announcement instead of adding
  another one.
- The script only edits the publication list (and, with `--add-news`, the news
  list); review the result with `git diff` and revert with
  `git checkout -- index.html` if needed.

---

## Adding a news item — `add_news.py`

`add_news.py` adds an item to the news section of `index.html`.

### Usage

```sh
.venv/bin/python add_news.py "I will present our paper at EMNLP 2026!"
```

The text can also come from a `.txt` or `.md` file:

```sh
.venv/bin/python add_news.py news.txt --date 2026-10-20
```

File contents are read as plain text.

Add optional link buttons:

```sh
.venv/bin/python add_news.py "Promptology at EMNLP 2026" \
  --date 2026-10-20 \
  --paper https://aclanthology.org/2026.emnlp-main.428/ \
  --poster assets/pdf/posters/promptology_poster.pdf
```

Arbitrary labelled buttons use `--link`:

```sh
.venv/bin/python add_news.py "New dataset released" \
  --link "Dataset=https://huggingface.co/datasets/mmmaurer/project"
```

### Options

| Option | Description |
| --- | --- |
| `--date YYYY-MM-DD` | Date shown above the item (default: today) |
| `--paper URL` | Add a **Paper** button |
| `--code URL` | Add a **Code** button |
| `--data URL` | Add a **Data** button |
| `--poster URL` | Add a **Poster** button |
| `--slides URL` | Add a **Slides** button |
| `--link LABEL=URL` | Add a custom button (repeatable) |
| `--html FILE` | Update another HTML file (default: `index.html`) — useful for testing |
| `--force` | Add a duplicate instead of replacing an item with the same date and text |
| `--dry-run` | Print the generated HTML instead of writing the file |

### Behaviour

- Items are ordered newest first; new items go above existing items from the
  same date.
- The text is HTML-escaped and whitespace-normalised, so `<`, `>`, and `&`
  are displayed literally. Multi-line text is joined into one paragraph.
- If an item with the same date and text already exists, it is replaced in
  place, keeping its button links unless overridden by flags. This makes it
  easy to add a poster or fix a link later. `--force` adds a duplicate instead.
- If no link flags are given, the button row is omitted.
- The script only edits the news list; review the result with `git diff` and
  revert with `git checkout -- index.html` if needed.
- New blog posts and publications are announced with `--add-news` in
  `convert_post.py` and `add_publication.py`, which use the same machinery: if
  an item already links to the same target, it is updated in place (moving to
  its new date if that changed) instead of being duplicated.

---

## Adding a blog post — `convert_post.py`

`convert_post.py` converts an Obsidian Markdown note into a standalone HTML
page, copies its images into the website, and registers the post in the blog
index and tag filter.

### Usage

```sh
.venv/bin/python convert_post.py "/path/to/Obsidian Vault/Blog/My Post.md"
```

Add `--add-news` to announce the post in the news section of `index.html`:

```sh
.venv/bin/python convert_post.py "/path/to/Obsidian Vault/Blog/My Post.md" --add-news
```

The resulting item reads “New blog post: *title*”, where the title links to the
new post. The item is shown with the post's frontmatter date.

The script:

1. Reads YAML frontmatter and the Markdown body.
2. Converts Obsidian image embeds (`![[image.jpg]]`) to normal Markdown images
   and copies each file from the nearest `attachments/` folder into
   `assets/img/blog/`.
3. Converts Markdown to HTML, adds lazy loading and a click-to-zoom lightbox
   wrapper to images, and uses the first paragraph as the excerpt.
4. Writes the post to `blog/<timestamp>.html`.
5. Prepends the post to `blog.html` and to the `POSTS` array in
   `blog/tags.html`.
6. With `--add-news`, adds the news item to `index.html`.

### Frontmatter

```yaml
---
title: My Post
date: 2026-11-13
tags:
  - nlp
  - python
---

Post content starts here.
```

- `title` — used for the page `<title>`, heading, blog index, and tag filter
  (defaults to the file name).
- `date` — `YYYY-MM-DD` (YAML may parse it as a date); defaults to today.
  Displayed as “Month D, YYYY”.
- `tags` — list of tags; each becomes a link to the tag filter.

### Notes

- The post URL is a timestamp (`blog/20261113141516.html`), so running the
  script twice for the same note creates two entries — run it once per post,
  and delete/revert the generated files if you need to redo it.
- Images are copied from an `attachments/` folder in the note’s directory or
  any parent directory, matching the usual Obsidian vault layout.
- The generated page uses the shared `../site.js` and `../styles.css`, so it
  inherits the site navigation, theme, and lightbox.

---

## Repository layout

```text
.
├── index.html                 # home page
├── blog.html                  # blog index
├── blog/                      # generated posts + tags.html
├── assets/                    # icons, images, PDFs (posters, slides)
├── styles.css                 # shared styles
├── site.js                    # shared navigation and behaviour
├── add_publication.py         # BibTeX → publication entry in index.html
├── add_news.py                # news text → news item in index.html
├── convert_post.py            # Obsidian Markdown → blog post
└── pyproject.toml             # Python dependencies
```
