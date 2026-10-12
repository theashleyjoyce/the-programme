"""The Critic: reads a finished plan and says whether it is actually good.

The planner is deterministic, which makes it fast and predictable and means it
cannot notice when the output does not work as an evening. It matched
categories, respected the filters and kept the stops close together; it has no
way of seeing that "somewhere quiet, we want to talk" was answered with a
650-capacity room, or that forty-five minutes is not enough for dinner before
a nine o'clock door.

So a second agent reads the plan the way a person would. If it objects to one
stop, the planner rebuilds without it. The pattern is deliberately narrow:
the Critic judges, it never writes, and the deterministic planner stays in
charge of what a plan may contain.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    APPROVE = "approve"
    RESHUFFLE = "reshuffle"      # one stop is wrong; name it
    REJECT = "reject"            # the whole plan misses the brief


class Objection(BaseModel):
    """One specific thing wrong, in terms a person would recognise."""

    stop: str | None = Field(
        default=None, description="Venue name, or null if it is about the whole night")
    problem: str = Field(
        max_length=200,
        description="What is wrong, in one sentence. Concrete, not a matter of taste.")


class Critique(BaseModel):
    verdict: Verdict
    reasoning: str = Field(
        max_length=300,
        description="One or two sentences. Why this verdict, in plain language.")
    objections: list[Objection] = Field(default_factory=list, max_length=3)
    worst_stop: str | None = Field(
        default=None,
        description="For a reshuffle: the exact venue name to drop. Null otherwise.")


def plan_as_text(night, brief) -> str:
    """The plan, as the Critic sees it. Deliberately plain: judging prose is
    not the job, judging the evening is."""
    lines = [
        f"THEY ASKED FOR: \"{brief.vibe}\"",
        f"  date: {brief.date or 'unspecified'}"
        f"   party: {brief.party_size or 'unspecified'}"
        f"   occasion: {brief.occasion.value if brief.occasion else 'none'}",
        f"  budget: {brief.budget.label if brief.budget else 'unspecified'}"
        f"   style: {', '.join(brief.style) or 'none stated'}",
        f"  wants: {', '.join(w.value for w in brief.wants) or 'not specified'}",
        "",
        "THE PLAN:",
    ]
    for i, s in enumerate(night.stops, 1):
        bits = [f"{i}. {s.start_time}" + (f"–{s.end_time}" if s.end_time else ""),
                s.name, f"[{s.kind.value}]", s.neighborhood]
        if s.venue_size:
            bits.append(f"{s.venue_size.value}")
        if s.capacity:
            bits.append(f"cap {s.capacity}")
        if s.setting:
            bits.append(s.setting.value)
        if s.price_band:
            bits.append(s.price_band.value)
        if s.travel_minutes_from_previous:
            bits.append(f"({s.travel_minutes_from_previous} min "
                        f"{s.travel_mode or 'travel'} from the last stop)")
        lines.append("   " + "  ".join(bits))
        lines.append(f"      {s.why}")
    return "\n".join(lines)
