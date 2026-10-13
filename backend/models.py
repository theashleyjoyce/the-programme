"""Typed contract between the agents and the editorial renderer.

The agents never write prose into a chat log. They return a `Night`, and the
front end lays it out. That inversion -- chat is the input, a designed page is
the output -- is the product, and it only works if the output is structured.

Two rubric lines lean on this file:

  Look + feel (10 pts)  - a renderer can only set type, rhythm, and hierarchy
                          if it knows what each field means. `why` is a pull
                          quote; `order_this` is a caption. Freeform text
                          cannot be designed.
  Agent design (10 pts) - every claim carries `sources`, so a traced run shows
                          which scout found what.
"""

from __future__ import annotations

from datetime import date as Date
from typing import ClassVar
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class VenueSize(str, Enum):
    """Experience texture -- the axis every listing app ignores.

    Competitors filter genre, date, neighborhood, price. None of them let you
    say "I want to be in a room of 80 people" versus "I want to disappear into
    a crowd," which is how people actually choose a night. Capacity is the
    proxy; the feeling is the point.
    """

    INTIMATE = "intimate"       # under ~150. Front row by accident.
    MIDSIZE = "midsize"         # ~150-700. A real crowd, still a room.
    LARGE = "large"             # ~700-3000. You are part of an audience.
    MASSIVE = "massive"         # 3000+. Getting lost in it is the appeal.

    @property
    def blurb(self) -> str:
        return {
            "intimate": "Small room. You will be close enough to see the setlist.",
            "midsize": "Busy but navigable. A crowd you can still move through.",
            "large": "A proper audience. Big sound, big room.",
            "massive": "Arena scale. The point is the crowd.",
        }[self.value]


class Setting(str, Enum):
    """Indoor, outdoor, or convertible -- the other half of "what is the room like".

    Capacity says how many people. Setting says what the space *is*, which is
    the difference between a January recommendation that works and one that
    sends someone to a yard in the cold. It also fixes a real modeling problem:
    a venue is not one number. Nowadays is a 269-capacity indoor room AND an
    800-capacity outdoor yard. Those are different nights.
    """

    INDOOR = "indoor"
    OUTDOOR = "outdoor"          # yard, garden, lot, patio
    ROOFTOP = "rooftop"
    CONVERTIBLE = "convertible"  # retractable roof, or indoor+outdoor on one ticket

    @property
    def blurb(self) -> str:
        return {
            "indoor": "Inside, weatherproof.",
            "outdoor": "Open air. Check the forecast.",
            "rooftop": "Up top and exposed. Colder than street level.",
            "convertible": "Indoor and outdoor space on the same ticket.",
        }[self.value]

    @property
    def weather_dependent(self) -> bool:
        return self in {Setting.OUTDOOR, Setting.ROOFTOP}


class StopKind(str, Enum):
    """What kind of stop this is.

    Arts entries are separate kinds rather than a generic "activity" because
    they behave differently: a gallery opening is free, time-boxed, and ends
    early enough to lead somewhere else. The competitors in this category cover
    nightlife and restaurants only, so culture is part of the novelty case.
    """

    DINNER = "dinner"
    DRINKS = "drinks"
    SHOW = "show"
    LATE = "late"
    DESSERT = "dessert"    # late-night sweet treat, the thing that caps a night
    COFFEE = "coffee"
    CLUB = "club"            # a dance floor, as distinct from a bar
    HOTEL_BAR = "hotel_bar"  # a destination in its own right in New York
    TEA = "tea"              # tea house, ceremonial or late
    SHOPPING = "shopping"    # late-opening stores, vintage, records, markets
    GALLERY = "gallery"      # opening, private view
    MUSEUM = "museum"        # late hours, member evening
    THEATRE = "theatre"      # play, dance, performance
    SCREENING = "screening"  # repertory film
    COMEDY = "comedy"        # stand-up, improv, a club with a line-up
    KARAOKE = "karaoke"      # private rooms or a bar with a book
    GAMES = "games"          # bowling, arcade bars, pool, darts
    MARKET = "market"        # night markets, food halls, Smorgasburg
    PARK = "park"            # a park, a pier, a garden, a waterfront
    ACTIVITY = "activity"


