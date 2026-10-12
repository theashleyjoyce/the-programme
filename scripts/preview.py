"""Render a sample night so the design can be reviewed without burning tokens.

Real venues and real researched capacities from data/nyc_venues.json. The
editorial copy is written by hand here -- this previews the LAYOUT, not the
agents. `python app.py` is what exercises the model.
"""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from brief import Brief, Budget, Occasion          # noqa: E402
from models import (                                # noqa: E402
    Night, PriceBand, Setting, Source, Stop, StopKind, VenueSize,
)
from render import render_night                     # noqa: E402
from sources import dataset_status                  # noqa: E402

brief = Brief(
    vibe="loud and a little sweaty, somewhere we can actually dance",
    date="2026-10-17", neighborhood="Bushwick", party_size=4,
    occasion=Occasion.BIRTHDAY, budget=Budget.CHEAP,
    venue_sizes=[VenueSize.INTIMATE], settings=[Setting.INDOOR],
)

night = Night(
    summary="A birthday night that starts with dinner at Win Son, then drinks on "
            "the roof at Our Wicked Lady, and ends on the floor at Bossa Nova Civic Club.",
    headline="Friday in Bushwick",
    dek="",
    date="2026-10-17", neighborhood="Bushwick",
    vibe=brief.vibe, est_total_cost_usd=38,
    notes="Bossa Nova is cash-friendly at the door and fills after midnight. "
          "Go before 11 if you want to be able to move.",
    stops=[
        Stop(
            name="Win Son", kind=StopKind.DINNER, neighborhood="East Williamsburg",
            start_time="19:15", end_time="20:30",
            why="Taiwanese-American cooking built for a table that talks over "
                "itself. Loud enough that a birthday doesn't feel conspicuous, "
                "small enough that four is the right number.",
            order_this="The fly's head, the beef roll, and one more order of the beef roll.",
            price_band=PriceBand.MODERATE, est_cost_usd=45, setting=Setting.INDOOR,
            booking_url="https://resy.com/cities/ny", booking_label="Reserve on Resy",
            sources=[Source(name="Eater NY", url="https://ny.eater.com/")],
        ),
        Stop(
            name="Our Wicked Lady", kind=StopKind.DRINKS, neighborhood="Bushwick",
            start_time="20:50", end_time="22:15",
            why="A rooftop to kill ninety minutes in without committing to "
                "anything. The drinks are unremarkable and that is fine — you "
                "are here for the altitude and the wait.",
            venue_size=VenueSize.INTIMATE, capacity=125, setting=Setting.ROOFTOP,
            price_band=PriceBand.CHEAP, est_cost_usd=16,
            travel_minutes_from_previous=11, travel_mode="walk",
            sources=[Source(name="Venue capacity research",
                            url="https://www.jambase.com/venue/our-wicked-lady")],
        ),
        Stop(
            name="Bossa Nova Civic Club", kind=StopKind.SHOW, neighborhood="Bushwick",
            start_time="22:40",
            why="One hundred and forty people in a dark green room with a "
                "sound system that is better than it has any right to be. If "
                "you wanted to be anonymous you came to the wrong place.",
            venue_size=VenueSize.INTIMATE, capacity=140, setting=Setting.INDOOR,
            price_band=PriceBand.CHEAP, est_cost_usd=15,
            travel_minutes_from_previous=7, travel_mode="walk",
            booking_url="https://dice.fm/", booking_label="Tickets on DICE",
            sources=[Source(name="Mixmag",
                            url="https://mixmag.net/read/new-york-bossa-nova-civic-club-significantly-damaged-fire-news")],
        ),
    ],
)

# Representative of a real run; replaced by live numbers once app.py runs.
usage = {"input_tokens": 14820, "cached_input_tokens": 9310, "output_tokens": 1180,
         "calls": 4, "cost_usd": 0.0312, "cache_hit_rate": 0.386}

out = ROOT / "output" / "preview.html"
from budget import status as budget_status  # noqa: E402
out.write_text(render_night(night, brief=brief, usage=usage, dataset=dataset_status(),
                            budget=budget_status(), standalone=True), encoding="utf-8")
print(f"Wrote {out}")
if "--open" in sys.argv:
    webbrowser.open(out.as_uri())
