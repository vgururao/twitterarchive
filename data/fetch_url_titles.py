#!/usr/bin/env python3
"""
Fetch page titles for all URLs referenced in the selected book content.

Outputs data/url_titles.json with structure:
{
  "https://example.com/page": {
    "title": "Page Title",
    "display_url": "example.com/page...",
    "status": "ok",          # ok | broken | timeout | redirect | no_title
    "fetched_at": "2025-..."
  },
  ...
}

Usage:
  python3 data/fetch_url_titles.py              # fetch only new URLs
  python3 data/fetch_url_titles.py --retry      # also retry broken/timeout URLs
  python3 data/fetch_url_titles.py --all        # refetch everything
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
THREADS_FILE = HERE / "threads_data_ops_patched.jsonl"
TWEETS_FILE = HERE / "tweets_normalized.jsonl"
SELECTION_FILE = HERE / "selection_final_clean.json"
OUTPUT_FILE = HERE / "url_titles.json"

TIMEOUT = 10  # seconds per request
DELAY = 0.3   # seconds between requests (polite crawling)

# Regex to extract <title> from HTML
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

# User agent to avoid bot blocks
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def iter_jsonl(p: Path):
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def extract_urls_from_selected() -> dict[str, str]:
    """Return {expanded_url: display_url} for all URLs in selected content."""
    sel = json.loads(SELECTION_FILE.read_text(encoding="utf-8"))
    selected_threads = set(sel.get("chapter_threads", []))
    compendium_tweets = set(sel.get("compendium_tweets", []))

    tweets_by_id: dict[str, dict] = {}
    for obj in iter_jsonl(TWEETS_FILE):
        tid = obj.get("id_str")
        if tid:
            tweets_by_id[tid] = obj

    urls: dict[str, str] = {}

    def collect_from_raw(raw: dict):
        for u in (raw.get("entities") or {}).get("urls", []):
            exp = u.get("expanded_url")
            if exp:
                urls.setdefault(exp, u.get("display_url", ""))

    # From selected threads
    for th in iter_jsonl(THREADS_FILE):
        if str(th.get("thread_id")) not in selected_threads:
            continue
        for tw in th.get("tweets", []):
            tid = tw.get("id_str")
            full = tweets_by_id.get(tid) or {}
            raw = full.get("raw") or {}
            if isinstance(raw, dict):
                collect_from_raw(raw)

    # From compendium tweets
    for ctid in compendium_tweets:
        full = tweets_by_id.get(ctid) or {}
        raw = full.get("raw") or {}
        if isinstance(raw, dict):
            collect_from_raw(raw)

    return urls


def fetch_title(url: str) -> tuple[str, str]:
    """
    Fetch URL and extract <title>. Returns (title, status).
    Status is one of: ok, broken, timeout, no_title, redirect.
    """
    # Create SSL context that doesn't verify (many old links have cert issues)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        resp = urlopen(req, timeout=TIMEOUT, context=ctx)
        # Read up to 64KB — title is always near the top
        data = resp.read(65536)
        # Try to decode
        charset = resp.headers.get_content_charset() or "utf-8"
        try:
            html = data.decode(charset, errors="replace")
        except (LookupError, UnicodeDecodeError):
            html = data.decode("utf-8", errors="replace")

        m = TITLE_RE.search(html)
        if m:
            title = unescape(m.group(1)).strip()
            # Clean up whitespace
            title = re.sub(r"\s+", " ", title)
            if title:
                return title, "ok"
        return "", "no_title"

    except HTTPError as e:
        return "", f"broken_{e.code}"
    except (URLError, OSError):
        return "", "broken"
    except TimeoutError:
        return "", "timeout"
    except Exception as e:
        return "", f"error_{type(e).__name__}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retry", action="store_true", help="Retry broken/timeout URLs")
    ap.add_argument("--all", action="store_true", help="Refetch all URLs")
    args = ap.parse_args()

    # Load existing results
    existing: dict[str, dict] = {}
    if OUTPUT_FILE.exists() and not args.all:
        existing = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))

    # Get all URLs needed
    url_map = extract_urls_from_selected()
    print(f"URLs in selected content: {len(url_map)}")

    # Determine which to fetch
    to_fetch: dict[str, str] = {}
    for url, display in url_map.items():
        if url not in existing:
            to_fetch[url] = display
        elif args.retry and existing[url].get("status", "") not in ("ok", "no_title"):
            to_fetch[url] = display

    print(f"Already fetched: {len(url_map) - len(to_fetch)}")
    print(f"To fetch: {len(to_fetch)}")

    if not to_fetch:
        print("Nothing to fetch.")
        # Still ensure all display_urls are current
        for url, display in url_map.items():
            if url in existing:
                existing[url]["display_url"] = display
        OUTPUT_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
        return

    # Fetch titles
    results = dict(existing)
    fetched = 0
    for i, (url, display) in enumerate(to_fetch.items(), 1):
        print(f"  [{i}/{len(to_fetch)}] {url[:80]}...", end=" ", flush=True)
        title, status = fetch_title(url)
        print(f"-> {status}" + (f" \"{title[:50]}\"" if title else ""))

        results[url] = {
            "title": title,
            "display_url": display,
            "status": status,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        fetched += 1

        # Save periodically (every 20) in case of interruption
        if fetched % 20 == 0:
            OUTPUT_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

        time.sleep(DELAY)

    # Final save
    OUTPUT_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    # Summary
    statuses: dict[str, int] = {}
    for v in results.values():
        s = v.get("status", "unknown")
        statuses[s] = statuses.get(s, 0) + 1

    print(f"\nDone. Fetched {fetched} URLs.")
    print(f"Results saved to: {OUTPUT_FILE}")
    print("Status summary:")
    for s, c in sorted(statuses.items(), key=lambda x: -x[1]):
        print(f"  {s}: {c}")


if __name__ == "__main__":
    main()
