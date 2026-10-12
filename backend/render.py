"""Night -> editorial HTML.

The agents produce a typed `Night`; this turns it into a page. Keeping the two
apart is what lets the layout be designed at all -- a renderer can set a pull
quote in italic because it knows `why` is a pull quote. Freeform model prose
could only ever be dumped into a <p>.

`standalone=True` inlines the stylesheet so a saved page opens anywhere with
nothing missing, which is what the report and slide deliverables require.
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from brief import Brief
from models import Night, Setting, Stop
from transit import nearest as nearest_stations

STATIC = Path(__file__).resolve().parent.parent / "frontend" / "static"
CSS_PATH = STATIC / "night.css"


def css_version() -> str:
    """Short hash of the stylesheet, appended to its URL.

    Without this a CSS edit can sit invisible behind a browser cache, and you
    end up debugging a layout that is already fixed.
    """
    try:
        import hashlib
        return hashlib.sha1(CSS_PATH.read_bytes()).hexdigest()[:8]
    except OSError:
        return "0"

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?'
         'family=Bodoni+Moda:ital,opsz,wght@0,6..96,400..700;1,6..96,400..600&'
         'family=Inter:wght@400;500;600&display=swap" rel="stylesheet">')


def e(value: Any) -> str:
    """Escape anything bound for the page.

    Every string here passed through a model that read third-party listing
    text, so it is untrusted by construction. sanitize.py removes injected
    *instructions*; this stops injected *markup*.
    """
    return html.escape(str(value), quote=True) if value is not None else ""
def _refine_query(brief: Brief | None) -> str:
    """Rebuild the search form's query string from the brief.

    "Refine" should return you to the form exactly as you left it. Retyping a
    request to change one field is the fastest way to make someone stop using
    an app.
    """
    if brief is None:
        return ""
    from urllib.parse import urlencode

    params: list[tuple[str, str]] = [("vibe", brief.vibe)]
    if brief.date:
        params.append(("date", brief.date.isoformat()))
    if brief.borough:
        params.append(("borough", brief.borough))
    if brief.neighborhood:
        params.append(("neighborhood", brief.neighborhood))
    if brief.party_size:
        params.append(("party_size", str(brief.party_size)))
    if brief.budget:
        params.append(("budget", brief.budget.value))
    if brief.occasion:
        params.append(("occasion", brief.occasion.value))
    params += [("venue_sizes", v.value) for v in brief.venue_sizes]
    params += [("settings", v.value) for v in brief.settings]
    params += [("wants", v.value) for v in brief.wants]
    return "/?" + urlencode(params)



def _clock(value: str | None) -> str:
    """24h "19:15" -> "7:15pm". Display only.

    The schema keeps 24-hour because the sequencer does arithmetic on these and
    "7:15pm" does not subtract. But nobody reads 20:45 as a time they are going
    somewhere, so it never reaches the page in that form. On the hour drops the
    minutes, because people write "8pm", not "8:00pm".
    """
    if not value or ":" not in value:
        return value or ""
    try:
        hh, mm = (int(part) for part in value.split(":", 1))
    except ValueError:
        return value
    suffix = "am" if hh < 12 else "pm"
    hour = hh % 12 or 12
    return f"{hour}{'' if mm == 0 else f':{mm:02d}'}{suffix}"



def _figure(stop: Stop) -> str:
    """Image when there is one, a typeset placeholder when there is not.

    A missing photo should look deliberate rather than broken -- listings
    routinely lack images and the page still has to hold together.
    """
    caption = (f'<figcaption class="stop__caption">{e(stop.order_this)}</figcaption>'
               if stop.order_this else "")
    if stop.image_url:
        return (f'<figure class="stop__figure">'
                f'<img src="{e(stop.image_url)}" alt="{e(stop.name)}" loading="lazy">'
                f'{caption}</figure>')
    if not caption:
        return ""
    return f'<figure class="stop__figure">{caption}</figure>'


def _chips(stop: Stop) -> str:
    """Room, capacity, setting, price. The differentiator, made visible."""
    chips: list[str] = []
    if stop.venue_size:
        chips.append(f'<span class="chip chip--room">{e(stop.venue_size.value)}</span>')
    if stop.capacity:
        chips.append(f'<span class="chip">{stop.capacity:,} cap</span>')
    if stop.setting:
        cls = "chip chip--outdoor" if stop.setting.weather_dependent else "chip"
        chips.append(f'<span class="{cls}">{e(stop.setting.value)}</span>')
    if stop.price_band:
        chips.append(f'<span class="chip">{e(stop.price_band.value)}</span>')
    chips.append(f'<span class="chip">{e(stop.neighborhood)}</span>')
    return f'<div class="chips">{"".join(chips)}</div>'


def _actions(stop: Stop) -> str:
    """Book button, or an explanation of why there isn't one.

    A stop whose link failed the allowlist renders the refusal rather than
    nothing, so the safety layer is visible to the user instead of silent.
    """
    if stop.booking_url:
        label = stop.booking_label or "Book"
        bits = [f'<a class="book" href="{e(stop.booking_url)}" '
                f'target="_blank" rel="noopener noreferrer">{e(label)}</a>']
    elif stop.booking_label:
        bits = [f'<span class="book--blocked">Link withheld — unrecognised booking domain</span>']
    else:
        bits = []
    if stop.est_cost_usd is not None:
        bits.append(f'<span class="stop__price">≈ ${stop.est_cost_usd:,.0f} pp</span>')
    return f'<div class="stop__actions">{"".join(bits)}</div>' if bits else ""


def _sources(stop: Stop) -> str:
    if not stop.sources:
        return ""
    items = [f'<a href="{e(s.url)}" target="_blank" rel="noopener noreferrer">{e(s.name)}</a>'
             if s.url else e(s.name) for s in stop.sources]
    return f'<p class="stop__sources">Sources: {" · ".join(items)}</p>'


def _travel(stop: Stop) -> str:
    if not stop.travel_minutes_from_previous:
        return ""
    mode = stop.travel_mode or "travel"
    return f'<div class="travel">{stop.travel_minutes_from_previous} min {e(mode)}</div>'

# Half a minute of walking either side of the pin. Tight enough that the
# street grid is legible, wide enough to see which corner it is on.
MAP_SPAN = 0.0045


def _map_iframe(stop: Stop) -> str:
    """OpenStreetMap embed. No API key, no tracking, no account.

    Rendered only when the Editor supplied coordinates it was confident about.
    A map pointing at the wrong block is worse than no map, so an absent
    lat/lon simply means no map rather than a guess.
    """
    if stop.lat is None or stop.lon is None:
        return ""
    west, east = stop.lon - MAP_SPAN, stop.lon + MAP_SPAN
    south, north = stop.lat - MAP_SPAN, stop.lat + MAP_SPAN
    src = (f"https://www.openstreetmap.org/export/embed.html"
           f"?bbox={west:.5f}%2C{south:.5f}%2C{east:.5f}%2C{north:.5f}"
           f"&layer=mapnik&marker={stop.lat:.5f}%2C{stop.lon:.5f}")
    link = f"https://www.openstreetmap.org/?mlat={stop.lat:.5f}&mlon={stop.lon:.5f}#map=17/{stop.lat:.5f}/{stop.lon:.5f}"
    return (f'<div class="stop__map">'
            f'<iframe src="{e(src)}" loading="lazy" title="Map of {e(stop.name)}" '
            f'referrerpolicy="no-referrer"></iframe>'
            f'<a class="stop__maplink" href="{e(link)}" target="_blank" '
            f'rel="noopener noreferrer">Open in maps</a>'
            f"</div>")


def _transit(stop: Stop) -> str:
    """Nearest subway stations, computed from the cached MTA dataset.

    Not asked of the model: a model will confidently name a station four stops
    away, and distance is arithmetic.
    """
    found = nearest_stations(stop.lat, stop.lon, limit=2)
    if not found:
        return ""
    rows = []
    for st in found:
        routes = "".join(f'<span class="bullet">{e(r)}</span>' for r in st["routes"][:5])
        ada = '<span class="stop__ada" title="Accessible station">&#9855;</span>' if st["ada"] else ""
        rows.append(
            f'<li><span class="stop__station">{e(st["name"])}{ada}</span>'
            f'<span class="stop__routes">{routes}</span>'
            f'<span class="stop__walk">{st["walk_minutes"]} min walk</span></li>'
        )
    return f'<div class="stop__transit"><h5>Nearest train</h5><ul>{"".join(rows)}</ul></div>'


@lru_cache(maxsize=1)
def _venue_photos() -> dict[str, dict]:
    """Photographs cached from venues' own sites by scripts/fetch_venue_photos.py."""
    path = Path(__file__).resolve().parent.parent / "data" / "venue_photos.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _venue_photo(stop: Stop) -> str:
    """The venue's own photograph, when there is an appropriate one.

    Only images the offline fetcher accepted: served from the venue's own
    domain, not a logo, big enough to be a photograph. Anything else and the
    card shows the map alone, which is what Ashley asked for -- a directory's
    logo next to a bar is worse than nothing.

    The file is served from the venue's own host with a visible credit and a
    link back, the way a link preview works. Nothing is copied into the repo.
    """
    entry = _venue_photos().get(stop.name) or {}
    url = entry.get("image_url")
    if not url:
        return ""
    credit = entry.get("credit") or ""
    link = entry.get("credit_url") or url
    return (f'<figure class="stop__photo">'
            f'<img src="{e(url)}" alt="{e(stop.name)}" loading="lazy" '
            f'referrerpolicy="no-referrer">'
            f'<figcaption>Photo: <a href="{e(link)}" target="_blank" '
            f'rel="noopener noreferrer">{e(credit)}</a></figcaption></figure>')


