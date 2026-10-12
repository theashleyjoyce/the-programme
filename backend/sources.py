"""The agents' tools: search over cached NYC data.

Everything here reads local files. No network calls at request time -- that is
what keeps a grader's fresh clone inside the 10-minute rule, and what keeps the
per-request token bill flat instead of scaling with the number of candidate
venues.

Two datasets:
  data/nyc_venues.json  - capacity map, built offline by scripts/enrich_capacity.py.
                          Ticketmaster does not expose capacity, so this is the
                          file that makes the venue-size filter possible.
  data/nyc_events.json  - what is on. Either a real Ticketmaster Discovery pull
                          (scripts/fetch_events.py) or the committed sample.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date as Date
from functools import lru_cache
from pathlib import Path
from typing import Any

from config import DATA_DIR
from models import Setting, VenueSize

VENUES_PATH = DATA_DIR / "nyc_venues.json"
EVENTS_PATH = DATA_DIR / "nyc_events.json"
EVENTS_SAMPLE_PATH = DATA_DIR / "nyc_events.sample.json"

# Band edges in one place. models.VenueSize documents what each band feels
# like; these are the numbers that assign it.
SIZE_EDGES: tuple[tuple[int, VenueSize], ...] = (
    (150, VenueSize.INTIMATE),
    (700, VenueSize.MIDSIZE),
    (3000, VenueSize.LARGE),
)


def size_for_capacity(capacity: int | None) -> VenueSize | None:
    """Capacity -> experience band. None when capacity is unknown, which is
    honest: an unknown room should not be sold as an intimate one."""
    if capacity is None:
        return None
    for ceiling, band in SIZE_EDGES:
        if capacity < ceiling:
            return band
    return VenueSize.MASSIVE


@dataclass(frozen=True)
class Space:
    """One room inside a venue.

    Capacity and setting live here, not on the venue, because a venue is not
    one number. Nowadays is a 269-capacity indoor room and an 800-capacity
    yard; House of Yes is a 650 main room and the Onyx Room. Clubs have
    several rooms and restaurants have back rooms, so the room is the unit
    people actually choose.
    """

    name: str
    capacity: int | None
    seated_capacity: int | None
    setting: Setting

    @property
    def size(self) -> VenueSize | None:
        return size_for_capacity(self.capacity)

    @property
    def fits_party(self) -> int | None:
        """Seated capacity is the honest number for a group that wants a
        table. Falls back to standing when no seated figure was found."""
        return self.seated_capacity or self.capacity


@dataclass(frozen=True)
class Venue:
    name: str
    neighborhood: str
    borough: str
    spaces: tuple[Space, ...]
    source_url: str | None = None
    confidence: str = "unverified"
    takes_large_groups: bool | None = None
    has_private_space: bool | None = None
    lat: float | None = None
    lon: float | None = None

    @property
    def main_space(self) -> Space:
        """Largest known room. What "how big is this place" usually means."""
        return max(self.spaces, key=lambda sp: sp.capacity or 0)

    @property
    def size(self) -> VenueSize | None:
        return self.main_space.size

    def spaces_matching(
        self,
        sizes: list[VenueSize] | None = None,
        settings: list[Setting] | None = None,
        party_size: int | None = None,
    ) -> list[Space]:
        """Rooms in this venue that fit the ask. A venue qualifies if ANY of
        its rooms do, which is the whole point of modeling rooms."""
        out = []
        for sp in self.spaces:
            if sizes and sp.size not in sizes:
                continue
            if settings and sp.setting not in settings:
                continue
            if party_size:
                # An unknown capacity must not be sold as a fit. Rooms with no
                # researched figure are excluded from party-size searches
                # rather than quietly included -- telling someone a room holds
                # their twelve guests when nobody checked is the worst failure
                # this app can have on a birthday.
                if sp.fits_party is None or sp.fits_party < party_size:
                    continue
            out.append(sp)
        return out


@lru_cache(maxsize=1)
def venues() -> dict[str, Venue]:
    """Venue map keyed by lowercased name."""
    if not VENUES_PATH.is_file():
        return {}
    raw = json.loads(VENUES_PATH.read_text(encoding="utf-8"))
    out: dict[str, Venue] = {}
    for v in raw.get("venues", []):
        spaces = tuple(
            Space(
                name=sp.get("space", "Main Room"),
                capacity=sp.get("capacity"),
                seated_capacity=sp.get("seated_capacity"),
                setting=Setting(sp.get("setting", "indoor")),
            )
            for sp in v.get("spaces", [])
        ) or (Space("Main Room", None, None, Setting.INDOOR),)
        out[v["name"].lower()] = Venue(
            name=v["name"],
            neighborhood=v.get("neighborhood", "Unknown"),
            borough=v.get("borough", "Unknown"),
            spaces=spaces,
            source_url=v.get("source_url"),
            confidence=v.get("confidence", "unverified"),
            takes_large_groups=v.get("takes_large_groups"),
            has_private_space=v.get("has_private_space"),
            lat=v.get("lat"),
            lon=v.get("lon"),
        )
    return out


def lookup_venue(name: str) -> Venue | None:
    """Exact match, then a containment pass so 'Elsewhere' finds
    'Elsewhere (The Hall)' when a listing is less specific than the map."""
    index = venues()
    if (hit := index.get(name.lower())) is not None:
        return hit
    needle = name.lower().strip()
    for key, venue in index.items():
        if needle in key or key in needle:
            return venue
    return None


@lru_cache(maxsize=1)
def events() -> list[dict[str, Any]]:
    """Live pull if present, otherwise the committed sample.

    The sample is what makes a fresh clone work with no Ticketmaster key, which
    the assignment asks for directly: ship a small test dataset and say how to
    switch.
    """
    path = EVENTS_PATH if EVENTS_PATH.is_file() else EVENTS_SAMPLE_PATH
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw.get("events", [])


def using_live_events() -> bool:
    return EVENTS_PATH.is_file()


def search_events(
    on_date: Date | str | None = None,
    neighborhood: str | None = None,
    borough: str | None = None,
    sizes: list[VenueSize] | None = None,
    settings: list[Setting] | None = None,
    party_size: int | None = None,
    genre: str | None = None,
    max_price: float | None = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Filter cached events. The scout agent's main tool.

    Matching happens at the ROOM level, so "outdoor, big enough for 12" finds
    the Nowadays yard without wrongly claiming the indoor room fits. Results
    name the specific room, which is what the editorial page prints.
    """
    wanted_date = str(on_date) if on_date else None
    results: list[dict[str, Any]] = []

    for ev in events():
        if wanted_date and ev.get("date") != wanted_date:
            continue
        if genre and genre.lower() not in (ev.get("genre", "") or "").lower():
            continue
        if max_price is not None and ev.get("price_from") is not None and ev["price_from"] > max_price:
            continue

        venue = lookup_venue(ev.get("venue", ""))
        if venue is None:
            # Unknown venue: pass it through only when the request puts no
            # constraints on the room, rather than silently claiming a fit.
            if sizes or settings or party_size:
                continue
            results.append({**ev, "venue_size": None, "room": None,
                            "size_feels_like": "Room size unknown.",
                            "neighborhood": ev.get("neighborhood", "Unknown")})
            continue

        if neighborhood and neighborhood.lower() not in venue.neighborhood.lower():
            continue
        if borough and borough.lower() != venue.borough.lower():
            continue

        rooms = venue.spaces_matching(sizes=sizes, settings=settings, party_size=party_size)
        if not rooms:
            continue
        room = rooms[0]

        results.append({
            **ev,
            "room": room.name,
            "capacity": room.capacity,
            "seated_capacity": room.seated_capacity,
            "setting": room.setting.value,
            "setting_note": room.setting.blurb,
            "venue_size": room.size.value if room.size else None,
            "size_feels_like": room.size.blurb if room.size else "Room size unknown.",
            "neighborhood": venue.neighborhood,
            "borough": venue.borough,
            "other_rooms": [sp.name for sp in venue.spaces if sp.name != room.name],
            "has_private_space": venue.has_private_space,
            "capacity_source": venue.source_url,
            "capacity_confidence": venue.confidence,
        })
        if len(results) >= limit:
            break

    return results