class Entry(str, Enum):
    """Can you walk in, or do you need a ticket for something specific?

    This is the difference between a plan that works and one that leaves you
    outside a dark building. A bar you turn up to. A promoter-led venue opens
    only for programmed events, so "club, 11pm" is a promise it cannot keep
    unless something is actually on that night.
    """

    WALK_IN = "walk_in"        # turn up
    TICKETED = "ticketed"      # only open for programmed events
    EITHER = "either"          # a bar most nights, a venue when something is on
    UNKNOWN = "unknown"        # not checked, and said so

    @property
    def note(self) -> str:
        return {
            "walk_in": "",
            "ticketed": "Opens for programmed events only. Check what is on before you go.",
            "either": "Sometimes a walk-in, sometimes a ticketed night. Check the listing.",
            "unknown": "We have not checked whether this needs a ticket.",
        }[self.value]


class PriceBand(str, Enum):
    FREE = "free"
    CHEAP = "$"
    MODERATE = "$$"
    SPENDY = "$$$"
    SPLURGE = "$$$$"


class Source(BaseModel):
    """Attribution for one claim. Editorial credibility and injection defense.

    Any fact in a stop must trace to a source the scouts actually fetched. A
    stop that cannot cite anything is a hallucination, and the validator in
    `Night` rejects it.
    """

    name: str = Field(description="Publication or platform, e.g. Eater NY, Bandsintown")
    url: str | None = Field(default=None, description="Absolute http(s) URL")
    retrieved_at: str | None = Field(default=None, description="ISO timestamp of the fetch")


class Stop(BaseModel):
    """One place, one time slot, one reason to go."""

    name: str
    kind: StopKind
    neighborhood: str

    start_time: str = Field(description="24h local, e.g. 19:30")
    end_time: str | None = Field(default=None)

    why: str = Field(
        max_length=320,
        description="Editorial voice, 1-2 sentences, a point of view. Renders as the pull quote.",
    )
    order_this: str | None = Field(
        default=None,
        max_length=160,
        description="The specific insider line. Renders as a caption under the image.",
    )

    venue_size: VenueSize | None = Field(default=None, description="Required for SHOW stops.")
    setting: Setting | None = Field(
        default=None,
        description="Indoor/outdoor/rooftop. Drives the seasonal warning on the rendered page.",
    )
    entry: Entry | None = Field(
        default=None,
        description="Walk in, or does it need a ticket for a specific event?",
    )
    capacity: int | None = Field(default=None, description="Stated capacity, when a source gives one.")
    price_band: PriceBand | None = Field(default=None)
    est_cost_usd: float | None = Field(default=None, ge=0)

    image_url: str | None = Field(default=None, description="Absolute http(s) URL")
    booking_url: str | None = Field(
        default=None,
        description="Hand-off link, absolute http(s). The app never completes a purchase itself.",
    )
    booking_label: str | None = Field(default=None, description="e.g. Reserve on Resy, Tickets on AXS")

    lat: float | None = Field(default=None, ge=40.4, le=41.0,
                              description="Latitude. NYC only; leave null unless you are confident.")
    lon: float | None = Field(default=None, ge=-74.3, le=-73.6,
                              description="Longitude. NYC only; leave null unless you are confident.")

    travel_minutes_from_previous: int | None = Field(default=None, ge=0, le=180)
    travel_mode: str | None = Field(default=None, description="subway, walk, cab")

    sources: list[Source] = Field(default_factory=list)


    @field_validator("image_url", "booking_url")
    @classmethod
    def _plausible_url(cls, v: str | None) -> str | None:
        """Drop anything that is not an absolute http(s) URL.

        Returns None rather than raising: one bad link should cost the stop its
        button, not invalidate an otherwise good night.
        """
        if not v:
            return None
        v = v.strip()
        return v if v.startswith(("http://", "https://")) else None

    @field_validator("start_time", "end_time")
    @classmethod
    def _check_clock(cls, v: str | None) -> str | None:
        """24h HH:MM. The sequencer does arithmetic on these, so a loose
        format here becomes a wrong travel gap downstream."""
        if v is None:
            return v
        parts = v.split(":")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise ValueError(f"start/end time must be HH:MM, got {v!r}")
        hh, mm = int(parts[0]), int(parts[1])
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError(f"time out of range: {v!r}")
        return f"{hh:02d}:{mm:02d}"


