#!/usr/bin/env python3
import json
import argparse
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tagged", default="data/compendium_tagged_updated.json")
    ap.add_argument("--ids", required=True, help="Text file with one tweet id per line (first 10)")
    ap.add_argument("--out", default="data/compendium_tagged_with_prehistory.json")
    ap.add_argument("--title", default="2007: Earliest Tweets")
    ap.add_argument("--year", default="2007")
    args = ap.parse_args()

    tagged_path = Path(args.tagged)
    ids_path = Path(args.ids)
    out_path = Path(args.out)

    data = json.loads(tagged_path.read_text(encoding="utf-8"))
    tweets = data.get("tweets") or []

    pre_ids = [line.strip() for line in ids_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    # Index existing ids
    existing = {str(t.get("id_str")) for t in tweets if isinstance(t, dict) and t.get("id_str") is not None}

    # Build header marker + tweet entries
    header = {
        "kind": "section_header",
        "title": args.title,
        "year": args.year
    }

    pre_entries = []
    for tid in pre_ids:
        if tid in existing:
            continue
        pre_entries.append({
            "id_str": tid,
            "tags": ["prehistory"],
            "featured": False,
            "discard": False
        })

    # Prepend: header + entries, then old content
    new_tweets = [header] + pre_entries + tweets
    data["tweets"] = new_tweets

    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Wrote patched compendium file: {out_path}")
    print(f"Added {len(pre_entries)} new prehistory tweets (skipped {len(pre_ids)-len(pre_entries)} already present).")

if __name__ == "__main__":
    main()
