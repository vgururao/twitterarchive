#!/usr/bin/env python3
import json
import re
from pathlib import Path

IN_PATH = Path("compendium_tagged.json")
OUT_PATH = Path("compendium_tagged_classified.json")


def load_compendium(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_compendium(data, path: Path):
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------- classification heuristics ----------

JOKE_MARKERS = [
    "lol", "lmao", "rofl", "haha", "hehe", "😂", "🤣", "😅", "😆",
    "/s", " (jk)", " jk", "joke:"
]

HOT_TAKE_MARKERS = [
    "hot take", "unpopular opinion", "here's my take", "here is my take",
    "here’s my take", "my take on", "change my mind", "fight me"
]

ADVICE_PHRASES = [
    "you should", "you need to", "you have to", "you must",
    "try to", "remember to", "the trick is", "rule of thumb",
    "a good rule is", "here's a tip", "here is a tip", "pro tip",
    "my advice", "good advice", "bad advice", "life advice"
]

IMPERATIVE_STARTS = [
    "stop ", "start ", "never ", "always ", "get ", "learn to ",
    "avoid ", "remember ", "don’t ", "don't "
]

GENERAL_SUBJECTS = [
    "people", "everyone", "everybody", "no one", "nobody", "someone",
    "society", "reality", "capitalism", "history", "technology",
    "markets", "institutions"
]

# very rough pronoun detectors
FIRST_PERSON = [" i ", " i'm ", " i’m ", " my ", " me ", " we ", " us ", " our "]
SECOND_PERSON = [" you ", " you’re ", " you're ", " your ", " u "]


def normalize_text(text: str) -> str:
    t = text.replace("\n", " ")
    # add spaces around to make " i " style checks safer
    t = " " + t + " "
    return t


def is_joke(t: str) -> bool:
    lower = t.lower()
    if any(m in lower for m in JOKE_MARKERS):
        return True
    if lower.strip().endswith((" :)", " :-)", " :d", " :p")):
        return True
    return False


def is_hot_take(t: str) -> bool:
    lower = t.lower()
    if any(m in lower for m in HOT_TAKE_MARKERS):
        return True
    # strong stance combined with "objectively"
    if "objectively" in lower and ("good" in lower or "bad" in lower):
        return True
    return False


def is_advice(t: str) -> bool:
    lower = t.lower()
    # clear advice phrases
    if any(p in lower for p in ADVICE_PHRASES):
        return True
    # imperative in second person: starts with "stop/never/get/..." and contains "you"
    stripped = lower.strip()
    if any(stripped.startswith(p) for p in IMPERATIVE_STARTS) and "you " in lower:
        return True
    return False


def looks_general_statement(t: str) -> bool:
    """
    Heuristic for aphorism vs reflection. We want short, generalized,
    non-story statements.
    """
    text = t.strip()
    lower = text.lower()

    # Not too long
    if len(text) > 220:
        return False

    # avoid clear questions
    if "?" in text:
        return False

    # general subjects or "X is Y" patterns
    if any(g in lower for g in GENERAL_SUBJECTS):
        return True

    # starts with "The ..." often generalization
    if lower.startswith("the "):
        return True

    # "X is Y" pattern in the middle, e.g. "X is just Y" etc.
    if re.search(r"\bis\b", lower):
        return True

    return False


def has_first_person(t: str) -> bool:
    lower = t.lower()
    return any(p in lower for p in FIRST_PERSON)


def has_second_person(t: str) -> bool:
    lower = t.lower()
    return any(p in lower for p in SECOND_PERSON)


def classify_single_tweet(text: str):
    """
    Return a *single* primary tag in a list:
    one of: aphorism, hot_take, joke, advice, reflection, unclassified.
    """
    if not text:
        return ["unclassified"]

    t = normalize_text(text)

    # 1. Hard markers: joke / hot take / advice
    if is_joke(t):
        return ["joke"]
    if is_hot_take(t):
        return ["hot_take"]
    if is_advice(t):
        return ["advice"]

    # 2. Questions -> reflection (if not clearly a joke)
    if "?" in text:
        return ["reflection"]

    # 3. General short statements with no "I" etc -> aphorism
    if looks_general_statement(t) and not has_first_person(t):
        return ["aphorism"]

    # 4. If it's short and somewhat general but with "I", lean to reflection
    if len(text.strip()) <= 220 and not has_second_person(t):
        # introspective / observational → reflection
        return ["reflection"]

    # 5. Longer text, likely micro-essay or reflection
    if len(text.strip()) > 220:
        return ["reflection"]

    # Fallback
    return ["unclassified"]


def main():
    if not IN_PATH.exists():
        raise SystemExit(f"{IN_PATH} not found in current directory")

    data = load_compendium(IN_PATH)

    tweets = data.get("tweets", [])
    print(f"Loaded {len(tweets)} tweets from {IN_PATH}")

    updated = []
    for rec in tweets:
        text = rec.get("text") or ""
        new_tags = classify_single_tweet(text)

        # overwrite tags, but preserve featured/discard
        rec["tags"] = new_tags

        if "featured" not in rec:
            rec["featured"] = False
        if "discard" not in rec:
            rec["discard"] = False

        updated.append(rec)

    out_data = {"tweets": updated}
    save_compendium(out_data, OUT_PATH)

    print(f"Wrote {len(updated)} tweets with new tags to {OUT_PATH}")
    print("Primary tags used: aphorism, hot_take, joke, advice, reflection, unclassified")


if __name__ == "__main__":
    main()
