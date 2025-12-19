#!/usr/bin/env python3
from pathlib import Path

CSS_PATH = Path("book/compendium.css")

TWEET_IDS = [
    "1018724483509542912",
    "1018734664352059392",
]

PATCH_MARKER_START = "/* === ASCII FIX PATCH (manual) START === */"
PATCH_MARKER_END   = "/* === ASCII FIX PATCH (manual) END === */"

def main():
    if not CSS_PATH.exists():
        raise SystemExit(f"Missing {CSS_PATH}. Run generator with --patch-css first.")

    css = CSS_PATH.read_text(encoding="utf-8")

    # Remove old patch block if present
    if PATCH_MARKER_START in css and PATCH_MARKER_END in css:
        pre = css.split(PATCH_MARKER_START)[0]
        post = css.split(PATCH_MARKER_END)[1]
        css = pre + post

    selectors = ",\n".join([f'.compendium-page [data-tweet-id="{tid}"] pre' for tid in TWEET_IDS])

    patch = f"""
{PATCH_MARKER_START}
{selectors} {{
  white-space: pre;        /* critical: do NOT wrap */
  overflow-x: auto;        /* allow horizontal scroll */
  font-size: 0.90rem;      /* optional: slightly smaller */
  line-height: 1.15;       /* optional: tighter */
}}
{PATCH_MARKER_END}
"""

    css = css.rstrip() + "\n\n" + patch.lstrip()
    CSS_PATH.write_text(css, encoding="utf-8")
    print(f"Patched {CSS_PATH} for ASCII alignment on {len(TWEET_IDS)} tweets.")

if __name__ == "__main__":
    main()
