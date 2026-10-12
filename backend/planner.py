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
    Entry, Night, PriceBand, Setting, Source, Stop, StopKind, VenueSize,
)
from linkcheck import verify
from sanitize import classify_booking_url
from sources import lookup_venue, venues
from transit import haversine_miles

COPY_PATH = DATA_DIR / "venue_copy.json"
VENUES_FILE = DATA_DIR / "nyc_venues.json"
CANDIDATES_FILE = DATA_DIR / "candidate_venues.json"

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

# What the button says, by kind of stop. "Book" is wrong for a gallery and
# "Tickets" is wrong for a bar, and a button that misdescribes where it goes is
# worse than a plain one.
BOOKING_LABEL: dict[StopKind, str] = {
    StopKind.DINNER: "Book a table", StopKind.DRINKS: "Visit the bar",
    StopKind.HOTEL_BAR: "Visit the bar", StopKind.CLUB: "Tickets and hours",
    StopKind.SHOW: "Tickets", StopKind.THEATRE: "Tickets",
    StopKind.SCREENING: "Showtimes", StopKind.LATE: "Hours and door",
    StopKind.DESSERT: "Hours", StopKind.TEA: "Hours",
    StopKind.COFFEE: "Hours", StopKind.GALLERY: "What is on",
    StopKind.MUSEUM: "What is on", StopKind.SHOPPING: "Hours",
    StopKind.ACTIVITY: "Details",
}

# Kinds that are usually programmed rather than open-door. Until a venue has
# been checked individually, the card says so rather than implying you can
# turn up. Honest uncertainty beats a confident wrong answer.
# What a stop of each kind should actually be about. The dataset's categories
# are coarse -- "club" covers both a dance floor and a members' room -- so the
# venue's own description is used to tell them apart. A CLUB stop should mean
# music and dancing, not a sofa and a doorman.
KIND_KEYWORDS: dict[StopKind, tuple[str, ...]] = {
    StopKind.CLUB:   ("dance", "dancing", "dj", "djs", "techno", "house",
                      "disco", "dancefloor", "dance floor", "party", "nightclub",
                      "late-night", "soundsystem", "sound system"),
    StopKind.SHOW:   ("live music", "band", "bands", "concert", "gig", "stage",
                      "venue", "jazz", "sets", "performance"),
    StopKind.DRINKS: ("cocktail", "cocktails", "wine", "beer", "bar", "natural wine"),
    StopKind.HOTEL_BAR: ("hotel", "rooftop", "lobby", "terrace"),
    StopKind.DINNER: ("restaurant", "menu", "kitchen", "plates", "dining",
                      "tasting", "trattoria", "cuisine"),
    StopKind.DESSERT: ("ice cream", "dessert", "pastry", "bakery", "gelato",
                       "cake", "sweet", "soft serve"),
    StopKind.TEA:    ("tea", "matcha", "teahouse", "tea room"),
    StopKind.GALLERY: ("gallery", "exhibition", "artist", "opening", "art"),
    StopKind.MUSEUM: ("museum", "collection", "exhibition"),
    StopKind.THEATRE: ("theater", "theatre", "play", "stage", "dance company",
                       "performance"),
    StopKind.SCREENING: ("cinema", "film", "screening", "repertory", "movies"),
    StopKind.SHOPPING: ("shop", "store", "vintage", "records", "books", "market",
                        "boutique"),
}

# A venue whose description says nothing relevant is not rejected, it just
# loses to one that does. Rejecting outright would empty the thinner
# categories entirely.
def _keyword_miss(row: dict, kind: StopKind) -> int:
    """0 when the description matches what this kind of stop is for, 1 when it
    says nothing either way."""
    words = KIND_KEYWORDS.get(kind)
    if not words:
        return 0
    text = f"{row.get('one_line', '')} {row.get('name', '')}".lower()
    if not text.strip():
        return 1
    return 0 if any(w in text for w in words) else 1


TICKETED_KINDS: frozenset[StopKind] = frozenset({
    StopKind.SHOW, StopKind.THEATRE, StopKind.SCREENING, StopKind.CLUB,
})

PRICE_CEILING = {
    PriceBand.FREE: 0.0, PriceBand.CHEAP: 25.0, PriceBand.MODERATE: 60.0,
    PriceBand.SPENDY: 120.0, PriceBand.SPLURGE: 250.0,
}

WALK_MINUTES_PER_MILE = 20

