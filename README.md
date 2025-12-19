# Twitter Archive → Static HTML “Book” (Threads) + Compendium

This repo turns a Twitter export (Dec 2022 schema) into a static HTML book:
- One chapter per selected thread
- (Later) A compendium of selected singleton tweets, tagged and styled

## Directory layout (canonical)

- `data/`
  - `tweets_normalized.jsonl` — normalized full tweets with `raw` payload
  - `threads_data.jsonl` — thread extraction output
  - `threads_data_patched.jsonl` — tweet-level deletions applied (drops within threads)
  - `threads_data_ops_patched.jsonl` — thread-level ops applied (merge/append/drop)
  - `selection_final_clean.json` — final selected chapter thread_ids (post-clean)
  - `thread_patches.json` — tweet-level patch list (drops within threads)
  - `thread_ops.json` — thread-level ops (merge/append/drop)
  - scripts (see below)

- `book/`
  - `index.html` — book index
  - `chapters/` — generated chapters `NNN_<thread_id>.html`
  - `assets/media/` — local media copied from export for embedding
  - `style.css`
  - `thread_cleanup_ui.html` — UI to drop tweets within chapters
  - `chapters_list.json` — index used by cleanup UI

IMPORTANT: There used to be an accidental `data/book/` tree. The canonical one is `book/`.

## Core scripts (pipeline)

### A) Normalize tweets (one-time / whenever raw changes)
Creates `tweets_normalized.jsonl`.

### B) Build threads
Creates `threads_data.jsonl`, then apply filtering to select long threads for chapter candidates.

### C) Tweet-level cleanup (remove junk tweets inside threads)
- Use cleanup UI + patch file
- Apply patches → `threads_data_patched.jsonl`

### D) Thread-level operations (merge/append/drop)
Apply ops on top of cleaned threads:
- INPUT: `threads_data_patched.jsonl`
- OUTPUT: `threads_data_ops_patched.jsonl`

Typical ops:
- merge a continuation thread into another
- append a reply-chain continuation
- drop unwanted threads/chapters by *thread_id/root*

### E) Clean selection
If ops/drops removed some threads, clean selection:
- INPUT: `selection_final.json`
- OUTPUT: `selection_final_clean.json`

### F) Copy media to book assets
Copies referenced media from export to `book/assets/media/`.
Local export filenames are typically `<prefix>-<pbs_basename>.<ext>`.
We index by `<pbs_basename>` and copy all matches.

### G) Generate book HTML
Generates `book/chapters/*.html` and `book/index.html` from:
- threads: `threads_data_ops_patched.jsonl`
- selection: `selection_final_clean.json`
- tweets: `tweets_normalized.jsonl`

Generator also:
- embeds local media if available in `book/assets/media/`
- embeds self-quoted/self-linked tweets as indented quote boxes
- leaves other links as links

### H) Rebuild chapters list for cleanup UI
Generates `book/chapters_list.json` from `book/chapters/`.

## Regeneration order (common workflow)

1. Apply tweet-level drops → `threads_data_patched.jsonl`
2. Apply thread ops → `threads_data_ops_patched.jsonl`
3. Clean selection → `selection_final_clean.json`
4. Copy media → `book/assets/media/`
5. Generate book (wipes old chapters) → `book/chapters/*.html`
6. Rebuild chapters list → `book/chapters_list.json`

## Key gotchas learned

- “Thread id” vs “tweet id”: drops/selection must use *thread root id*.
- Always wipe `book/chapters/*.html` before regenerating to avoid stale chapters.
- Cleanup UI indexes can go stale; rerun chapter list builder after regenerating.
- Media filenames in export are not the pbs basename alone; they’re prefixed.

## Current status checkpoint (update this as you go)

- Chapters: stable selection, tweet-level drops done, thread ops applied, media embeds working.
- Quote boxes: present but need styling improvements.
- Next major tasks:
  1) Finish singleton compendium selection/tagging and generate compendium pages
  2) Integrate compendium into book index/nav
  3) Styling pass (typography, quote box formatting, media layout)
  4) Metadata + chapter titles + intro + cover image

## How to run locally

Serve the book:
```sh
cd book
python3 -m http.server 8000
