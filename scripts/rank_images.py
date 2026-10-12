"""Score collage images on contrast and colour, and record it in the manifest.

A pale, low-contrast photograph renders as an empty rectangle against the warm
paper background -- it loads fine and still looks broken. Rather than eyeball
thirty-nine placeholders, measure them: standard deviation of luminance for
contrast, mean saturation for colour, and mean luminance to catch the
washed-out ones.

`collage.py` then prefers the strongest image in each slot instead of picking
at random among good and bad alike. Pinned images still win regardless -- a
deliberate choice beats a metric.

    python scripts/rank_images.py
    python scripts/rank_images.py --show
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageStat

IMG_DIR = Path(__file__).resolve().parents[1] / "frontend" / "static" / "img"
CREDITS = IMG_DIR / "credits.json"


def score(path: Path) -> dict[str, float]:
    """Contrast, colour and brightness for one image, 0-100ish."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((240, 240))
        grey = im.convert("L")
        contrast = ImageStat.Stat(grey).stddev[0]          # 0 flat, ~80 punchy
        brightness = ImageStat.Stat(grey).mean[0]           # 0 black, 255 white
        sat = ImageStat.Stat(im.convert("HSV")).mean[1]     # 0 grey, 255 vivid

    # Penalise images that are mostly very light: those are the ones that
    # disappear into the page. Mid-to-dark with strong contrast reads best.
    washed = max(0.0, (brightness - 150) / 60.0)            # bites earlier and harder
    quality = contrast * (1.0 - 0.9 * min(washed, 1.0)) + sat * 0.25

    return {"contrast": round(contrast, 1), "brightness": round(brightness, 1),
            "saturation": round(sat, 1), "quality": round(quality, 1)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Score collage images.")
    ap.add_argument("--show", action="store_true", help="print the ranking only")
    args = ap.parse_args()

    credits = json.loads(CREDITS.read_text())
    rows = []
    for name, meta in credits.items():
        path = IMG_DIR / name
        if not path.is_file():
            continue
        s = score(path)
        meta.update(s)
        rows.append((meta.get("slot", "?"), name, s, bool(meta.get("pinned"))))

    rows.sort(key=lambda r: (r[0], -r[2]["quality"]))
    by_slot: dict[str, list] = {}
    for slot, name, s, pinned in rows:
        by_slot.setdefault(slot, []).append((name, s, pinned))

    for slot, items in by_slot.items():
        print(f"\n{slot}")
        for name, s, pinned in items:
            flag = "  <- PINNED" if pinned else ("  <- best" if items[0][0] == name else "")
            print(f"   {name:24} quality {s['quality']:5.1f}  "
                  f"contrast {s['contrast']:5.1f}  bright {s['brightness']:5.1f}{flag}")

    if not args.show:
        CREDITS.write_text(json.dumps(credits, indent=2) + "\n", encoding="utf-8")
        print(f"\nScores written to {CREDITS.name}")

    weak = [n for _, n, s, _ in rows if s["quality"] < 25]
    if weak:
        print(f"\n{len(weak)} images score below 25 and will render as near-blank tiles:")
        print("   " + ", ".join(weak[:12]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
