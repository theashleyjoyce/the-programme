"""Pin or unpin a collage image, so a picture you like stops being shuffled out.

    python scripts/pin_image.py cocktail-3.jpg discoball-1.jpg
    python scripts/pin_image.py --unpin cocktail-3.jpg
    python scripts/pin_image.py --list
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

CRED = Path(__file__).resolve().parents[1] / "frontend" / "static" / "img" / "credits.json"


def main() -> int:
    ap = argparse.ArgumentParser(description="Pin collage images.")
    ap.add_argument("names", nargs="*", help="e.g. cocktail-3.jpg")
    ap.add_argument("--unpin", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    credits = json.loads(CRED.read_text())

    if args.list or not args.names:
        by_slot: dict[str, list[str]] = {}
        for name, meta in sorted(credits.items()):
            mark = " [PINNED]" if meta.get("pinned") else ""
            by_slot.setdefault(meta["slot"], []).append(name + mark)
        for slot, names in sorted(by_slot.items()):
            print(f"{slot}:")
            for n in names:
                print(f"   {n}")
        return 0

    for name in args.names:
        if name not in credits:
            print(f"  ! {name} is not in the manifest")
            continue
        credits[name]["pinned"] = not args.unpin
        print(f"  {'unpinned' if args.unpin else 'pinned'} {name}")

    CRED.write_text(json.dumps(credits, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
