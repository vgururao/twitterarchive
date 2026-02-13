import json
import shutil
from pathlib import Path
from collections import defaultdict

HERE = Path(__file__).resolve().parent        # .../twitterarchive/data
ROOT = HERE.parent                             # .../twitterarchive

THREADS_FILE   = HERE / "threads_data_ops_patched.jsonl"
TWEETS_FILE    = HERE / "tweets_normalized.jsonl"
SELECTION_FILE = HERE / "selection_final_clean.json"
OUT_DIR        = ROOT / "book" / "assets" / "media"

MEDIA_DIRS = [
    ROOT / "data" / "tweets_media",
    ROOT / "data" / "twitter_circle_tweet_media",
    ROOT / "data" / "profile_media",
]

def iter_jsonl(p: Path):
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)

def get_media(raw: dict):
    ee = raw.get("extended_entities") or {}
    if ee.get("media"):
        return ee["media"]
    en = raw.get("entities") or {}
    return en.get("media") or []

def basename_from_media(m: dict):
    url = m.get("media_url_https") or m.get("media_url") or ""
    return url.split("/")[-1] if url else ""

def build_media_index():
    """
    Map pbs_basename.ext -> list of local file paths like:
    1170947508337434624-EEAKjMdUUAAXU9d.jpg
                     ^ split at first '-'
    """
    idx = defaultdict(list)
    scanned = 0
    for d in MEDIA_DIRS:
        if not d.exists():
            continue
        for p in d.iterdir():
            if not p.is_file():
                continue
            name = p.name
            if "-" not in name:
                continue
            _, tail = name.split("-", 1)
            idx[tail].append(p)
            scanned += 1

    # deterministic ordering
    for k in list(idx.keys()):
        idx[k] = sorted(idx[k], key=lambda x: str(x))
    return idx, scanned

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load tweets
    tweets_by_id = {}
    for t in iter_jsonl(TWEETS_FILE):
        tid = t.get("id_str")
        if tid:
            tweets_by_id[tid] = t

    # Load selection
    sel = json.loads(SELECTION_FILE.read_text(encoding="utf-8"))
    selected_threads = set(sel.get("chapter_threads", []))
    compendium_tweets = set(sel.get("compendium_tweets", []))

    # Build needed basenames from selected chapter threads
    needed = set()
    for th in iter_jsonl(THREADS_FILE):
        if str(th.get("thread_id")) not in selected_threads:
            continue
        for tw in th.get("tweets", []):
            tid = tw.get("id_str")
            full = tweets_by_id.get(tid) or {}
            raw = full.get("raw") or {}
            if not isinstance(raw, dict):
                continue
            for m in get_media(raw):
                base = basename_from_media(m)
                if base:
                    needed.add(base)

    # Also include media from compendium singleton tweets
    for ctid in compendium_tweets:
        full = tweets_by_id.get(ctid) or {}
        raw = full.get("raw") or {}
        if not isinstance(raw, dict):
            continue
        for m in get_media(raw):
            base = basename_from_media(m)
            if base:
                needed.add(base)

    idx, scanned = build_media_index()
    print("Media files scanned:", scanned)
    print("Needed basenames:", len(needed))
    print("Index keys:", len(idx))

    copied = 0
    missing = 0

    for base in sorted(needed):
        paths = idx.get(base)
        if not paths:
            missing += 1
            continue

        # Copy ALL matches (rare duplicates), deterministic
        for src in paths:
            dst = OUT_DIR / base
            if not dst.exists():
                shutil.copy2(src, dst)
                copied += 1

    print("Copied files:", copied)
    print("Missing basenames:", missing)
    print("Output:", OUT_DIR)

if __name__ == "__main__":
    main()
