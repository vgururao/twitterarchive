#!/usr/bin/env python3
import json

THREADS_DATA_JSONL = "threads_data.jsonl"
THREADS_UI_JSON = "threads_ui.json"

def main():
    threads = []
    with open(THREADS_DATA_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)

            # Trim down to the fields the UI actually needs
            threads.append({
                "thread_id": obj.get("thread_id"),
                "root_id": obj.get("root_id"),
                "start_created_at": obj.get("start_created_at"),
                "num_tweets": obj.get("num_tweets"),
                "max_favorites": obj.get("max_favorites"),
                "max_retweets": obj.get("max_retweets"),
                "has_external_dependency": obj.get("has_external_dependency", False),
                "has_external_reply": obj.get("has_external_reply", False),
                "has_external_quote": obj.get("has_external_quote", False),
                "tweets": [
                    {
                        "id_str": t.get("id_str"),
                        "created_at": t.get("created_at"),
                        "full_text": t.get("full_text"),
                        "favorite_count": t.get("favorite_count", 0),
                        "retweet_count": t.get("retweet_count", 0),
                    }
                    for t in obj.get("tweets", [])
                ],
            })

    with open(THREADS_UI_JSON, "w", encoding="utf-8") as out_f:
        json.dump(threads, out_f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(threads)} threads to {THREADS_UI_JSON}")

if __name__ == "__main__":
    main()
