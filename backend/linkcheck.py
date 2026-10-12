"""Verify a booking link opens the right venue, and remember the answer.

The problem this solves: a Resy or OpenTable URL produced from a model's
memory almost always resolves. That is what makes it dangerous. It looks
correct, returns 200, and opens a different restaurant, and the user does not
discover this until they are standing outside one.

Dropping every such link was the first fix, but it removed the feature rather
than repairing it. So instead the page is fetched once and kept only if it
actually names the venue. Results are cached on disk, so a venue is checked
once and every later plan is instant.

Checks run with a short timeout and fail closed: if we cannot confirm a link,
it is not shown.
"""

from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import httpx

CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "link_checks.json"
UA = {"User-Agent": "TheProgramme/0.1 (Yale MGT409 course project; link verification)"}

TIMEOUT_SECONDS = 4.0
# Re-check occasionally: venues close, and a stale "verified" is its own lie.
TTL_SECONDS = 60 * 60 * 24 * 30

_lock = threading.Lock()
_memory: dict[str, dict] | None = None
_memory_mtime: int = -1

# Words too common to identify a venue on their own.
STOPWORDS = {
    "the", "a", "an", "and", "of", "at", "bar", "cafe", "restaurant", "club",
    "room", "house", "nyc", "new", "york", "co", "company", "kitchen", "grill",
    "lounge", "tavern", "pub", "eatery",
}


def _load() -> dict[str, dict]:
    """Read the cache, re-reading when the file has changed underneath us.

    Caching it once and never looking again meant a running app kept serving
    an empty cache after the bulk verification had written hundreds of
    results, so every plan showed no booking buttons. Keying on mtime costs
    one stat call and makes an offline rebuild take effect immediately.
    """
    global _memory, _memory_mtime
    try:
        mtime = CACHE_PATH.stat().st_mtime_ns
    except OSError:
        mtime = 0
    if _memory is None or mtime != _memory_mtime:
        try:
            _memory = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _memory = {}
        _memory_mtime = mtime
    return _memory


def _save() -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(_load(), indent=1) + "\n", encoding="utf-8")
    tmp.replace(CACHE_PATH)


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower())


def _tokens(name: str) -> list[str]:
    return [w for w in _normalise(name).split() if len(w) > 2 and w not in STOPWORDS]


def page_names_venue(html: str, venue: str) -> bool:
    """Does the page actually name this venue?

    Every distinctive word must appear when there are only one or two of them.
    One shared word is not enough: a page about a different 'Jimmy' is exactly
    the failure this exists to catch.
    """
    tokens = _tokens(venue)
    if not tokens:
        return False
    body = _normalise(html[:200_000])
    hits = sum(1 for t in tokens if t in body)
    return hits == len(tokens) if len(tokens) <= 2 else hits >= len(tokens) - 1


def verify(url: str | None, venue: str, allow_fetch: bool = True) -> bool:
    """True when this link is confirmed to open this venue.

    Fails closed. A timeout, an error, or a page that does not name the venue
    all mean "do not show it".

    `allow_fetch=False` answers only from the cache and never touches the
    network. That is what request handling uses: a four second check is fine
    once, offline, but not while somebody is waiting for a plan. Pre-verify
    with scripts/verify_links.py and the answer is already here.
    """
    if not url or not venue:
        return False

    key = f"{urlparse(url).netloc}|{urlparse(url).path}|{venue}".lower()
    cache = _load()
    hit = cache.get(key)
    if hit and (time.time() - hit.get("at", 0)) < TTL_SECONDS:
        return bool(hit["ok"])

    if not allow_fetch:
        return False          # unknown means not shown

    try:
        with httpx.Client(headers=UA, timeout=TIMEOUT_SECONDS,
                          follow_redirects=True) as client:
            r = client.get(url)
            ok = r.status_code < 400 and page_names_venue(r.text, venue)
    except (httpx.HTTPError, UnicodeDecodeError, ValueError):
        ok = False

    with _lock:
        cache[key] = {"ok": ok, "at": int(time.time()), "url": url, "venue": venue}
        try:
            _save()
            global _memory_mtime
            try:
                _memory_mtime = CACHE_PATH.stat().st_mtime_ns
            except OSError:
                pass
        except OSError:
            pass
    return ok


def stats() -> dict[str, int]:
    cache = _load()
    return {
        "checked": len(cache),
        "verified": sum(1 for v in cache.values() if v.get("ok")),
        "rejected": sum(1 for v in cache.values() if not v.get("ok")),
    }
