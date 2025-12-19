#!/usr/bin/env python3
import json
import os

SMUGISMS_JSON = "smugisms_seeds.json"
SINGLETONS_JSON = "singleton_candidates.json"
OUT_JSON = "singles_ui.json"


def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    smug = load_json(SMUGISMS_JSON)
    singles = load_json(SINGLETONS_JSON)

    print(f"Loaded {len(smug)} smugisms seeds from {SMUGISMS_JSON}")
    print(f"Loaded {len(singles)} singleton candidates from {SINGLETONS_JSON}")

    by_id = {}

    # First, add singleton candidates
    for row in singles:
        tid = row.get("id_str")
        if not tid:
            continue
        fav = row.get("favorite_count", 0) or 0
        rt = row.get("retweet_count", 0) or 0
        score = row.get("score", fav + rt)
        text = (row.get("text") or "").replace("\n", " ")
        is_reply = 1 if row.get("in_reply_to_status_id_str") else 0

        by_id[tid] = {
            "id_str": tid,
            "created_at": row.get("created_at"),
            "favorite_count": fav,
            "retweet_count": rt,
            "score": score,
            "is_reply": bool(is_reply),
            "text": text,
            "from_smugisms": False,
        }

    # Then, merge in smugisms (may overlap, but mark them)
    for row in smug:
        tid = row.get("id_str")
        if not tid:
            continue
        fav = row.get("favorite_count", 0) or 0
        rt = row.get("retweet_count", 0) or 0
        score = row.get("score", fav + rt)
        text = (row.get("text") or "").replace("\n", " ")

        existing = by_id.get(tid)
        if existing:
            # Merge, preferring max stats and preserving reply flag
            existing["favorite_count"] = max(existing["favorite_count"], fav)
            existing["retweet_count"] = max(existing["retweet_count"], rt)
            existing["score"] = max(existing["score"], score)
            if not existing["text"]:
                existing["text"] = text
            existing["from_smugisms"] = True
        else:
            by_id[tid] = {
                "id_str": tid,
                "created_at": row.get("created_at"),
                "favorite_count": fav,
                "retweet_count": rt,
                "score": score,
                "is_reply": False,
                "text": text,
                "from_smugisms": True,
            }

    merged = list(by_id.values())

    # Sort by score desc, then likes, then rts
    merged.sort(
        key=lambda x: (-(x["score"]), -(x["favorite_count"]), -(x["retweet_count"]))
    )

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"Merged {len(merged)} unique tweets into {OUT_JSON}")
    smug_count = sum(1 for x in merged if x["from_smugisms"])
    print(f"  of which {smug_count} are marked from_smugisms=True")


if __name__ == "__main__":
    main()
