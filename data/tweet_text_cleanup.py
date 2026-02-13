#!/usr/bin/env python3
"""
Shared tweet text cleanup/rendering for both book and compendium generators.

Features:
1) Decode literal HTML entities in tweet text (e.g., &gt; -> >) so they display correctly.
2) Render lightweight "Twitter markdown": *bold* and _italics_.
3) Render entity URLs with fetched page titles (from url_titles.json),
   falling back to display_url, then "link".
"""
from __future__ import annotations

import json
import re
from html import escape, unescape
from pathlib import Path
from typing import Any, Dict, List, Optional

# Conservative patterns:
# - avoid matching inside words
# - single-line only
BOLD_RE = re.compile(r"(?<!\w)\*(?=\S)([^\n*]+?)(?<=\S)\*(?!\w)")
ITALIC_RE = re.compile(r"(?<!\w)_(?=\S)([^\n_]+?)(?<=\S)_(?!\w)")

# Paths to data files
_DATA_DIR = Path(__file__).resolve().parent
URL_TITLES_FILE = _DATA_DIR / "url_titles.json"
URL_OVERRIDES_FILE = _DATA_DIR / "url_overrides.json"


def load_url_titles(path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """Load the url_titles.json map. Returns {} if file doesn't exist."""
    p = path or URL_TITLES_FILE
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def load_url_overrides(path: Optional[Path] = None) -> Dict[str, Dict[str, str]]:
    """
    Load url_overrides.json. Returns {original_url: {replacement_url, title, reason}}.
    """
    p = path or URL_OVERRIDES_FILE
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {o["original_url"]: o for o in data.get("overrides", []) if o.get("original_url")}


def _resolve_url(expanded_url: str, url_overrides: Dict[str, Dict[str, str]]) -> tuple:
    """
    Apply URL override if one exists. Returns (href, title_override_or_None).
    """
    override = url_overrides.get(expanded_url)
    if override:
        return override.get("replacement_url", expanded_url), override.get("title")
    return expanded_url, None


def _get_link_text(expanded_url: str, display_url: str,
                   url_titles: Dict[str, Dict[str, Any]],
                   title_override: Optional[str] = None) -> str:
    """
    Determine the best anchor text for a URL:
    0. Explicit title override (from url_overrides.json)
    1. Fetched page title (if status is "ok" and title is non-empty)
    2. display_url from Twitter entity data
    3. "link" as last resort
    """
    if title_override:
        return title_override
    entry = url_titles.get(expanded_url)
    if entry and entry.get("status") == "ok" and entry.get("title"):
        return entry["title"]
    if display_url:
        return display_url
    return "link"


def _apply_simple_markdown(escaped_text: str) -> str:
    escaped_text = BOLD_RE.sub(r"<strong>\1</strong>", escaped_text)
    escaped_text = ITALIC_RE.sub(r"<em>\1</em>", escaped_text)
    return escaped_text


def _get_entity_urls(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    entities = (raw or {}).get("entities") or {}
    urls = entities.get("urls") or []
    return [u for u in urls if isinstance(u, dict)]


_SELF_TWEET_URL_RE = re.compile(r'twitter\.com/vgr/status/\d+')
_OTHER_TWEET_URL_RE = re.compile(r'twitter\.com/(\w+)/status/(\d+)')


def render_tweet_text_html(text: str, raw: Dict[str, Any],
                           url_titles: Optional[Dict[str, Dict[str, Any]]] = None,
                           url_overrides: Optional[Dict[str, Dict[str, str]]] = None,
                           embed_self_tweets: bool = False,
                           endnotes: Optional[List[Dict[str, str]]] = None,
                           link_label: str = "link") -> str:
    """
    Convert tweet text to HTML:
      - unescape literal HTML entities in the tweet text (so &gt; displays as >)
      - apply URL overrides (hijacked/broken link replacements)
      - replace t.co urls with <a href="expanded_url">title or display_url</a>
      - if embed_self_tweets, remove self-tweet links (content shown as quote box instead)
      - other-people tweet links rendered as "tweet" with superscript endnote
      - escape all remaining text
      - apply *bold* and _italics_
      - convert newlines to <br>
    """
    if not text:
        return ""
    if url_titles is None:
        url_titles = {}
    if url_overrides is None:
        url_overrides = {}

    decoded = unescape(text)

    # Strip media t.co URLs from text (media is rendered separately as embeds)
    media = ((raw or {}).get("extended_entities") or {}).get("media") or \
            ((raw or {}).get("entities") or {}).get("media") or []
    for m in media:
        short = (m if isinstance(m, dict) else {}).get("url")
        if short:
            decoded = decoded.replace(short, "")

    urls = _get_entity_urls(raw)
    # placeholders unlikely to appear in real text
    for i, u in enumerate(urls):
        short = u.get("url")
        if short:
            decoded = decoded.replace(short, f"\u0000URL{i}\u0000")

    esc = escape(decoded, quote=False)

    for i, u in enumerate(urls):
        expanded = u.get("expanded_url") or u.get("url") or ""
        display = u.get("display_url") or ""
        placeholder = escape(f"\u0000URL{i}\u0000", quote=False)

        # Self-tweet links: strip from text when embedding as quote boxes
        if embed_self_tweets and _SELF_TWEET_URL_RE.search(expanded):
            esc = esc.replace(placeholder, "")
            continue

        # Other-people tweet links: render as "tweet" with endnote
        other_match = _OTHER_TWEET_URL_RE.search(expanded)
        if other_match and endnotes is not None:
            handle = other_match.group(1)
            note_num = len(endnotes) + 1
            endnotes.append({"num": note_num, "handle": handle, "url": expanded})
            esc = esc.replace(
                placeholder,
                f'<a href="{escape(expanded)}" target="_blank" rel="noreferrer">tweet</a>'
                f'<sup class="endnote-ref"><a href="#endnote-{note_num}">[{note_num}]</a></sup>'
            )
            continue

        if expanded:
            href, title_override = _resolve_url(expanded, url_overrides)
            anchor = _get_link_text(expanded, display, url_titles, title_override)
            esc = esc.replace(
                placeholder,
                f'<a href="{escape(href)}" target="_blank" rel="noreferrer">{escape(anchor)}</a>'
            )
        else:
            esc = esc.replace(placeholder, escape(link_label))

    esc = _apply_simple_markdown(esc)

    return esc.replace("\n", "<br>\n")


def render_ascii_pre(text: str) -> str:
    """
    For ASCII-art tweets: decode entities (so &gt; becomes >) but do NOT apply markdown,
    and keep as preformatted text (caller wraps in <pre>).
    """
    return escape(unescape(text or ""), quote=False)
