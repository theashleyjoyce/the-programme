"""Canonical neighbourhood names.

The Scout returns whatever a listing called the place, so one neighbourhood
arrives under many labels: Long Island City also appears as Court Square, Dutch
Kills, Hunters Point, Queens Plaza and Vernon Boulevard. Left alone that splits
a neighbourhood with thirty venues into six with five each, and every one of
them falls below the threshold to appear in the menu at all.

Sub-neighbourhoods are folded into the name people actually use when deciding
where to go. Where a distinction is real to a New Yorker it is kept: East
Harlem is not Central Harlem, and Midtown East is not Midtown West.
"""

from __future__ import annotations

ALIASES: dict[str, str] = {
    # Long Island City and its many names
    "court square": "Long Island City",
    "dutch kills": "Long Island City",
    "hunters point": "Long Island City",
    "hunters point south": "Long Island City",
    "queens plaza": "Long Island City",
    "vernon boulevard": "Long Island City",
    "lic": "Long Island City",

    # Midtown. East and West stay apart; the landmarks fold in.
    "times square": "Theater District",
    "rockefeller center": "Midtown West",
    "midtown south": "Midtown East",
    "midtown": "Midtown East",

    # Harlem. East Harlem is genuinely a different place and stays.
    "west harlem": "Central Harlem",
    "south harlem": "Central Harlem",
    "sugar hill": "Hamilton Heights",

    # Upper East Side
    "carnegie hill": "Upper East Side",
    "lenox hill": "Upper East Side",
    "yorkville": "Upper East Side",

    # Upper West Side
    "lincoln square": "Upper West Side",
    "manhattan valley": "Upper West Side",
    "morningside heights": "Upper West Side",

    # Williamsburg
    "south williamsburg": "Williamsburg",
    "north williamsburg": "Williamsburg",
    "east williamsburg": "East Williamsburg",   # genuinely separate

    # Staten Island
    "stapleton waterfront": "Stapleton",
    "st george": "St. George",

    # Common spellings
    "dumbo": "DUMBO",
    "soho": "SoHo",
    "noho": "NoHo",
    "nolita": "Nolita",
    "tribeca": "Tribeca",
    "bed stuy": "Bedford-Stuyvesant",
    "bed-stuy": "Bedford-Stuyvesant",
    "bedford stuyvesant": "Bedford-Stuyvesant",
    "the bronx": "Bronx",
}


def canonical(name: str | None) -> str:
    """The name people use when deciding where to go."""
    if not name:
        return ""
    key = name.strip().lower().replace("’", "'")
    return ALIASES.get(key, name.strip())
