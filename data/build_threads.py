#!/usr/bin/env python3
import json
from collections import defaultdict
from datetime import datetime

TWEETS_PATH = "tweets_normalized.jsonl"
THREADS_INDEX_CSV = "threads_index.csv"
THREADS_DATA_JSONL = "threads_data.jsonl"

# Only threads with at least this many tweets are emitted
MIN_THREAD_LENGTH = 4


def iter_tweets(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def parse_created_at(ts):
    """
    Twitter exports use ISO-like format, e.g. '2022-12-10T00:53:56.000Z'.
    """
    if ts is None:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def main():
    print(f"Loading tweets from {TWEETS_PATH} ...")

    tweets_by_id = {}
    reply_parent = {}          # tid -> in_reply_to_status_id_str
    created_at_map = {}

    # First pass: load tweets and build reply map
    for obj in iter_tweets(TWEETS_PATH):
        tid = obj.get("id_str")
        if not tid:
            continue
        tweets_by_id[tid] = obj

        parent_id = obj.get("in_reply_to_status_id_str")
        if parent_id:
            reply_parent[tid] = parent_id

        created_at_map[tid] = obj.get("created_at")

    print(f"Loaded {len(tweets_by_id)} tweets")

    # Second pass: build a map of "quote parents" for broken threads
    # tid -> quoted tweet id (only when quoted tweet exists in your archive)
    quote_parent = {}
    for tid, obj in tweets_by_id.items():
        raw = obj.get("raw") or {}

        quoted = raw.get("quoted_status")
        q_id = None

        if quoted:
            q_id = quoted.get("id_str") or quoted.get("id")
            if q_id is not None:
                q_id = str(q_id)
        else:
            q_id = raw.get("quoted_status_id_str")
            if q_id is not None:
                q_id = str(q_id)

        # Only treat as a "quote parent" if quoted tweet exists in your archive
        if q_id and q_id in tweets_by_id:
            quote_parent[tid] = q_id

    print(f"Detected {len(quote_parent)} quote links to tweets in your archive")

    # Root finding with reply chain first, then self-quote-like linking
    root_cache = {}

    def find_root(tid):
        if tid in root_cache:
            return root_cache[tid]

        seen = set()
        current_id = tid

        while True:
            if current_id in seen:
                # Cycle (should not happen) – break
                break
            seen.add(current_id)

            parent_id = None

            # 1) Prefer normal reply parent if it exists in your archive
            candidate = reply_parent.get(current_id)
            if candidate and candidate in tweets_by_id:
                parent_id = candidate

            # 2) If no reply parent, try quote parent
            if parent_id is None:
                candidate = quote_parent.get(current_id)
                if candidate and candidate in tweets_by_id:
                    parent_id = candidate

            if not parent_id:
                break

            current_id = parent_id

        root_cache[tid] = current_id
        return current_id

    # Group tweets by root id (threads)
    threads = defaultdict(list)
    for tid, obj in tweets_by_id.items():
        root_id = find_root(tid)
        threads[root_id].append(obj)

    print(f"Identified {len(threads)} threads (including singletons)")

    # Write outputs
    print(f"Writing {THREADS_INDEX_CSV} and {THREADS_DATA_JSONL} ...")

    with open(THREADS_INDEX_CSV, "w", encoding="utf-8") as index_f, \
         open(THREADS_DATA_JSONL, "w", encoding="utf-8") as data_f:

        index_f.write(
            "thread_id,root_id,start_created_at,num_tweets,"
            "max_favorites,max_retweets,has_external_dependency,"
            "has_external_reply,has_external_quote,sample_text\n"
        )

        for root_id, tweets in threads.items():
            # Sort by created_at
            def sort_key(t):
                ts = t.get("created_at")
                dt = parse_created_at(ts)
                return dt or ts or ""

            tweets_sorted = sorted(tweets, key=sort_key)
            num = len(tweets_sorted)

            # Enforce minimum thread length
            if num < MIN_THREAD_LENGTH:
                continue

            favs = [t.get("favorite_count", 0) or 0 for t in tweets_sorted]
            rts = [t.get("retweet_count", 0) or 0 for t in tweets_sorted]
            max_fav = max(favs) if favs else 0
            max_rt = max(rts) if rts else 0

            root_tweet = tweets_by_id[root_id]
            start_created_at = root_tweet.get("created_at")

            # External dependency flags
            has_external_reply = False
            has_external_quote = False

            for t in tweets_sorted:
                # External reply: replying to a tweet not in your archive
                reply_id = t.get("in_reply_to_status_id_str")
                if reply_id and reply_id not in tweets_by_id:
                    has_external_reply = True

                # External quote: quoting a tweet not in your archive
                raw_t = t.get("raw") or {}
                quoted = raw_t.get("quoted_status")
                q_id = None
                if quoted:
                    q_id = quoted.get("id_str") or quoted.get("id")
                    if q_id is not None:
                        q_id = str(q_id)
                else:
                    q_id = raw_t.get("quoted_status_id_str")
                    if q_id is not None:
                        q_id = str(q_id)

                if q_id and q_id not in tweets_by_id:
                    has_external_quote = True

            has_external_dep = has_external_reply or has_external_quote

            sample_text = (root_tweet.get("full_text") or "").replace("\n", " ")
            sample_text = sample_text.replace(",", " ")
            if len(sample_text) > 120:
                sample_text = sample_text[:117] + "..."

            # CSV row
            index_f.write(
                f"{root_id},{root_id},{start_created_at},{num},"
                f"{max_fav},{max_rt},"
                f"{int(has_external_dep)},{int(has_external_reply)},"
                f"{int(has_external_quote)},{sample_text}\n"
            )

            # JSONL thread record
            thread_record = {
                "thread_id": root_id,
                "root_id": root_id,
                "start_created_at": start_created_at,
                "num_tweets": num,
                "max_favorites": max_fav,
                "max_retweets": max_rt,
                "has_external_dependency": has_external_dep,
                "has_external_reply": has_external_reply,
                "has_external_quote": has_external_quote,
                "tweets": [
                    {
                        "id_str": t.get("id_str"),
                        "created_at": t.get("created_at"),
                        "full_text": t.get("full_text"),
                        "favorite_count": t.get("favorite_count", 0),
                        "retweet_count": t.get("retweet_count", 0),
                        "in_reply_to_status_id_str": t.get("in_reply_to_status_id_str"),
                        "in_reply_to_user_id_str": t.get("in_reply_to_user_id_str"),
                    }
                    for t in tweets_sorted
                ],
            }
            data_f.write(json.dumps(thread_record, ensure_ascii=False) + "\n")

    print("Done.")


if __name__ == "__main__":
    main()
