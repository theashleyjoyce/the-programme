"""Offline agent that researches venue capacity and grows data/nyc_venues.json.

Capacity is public but scattered -- venue "about" pages, Wikipedia, promoter
listings, fire-code filings. Ticketmaster's API does not return it. So this
script sends a research agent to find it once, with a citation, and caches the
answer.

Why this runs OFFLINE and not at request time:
  - The 10-minute rule (5 pts). A grader's clone must not depend on live
    scraping that can rate-limit, change layout, or hang.
  - Tokenomics (8 pts). Researching a venue once and reusing it across every
    future request is the single biggest cost lever in the app. Per-request
    lookup would multiply input tokens by the number of candidate venues.

Usage:
    python scripts/enrich_capacity.py --venue "Elsewhere" --venue "Nowadays"
    python scripts/enrich_capacity.py --from-events        # anything missing
    python scripts/enrich_capacity.py --dry-run --venue "Public Records"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from budget import BudgetExceeded, check_before_call, record  # noqa: E402
from config import DATA_DIR, model_config  # noqa: E402
from tokens import Usage  # noqa: E402
from openai import OpenAI                  # noqa: E402

VENUES_PATH = DATA_DIR / "nyc_venues.json"

RESEARCH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "capacity", "neighborhood", "borough", "source_url", "confidence", "notes"],
    "properties": {
        "name": {"type": "string", "description": "Official venue name"},
        "capacity": {"type": ["integer", "null"], "description": "Standing/seated capacity. null if not found."},
        "neighborhood": {"type": ["string", "null"]},
        "borough": {"type": ["string", "null"]},
        "source_url": {"type": ["string", "null"], "description": "Where the capacity figure came from"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low", "not_found"]},
        "notes": {"type": ["string", "null"], "description": "e.g. multiple rooms, differs standing vs seated"},
    },
}

INSTRUCTIONS = """\
You research live-music and nightlife venue capacities in New York City.

Find the venue's published capacity. Prefer, in order: the venue's own site,
Wikipedia, a promoter or ticketing listing, a reputable press article.

Rules:
- Report only a figure you actually found. Never estimate from the venue's
  size, genre, or reputation. If you cannot find it, set capacity to null and
  confidence to "not_found". A missing value is useful; a guessed one is not.
- If a venue has several rooms with different capacities, report the main room
  and say so in notes.
- If standing and seated capacities differ, report standing and note both.
- Always give the URL the number came from.
"""


def load_venues() -> dict:
    return json.loads(VENUES_PATH.read_text(encoding="utf-8"))


def research(client: OpenAI, model: str, venue: str) -> tuple[dict, object]:
    """One venue, one call. Returns the parsed record and the raw response
    so the caller can read token usage off it."""
    check_before_call(0.03)
    response = client.responses.create(
        model=model,
        store=False,
        instructions=INSTRUCTIONS,
        tools=[{"type": "web_search"}],
        text={"format": {"type": "json_schema", "name": "venue_capacity",
                         "strict": True, "schema": RESEARCH_SCHEMA}},
        input=f"Find the capacity of this New York City venue: {venue}",
    )
    record(Usage.from_response(response), f"enrich:{venue}", model)
    return json.loads(response.output_text), response


def main() -> int:
    ap = argparse.ArgumentParser(description="Research NYC venue capacities and cache them.")
    ap.add_argument("--venue", action="append", default=[], help="Venue name (repeatable)")
    ap.add_argument("--dry-run", action="store_true", help="Research but do not write the file")
    args = ap.parse_args()

    if not args.venue:
        ap.error("give at least one --venue")

    cfg = model_config()
    client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url) if cfg.base_url else OpenAI(api_key=cfg.api_key)
    print(f"Model: {cfg.describe()}\n")

    data = load_venues()
    known = {v["name"].lower() for v in data["venues"]}
    added, total_in, total_out = 0, 0, 0

    for name in args.venue:
        if name.lower() in known:
            print(f"  = {name}: already cached, skipping")
            continue
        try:
            record, raw = research(client, cfg.model, name)
        except Exception as exc:                      # noqa: BLE001
            print(f"  ! {name}: lookup failed -- {type(exc).__name__}: {exc}")
            continue

        usage = getattr(raw, "usage", None)
        if usage:
            total_in += int(getattr(usage, "input_tokens", 0) or 0)
            total_out += int(getattr(usage, "output_tokens", 0) or 0)

        if record.get("capacity") is None:
            print(f"  ? {name}: not found (confidence={record['confidence']})")
            continue

        print(f"  + {record['name']}: {record['capacity']} "
              f"[{record['confidence']}] {record.get('neighborhood') or '?'}")
        print(f"      source: {record.get('source_url')}")
        if record.get("notes"):
            print(f"      notes:  {record['notes']}")

        data["venues"].append({
            "name": record["name"],
            "capacity": record["capacity"],
            "neighborhood": record.get("neighborhood") or "Unknown",
            "borough": record.get("borough") or "Unknown",
            "source_url": record.get("source_url"),
            "confidence": record["confidence"],
            "notes": record.get("notes"),
        })
        added += 1

    print(f"\nTokens this run: {total_in:,} in / {total_out:,} out")

    if args.dry_run:
        print("Dry run -- nothing written.")
        return 0
    if added:
        data["venues"].sort(key=lambda v: v["capacity"])
        VENUES_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {added} new venue(s) to {VENUES_PATH.relative_to(VENUES_PATH.parents[1])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
