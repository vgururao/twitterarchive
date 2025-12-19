#!/usr/bin/env python3
"""
Generate a chronological Compendium chapter from a tagged singleton-tweets JSON export.

Inputs (defaults assume repo layout):
- data/compendium_tagged_updated.json  (export from compendium_selector.html)
- data/tweets_normalized.jsonl         (normalized tweets with 'raw' payload)

Outputs:
- book/chapters/compendium.html
- (optional) book/compendium.css       (created/updated idempotently with --patch-css)
- (optional) book/index.html           (patched idempotently with --patch-index)

Behavior:
- Discards tweets with discard=true.
- Renames tag "hot_take" -> "take" in rendered output (does not rewrite JSON).
- Strict chronological order with year dividers.
- Tweet meta is a single footer row (date + id). Date rendered like "Nov 22, 2022".
- Likes/RT counts are suppressed, but a subtle star appears top-right when (likes + RTs) > 100.
- Featured tweets are marked with .featured class (styling handled in compendium.css).
- ASCII-tagged tweets are rendered inside <pre>.

Notes:
- Media embedding looks for local copies in book/assets/media/ as "*-<basename>".
- Quote boxes are rendered for quoted tweets and self-linked status URLs that resolve to your archive.
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import escape
from pathlib import Path

STATUS_URL_RE = re.compile(r"https?://(?:x|twitter)\.com/[^/]+/status/(\d+)")


def iter_jsonl(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
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
    Handles:
    - ISO 8601 (possibly with Z)
    - Twitter export-style date strings
    Returns tz-aware datetime or None.
    """
    if not ts:
        return None
    ts = ts.strip()
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


