"""Picks the images for the masthead collage.

Data-driven on purpose: the collage reads whatever is in
frontend/static/img/credits.json, so replacing the placeholder set with real
photographs is dropping files into that folder and re-running the manifest
script. No markup changes, no CSS changes.

The slot names are the brief. Each one is a thing the collage needs to say:
dinner, dancing, two people out together, somewhere with art on the wall.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

IMG_DIR = Path(__file__).resolve().parent.parent / "frontend" / "static" / "img"
CREDITS = IMG_DIR / "credits.json"

# Order matters -- it is the visual rhythm of the cluster, biggest first.
# Order is the visual rhythm of the cluster: the biggest, most important tile
# first. Slots with no images are skipped, so this can list more than the
# collage shows and simply fill up as photography arrives.
COLLAGE_SLOTS: tuple[str, ...] = (
    "facade",         # the frontage: what makes going out HERE specific
    "plates",         # dinner plates at a good restaurant, shot from above
    "hand-in-hand",   # two people out together, tonight
    "discoball",      # dancing, without resorting to a photo of a crowd
    "gallery",        # the arts half of the product
    "interior",       # a room with character — tin ceiling, old bar, banquette
    "dinner-table",
    "cocktail",
    "night-street",
    "live-music",
    "dessert",
    "dancing",
    "spaghetti",
)


def _manifest() -> dict[str, dict]:
    if not CREDITS.is_file():
        return {}
    try:
        return json.loads(CREDITS.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def collage_images(count: int = 8, seed: int | None = None) -> list[dict]:
    """One image per slot, in slot order, skipping slots with nothing in them.

    A pinned image always wins its slot. Everything else is randomised, so the
    masthead shifts slightly between visits -- a magazine changes, a screenshot
    does not. But rotation must not override a deliberate choice: pin the
    pictures you actually like and the shuffle works around them.

    Pin by setting "pinned": true on an entry in credits.json.
    """
    manifest = _manifest()
    by_slot: dict[str, list[tuple[str, dict]]] = {}
    for name, meta in manifest.items():
        if (IMG_DIR / name).is_file():
            by_slot.setdefault(meta.get("slot", "other"), []).append((name, meta))

    rng = random.Random(seed)
    picked: list[dict] = []
    for slot in COLLAGE_SLOTS:
        options = by_slot.get(slot)
        if not options:
            continue
        pinned = [o for o in options if o[1].get("pinned")]
        if pinned:
            name, meta = pinned[0]
        else:
            # Shuffle among the strongest images rather than all of them. A
            # washed-out photo renders as an empty rectangle against the paper
            # background, so rotation should not be free to pick one.
            # scripts/rank_images.py writes the "quality" score.
            ranked = sorted(options, key=lambda o: -(o[1].get("quality") or 0))
            top = [o for o in ranked if (o[1].get("quality") or 0) >= (ranked[0][1].get("quality") or 0) * 0.8]
            name, meta = rng.choice(top or ranked)
        picked.append({
            "src": f"/static/img/{name}",
            "slot": slot,
            "credit": meta.get("creator") or meta.get("author") or "",
            "license": meta.get("license", ""),
            "source_page": meta.get("source_page") or "",
            "is_original": meta.get("original_photography", False),
            "pinned": bool(meta.get("pinned")),
        })
        if len(picked) >= count:
            break
    return picked


def collage_html(count: int = 8, seed: int | None = None) -> str:
    """Markup for the cluster. Empty string when there are no images, so the
    page degrades to the plain layout rather than leaving a hole."""
    images = collage_images(count=count, seed=seed)
    if not images:
        return ""
    tiles = "".join(
        f'<figure class="collage__tile collage__tile--{i+1}">'
        f'<img src="{img["src"]}" alt="" loading="lazy" decoding="async">'
        f"</figure>"
        for i, img in enumerate(images)
    )
    return f'<div class="collage" aria-hidden="true">{tiles}</div>'


def collage_credit_line() -> str:
    """One line for the footer. Says plainly whether the photography is the
    author's own, because that is worth claiming when it is true."""
    images = collage_images(count=12)
    if not images:
        return ""
    if all(i["is_original"] for i in images):
        return "Photography by Ashley Wheeler."
    names = sorted({i["credit"] for i in images if i["credit"] and not i["is_original"]})
    if not names:
        return ""
    shown = ", ".join(names[:4]) + (", and others" if len(names) > 4 else "")
    return f"Placeholder imagery via Openverse: {shown}. To be replaced with original photography."