# New York is a grid, so you cannot cut the diagonal between two points. A
# straight line underestimates a real walk by roughly a third, which is the
# difference between "two minutes" and actually arriving on time.
GRID_FACTOR = 1.32

# Travel is reported in the increments people actually think in. "Twelve
# minutes" is a number; "fifteen minutes" is a plan.
TRAVEL_BUCKETS = (5, 15, 30, 60)


def _bucket_travel(minutes: float) -> int:
    """Round a journey to 5, 15, 30 or 60 minutes, whichever is nearest."""
    if minutes <= 0:
        return TRAVEL_BUCKETS[0]
    return min(TRAVEL_BUCKETS, key=lambda b: (abs(b - minutes), b))


def _round_clock(moment: datetime) -> datetime:
    """Round a start time up to the next quarter hour.

    A plan that says 9:02 reads like a train timetable. Rounding up rather
    than to nearest also means the time printed is never earlier than the
    journey actually allows.
    """
    if moment.minute % 15 == 0 and moment.second == 0:
        return moment.replace(second=0, microsecond=0)
    add = 15 - (moment.minute % 15)
    return (moment + timedelta(minutes=add)).replace(second=0, microsecond=0)

# The whole night should fit inside a believable radius of the first stop.
# Beyond this it stops being an evening and becomes a commute.
MAX_NIGHT_MILES = 2.5

# When someone explicitly wants to range across the city. Still bounded: an
# unbounded night is a night spent on the train.
ROAM_NIGHT_MILES = 7.0


def _same_area(a: dict, b: dict) -> int:
    """Geographic closeness without coordinates: 0 same neighborhood,
    1 same borough, 2 different borough.

    New Yorkers are acutely aware of travel time, and until a venue is
    geocoded the mileage check cannot run at all. This is the fallback that
    stops a plan sending someone from the Lower East Side to Williamsburg
    between courses just because neither venue has a latitude yet.
    """
    an, bn = (a.get("neighborhood") or "").lower(), (b.get("neighborhood") or "").lower()
    if an and an == bn:
        return 0
    ab, bb = (a.get("borough") or "").lower(), (b.get("borough") or "").lower()
    if ab and ab == bb:
        return 1
    return 2


def _miles_apart(a: dict, b: dict) -> float | None:
    """Distance between two venues, or None when either cannot be placed.

    None means unknown, not far. An earlier version returned 99 miles for a
    missing coordinate, which quietly dropped every venue we had not geocoded
    yet -- and that is most of them, so multi-stop nights collapsed to one.
    """
    if None in (a.get("lat"), a.get("lon"), b.get("lat"), b.get("lon")):
        return None
    return haversine_miles(a["lat"], a["lon"], b["lat"], b["lon"])


def _incompleteness(row: dict) -> int:
    """How much of a card this venue cannot fill: 0 best, 2 worst.

    A stop with no coordinates draws no map and no walk time, and one with no
    website shows no button. Both are honest omissions, but a plan full of
    them looks broken, so a complete record wins a tie. Nothing is invented to
    fill the gap; we simply prefer the venues we actually know more about.
    """
    return (row.get("lat") is None) + (not row.get("website"))


def _style_miss(row: dict, style: list[str]) -> int:
    """How badly a venue misses what was asked for: 0 best, 2 worst.

    Three tiers, because a structured tag is a stronger signal than a word
    that happens to appear in a sentence:

        0  a cuisine or genre tag matches     "techno" vs genre=["techno"]
        1  the description mentions it        "techno" appears in the prose
        2  nothing matches

    Tiered rather than binary so a request still returns something when
    nothing in the city matches exactly, rather than an empty page.
    """
    if not style:
        return 0

    wanted = [w.lower().strip() for w in style if w.strip()]
    if not wanted:
        return 0

    tags = {t.lower() for t in (row.get("cuisine") or []) + (row.get("genre") or [])}
    if tags and any(w in t or t in w for w in wanted for t in tags):
        return 0

    text = f"{row.get('one_line', '')} {row.get('name', '')}".lower()
    if text.strip() and any(w in text for w in wanted):
        return 1

    return 2


