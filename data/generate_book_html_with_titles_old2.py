#!/usr/bin/env python3
import json
import re
import subprocess
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import escape
from pathlib import Path
# from data.tweet_text_cleanup import render_tweet_text_html
from tweet_text_cleanup import render_tweet_text_html


HERE = Path(__file__).resolve()
ROOT = HERE.parent.parent

DATA_DIR = ROOT / "data"
BOOK_DIR = ROOT / "book"
CHAPTERS_DIR = BOOK_DIR / "chapters"
ASSETS_DIR = BOOK_DIR / "assets"
ASSETS_MEDIA_DIR = ASSETS_DIR / "media"

# Canonical inputs
THREADS_DATA = DATA_DIR / "threads_data_ops_patched.jsonl"
TWEETS_DATA = DATA_DIR / "tweets_normalized.jsonl"
SELECTION = DATA_DIR / "selection_final_clean.json"
CHAPTER_TITLES_PATH = DATA_DIR / "chapter_titles.json"

# Output
INDEX_PATH = BOOK_DIR / "index.html"

STATUS_URL_RE = re.compile(r"https?://(?:x|twitter)\.com/[^/]+/status/(\d+)")


def iter_jsonl(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def parse_created_at_any(ts: str):
    if not ts:
        return None
    ts = str(ts).strip()
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    try:
        dt = parsedate_to_datetime(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def load_selection(path: Path):
    sel = json.loads(path.read_text(encoding="utf-8"))
    chapter_threads = sel.get("chapter_threads", [])
    compendium_tweets = sel.get("compendium_tweets", [])
    if not isinstance(chapter_threads, list):
        raise SystemExit("selection_final_clean.json: expected key 'chapter_threads' to be a list")
    if not isinstance(compendium_tweets, list):
        compendium_tweets = []
    return [str(x) for x in chapter_threads], [str(x) for x in compendium_tweets]


def load_threads(path: Path):
    threads_by_id = {}
    for obj in iter_jsonl(path):
        tid = obj.get("thread_id")
        if not tid:
            continue
        threads_by_id[str(tid)] = obj
    return threads_by_id


def load_tweets_raw(path: Path):
    tweets_by_id = {}
    for obj in iter_jsonl(path):
        tid = obj.get("id_str")
        if tid:
            tweets_by_id[str(tid)] = obj
    return tweets_by_id


def load_chapter_title_overrides():
    if not CHAPTER_TITLES_PATH.exists():
        raise SystemExit(f"Missing {CHAPTER_TITLES_PATH}")
    data = json.loads(CHAPTER_TITLES_PATH.read_text(encoding="utf-8"))
    chapters = data.get("chapters")
    if not isinstance(chapters, list):
        raise SystemExit("chapter_titles.json: expected top-level key 'chapters' to be a list")
    overrides = {}
    for c in chapters:
        tid = c.get("thread_id")
        if not tid:
            continue
        title = (c.get("override_title") or "").strip()
        if title:
            overrides[str(tid)] = title
    return overrides


def media_items(raw: dict):
    ee = (raw or {}).get("extended_entities") or {}
    if ee.get("media"):
        return ee["media"]
    en = (raw or {}).get("entities") or {}
    return en.get("media") or []


def find_local_media_by_basename(media_dir: Path, basename: str):
    if not basename:
        return None
    hits = sorted(media_dir.glob(f"*-{basename}"))
    return hits[0].name if hits else None


def render_media_html(raw: dict, media_dir: Path):
    media = media_items(raw)
    if not media:
        return ""
    parts = ['<div class="tweet-media">']
    for m in media:
        mtype = m.get("type") or "media"
        url = m.get("media_url_https") or m.get("media_url") or ""
        basename = url.split("/")[-1] if url else ""
        local_name = find_local_media_by_basename(media_dir, basename)

        if local_name:
            src = f"../assets/media/{escape(local_name)}"
            if mtype == "photo":
                parts.append(f'<img class="tweet-photo" src="{src}" alt="tweet photo">')
            elif mtype in ("video", "animated_gif"):
                if local_name.lower().endswith(".mp4"):
                    parts.append(f'<video class="tweet-video" controls preload="metadata" src="{src}"></video>')
                else:
                    parts.append(f'<a href="{src}" target="_blank" rel="noreferrer">[{escape(mtype)}]</a>')
            else:
                parts.append(f'<a href="{src}" target="_blank" rel="noreferrer">[media]</a>')
        else:
            if url:
                parts.append(f'<a href="{escape(url)}" target="_blank" rel="noreferrer">[{escape(mtype)}]</a>')
    parts.append("</div>")
    return "\n".join(parts)


def quoted_id(raw: dict):
    q = (raw or {}).get("quoted_status_id_str") or (raw or {}).get("quoted_status_id")
    if q:
        return str(q)
    qs = (raw or {}).get("quoted_status")
    if isinstance(qs, dict):
        q2 = qs.get("id_str") or qs.get("id")
        if q2:
            return str(q2)
    return None


def self_linked_status_ids(raw: dict, tweets_by_id: dict):
    out = []
    entities = (raw or {}).get("entities") or {}
    urls = entities.get("urls") or []
    for u in urls:
        expanded = u.get("expanded_url") or u.get("url") or ""
        m = STATUS_URL_RE.search(expanded)
        if not m:
            continue
        sid = m.group(1)
        if sid in tweets_by_id:
            out.append(sid)
    seen = set()
    uniq = []
    for sid in out:
        if sid not in seen:
            seen.add(sid)
            uniq.append(sid)
    return uniq


def render_quote_box_for_id(qid: str, tweets_by_id: dict, media_dir: Path):
    qt = tweets_by_id.get(qid)
    if not qt:
        return ""
    qraw = qt.get("raw") or {}
    qtext = (qt.get("full_text") or qraw.get("full_text") or "").strip()
    qdt = parse_created_at_any(qt.get("created_at") or qraw.get("created_at") or "")
    qdate = qdt.isoformat() if qdt else ""
    parts = [
        '<div class="quote-box">',
        f'<div class="quote-meta">{escape(qdate)}</div>',
        f'<div class="quote-text">{escape(qtext)}</div>',
    ]
    media_html = render_media_html(qraw, media_dir)
    if media_html:
        parts.append(media_html)
    parts.append("</div>")
    return "\n".join(parts)


def render_quote_boxes(raw: dict, tweets_by_id: dict, media_dir: Path):
    boxes = []
    qid = quoted_id(raw)
    if qid and qid in tweets_by_id:
        boxes.append(render_quote_box_for_id(qid, tweets_by_id, media_dir))
    for sid in self_linked_status_ids(raw, tweets_by_id):
        if sid == qid:
            continue
        boxes.append(render_quote_box_for_id(sid, tweets_by_id, media_dir))
    return "\n".join([b for b in boxes if b])


# def auto_link_text(text: str, raw: dict):
#     if not text:
#         return ""
#     entities = (raw or {}).get("entities") or {}
#     urls = entities.get("urls") or []
#
#     for u in urls:
#         short = u.get("url")
#         if short:
#             text = text.replace(short, f"@@URL@@{short}@@END@@")
#
#     esc_text = escape(text, quote=False)
#
#     for u in urls:
#         short = u.get("url")
#         expanded = u.get("expanded_url") or short or ""
#         display = u.get("display_url") or expanded
#         if short and expanded:
#             placeholder = escape(f"@@URL@@{short}@@END@@", quote=False)
#             link_html = f'<a href="{escape(expanded)}">{escape(display)}</a>'
#             esc_text = esc_text.replace(placeholder, link_html)
#
#     return esc_text.replace("\n", "<br>\n")


def clear_old_chapters():
    CHAPTERS_DIR.mkdir(parents=True, exist_ok=True)
    removed = 0
    for p in CHAPTERS_DIR.glob("*.html"):
        p.unlink()
        removed += 1
    print("Cleared old chapter HTML files" if removed else "No old chapter HTML files to clear")


def write_front_matter_pages(book_title: str, author: str, cover_image_rel: str):
    CHAPTERS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    cover_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{escape(book_title)} - Cover</title>
  <link rel="stylesheet" href="../style.css">
</head>
<body>
  <div class="chapter frontmatter cover-page">
    <div class="cover-wrap">
      <img class="cover-image" src="../{escape(cover_image_rel)}" alt="Cover image">
      <div class="cover-caption">(Replace this cover image later)</div>
    </div>
    <div class="nav"><a href="../index.html">Back to index</a></div>
  </div>
</body>
</html>
'''

    title_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{escape(book_title)} - Title</title>
  <link rel="stylesheet" href="../style.css">
</head>
<body>
  <div class="chapter frontmatter title-page">
    <h1>{escape(book_title)}</h1>
    <p class="byline">{escape(author)}</p>
    <div class="nav"><a href="../index.html">Back to index</a></div>
  </div>
</body>
</html>
'''

    preface_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{escape(book_title)} - Preface</title>
  <link rel="stylesheet" href="../style.css">
</head>
<body>
  <div class="chapter frontmatter preface-page">
    <h1>Preface</h1>
    <p>
      Lorem ipsum dolor sit amet, consectetur adipiscing elit. This is a placeholder preface.
      Replace this content later.
    </p>
    <div class="nav"><a href="../index.html">Back to index</a></div>
  </div>
</body>
</html>
'''

    (CHAPTERS_DIR / "cover.html").write_text(cover_html, encoding="utf-8")
    (CHAPTERS_DIR / "title.html").write_text(title_html, encoding="utf-8")
    (CHAPTERS_DIR / "preface.html").write_text(preface_html, encoding="utf-8")


def generate_thread_chapter(thread: dict, thread_id: str, display_title: str, tweets_by_id: dict, media_dir: Path):
    tweets = thread.get("tweets") or []
    if not tweets:
        return None

    parts = []
    for tw in tweets:
        tid = str(tw.get("id_str") or "")
        raw = (tweets_by_id.get(tid) or {}).get("raw") or tw.get("raw") or {}
        text = (tw.get("full_text") or "").strip()

        dt = parse_created_at_any(tw.get("created_at") or raw.get("created_at") or "")
        dt_s = dt.isoformat() if dt else ""

        block = [
            f'<div class="tweet" data-tweet-id="{escape(tid)}">',
            f'  <div class="tweet-text">{render_tweet_text_html(text, raw, link_label="link")}</div>',
        ]
        media_html = render_media_html(raw, media_dir)
        if media_html:
            block.append(media_html)
        quote_html = render_quote_boxes(raw, tweets_by_id, media_dir)
        if quote_html:
            block.append(quote_html)
        block.append(f'  <div class="tweet-meta">{escape(dt_s)}</div>')
        block.append("</div>")
        parts.append("\n".join(block))

    body = "\n\n".join(parts)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{escape(display_title)}</title>
  <link rel="stylesheet" href="../style.css">
</head>
<body>
  <div class="chapter">
    <h1>{escape(display_title)}</h1>
{body}
    <div class="nav"><a href="../index.html">Back to index</a></div>
  </div>
</body>
</html>
'''
    filename = f"chapter_{thread_id}.html"
    (CHAPTERS_DIR / filename).write_text(html, encoding="utf-8")
    return filename


def generate_index(items):
    li = []
    for it in items:
        meta_html = f'<div class="chapter-meta">{escape(it["meta"])}</div>' if it.get("meta") else ""
        li.append(f'<li><a href="{escape(it["href"])}">{escape(it["title"])}</a>{meta_html}</li>')
    items_html = "\n".join(li)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Index</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <h1>Index</h1>
  <ul class="chapter-list">
{items_html}
  </ul>
</body>
</html>
'''
    INDEX_PATH.write_text(html, encoding="utf-8")


def maybe_run_cleanup_stub(run_cleanup: bool):
    script = DATA_DIR / "cleanup_tweet_content.py"
    if not run_cleanup:
        print("Cleanup stub: skipped (use --run-cleanup to invoke later).")
        return
    if not script.exists():
        print(f"Cleanup stub: {script} does not exist yet. (We'll add it later.)")
        return
    print(f"Cleanup stub: running {script} ...")
    subprocess.run(["python3", str(script)], check=True)


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--run-cleanup", action="store_true", help="Invoke cleanup_tweet_content.py if present (stub).")
    ap.add_argument("--book-title", default="Twitter Archive Book (Dev)")
    ap.add_argument("--author", default="(Author)")
    ap.add_argument("--cover-image", default="assets/cover.png", help="Path relative to book/ (placeholder)")
    args = ap.parse_args()

    BOOK_DIR.mkdir(parents=True, exist_ok=True)
    CHAPTERS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    clear_old_chapters()

    maybe_run_cleanup_stub(args.run_cleanup)

    print(f"Loading selection from {SELECTION} ...")
    chapter_thread_ids, compendium_tweets = load_selection(SELECTION)
    print(f"Selected chapter threads: {len(chapter_thread_ids)}")
    print(f"Selected compendium tweets (unused here): {len(compendium_tweets)}")

    print(f"Loading threads from {THREADS_DATA} ...")
    threads_by_id = load_threads(THREADS_DATA)

    print(f"Loading tweets (with raw) from {TWEETS_DATA} ...")
    tweets_raw = load_tweets_raw(TWEETS_DATA)

    chapter_title_overrides = load_chapter_title_overrides()

    # Front matter placeholder pages
    write_front_matter_pages(args.book_title, args.author, args.cover_image)

    index_items = []
    index_items.append({"href": "chapters/cover.html", "title": "Cover", "meta": ""})
    index_items.append({"href": "chapters/title.html", "title": "Title page", "meta": ""})
    index_items.append({"href": "chapters/preface.html", "title": "Preface", "meta": ""})

    # Compendium is generated separately; include link regardless (stable nav)
    index_items.append({"href": "chapters/compendium.html", "title": "Compendium", "meta": ""})

    missing = []
    for thread_id in chapter_thread_ids:
        thread = threads_by_id.get(thread_id)
        if not thread:
            missing.append(thread_id)
            continue

        display_title = chapter_title_overrides.get(str(thread_id), "").strip()
        if not display_title:
            raise SystemExit(
                f"Missing override_title for thread_id {thread_id} in {CHAPTER_TITLES_PATH}. "
                "You said titles are fully updated; please add it."
            )

        chapter_filename = generate_thread_chapter(thread, str(thread_id), display_title, tweets_raw, ASSETS_MEDIA_DIR)
        if chapter_filename:
            index_items.append({
                "href": f"chapters/{chapter_filename}",
                "title": display_title,
                "meta": f"thread {thread_id}"
            })

    if missing:
        print(f"Warning: {len(missing)} selected thread_ids not found in {THREADS_DATA.name}")

    generate_index(index_items)
    print(f"Wrote index: {INDEX_PATH}")


if __name__ == "__main__":
    main()