def _aside(stop: Stop) -> str:
    """The right-hand column of a stop: what it looks like, where it is, and
    how to get there. Any part may be absent; the column simply shortens."""
    inner = _venue_photo(stop) + _map_iframe(stop) + _transit(stop)
    return f'<aside class="stop__aside">{inner}</aside>' if inner else ""


def _stop(index: int, stop: Stop) -> str:
    kicker = stop.kind.value
    end = f" – {e(_clock(stop.end_time))}" if stop.end_time else ""
    feels = (f'<p class="stop__feels">{e(stop.venue_size.blurb)} '
             f'{e(stop.setting.blurb) if stop.setting else ""}</p>'
             if stop.venue_size else "")
    return f"""{_travel(stop)}
<article class="stop" id="stop-{index}">
  <div>
    <div class="stop__index">{index}</div>
    <div class="stop__time">{e(_clock(stop.start_time))}{end}</div>
  </div>
  <div>
    <p class="stop__kicker">{e(kicker)}</p>
    <h2 class="stop__name">{e(stop.name)}</h2>
    {_chips(stop)}
    {_figure(stop)}
    <p class="stop__why">{e(stop.why)}</p>
    {feels}
    {_actions(stop)}
    {_sources(stop)}
  </div>
  {_aside(stop)}
</article>"""


