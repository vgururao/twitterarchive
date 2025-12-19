import json

THREADS_FILE = "threads_data_ops_patched.jsonl"
SELECTION_IN = "selection_final.json"
SELECTION_OUT = "selection_final_clean.json"

# load valid thread_ids
valid = set()
with open(THREADS_FILE, "r", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            obj = json.loads(line)
            tid = obj.get("thread_id")
            if tid:
                valid.add(tid)

# load selection
with open(SELECTION_IN, "r", encoding="utf-8") as f:
    sel = json.load(f)

before = len(sel.get("chapter_threads", []))

# filter chapter_threads
sel["chapter_threads"] = [
    tid for tid in sel.get("chapter_threads", [])
    if tid in valid
]

after = len(sel["chapter_threads"])

# write cleaned selection
with open(SELECTION_OUT, "w", encoding="utf-8") as f:
    json.dump(sel, f, indent=2)

print(f"Chapter threads: {before} -> {after}")
print(f"Wrote {SELECTION_OUT}")
