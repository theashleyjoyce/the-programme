"""The Writer: editorial copy for each venue, written once, offline.

Third agent in the corpus team.

    Scout      neighborhood  -> candidate venues      (discover_venues.py)
    Researcher venue         -> rooms, capacity, etc. (enrich_capacity.py)
    Writer     venue         -> the prose on the card (this file)

Why offline: the copy about a venue is the same every time somebody is sent
there, so generating it per request pays for the same sentences over and over.
Writing it once turns a 2,000-token request into a 150-token one and takes the
plan from twenty-five seconds to about two. It is also how a real city guide
works: The Infatuation writes one review per restaurant, not one per reader.

    python scripts/write_venue_copy.py --limit 40
    python scripts/write_venue_copy.py --venue "Nowadays" --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from budget import BudgetExceeded, check_before_call, record  # noqa: E402
from config import DATA_DIR, model_config                     # noqa: E402
from openai import OpenAI                                      # noqa: E402
from tokens import Usage                                       # noqa: E402

COPY_PATH = DATA_DIR / "venue_copy.json"
CANDIDATES = DATA_DIR / "candidate_venues.json"
VENUES = DATA_DIR / "nyc_venues.json"

# Several venues per call. The instructions are the expensive part of this
# prompt, so paying for them once per batch rather than once per venue is most
# of the saving.
BATCH = 8

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["entries"],
    "properties": {"entries": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["name", "why", "order_this"],
        "properties": {
            "name": {"type": "string", "description": "Exactly as given"},
            "why": {"type": "string", "description": "One or two sentences, under 280 characters"},
            "order_this": {"type": ["string", "null"],
                           "description": "The one specific thing, under 120 chars. null if nothing specific."},
        }}}},
}

INSTRUCTIONS = """\
You write the short entry that appears under a venue's name in a city guide.

Voice: direct, confident, useful. The Infatuation, not a press release. You
have been there and you are telling a friend what it is actually like.

Rules for `why`:
- One or two sentences. Under 280 characters. Shorter is better, and a good
  twelve-word entry beats a padded thirty-word one.

- NEVER open with "<Name> is a ...". That construction is banned outright. The
  reader can already see the name, the neighborhood and the category on the
  card, so repeating them back is a wasted sentence.
  BAD:  "Smalls is a tiny West Village jazz club for serious listening."
  GOOD: "A basement room where the music is the entire point and the front row
         is four feet from the piano."

- Vary how entries begin across the batch. If two in a row start the same way,
  rewrite one. Start with the room, the food, the crowd, the hour, a verb, a
  caveat. Not always a noun phrase.

- Write about the specific place, not its category. "Bands play here" is true
  of every music venue and therefore says nothing.

- No superlatives, no "hidden gem", no "nestled", no "vibrant", no "a must",
  no "for people who want".

- Never invent a fact. If you genuinely know little, write one short honest
  line and stop. A nine-word entry that is true beats two sentences of filler.

- Do not mention capacity numbers; the card shows those separately.

Rules for `order_this`:
- The one specific thing: a dish, a drink, the room to stand in, the night to
  go. Under 120 characters.
- null is a perfectly good answer. Padding it with "the house cocktail" when
  you do not know is worse than leaving it empty.
"""


def load_pool() -> list[dict]:
    pool: list[dict] = []
    if VENUES.is_file():
        for v in json.loads(VENUES.read_text()).get("venues", []):
            pool.append({"name": v["name"], "category": "live music venue",
                         "neighborhood": v.get("neighborhood", ""),
                         "detail": v.get("notes") or ""})
    if CANDIDATES.is_file():
        for v in json.loads(CANDIDATES.read_text()).get("venues", []):
            pool.append({"name": v.get("name", ""), "category": v.get("category", ""),
                         "neighborhood": v.get("neighborhood", ""),
                         "detail": v.get("one_line", "")})
    return [v for v in pool if v["name"]]


def main() -> int:
    ap = argparse.ArgumentParser(description="Write editorial copy for venues.")
    ap.add_argument("--venue", action="append", default=[])
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    copy: dict[str, dict] = json.loads(COPY_PATH.read_text()) if COPY_PATH.is_file() else {}
    pool = load_pool()
    if args.venue:
        wanted = {v.lower() for v in args.venue}
        pool = [v for v in pool if v["name"].lower() in wanted]
    todo = [v for v in pool if v["name"] not in copy][:args.limit]

    if not todo:
        print(f"Nothing to write. {len(copy)} venues already have copy.")
        return 0

    cfg = model_config()
    client = (OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
              if cfg.base_url else OpenAI(api_key=cfg.api_key))
    print(f"Model: {cfg.describe()}\nWriting {len(todo)} entries in batches of {BATCH}\n")

    written = 0
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        listing = "\n".join(
            f"- {v['name']} | {v['category']} | {v['neighborhood']}"
            + (f" | {v['detail']}" if v["detail"] else "")
            for v in batch)
        try:
            check_before_call(0.02)
            r = client.responses.create(
                model=cfg.model, store=False, instructions=INSTRUCTIONS,
                text={"format": {"type": "json_schema", "name": "venue_copy",
                                 "strict": True, "schema": SCHEMA}},
                input=f"Write the entry for each of these New York venues:\n{listing}",
            )
            record(Usage.from_response(r), f"write_copy:{len(batch)}", cfg.model)
        except BudgetExceeded as exc:
            print(f"\nSTOPPED: {exc}")
            break
        except Exception as exc:                            # noqa: BLE001
            print(f"  ! batch failed: {type(exc).__name__}: {exc}")
            continue

        for entry in json.loads(r.output_text)["entries"]:
            name = entry["name"]
            if not any(v["name"] == name for v in batch):
                continue                                    # not one we asked for
            copy[name] = {"why": entry["why"][:320],
                          "order_this": (entry.get("order_this") or None),
                          "source_name": "The Programme"}
            written += 1
            print(f"  + {name[:30]:32} {entry['why'][:60]}")

        if not args.dry_run:
            COPY_PATH.write_text(json.dumps(copy, indent=1) + "\n", encoding="utf-8")

    print(f"\nWrote {written}. {len(copy)} venues now have copy in {COPY_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
