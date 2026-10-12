"""Cache modern, openly-licensed imagery for the masthead collage.

Source: Openverse (api.openverse.org), which aggregates CC-licensed images and
needs no API key -- so even this offline build step requires no credential
beyond the two the assignment allows.

Brief, from the design direction: it has to look like an experience someone
could have TONIGHT. Not archival, not stock-cheesy. Objects and moments --
a plate of spaghetti, a disco ball, two people walking hand in hand -- rather
than crowd scenes, because objects cut out and overlap cleanly in a collage and
a photograph of strangers in a bar always looks like stock.

Licence policy: CC0 and public domain only, with CC BY allowed and credited.
ND (no derivatives) is excluded because a collage crops and overlaps, which is
a derivative. SA and NC are excluded as a matter of not taking on obligations
when CC0 material is plentiful.

Usage:
    python scripts/fetch_images.py
    python scripts/fetch_images.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
IMG_DIR = ROOT / "frontend" / "static" / "img"
CREDITS = IMG_DIR / "credits.json"
API = "https://api.openverse.org/v1/images/"
UA = "NightEditor/0.1 (Yale MGT409 course project; ashley.wheeler@yale.edu)"

# Licences we will ship. "pdm" = public domain mark.
ALLOWED = {"cc0", "pdm", "by"}
# A collage crops and layers, which ND forbids. SA and NC bring obligations we
# have no reason to accept.
FORBIDDEN = {"nd", "sa", "nc", "by-nd", "by-sa", "by-nc", "by-nc-sa", "by-nc-nd"}

# slot -> search. Each slot is one tile in the collage.
SLOTS: dict[str, str] = {
    # The four the collage leads with. Named for what they have to say:
    # where you are, what you eat, who you are with, what the room is like.
    "facade":        "historic building facade night neon sign storefront",
    "plates":        "restaurant table dishes plates food overhead",
    "interior":      "restaurant bar interior warm lighting booth",
    "hand-in-hand":  "couple holding hands walking city street",
    "spaghetti":     "plate of spaghetti pasta restaurant",
    "discoball":     "disco ball mirror ball lights",
    "cocktail":      "cocktail glass bar drink",
    "dancing":       "people dancing club lights",
    "gallery":       "art gallery wall paintings people",
    "dessert":       "dessert ice cream sundae",
    "night-street":  "city street at night lights",
    "dinner-table":  "friends dinner table restaurant evening",
    "live-music":    "live band concert stage lights crowd",
}

PER_SLOT = 4   # a few per slot so there is something to choose from


def licence_ok(code: str) -> bool:
    c = (code or "").strip().lower()
    return c in ALLOWED and c not in FORBIDDEN


def main() -> int:
    ap = argparse.ArgumentParser(description="Cache modern openly-licensed imagery.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    IMG_DIR.mkdir(parents=True, exist_ok=True)
    credits: dict[str, dict] = {}
    saved = skipped = 0

    with httpx.Client(headers={"User-Agent": UA}, timeout=60, follow_redirects=True) as client:
        for slot, query in SLOTS.items():
            print(f"\n{slot}")
            try:
                r = client.get(API, params={"q": query, "license_type": "commercial",
                                            "page_size": PER_SLOT * 5, "mature": "false"})
                r.raise_for_status()
                hits = r.json().get("results", [])
            except httpx.HTTPError as exc:
                print(f"  ! search failed: {type(exc).__name__}")
                continue

            kept = 0
            for hit in hits:
                if kept >= PER_SLOT:
                    break
                if not licence_ok(hit.get("license", "")):
                    skipped += 1
                    continue
                url = hit.get("url")
                if not url:
                    continue

                kept += 1
                name = f"{slot}-{kept}.jpg"
                lic = hit.get("license", "").upper()
                creator = hit.get("creator") or "Unknown"
                print(f"  + {name:22} {lic:5} {creator[:30]}")

                credits[name] = {
                    "slot": slot,
                    "title": (hit.get("title") or "")[:120],
                    "creator": creator,
                    "creator_url": hit.get("creator_url"),
                    "license": lic,
                    "license_url": hit.get("license_url"),
                    "source": hit.get("source"),
                    "source_page": hit.get("foreign_landing_url"),
                    "scene_setting_only": True,
                }

                if args.dry_run:
                    continue
                try:
                    img = client.get(url)
                    img.raise_for_status()
                    if len(img.content) < 8_000:      # placeholder or error page
                        raise httpx.HTTPError("too small")
                    (IMG_DIR / name).write_bytes(img.content)
                    saved += 1
                except httpx.HTTPError:
                    print(f"    ! download failed, dropping {name}")
                    credits.pop(name, None)
                    kept -= 1
                time.sleep(0.3)

    if args.dry_run:
        print(f"\nDry run. Would keep {len(credits)}, skipped {skipped} on licence.")
        return 0

    CREDITS.write_text(json.dumps(credits, indent=2) + "\n", encoding="utf-8")
    print(f"\nSaved {saved} images -> {IMG_DIR}")
    print(f"Skipped {skipped} on licence. Credits -> {CREDITS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