def _summary(night: Night) -> str:
    """The chat reply: one sentence, with every venue name linked to its card.

    Linking is done here rather than asked of the model. Making a model emit
    anchor markup invites broken HTML and is one more thing an injected listing
    could try to influence; matching names we already trust is safer and cannot
    produce a link to anywhere but this page.

    Longest-first matching so "Elsewhere (The Hall)" wins over "Elsewhere".
    """
    text = e(night.summary)
    ordered = sorted(
        ((i, s) for i, s in enumerate(night.stops, start=1)),
        key=lambda pair: len(pair[1].name),
        reverse=True,
    )
    for index, stop in ordered:
        name = e(stop.name)
        if name and name in text:
            text = text.replace(name, f'<a class="summary__link" href="#stop-{index}">{name}</a>', 1)
    return f'<p class="summary">{text}</p>'


def _advisory(night: Night) -> str:
    warnings = night.weather_warnings()
    if not warnings:
        return ""
    items = "".join(f"<p>{e(w)}</p>" for w in warnings)
    return f'<aside class="advisory"><strong>Dress for it.</strong>{items}</aside>'


def _colophon(night: Night, brief: Brief | None, usage: dict | None,
              dataset: dict | None, budget: dict | None = None) -> str:
    """Magazine colophon, doing double duty as rubric evidence.

    The assignment says the app may display its own token usage as tokenomics
    evidence, so the measured counts live here where a screenshot of any plan
    captures them.
    """
    cols: list[str] = []

    if usage:
        cols.append(
            "<div><h4>What this cost</h4>"
            f'<p class="colophon__figure">{usage.get("input_tokens", 0):,} input · '
            f'{usage.get("cached_input_tokens", 0):,} cached · '
            f'{usage.get("output_tokens", 0):,} output</p>'
            f'<p class="colophon__figure">${usage.get("cost_usd", 0):.4f} · '
            f'{usage.get("calls", 0)} model calls</p>'
            f'<p>Cache hit rate {usage.get("cache_hit_rate", 0) * 100:.0f}%</p></div>')

    if dataset:
        cols.append(
            "<div><h4>Where this came from</h4>"
            f'<p>{dataset.get("rooms_known", 0)} rooms across '
            f'{dataset.get("venues_known", 0)} venues</p>'
            f'<p>{dataset.get("multi_room_venues", 0)} venues with more than one room</p>'
            f'<p>Events: {e(dataset.get("events_source", "unknown"))}</p></div>')

    if budget:
        cols.append(
            "<div><h4>Running total</h4>"
            f'<p class="colophon__figure">${budget["spent_usd"]:.2f} of '
            f'${budget["budget_usd"]:.2f} spent</p>'
            f'<p>{budget["calls_recorded"]} model calls, all time</p>'
            f'<p>A hard cap refuses the next call at the limit.</p></div>')

    if brief:
        cols.append("<div><h4>What you asked for</h4>"
                    f'<p>“{e(brief.vibe)}”</p><p>{e(brief.constraints_summary())}</p></div>')

    cols.append("<div><h4>How to read this</h4>"
                "<p>Capacities are researched per room and cited. Booking links "
                "open the venue's own page — The Programme never completes a "
                "purchase for you.</p></div>")

    return f'<footer class="colophon">{"".join(cols)}</footer>'


