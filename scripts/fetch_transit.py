"""Download every NYC subway station once, and cache it.

Source: MTA's open dataset on data.ny.gov. No API key, and the file is small
enough to commit, so the app never calls this at request time. That keeps a
grader's fresh clone inside the ten-minute rule and keeps "nearest train" off
the critical path of a plan.

    python scripts/fetch_transit.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "subway_stations.json"
URL = "https://data.ny.gov/resource/39hk-dx4f.json"
UA = {"User-Agent": "TheProgramme/0.1 (Yale MGT409 course project)"}

BOROUGH = {"M": "Manhattan", "Bk": "Brooklyn", "Bx": "Bronx",
           "Q": "Queens", "SI": "Staten Island"}


def main() -> int:
    rows: list[dict] = []
    with httpx.Client(headers=UA, timeout=60, follow_redirects=True) as c:
        offset = 0
        while True:
            r = c.get(URL, params={"$limit": 1000, "$offset": offset})
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            rows.extend(batch)
            offset += len(batch)
            if len(batch) < 1000:
                break

    stations = []
    for row in rows:
        try:
            lat = float(row["gtfs_latitude"])
            lon = float(row["gtfs_longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        stations.append({
            "name": row.get("stop_name", "").strip(),
            "routes": (row.get("daytime_routes") or "").split(),
            "line": row.get("line", ""),
            "borough": BOROUGH.get(row.get("borough", ""), row.get("borough", "")),
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "ada": row.get("ada") in ("1", 1, True, "true"),
        })

    # One entry per physical station: the feed lists a row per platform/
    # direction, and four identical "Bedford Av" pins would be noise.
    seen: dict[tuple, dict] = {}
    for st in stations:
        key = (st["name"], round(st["lat"], 4), round(st["lon"], 4))
        if key in seen:
            merged = sorted(set(seen[key]["routes"]) | set(st["routes"]))
            seen[key]["routes"] = merged
            seen[key]["ada"] = seen[key]["ada"] or st["ada"]
        else:
            seen[key] = st

    final = sorted(seen.values(), key=lambda s: (s["borough"], s["name"]))
    OUT.write_text(json.dumps({"stations": final, "source": URL,
                               "licence": "MTA open data"}, indent=1) + "\n",
                   encoding="utf-8")

    by_b: dict[str, int] = {}
    for s in final:
        by_b[s["borough"]] = by_b.get(s["borough"], 0) + 1
    print(f"{len(rows)} rows -> {len(final)} stations")
    for b, n in sorted(by_b.items()):
        print(f"   {b:16} {n}")
    print(f"ADA accessible: {sum(1 for s in final if s['ada'])}")
    print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
