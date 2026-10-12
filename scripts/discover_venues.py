"""Stage one of dataset building: find venue NAMES worth researching.

Two stages, both offline:

    discover_venues.py   category x neighborhood -> candidate names
    enrich_capacity.py   name -> rooms, capacities, settings, citation

Splitting them matters for cost. Discovery is one cheap call per
category/neighborhood pair that returns ~15 names; enrichment is one call per
venue. Asking a single agent to do both would re-pay the expensive research
step for venues that turn out to be closed or duplicates.

Only names and a one-line descriptor are taken. Facts about what exists are not
anyone's property, and nothing is copied from the guides that mention them.

    python scripts/discover_venues.py --category restaurant --neighborhood Bushwick
    python scripts/discover_venues.py --plan          # show the full grid and cost
    python scripts/discover_venues.py --run-all       # work the whole grid
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from budget import BudgetExceeded, check_before_call, record  # noqa: E402
from config import DATA_DIR, model_config  # noqa: E402
from tokens import Usage  # noqa: E402
from openai import OpenAI                  # noqa: E402

CANDIDATES = DATA_DIR / "candidate_venues.json"

# The categories the app offers but the dataset does not yet cover.
CATEGORIES: dict[str, str] = {
    "restaurant":  "notable restaurants people go to for a night out",
    "bar":         "bars and cocktail bars, including back rooms and basement bars",
    "hotel_bar":   "hotel bars and hotel rooftops, the kind people go to as a destination",
    "club":        "nightclubs and dance floors, including members' rooms and late venues",
    "gallery":     "contemporary art galleries that hold public openings",
    "museum":      "museums, including ones with late or evening hours",
    "theatre":     "theatres and performance spaces, including off-Broadway and dance",
    "cinema":      "independent and repertory cinemas",
    "comedy":      "comedy clubs and venues with regular comedy nights",
    "dessert":     "late-night dessert, ice cream and sweet spots",
    "tea":         "tea houses and tea rooms, including ceremonial and late-opening ones",
    "shopping":    "shopping worth making an evening of: late-opening stores, vintage, record shops, markets",
}

# Where people actually go out. Not every neighborhood -- a grid of all of them
# would be mostly empty cells and wasted calls.
NEIGHBORHOODS: list[str] = [
    # Manhattan
    "Lower East Side", "East Village", "West Village", "Greenwich Village",
    "SoHo", "Tribeca", "Chelsea", "Midtown", "Harlem", "Upper West Side",
    # Brooklyn
    "Williamsburg", "Greenpoint", "Bushwick", "Bed-Stuy", "Fort Greene",
    "Gowanus", "Park Slope", "Crown Heights", "Red Hook", "Dumbo",
    # Queens
    "Ridgewood", "Astoria", "Long Island City", "Flushing", "Jackson Heights",
    # Bronx
    "Mott Haven", "Belmont", "Fordham", "Riverdale", "Concourse",
    # Staten Island
    "St. George", "Stapleton", "Tompkinsville", "Port Richmond",
]

# Four neighborhoods from every borough, so coverage is even rather than
# proportional to how much press a borough gets. The Bronx and Staten Island
# get the same budget as Manhattan.
CORE_NEIGHBORHOODS: list[str] = [
    "Lower East Side", "East Village", "West Village", "Harlem",
    "Williamsburg", "Bushwick", "Fort Greene", "Crown Heights",
    "Ridgewood", "Astoria", "Long Island City", "Jackson Heights",
    "Mott Haven", "Belmont", "Fordham", "Riverdale",
    "St. George", "Stapleton", "Tompkinsville", "Port Richmond",
]

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["venues"],
    "properties": {"venues": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["name", "category", "neighborhood", "borough", "one_line",
                     "price_band", "good_for_groups", "has_private_space",
                     "website", "lat", "lon", "sources", "still_open"],
        "properties": {
            "name": {"type": "string"},
            "category": {"type": "string", "enum": sorted(CATEGORIES)},
            "neighborhood": {"type": "string"},
            "borough": {"type": "string"},
            "one_line": {"type": "string", "description": "Under 15 words, factual"},
            "price_band": {"type": ["string", "null"], "enum": ["free", "$", "$$", "$$$", "$$$$", None]},
            "good_for_groups": {"type": ["boolean", "null"],
                                "description": "Takes a party of 8+. null if unknown."},
            "has_private_space": {"type": ["boolean", "null"],
                                  "description": "Back room, private room or separate space."},
            "website": {"type": ["string", "null"],
                        "description": "The venue's OWN site. Never a directory listing."},
            "lat": {"type": ["number", "null"]},
            "lon": {"type": ["number", "null"]},
            "sources": {"type": "array", "items": {"type": "string"},
                        "description": "Publications that recommended it. Empty if none found."},
            "still_open": {"type": "boolean", "description": "False if closed or you are unsure"},
        }}}},
}

INSTRUCTIONS = """\
You list real, currently-operating New York City venues for ONE neighborhood,
across every category below.

