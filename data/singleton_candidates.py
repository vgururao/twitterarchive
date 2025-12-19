#!/usr/bin/env python3
import json
from collections import defaultdict

TWEETS_DATA = "tweets_normalized.jsonl"
OUT_JSON = "singleton_candidates.json"
OUT_CSV = "singleton_candidates.csv"

TOP_N = 1000  # adjust as needed


def iter_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def main():
    tweets = {}
    reply_parent = {}

    # 1) Load tweets and parents
    for obj in iter_jsonl(TWEETS_DATA):
        tid = obj.get("id_str")
        if not tid:
            continue
        tweets[tid] = {
            "id_str": tid,
            "created_at": obj.get("created_at"),
            "favorite_count": obj.get("favorite_count", 0),
            "retweet_count": obj.get("retweet_count", 0),
            "in_reply_to_status_id_str": obj.get("in_reply_to_status_id_str"),
            "full_text": (obj.get("full_text") or obj.get("text") or ""),
        }
        parent = obj.get("in_reply_to_status_id_str")
        if parent:
            reply_parent[tid] = parent

    print(f"Loaded {len(tweets)} tweets")

    # 2) Compute root for each tweet
    root_for = {}

    def find_root(tid):
        seen = set()
        cur = tid
        while True:
            if cur in root_for:
                return root_for[cur]
            if cur in seen:
                return cur
            seen.add(cur)
            parent = reply_parent.get(cur)
            if not parent or parent not in tweets:
                return cur
            cur = parent

    for tid in tweets.keys():
        root_for[tid] = find_root(tid)

    # 3) Count thread sizes
    thread_size = defaultdict(int)
    for tid, root in root_for.items():
        thread_size[root] += 1

    # 4) Collect singleton tweets (thread size == 1)
    singles = []
    for tid, info in tweets.items():
        root = root_for[tid]
        if thread_size[root] != 1:
            continue  # part of a multi-tweet thread

        fav = info["favorite_count"] or 0
        rt = info["retweet_count"] or 0
        text = info["full_text"].replace("\n", " ")

        singles.append({
            "id_str": tid,
            "created_at": info["created_at"],
            "favorite_count": fav,
            "retweet_count": rt,
            "score": fav + rt,
            "in_reply_to_status_id_str": info["in_reply_to_status_id_str"],
            "text": text,
        })

    print(f"Found {len(singles)} singleton tweets (no in-archive thread)")

    # 5) Sort by engagement
    singles_sorted = sorted(
        singles,
        key=lambda x: (-(x["score"]), -(x["favorite_count"]), -(x["retweet_count"]))
    )

    top = singles_sorted[:TOP_N]
    print(f"Keeping top {len(top)} by engagement")

    # 6) Write JSON
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(top, f, ensure_ascii=False, indent=2)

    # 7) Write CSV for eyeballing
    with open(OUT_CSV, "w", encoding="utf-8") as f:
        f.write("id_str,created_at,favorite_count,retweet_count,score,is_reply,text\n")
        for row in top:
            is_reply = 1 if row["in_reply_to_status_id_str"] else 0
            text = row["text"].replace('"', '""')
            f.write(
                f"\"{row['id_str']}\",\"{row['created_at']}\",{row['favorite_count']},"
                f"{row['retweet_count']},{row['score']},{is_reply},\"{text}\"\n"
            )

    print(f"Wrote {len(top)} singleton candidates to {OUT_JSON} and {OUT_CSV}")


if __name__ == "__main__":
    main()
