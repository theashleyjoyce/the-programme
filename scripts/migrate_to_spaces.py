"""One-off migration: flat venue capacities -> venues with multiple spaces.

The flat model was wrong and the research data proved it. Five of the first
twelve venues researched have more than one room: Nowadays (indoor room + yard),
Public Records (Sound Room + others), House of Yes (main + Onyx Room), Good Room
(Good Room + Bad Room), Brooklyn Bowl (music room + full event space).

Clubs have multiple rooms and restaurants have back rooms, so "what is this
venue's capacity" is the wrong question. The right one is "which room, how big,
indoors or out, and will they take a party of twelve."
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from config import DATA_DIR  # noqa: E402

PATH = DATA_DIR / "nyc_venues.json"

# Venues whose research notes revealed a second space. Capacities for the
# secondary rooms still need their own lookup; recorded as null rather than
# guessed, so the UI can say "unknown" instead of inventing a number.
KNOWN_MULTI_SPACE: dict[str, list[dict]] = {
    "nowadays": [
        {"space": "Indoor Room", "capacity": 269, "seated_capacity": 188, "setting": "indoor"},
        {"space": "The Yard", "capacity": 800, "seated_capacity": None, "setting": "outdoor"},
    ],
    "public records": [
        {"space": "The Sound Room", "capacity": 200, "seated_capacity": None, "setting": "indoor"},
        {"space": "The Attic", "capacity": None, "seated_capacity": None, "setting": "indoor"},
        {"space": "The Yard", "capacity": None, "seated_capacity": None, "setting": "outdoor"},
    ],
    "house of yes": [
        {"space": "Main Room", "capacity": 650, "seated_capacity": 200, "setting": "indoor"},
        {"space": "Onyx Room", "capacity": None, "seated_capacity": None, "setting": "indoor"},
    ],
    "good room": [
        {"space": "Good Room", "capacity": 500, "seated_capacity": None, "setting": "indoor"},
        {"space": "Bad Room", "capacity": None, "seated_capacity": None, "setting": "indoor"},
    ],
    "brooklyn bowl": [
        {"space": "Music Room", "capacity": 600, "seated_capacity": None, "setting": "indoor"},
        {"space": "Full Venue (buyout)", "capacity": 2500, "seated_capacity": None, "setting": "indoor"},
    ],
    "elsewhere (zone one)": [
        {"space": "Zone One", "capacity": 400, "seated_capacity": None, "setting": "indoor"},
    ],
    "elsewhere (the hall)": [
        {"space": "The Hall", "capacity": 775, "seated_capacity": None, "setting": "indoor"},
        {"space": "The Rooftop", "capacity": 300, "seated_capacity": None, "setting": "rooftop"},
    ],
}

# Rooftop and open-air venues that the flat model recorded as plain indoor.
SETTING_OVERRIDES = {
    "the sultan room": "indoor",      # has a separate rooftop, researched later
    "the brooklyn mirage": "outdoor",
    "knockdown center": "convertible",
}


def main() -> int:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    migrated = []

    for v in data["venues"]:
        key = v["name"].lower()
        spaces = KNOWN_MULTI_SPACE.get(key)
        if spaces is None:
            spaces = [{
                "space": "Main Room",
                "capacity": v.get("capacity"),
                "seated_capacity": None,
                "setting": SETTING_OVERRIDES.get(key, "indoor"),
            }]

        migrated.append({
            "name": v["name"],
            "neighborhood": v.get("neighborhood", "Unknown"),
            "borough": v.get("borough", "Unknown"),
            "spaces": spaces,
            "source_url": v.get("source_url"),
            "confidence": v.get("confidence", "unverified"),
            "notes": v.get("notes"),
            # Null, not false: "we have not checked" is different from "no".
            # The UI must not tell a user a venue refuses groups on no evidence.
            "takes_large_groups": None,
            "has_private_space": len(spaces) > 1 or None,
        })

    migrated.sort(key=lambda v: (v["spaces"][0]["capacity"] or 0))
    data["venues"] = migrated
    data["_schema"] = "venues have one or more spaces; capacity and setting live on the space, not the venue"
    data["_settings"] = ["indoor", "outdoor", "rooftop", "convertible"]
    PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    multi = [v["name"] for v in migrated if len(v["spaces"]) > 1]
    print(f"Migrated {len(migrated)} venues.")
    print(f"Multi-space venues ({len(multi)}): {', '.join(multi)}")
    print(f"Total spaces: {sum(len(v['spaces']) for v in migrated)}")
    unknown = sum(1 for v in migrated for s in v["spaces"] if s["capacity"] is None)
    print(f"Spaces still needing a capacity lookup: {unknown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
