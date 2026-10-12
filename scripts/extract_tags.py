"""Derive cuisine and genre from the venue descriptions we already hold.

Free. No model call. The Scout already wrote "Italian-American restaurant
known for lasagna" and "techno and house with international guests"; this
turns that prose into fields the planner can actually filter on.

Structured tags beat free-text search because a request for techno should
rank a techno room above a cabaret bar even when both descriptions happen to
contain the word "dancing".

Anything the vocabulary does not recognise is left empty rather than guessed,
and `--report` shows what is still missing so the gaps are visible.

    python scripts/extract_tags.py
    python scripts/extract_tags.py --report
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from config import DATA_DIR  # noqa: E402

CANDIDATES = DATA_DIR / "candidate_venues.json"
VENUES = DATA_DIR / "nyc_venues.json"

# Cuisine. Ordered so a more specific match wins: "Neapolitan" before "pizza",
# "Sichuan" before "Chinese".
CUISINE: dict[str, tuple[str, ...]] = {
    "neapolitan": ("neapolitan",),
    "pizza": ("pizza", "pizzeria", "slice"),
    "italian": ("italian", "trattoria", "osteria", "pasta", "roman", "sicilian"),
    "sichuan": ("sichuan", "szechuan"),
    "cantonese": ("cantonese", "dim sum"),
    "chinese": ("chinese", "hand-pulled", "dumpling"),
    "japanese": ("japanese", "omakase", "sushi", "izakaya", "yakitori", "soba", "ramen"),
    "korean": ("korean", "kbbq", "banchan"),
    "thai": ("thai", "isan"),
    "vietnamese": ("vietnamese", "pho", "banh mi"),
    "indian": ("indian", "south indian", "dosa", "tandoori", "kerala"),
    "mexican": ("mexican", "taqueria", "tacos", "oaxacan", "mezcal"),
    "latin": ("latin", "peruvian", "colombian", "dominican", "cuban", "argentine", "venezuelan"),
    "caribbean": ("caribbean", "jamaican", "trinidadian", "jerk"),
    "french": ("french", "bistro", "brasserie", "parisian"),
    "spanish": ("spanish", "tapas", "basque", "iberian", "paella"),
    "greek": ("greek", "taverna"),
    "turkish": ("turkish", "anatolian"),
    "middle eastern": ("middle eastern", "lebanese", "levantine", "israeli", "falafel", "mezze"),
    "ethiopian": ("ethiopian", "injera"),
    "west african": ("nigerian", "senegalese", "ghanaian", "west african", "suya"),
    "american": ("american", "burger", "steakhouse", "diner", "southern", "bbq", "soul food"),
    "seafood": ("seafood", "oyster", "raw bar", "fish"),
    "vegetarian": ("vegetarian", "vegan", "plant-based", "plant based"),
    "bakery": ("bakery", "pastry", "croissant", "bread"),
    "deli": ("deli", "sandwich", "bodega", "appetizing"),
}

# Genre, for anywhere with music or a stage.
GENRE: dict[str, tuple[str, ...]] = {
    "techno": ("techno",),
    "house": ("house music", " house,", "deep house", "disco house"),
    "disco": ("disco",),
    "electronic": ("electronic", "dj", "djs", "dance music", "edm", "rave"),
    "hip hop": ("hip hop", "hip-hop", "rap"),
    "r&b": ("r&b", "rnb", "soul night"),
    "afrobeats": ("afrobeats", "amapiano", "afrobeat"),
    "latin": ("latin", "salsa", "bachata", "reggaeton", "cumbia"),
    "reggae": ("reggae", "dancehall", "dub"),
    "jazz": ("jazz", "bebop", "big band"),
    "blues": ("blues",),
    "indie": ("indie", "alternative", "shoegaze"),
    "rock": ("rock", "punk", "metal", "hardcore", "garage"),
    "folk": ("folk", "singer-songwriter", "americana", "bluegrass"),
    "classical": ("classical", "chamber", "orchestra", "opera", "recital"),
    "experimental": ("experimental", "avant-garde", "noise", "improvised"),
    "world": ("world music", "global", "traditional music"),
    "cabaret": ("cabaret", "burlesque", "drag", "variety"),
    "comedy": ("comedy", "stand-up", "standup", "improv"),
    "theatre": ("play", "theater", "theatre", "musical", "broadway", "off-broadway"),
    "dance": ("dance company", "ballet", "contemporary dance", "choreograph"),
}

FOOD_CATEGORIES = {"restaurant", "dessert", "tea", "cafe"}
MUSIC_CATEGORIES = {"club", "music", "theatre", "comedy", "cinema", "bar", "hotel_bar"}


def match(text: str, vocab: dict[str, tuple[str, ...]], limit: int = 3) -> list[str]:
    found: list[str] = []
    low = text.lower()
    for label, words in vocab.items():
        if any(w in low for w in words):
            found.append(label)
        if len(found) >= limit:
            break
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description="Derive cuisine and genre tags.")
    ap.add_argument("--report", action="store_true", help="show coverage only")
    args = ap.parse_args()

    data = json.loads(CANDIDATES.read_text())
    tagged_c = tagged_g = 0

    for v in data["venues"]:
        text = f"{v.get('one_line','')} {v.get('name','')}"
        cat = v.get("category", "")

        cuisine = match(text, CUISINE) if cat in FOOD_CATEGORIES else []
        genre = match(text, GENRE) if cat in MUSIC_CATEGORIES else []

        if not args.report:
            v["cuisine"] = cuisine
            v["genre"] = genre
        tagged_c += bool(cuisine)
        tagged_g += bool(genre)

    if not args.report:
        CANDIDATES.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    food = [v for v in data["venues"] if v.get("category") in FOOD_CATEGORIES]
    music = [v for v in data["venues"] if v.get("category") in MUSIC_CATEGORIES]
    print(f"cuisine : {tagged_c} of {len(food)} food venues tagged")
    print(f"genre   : {tagged_g} of {len(music)} music/nightlife venues tagged")

    print("\ntop cuisines:")
    for k, n in Counter(c for v in data["venues"] for c in (v.get("cuisine") or [])).most_common(10):
        print(f"   {k:16} {n}")
    print("\ntop genres:")
    for k, n in Counter(g for v in data["venues"] for g in (v.get("genre") or [])).most_common(10):
        print(f"   {k:16} {n}")

    untagged = [v["name"] for v in food if not v.get("cuisine")][:6]
    if untagged:
        print(f"\nfood venues with no cuisine match ({len([v for v in food if not v.get('cuisine')])}):")
        print("   " + ", ".join(untagged))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
