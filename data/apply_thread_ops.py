#!/usr/bin/env python3
import json
from pathlib import Path
from collections import defaultdict

# IN_THREADS = Path("threads_data.jsonl")
IN_THREADS = Path("threads_data_patched.jsonl")
IN_TWEETS = Path("tweets_normalized.jsonl")  # fallback source of truth
OPS_PATH = Path("thread_ops.json")
OUT_THREADS = Path("threads_data_ops_patched.jsonl")


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: Path, objs):
    with path.open("w", encoding="utf-8") as f:
        for obj in objs:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def load_ops(path: Path):
    ops = json.loads(path.read_text(encoding="utf-8"))
    ops.setdefault("drops", [])
    ops.setdefault("merges", [])
    ops.setdefault("append_by_url", [])
    ops.setdefault("validate_roots", [])
    return ops


def is_likely_true_root(thread_obj) -> bool:
    tweets = thread_obj.get("tweets") or []
    if not tweets:
        return True
    first = tweets[0]
    parent = first.get("in_reply_to_status_id_str")
    return not (isinstance(parent, str) and parent.isdigit())


def merge_threads(into_thread, from_tweets, from_id_for_provenance=None):
    into_ids = {t.get("id_str") for t in (into_thread.get("tweets") or [])}
    deduped = [t for t in from_tweets if t.get("id_str") not in into_ids]
    into_thread["tweets"] = (into_thread.get("tweets") or []) + deduped
    into_thread["num_tweets"] = len(into_thread["tweets"])
    if from_id_for_provenance:
        into_thread.setdefault("merged_from", [])
        into_thread["merged_from"].append(from_id_for_provenance)
    return into_thread


def load_needed_tweets(ids_needed: set[str]):
    """
    Load only tweets we need and any that reference them in_reply_to,
    but simplest + safe is load all tweets (153k) which is fine.
    We'll load all to enable reconstruction traversals.
    """
    tweets_by_id = {}
    children = defaultdict(list)

    for tw in iter_jsonl(IN_TWEETS):
        tid = tw.get("id_str")
        if not tid:
            continue
        tweets_by_id[tid] = tw
        parent = tw.get("in_reply_to_status_id_str")
        if parent:
            children[parent].append(tid)

    # sort children by created_at so traversal is deterministic
    def created_key(tid):
        t = tweets_by_id.get(tid) or {}
        return t.get("created_at") or ""

    for parent, kids in children.items():
        kids.sort(key=created_key)

    return tweets_by_id, children


def reconstruct_chain_from_root(root_id: str, tweets_by_id, children_map):
    """
    Reconstruct a linear thread chain starting from root_id by repeatedly choosing
    the earliest child reply (by created_at). This matches typical posting order.
    If branching occurs, we follow the mainline (first child) only.
    """
    if root_id not in tweets_by_id:
        return []

    chain = []
    cur = root_id
    visited = set()

    while cur and cur not in visited:
        visited.add(cur)
        chain.append(tweets_by_id[cur])
        kids = children_map.get(cur, [])
        if not kids:
            break
        # follow the earliest reply as "next"
        cur = kids[0]

    return chain

def main():
    ops = load_ops(OPS_PATH)

    drops = set(ops["drops"])
    merges = list(ops["merges"])
    appends = list(ops["append_by_url"])
    validate = {v["root"]: v for v in ops["validate_roots"]}

    # ---- load indexed threads ----
    threads_by_id = {}
    order = []
    tweet_to_thread = {}

    for th in iter_jsonl(IN_THREADS):
        tid = th.get("thread_id")
        if not tid:
            continue
        threads_by_id[tid] = th
        order.append(tid)
        for t in th.get("tweets", []):
            twid = t.get("id_str")
            if twid:
                tweet_to_thread[twid] = tid

    print(f"Loaded {len(threads_by_id)} threads from {IN_THREADS}")
    print(f"Indexed {len(tweet_to_thread)} tweet->thread mappings")

    # ---- load full tweet universe for reconstruction ----
    print(f"Loading tweets from {IN_TWEETS} for reconstruction fallback ...")
    tweets_by_id, children = load_needed_tweets(set())
    print(f"Loaded {len(tweets_by_id)} tweets; built reply index for {len(children)} parents")

    # ---- validate roots ----
    for root_id, rule in validate.items():
        th = threads_by_id.get(root_id)
        if not th:
            continue
        if rule.get("action_if_missing_parent") == "drop":
            if not is_likely_true_root(th):
                drops.add(root_id)
                print(f"Validate: dropping {root_id} (looks like mid-thread root)")

    merged_from_ids = set()

    # ---- apply true merges (thread -> thread) ----
    for m in merges:
        into_root = m["into_root"]
        from_root = m["from_root"]

        if into_root in drops or from_root in drops:
            continue

        into_th = threads_by_id.get(into_root)
        if not into_th:
            print(f"Merge error: into_root not found: {into_root}")
            continue

        # resolve from_root via tweet_to_thread
        resolved_root = from_root
        if from_root not in threads_by_id:
            mapped = tweet_to_thread.get(from_root)
            if mapped:
                resolved_root = mapped

        if resolved_root == into_root:
            print(f"Merge skipped: self-merge {into_root}")
            continue

        from_th = threads_by_id.get(resolved_root)
        if not from_th:
            print(f"Merge error: from_root not found as thread: {from_root}")
            continue

        threads_by_id[into_root] = merge_threads(
            into_th,
            from_th.get("tweets", []),
            from_id_for_provenance=resolved_root
        )
        merged_from_ids.add(resolved_root)
        print(f"Merged {resolved_root} -> {into_root}")

    # ---- append-by-chain (tweet-id continuation) ----
    for a in appends:
        root = a["root"]
        cont = a["continuation_root"]

        if root in drops:
            continue

        into_th = threads_by_id.get(root)
        if not into_th:
            print(f"Append error: root not found: {root}")
            continue

        chain = reconstruct_chain_from_root(cont, tweets_by_id, children)
        if not chain:
            print(f"Append error: cannot reconstruct chain from {cont}")
            continue

        before = into_th.get("num_tweets", len(into_th.get("tweets", [])))
        threads_by_id[root] = merge_threads(
            into_th,
            chain,
            from_id_for_provenance=cont
        )
        after = threads_by_id[root]["num_tweets"]
        print(f"Appended chain from {cont} -> {root} ({before} -> {after})")

    # ---- build final output ----
    final_threads = []
    dropped_count = 0
    merged_removed = 0

    for tid in order:
        if tid in drops:
            dropped_count += 1
            continue
        if tid in merged_from_ids:
            merged_removed += 1
            continue
        final_threads.append(threads_by_id[tid])

    write_jsonl(OUT_THREADS, final_threads)

    print(f"Wrote {len(final_threads)} threads to {OUT_THREADS}")
    print(f"Dropped threads: {dropped_count}")
    print(f"Removed merged-from threads: {merged_removed}")


if __name__ == "__main__":
    main()
