"""Collect opening hours from OpenStreetMap, once, offline.

Nominatim returns `opening_hours` in extratags alongside the geocoding we
already do, at no extra cost. Without it the planner places a stop at 7:30pm
with no idea whether anywhere is open, which is the one place the app still
promises something it cannot back.

    python scripts/fetch_hours.py --limit 400
    python scripts/fetch_hours.py --report
"""

from __future__ import annotations

import argparse
import json
import sys
import time as clock
from collections import Counter
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from config import DATA_DIR   # noqa: E402
from hours import parse       # noqa: E402

CANDIDATES = DATA_DIR / "candidate_venues.json"
VENUES = DATA_DIR / "nyc_venues.json"
API = "https://nominatim.openstreetmap.org/search"
UA = {"User-Agent": "TheProgramme/0.1 (Yale MGT409 course project; ashley.wheeler@yale.edu)"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Collect opening hours from OSM.")
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    files = [(CANDIDATES, json.loads(CANDIDATES.read_text()))]
    if VENUES.is_file():
        files.append((VENUES, json.loads(VENUES.read_text())))
    rows = [v for _, d in files for v in d["venues"]]

    if args.report:
        have = [v for v in rows if v.get("opening_hours")]
        readable = [v for v in have if parse(v["opening_hours"])]
        print(f"{len(have)} of {len(rows)} venues have hours on file")
        print(f"{len(readable)} of those are in a format the parser understands")
        for spec, n in Counter(v["opening_hours"] for v in have).most_common(8):
            print(f"   {n:4}  {spec[:60]}")
        return 0

    todo = [v for v in rows if v.get("hours_checked") is None][:args.limit]
    print(f"checking {len(todo)} venues\n")
    found = unreadable = 0

    with httpx.Client(headers=UA, timeout=30, follow_redirects=True) as c:
        for i, v in enumerate(todo, 1):
            q = f"{v['name']}, {v.get('neighborhood','')}, New York City"
            try:
                r = c.get(API, params={"q": q, "format": "json", "limit": 1,
                                       "countrycodes": "us", "extratags": 1})
                r.raise_for_status()
                hits = r.json()
            except httpx.HTTPError:
                hits = []

            spec = None
            if hits:
                spec = (hits[0].get("extratags") or {}).get("opening_hours")

            v["hours_checked"] = True
            if spec:
                v["opening_hours"] = spec
                if parse(spec):
                    found += 1
                    print(f"  + {v['name'][:28]:30} {spec[:44]}", flush=True)
                else:
                    unreadable += 1
                    print(f"  ? {v['name'][:28]:30} {spec[:44]}  (not parseable)", flush=True)

            if i % 20 == 0:
                for path, data in files:
                    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            clock.sleep(1.1)

    for path, data in files:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"\n{found} usable, {unreadable} present but unparseable, "
          f"{len(todo) - found - unreadable} with none on file")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
