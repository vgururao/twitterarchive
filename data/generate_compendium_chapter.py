#!/usr/bin/env python3
"""
Generate a chronological Compendium chapter from a tagged singleton-tweets JSON export.

INPUTS (defaults assume repo layout from README):
- data/compendium_tagged_updated.json  (from compendium_selector.html export)
- data/tweets_normalized.jsonl         (normalized tweets with 'raw' payload, for links/media/quotes)

OUTPUTS:
- book/chapters/compendium.html
- (optional) book/style.css appended with a small COMPENDIUM block (idempotent)
- (optional) book/index.html patched to include a Compendium link (idempotent)

Notes:
- Discards tweets with discard=true.
- Renames tag "hot_take" -> "take" in output (does not rewrite the JSON).
- Uses tweets_normalized.jsonl when available for canonical text/raw/entities/media.
"""

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import escape, unescape
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

DATA_DIR = ROOT / "data"
BOOK_DIR = ROOT / "book"
CHAPTERS_DIR = BOOK_DIR / "chapters"
ASSETS_MEDIA_DIR = BOOK_DIR / "assets" / "media"
STYLE_PATH = BOOK_DIR / "style.css"
INDEX_PATH = BOOK_DIR / "index.html"

STATUS_URL_RE = re.compile(r"https?://(?:x|twitter)\.com/[^/]+/status/(\d+)")



def nav_bar(prev_href: str = "preface.html", prev_title: str = "Preface",
            next_href: str = "", next_title: str = "",
            toc_href: str = "../toc.html") -> str:
    left = f'<a class="nav-link nav-prev" href="{escape(prev_href)}">⬅️ {escape(prev_title)}</a>' if prev_href else '<span class="nav-link nav-prev disabled">⬅️</span>'
    center = f'<a class="nav-link nav-toc" href="{escape(toc_href)}">⬆️ ToC</a>'
    right = f'<a class="nav-link nav-next" href="{escape(next_href)}">{escape(next_title)} ➡️</a>' if next_href else '<span class="nav-link nav-next disabled">➡️</span>'
    return (
        '<nav class="book-nav">'
        f'<div class="nav-left">{left}</div>'
        f'<div class="nav-center">{center}</div>'
        f'<div class="nav-right">{right}</div>'
        '</nav>'
    )

