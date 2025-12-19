#!/usr/bin/env python3
import json
from pathlib import Path

IN_THREADS = Path("threads_data.jsonl")
PATCHES = Path("thread_patches.json")
OUT_THREADS = Path("threads_data_patched.jsonl")

def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)

def main():
    patches = json.loads(PATCHES.read_text(encoding="utf-8"))
    print(f"Loaded patches for {len(patches)} threads")

    dropped_total = 0
    kept_threads = 0

    with OUT_THREADS.open("w", encoding="utf-8") as out:
        for thread in iter_jsonl(IN_THREADS):
            tid = thread.get("thread_id")
            drop_ids = set((patches.get(tid) or {}).get("drop_tweets", []))

            if drop_ids:
                tweets = thread.get("tweets", [])
                new_tweets = [t for t in tweets if t.get("id_str") not in drop_ids]
                dropped = len(tweets) - len(new_tweets)
                dropped_total += dropped
                thread["tweets"] = new_tweets
                thread["num_tweets"] = len(new_tweets)

            kept_threads += 1
            out.write(json.dumps(thread, ensure_ascii=False) + "\n")

    print(f"Wrote {kept_threads} threads to {OUT_THREADS}")
    print(f"Dropped {dropped_total} tweets total")

if __name__ == "__main__":
    main()
