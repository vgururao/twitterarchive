#!/usr/bin/env python3
import json
import re
from collections import defaultdict

TWEETS_DATA = "tweets_normalized.jsonl"

SMUGISMS_ROOT_ID = "1310769794665177088"  # your smugisms meta-thread root

OUT_JSON = "smugisms_seeds.json"
OUT_CSV = "smugisms_seeds.csv"

STATUS_ID_RE = re.compile(r"status(?:es)?/(\d+)")


def iter_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def main():
    # 1) Load all tweets with raw
    tweets_by_id = {}
    reply_parent = {}

    for obj in iter_jsonl(TWEETS_DATA):
        tid = obj.get("id_str")
        if not tid:
            continue
        tweets_by_id[tid] = obj
        parent = obj.get("in_reply_to_status_id_str")
        if parent:
            reply_parent[tid] = parent

    print(f"Loaded {len(tweets_by_id)} tweets from {TWEETS_DATA}")

    if SMUGISMS_ROOT_ID not in tweets_by_id:
        raise SystemExit(f"Smugisms root {SMUGISMS_ROOT_ID} not found in archive")

    # 2) Compute root-for map to reconstruct threads
    root_for = {}

    def find_root(tid):
        seen = set()
        cur = tid
        while True:
            if cur in root_for:
                return root_for[cur]
            if cur in seen:
                # cycle, treat as root
                return cur
            seen.add(cur)
            parent = reply_parent.get(cur)
            if not parent or parent not in tweets_by_id:
                return cur
            cur = parent

    for tid in tweets_by_id.keys():
        root_for[tid] = find_root(tid)

    # 3) Collect all tweets whose root is the smugisms root (the smugisms thread)
    smugisms_tweets = [
        obj for tid, obj in tweets_by_id.items()
        if root_for.get(tid) == SMUGISMS_ROOT_ID
    ]

    print(f"Smugisms thread contains {len(smugisms_tweets)} tweets (including root)")

    # 4) From each smugisms tweet, extract status IDs from expanded_url
    candidates = {}

    for tw in smugisms_tweets:
        raw = tw.get("raw") or {}
        entities = raw.get("entities") or {}
        urls = entities.get("urls") or []

        for u in urls:
            expanded = u.get("expanded_url") or ""
            m = STATUS_ID_RE.search(expanded)
            if not m:
                continue
            target_id = m.group(1)
            target = tweets_by_id.get(target_id)
            if not target:
                continue

            txt = (target.get("full_text") or target.get("text") or "").replace("\n", " ")
            fav = target.get("favorite_count", 0)
            rt = target.get("retweet_count", 0)

            candidates[target_id] = {
                "id_str": target_id,
                "created_at": target.get("created_at"),
                "favorite_count": fav,
                "retweet_count": rt,
                "score": fav + rt,
                "text": txt,
            }

    print(f"Extracted {len(candidates)} smugism target tweets")

    # 5) Sort by engagement
    data = sorted(
        candidates.values(),
        key=lambda x: (-(x["score"]), -(x["favorite_count"]), -(x["retweet_count"]))
    )

    # 6) Write JSON
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 7) Write CSV
    with open(OUT_CSV, "w", encoding="utf-8") as f:
        f.write("id_str,created_at,favorite_count,retweet_count,score,text\n")
        for row in data:
            text = row["text"].replace('"', '""')
            f.write(
                f"\"{row['id_str']}\",\"{row['created_at']}\",{row['favorite_count']},"
                f"{row['retweet_count']},{row['score']},\"{text}\"\n"
            )

    print(f"Wrote {len(data)} smugisms seeds to {OUT_JSON} and {OUT_CSV}")


if __name__ == "__main__":
    main()
