"""The Brief: what the Concierge extracts from "what's your vibe?".

The chat is the input, so the first agent's whole job is turning free text into
something the planner can act on -- and then asking for what is genuinely
missing, rather than interrogating everyone through the same form.

That restraint is the design. "Friday, 8 of us, Bushwick, under $50" is a
complete brief and should produce a plan immediately. "something fun" needs two
questions. Asking a user what they already told you is how an assistant stops
feeling like one.
"""

from __future__ import annotations

from datetime import date as Date
from enum import Enum

from models import PriceBand, Setting, StopKind, VenueSize
from pydantic import BaseModel, Field


class Occasion(str, Enum):
    """Why they are going out. Changes what a good answer looks like.

    A birthday for twelve is a different search from a second date, even with
    an identical vibe string: it needs a room that takes groups, somewhere to
    put coats, and a table nobody has to shout across.
    """

    CASUAL = "casual"
    DATE = "date"
    BIRTHDAY = "birthday"
    CELEBRATION = "celebration"
    FRIENDS_VISITING = "friends_visiting"
    SOLO = "solo"
    WORK = "work"


class Budget(str, Enum):
    """Per person, for the whole night, door and dinner included."""

    FREE = "free"            # $0 - gallery openings, free shows
    CHEAP = "under_40"
    MODERATE = "40_to_90"
    SPENDY = "90_to_200"
    NO_LIMIT = "no_limit"

    @property
    def ceiling_usd(self) -> float | None:
        return {"free": 0.0, "under_40": 40.0, "40_to_90": 90.0,
                "90_to_200": 200.0, "no_limit": None}[self.value]

    @property
    def label(self) -> str:
        return {"free": "Free", "under_40": "Under $40", "40_to_90": "$40–90",
                "90_to_200": "$90–200", "no_limit": "No limit"}[self.value]


class Brief(BaseModel):
    """A plannable request. Only `vibe` is ever required."""

    vibe: str = Field(description="Their words, kept verbatim. The editorial voice echoes this back.")

    date: Date | None = None
    start_time: str | None = Field(default=None, description="HH:MM, when they want to start")
    neighborhood: str | None = None
    borough: str | None = None

    party_size: int | None = Field(default=None, ge=1, le=60)
    occasion: Occasion | None = None
    budget: Budget | None = None

    venue_sizes: list[VenueSize] = Field(default_factory=list)
    settings: list[Setting] = Field(default_factory=list)
    wants: list[StopKind] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list, description="Named dislikes: 'no techno', 'not a dive'")

    style: list[str] = Field(
        default_factory=list,
        description=(
            "The descriptive words that say what KIND of place, not what kind "
            "of stop. 'techno', 'natural wine', 'jazz', 'dive', 'speakeasy', "
            "'omakase', 'rooftop', 'burlesque', 'vinyl'. Lowercase, their own "
            "words, no synonyms invented. This is what makes one request "
            "different from another once the structure matches."
        ),
    )

    roam: bool = Field(
        default=False,
        description=(
            "True only when they say they want to range across the city: "
            "'bounce around', 'explore', 'all over town', 'show me the city'. "
            "Default false, because a tighter night fits in more stops."
        ),
    )

    @property
    def is_group(self) -> bool:
        """Six is where reservations get hard and most rooms stop being an
        option, so it is the threshold that changes the search."""
        return bool(self.party_size and self.party_size >= 6)

    def missing_critical(self) -> list[str]:
        """Fields worth one follow-up question, in priority order.

        Deliberately short. Date and neighborhood change the result set; the
        rest can be inferred or left open without producing a bad plan.
        Party size only matters once it is large enough to constrain the room,
        which is exactly when the user tends to mention it anyway.
        """
        gaps: list[str] = []
        if self.date is None:
            gaps.append("date")
        if not (self.neighborhood or self.borough):
            gaps.append("area")
        if self.occasion in {Occasion.BIRTHDAY, Occasion.CELEBRATION} and self.party_size is None:
            gaps.append("party_size")
        return gaps

    def constraints_summary(self) -> str:
        """One line for the page, so the user can see what it understood."""
        bits: list[str] = []
        if self.date:
            bits.append(self.date.strftime("%a %-d %b"))
        if self.neighborhood or self.borough:
            bits.append(self.neighborhood or self.borough or "")
        if self.party_size:
            bits.append(f"party of {self.party_size}")
        if self.budget:
            bits.append(self.budget.label)
        if self.venue_sizes:
            bits.append("/".join(v.value for v in self.venue_sizes))
        if self.settings:
            bits.append("/".join(s.value for s in self.settings))
        return " · ".join(b for b in bits if b)


# Questions the Concierge may ask, one per gap. Written to sound like a person
# who is already working on it, not a form that needs completing.
FOLLOW_UPS: dict[str, str] = {
    "date": "What night are we talking about?",
    "area": "Anywhere in particular, or should I range across the city?",
    "party_size": "How many of you?",
}

MAX_FOLLOW_UPS = 2  # Two questions is help. Four is a form.


def next_questions(brief: Brief) -> list[str]:
    return [FOLLOW_UPS[g] for g in brief.missing_critical()[:MAX_FOLLOW_UPS]]
