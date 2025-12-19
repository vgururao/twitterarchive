#!/usr/bin/env python3
import json
import re
from datetime import datetime

TWEETS_DATA = "tweets_normalized.jsonl"
THREADS_DATA = "threads_data.jsonl"
THREAD_OF_THREADS_ID = "1279451428302422016"

STATUS_ID_RE = re.compile(r"status(?:es)?/(\d+)")


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
    # 1) Load threads and build tweet_id -> thread_id map
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

    # 4) For each tweet, extract status IDs from expanded_url in entities.urls
    referenced_thread_roots = {}
    url_only_ids = set()
    no_urls = 0

    for tot_tid in tot_tweet_ids:
        tw = full_tweets.get(tot_tid)
        if not tw:
            continue

        raw = tw.get("raw") or {}
        entities = raw.get("entities") or {}
        urls = entities.get("urls") or []

        if not urls:
            no_urls += 1
            continue

        for u in urls:
            expanded = u.get("expanded_url") or ""
            if not expanded:
                continue
            m = STATUS_ID_RE.search(expanded)
            if not m:
                continue

            status_id = m.group(1)
            url_only_ids.add(status_id)

            # Map status_id (tweet) -> thread root (if ≥4-tweet thread exists)
            thread_id = tweet_to_thread.get(status_id)
            if not thread_id:
                continue

            thread = threads_by_id.get(thread_id)
            if not thread:
                continue

            tweets = thread.get("tweets", [])
            if not tweets:
                continue

            # earliest tweet in thread
            def sort_key(t0):
                ts0 = t0.get("created_at")
                dt0 = parse_created_at(ts0)
                return dt0 or ts0 or ""

            tweets_sorted = sorted(tweets, key=sort_key)
            root_tweet = tweets_sorted[0]
            root_text = (root_tweet.get("full_text") or "").replace("\n", " ")
            if len(root_text) > 140:
                root_text = root_text[:137] + "..."

            referenced_thread_roots[thread_id] = {
                "quoted_like_tweet_id": status_id,
                "root_tweet_id": root_tweet.get("id_str"),
                "root_text": root_text,
            }

    # 5) Report
    print()
    print(f"Distinct status IDs extracted from URLs: {len(url_only_ids)}")
    print(f"Quoted-like threads that resolve to your ≥4-tweet threads: {len(referenced_thread_roots)}")
    print(f"Tweets in thread-of-threads with no URLs: {no_urls}")
    print()

    for i, (thread_id, info) in enumerate(sorted(referenced_thread_roots.items()), start=1):
        print(f"{i:3d}. thread_id={thread_id} via status_id={info['quoted_like_tweet_id']}")
        print(f"     root_tweet_id={info['root_tweet_id']}")
        print(f"     text: {info['root_text']}")
        print()


if __name__ == "__main__":
    main()
