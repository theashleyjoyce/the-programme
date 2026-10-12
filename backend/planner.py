"""Deterministic plan assembly. No model call, no network.

The slow path used one model call to choose venues, sequence them, and write
the copy, which meant ~2,000 output tokens and seven to twenty-five seconds.
Almost none of that needed a model:

    choosing    filtering rows by size, setting, party, budget   -> Python
    sequencing  start times, travel gaps, door times              -> arithmetic
    writing     the prose about a venue                           -> a model,
                but the same prose every time, so write it ONCE offline

So selection and sequencing happen here, instantly, and the editorial copy is
read from a cache keyed by venue. What remains for the model at request time is
at most a single sentence tying the night together, which is ~60 tokens instead
of two thousand.

The LLM editor in agents.py is still there, and still used when the dataset
cannot cover a request. This is the fast path, not the only path.
"""

from __future__ import annotations

import json
import random
from datetime import date as Date
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from brief import Brief, Budget
from config import DATA_DIR
from models import (
    Night, PriceBand, Setting, Source, Stop, StopKind, VenueSize,
)
from sources import lookup_venue, venues
from transit import haversine_miles

COPY_PATH = DATA_DIR / "venue_copy.json"

# A night runs in this order when several kinds are wanted. Shopping and
# galleries close early; dessert and clubs are where a night ends.
KIND_ORDER: list[StopKind] = [
    StopKind.SHOPPING, StopKind.GALLERY, StopKind.MUSEUM, StopKind.TEA,
    StopKind.COFFEE, StopKind.DINNER, StopKind.THEATRE, StopKind.SCREENING,
    StopKind.DRINKS, StopKind.HOTEL_BAR, StopKind.SHOW, StopKind.CLUB,
    StopKind.LATE, StopKind.DESSERT,
]

# Typical start time and length, in minutes, for each kind.
KIND_TIMING: dict[StopKind, tuple[str, int]] = {
    StopKind.SHOPPING: ("17:30", 60), StopKind.GALLERY: ("18:00", 75),
    StopKind.MUSEUM: ("18:00", 90), StopKind.TEA: ("16:00", 60),
    StopKind.COFFEE: ("17:00", 45), StopKind.DINNER: ("19:30", 90),
    StopKind.THEATRE: ("19:30", 135), StopKind.SCREENING: ("19:45", 120),
    StopKind.DRINKS: ("21:00", 75), StopKind.HOTEL_BAR: ("21:00", 75),
    StopKind.SHOW: ("21:30", 120), StopKind.CLUB: ("23:00", 150),
    StopKind.LATE: ("23:00", 90), StopKind.DESSERT: ("22:30", 45),
}

# Which dataset categories can satisfy which kind of stop.
KIND_CATEGORIES: dict[StopKind, tuple[str, ...]] = {
    StopKind.DINNER: ("restaurant",), StopKind.DRINKS: ("bar",),
    StopKind.HOTEL_BAR: ("hotel_bar", "bar"), StopKind.CLUB: ("club", "nightclub"),
    StopKind.SHOW: ("music", "club"), StopKind.LATE: ("bar", "club", "music"),
    StopKind.DESSERT: ("dessert",), StopKind.TEA: ("tea", "cafe"),
    StopKind.COFFEE: ("cafe", "tea"), StopKind.GALLERY: ("gallery",),
    StopKind.MUSEUM: ("museum",), StopKind.THEATRE: ("theatre",),
    StopKind.SCREENING: ("cinema",), StopKind.SHOPPING: ("shopping",),
}

PRICE_CEILING = {
    PriceBand.FREE: 0.0, PriceBand.CHEAP: 25.0, PriceBand.MODERATE: 60.0,
    PriceBand.SPENDY: 120.0, PriceBand.SPLURGE: 250.0,
}

WALK_MINUTES_PER_MILE = 20

# The whole night should fit inside a believable radius of the first stop.
# Beyond this it stops being an evening and becomes a commute.
MAX_NIGHT_MILES = 2.5


def _miles_apart(a: dict, b: dict) -> float | None:
    """Distance between two venues, or None when either cannot be placed.

    None means unknown, not far. An earlier version returned 99 miles for a
    missing coordinate, which quietly dropped every venue we had not geocoded
    yet -- and that is most of them, so multi-stop nights collapsed to one.
    """
    if None in (a.get("lat"), a.get("lon"), b.get("lat"), b.get("lon")):
        return None
    return haversine_miles(a["lat"], a["lon"], b["lat"], b["lon"])


