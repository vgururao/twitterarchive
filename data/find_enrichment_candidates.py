import json

THREADS_FILE = "threads_data_ops_patched.jsonl"
TWEETS_FILE = "tweets_normalized.jsonl"

def iter_jsonl(p):
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if line:
                yield json.loads(line)

def get_media(raw: dict):
    # some tweets have extended_entities; your sample doesn't, but check anyway
    ee = raw.get("extended_entities") or {}
    if ee.get("media"):
        return ee.get("media") or []
    en = raw.get("entities") or {}
    return en.get("media") or []

def get_quoted_id(raw: dict):
    # try common locations; normalize to str
    for k in ("quoted_status_id_str", "quoted_status_id"):
        if k in raw and raw[k]:
            return str(raw[k])
    qs = raw.get("quoted_status")
    if isinstance(qs, dict):
        qid = qs.get("id_str") or qs.get("id")
        if qid:
            return str(qid)
    return None

def main():
    tweets_by_id = {}
    for t in iter_jsonl(TWEETS_FILE):
        tid = t.get("id_str")
        if tid:
            tweets_by_id[tid] = t

    total = 0
    media_count = 0
    self_quote_count = 0

    for th in iter_jsonl(THREADS_FILE):
        for tw in th.get("tweets", []):
            total += 1
            tid = tw.get("id_str")
            full = tweets_by_id.get(tid) or tw
            raw = full.get("raw") or {}

            if isinstance(raw, dict) and get_media(raw):
                media_count += 1

            if isinstance(raw, dict):
                qid = get_quoted_id(raw)
                if qid and qid in tweets_by_id:
                    self_quote_count += 1

    print("Total chapter tweets:", total)
    print("Tweets with media:", media_count)
    print("Tweets quoting your own tweet:", self_quote_count)

if __name__ == "__main__":
    main()
