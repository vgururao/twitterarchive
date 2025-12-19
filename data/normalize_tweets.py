#!/usr/bin/env python3
import json
import glob
import os
import re

# Adjust this if you want the output elsewhere
OUTPUT_PATH = "tweets_normalized.jsonl"

def load_tweet_objects_from_js(path):
    """
    Given a Twitter archive tweets.js / tweets-partX.js file,
    strip the 'window.YTD.tweets.partN = ' wrapper and yield
    the inner .tweet objects.
    """
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find first '[' and last ']' to extract the JSON array safely
    start = content.find('[')
    end = content.rfind(']')

    if start == -1 or end == -1:
        raise ValueError(f"Could not find JSON array brackets in {path}")

    json_text = content[start:end + 1]

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON decode error in {path}: {e}") from e

    for entry in data:
        tweet = entry.get("tweet", {})
        if tweet:
            yield tweet


def normalize_tweet(tweet):
    """
    Extract the fields we care about and normalize types.
    This is robust to missing keys.
    """
    # Some exports use 'full_text', some 'text'
    full_text = tweet.get("full_text") or tweet.get("text") or ""

    # Created_at should already be an ISO-ish datetime string
    created_at = tweet.get("created_at")

    # Counts are often strings in the export; normalize to int
    def to_int(x):
        try:
            return int(x)
        except (TypeError, ValueError):
            return 0

    favorite_count = to_int(tweet.get("favorite_count"))
    retweet_count = to_int(tweet.get("retweet_count"))

    # Basic relational fields
    in_reply_to_status_id_str = tweet.get("in_reply_to_status_id_str")
    in_reply_to_user_id_str = tweet.get("in_reply_to_user_id_str")

    # Conversation id (may or may not be present depending on export)
    conv_id = (
        tweet.get("conversation_id_str")
        or str(tweet.get("conversation_id"))
        if tweet.get("conversation_id") is not None
        else None
    )

    # Retweet / quote flags
    is_retweet = bool(tweet.get("retweeted") or tweet.get("retweeted_status"))
    is_quote_status = bool(tweet.get("is_quote_status"))

    return {
        "id_str": tweet.get("id_str") or str(tweet.get("id")),
        "created_at": created_at,
        "full_text": full_text,
        "in_reply_to_status_id_str": in_reply_to_status_id_str,
        "in_reply_to_user_id_str": in_reply_to_user_id_str,
        "favorite_count": favorite_count,
        "retweet_count": retweet_count,
        "is_retweet": is_retweet,
        "is_quote_status": is_quote_status,
        "conversation_id_str": conv_id,
        # Keep original raw tweet if you want to debug later
        "raw": tweet,
    }


def main():
    js_files = sorted(glob.glob("tweets*.js"))
    if not js_files:
        raise SystemExit("No tweets*.js files found in current directory")

    print("Found tweet files:")
    for p in js_files:
        print("  -", p)

    out_count = 0
    with open(OUTPUT_PATH, "w", encoding="utf-8") as out_f:
        for path in js_files:
            print(f"Processing {path} ...")
            for tweet in load_tweet_objects_from_js(path):
                norm = normalize_tweet(tweet)
                # Skip if somehow id_str missing (shouldn't happen)
                if not norm["id_str"]:
                    continue
                out_f.write(json.dumps(norm, ensure_ascii=False) + "\n")
                out_count += 1

    print(f"Done. Wrote {out_count} tweets to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
