#!/usr/bin/env python3
import json
from datetime import datetime

TWEETS_DATA = "tweets_normalized.jsonl"
THREADS_DATA = "threads_data.jsonl"
THREAD_OF_THREADS_ID = "1279451428302422016"


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
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def main():
    # 1) Load threads and build tweet_id -> thread_id mapping
    threads_by_id = {}
    tweet_to_thread = {}

    for thread in iter_jsonl(THREADS_DATA):
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

    # 2) Ensure the thread-of-threads itself exists
    thread_of_threads = threads_by_id.get(THREAD_OF_THREADS_ID)
    if not thread_of_threads:
        raise SystemExit(
            f"Thread-of-threads {THREAD_OF_THREADS_ID} not found in {THREADS_DATA}"
        )

    # Collect all tweet IDs in that thread
    tot_tweet_ids = []
    for tw in thread_of_threads.get("tweets", []):
        tid = tw.get("id_str")
        if tid:
            tot_tweet_ids.append(tid)

    print(f"Thread-of-threads contains {len(tot_tweet_ids)} tweets")

    # 3) Load full tweet objects (with 'raw') for those ids
    full_tweets = {}
    needed = set(tot_tweet_ids)
    found = 0
    for obj in iter_jsonl(TWEETS_DATA):
        tid = obj.get("id_str")
        if tid in needed:
            full_tweets[tid] = obj
            found += 1
            if found == len(needed):
                break

    print(f"Resolved {found} of {len(needed)} TOT tweets to full records")

    # 4) For each tweet in the thread-of-threads, look at quoted_status / quoted_status_id_str
    referenced_thread_roots = {}
    external_quotes = 0
    no_quote = 0

    for tid in tot_tweet_ids:
        tw = full_tweets.get(tid)
        if not tw:
            continue
        raw = tw.get("raw") or {}

        q_id = None
        q_root_thread_id = None

        quoted = raw.get("quoted_status")
        if quoted:
            q_id = quoted.get("id_str") or quoted.get("id")
            if q_id is not None:
                q_id = str(q_id)
        else:
            q_id = raw.get("quoted_status_id_str")
            if q_id is not None:
                q_id = str(q_id)

        if not q_id:
            no_quote += 1
            continue

        # See if this quoted tweet belongs to one of your >=4-tweet threads
        q_root_thread_id = tweet_to_thread.get(q_id)
        if not q_root_thread_id:
            external_quotes += 1
            continue

        # Get that thread and its root tweet (earliest created_at)
        thread = threads_by_id.get(q_root_thread_id)
        if not thread:
            continue

        tweets = thread.get("tweets", [])
        if not tweets:
            continue

        # Find earliest tweet in this thread
        def sort_key(t):
            ts = t.get("created_at")
            dt = parse_created_at(ts)
            return dt or ts or ""

        tweets_sorted = sorted(tweets, key=sort_key)
        root_tweet = tweets_sorted[0]
        root_text = (root_tweet.get("full_text") or "").replace("\n", " ")
        if len(root_text) > 140:
            root_text = root_text[:137] + "..."

        referenced_thread_roots[q_root_thread_id] = {
            "quoted_tweet_id": q_id,
            "root_tweet_id": root_tweet.get("id_str"),
            "root_text": root_text,
        }

    # 5) Report
    print()
    print(f"Quoted threads that resolve to your >=4-tweet threads: {len(referenced_thread_roots)}")
    print(f"Tweets in thread-of-threads with no quote attached: {no_quote}")
    print(f"Quotes that don't map to your >=4-tweet threads (external/short): {external_quotes}")
    print()

    # Dump details
    for i, (thread_id, info) in enumerate(sorted(referenced_thread_roots.items()), start=1):
        print(f"{i:3d}. thread_id={thread_id} quoted_tweet_id={info['quoted_tweet_id']}")
        print(f"     root_tweet_id={info['root_tweet_id']}")
        print(f"     text: {info['root_text']}")
        print()


if __name__ == "__main__":
    main()