Work from what the city is actually writing about, not from memory. Search
these by name and read what they currently recommend in this neighborhood:

  FOOD AND DRINK   Eater NY, The Infatuation, Grub Street, The New York Times,
                   Resy's editorial, Bon Appetit
  STYLE AND TRAVEL Vogue, Conde Nast Traveler, Travel + Leisure, Harper's Bazaar
  CITY GUIDES      Time Out New York, New York Magazine, The New Yorker's
                   "Goings On About Town", Secret NYC, Thrillist, Gothamist
  MUSIC AND CLUBS  Resident Advisor, Brooklyn Vegan, Oh My Rockness, Pitchfork
  ART              Artforum, Artnet, Hyperallergic, gallery listings
  LOCAL            neighborhood press and blogs, which carry the places the
                   national titles have not reached yet

Range across them. Two restaurants from Eater and nothing else is a worse
answer than eight places from eight different sources, because the whole point
of this app is to save someone from reading all of them, and to surface things
they would not have found on their own.

Actively prefer a place you found in local or niche coverage over one that is
on every list. Somewhere a neighborhood blog is excited about is a better
discovery than the restaurant that has been written about forty times.

Categories to cover, with roughly equal attention:
{categories}

Rules:
- Real places only. Never invent a name. If you are not confident a place is
  still trading, set still_open to false and it will be dropped.
- Cover every category you can find something for. A neighborhood with no
  cinema simply returns no cinema; do not pad it with a guess.
- Prefer places people actually go to, across price levels. Do not list only
  the most famous ones -- the app exists partly to get people out of a rut, and
  a dataset of the twelve obvious answers cannot do that.
- No chains unless the specific location is a genuine destination.
- one_line is plain fact: cuisine, what it is known for, what happens there.
  No marketing language, no "hidden gem", no adjectives you cannot source.
- sources: name the publications that actually recommended this place, e.g.
  ["Eater NY", "The Infatuation"]. Leave it empty rather than guessing. This is
  what the app cites on the page, so an invented citation is worse than none.
- good_for_groups and has_private_space: only set true or false when a source
  actually says so. Otherwise null. A wrong "yes" ruins someone's birthday.
- website must be the venue's own domain. A Yelp, JamBase, Instagram or
  Eventbrite page is not a website; leave it null instead.
- lat and lon only when you are confident of the address. A map on the wrong
  block is worse than no map, and null simply means no map is drawn.