def iter_jsonl(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def load_tweets_raw(tweets_jsonl: Path) -> dict:
    """Map tweet id_str -> normalized record (with 'raw')."""
    tweets_by_id = {}
    for obj in iter_jsonl(tweets_jsonl):
        tid = obj.get("id_str")
        if tid:
            tweets_by_id[tid] = obj
    return tweets_by_id


def parse_created_at_any(ts: str):
    """
    Handles both:
    - ISO 8601 timestamps (from normalized pipeline)
    - Twitter export format: 'Sat Sep 01 22:53:29 +0000 2018'
    Returns timezone-aware datetime if possible; otherwise None.
    """
    if not ts:
        return None
    ts = ts.strip()
    # ISO-ish
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    # Twitter export format
    try:
        dt = parsedate_to_datetime(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def media_items(raw: dict):
    ee = (raw or {}).get("extended_entities") or {}
    if ee.get("media"):
        return ee["media"]
    en = (raw or {}).get("entities") or {}
    return en.get("media") or []


def find_local_media_by_basename(basename: str):
    if not basename:
        return None
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
    """Extract status IDs referenced in URLs that resolve to tweets in your archive."""
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
        f'<div class="quote-meta">{escape(str(qdate))} · ❤️ {qlikes} · 🔁 {qrt} · id {escape(qid)}</div>',
        f'<div class="quote-text">{escape(unescape(qtext))}</div>',
    ]
    media_html = render_media_html(qraw)
    if media_html:
        parts.append(media_html)
    parts.append("</div>")
    return "\n".join(parts)


def render_quote_boxes(raw: dict, tweets_by_id: dict):
    boxes = []
    qid = quoted_id(raw)
    if qid and qid in tweets_by_id:
        boxes.append(render_quote_box_for_id(qid, tweets_by_id))
    for sid in self_linked_status_ids(raw, tweets_by_id):
        if sid == qid:
            continue
        boxes.append(render_quote_box_for_id(sid, tweets_by_id))
    return "\n".join([b for b in boxes if b])


def auto_link_text(text: str, raw: dict, url_titles: dict = None, url_overrides: dict = None):
    """
    Replace t.co URLs with <a href="expanded_url">title or display_url</a>.
    Applies URL overrides for hijacked/broken links.
    Preserve line breaks. No markdown, just simple HTML.
    """
    if not text:
        return ""
    if url_titles is None:
        url_titles = {}
    if url_overrides is None:
        url_overrides = {}
    text_html = unescape(text)

    entities = (raw or {}).get("entities") or {}
    urls = entities.get("urls") or []
    for u in urls:
        short = u.get("url")
        expanded = u.get("expanded_url") or short
        display = u.get("display_url") or expanded
        # Apply override if present
        override = url_overrides.get(expanded)
        if override:
            href = override.get("replacement_url", expanded)
            anchor = override.get("title", display)
        else:
            href = expanded
            entry = url_titles.get(expanded)
            if entry and entry.get("status") == "ok" and entry.get("title"):
                anchor = entry["title"]
            else:
                anchor = display
        if short:
            short_esc = escape(short)
            link_html = f'<a href="{escape(href)}">{escape(anchor)}</a>'
            text_html = text_html.replace(short, short_esc)
            text_html = text_html.replace(short_esc, link_html)

    text_html = escape(text_html, quote=False)
    text_html = text_html.replace("\n", "<br>\n")
    return text_html


def normalize_tags(tags):
    out = []
    for t in (tags or []):
        t = (t or "").strip()
        if not t:
            continue
        if t == "hot_take":
            t = "take"
        out.append(t)
    # stable + unique
    seen = set()
    uniq = []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def render_tag_badges(tags):
    if not tags:
        return ""
    badges = " ".join([f'<span class="tag-badge tag-{escape(t)}">{escape(t)}</span>' for t in tags])
    return f'<div class="tweet-tags">{badges}</div>'


def ensure_compendium_css():
    if not STYLE_PATH.exists():
        return
    css = STYLE_PATH.read_text(encoding="utf-8")
    if "/* COMPENDIUM */" in css:
        return
    block = r"""

/* COMPENDIUM */
.compendium-intro { margin-top: 0.25rem; color: #444; }
.compendium-stats {
  margin: 1rem 0 1.25rem 0;
  padding: 0.75rem 1rem;
  border: 1px solid #eee;
  background: #fafafa;
  border-radius: 6px;
  font-size: 0.9rem;
}
.year-divider {
  margin: 1.25rem 0 0.5rem 0;
  font-size: 1.15rem;
  border-bottom: 1px solid #eee;
  padding-bottom: 0.25rem;
  color: #333;
}
.tweet-tags { margin-top: 0.35rem; }
.tag-badge {
  display: inline-block;
  border: 1px solid #ddd;
  background: #f3f3f3;
  border-radius: 999px;
  padding: 0.05rem 0.5rem;
  margin-right: 0.35rem;
  font-size: 0.75rem;
  color: #444;
}
.tweet.featured {
  border-left: 4px solid #222;
  padding-left: 0.75rem;
}
.tweet-text-ascii pre {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.9rem;
  margin: 0.25rem 0 0 0;
}
"""
    STYLE_PATH.write_text(css.rstrip() + "\n" + block.lstrip(), encoding="utf-8")


def patch_index_with_compendium_link(compendium_filename: str, kept_count: int, year_min: int, year_max: int):
    if not INDEX_PATH.exists():
        return
    html = INDEX_PATH.read_text(encoding="utf-8")

    marker = 'data-kind="compendium-link"'
    if marker in html:
        return

    li = (
        f'<li {marker}>\n'
        f'  <a href="chapters/{escape(compendium_filename)}">Compendium</a>\n'
        f'  <div class="chapter-meta">{year_min}–{year_max} · {kept_count} tweets</div>\n'
        f'</li>\n'
    )

    ul_tag = '<ul class="chapter-list">'
    if ul_tag in html:
        html = html.replace(ul_tag, ul_tag + "\n" + li, 1)
    else:
        # fallback: prepend to body
        html = html.replace("<body>", "<body>\n" + li, 1)

    INDEX_PATH.write_text(html, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tagged", default=str(DATA_DIR / "compendium_tagged_with_prehistory.json"),
                    help="Tagged compendium JSON (export from compendium_selector.html)")
    ap.add_argument("--tweets", default=str(DATA_DIR / "tweets_normalized.jsonl"),
                    help="Normalized tweets JSONL (must include raw payload)")
    ap.add_argument("--out", default=str(CHAPTERS_DIR / "compendium.html"),
                    help="Output chapter HTML path")
    ap.add_argument("--patch-index", action="store_true", help="Patch book/index.html to link compendium")
    ap.add_argument("--patch-css", action="store_true", help="Append minimal compendium CSS to book/style.css (idempotent)")
    args = ap.parse_args()

    tagged_path = Path(args.tagged)
    tweets_path = Path(args.tweets)
    out_path = Path(args.out)

    if not tagged_path.exists():
        raise SystemExit(f"Missing tagged file: {tagged_path}")
    if not tweets_path.exists():
        raise SystemExit(f"Missing tweets file: {tweets_path}")

    BOOK_DIR.mkdir(parents=True, exist_ok=True)
    CHAPTERS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    data = json.loads(tagged_path.read_text(encoding="utf-8"))
    tagged = data.get("tweets") or []
    tweets_by_id = load_tweets_raw(tweets_path)

    # Load URL title map and overrides
    from tweet_text_cleanup import load_url_titles, load_url_overrides
    url_titles = load_url_titles()
    url_overrides = load_url_overrides()

    # Enrich + filter
    rows = []
    for t in tagged:
        if t.get("discard") is True:
            continue
        tid = str(t.get("id_str") or "").strip()
        if not tid:
            continue

        norm = tweets_by_id.get(tid) or {}
        raw = norm.get("raw") or {}

        created_at = norm.get("created_at") or t.get("created_at") or raw.get("created_at") or ""
        dt = parse_created_at_any(created_at) or parse_created_at_any(t.get("created_at") or "")

        fav = norm.get("favorite_count") or raw.get("favorite_count") or t.get("favorite_count") or 0
        rt = norm.get("retweet_count") or raw.get("retweet_count") or t.get("retweet_count") or 0

        text = (norm.get("full_text") or raw.get("full_text") or t.get("text") or "").strip()
        tags = normalize_tags(t.get("tags"))
        featured = bool(t.get("featured"))

        rows.append({
            "id_str": tid,
            "dt": dt,
            "created_at": created_at,
            "favorite_count": int(fav) if str(fav).isdigit() else fav,
            "retweet_count": int(rt) if str(rt).isdigit() else rt,
            "text": text,
            "raw": raw,
            "tags": tags,
            "featured": featured,
        })

    # Strict chronological order
    rows.sort(key=lambda r: (r["dt"] or datetime.min.replace(tzinfo=timezone.utc), r["id_str"]))

    # Stats
    kept_count = len(rows)
    featured_count = sum(1 for r in rows if r["featured"])
    tag_counts = Counter()
    by_year = defaultdict(int)
    years = []
    for r in rows:
        for tg in (r["tags"] or ["unclassified"]):
            tag_counts[tg] += 1
        if r["dt"]:
            years.append(r["dt"].year)
            by_year[r["dt"].year] += 1

    year_min = min(years) if years else 0
    year_max = max(years) if years else 0

    # Render tweet blocks, with year dividers
    parts = []
    current_year = None
    for r in rows:
        dt = r["dt"]
        year = dt.year if dt else None
        if year and year != current_year:
            current_year = year
            parts.append(f'<h2 class="year-divider">{year}</h2>')

        raw = r["raw"]
        text = r["text"]
        tags = r["tags"]
        is_ascii = "ascii" in set(tags)
        classes = ["tweet", "compendium-tweet"]
        if r["featured"]:
            classes.append("featured")
        for tg in tags:
            classes.append(f"tag-{re.sub(r'[^a-zA-Z0-9_-]+', '', tg)}")

        # Format date as "Jan 1, 2018"
        if dt:
            date_str = dt.strftime("%b %-d, %Y")
        else:
            date_str = ""

        tweet_id = escape(r["id_str"])
        tweet_html = []
        tweet_html.append(f'<div class="{" ".join(classes)}" data-tweet-id="{tweet_id}" id="t{tweet_id}">')
        tweet_html.append(f'<a class="tweet-permalink" href="#t{tweet_id}" title="Copy link to this tweet" onclick="return copyTweetLink(this, \'t{tweet_id}\')">&#x1F517;</a>')
        tweet_html.append(f'<div class="tweet-date">{escape(date_str)}</div>')

        if is_ascii:
            tweet_html.append(f'<div class="tweet-text tweet-text-ascii"><pre>{escape(text)}</pre></div>')
        else:
            tweet_html.append(f'<div class="tweet-text">{auto_link_text(text, raw, url_titles, url_overrides)}</div>')

        media_html = render_media_html(raw)
        if media_html:
            tweet_html.append(media_html)

        quote_html = render_quote_boxes(raw, tweets_by_id)
        if quote_html:
            tweet_html.append(quote_html)

        tags_html = render_tag_badges(tags)
        if tags_html:
            tweet_html.append(tags_html)

        tweet_html.append("</div>")
        parts.append("\n".join(tweet_html))

    # Build stats HTML (deterministic ordering)
    tag_badges_stats = []
    for tag, cnt in sorted(tag_counts.items(), key=lambda x: (-x[1], x[0])):
        tag_badges_stats.append(
            f'<span class="tag-badge tag-{escape(tag)}">{escape(tag)}: {cnt}</span>'
        )
    tag_summary_html = " ".join(tag_badges_stats)

    year_lines = []
    for y in sorted(by_year.keys()):
        year_lines.append(f"{y}: {by_year[y]}")
    year_summary = " · ".join(year_lines)

    intro_paras = [
        "While most of this book is threads, this opening chapter contains a curated selection of "
        "stand-alone tweets that were either exceptionally popular (as measured by likes and retweets), "
        "personal favorites, or both. There are 396 tweets included, out of over 150k, or approximately "
        "0.26%. I have also included my 10 earliest tweets, from 2007, even though there is nothing "
        "notable about them, to convey a sense of the early calm before the later storms. "
        "Of these 396, I have also highlighted 38 \u2014 0.026% \u2014 as particularly noteworthy. "
        "In most cases, these are not just notable tweets, but ones with stories of some sort attached, "
        "like interesting conversations ensuing, or the tweet marking an evolution in my philosophy. I "
        "also classified and tagged these 396 tweets by category, primarily to try and fingerprint my "
        "overall evolving vibe over the years. You can see summary statistics at the end of this chapter.",

        "In many ways, for tweet-sized thinking and writing, singles are to threads what short stories "
        "are to novels in long form. Many of my favorite writers, such as J. G. Ballard and Jorge Luis "
        "Borges, were not only at their best with short stories, but revealed their thought processes the "
        "most with shorter forms. Many twitter users I appreciated were masters of the one-off single. I "
        "am not sure where I land, but I suspect browsing my most noteworthy single tweets is the best "
        "way to get a sense of the gestalt of this book.",

        "While I\u2019m proud of many of my threads, my most <em>memorable</em> tweets, which I can quote "
        "from memory, were singles, and I think I\u2019ve captured most of them in this chapter. If you "
        "weren\u2019t following me live during my active twitter years, browsing this chapter is probably "
        "the best way to get a highlights-reel sense of my thinking through those years. Even more than "
        "my long-form blogs, twitter was where I workshopped my thinking.",
    ]
    intro_html = "\n".join([f"<p>{p}</p>" for p in intro_paras])

    nav_top = nav_bar()
    nav_bottom = nav_top
    _NL2 = "\n\n"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>vgr: The Twitter Years (2007&#x2013;22) | 1. Singles</title>
  <meta property="og:title" content="vgr: The Twitter Years (2007&#x2013;22) | 1. Singles">
  <meta property="og:description" content="A curated collection of tweets and threads by Venkatesh Rao (@vgr), 2007&#x2013;22.">
  <meta property="og:image" content="https://venkateshrao.com/twitter-book/assets/cover.png">
  <meta property="og:type" content="book">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="vgr: The Twitter Years (2007&#x2013;22) | 1. Singles">
  <meta name="twitter:description" content="A curated collection of tweets and threads by Venkatesh Rao (@vgr), 2007&#x2013;22.">
  <meta name="twitter:image" content="https://venkateshrao.com/twitter-book/assets/cover.png">
  <link rel="stylesheet" href="../style.css">
  <link rel="stylesheet" href="../compendium.css">
  <link rel="stylesheet" href="../mobile.css">
</head>
<body>
  <div class="page">
    <div class="page-content">
      <div class="chapter">
        <header>
          <h1 class="chapter-title">Singles <a class="chapter-permalink" href="#" title="Copy link to this page" onclick="return copyPageLink(this)">&#x1F517;</a></h1>
          <div class="compendium-intro">{intro_html}</div>
        </header>

        {_NL2.join(parts)}

        <div class="compendium-stats">
          <h3 class="stats-title">Chapter Statistics</h3>
          <div class="stats-row"><span class="stats-label">Range</span> {year_min}–{year_max}</div>
          <div class="stats-row"><span class="stats-label">Tweets</span> {kept_count} included · {featured_count} featured</div>
          <div class="stats-row"><span class="stats-label">By tag</span> {tag_summary_html}</div>
          <div class="stats-row"><span class="stats-label">By year</span> {year_summary}</div>
        </div>

      </div>
    </div>
  </div>
<script>
function copyPageLink(el) {{
  navigator.clipboard.writeText(window.location.origin + window.location.pathname).then(function() {{
    var tip = document.createElement('span');
    tip.className = 'copy-tooltip';
    tip.textContent = 'Link copied!';
    el.appendChild(tip);
    setTimeout(function() {{ tip.remove(); }}, 1800);
  }});
  return false;
}}
function copyTweetLink(el, id) {{
  var tweet = document.getElementById(id);
  if (!tweet) return false;
  // Build full permalink URL
  var url = window.location.origin + window.location.pathname + '#' + id;
  // Copy to clipboard
  navigator.clipboard.writeText(url).then(function() {{
    // Show tooltip
    var tip = document.createElement('span');
    tip.className = 'copy-tooltip';
    tip.textContent = 'Link copied!';
    el.appendChild(tip);
    setTimeout(function() {{ tip.remove(); }}, 1800);
  }});
  // Scroll tweet near top (offset by ~100px for "second tweet" position)
  var y = tweet.getBoundingClientRect().top + window.pageYOffset - 100;
  window.scrollTo({{ top: y, behavior: 'smooth' }});
  // Clear any previous highlight, then highlight this tweet
  var prev = document.querySelector('.permalink-highlight');
  if (prev) prev.classList.remove('permalink-highlight');
  tweet.classList.add('permalink-highlight');
  // Update URL hash without jumping
  history.replaceState(null, '', '#' + id);
  return false;
}}
// On page load, highlight tweet if hash is present
(function() {{
  if (window.location.hash) {{
    var id = window.location.hash.substring(1);
    var tweet = document.getElementById(id);
    if (tweet) {{
      setTimeout(function() {{
        var y = tweet.getBoundingClientRect().top + window.pageYOffset - 100;
        window.scrollTo({{ top: y, behavior: 'smooth' }});
        tweet.classList.add('permalink-highlight');
      }}, 300);
    }}
  }}
}})();
</script>
</body>
</html>
"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote compendium chapter: {out_path}")

    if args.patch_css:
        ensure_compendium_css()
        print(f"Patched CSS (if needed): {STYLE_PATH}")

    if args.patch_index:
        patch_index_with_compendium_link(out_path.name, kept_count, year_min, year_max)
        print(f"Patched index (if needed): {INDEX_PATH}")


if __name__ == "__main__":
    main()
