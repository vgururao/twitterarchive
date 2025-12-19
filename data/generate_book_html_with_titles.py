#!/usr/bin/env python3
import json
import os
import re
from datetime import datetime
from html import escape
from pathlib import Path
from html import escape

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

BOOK_DIR = ROOT / "book"
ASSETS_MEDIA_DIR = Path("book/assets/media")
ASSETS_MEDIA_DIR = ROOT / "book" / "assets" / "media"

CHAPTER_TITLES_PATH = ROOT / "data" / "chapter_titles.json"

def load_chapter_title_overrides():
    """Return dict: thread_id -> override_title."""
    if not CHAPTER_TITLES_PATH.exists():
        return {}
    try:
        data = json.loads(CHAPTER_TITLES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    chapters = data.get("chapters") if isinstance(data, dict) else None
    if not isinstance(chapters, list):
        return {}
    overrides = {}
    for c in chapters:
        tid = c.get("thread_id")
        if not tid:
            continue
        overrides[str(tid)] = c.get("override_title") or c.get("current_title") or ""
    return overrides

def media_items(raw: dict):
    ee = raw.get("extended_entities") or {}
    if ee.get("media"):
        return ee["media"]
    en = raw.get("entities") or {}
    return en.get("media") or []

def find_local_media_by_basename(basename: str):
    if not basename:
        return None
    # files are like: <prefix>-<basename>
    hits = sorted(ASSETS_MEDIA_DIR.glob(f"*-{basename}"))
    return hits[0].name if hits else None

def render_media_html(raw: dict):
    media = media_items(raw)
    if not media:
        return ""

    parts = ['<div class="tweet-media">']
    for m in media:
        mtype = m.get("type") or "media"
        url = m.get("media_url_https") or m.get("media_url") or ""
        basename = url.split("/")[-1] if url else ""
        local_name = find_local_media_by_basename(basename)

        if local_name:
            src = f"../assets/media/{escape(local_name)}"
            if mtype == "photo":
                parts.append(f'<img class="tweet-photo" src="{src}" alt="tweet photo">')
            elif mtype in ("video", "animated_gif"):
                # only works if file is mp4; if jpg, it’ll still render as a link below
                if local_name.lower().endswith(".mp4"):
                    parts.append(f'<video class="tweet-video" controls preload="metadata" src="{src}"></video>')
                else:
                    parts.append(f'<a href="{src}" target="_blank" rel="noreferrer">[{escape(mtype)}]</a>')
            else:
                parts.append(f'<a href="{src}" target="_blank" rel="noreferrer">[media]</a>')
        else:
            # fallback to remote URL link
            if url:
                parts.append(f'<a href="{escape(url)}" target="_blank" rel="noreferrer">[{escape(mtype)}]</a>')

    parts.append("</div>")
    return "\n".join(parts)



def quoted_id(raw: dict):
    q = raw.get("quoted_status_id_str") or raw.get("quoted_status_id")
    if q:
        return str(q)
    qs = raw.get("quoted_status")
    if isinstance(qs, dict):
        q2 = qs.get("id_str") or qs.get("id")
        if q2:
            return str(q2)
    return None


_STATUS_URL_RE = re.compile(r"https?://(?:x|twitter)\.com/[^/]+/status/(\d+)")


def self_linked_status_ids(raw: dict, tweets_by_id: dict):
    """Extract status IDs referenced in URLs that resolve to tweets in your archive."""
    out = []
    entities = (raw or {}).get("entities") or {}
    urls = entities.get("urls") or []
    for u in urls:
        expanded = u.get("expanded_url") or u.get("url") or ""
        m = _STATUS_URL_RE.search(expanded)
        if not m:
            continue
        sid = m.group(1)
        if sid in tweets_by_id:
            out.append(sid)
    # unique, stable order
    seen = set()
    uniq = []
    for sid in out:
        if sid not in seen:
            seen.add(sid)
            uniq.append(sid)
    return uniq


def render_quote_box_for_id(qid: str, tweets_by_id: dict):
    qt = tweets_by_id.get(qid)
    if not qt:
        return ""
    qraw = qt.get("raw") or {}
    qtext = (qt.get("full_text") or qraw.get("full_text") or "").strip()
    qdate = qt.get("created_at") or qraw.get("created_at") or ""
    qlikes = qt.get("favorite_count") or qraw.get("favorite_count") or 0
    qrt = qt.get("retweet_count") or qraw.get("retweet_count") or 0

    parts = [
        '<div class="quote-box">',
        f'<div class="quote-meta">{escape(qdate)} · ❤️ {qlikes} · 🔁 {qrt} · id {escape(qid)}</div>',
        f'<div class="quote-text">{escape(qtext)}</div>',
    ]
    media_html = render_media_html(qraw)
    if media_html:
        parts.append(media_html)
    parts.append("</div>")
    return "\n".join(parts)


def render_quote_boxes(raw: dict, tweets_by_id: dict):
    """Render embedded quote/mention boxes for tweets in your archive."""
    boxes = []
    qid = quoted_id(raw)
    if qid and qid in tweets_by_id:
        boxes.append(render_quote_box_for_id(qid, tweets_by_id))

    # Also embed self-linked status URLs (mentions) that resolve to your archive
    for sid in self_linked_status_ids(raw, tweets_by_id):
        if sid == qid:
            continue
        boxes.append(render_quote_box_for_id(sid, tweets_by_id))

    return "\n".join([b for b in boxes if b])



chapters_dir = Path(BOOK_DIR) / "chapters"
chapters_dir.mkdir(parents=True, exist_ok=True)

# remove old chapters so drops actually disappear
for p in chapters_dir.glob("*.html"):
    p.unlink()
print("Cleared old chapter HTML files")


# THREADS_DATA = "threads_data.jsonl"
# can run thread_cleanup_ui.html on local webserver to generate cleaned up patched jsonl files as below as needed
# THREADS_DATA = "threads_data_patched.jsonl"
THREADS_DATA = "threads_data_ops_patched.jsonl"
TWEETS_DATA = "tweets_normalized.jsonl"
#SELECTION = "selection_final.json"
SELECTION = "selection_final_clean.json"

BOOK_DIR = str(ROOT / "book")
CHAPTERS_DIR = os.path.join(BOOK_DIR, "chapters")
STYLE_PATH = os.path.join(BOOK_DIR, "style.css")
INDEX_PATH = os.path.join(BOOK_DIR, "index.html")


def iter_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def parse_created_at(ts):
    if ts is None:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def load_selection(path):
    with open(path, "r", encoding="utf-8") as f:
        sel = json.load(f)
    chapter_threads = set(sel.get("chapter_threads", []))
    compendium_tweets = set(sel.get("compendium_tweets", []))
    return chapter_threads, compendium_tweets


def load_threads(path):
    threads_by_id = {}
    for obj in iter_jsonl(path):
        tid = obj.get("thread_id")
        if not tid:
            continue
        threads_by_id[tid] = obj
    return threads_by_id


def load_tweets_raw(path):
    """Map tweet id -> full normalized record (with 'raw')."""
    tweets_by_id = {}
    for obj in iter_jsonl(path):
        tid = obj.get("id_str")
        if not tid:
            continue
        tweets_by_id[tid] = obj
    return tweets_by_id


def auto_link_text(text, raw):
    """
    Replace t.co URLs with <a href="expanded_url">display_url</a>.
    Preserve line breaks. No markdown, just simple HTML.
    """
    if not text:
        return ""

    text_html = text

    entities = (raw or {}).get("entities") or {}
    urls = entities.get("urls") or []

    # Replace t.co URLs in the text with expanded URLs
    for u in urls:
        short = u.get("url")
        expanded = u.get("expanded_url") or short
        display = u.get("display_url") or expanded
        if short:
            short_esc = escape(short)
            link_html = f'<a href="{escape(expanded)}">{escape(display)}</a>'
            text_html = text_html.replace(short, short_esc)  # escape short first
            # crude replacement: after escaping, replace escaped short with link
            text_html = text_html.replace(short_esc, link_html)

    # Escape everything else
    text_html = escape(text_html, quote=False)

    # Convert newlines to <br>
    text_html = text_html.replace("\n", "<br>\n")
    return text_html


def render_media(raw):
    """Render embedded media (photos/videos) when local copies exist; otherwise fall back to links."""
    return render_media_html(raw or {})



def ensure_dirs():
    os.makedirs(BOOK_DIR, exist_ok=True)
    os.makedirs(CHAPTERS_DIR, exist_ok=True)


def write_style():
    css = """
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      padding: 1rem 2rem;
      background: #f7f7f7;
      color: #222;
    }
    a { color: #0645ad; text-decoration: none; }
    a:hover { text-decoration: underline; }
    header {
      margin-bottom: 1.5rem;
    }
    .chapter-list {
      list-style: none;
      padding: 0;
    }
    .chapter-list li {
      margin-bottom: 0.5rem;
    }
    .chapter-meta {
      font-size: 0.85rem;
      color: #555;
    }
    .chapter {
      max-width: 800px;
      margin: 0 auto;
      background: #fff;
      padding: 1.5rem 2rem;
      border-radius: 6px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .tweet {
      border-bottom: 1px solid #eee;
      padding: 0.5rem 0;
    }
    .tweet:last-child {
      border-bottom: none;
    }
    .tweet-meta {
      font-size: 0.75rem;
      color: #666;
      margin-bottom: 0.2rem;
    }
    .tweet-text {
      font-size: 0.95rem;
      line-height: 1.4;
    }
    .tweet-media {
      font-size: 0.8rem;
      margin-top: 0.25rem;
    }
    .ext-flags {
      font-size: 0.75rem;
      color: #b04;
      margin-bottom: 0.5rem;
    }
    .nav {
      margin-top: 1rem;
      font-size: 0.85rem;
    }
    """
    with open(STYLE_PATH, "w", encoding="utf-8") as f:
        f.write(css.strip() + "\n")


def generate_chapter_html(chapter_idx, thread, tweets_raw):
    """
    Returns (filename, html_text) for a single chapter.
    """
    thread_id = thread.get("thread_id")
    start_created_at = thread.get("start_created_at") or ""
    num_tweets = thread.get("num_tweets", len(thread.get("tweets", [])))
    max_fav = thread.get("max_favorites", 0)
    max_rt = thread.get("max_retweets", 0)

    has_ext_dep = thread.get("has_external_dependency", False)
    has_ext_reply = thread.get("has_external_reply", False)
    has_ext_quote = thread.get("has_external_quote", False)

    ext_flags = []
    if has_ext_dep:
        ext_flags.append("external dependency")
    if has_ext_reply:
        ext_flags.append("external reply")
    if has_ext_quote:
        ext_flags.append("external quote")
    ext_flags_str = ", ".join(ext_flags)

    tweets = thread.get("tweets", [])
    # assume already sorted; if not, we can sort by created_at
    # but build_threads.py sorted them when writing.

    if tweets:
        root_text = (tweets[0].get("full_text") or "").replace("\n", " ")
    else:
        root_text = ""

    root_snippet = root_text[:140] + ("..." if len(root_text) > 140 else "")
    title = f"Thread {thread_id}"

    display_title = chapter_title_overrides.get(str(thread_id), "") or root_snippet


    filename = f"{chapter_idx:03d}_{thread_id}.html"

    # Build tweet HTML blocks
    tweet_blocks = []
    for t in tweets:
        tid = t.get("id_str")
        created_at = t.get("created_at") or ""
        fav = t.get("favorite_count", 0)
        rt = t.get("retweet_count", 0)

        raw = (tweets_raw.get(tid) or {}).get("raw") or {}
        text_html = auto_link_text(t.get("full_text") or "", raw)
        media_html = render_media(raw)

        tweet_html = []
#        tweet_html.append(f'<div class="tweet" data-tweet-id="{tweet["id_str"]}">')
        tweet_html.append(f'<div class="tweet" data-tweet-id="{t.get("id_str","")}">')
        tweet_html.append(
            f'<div class="tweet-meta">{escape(created_at)} · ❤️ {fav} · 🔁 {rt} · id {escape(tid or "")}</div>'
        )
        tweet_html.append(f'<div class="tweet-text">{text_html}</div>')
        if media_html:
            tweet_html.append(media_html)
        quote_html = render_quote_boxes(raw, tweets_raw)
        if quote_html:
            tweet_html.append(quote_html)
        tweet_html.append("</div>")
        tweet_blocks.append("\n".join(tweet_html))

    tweets_html = "\n\n".join(tweet_blocks)

    ext_html = ""
    if ext_flags_str:
        ext_html = f'<div class="ext-flags">Flags: {escape(ext_flags_str)}</div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{escape(display_title)}</title>
  <link rel="stylesheet" href="../style.css">
</head>
<body>
  <div class="chapter">
    <header>
      <h1>{escape(display_title)}</h1>
      <div class="chapter-meta">
        Thread id: {escape(thread_id or "")}<br>
        Start: {escape(start_created_at)} · Tweets: {num_tweets} · Max ❤️ {max_fav} · Max 🔁 {max_rt}
      </div>
      {ext_html}
    </header>
    {tweets_html}
    <div class="nav">
      <a href="../index.html">Back to index</a>
    </div>
  </div>
</body>
</html>
"""
    return filename, html


def write_index(chapter_infos):
    """
    chapter_infos: list of dicts with keys:
      idx, thread_id, title_snippet, start_created_at, num_tweets, max_fav, max_rt, filename
    """
    items = []
    for info in chapter_infos:
        ext_info = []
        if info.get("has_external_dependency"):
            ext_info.append("dep")
        if info.get("has_external_reply"):
            ext_info.append("reply")
        if info.get("has_external_quote"):
            ext_info.append("quote")
        ext_str = f" · flags: {', '.join(ext_info)}" if ext_info else ""

        items.append(
            f'<li>'
            f'<a href="chapters/{escape(info["filename"])}">'
            f'{escape(info["title_snippet"])}'
            f'</a>'
            f'<div class="chapter-meta">'
            f'{escape(info["start_created_at"] or "")} · '
            f'{info["num_tweets"]} tweets · '
            f'❤️ {info["max_fav"]} · 🔁 {info["max_rt"]}{ext_str}'
            f'</div>'
            f'</li>'
        )

    items_html = "\n".join(items)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Twitter Threads Book</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header>
    <h1>Twitter Threads Book</h1>
    <p>Static archive of selected threads.</p>
  </header>
  <ul class="chapter-list">
    {items_html}
  </ul>
</body>
</html>
"""
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    print(f"Loading selection from {SELECTION} ...")
    chapter_threads, compendium_tweets = load_selection(SELECTION)
    print(f"Selected chapter threads: {len(chapter_threads)}")
    print(f"Selected compendium tweets (unused for now): {len(compendium_tweets)}")

    print(f"Loading threads from {THREADS_DATA} ...")
    threads_by_id = load_threads(THREADS_DATA)
    print(f"Total threads in threads_data: {len(threads_by_id)}")

    print(f"Loading tweets (with raw) from {TWEETS_DATA} ...")
    tweets_raw = load_tweets_raw(TWEETS_DATA)
    print(f"Total tweets loaded: {len(tweets_raw)}")

    ensure_dirs()
    write_style()

    # Filter to selected threads and collect metadata
    selected_threads = []
    missing = []

    for tid in chapter_threads:
        thread = threads_by_id.get(tid)
        if not thread:
            missing.append(tid)
            continue
        selected_threads.append(thread)

    if missing:
        print(f"Warning: {len(missing)} selected thread_ids not found in threads_data")

    # Sort chapters by start_created_at (oldest first)
    def sort_key(thread):
        ts = thread.get("start_created_at")
        dt = parse_created_at(ts)
        return dt or ts or ""

    selected_threads_sorted = sorted(selected_threads, key=sort_key)

    chapter_infos = []

    print("Generating chapter HTML ...")
    for idx, thread in enumerate(selected_threads_sorted, start=1):
        fname, html = generate_chapter_html(idx, thread, tweets_raw)
        out_path = os.path.join(CHAPTERS_DIR, fname)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)

        tweets = thread.get("tweets", [])
        if tweets:
            root_text = (tweets[0].get("full_text") or "").replace("\n", " ")
        else:
            root_text = ""
        title_snippet = root_text[:140] + ("..." if len(root_text) > 140 else "")

        chapter_infos.append({
            "idx": idx,
            "thread_id": thread.get("thread_id"),
            "start_created_at": thread.get("start_created_at"),
            "num_tweets": thread.get("num_tweets", len(tweets)),
            "max_fav": thread.get("max_favorites", 0),
            "max_rt": thread.get("max_retweets", 0),
            "has_external_dependency": thread.get("has_external_dependency", False),
            "has_external_reply": thread.get("has_external_reply", False),
            "has_external_quote": thread.get("has_external_quote", False),
            "title_snippet": title_snippet,
            "filename": fname,
        })

    print(f"Wrote {len(chapter_infos)} chapter files to {CHAPTERS_DIR}")

    print("Writing index.html ...")
    write_index(chapter_infos)
    print("Done.")


if __name__ == "__main__":
    main()
