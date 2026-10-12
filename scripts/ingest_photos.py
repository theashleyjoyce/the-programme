"""Register your own photographs for the collage.

Drop JPEGs into frontend/static/img/ named by slot, then run this. The naming
convention IS the interface:

    facade-1.jpg      a historic frontage at night
    plates-1.jpg      dinner plates at a good restaurant
    hand-in-hand-1.jpg
    interior-1.jpg    a room with history in it
    discoball-1.jpg
    gallery-1.jpg
    cocktail-1.jpg
    night-street-1.jpg

Anything matching a known slot is recorded as original photography, which the
footer then says plainly instead of crediting Openverse.

    python scripts/ingest_photos.py --author "Ashley Wheeler"
    python scripts/ingest_photos.py --purge-placeholders
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from collage import COLLAGE_SLOTS  # noqa: E402

IMG_DIR = ROOT / "frontend" / "static" / "img"
CREDITS = IMG_DIR / "credits.json"


def main() -> int:
    ap = argparse.ArgumentParser(description="Register your own photos for the collage.")
    ap.add_argument("--author", default="Ashley Wheeler")
    ap.add_argument("--purge-placeholders", action="store_true",
                    help="delete every image not marked as original photography")
    args = ap.parse_args()

    credits = json.loads(CREDITS.read_text()) if CREDITS.is_file() else {}
    added = 0

    for path in sorted(IMG_DIR.glob("*.jpg")) + sorted(IMG_DIR.glob("*.jpeg")):
        name = path.name
        if credits.get(name, {}).get("original_photography"):
            continue
        slot = next((s for s in COLLAGE_SLOTS if name.startswith(s + "-")), None)
        if slot is None:
            continue
        if name in credits and not args.purge_placeholders:
            continue          # an Openverse placeholder; leave it unless purging
        credits[name] = {
            "slot": slot,
            "title": "",
            "creator": args.author,
            "license": "All rights reserved — used with the photographer's permission",
            "source": "Original photography",
            "original_photography": True,
            "scene_setting_only": True,
        }
        added += 1
        print(f"  + {name:26} slot={slot}")

    if args.purge_placeholders:
        removed = [n for n, m in credits.items() if not m.get("original_photography")]
        for n in removed:
            (IMG_DIR / n).unlink(missing_ok=True)
            credits.pop(n)
        print(f"  purged {len(removed)} placeholder images")

    CREDITS.write_text(json.dumps(credits, indent=2) + "\n", encoding="utf-8")
    originals = sum(1 for m in credits.values() if m.get("original_photography"))
    print(f"\nRegistered {added}. Manifest now holds {len(credits)} images, {originals} original.")
    missing = [s for s in COLLAGE_SLOTS
               if not any(m.get("slot") == s for m in credits.values())]
    if missing:
        print(f"Slots still empty: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
