"""Cache one photograph per venue, taken from the venue's own site.

Every restaurant and venue publishes an og:image so their link previews look
right. That is the picture they chose to represent themselves, which is
exactly what belongs next to their entry.

Runs OFFLINE and caches the URL. Doing this at request time would add a page
fetch per stop to a plan we are actively trying to make faster, and would break
on any site that is slow or down.

What is stored is the URL plus attribution, not the file: the image is served
from the venue's own host, with a visible credit and a link back, the same way
a link preview works. Nothing is copied into the repo.

    python scripts/fetch_venue_photos.py --limit 40
    python scripts/fetch_venue_photos.py --venue "Nowadays"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from config import DATA_DIR  # noqa: E402

PHOTOS = DATA_DIR / "venue_photos.json"
CANDIDATES = DATA_DIR / "candidate_venues.json"
VENUES = DATA_DIR / "nyc_venues.json"

UA = {"User-Agent": "TheProgramme/0.1 (+Yale MGT409 course project; link-preview style fetch)"}

# Directories and aggregators. Their og:image is a site logo or a generic
# banner, never a photograph of the venue, so a hit from one of these is worse
# than no photo at all.
AGGREGATORS = {
    "jambase.com", "wikimedia.org", "wikipedia.org", "songkick.com",
    "bandsintown.com", "yelp.com", "tripadvisor.com", "facebook.com",
    "instagram.com", "eventbrite.com", "ticketmaster.com", "axs.com",
    "dice.fm", "seetickets.us", "foursquare.com", "google.com", "apple.com",
    "timeout.com", "eater.com", "theinfatuation.com", "nycgo.com",
    "mixmag.net", "pollstar.com", "rippit.nyc", "supabase.co",
}

# Logos, icons, sprites and placeholders dressed up as og:image.
BAD_IMAGE_HINTS = re.compile(
    r"(logo|icon|sprite|favicon|placeholder|default|share[-_]?image|"
    r"og[-_]?default|social[-_]?card|banner[-_]?default)", re.I)

# Below this an image is a logo or a thumbnail, not a photograph.
MIN_IMAGE_BYTES = 25_000

OG = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](og:image(?::secure_url)?|twitter:image)["\'][^>]*>',
    re.I)
CONTENT = re.compile(r'content=["\']([^"\']+)["\']', re.I)


def extract_image(html: str, base: str) -> str | None:
    for tag in OG.findall(html) or []:
        pass
    for match in re.finditer(OG, html):
        content = CONTENT.search(match.group(0))
        if content:
            url = content.group(1).strip()
            if url.startswith("//"):
                url = "https:" + url
            elif url.startswith("/"):
                url = urljoin(base, url)
            if url.startswith("http"):
                return url
    return None


def registrable(host: str) -> str:
    host = host.lower().removeprefix("www.")
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def site_for(venue: dict) -> str | None:
    """The venue's OWN site, never a directory listing about it."""
    for key in ("website", "source_url", "url"):
        v = venue.get(key)
        if not v or not str(v).startswith("http"):
            continue
        if registrable(urlparse(str(v)).netloc) in AGGREGATORS:
            continue
        return str(v)
    return None


def image_is_appropriate(client: httpx.Client, image_url: str, site: str) -> tuple[bool, str]:
    """A photograph of the place, or nothing.

    Three ways an og:image fails to be that: it is served by an aggregator, its
    filename says logo, or it is too small to be a photograph. Any of those and
    the card shows the map alone, which is the honest outcome.
    """
    host = registrable(urlparse(image_url).netloc)
    if host in AGGREGATORS:
        return False, f"aggregator image ({host})"
    if BAD_IMAGE_HINTS.search(urlparse(image_url).path):
        return False, "looks like a logo"
    try:
        head = client.head(image_url, timeout=10)
        if head.status_code >= 400:
            head = client.get(image_url, timeout=12, headers={"Range": "bytes=0-2048"})
        ctype = head.headers.get("content-type", "")
        if "image" not in ctype:
            return False, f"not an image ({ctype[:24]})"
        if "svg" in ctype:
            return False, "svg, so a logo"
        size = int(head.headers.get("content-length") or 0)
        if size and size < MIN_IMAGE_BYTES:
            return False, f"too small ({size // 1024} KB)"
    except (httpx.HTTPError, ValueError):
        return False, "could not verify"
    return True, ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Cache one photo per venue from its own site.")
    ap.add_argument("--venue", action="append", default=[])
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    photos: dict[str, dict] = json.loads(PHOTOS.read_text()) if PHOTOS.is_file() else {}

    pool: list[dict] = []
    if VENUES.is_file():
        pool += json.loads(VENUES.read_text()).get("venues", [])
    if CANDIDATES.is_file():
        pool += json.loads(CANDIDATES.read_text()).get("venues", [])

    if args.venue:
        wanted = {v.lower() for v in args.venue}
        pool = [v for v in pool if v.get("name", "").lower() in wanted]

    done = found = 0
    with httpx.Client(headers=UA, timeout=15, follow_redirects=True) as c:
        for venue in pool:
            if done >= args.limit:
                break
            name = venue.get("name", "").strip()
            if not name or name in photos:
                continue
            site = site_for(venue)
            if not site:
                continue

            done += 1
            try:
                r = c.get(site)
                r.raise_for_status()
                image = extract_image(r.text, site)
            except (httpx.HTTPError, UnicodeDecodeError) as exc:
                print(f"  ! {name[:32]:34} {type(exc).__name__}")
                photos[name] = {"image_url": None, "checked": True}
                continue

            if not image:
                print(f"  - {name[:32]:34} no og:image")
                photos[name] = {"image_url": None, "checked": True}
                continue

            ok, why = image_is_appropriate(c, image, site)
            if not ok:
                print(f"  - {name[:32]:34} rejected: {why}")
                photos[name] = {"image_url": None, "checked": True, "rejected": why}
                continue

            found += 1
            print(f"  + {name[:32]:34} {urlparse(image).netloc}")
            photos[name] = {
                "image_url": image,
                "credit": urlparse(site).netloc.removeprefix("www."),
                "credit_url": site,
                "checked": True,
            }
            time.sleep(0.4)

    if not args.dry_run:
        PHOTOS.parent.mkdir(parents=True, exist_ok=True)
        PHOTOS.write_text(json.dumps(photos, indent=1) + "\n", encoding="utf-8")
    print(f"\nChecked {done}, found {found}. {sum(1 for v in photos.values() if v.get('image_url'))} "
          f"photos cached in {PHOTOS.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
