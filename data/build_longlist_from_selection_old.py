#!/usr/bin/env python3
import json
import re

SELECTION_IN = "selection.json"
THREADS_DATA = "threads_data.jsonl"
SELECTION_OUT = "selection_longlist.json"

THREAD_OF_THREADS_ID = "1279451428302422016"

# Regex to catch tweet URLs like .../status/1234567890123456789
STATUS_ID_RE = re.compile(r"status/(\d+)")


def load_selection(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def iter_threads(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def main():
    sel = load_selection(SELECTION_IN)
    chapter_threads = set(sel.get("chapter_threads", []))
    compendium_tweets = set(sel.get("compendium_tweets", []))

    print(f"Initial chapter_threads: {len(chapter_threads)}")
    print(f"Initial compendium_tweets: {len(compendium_tweets)}")

    # Index threads by id
    threads_by_id = {}
    for thread in iter_threads(THREADS_DATA):
        tid = thread.get("thread_id")
        if not tid:
            continue
        threads_by_id[tid] = thread

    print(f"Loaded {len(threads_by_id)} threads from {THREADS_DATA}")

    # Get the "thread of threads"
    thread_of_threads = threads_by_id.get(THREAD_OF_THREADS_ID)
    if not thread_of_threads:
        raise SystemExit(
            f"Thread-of-threads {THREAD_OF_THREADS_ID} not found in {THREADS_DATA}"
        )

    # Extract candidate thread ids from all tweets in that thread
    referenced_ids = set()
    missing_in_archive = set()

    for tw in thread_of_threads.get("tweets", []):
        text = tw.get("full_text") or ""
        for match in STATUS_ID_RE.finditer(text):
            tid = match.group(1)
            # Only count 64-bit looking IDs (defensive)
            if len(tid) >= 15:
                if tid in threads_by_id:
                    referenced_ids.add(tid)
                else:
                    missing_in_archive.add(tid)

    print(f"Found {len(referenced_ids)} referenced thread ids present in archive")
    if missing_in_archive:
        print(f"{len(missing_in_archive)} referenced ids not in threads_data.jsonl")

    # Build merged chapter list
    merged_chapters = sorted(chapter_threads.union(referenced_ids))
    print(f"Merged chapter_threads longlist size: {len(merged_chapters)}")

    out = {
        "chapter_threads": merged_chapters,
        "compendium_tweets": sorted(compendium_tweets),
        "metadata": {
            "source_selection": SELECTION_IN,
            "thread_of_threads": THREAD_OF_THREADS_ID,
            "added_from_thread_of_threads": sorted(referenced_ids - chapter_threads),
            "missing_referenced_ids": sorted(missing_in_archive),
        },
    }

    with open(SELECTION_OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote merged selection longlist to {SELECTION_OUT}")


if __name__ == "__main__":
    main()