def _rank(row: dict, anchor: dict | None) -> tuple:
    """Sort key: known-near first, then unknown, then known-far.

    An unplaceable venue is not rejected, it just loses to one we can confirm
    is round the corner.
    """
    if anchor is None:
        return (0, 0.0, row.get("lat") is None)
    distance = _miles_apart(anchor, row)
    if distance is None:
        return (1, 0.0, True)            # unknown: middle of the pack
    return (0 if distance <= MAX_NIGHT_MILES else 2, round(distance, 2), False)


@lru_cache(maxsize=1)
def venue_copy() -> dict[str, dict]:
    """Editorial copy written once, offline, keyed by venue name."""
    if not COPY_PATH.is_file():
        return {}
    try:
        return json.loads(COPY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


@lru_cache(maxsize=1)
def catalogue() -> list[dict[str, Any]]:
    """Every venue we can place, from both datasets, flattened."""
    rows: list[dict[str, Any]] = []

    for v in venues().values():
        room = v.main_space
        rows.append({
            "name": v.name, "category": "music",
            "neighborhood": v.neighborhood, "borough": v.borough,
            "lat": v.lat, "lon": v.lon,
            "capacity": room.capacity, "seated": room.seated_capacity,
            "setting": room.setting, "size": room.size,
            "price_band": None, "good_for_groups": v.takes_large_groups,
            "website": None, "source_url": v.source_url,
        })

    path = DATA_DIR / "candidate_venues.json"
    if path.is_file():
        try:
            for v in json.loads(path.read_text(encoding="utf-8")).get("venues", []):
                band = None
                if v.get("price_band"):
                    try:
                        band = PriceBand(v["price_band"])
                    except ValueError:
                        band = None
                rows.append({
                    "name": v.get("name", ""), "category": v.get("category", ""),
                    "neighborhood": v.get("neighborhood", ""), "borough": v.get("borough", ""),
                    "lat": v.get("lat"), "lon": v.get("lon"),
                    "capacity": None, "seated": None,
                    "setting": Setting.INDOOR, "size": None,
                    "price_band": band, "good_for_groups": v.get("good_for_groups"),
                    "website": v.get("website"), "source_url": v.get("website"),
                    "one_line": v.get("one_line", ""),
                    "sources": v.get("sources") or [],
                })
        except json.JSONDecodeError:
            pass

    return [r for r in rows if r["name"]]


def _matches(row: dict, kind: StopKind, brief: Brief) -> bool:
    if row["category"] not in KIND_CATEGORIES.get(kind, ()):
        return False
    if brief.neighborhood and brief.neighborhood.lower() not in (row["neighborhood"] or "").lower():
        return False
    if brief.borough and brief.borough.lower() != (row["borough"] or "").lower():
        return False
    if brief.venue_sizes and row["size"] is not None and row["size"] not in brief.venue_sizes:
        return False
    if brief.settings and row["setting"] not in brief.settings:
        return False
    if brief.is_group and row.get("good_for_groups") is False:
        return False
    if brief.budget and brief.budget is not Budget.NO_LIMIT and row["price_band"]:
        ceiling = brief.budget.ceiling_usd
        if ceiling is not None and PRICE_CEILING.get(row["price_band"], 0) > ceiling:
            return False
    return True


def _wanted_kinds(brief: Brief) -> list[StopKind]:
    if brief.wants:
        return [k for k in KIND_ORDER if k in set(brief.wants)][:4]
    # Nothing ticked: a dinner and somewhere after is the default night out.
    return [StopKind.DINNER, StopKind.DRINKS]


def _travel_minutes(a: dict, b: dict) -> tuple[int, str]:
    # No coordinates means no honest estimate. Say nothing rather than invent
    # a number someone will plan their evening around.
    if None in (a.get("lat"), a.get("lon"), b.get("lat"), b.get("lon")):
        return 0, ""
    miles = haversine_miles(a["lat"], a["lon"], b["lat"], b["lon"])
    if miles <= 0.9:
        return max(2, round(miles * WALK_MINUTES_PER_MILE)), "walk"
    if miles <= 4:
        return max(8, round(miles * 6)), "subway"
    return max(12, round(miles * 4)), "cab"


def _to_stop(row: dict, kind: StopKind, start: datetime, end: datetime | None,
             travel: tuple[int, str] | None) -> Stop:
    copy = venue_copy().get(row["name"], {})
    why = copy.get("why") or row.get("one_line") or (
        f"{row['category'].replace('_', ' ').title()} in {row['neighborhood']}.")
    # Cite the publications that actually recommended the place. Falling back
    # to our own dataset is honest but weak, so the editorial names come first.
    named = row.get("sources") or []
    if named:
        sources = [Source(name=n, url=None) for n in named[:3]]
        if row.get("source_url"):
            sources.append(Source(name=row["name"], url=row["source_url"]))
    else:
        sources = [Source(name=copy.get("source_name") or "The Programme dataset",
                          url=row.get("source_url") or None)]
    return Stop(
        name=row["name"], kind=kind, neighborhood=row["neighborhood"] or "New York",
        start_time=start.strftime("%H:%M"),
        end_time=end.strftime("%H:%M") if end else None,
        why=why[:320], order_this=copy.get("order_this"),
        venue_size=row["size"], capacity=row["capacity"],
        setting=row["setting"], price_band=row["price_band"],
        lat=row.get("lat"), lon=row.get("lon"),
        travel_minutes_from_previous=travel[0] if travel else None,
        travel_mode=travel[1] if travel else None,
        sources=sources,
    )


def build_night(brief: Brief, seed: int | None = None,
                exclude: set[str] | None = None,
                pin: dict[str, str] | None = None) -> Night | None:
    """Assemble a night from the cache. Returns None if the data cannot cover it.

    None is not a failure: it is the signal for agents.plan_night to fall back
    to the model, which can search the web for what we do not hold.
    """
    rows = catalogue()
    if not rows:
        return None

    rng = random.Random(seed)
    when = brief.date or Date.today()
    kinds = _wanted_kinds(brief)

    chosen: list[tuple[StopKind, dict]] = []
    used: set[str] = set(exclude or ())
    pin = pin or {}
    by_name = {r["name"]: r for r in rows}

    for kind in kinds:
        # A stop the user kept stays exactly where it is while the rest change.
        if (kept := pin.get(kind.value)) and kept in by_name:
            chosen.append((kind, by_name[kept]))
            used.add(kept)
            continue

        options = [r for r in rows if r["name"] not in used and _matches(r, kind, brief)]
        if not options:
            continue
        # Shuffle rather than always taking the first: a planner that returns
        # the same answer every time cannot help anyone out of a rut.
        rng.shuffle(options)

        anchor = chosen[0][1] if chosen else None
        options.sort(key=lambda r: _rank(r, anchor))
        pick = options[0]

        # A night that crosses the city is not a night. Drop a stop only when
        # we KNOW it is too far -- an unknown distance is not a reason to lose
        # a venue, it is a reason to geocode it later.
        if anchor is not None:
            apart = _miles_apart(anchor, pick)
            if apart is not None and apart > MAX_NIGHT_MILES:
                continue
        used.add(pick["name"])
        chosen.append((kind, pick))

    if not chosen:
        return None

    stops: list[Stop] = []
    cursor: datetime | None = None
    previous: dict | None = None

    for kind, row in chosen:
        default_start, minutes = KIND_TIMING[kind]
        hh, mm = (int(x) for x in (brief.start_time or default_start).split(":"))
        wanted = datetime.combine(when, datetime.min.time()).replace(hour=hh, minute=mm)

        travel = None
        if previous is not None:
            gap, mode = _travel_minutes(previous, row)
            travel = (gap, mode) if gap else None
            earliest = cursor + timedelta(minutes=gap or 15) if cursor else wanted
            start = max(wanted, earliest)
        else:
            start = wanted

        end = start + timedelta(minutes=minutes)
        stops.append(_to_stop(row, kind, start, end, travel))
        cursor, previous = end, row

    first, last = chosen[0][1], chosen[-1][1]
    where = first["neighborhood"] or brief.neighborhood or "New York"
    headline = f"{when:%A} in {where}"

    names = [s.name for s in stops]
    if len(names) == 1:
        summary = f"A night at {names[0]}."
    else:
        summary = f"A night that starts at {names[0]}, " + \
                  ", then ".join(names[1:-1] + [f"and ends at {names[-1]}."]) \
                  if len(names) > 2 else f"A night that starts at {names[0]} and ends at {names[1]}."

    return Night(
        summary=summary, headline=headline, dek="",
        date=when, neighborhood=where, vibe=brief.vibe, stops=stops,
    )
