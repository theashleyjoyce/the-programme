"""Nearest subway stations for a point, from the cached MTA dataset.

Computed here rather than asked of the model. Two reasons: a model will
cheerfully invent a station that is four stops away, and distance is
arithmetic, which is free. data/subway_stations.json is 493 stations across
all five boroughs, downloaded once by scripts/fetch_transit.py.
"""

from __future__ import annotations

import json
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any

STATIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "subway_stations.json"

EARTH_MILES = 3958.8
# Beyond this a station is not "nearby" in any useful sense, and saying so is
# worse than saying nothing.
MAX_WALK_MILES = 0.75
# Rule of thumb for city walking, including waiting at lights.
MINUTES_PER_MILE = 20


@lru_cache(maxsize=1)
def stations() -> list[dict[str, Any]]:
    if not STATIONS_PATH.is_file():
        return []
    return json.loads(STATIONS_PATH.read_text(encoding="utf-8")).get("stations", [])


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * EARTH_MILES * asin(sqrt(a))


def nearest(lat: float | None, lon: float | None, limit: int = 2) -> list[dict[str, Any]]:
    """Closest stations within walking distance, nearest first.

    Returns an empty list rather than a far-away station: "nearest train:
    42nd St, 3 miles" is noise on a page about where to spend an evening.
    """
    if lat is None or lon is None:
        return []

    scored = []
    for st in stations():
        miles = haversine_miles(lat, lon, st["lat"], st["lon"])
        if miles <= MAX_WALK_MILES:
            scored.append((miles, st))

    scored.sort(key=lambda pair: pair[0])
    out: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for miles, st in scored:
        if st["name"] in seen_names:
            continue
        seen_names.add(st["name"])
        out.append({
            "name": st["name"],
            "routes": st["routes"],
            "miles": round(miles, 2),
            "walk_minutes": max(1, round(miles * MINUTES_PER_MILE)),
            "ada": st["ada"],
        })
        if len(out) >= limit:
            break
    return out


def summary(lat: float | None, lon: float | None, limit: int = 2) -> str:
    """One short line for the card, e.g. 'Jefferson St (L) 4 min walk'."""
    found = nearest(lat, lon, limit=limit)
    if not found:
        return ""
    bits = []
    for st in found:
        routes = "/".join(st["routes"]) if st["routes"] else ""
        bits.append(f"{st['name']}{f' ({routes})' if routes else ''} {st['walk_minutes']} min")
    return " · ".join(bits)
