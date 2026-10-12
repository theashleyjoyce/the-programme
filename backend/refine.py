"""Conversational refinement: an amendment to a plan, not a new plan.

Someone looking at a finished night and saying "cheaper" or "swap the second
one" is doing something a form cannot express. This reads the message against
the plan in front of them and returns a structured edit, which the
deterministic planner then applies.

The division is the same as everywhere else in this app: the model handles the
language, Python handles the planning. The model never chooses venues here. It
decides what the person meant, and the planner does the rest.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BriefChanges(BaseModel):
    """Only the fields that actually change. Everything else stays."""

    budget: str | None = Field(
        default=None,
        description="free | under_40 | 40_to_90 | 90_to_200 | no_limit")
    start_time: str | None = Field(default=None, description="HH:MM")
    party_size: int | None = Field(default=None, ge=1, le=60)
    neighborhood: str | None = Field(default=None)
    borough: str | None = Field(default=None)
    venue_sizes: list[str] = Field(
        default_factory=list, description="intimate | midsize | large | massive")
    settings: list[str] = Field(
        default_factory=list, description="indoor | outdoor | rooftop | convertible")
    add_wants: list[str] = Field(
        default_factory=list,
        description="Kinds of stop to add: dinner, drinks, club, show, gallery, "
                    "museum, theatre, screening, dessert, tea, shopping, late, "
                    "hotel_bar, coffee")
    remove_wants: list[str] = Field(default_factory=list)
    style: list[str] = Field(
        default_factory=list,
        description="Descriptive words they used: 'quieter', 'techno', 'natural wine'")
    roam: bool | None = Field(default=None)


class Amendment(BaseModel):
    drop: list[str] = Field(
        default_factory=list, max_length=5,
        description="Exact venue names to remove from the plan")
    keep: list[str] = Field(
        default_factory=list, max_length=5,
        description="Exact venue names to protect")
    brief_changes: BriefChanges = Field(default_factory=BriefChanges)
    reply: str = Field(
        max_length=160,
        description="One sentence back to them. What changed, in the app's voice.")

    @property
    def is_noop(self) -> bool:
        c = self.brief_changes
        return not (self.drop or self.keep or c.budget or c.start_time
                    or c.party_size or c.neighborhood or c.borough
                    or c.venue_sizes or c.settings or c.add_wants
                    or c.remove_wants or c.style or c.roam is not None)
