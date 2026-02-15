# Twitter Archive → Static HTML Book

Converts a Dec 2022 Twitter export into a static HTML "book" with curated thread chapters, a compendium of singleton tweets, and frontmatter (cover, title page, ToC, preface).

**Title:** *vgr: The Twitter Years, 2007–22*
**Author:** Venkatesh Rao
**Live:** https://venkateshrao.com/twitter-book/

## Directory layout

```
data/
  tweets_normalized.jsonl      — normalized tweets with raw payload
  threads_data.jsonl           — thread extraction output
  threads_data_patched.jsonl   — tweet-level deletions applied
  threads_data_ops_patched.jsonl — thread-level ops applied (merge/append/drop)
  selection_final_clean.json   — final selected thread IDs + compendium tweet IDs
  chapter_titles.json          — human-edited chapter title overrides
  chapter_summaries.json       — AI-generated chapter summaries (ToC tooltips + headers)
  compendium_tagged_with_prehistory.json — curated singles with tags (includes 2007 tweets)
  thread_patches.json          — tweet-level patch list
  thread_ops.json              — thread-level ops (merge/append/drop)
  url_titles.json              — cached page titles for URLs (fetched)
  url_overrides.json           — manual replacements for broken/hijacked URLs
  frontmatter/                 — hand-edited HTML fragments (cover, title, preface)
  tweet_text_cleanup.py        — shared tweet text rendering (used by both generators)
  generate_compendium_chapter.py — generates Singles chapter
  generate_book_html_with_titles.py — generates everything else
  *.py                         — other pipeline scripts (see below)

book/                          — generated output (served as static site)
  index.html                   — cover page
  toc.html                     — table of contents
  style.css                    — main stylesheet (hand-edited, never overwritten by build)
  compendium.css               — singles chapter styling (hand-edited, never overwritten)
  mobile.css                   — mobile-responsive overrides (hand-edited, never overwritten)
  chapters/
    title.html                 — title page
    preface.html               — preface
    compendium.html            — "Singles" compendium (396 curated tweets)
    chapter_<id>.html          — thread chapters (101 chapters)
  assets/
    cover.png                  — cover image
    media/                     — embedded images, videos, GIFs (~50 files)
```

## Build and deploy

```bash
# Standard rebuild (run both, in this order):
python3 data/generate_compendium_chapter.py
python3 data/generate_book_html_with_titles.py

# Preview:
cd book && python3 -m http.server 8000

# Deploy to venkateshrao.com/twitter-book:
bash deploy.sh
cd ~/Dropbox/Code/consulting/vgururao.github.io
git add twitter-book/ && git commit -m "Update twitter-book" && git push
```

### Other pipeline scripts (run only when upstream data changes)

```bash
python3 data/normalize_tweets.py         # Normalize raw tweets (one-time)
python3 data/build_threads.py            # Build threads from normalized tweets
python3 data/apply_thread_patches.py     # Apply tweet-level drops
python3 data/apply_thread_ops.py         # Apply thread-level ops (merge/append/drop)
python3 data/clean_selection_threads.py  # Clean selection after ops
python3 data/copy_media_to_book.py       # Copy media to book assets (selected content only)
python3 data/fetch_url_titles.py         # Fetch/update URL page titles
```

## Features

- **102 chapters**: 1 compendium of 396 curated singles + 101 thread chapters, chronologically ordered
- **Chapter titles and summaries**: Human-edited titles, AI-generated "In which I..." summaries shown in headers and ToC tooltips
- **Typography**: Georgia serif body, system-ui sans titles, warm parchment/cream palette
- **URL link text**: Fetched page titles cached in `url_titles.json`, with fallback chain (override title → fetched title → display_url → "link")
- **URL overrides**: Broken/hijacked links replaced via `url_overrides.json`
- **Self-tweet embedding**: References to own tweets rendered as indented quote boxes
- **External tweet references**: Rendered as "tweet" link with superscript endnotes per chapter
- **Media**: Photos, videos, and animated GIFs embedded; t.co URLs stripped from text
- **Twitter markdown**: `*bold*` and `_italics_` rendered as HTML
- **Navigation**: Boxed nav bar on every page with prev/next/ToC links
- **Mobile-responsive**: Viewport meta + dedicated mobile CSS for phone readability
- **Social cards**: Open Graph and Twitter Card meta on every page with cover image and per-chapter summaries
- **Permalink anchors**: Each compendium tweet has a direct-link anchor for sharing individual singles
- **Page metadata**: `<title>` tags with book title prefix on all pages

## Search engine and LLM discoverability

The build generates three discovery files in `book/`:

- **`sitemap.xml`** — standard XML sitemap for search engine crawlers (106 URLs with priority hints)
- **`llms.txt`** — Markdown index following the [llms.txt spec](https://llmstxt.org/): book title, summary, and all 102 chapters with titles, dates, and summaries
- **`llms-full.txt`** — the entire book as a single ~730KB Markdown file: all tweet text from all 102 chapters with expanded URLs, no HTML markup

These are generated automatically at the end of `generate_book_html_with_titles.py` and deployed with the rest of the site.

## Future subprojects

### ePub
Generate an ePub version of the book for e-readers (Kindle, Apple Books, etc.).

### Print/PDF
Generate a print-ready PDF version with proper page layout, margins, and typography.

### Oracle
Put the full ~150k tweet archive online as a queryable corpus with an associated AI model. Four phases:

1. **Normalize full corpus** — Clean the entire archive (not just the curated 102 chapters) into a single canonical format. Consistent fields, full thread reconstruction for all threads.
2. **IPFS archival** — Pin the rendered book + full corpus on IPFS for permanent addressability. GitHub Pages remains primary access; IPFS as the permanence layer.
3. **RAG-based query interface** — Embed all tweets into a vector store, build semantic search + retrieval-augmented generation. Allows queries like "what did vgr say about X?" with cited source tweets. Could be a lightweight web app or CLI tool.
4. **MCP server + fine-tuned oracle** — Expose the corpus and search tools via an MCP server, so LLM clients (Claude Desktop, Claude Code, etc.) can query the archive directly through tool use. Explore fine-tuning or persona distillation to create a model that responds in vgr's voice/style. Hybrid approach: RAG for factual grounding + system prompt for personality. Consider mixing in ribbonfarm/blog content for richer training signal.

## Pending cleanup

- Fix chapter 57 title (contains raw t.co URL in `chapter_titles.json`)
- Remove ghost thread `1279451428302422016` from `selection_final_clean.json`
- Retrieve other-people's tweets via Wayback Machine for quote-box embedding
- Clean up stale `_old` script files in `data/`

## A note on forking

This repo is not a generic "Twitter archive to book" tool. It is a bespoke editorial pipeline built for one specific book. Almost everything of value here — the thread selection, chapter titles, summaries, compendium curation, preface — is hand-crafted content, not reusable automation.

If you want to make a similar book from your own Twitter archive, this repo may be useful as *reference* for how to approach the problem: how to extract and normalize tweets, build threads, render text with proper link handling, embed media, and generate a navigable static site. But you should expect to read the code and adapt it to your needs, not drop in your data and hit "build." The handle `@vgr` is hardcoded in several regexes, the selection and curation files are specific to this project, and the generators make assumptions about the structure of this particular book.

In short: study it, steal ideas from it, but don't expect it to work out of the box for a different archive.