def _rank(row: dict, anchor: dict | None, kind: StopKind,
          max_miles: float = MAX_NIGHT_MILES,
          style: list[str] | None = None) -> tuple:
    """Sort key: right kind of place, then near, then well documented.

    Order matters. Relevance comes first because a nearby venue that is the
    wrong sort of place is not a better answer than a right one ten minutes
    away. Proximity comes second because the less time spent travelling, the
    more of the night is actually spent somewhere.
    """
    # Asked-for style comes first. Someone who said "techno" would rather
    # travel ten minutes for a techno room than walk two minutes to a room
    # playing something else.
    style_miss = _style_miss(row, style or [])
    miss = _keyword_miss(row, kind)
    incomplete = _incompleteness(row)

    if anchor is None:
        return (style_miss, miss, 0, incomplete, 0.0)

    distance = _miles_apart(anchor, row)
    if distance is None:
        area = _same_area(anchor, row)
        return (style_miss, miss, area, incomplete, 50.0 + area)

    band = 0 if distance <= max_miles else 2
    return (style_miss, miss, band, incomplete, round(distance, 2))


@lru_cache(maxsize=1)
def venue_copy() -> dict[str, dict]:
    """Editorial copy written once, offline, keyed by venue name."""
    if not COPY_PATH.is_file():
        return {}
    try:
        return json.loads(COPY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _data_fingerprint() -> tuple:
    """Modification times of the files the catalogue is built from.

    Used as the cache key so rebuilding the dataset takes effect without a
    restart. An earlier version cached on nothing, so after an hour of
    geocoding the running app was still serving the old coordinates and every
    plan came back without a map.
    """
    out = []
    for path in (VENUES_FILE, CANDIDATES_FILE):
        try:
            out.append(path.stat().st_mtime_ns)
        except OSError:
            out.append(0)
    return tuple(out)


def catalogue() -> list[dict[str, Any]]:
    """Every venue we can place, from both datasets, flattened."""
    return _catalogue_cached(_data_fingerprint())


@lru_cache(maxsize=2)
def _catalogue_cached(fingerprint: tuple) -> list[dict[str, Any]]:
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
            "cuisine": [], "genre": [],
        })

    if CANDIDATES_FILE.is_file():
        try:
            for v in json.loads(CANDIDATES_FILE.read_text(encoding="utf-8")).get("venues", []):
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
                    "cuisine": v.get("cuisine") or [],
                    "genre": v.get("genre") or [],
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
        spend = PRICE_CEILING.get(row["price_band"], 0)
        ceiling = brief.budget.ceiling_usd
        if ceiling is not None and spend > ceiling:
            return False
        # A budget is a target, not only a limit. Someone who says "high end"
        # is asking to be taken somewhere good, so a $ dive is as wrong an
        # answer as a $$$$ one is for someone who said cheap.
        if brief.budget is Budget.SPENDY and spend < PRICE_CEILING[PriceBand.MODERATE]:
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
    miles = haversine_miles(a["lat"], a["lon"], b["lat"], b["lon"]) * GRID_FACTOR
    if miles <= 0.9:
        return _bucket_travel(miles * WALK_MINUTES_PER_MILE), "walk"
    if miles <= 4:
        return _bucket_travel(max(10, miles * 6)), "subway"
    return _bucket_travel(max(15, miles * 4)), "cab"


def _to_stop(row: dict, kind: StopKind, start: datetime, end: datetime | None,
             travel: tuple[int, str] | None) -> Stop:
    """Build one stop. Also decides whether it can honestly be called a SHOW.

    The schema requires a SHOW to state its room size, because the size of the
    room is the product's whole promise. Most venues in the discovered dataset
    have no capacity on file, so rather than fail the plan or invent a number,
    such a stop is reported as a late one instead. Demoting the label is
    honest; guessing the capacity would not be.
    """
    size = row.get("size")
    if size is None:
        known = lookup_venue(row["name"])
        if known is not None:
            size = known.size
            row = {**row, "size": size, "capacity": known.main_space.capacity}
    if kind is StopKind.SHOW and size is None:
        kind = StopKind.LATE

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
    # The venue's own page. The About page promises every button opens the
    # venue's own site, and this is where that promise is kept. Anything that
    # fails the allowlist check is dropped downstream rather than shown.
    booking_url = booking_label = None
    if (site := row.get("website")) and str(site).startswith("https://"):
        verdict, _ = classify_booking_url(str(site))
        # Two gates. The allowlist stops a lookalike domain; the link check
        # stops a real domain that opens the wrong venue. Cache only, so this
        # never adds time to a request.
        if verdict in {"trusted", "venue"} and verify(str(site), row["name"], allow_fetch=False):
            booking_url = str(site)
            booking_label = BOOKING_LABEL.get(kind, "Visit")

    return Stop(
        name=row["name"], kind=kind, neighborhood=row["neighborhood"] or "New York",
        start_time=start.strftime("%H:%M"),
        end_time=end.strftime("%H:%M") if end else None,
        why=why[:320], order_this=copy.get("order_this"),
        venue_size=row["size"], capacity=row["capacity"],
        setting=row["setting"], price_band=row["price_band"],
        entry=(Entry(row["entry"]) if row.get("entry")
               else (Entry.TICKETED if kind in TICKETED_KINDS else Entry.WALK_IN)),
        lat=row.get("lat"), lon=row.get("lon"),
        travel_minutes_from_previous=travel[0] if travel else None,
        travel_mode=travel[1] if travel else None,
        booking_url=booking_url, booking_label=booking_label,
        sources=sources,
    )