def render_night(
    night: Night,
    brief: Brief | None = None,
    usage: dict | None = None,
    dataset: dict | None = None,
    budget: dict | None = None,
    standalone: bool = False,
) -> str:
    """Full HTML document for one night."""
    if standalone and CSS_PATH.is_file():
        style = f"<style>{CSS_PATH.read_text(encoding='utf-8')}</style>"
    else:
        style = f'<link rel="stylesheet" href="/static/night.css?v={css_version()}">'

    stops = "".join(_stop(i, s) for i, s in enumerate(night.stops, start=1))
    stamp = datetime.now().strftime("%d %b %Y")
    total = (f' · ≈ ${night.est_total_cost_usd:,.0f} per person'
             if night.est_total_cost_usd else "")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(night.headline)} — The Programme</title>
{FONTS}
{style}
</head>
<body>
<header class="masthead">
  <a class="masthead__home" href="/">The Programme</a>
  <nav class="masthead__nav">
    <a href="{_refine_query(brief)}">Refine this</a>
    <a href="/">New search</a>
    <button type="button" class="masthead__print" onclick="window.print()">Print</button>
  </nav>
</header>

<section class="hero">
  <p class="hero__kicker">{e(night.date.strftime("%A %-d %B"))} · {e(night.neighborhood)}</p>
  {_summary(night)}
  <p class="hero__constraints">{e(brief.constraints_summary()) if brief else e(night.vibe)}{total}</p>
</section>

{_advisory(night)}

<main class="night">{stops}</main>

<div class="footer-actions">
  <a class="primary" href="{_refine_query(brief)}">Change something</a>
  <a href="/">Plan a different night</a>
</div>

{_colophon(night, brief, usage, dataset, budget)}
</body>
</html>"""
