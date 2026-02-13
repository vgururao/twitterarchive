# Twitter Archive → Static HTML Book

Converts a Dec 2022 Twitter export into a static HTML "book" with curated thread chapters, a compendium of singleton tweets, and frontmatter (cover, title page, ToC, preface).

**Title:** *vgr: The Twitter Years, 2007–22*
**Author:** Venkatesh Rao

## Directory layout

```
data/
  tweets_normalized.jsonl      — normalized tweets with raw payload
  threads_data.jsonl           — thread extraction output
  threads_data_patched.jsonl   — tweet-level deletions applied
  threads_data_ops_patched.jsonl — thread-level ops applied (merge/append/drop)
  selection_final_clean.json   — final selected thread IDs + compendium tweet IDs
  chapter_titles.json          — human-edited chapter title overrides
  thread_patches.json          — tweet-level patch list
  thread_ops.json              — thread-level ops (merge/append/drop)
  url_titles.json              — cached page titles for URLs (fetched)
  url_overrides.json           — manual replacements for broken/hijacked URLs
  frontmatter/                 — hand-edited HTML fragments (cover, title, preface)
  *.py                         — pipeline scripts (see below)

book/                          — generated output (served as static site)
  index.html                   — cover page
  toc.html                     — table of contents
  style.css                    — manually edited stylesheet (never overwritten by build)
  chapters/
    title.html                 — title page
    preface.html               — preface
    compendium.html            — "Noteworthy Singletons" (singleton tweets)
    chapter_<id>.html          — thread chapters (101 chapters)
  assets/
    cover.png                  — cover image
    media/                     — embedded images, videos, GIFs (~50 files)
```

## Build process

From repo root:

```bash
# 1. Generate compendium chapter
python3 data/generate_compendium_chapter.py

# 2. Generate book structure (thread chapters, frontmatter, ToC, nav)
python3 data/generate_book_html_with_titles.py

# 3. Preview
cd book && python3 -m http.server 8000
# Open http://localhost:8000
```

### Other pipeline scripts (run only when upstream data changes)

```bash
# Normalize raw tweets (one-time)
python3 data/normalize_tweets.py

# Build threads from normalized tweets
python3 data/build_threads.py

# Apply tweet-level drops
python3 data/apply_thread_patches.py

# Apply thread-level ops (merge/append/drop)
python3 data/apply_thread_ops.py

# Clean selection after ops
python3 data/clean_selection_threads.py

# Copy media from export to book assets (selected content only)
python3 data/copy_media_to_book.py

# Fetch/update URL page titles
python3 data/fetch_url_titles.py
```

## Key features

- **102 chapters**: 1 compendium + 101 thread chapters, chronologically ordered
- **Chapter titles**: Human-edited via `chapter_titles.json`
- **URL link text**: Fetched page titles cached in `url_titles.json`, with fallback chain (override title → fetched title → display_url → "link")
- **URL overrides**: Broken/hijacked links replaced via `url_overrides.json`
- **Self-tweet embedding**: References to own tweets rendered as quote boxes
- **External tweet references**: Rendered as "tweet" link with superscript endnotes per chapter
- **Media**: Photos, videos, and animated GIFs embedded; t.co URLs stripped from text
- **Twitter markdown**: `*bold*` and `_italics_` rendered as HTML
- **Navigation**: Top/bottom nav on every page with prev/next/ToC links

## Current status

- Thread chapters: complete, stable selection
- Compendium: generated, content complete
- Frontmatter: cover and title page done; preface has placeholder lorem ipsum
- Media: 50 assets (images + MP4s for animated GIFs)
- Links: titles fetched, overrides system in place, endnotes for external tweets
- Styling: functional, could use a polish pass

## Pending work

- Write real preface content
- Fix chapter 57 title (contains raw t.co URL in `chapter_titles.json`)
- Remove ghost thread `1279451428302422016` from `selection_final_clean.json`
- Retrieve other-people's tweets via Wayback Machine for quote-box embedding (pinned for later)
- ePub and print book generation
- Typography and styling polish pass
- Clean up stale `_old` script files in `data/`