def _pick_area(rows: list[dict], kinds: list[StopKind], brief: Brief,
               rng: random.Random) -> str | None:
    """Choose the borough the night happens in, before choosing any venue.

    Picking a restaurant first and then hoping a club is nearby produces
    either a cross-city plan or a plan missing its second half. Deciding the
    area first guarantees both: everything that follows is already local.

    Prefers a borough that can satisfy every kind asked for. Falls back to the
    one that covers the most.
    """
    if brief.borough:
        return brief.borough

    boroughs: dict[str, set[StopKind]] = {}
    for row in rows:
        b = row.get("borough")
        if not b:
            continue
        for kind in kinds:
            if row["category"] in KIND_CATEGORIES.get(kind, ()):
                boroughs.setdefault(b, set()).add(kind)

    if not boroughs:
        return None

    best = max(len(v) for v in boroughs.values())
    complete = [b for b, v in boroughs.items() if len(v) == best]
    # Weight by how much there is to choose from, so Manhattan and Brooklyn
    # come up more often than Staten Island without ever excluding it.
    weights = [sum(1 for r in rows if r.get("borough") == b) for b in complete]
    return rng.choices(complete, weights=weights, k=1)[0]


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

    # Someone who asks to bounce around the city is asking for a wider night,
    # so the radius opens up. Everyone else gets the tight one, because the
    # less time spent travelling, the more places you actually get to.
    roaming = bool(getattr(brief, "roam", False))
    max_miles = ROAM_NIGHT_MILES if roaming else MAX_NIGHT_MILES

    # Decide where the night happens before deciding what is in it.
    area = None if roaming else _pick_area(rows, kinds, brief, rng)
    if area:
        local = [r for r in rows if (r.get("borough") or "").lower() == area.lower()]
        if len(local) >= len(kinds):
            rows = local

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
        options.sort(key=lambda r: _rank(r, anchor, kind, max_miles, brief.style))
        pick = options[0]

        # A night that crosses the city is not a night.
        if anchor is not None:
            apart = _miles_apart(anchor, pick)
            if apart is not None:
                if apart > max_miles:
                    continue
            elif not roaming and _same_area(anchor, pick) == 2:
                # Different boroughs, and no coordinates to prove it is close.
                # Leave the stop out rather than put someone on a long train
                # ride they did not ask for.
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
            start = _round_clock(max(wanted, earliest))
        else:
            start = _round_clock(wanted)

        end = start + timedelta(minutes=minutes)
        stops.append(_to_stop(row, kind, start, end, travel))
        cursor, previous = end, row

    # Name every neighborhood the night touches, in the order you reach them.
    # Saying only the first is how someone ends up surprised by a train ride
    # they did not agree to.
    seen: list[str] = []
    for _, row in chosen:
        hood = (row.get("neighborhood") or "").strip()
        if hood and hood not in seen:
            seen.append(hood)

    if not seen:
        where = brief.neighborhood or brief.borough or "New York"
    elif len(seen) == 1:
        where = seen[0]
    elif len(seen) == 2:
        where = f"{seen[0]} and {seen[1]}"
    else:
        where = ", ".join(seen[:-1]) + f" and {seen[-1]}"

    headline = f"{when:%A} in {where}"

    names = [s.name for s in stops]
    if len(names) == 1:
        summary = f"A night at {names[0]}."
    elif len(names) == 2:
        summary = f"A night that starts at {names[0]} and ends at {names[1]}."
    else:
        middle = ", then ".join(names[1:-1])
        summary = (f"A night that starts at {names[0]}, then {middle}, "
                   f"and ends at {names[-1]}.")

    return Night(
        summary=summary, headline=headline, dek="",
        date=when, neighborhood=where, vibe=brief.vibe, stops=stops,
    )
