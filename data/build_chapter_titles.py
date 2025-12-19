#!/usr/bin/env python3
import argparse, json, re
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

STATUS_URL_RE = re.compile(r"https?://(?:x|twitter)\.com/[^/]+/status/(\d+)")
TITLE_RE = re.compile(r"^\s*\d+[\.\)]\s*(.+?)\s*$")  # allow "1." or "1)"

def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)

def parse_dt(s):
    if not s:
        return None
    s = str(s).strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    try:
        dt = parsedate_to_datetime(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def normalize_title_from_meta(text):
    if not text:
        return None
    first = text.strip().splitlines()[0].strip()
    m = TITLE_RE.match(first)
    return m.group(1).strip() if m else None

def extract_status_ids(text):
    return [str(x) for x in STATUS_URL_RE.findall(text or "")]

def extract_status_ids_from_raw(raw):
    ids = []
    urls = (raw.get("entities") or {}).get("urls") or []
    for u in urls:
        expanded = u.get("expanded_url") or u.get("url") or ""
        ids.extend(STATUS_URL_RE.findall(expanded))
    return [str(x) for x in ids]

def load_tweets_normalized(path: Path):
    out = {}
    for obj in iter_jsonl(path):
        tid = obj.get("id_str")
        if tid:
            out[str(tid)] = obj
    return out

def load_threads(path: Path):
    out = {}
    for obj in iter_jsonl(path):
        tid = obj.get("thread_id") or obj.get("id")
        if tid:
            out[str(tid)] = obj
    return out

def crawl_meta_tree(tweets_by_id, root_id):
    root = tweets_by_id.get(root_id)
    if not root:
        raise SystemExit(f"Meta root tweet {root_id} not found")

    raw_root = root.get("raw") or {}
    author_id = raw_root.get("user_id_str") or (raw_root.get("user") or {}).get("id_str")

    # parent -> children (self replies only)
    children = defaultdict(list)
    for tid, rec in tweets_by_id.items():
        raw = rec.get("raw") or {}
        parent = raw.get("in_reply_to_status_id_str") or raw.get("in_reply_to_status_id")
        if not parent:
            continue
        uid = raw.get("user_id_str") or (raw.get("user") or {}).get("id_str")
        if author_id and uid and uid != author_id:
            continue
        children[str(parent)].append(str(tid))

    # DFS all reachable tweets from root
    seen = set()
    stack = [str(root_id)]
    out = []
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        rec = tweets_by_id.get(cur)
        if rec:
            out.append(rec)
            # push children
            for kid in children.get(cur, []):
                if kid not in seen:
                    stack.append(kid)

    # sort output chronologically for stable processing
    def key(rec):
        raw = rec.get("raw") or {}
        dt = parse_dt(rec.get("created_at") or raw.get("created_at") or "")
        return (dt or datetime.min.replace(tzinfo=timezone.utc), rec.get("id_str") or "")
    out.sort(key=key)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", default="data/threads_data_ops_patched.jsonl")
    ap.add_argument("--selection", default="data/selection_final_clean.json")
    ap.add_argument("--tweets", default="data/tweets_normalized.jsonl")
    ap.add_argument("--meta-root-id", default="1279451428302422016")
    ap.add_argument("--out", default="data/chapter_titles.json")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    threads = load_threads(root / args.threads)
    selection = json.loads((root / args.selection).read_text(encoding="utf-8"))
    tweets_by_id = load_tweets_normalized(root / args.tweets)

    if not (isinstance(selection, dict) and isinstance(selection.get("chapter_threads"), list)):
        raise SystemExit("Expected selection['chapter_threads'] to be a list")
    ordered_thread_ids = [str(x) for x in selection["chapter_threads"]]

    # Gather chapter root tweet ids (used to pick the correct link when meta tweet has many)
    chapter_root_ids = set()
    for thread_id in ordered_thread_ids:
        th = threads.get(thread_id)
        if th and th.get("tweets") and th["tweets"][0].get("id_str"):
            chapter_root_ids.add(str(th["tweets"][0]["id_str"]))

    meta_recs = crawl_meta_tree(tweets_by_id, str(args.meta_root_id))

    overrides = {}  # root_tweet_id -> title

    for rec in meta_recs:
        raw = rec.get("raw") or {}
        text = rec.get("full_text") or raw.get("full_text") or ""
        title = normalize_title_from_meta(text)
        if not title:
            continue

        ids = []
        ids.extend(extract_status_ids(text))
        ids.extend(extract_status_ids_from_raw(raw))

        # Pick the first link that matches a known chapter root id (most robust)
        picked = None
        for sid in ids:
            if sid in chapter_root_ids:
                picked = sid
                break
        # If none match, fall back to the first link (still useful for manual inspection)
        if not picked and ids:
            picked = ids[0]

        if picked:
            overrides[picked] = title

    out = {
        "meta_root_id": str(args.meta_root_id),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chapters": []
    }

    for thread_id in ordered_thread_ids:
        th = threads.get(thread_id)
        if not th or not th.get("tweets"):
            out["chapters"].append({
                "thread_id": thread_id,
                "root_tweet_id": None,
                "current_title": None,
                "override_title": None,
                "source": "missing_thread_record"
            })
            continue

        root_tweet = th["tweets"][0]
        root_id = str(root_tweet.get("id_str") or "")
        root_text = (root_tweet.get("full_text") or "").replace("\n", " ").strip()
        current_title = root_text[:140] + ("…" if len(root_text) > 140 else "")
        override = overrides.get(root_id)

        out["chapters"].append({
            "thread_id": str(thread_id),
            "root_tweet_id": root_id or None,
            "current_title": current_title if current_title else None,
            "override_title": override if override else current_title,
            "source": "meta_thread" if override else "current_root_snippet"
        })

    (root / args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    hits = sum(1 for c in out["chapters"] if c.get("source") == "meta_thread")
    print(f"Wrote {args.out} — meta-thread hits: {hits}/{len(out['chapters'])}")
    print(f"Meta tweets scanned (reachable self-replies): {len(meta_recs)}")
    print(f"Unique overrides extracted: {len(overrides)}")

if __name__ == "__main__":
    main()