- Return up to 40 across all categories. Real ones only.
"""


def discover(client: OpenAI, model: str, neighborhood: str) -> tuple[list[dict], object]:
    """One call covers one neighborhood across every category.

    Measured: a per-category call costs ~$0.06 because web_search pushes input
    past 38k tokens, and that cost is paid again for each category in the same
    neighborhood. Asking once per neighborhood pays the search overhead a
    single time, which is roughly six times cheaper for the same coverage.

    Offline scripts spend from the same ledger as the app. A cap only one
    caller respects is not a cap on the project.
    """
    check_before_call(0.10)
    listing = "\n".join(f"- {name}: {desc}" for name, desc in sorted(CATEGORIES.items()))
    r = client.responses.create(
        model=model, store=False,
        instructions=INSTRUCTIONS.format(categories=listing),
        tools=[{"type": "web_search"}],
        text={"format": {"type": "json_schema", "name": "venue_candidates",
                         "strict": True, "schema": SCHEMA}},
        input=f"List venues in {neighborhood}, New York City, across every category.",
    )
    record(Usage.from_response(r), f"discover:{neighborhood}", model)
    return json.loads(r.output_text)["venues"], r


def main() -> int:
    ap = argparse.ArgumentParser(description="Discover candidate NYC venues.")
    ap.add_argument("--category", action="append", choices=sorted(CATEGORIES), default=[])
    ap.add_argument("--neighborhood", action="append", default=[])
    ap.add_argument("--plan", action="store_true", help="show the grid and estimated cost")
    ap.add_argument("--run-all", action="store_true")
    ap.add_argument("--core", action="store_true",
                    help="use the core neighborhood subset, all five boroughs")
    args = ap.parse_args()

    cats = args.category or sorted(CATEGORIES)
    hoods = args.neighborhood or (CORE_NEIGHBORHOODS if args.core else NEIGHBORHOODS)

    if args.plan:
        # Measured on a real run: ~38k input / ~1.4k out per call, which is
        # ~$0.06. One call per neighborhood, all categories at once.
        est = len(hoods) * 0.075
        print(f"{len(hoods)} neighborhoods, one call each, all {len(CATEGORIES)} categories")
        print(f"Estimated discovery cost: ${est:.2f}  (~25-40 venues each)")
        return 0

    if not (args.run_all or args.core or (args.category and args.neighborhood)):
        ap.error("give --category and --neighborhood, or --run-all, or --plan")

    cfg = model_config()
    client = (OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
              if cfg.base_url else OpenAI(api_key=cfg.api_key))
    print(f"Model: {cfg.describe()}\n")

    store = json.loads(CANDIDATES.read_text()) if CANDIDATES.is_file() else {"venues": []}
    seen = {(v["name"].lower(), v["neighborhood"].lower()) for v in store["venues"]}
    added = tin = tout = 0

    for hood in hoods:
        try:
            found, raw = discover(client, cfg.model, hood)
        except BudgetExceeded as exc:
            print(f"\n  STOPPED: {exc}")
            CANDIDATES.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")
            return 2
        except Exception as exc:                      # noqa: BLE001
            print(f"  ! {hood}: {type(exc).__name__}: {exc}")
            continue
        if (u := getattr(raw, "usage", None)):
            tin += int(getattr(u, "input_tokens", 0) or 0)
            tout += int(getattr(u, "output_tokens", 0) or 0)

        fresh, by_cat = 0, {}
        for v in found:
            if not v.get("still_open"):
                continue
            key = (v["name"].lower(), v["neighborhood"].lower())
            if key in seen:
                continue
            seen.add(key)
            store["venues"].append(v)
            by_cat[v.get("category", "?")] = by_cat.get(v.get("category", "?"), 0) + 1
            fresh += 1
        added += fresh
        spread = " ".join(f"{c[:4]}:{n}" for c, n in sorted(by_cat.items()))
        print(f"  {hood:20} +{fresh:2}  {spread}")
        CANDIDATES.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")

    cost = tin / 1e6 * 1.25 + tout / 1e6 * 10
    print(f"\nAdded {added} candidates. {len(store['venues'])} total in {CANDIDATES.name}")
    print(f"Tokens: {tin:,} in / {tout:,} out  (~${cost:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
