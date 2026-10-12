"""Add coordinates to the venue dataset, once, offline.

Maps and nearest-train lookups both need a lat/lon. Asking the Editor for them
turned out unreliable: it leaves them null more often than not, and a model
that guesses coordinates puts a venue on the wrong block, which is worse than
drawing no map at all.

So they are geocoded here instead, from the venue name plus neighborhood, and
cached. Deterministic, free, and the app never does it at request time.

Source: Nominatim (OpenStreetMap). No API key. Their usage policy asks for an
identifying User-Agent and at most one request a second, both of which this
respects.

    python scripts/geocode_venues.py --limit 50
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from config import DATA_DIR  # noqa: E402

VENUES = DATA_DIR / "nyc_venues.json"
API = "https://nominatim.openstreetmap.org/search"
UA = {"User-Agent": "TheProgramme/0.1 (Yale MGT409 course project; ashley.wheeler@yale.edu)"}

# Rough bounds for the five boroughs. Anything outside is a bad match, not a
# venue -- Nominatim will happily return a "Bowery Ballroom" in another country.
NYC = {"min_lat": 40.47, "max_lat": 40.93, "min_lon": -74.27, "max_lon": -73.68}


def in_nyc(lat: float, lon: float) -> bool:
    return (NYC["min_lat"] <= lat <= NYC["max_lat"]
            and NYC["min_lon"] <= lon <= NYC["max_lon"])


# Rough centres for the neighborhoods in the dataset. A geocode that lands
# more than a mile from the neighborhood we already recorded is the wrong
# place: Nominatim matched a different business with the same name.
HOOD_CENTRES: dict[str, tuple[float, float]] = {
    "Lower East Side": (40.7180, -73.9880), "East Village": (40.7265, -73.9815),
    "West Village": (40.7358, -74.0036), "Greenwich Village": (40.7336, -74.0027),
    "Chelsea": (40.7465, -74.0014), "Midtown": (40.7549, -73.9840),
    "Harlem": (40.8116, -73.9465), "Upper West Side": (40.7870, -73.9754),
    "Union Square": (40.7359, -73.9911), "Gramercy": (40.7368, -73.9830),
    "Hell's Kitchen": (40.7638, -73.9918), "Theater District": (40.7590, -73.9845),
    "Williamsburg": (40.7081, -73.9571), "East Williamsburg": (40.7122, -73.9335),
    "Greenpoint": (40.7304, -73.9540), "Bushwick": (40.6944, -73.9213),
    "Bedford-Stuyvesant": (40.6872, -73.9418), "Gowanus": (40.6736, -73.9890),
    "Fort Greene": (40.6892, -73.9742), "Crown Heights": (40.6694, -73.9442),
    "Prospect Heights": (40.6782, -73.9690), "Flatbush": (40.6409, -73.9624),
    "Ridgewood": (40.7005, -73.9060), "Astoria": (40.7644, -73.9235),
    "Long Island City": (40.7447, -73.9485), "Maspeth": (40.7245, -73.9060),
    "Mott Haven": (40.8090, -73.9229), "Belmont": (40.8540, -73.8880),
    "St. George": (40.6437, -74.0776),
}
MAX_HOOD_MILES = 1.2


def miles_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    from math import asin, cos, radians, sin, sqrt
    dlat, dlon = radians(b[0] - a[0]), radians(b[1] - a[1])
    h = sin(dlat / 2) ** 2 + cos(radians(a[0])) * cos(radians(b[0])) * sin(dlon / 2) ** 2
    return 2 * 3958.8 * asin(sqrt(h))


def plausible_for_hood(lat: float, lon: float, hood: str) -> bool:
    centre = HOOD_CENTRES.get(hood)
    if centre is None:
        return True          # unknown neighborhood: nothing to check against
    return miles_between((lat, lon), centre) <= MAX_HOOD_MILES


def geocode(client: httpx.Client, query: str) -> tuple[float, float] | None:
    r = client.get(API, params={"q": query, "format": "json", "limit": 1,
                                "countrycodes": "us"})
    r.raise_for_status()
    hits = r.json()
    if not hits:
        return None
    lat, lon = float(hits[0]["lat"]), float(hits[0]["lon"])
    return (lat, lon) if in_nyc(lat, lon) else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Geocode the venue dataset.")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--redo", action="store_true", help="re-geocode venues that already have coords")
    args = ap.parse_args()

    data = json.loads(VENUES.read_text())
    venues = data["venues"]
    done = hit = 0

    with httpx.Client(headers=UA, timeout=30, follow_redirects=True) as c:
        for v in venues:
            if done >= args.limit:
                break
            if v.get("lat") is not None and not args.redo:
                continue
            done += 1
            name, hood = v["name"], v.get("neighborhood", "")
            # Most specific first: a bare venue name matches the wrong city.
            for query in (f"{name}, {hood}, New York City",
                          f"{name}, New York, NY"):
                try:
                    found = geocode(c, query)
                except httpx.HTTPError as exc:
                    print(f"  ! {name[:30]:32} {type(exc).__name__}")
                    found = None
                time.sleep(1.1)     # Nominatim asks for <= 1 request/second
                if found and not plausible_for_hood(found[0], found[1], hood):
                    print(f"    rejected {found[0]:.4f},{found[1]:.4f} "
                          f"-- too far from {hood}")
                    found = None
                if found:
                    break
            if found:
                v["lat"], v["lon"] = round(found[0], 6), round(found[1], 6)
                hit += 1
                print(f"  + {name[:30]:32} {v['lat']:.4f}, {v['lon']:.4f}")
            else:
                v["lat"], v["lon"] = None, None
                print(f"  - {name[:30]:32} not found")

    VENUES.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    total = sum(1 for v in venues if v.get("lat") is not None)
    print(f"\nGeocoded {hit} of {done} tried. {total}/{len(venues)} venues now have coordinates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
