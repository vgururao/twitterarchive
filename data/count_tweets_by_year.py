#!/usr/bin/env python3
import argparse, json, re
from pathlib import Path
from collections import Counter
from datetime import datetime
from email.utils import parsedate_to_datetime

# Twitter export often uses this format: "Sat Sep 01 22:53:29 +0000 2018"
def parse_dt(s: str):
    if not s:
        return None
    s = s.strip()
    # ISO 8601-ish
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt
    except Exception:
        pass
    # Twitter export format
    try:
        return parsedate_to_datetime(s)
    except Exception:
        return None

def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)

def iter_export_js_objects(path: Path):
    """
    Twitter export tweets.js/tweets-part*.js are JS wrappers around JSON.
    We strip a leading assignment and parse the JSON payload.
    """
    txt = path.read_text(encoding="utf-8", errors="replace").strip()
    # Remove leading "window.YTD.tweets.part0 = " or similar
    txt = re.sub(r"^\s*window\.[^=]+=\s*", "", txt, flags=re.DOTALL)
    # Remove trailing semicolon
    txt = re.sub(r";\s*$", "", txt)
    data = json.loads(txt)
    # Export format is usually a list of {"tweet": {...}} wrappers
    for item in data:
        if isinstance(item, dict) and "tweet" in item and isinstance(item["tweet"], dict):
            yield item["tweet"]
        elif isinstance(item, dict):
            yield item

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--normalized", default="data/tweets_normalized.jsonl",
                    help="Path to normalized tweets JSONL")
    ap.add_argument("--export_glob", default="data/tweets*.js",
                    help="Glob for raw export JS files (tweets.js, tweets-part*.js)")
    ap.add_argument("--start", type=int, default=2007)
    ap.add_argument("--end", type=int, default=2022)
    args = ap.parse_args()

    counts = Counter()
    total = 0
    unknown_date = 0
    earliest = []

    norm_path = Path(args.normalized)
    if norm_path.exists():
        # normalized record expected to have created_at or raw.created_at
        for obj in iter_jsonl(norm_path):
            raw = obj.get("raw") if isinstance(obj, dict) else None
            created = None
            if isinstance(obj, dict):
                created = obj.get("created_at") or (raw.get("created_at") if isinstance(raw, dict) else None)
            dt = parse_dt(created or "")
            if dt:
                counts[dt.year] += 1
                text = obj.get("full_text") or (raw.get("full_text") if isinstance(raw, dict) else "")
                tid = obj.get("id_str") or obj.get("id")
                earliest.append((dt, tid, text))
            else:
                unknown_date += 1
            total += 1
    else:
        # fallback: parse export JS
        js_files = sorted(Path().glob(args.export_glob))
        if not js_files:
            raise SystemExit(f"No normalized file at {norm_path} and no export JS files matching {args.export_glob}")
        for js in js_files:
            for tw in iter_export_js_objects(js):
                created = tw.get("created_at") if isinstance(tw, dict) else None
        dt = parse_dt(created or "")
        if dt:
            counts[dt.year] += 1
            text = tw.get("full_text") or tw.get("text") or ""
            tid = tw.get("id_str") or tw.get("id")
            earliest.append((dt, tid, text))
        else:
            unknown_date += 1
        total += 1

    print(f"Total tweets scanned: {total}")
    if unknown_date:
        print(f"Tweets with unparseable/missing date: {unknown_date}")

    for y in range(args.start, args.end + 1):
        print(f"{y}\t{counts.get(y, 0)}")

    # Helpful sanity: earliest/latest year actually present
    present_years = sorted([y for y, c in counts.items() if c > 0])
    if present_years:
        print(f"\nEarliest year present: {present_years[0]}")
        print(f"Latest year present: {present_years[-1]}")
    earliest.sort(key=lambda x: x[0])

    print("\nFirst 10 tweets in archive:")
    for dt, tid, text in earliest[:25]:
        clean = " ".join(text.split())
        if len(clean) > 140:
            clean = clean[:137] + "..."
        print(f"{dt.strftime('%Y-%m-%d')} | {tid} | {clean}")


if __name__ == "__main__":
    main()