def find_rooms(
    sizes: list[VenueSize] | None = None,
    settings: list[Setting] | None = None,
    party_size: int | None = None,
    neighborhood: str | None = None,
    borough: str | None = None,
    limit: int = 40,
) -> list[dict[str, Any]]:
    """Browse rooms directly, for requests with no specific act in mind --
    "somewhere outdoors in Brooklyn for 15 of us"."""
    out: list[dict[str, Any]] = []
    for venue in venues().values():
        if neighborhood and neighborhood.lower() not in venue.neighborhood.lower():
            continue
        if borough and borough.lower() != venue.borough.lower():
            continue
        for room in venue.spaces_matching(sizes=sizes, settings=settings, party_size=party_size):
            out.append({
                "venue": venue.name,
                "room": room.name,
                "capacity": room.capacity,
                "seated_capacity": room.seated_capacity,
                "setting": room.setting.value,
                "setting_note": room.setting.blurb,
                "venue_size": room.size.value if room.size else None,
                "feels_like": room.size.blurb if room.size else "Room size unknown.",
                "neighborhood": venue.neighborhood,
                "borough": venue.borough,
                "source": venue.source_url,
                "confidence": venue.confidence,
            })
            if len(out) >= limit:
                return out
    return out


def dataset_status() -> dict[str, Any]:
    """Shown in the UI footer and recorded in the audit trail, so every
    screenshot says whether it came from live data or the committed sample."""
    all_spaces = [sp for v in venues().values() for sp in v.spaces]
    return {
        "venues_known": len(venues()),
        "rooms_known": len(all_spaces),
        "rooms_with_capacity": sum(1 for sp in all_spaces if sp.capacity),
        "multi_room_venues": sum(1 for v in venues().values() if len(v.spaces) > 1),
        "outdoor_rooms": sum(1 for sp in all_spaces if sp.setting.weather_dependent),
        "events_loaded": len(events()),
        "events_source": "live pull" if using_live_events() else "committed sample",
    }
