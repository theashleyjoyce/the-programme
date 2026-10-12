"""Opening hours: parse what we can, admit what we cannot.

The planner used to place a stop at 7:30pm with no idea whether the place is
open. That is the app making a promise it cannot keep, and the failure lands on
the user standing outside a dark building.

OpenStreetMap carries an `opening_hours` field, free, in the same request we
already make for geocoding. Its grammar is large; this parses the common forms
and returns UNKNOWN for anything else. Guessing would be worse than silence.

Handles:   Mo-Su 18:00-04:00
           Tu-Sa 17:00-23:00; Su 12:00-18:00
           Mo-Fr 11:00-22:00, Sa-Su 10:00-23:00
           24/7
           Mo off / closed
Declines:  "According to schedule", PH rules, month ranges, week numbers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time
from enum import Enum

DAYS = ["mo", "tu", "we", "th", "fr", "sa", "su"]
DAY_INDEX = {d: i for i, d in enumerate(DAYS)}

TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
RANGE_RE = re.compile(
    r"^(?P<days>(?:[A-Za-z]{2}(?:-[A-Za-z]{2})?)(?:,[A-Za-z]{2}(?:-[A-Za-z]{2})?)*)?"
    r"\s*(?P<times>.*)$"
)


class Status(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"

    @property
    def note(self) -> str:
        return {
            "open": "",
            "closed": "Closed on this day. Pick another night, or another place.",
            "unknown": "Opening hours not on file; check before you go.",
        }[self.value]


@dataclass(frozen=True)
class Window:
    day: int          # 0 = Monday
    start: time
    end: time
    overnight: bool   # closes after midnight


def _parse_time(text: str) -> time | None:
    m = TIME_RE.match(text.strip())
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    if hh == 24 and mm == 0:
        return time(23, 59)
    return time(hh, mm) if 0 <= hh <= 23 and 0 <= mm <= 59 else None


def _expand_days(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip().lower()
        if "-" in part:
            a, b = part.split("-", 1)
            if a in DAY_INDEX and b in DAY_INDEX:
                i, j = DAY_INDEX[a], DAY_INDEX[b]
                out.extend(range(i, j + 1) if i <= j
                           else list(range(i, 7)) + list(range(0, j + 1)))
        elif part in DAY_INDEX:
            out.append(DAY_INDEX[part])
    return out


def parse(spec: str | None) -> list[Window] | None:
    """Windows per day, or None when the spec is beyond this parser."""
    if not spec or not spec.strip():
        return None
    text = spec.strip().strip('"')

    if text == "24/7":
        return [Window(d, time(0, 0), time(23, 59), False) for d in range(7)]

    # Anything with public holidays, months, weeks or prose is declined
    # rather than half-understood.
    if re.search(r"\b(PH|SH|week|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b",
                 text, re.I):
        return None
    if re.search(r"[A-Za-z]{4,}", re.sub(r"\b(off|closed|sunrise|sunset)\b", "", text, flags=re.I)):
        return None

    # Rules are separated by ';' but OSM also allows ',' between day-groups:
    #   "Mo-Fr 11:00-22:00, Sa-Su 10:00-23:00"
    # while using ',' *within* a rule to separate time spans:
    #   "Mo-Fr 09:00-12:00,13:00-17:00"
    # So a comma starts a new rule only when a day specifier follows it.
    text = re.sub(r",\s*(?=(?:[A-Za-z]{2}(?:-[A-Za-z]{2})?)(?:,[A-Za-z]{2}(?:-[A-Za-z]{2})?)*\s+\d)",
                  "; ", text)

    windows: list[Window] = []
    for chunk in re.split(r"[;]", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = RANGE_RE.match(chunk)
        if not m:
            return None
        days = _expand_days(m.group("days") or "") or list(range(7))
        body = (m.group("times") or "").strip()

        if re.fullmatch(r"(off|closed)", body, re.I):
            continue                       # that day simply has no window

        found = False
        for span in re.split(r"[,]", body):
            span = span.strip()
            if not span:
                continue
            if "-" not in span:
                return None
            a, b = span.split("-", 1)
            start, end = _parse_time(a), _parse_time(b)
            if start is None or end is None:
                return None
            overnight = end <= start
            for d in days:
                windows.append(Window(d, start, end, overnight))
            found = True
        if not found and body:
            return None

    return windows or None


def status_at(spec: str | None, when: date, at: time) -> Status:
    """Is it open on this day at this time?"""
    windows = parse(spec)
    if windows is None:
        return Status.UNKNOWN

    today = when.weekday()
    yesterday = (today - 1) % 7

    for w in windows:
        if w.day == today and not w.overnight and w.start <= at <= w.end:
            return Status.OPEN
        if w.day == today and w.overnight and at >= w.start:
            return Status.OPEN
        # A window that began yesterday and runs past midnight.
        if w.day == yesterday and w.overnight and at <= w.end:
            return Status.OPEN

    return Status.CLOSED if any(w.day in (today, yesterday) for w in windows) \
        else Status.CLOSED


def describe(spec: str | None) -> str:
    """A short human line, or empty when we cannot read the spec."""
    windows = parse(spec)
    if not windows:
        return ""
    by_day: dict[int, list[Window]] = {}
    for w in windows:
        by_day.setdefault(w.day, []).append(w)
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    open_days = sorted(by_day)
    if len(open_days) == 7:
        w = by_day[open_days[0]][0]
        return f"Daily {w.start:%H:%M}–{w.end:%H:%M}"
    return ", ".join(names[d] for d in open_days) + " only"
