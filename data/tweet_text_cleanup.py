#!/usr/bin/env python3
"""
Shared tweet text cleanup/rendering for both book and compendium generators.

Features:
1) Decode literal HTML entities in tweet text (e.g., &gt; -> >) so they display correctly.
2) Render lightweight "Twitter markdown": *bold* and _italics_.
3) Render all entity URLs with anchor text "link" (or custom label), not the URL.
"""
from __future__ import annotations

import re
from html import escape, unescape
from typing import Any, Dict, List

# Conservative patterns:
# - avoid matching inside words
# - single-line only
BOLD_RE = re.compile(r"(?<!\\w)\\*(?=\\S)([^\\n*]+?)(?<=\\S)\\*(?!\\w)")
ITALIC_RE = re.compile(r"(?<!\\w)_(?=\\S)([^\\n_]+?)(?<=\\S)_(?!\\w)")

def _apply_simple_markdown(escaped_text: str) -> str:
    escaped_text = BOLD_RE.sub(r"<strong>\\1</strong>", escaped_text)
    escaped_text = ITALIC_RE.sub(r"<em>\\1</em>", escaped_text)
    return escaped_text

def _get_entity_urls(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    entities = (raw or {}).get("entities") or {}
    urls = entities.get("urls") or []
    return [u for u in urls if isinstance(u, dict)]

def render_tweet_text_html(text: str, raw: Dict[str, Any], link_label: str = "link") -> str:
    """
    Convert tweet text to HTML:
      - unescape literal HTML entities in the tweet text (so &gt; displays as >)
      - replace t.co urls present in entities with <a href="expanded_url">link</a>
      - escape all remaining text
      - apply *bold* and _italics_
      - convert newlines to <br>
    """
    if not text:
        return ""

    decoded = unescape(text)

    urls = _get_entity_urls(raw)
    # placeholders unlikely to appear in real text
    for i, u in enumerate(urls):
        short = u.get("url")
        if short:
            decoded = decoded.replace(short, f"\\u0000URL{i}\\u0000")

    esc = escape(decoded, quote=False)

    for i, u in enumerate(urls):
        expanded = u.get("expanded_url") or u.get("url") or ""
        placeholder = escape(f"\\u0000URL{i}\\u0000", quote=False)
        if expanded:
            esc = esc.replace(
                placeholder,
                f'<a href="{escape(expanded)}" target="_blank" rel="noreferrer">{escape(link_label)}</a>'
            )
        else:
            esc = esc.replace(placeholder, escape(link_label))

    esc = _apply_simple_markdown(esc)

    return esc.replace("\\n", "<br>\\n")

def render_ascii_pre(text: str) -> str:
    """
    For ASCII-art tweets: decode entities (so &gt; becomes >) but do NOT apply markdown,
    and keep as preformatted text (caller wraps in <pre>).
    """
    return escape(unescape(text or ""), quote=False)
