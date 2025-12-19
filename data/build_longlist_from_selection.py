#!/usr/bin/env python3
import json
import re

SELECTION_IN = "selection.json"
THREADS_DATA = "threads_data.jsonl"
TWEETS_DATA = "tweets_normalized.jsonl"
SELECTION_OUT = "selection_longlist.json"

THREAD_OF_THREADS_ID = "1279451428302422016"

# 1) Standard tweet URLs: .../status/1234567890...
STATUS_ID_RE = re.compile(r"status(?:es)?/(\d+)")
# 2) Fallback: any long-ish numeric ID
BARE_ID_RE = re.compile(r"\b(\d{15,})\b")


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


def iter_tweets(path):
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

    # Load threads and build tweet_id -> thread_id map
    threads_by_id = {}
    tweet_to_thread = {}
    for thread in iter_threads(THREADS_DATA):
        tid = thread.get("thread_id")
        if not tid:
            continue
        threads_by_id[tid] = thread
        for tw in thread.get("tweets", []):
            twid = tw.get("id_str")
            if twid:
                tweet_to_thread[twid] = tid

    print(f"Loaded {len(threads_by_id)} threads from {THREADS_DATA}")
    print(f"Indexed {len(tweet_to_thread)} tweet->thread mappings")

    # Load all tweet IDs from the normalized tweets (for short threads, singles, etc.)
    all_tweet_ids = set()
    for obj in iter_tweets(TWEETS_DATA):
        tid = obj.get("id_str")
        if tid:
            all_tweet_ids.add(tid)

    print(f"Loaded {len(all_tweet_ids)} tweet ids from {TWEETS_DATA}")

    # Get the 'thread of threads' as a thread (it should be >= 4 tweets)
    thread_of_threads = threads_by_id.get(THREAD_OF_THREADS_ID)
    if not thread_of_threads:
        raise SystemExit(
            f"Thread-of-threads {THREAD_OF_THREADS_ID} not found in {THREADS_DATA}"
        )

    referenced_thread_ids = set()
    referenced_single_tweet_ids = set()
    missing_ids = set()

    # Extract candidate ids from all tweets in that thread
    for tw in thread_of_threads.get("tweets", []):
        text = tw.get("full_text") or ""
        candidates = set()

        # From explicit status URLs
        for m in STATUS_ID_RE.finditer(text):
            candidates.add(m.group(1))

        # From bare numeric IDs (fallback)
        for m in BARE_ID_RE.finditer(text):
            candidates.add(m.group(1))

        for cid in candidates:
            # 1) If this tweet appears in a known thread, use that thread_id
            if cid in tweet_to_thread:
                referenced_thread_ids.add(tweet_to_thread[cid])
            # 2) Else if it's at least present as a tweet, track it as a single-tweet/short-thread id
            elif cid in all_tweet_ids:
                referenced_single_tweet_ids.add(cid)
            else:
                missing_ids.add(cid)

    print(f"Referenced thread_ids via tweet_to_thread: {len(referenced_thread_ids)}")
    print(f"Referenced tweet_ids present only as singles/short: {len(referenced_single_tweet_ids)}")
    print(f"Referenced ids missing from archive: {len(missing_ids)}")

    # Build merged chapter list:
    # - existing chapter_threads
    # - threads pointed to by the thread-of-threads (via tweet_to_thread)
    # - single/short tweets referenced in thread-of-threads
    #   (we add these as chapter roots for now; later the book generator will
    #    build short 'chapters' around them from tweets_normalized.jsonl)
    merged_chapters = sorted(
        chapter_threads
        .union(referenced_thread_ids)
        .union(referenced_single_tweet_ids)
    )

    print(f"Merged chapter_threads longlist size: {len(merged_chapters)}")

    out = {
        "chapter_threads": merged_chapters,
        "compendium_tweets": sorted(compendium_tweets),
        "metadata": {
            "source_selection": SELECTION_IN,
            "thread_of_threads": THREAD_OF_THREADS_ID,
            "added_from_thread_of_threads_threads": sorted(referenced_thread_ids - chapter_threads),
            "added_from_thread_of_threads_singles": sorted(referenced_single_tweet_ids),
            "missing_referenced_ids": sorted(missing_ids),
        },
    }

    with open(SELECTION_OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote merged selection longlist to {SELECTION_OUT}")


if __name__ == "__main__":
    main()
