#!/usr/bin/env python3
import json
from pathlib import Path

OPS_PATH = Path("thread_ops.json")
SEL_IN = Path("selection_final.json")
SEL_OUT = Path("selection_final_ops_patched.json")

def main():
    ops = json.loads(OPS_PATH.read_text(encoding="utf-8"))
    sel = json.loads(SEL_IN.read_text(encoding="utf-8"))

    drops = set(ops.get("drops", []))
    merges = ops.get("merges", [])
    appends = ops.get("append_by_url", [])

    merged_from = {m["from_root"] for m in merges}
    merged_from |= {a["continuation_root"] for a in appends}

    chapter_threads = sel.get("chapter_threads", [])
    before = len(chapter_threads)

    # Drop any thread roots we dropped, and any roots we merged-from
    chapter_threads = [t for t in chapter_threads if t not in drops and t not in merged_from]

    sel["chapter_threads"] = chapter_threads

    SEL_OUT.write_text(json.dumps(sel, indent=2), encoding="utf-8")
    print(f"chapter_threads: {before} -> {len(chapter_threads)}")
    print(f"Wrote {SEL_OUT}")

if __name__ == "__main__":
    main()