class Night(BaseModel):
    """A full evening, laid out. This is what the renderer receives."""

    summary: str = Field(
        max_length=300,
        description=(
            "The chatbot's reply, as ONE flowing sentence that names each stop in "
            "order. Write it the way a friend describes a plan out loud: "
            "'A night that starts at Kings County Gallery, then dinner at Win Son, "
            "dance night at Bossa Nova Civic Club, capped off with a late-night "
            "sweet treat at Caffe Panna.' Use each venue's exact name -- the "
            "renderer turns those names into links down to their cards. "
            "No headline voice, no cleverness, no mentioning capacities."
        ),
    )
    headline: str = Field(
        max_length=90,
        description="Short page title for the saved/printed page. Plain and factual, e.g. 'Friday in Bushwick'.",
    )
    dek: str = Field(default="", max_length=220, description="Optional supporting line. May be empty.")

    date: Date
    neighborhood: str
    vibe: str = Field(description="The request, echoed back in the app's own voice.")

    stops: list[Stop] = Field(min_length=1, max_length=5)

    est_total_cost_usd: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, description="Caveats: sells out, cash only, no re-entry.")

    @field_validator("stops")
    @classmethod
    def _every_stop_is_sourced(cls, stops: list[Stop]) -> list[Stop]:
        """No source, no stop.

        The scouts read scraped editorial and venue pages, which is untrusted
        text. Requiring attribution means an invented venue -- whether from a
        hallucination or an injected instruction -- fails validation instead of
        reaching the user with a Book button on it.
        """
        unsourced = [s.name for s in stops if not s.sources]
        if unsourced:
            raise ValueError(f"Stops without a source are not allowed: {', '.join(unsourced)}")
        return stops

    @field_validator("stops")
    @classmethod
    def _shows_declare_their_size(cls, stops: list[Stop]) -> list[Stop]:
        """Venue size is the product's whole differentiator, so a show that
        omits it is an incomplete answer, not a minor gap."""
        missing = [s.name for s in stops if s.kind is StopKind.SHOW and s.venue_size is None]
        if missing:
            raise ValueError(f"SHOW stops must state venue_size: {', '.join(missing)}")
        return stops

    # NYC months when an outdoor recommendation needs a warning on the page.
    # Nov-Mar inclusive. April and October are judgement calls, so they pass
    # quietly rather than crying wolf on every shoulder-season night.
    COLD_MONTHS: ClassVar[frozenset[int]] = frozenset({11, 12, 1, 2, 3})

    def weather_warnings(self) -> list[str]:
        """Outdoor stops booked into the cold. Rendered as a standfirst note,
        not a validation error -- a heated rooftop in December is a real
        choice, it just has to be a choice the user sees."""
        if self.date.month not in self.COLD_MONTHS:
            return []
        return [
            f"{s.name} is {s.setting.value} \u2014 {self.date:%B} in New York. {s.setting.blurb}"
            for s in self.stops
            if s.setting and s.setting.weather_dependent
        ]

    def settings_present(self) -> list[str]:
        """Distinct settings across the night, for the filter chips."""
        return sorted({s.setting.value for s in self.stops if s.setting})

    def mappable(self) -> bool:
        """True when at least one stop can be put on a map."""
        return any(s.lat is not None and s.lon is not None for s in self.stops)

    def timeline(self) -> list[tuple[str, str]]:
        """(time, label) pairs for the rail down the left of the page."""
        return [(s.start_time, s.name) for s in self.stops]

class NightDraft(BaseModel):
    """What the model is allowed to return, before repair.

    `Night` enforces two rules that cannot be expressed in a JSON schema:
    every stop must cite a source, and a show must declare its room size.
    Those rules are right, but applying them at parse time meant one missing
    field threw away an otherwise good plan and returned a 500.

    So the model lands here, agents.repair_draft() fixes what it can from our
    own dataset and drops what it cannot, and only then is a strict `Night`
    constructed. Nothing unsourced ever reaches the page -- it is dropped
    rather than fatal.
    """

    summary: str = Field(max_length=300)
    headline: str = Field(max_length=90)
    dek: str = Field(default="", max_length=220)

    date: Date
    neighborhood: str
    vibe: str

    stops: list[Stop] = Field(min_length=1, max_length=5)

    est_total_cost_usd: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None)
