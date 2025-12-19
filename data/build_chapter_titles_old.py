#!/usr/bin/env python3
'''
Build chapter title overrides from:
- data/threads_data_ops_patched.jsonl (thread -> tweets[])
- data/selection_final_clean.json (which threads are in the book + order)
- data/tweets_normalized.jsonl (to crawl the 'thread of threads' meta-thread)

Meta-thread:
- starts at tweet id given by --meta-root-id
- we crawl replies by the same author, following in_reply_to_status_id(_str)

For meta-thread tweets, we extract:
- a human title like "1. Boundary Intelligence" -> "Boundary Intelligence"
- referenced root tweet ids via status URLs (twitter.com/.../status/<id> or x.com)

Then we map thread root tweet ids -> override title.

Output:
- data/chapter_titles.json : list of chapter records with
  {thread_id, root_tweet_id, current_title, override_title, source}
'''

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

STATUS_URL_RE = re.compile(r"https?://(?:x|twitter)\.com/[^/]+/status/(\d+)")
TITLE_RE = re.compile(r"^\s*\d+\.\s*(.+?)\s*$")

def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)

def parse_dt(s: str):
    if not s:
        return None
    s = str(s).strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

def normalize_title_from_meta(text: str):
    if not text:
        return None
    first_line = text.strip().splitlines()[0].strip()
    m = TITLE_RE.match(first_line)
    if not m:
        return None
    return m.group(1).strip()

def extract_status_ids(text: str):
    if not text:
        return []
    return STATUS_URL_RE.findall(text)

def extract_status_ids_from_raw(raw: dict):
    ids = []
    entities = (raw or {}).get("entities") or {}
    urls = entities.get("urls") or []
    for u in urls:
        expanded = u.get("expanded_url") or u.get("url") or ""
        ids.extend(STATUS_URL_RE.findall(expanded))
    return ids

def crawl_meta_thread(tweets_by_id: dict, meta_root_id: str):
    root = tweets_by_id.get(meta_root_id)
    if not root:
        raise SystemExit(f"Meta root tweet id {meta_root_id} not found in tweets file.")

    raw_root = root.get("raw") or {}
    author_id = raw_root.get("user_id_str") or (raw_root.get("user", {}) or {}).get("id_str")

    replies = defaultdict(list)
    for tid, rec in tweets_by_id.items():
        raw = rec.get("raw") or {}
        in_reply = raw.get("in_reply_to_status_id_str") or raw.get("in_reply_to_status_id")
        if not in_reply:
            continue
        uid = raw.get("user_id_str") or (raw.get("user", {}) or {}).get("id_str")
        if author_id and uid and uid != author_id:
            continue
        replies[str(in_reply)].append(str(tid))

    def sort_children(child_ids):
        def key(tid):
            rec = tweets_by_id.get(tid) or {}
            raw = rec.get("raw") or {}
            dt = parse_dt(rec.get("created_at") or raw.get("created_at") or "")
            return (dt or datetime.min.replace(tzinfo=timezone.utc), tid)
        return sorted(child_ids, key=key)

    chain = []
    cur = str(meta_root_id)
    seen = set()
    while cur and cur not in seen:
        seen.add(cur)
        rec = tweets_by_id.get(cur)
        if not rec:
            break
        chain.append(rec)
        kids = sort_children(replies.get(cur, []))
        if not kids:
            break
        cur = kids[0]
    return chain

def load_tweets_normalized(path: Path):
    tweets_by_id = {}
    for obj in iter_jsonl(path):
        tid = obj.get("id_str")
        if tid:
            tweets_by_id[str(tid)] = obj
    return tweets_by_id

def load_threads(path: Path):
    threads_by_id = {}
    for obj in iter_jsonl(path):
        tid = obj.get("thread_id") or obj.get("id") or obj.get("threadId")
        if tid:
            threads_by_id[str(tid)] = obj
    return threads_by_id

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", default="data/threads_data_ops_patched.jsonl")
    ap.add_argument("--selection", default="data/selection_final_clean.json")
    ap.add_argument("--tweets", default="data/tweets_normalized.jsonl")
    ap.add_argument("--meta-root-id", default="1279451428302422016")
    ap.add_argument("--out", default="data/chapter_titles.json")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent

    threads_path = root / args.threads
    selection_path = root / args.selection
    tweets_path = root / args.tweets
    out_path = root / args.out

    if not threads_path.exists():
        raise SystemExit(f"Missing threads file: {threads_path}")
    if not selection_path.exists():
        raise SystemExit(f"Missing selection file: {selection_path}")
    if not tweets_path.exists():
        raise SystemExit(f"Missing tweets file: {tweets_path}")

    threads = load_threads(threads_path)
    selection = json.loads(selection_path.read_text(encoding="utf-8"))

    ordered_thread_ids = []
    if isinstance(selection, dict) and "threads" in selection:
        ordered_thread_ids = [str(x) for x in selection["threads"]]
    elif isinstance(selection, list):
        ordered_thread_ids = [str(x) for x in selection]
    else:
        for k in ("selected_threads", "thread_ids", "items"):
            if isinstance(selection, dict) and k in selection:
                ordered_thread_ids = [str(x) for x in selection[k]]
                break
    if not ordered_thread_ids:
        raise SystemExit("Couldn't find ordered thread ids in selection_final_clean.json (expected list or {threads:[...]}).")

    tweets_by_id = load_tweets_normalized(tweets_path)

    meta_chain = crawl_meta_thread(tweets_by_id, str(args.meta_root_id))
    overrides_by_root_tweet = {}

    for rec in meta_chain:
        raw = rec.get("raw") or {}
        text = rec.get("full_text") or raw.get("full_text") or ""
        title = normalize_title_from_meta(text)
        if not title:
            continue
        ids = []
        ids.extend(extract_status_ids(text))
        ids.extend(extract_status_ids_from_raw(raw))
        ids = [str(x) for x in ids]
        if not ids:
            continue
        overrides_by_root_tweet[ids[0]] = title

    out = {
        "meta_root_id": str(args.meta_root_id),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chapters": []
    }

    for thread_id in ordered_thread_ids:
        th = threads.get(thread_id)
        if not th:
            out["chapters"].append({
                "thread_id": thread_id,
                "root_tweet_id": None,
                "current_title": None,
                "override_title": None,
                "source": "missing_thread_record"
            })
            continue

        tweets = th.get("tweets") or []
        root_tweet_id = str(tweets[0].get("id_str")) if tweets and tweets[0].get("id_str") else None
        root_text = (tweets[0].get("full_text") or "").replace("\n", " ").strip() if tweets else ""
        current_title = (root_text[:140] + ("..." if len(root_text) > 140 else "")) if root_text else f"Thread {thread_id}"

        override = overrides_by_root_tweet.get(root_tweet_id)
        if override:
            override_title = override
            source = "meta_thread"
        else:
            override_title = current_title
            source = "current_root_snippet"

        out["chapters"].append({
            "thread_id": thread_id,
            "root_tweet_id": root_tweet_id,
            "current_title": current_title,
            "override_title": override_title,
            "source": source
        })

    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote chapter titles file: {out_path}")
    meta_hits = sum(1 for c in out["chapters"] if c.get("source") == "meta_thread")
    print(f"Meta-thread title hits: {meta_hits} / {len(out['chapters'])}")

if __name__ == "__main__":
    main()
