#!/usr/bin/env python3
import json
from datetime import datetime

TWEETS_DATA = "tweets_normalized.jsonl"
COMPENDIUM_SELECTION = "compendium_selection.json"
OUT_JSON = "compendium_tagged.json"


def iter_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def parse_created_at(ts):
    if ts is None:
        return None
    try:
        # normalized script used ISO8601 with 'Z' or offset
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return None


# --- Heuristic classifier stub ---
# You can refine this; for now it’s conservative and defaults to "unclassified".
def classify_tweet(text: str):
    t = (text or "").lower()

    # Very crude heuristics; safe but not overconfident.
    if any(x in t for x in ["here's a tip", "pro tip", "advice", "you should", "if you want to", "do this"]):
        return ["advice"]
    if any(x in t for x in ["joke:", "haha", "lol", "😂", "😅"]):
        return ["joke"]
    if "thread" in t and len(t) < 120:
        # often meta/meta-hot-take, but compendium is singles; keep conservative
        return ["reflection"]
    if any(x in t for x in ["unpopular opinion", "hot take", "here’s my take", "my take"]):
        return ["hot_take"]
    if len(t) <= 140 and any(x in t for x in ["life is", "people are", "never", "always", "everybody", "nobody"]):
        # short, general statements
        return ["aphorism"]
    if any(x in t for x in ["i think", "i suspect", "it seems to me", "i’ve been thinking"]):
        return ["reflection"]

    # If nothing matches, leave it for you to classify
    return ["unclassified"]


def main():
    # 1) Load compendium selection IDs
    with open(COMPENDIUM_SELECTION, "r", encoding="utf-8") as f:
        sel = json.load(f)
    ids = set(sel.get("compendium_tweets", []))
    print(f"Loaded {len(ids)} compendium tweet IDs")

    # 2) Load tweets and filter to compendium set
    tweets = []
    id_hit = 0
    for obj in iter_jsonl(TWEETS_DATA):
        tid = obj.get("id_str")
        if not tid or tid not in ids:
            continue
        id_hit += 1
        text = obj.get("full_text") or obj.get("text") or ""
        created_at = obj.get("created_at")
        fav = obj.get("favorite_count", 0)
        rt = obj.get("retweet_count", 0)

        tags = classify_tweet(text)

        tweets.append(
            {
                "id_str": tid,
                "created_at": created_at,
                "favorite_count": fav,
                "retweet_count": rt,
                "text": text.replace("\n", " "),
                "tags": tags,
                "featured": False,
                "discard": False,
            }
        )

    print(f"Matched {id_hit} IDs in tweets_normalized.jsonl")

    # 3) Sort chronologically
    def sort_key(tw):
        dt = parse_created_at(tw["created_at"])
        return dt or tw["created_at"] or ""

    tweets_sorted = sorted(tweets, key=sort_key)

    out = {"tweets": tweets_sorted}

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(tweets_sorted)} tagged records to {OUT_JSON}")


if __name__ == "__main__":
    main()
