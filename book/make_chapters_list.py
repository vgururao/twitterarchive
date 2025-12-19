#!/usr/bin/env python3
import json
from pathlib import Path

CHAPTERS_DIR = Path("chapters")
OUT = Path("chapters_list.json")

def main():
    files = sorted([p.name for p in CHAPTERS_DIR.glob("*.html")])
    OUT.write_text(json.dumps(files, indent=2), encoding="utf-8")
    print(f"Wrote {len(files)} entries to {OUT}")

if __name__ == "__main__":
    main()
