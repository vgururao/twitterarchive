#!/usr/bin/env python3
import re
from pathlib import Path

HTML_PATH = Path("book/chapters/compendium.html")

TWEET_IDS = [
    "1018724483509542912",
    "1018734664352059392",
]

def patch_one(html: str, tid: str) -> tuple[str, int]:
    """
    Find the tweet div by data-tweet-id and patch only the <pre>...</pre> content inside it.
    Replace tab characters with 4 spaces.
    """
    # Narrow match: the tweet container with that id, up to its closing </div>
    # This assumes tweet blocks are not nested in a way that breaks this (they usually aren't).
    tweet_re = re.compile(
        rf'(<div[^>]+data-tweet-id="{re.escape(tid)}"[^>]*>)(.*?)(</div>\s*)',
        re.DOTALL
    )

    m = tweet_re.search(html)
    if not m:
        return html, 0

    head, body, tail = m.group(1), m.group(2), m.group(3)

    # Patch <pre> blocks inside this tweet only
    pre_re = re.compile(r'(<pre>)(.*?)(</pre>)', re.DOTALL)

    count = 0
    def pre_sub(mm):
        nonlocal count
        inner = mm.group(2)
        if "\t" in inner:
            inner = inner.replace("\t", "    ")
            count += 1
        return mm.group(1) + inner + mm.group(3)

    new_body = pre_re.sub(pre_sub, body)
    new_tweet = head + new_body + tail

    new_html = html[:m.start()] + new_tweet + html[m.end():]
    return new_html, count

def main():
    if not HTML_PATH.exists():
        raise SystemExit(f"Missing {HTML_PATH}. Run the generator first.")

    html = HTML_PATH.read_text(encoding="utf-8")

    total_patched = 0
    for tid in TWEET_IDS:
        html, patched = patch_one(html, tid)
        total_patched += patched

    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"Patched HTML: {HTML_PATH}")
    print(f"Patched <pre> blocks (tabs -> spaces): {total_patched}")

if __name__ == "__main__":
    main()