def format_date(dt):
    if not dt:
        return ""
    s = dt.strftime("%b %d, %Y")
    return s.replace(" 0", " ")


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
    qdate = format_date(qdt)

    parts = [
        '<div class="quote-box">',
        f'<div class="quote-meta">{escape(qdate)} · id {escape(qid)}</div>',
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


def auto_link_text(text: str, raw: dict):
    if not text:
        return ""
    entities = (raw or {}).get("entities") or {}
    urls = entities.get("urls") or []

    # placeholder substitution to avoid escaping issues
    for u in urls:
        short = u.get("url")
        if short:
            text = text.replace(short, f"@@URL@@{short}@@END@@")

    esc = escape(text, quote=False)

    for u in urls:
        short = u.get("url")
        expanded = u.get("expanded_url") or short or ""
        display = u.get("display_url") or expanded
        if short and expanded:
            placeholder = escape(f"@@URL@@{short}@@END@@", quote=False)
            link_html = f'<a href="{escape(expanded)}">{escape(display)}</a>'
            esc = esc.replace(placeholder, link_html)

    return esc.replace("\n", "<br>\n")


def normalize_tags(tags):
    out = []
    for t in (tags or []):
        t = (t or "").strip()
        if not t:
            continue
        if t == "hot_take":
            t = "take"
        out.append(t)
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
    badges = " ".join([f'<span class="tag-badge">{escape(t)}</span>' for t in tags])
    return f'<div class="tweet-tags">{badges}</div>'


def ensure_compendium_css(comp_css_path: Path):
    if comp_css_path.exists():
        existing = comp_css_path.read_text(encoding="utf-8")
        if "/* === COMPENDIUM === */" in existing:
            return

    css = """/* === COMPENDIUM === */

.compendium-page .tweet {
  position: relative;
  padding: 0.9rem 0;
}

/* Content-first layout */
.tweet-content {
  font-size: 0.95rem;
  line-height: 1.45;
}

/* Footer meta row */
.tweet-meta-footer {
  margin-top: 0.4rem;
  font-size: 0.75rem;
  color: #777;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* Tag styling */
.tweet-tags {
  margin-top: 0.35rem;
}

.tag-badge {
  display: inline-block;
  border: 1px solid #d5dbe3;
  background: #eef1f5;
  border-radius: 999px;
  padding: 0.05rem 0.5rem;
  margin-right: 0.35rem;
  font-size: 0.75rem;
  color: #333;
}

/* Featured = magazine callout */
.tweet.featured {
  border: 1px solid #ddd;
  background: #f9f9f7;
  padding: 0.9rem 1rem;
  border-radius: 6px;
}

.tweet.featured .tweet-content {
  font-weight: 600;
}

/* Star indicator */
.tweet-star {
  position: absolute;
  top: 0.4rem;
  right: 0.4rem;
  font-size: 0.85rem;
  color: #c8a000;
  opacity: 0.8;
}

/* ASCII tweets */
.tweet-text-ascii pre {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  background: #fafafa;
  padding: 0.5rem;
  border-radius: 4px;
  margin: 0.25rem 0 0 0;
}
"""
    comp_css_path.write_text(css, encoding="utf-8")


def patch_index_with_compendium_link(index_path: Path, compendium_filename: str, kept_count: int, year_min: int, year_max: int):
    if not index_path.exists():
        return
    html = index_path.read_text(encoding="utf-8")

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
        html = html.replace("<body>", "<body>\n" + li, 1)

    index_path.write_text(html, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tagged", default="data/compendium_tagged_updated.json")
    ap.add_argument("--tweets", default="data/tweets_normalized.jsonl")
    ap.add_argument("--out", default="book/chapters/compendium.html")
    ap.add_argument("--patch-index", action="store_true")
    ap.add_argument("--patch-css", action="store_true")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    book_dir = root / "book"
    media_dir = book_dir / "assets" / "media"
    index_path = book_dir / "index.html"
    comp_css_path = book_dir / "compendium.css"

    tagged_path = (root / args.tagged).resolve() if not Path(args.tagged).is_absolute() else Path(args.tagged)
    tweets_path = (root / args.tweets).resolve() if not Path(args.tweets).is_absolute() else Path(args.tweets)
    out_path = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)

    if not tagged_path.exists():
        raise SystemExit(f"Missing tagged file: {tagged_path}")
    if not tweets_path.exists():
        raise SystemExit(f"Missing tweets file: {tweets_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    media_dir.mkdir(parents=True, exist_ok=True)

    data = json.loads(tagged_path.read_text(encoding="utf-8"))
    tagged = data.get("tweets") or []
    tweets_by_id = load_tweets_raw(tweets_path)

    rows = []
    for t in tagged:
        if t.get("kind") == "section_header":
            title = t.get("title", "")
            parts.append(f'<h2 class="year-divider">{escape(title)}</h2>')
            continue

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
        try:
            fav_i = int(fav)
        except Exception:
            fav_i = 0
        try:
            rt_i = int(rt)
        except Exception:
            rt_i = 0
        engagement = fav_i + rt_i

        text = (norm.get("full_text") or raw.get("full_text") or t.get("text") or "").strip()
        tags = normalize_tags(t.get("tags"))
        featured = bool(t.get("featured"))
        star = engagement > 100

        rows.append({
            "id_str": tid,
            "dt": dt,
            "date_short": format_date(dt),
            "text": text,
            "raw": raw,
            "tags": tags,
            "featured": featured,
            "star": star,
        })

    rows.sort(key=lambda r: (r["dt"] or datetime.min.replace(tzinfo=timezone.utc), r["id_str"]))

    # Stats
    kept_count = len(rows)
    featured_count = sum(1 for r in rows if r["featured"])
    tag_counts = Counter()
    by_year = defaultdict(int)
    years = []
    for r in rows:
        if r["dt"]:
            years.append(r["dt"].year)
            by_year[r["dt"].year] += 1
        for tg in (r["tags"] or ["unclassified"]):
            tag_counts[tg] += 1

    year_min = min(years) if years else 0
    year_max = max(years) if years else 0

    tag_lines = [f"{escape(tag)}: {cnt}" for tag, cnt in sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))]
    tag_summary = ", ".join(tag_lines)
    year_lines = [f"{y}: {by_year[y]}" for y in sorted(by_year.keys())]
    year_summary = ", ".join(year_lines)

    intro_lorem = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
        "Compendium tweets are singletons selected from the archive and tagged for theme and tone. "
        "This chapter presents them in strict chronological order with lightweight styling cues."
    )

    # Render tweets
    parts = []
    current_year = None
    for r in rows:
        year = r["dt"].year if r["dt"] else None
        if year and year != current_year:
            current_year = year
            parts.append(f'<h2 class="year-divider">{year}</h2>')

        tags = r["tags"]
        is_ascii = "ascii" in set(tags)

        classes = ["tweet", "compendium-tweet"]
        if r["featured"]:
            classes.append("featured")
        for tg in tags:
            safe = re.sub(r'[^a-zA-Z0-9_-]+', '', tg)
            if safe:
                classes.append(f"tag-{safe}")

        block = [f'<div class="{" ".join(classes)}" data-tweet-id="{escape(r["id_str"])}">']

        if r["star"]:
            block.append('<div class="tweet-star" title="High engagement">★</div>')

        if is_ascii:
            block.append(f'<div class="tweet-content tweet-text-ascii"><pre>{escape(r["text"])}</pre></div>')
        else:
            block.append(f'<div class="tweet-content">{auto_link_text(r["text"], r["raw"])}</div>')

        tags_html = render_tag_badges(tags)
        if tags_html:
            block.append(tags_html)

        media_html = render_media_html(r["raw"], media_dir)
        if media_html:
            block.append(media_html)

        quote_html = render_quote_boxes(r["raw"], tweets_by_id, media_dir)
        if quote_html:
            block.append(quote_html)

        footer_left = escape(r["date_short"])
        footer_right = f"id {escape(r['id_str'])}"
        block.append(f'<div class="tweet-meta-footer"><span>{footer_left}</span><span>{footer_right}</span></div>')

        block.append("</div>")
        parts.append("\n".join(block))

    body_html = "\n\n".join(parts)

    head_links = ['<link rel="stylesheet" href="../style.css">']
    if args.patch_css:
        ensure_compendium_css(comp_css_path)
        head_links.append('<link rel="stylesheet" href="../compendium.css">')
    elif comp_css_path.exists():
        head_links.append('<link rel="stylesheet" href="../compendium.css">')
    head_links_html = "\n  ".join(head_links)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Compendium</title>
  {head_links_html}
</head>
<body>
  <div class="chapter compendium-page">
    <header>
      <h1>Compendium</h1>
      <p class="compendium-intro">{escape(intro_lorem)}</p>
      <div class="compendium-stats">
        <div><strong>Statistics</strong></div>
        <div>Range: {year_min}–{year_max}</div>
        <div>Included tweets: {kept_count}</div>
        <div>Featured tweets: {featured_count}</div>
        <div><strong>Tag counts</strong>: {tag_summary}</div>
        <div><strong>Year counts</strong>: {year_summary}</div>
      </div>
    </header>

{body_html}

    <div class="nav">
      <a href="../index.html">Back to index</a>
    </div>
  </div>
</body>
</html>
"""

    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote compendium chapter: {out_path}")

    if args.patch_css:
        print(f"Patched compendium CSS (if needed): {comp_css_path}")

    if args.patch_index:
        patch_index_with_compendium_link(index_path, out_path.name, kept_count, year_min, year_max)
        print(f"Patched index (if needed): {index_path}")


if __name__ == "__main__":
    main()
