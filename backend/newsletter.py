"""The welcome note new subscribers get, and the outbox it waits in.

Nothing here sends mail, deliberately. Actually delivering email needs an
account with a mail provider and its API key in the environment, and this
project is allowed two keys, both of them for models. So the note is composed
in full and written to output/newsletter_outbox/ instead, one file per
subscriber, exactly as it would arrive. Wiring a provider in later is one
function: everything above it already works.

Written as a standalone HTML document with inline styles, because that is what
an email has to be. Mail clients strip stylesheets.
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path
from typing import Any

OUTBOX = Path(__file__).resolve().parent.parent / "output" / "newsletter_outbox"

SUBJECT = "Welcome to The Programme!"
PREHEADER = "Tell us the vibe. We plan the night."

INK = "#14110F"
PAPER = "#FBF9F6"
SOFT = "#6B625C"
ACCENT = "#B8402C"
RULE = "#E4DCD2"


def _safe_name(value: str) -> str:
    """A filename that cannot climb out of the outbox."""
    return re.sub(r"[^A-Za-z0-9_.-]", "-", value)[:48] or "subscriber"


def welcome_html(name: str = "") -> str:
    """The note itself. Same voice as the About page, because it is the
    same promise: tell us how you want it to feel, we will find it."""
    greeting = f"Hello {html.escape(name)}," if name else "Hello,"
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(SUBJECT)}</title></head>
<body style="margin:0;padding:0;background:{PAPER};">
<span style="display:none;font-size:1px;color:{PAPER};">{html.escape(PREHEADER)}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="background:{PAPER};padding:40px 16px;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0"
       style="width:560px;max-width:100%;background:{PAPER};">

  <tr><td style="padding-bottom:22px;border-bottom:1px solid {INK};">
    <p style="margin:0;font-family:Georgia,'Times New Roman',serif;font-size:19px;
       letter-spacing:.3em;text-transform:uppercase;color:{INK};">The Programme</p>
  </td></tr>

  <tr><td style="padding:38px 0 0;">
    <p style="margin:0 0 6px;font-family:Helvetica,Arial,sans-serif;font-size:11px;
       letter-spacing:.2em;text-transform:uppercase;color:{ACCENT};font-weight:600;">
      New York, Your Way</p>
    <h1 style="margin:0 0 22px;font-family:Georgia,'Times New Roman',serif;
       font-size:36px;line-height:1.15;font-weight:500;color:{INK};">
      Tell us the vibe.<br>We plan the night.</h1>
  </td></tr>

  <tr><td style="font-family:Helvetica,Arial,sans-serif;font-size:15px;
     line-height:1.65;color:{INK};">
    <p style="margin:0 0 16px;">{greeting}</p>

    <p style="margin:0 0 16px;">Welcome to The Programme. You are in.</p>

    <p style="margin:0 0 16px;">This is for the explorers, the city lovers, the
    lovers and the friends. Your one stop shop for daytime or night time plans
    in New York City.</p>

    <p style="margin:0 0 16px;">It was born out of a love for food, fashion,
    live music and the kind of culture you can only get in a city this good.
    However you want the night to feel, it is out there. We will find it.</p>

    <p style="margin:0 0 26px;">New York is not short of options. It is short of
    a way through them. Tell us how you want the evening to feel and we return
    a whole one: somewhere to eat, somewhere to go after, close enough together
    that the night does not become a commute.</p>
  </td></tr>

  <tr><td style="padding:0 0 34px;">
    <a href="http://127.0.0.1:8010/"
       style="display:inline-block;background:{INK};color:{PAPER};
       font-family:Helvetica,Arial,sans-serif;font-size:12px;letter-spacing:.18em;
       text-transform:uppercase;font-weight:600;text-decoration:none;
       padding:15px 30px;">Plan tonight</a>
  </td></tr>

  <tr><td style="border-top:1px solid {RULE};padding:22px 0 0;
     font-family:Helvetica,Arial,sans-serif;font-size:12px;line-height:1.6;
     color:{SOFT};">
    <p style="margin:0 0 6px;">Made by New Yorkers, for New Yorkers.</p>
    <p style="margin:0;">You are getting this because you asked for the
    newsletter when you made your account. You can turn it off from your
    account page at any time.</p>
  </td></tr>

</table>
</td></tr></table>
</body>
</html>"""


def welcome_email(user: dict[str, Any]) -> dict[str, str]:
    """Subject, recipient and body, ready for whatever sends it."""
    return {
        "to": user.get("email") or "",
        "subject": SUBJECT,
        "preheader": PREHEADER,
        "html": welcome_html(user.get("name") or ""),
    }


def queue_welcome(user: dict[str, Any]) -> Path | None:
    """Write the note to the outbox. Returns the file, or None if it could not.

    Never raises into the signup path. Someone creating an account must not see
    it fail because a folder was not writable.
    """
    try:
        OUTBOX.mkdir(parents=True, exist_ok=True)
        note = welcome_email(user)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = OUTBOX / f"{stamp}-{_safe_name(user.get('username') or '')}.html"
        path.write_text(note["html"], encoding="utf-8")
        (path.with_suffix(".txt")).write_text(
            f"To: {note['to']}\nSubject: {note['subject']}\n"
            f"Queued: {datetime.now():%d %b %Y %H:%M}\n"
            f"Status: not sent, no mail provider is configured\n",
            encoding="utf-8")
        return path
    except OSError:
        return None
