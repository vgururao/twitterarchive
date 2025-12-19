#!/usr/bin/env python3
import json
import re
from datetime import datetime

SELECTION_IN = "selection.json"
THREADS_DATA = "threads_data.jsonl"
TWEETS_DATA = "tweets_normalized.jsonl"
SELECTION_OUT_JSON = "selection_longlist.json"
SELECTION_OUT_MD = "selection_longlist.md"

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
    # --- Load initial selection ---
    with open(SELECTION_IN, "r", encoding="utf-8") as f:
        sel = json.load(f)

    initial_chapter_threads = set(sel.get("chapter_threads", []))
    compendium_tweets = set(sel.get("compendium_tweets", []))

    print(f"Initial chapter_threads: {len(initial_chapter_threads)}")
    print(f"Initial compendium_tweets: {len(compendium_tweets)}")

    # --- Load threads and build tweet_id -> thread_id map ---
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

    # --- Ensure the thread-of-threads exists as a thread (>=4 tweets) ---
    thread_of_threads = threads_by_id.get(THREAD_OF_THREADS_ID)
    if not thread_of_threads:
        raise SystemExit(
            f"Thread-of-threads {THREAD_OF_THREADS_ID} not found in {THREADS_DATA}"
        )

    tot_tweet_ids = []
    for tw in thread_of_threads.get("tweets", []):
        tid = tw.get("id_str")
        if tid:
            tot_tweet_ids.append(tid)

    print(f"Thread-of-threads contains {len(tot_tweet_ids)} tweets")

    # --- Load full tweet objects for those ids (to access raw.entities.urls) ---
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

    # --- Extract status IDs from expanded_url in entities.urls ---
    referenced_status_ids = set()
    referenced_thread_ids = set()
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
            referenced_status_ids.add(status_id)

            # Map tweet ID to thread ID if it belongs to one of your >=4-tweet threads
            thread_id = tweet_to_thread.get(status_id)
            if thread_id and thread_id in threads_by_id:
                referenced_thread_ids.add(thread_id)

    print()
    print(f"Distinct status IDs extracted from URLs in TOT: {len(referenced_status_ids)}")
    print(f"Those that resolve to your ≥4-tweet threads: {len(referenced_thread_ids)}")
    print(f"TOT tweets with no URLs: {no_urls}")
    print()

    # --- Build merged chapter_threads longlist ---
    merged_chapter_threads = sorted(
        initial_chapter_threads.union(referenced_thread_ids)
    )

    print(f"Merged chapter_threads longlist size: {len(merged_chapter_threads)}")

    # --- Write JSON selection_longlist.json ---
    metadata = {
        "source_selection": SELECTION_IN,
        "thread_of_threads": THREAD_OF_THREADS_ID,
        "initial_chapter_threads_count": len(initial_chapter_threads),
        "tot_referenced_status_ids_count": len(referenced_status_ids),
        "tot_resolved_threads_count": len(referenced_thread_ids),
        "added_from_thread_of_threads": sorted(
            referenced_thread_ids - initial_chapter_threads
        ),
    }

    selection_out = {
        "chapter_threads": merged_chapter_threads,
        "compendium_tweets": sorted(compendium_tweets),
        "metadata": metadata,
    }

    with open(SELECTION_OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(selection_out, f, ensure_ascii=False, indent=2)

    print(f"Wrote merged selection longlist to {SELECTION_OUT_JSON}")

    # --- Build markdown overview for review: selection_longlist.md ---
    # For convenience, gather per-thread summary stats from threads_by_id
    rows = []

    for tid in merged_chapter_threads:
        thread = threads_by_id.get(tid)
        if not thread:
            continue

        num = thread.get("num_tweets", len(thread.get("tweets", [])))
        max_fav = thread.get("max_favorites", 0)
        max_rt = thread.get("max_retweets", 0)
        start_created_at = thread.get("start_created_at")

        has_ext_dep = thread.get("has_external_dependency", False)
        has_ext_reply = thread.get("has_external_reply", False)
        has_ext_quote = thread.get("has_external_quote", False)

        tweets = thread.get("tweets", [])
        if tweets:
            # first tweet text
            first_text = (tweets[0].get("full_text") or "").replace("\n", " ")
        else:
            first_text = ""

        if len(first_text) > 140:
            first_text = first_text[:137] + "..."

        rows.append({
            "thread_id": tid,
            "num_tweets": num,
            "start_created_at": start_created_at,
            "max_favorites": max_fav,
            "max_retweets": max_rt,
            "has_external_dependency": has_ext_dep,
            "has_external_reply": has_ext_reply,
            "has_external_quote": has_ext_quote,
            "sample_text": first_text,
        })

    # Sort rows by start_created_at (oldest first), falling back to thread_id
    def sort_key(row):
        dt = parse_created_at(row["start_created_at"])
        return (dt or row["start_created_at"] or "", row["thread_id"])

    rows_sorted = sorted(rows, key=sort_key)

    with open(SELECTION_OUT_MD, "w", encoding="utf-8") as f:
        f.write("# Longlist of Candidate Threads\n\n")
        f.write(f"- Total merged chapter threads: **{len(merged_chapter_threads)}**\n")
        f.write(f"- From initial manual selection: **{len(initial_chapter_threads)}**\n")
        f.write(f"- Added via thread-of-threads URLs (≥4-tweet threads): **{len(referenced_thread_ids - initial_chapter_threads)}**\n\n")

        f.write("| # | thread_id | start_created_at | num_tweets | max_fav | max_rt | external? | sample_text |\n")
        f.write("|---|-----------|------------------|-----------:|--------:|-------:|-----------|-------------|\n")

        for idx, row in enumerate(rows_sorted, start=1):
            ext_flags = []
            if row["has_external_dependency"]:
                ext_flags.append("dep")
            if row["has_external_reply"]:
                ext_flags.append("reply")
            if row["has_external_quote"]:
                ext_flags.append("quote")
            ext_str = ", ".join(ext_flags) if ext_flags else ""

            # Escape pipes in text just in case
            sample = row["sample_text"].replace("|", "\\|")

            f.write(
                f"| {idx} | {row['thread_id']} | {row['start_created_at'] or ''} | "
                f"{row['num_tweets']} | {row['max_favorites']} | {row['max_retweets']} | "
                f"{ext_str} | {sample} |\n"
            )

    print(f"Wrote markdown overview to {SELECTION_OUT_MD}")


if __name__ == "__main__":
    main()
