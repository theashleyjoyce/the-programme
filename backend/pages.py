"""HTML for the account pages.

Kept out of app.py so the routes stay readable, and out of render.py because
that module is about rendering a Night. Same editorial shell, different body.
"""

from __future__ import annotations

import html
from pathlib import Path

from collage import memory_image

TEMPLATES = Path(__file__).resolve().parent.parent / "frontend" / "templates"


def e(value: object) -> str:
    return html.escape(str(value), quote=True) if value is not None else ""


def nav_for(user: dict | None) -> str:
    if user:
        return ('<a href="/about">About</a>'
                '<a href="/saved">Your nights</a>'
                '<a href="/logout">Log out</a>')
    return ('<a href="/about">About</a>'
            '<a href="/login">Log in</a>'
            '<a href="/signup">Sign up</a>')


def _shell(*, title: str, kicker: str, blurb: str, action: str, fields: str,
           cta: str, alt: str, error: str, css_v: str, user: dict | None) -> str:
    error_html = f'<div class="account__error">{e(error)}</div>' if error else ""
    return (
        (TEMPLATES / "account.html").read_text(encoding="utf-8")
        .replace("{{TITLE}}", e(title))
        .replace("{{KICKER}}", e(kicker))
        .replace("{{BLURB}}", e(blurb))
        .replace("{{ACTION}}", e(action))
        .replace("{{FIELDS}}", fields)
        .replace("{{CTA}}", e(cta))
        .replace("{{ALT}}", alt)
        .replace("{{ERROR}}", error_html)
        .replace("{{CSS_V}}", e(css_v))
        .replace("{{NAV}}", nav_for(user))
    )


def signup_page(css_v: str, error: str = "", values: dict | None = None,
                user: dict | None = None) -> str:
    v = values or {}
    fields = f"""
    <div class="account__field">
      <label for="username">Username</label>
      <input type="text" id="username" name="username" required autocomplete="username"
             value="{e(v.get('username', ''))}" minlength="3" maxlength="24"
             pattern="[A-Za-z0-9_.\\-]{{3,24}}">
      <span class="account__note">3 to 24 characters. Letters, numbers, dots, dashes, underscores.</span>
    </div>
    <div class="account__field">
      <label for="email">Email</label>
      <input type="email" id="email" name="email" required autocomplete="email"
             value="{e(v.get('email', ''))}">
    </div>
    <div class="account__field">
      <label for="password">Password</label>
      <input type="password" id="password" name="password" required
             autocomplete="new-password" minlength="10">
      <span class="account__note">At least 10 characters. Length beats punctuation.</span>
    </div>
    <label class="account__check">
      <input type="checkbox" name="newsletter" value="1">
      <span><strong>Send me the newsletter.</strong> A curated note on what is
      worth going to, and the new places opening around the city.
      <a href="/newsletter/preview" target="_blank" rel="noopener">See it first</a>.</span>
    </label>
    """
    return _shell(
        title="Create an account", kicker="The Programme",
        blurb="Keep the nights you plan, revisit the spots you love.",
        action="/signup", fields=fields, cta="Create account",
        alt='Already have one? <a href="/login">Log in</a>.',
        error=error, css_v=css_v, user=user)


def login_page(css_v: str, error: str = "", values: dict | None = None,
               user: dict | None = None) -> str:
    v = values or {}
    fields = f"""
    <div class="account__field">
      <label for="identifier">Username or email</label>
      <input type="text" id="identifier" name="identifier" required
             autocomplete="username" value="{e(v.get('identifier', ''))}">
    </div>
    <div class="account__field">
      <label for="password">Password</label>
      <input type="password" id="password" name="password" required
             autocomplete="current-password">
    </div>
    """
    return _shell(
        title="Log in", kicker="The Programme",
        blurb="Your plans await.",
        action="/login", fields=fields, cta="Log in",
        alt='No account yet? <a href="/signup">Create one</a>.',
        error=error, css_v=css_v, user=user)


def about_page(css_v: str, user: dict | None, facts: dict) -> str:
    """What this is, how it works, and where the data comes from.

    Written in plain language on purpose. A reader who wants to know whether to
    trust a recommendation should be able to find out in one page, and saying
    how the sausage is made is part of earning that trust.
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>About — The Programme</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bodoni+Moda:ital,opsz,wght@0,6..96,400..700;1,6..96,400..600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/night.css?v={e(css_v)}">
</head>
<body>
<header class="masthead">
  <a class="masthead__home" href="/">The Programme</a>
  <nav class="masthead__nav">{nav_for(user)}</nav>
</header>

<article class="about">
  <p class="hero__kicker">About</p>

  <div class="about__hero">
    <h2 class="about__title">New York,<br>Your Way</h2>
    <img class="about__art" src="/static/img/programme.svg" alt="" aria-hidden="true">
  </div>

  <p class="about__lead">For the explorers, the city lovers, the lovers and the
  friends. Your one stop shop for daytime or night time plans in New York City.</p>

  <p class="about__lead about__lead--second">Born out of a love for food,
  fashion, live music and the kind of culture you can only get in a city this
  good. However you want the night to feel, it is out there. We will find it.</p>

  <p class="about__stamp">Made by New Yorkers, for New Yorkers.</p>

  <section class="about__block">
    <h3>Who we are</h3>
    <p>New York is not short of options. It is short of a way through them.</p>
    <p>The Programme is the editor we wanted and could not find. It reads the
    city so you do not have to, and returns a single evening that holds
    together. Somewhere to eat. Somewhere to go after. Close enough that the
    night does not become a commute.</p>
    <p>We built it for the table of eight that needs a room which will take
    them. For the second date that needs somewhere you can hear each other
    think. For the Friday with forty dollars in it that should still feel like
    something. The city holds an evening for each of them. The looking is what
    gets in the way.</p>
  </section>

  <section class="about__block">
    <h3>What we do</h3>
    <p>Tell us the vibe. We plan the night.</p>
    <p>Behind that, we keep a standing file on the city. What is open, which
    room you would be in, how big it is, whether it takes a group, what is on
    this week. It is checked and written up before you ever ask, which is why
    the answer arrives in about a second.</p>
    <p>What we are really after is discovery. The opening you would not have
    thought to look for. The tea room that keeps late hours. The basement with
    a sound system better than it has any right to be. We are built with a bias
    against the obvious, because a recommendation you could have made yourself
    is not worth making.</p>
    <p>And we pay attention to the room. A night in a space that holds eighty
    is not a night in one that holds three thousand, and a yard in July is not
    the same place in January. So we know which of a venue's rooms you would be
    standing in, how big it is, whether it sits indoors or out, and whether
    they will seat all eight of you.</p>
    <p>Say it in a sentence or set it with the filters. Either way you get one
    evening, in order, with the booking links and the nearest train.</p>

    <p class="about__count">{e(facts.get("line", ""))}</p>
  </section>

  <section class="about__block">
    <h3>What it will not do</h3>
    <p>It never completes a booking for you. Every Book button opens the
    venue's own page, and links that are not on a recognised booking domain are
    stripped rather than shown.</p>
    <p>It will not recommend a venue it cannot attribute, and it will not claim
    a room fits your group when nobody has checked.</p>
  </section>

  <section class="about__block">
    <h3>Your account</h3>
    <p>An account stores your email, your username, a hashed password, and the
    nights you saved. Passwords are hashed, never stored as text. The
    newsletter is opt in, never pre-ticked, and you can turn it off from your
    account in one click.</p>
  </section>

  <p class="about__sig">Built by Ashley Wheeler. New York, 2026.</p>
  <p class="about__credit">Maps &copy; OpenStreetMap contributors. Transit data
  from the MTA. Venue photographs belong to the venues.</p>
</article>
</body>
</html>"""


def _polaroid(night: dict) -> str:
    """A picture for a saved night, in the space beside it.

    A placeholder until people can add their own, and it says so rather than
    passing someone else's evening off as yours.
    """
    shot = memory_image(night.get("plan_id") or "")
    if not shot:
        return ""
    caption = night.get("night_date") or night.get("neighborhood") or "A night out"
    mine = shot.get("is_original")
    return (
        f'<figure class="polaroid">'
        f'<img src="{e(shot["src"])}" alt="" loading="lazy" decoding="async">'
        f'<figcaption>{e(caption)}</figcaption>'
        f'</figure>' if mine else
        f'<figure class="polaroid polaroid--stock" '
        f'title="A stand-in photograph, not from this night">'
        f'<img src="{e(shot["src"])}" alt="" loading="lazy" decoding="async">'
        f'<figcaption>{e(caption)}</figcaption>'
        f'</figure>'
    )


def saved_page(css_v: str, user: dict, nights: list[dict]) -> str:
    if nights:
        items = []
        for n in nights:
            went = " is-on" if n.get("went") else ""
            label = "Went" if n.get("went") else "Mark as went"
            meta = " · ".join(x for x in [n.get("night_date") or "",
                                          n.get("neighborhood") or ""] if x)
            items.append(f"""
            <article class="saved__item">
              <div>
                <p class="saved__summary">
                  <a href="/night/{e(n['plan_id'])}">{e(n['summary'])}</a>
                </p>
                <p class="saved__meta">{e(meta)}</p>
              </div>
              <div class="saved__actions">
                <form method="post" action="/saved/{e(n['plan_id'])}/went" style="display:inline">
                  <button type="submit" class="went{went}">{e(label)}</button>
                </form>
                <form method="post" action="/saved/{e(n['plan_id'])}/remove" style="display:inline">
                  <button type="submit">Remove</button>
                </form>
              </div>
              {_polaroid(n)}
            </article>""")
        body = "".join(items)
    else:
        body = ('<p class="saved__empty">Nothing saved yet. '
                '<a href="/">Plan a night</a> and hit save on it.</p>')

    went_count = sum(1 for n in nights if n.get("went"))
    count = (f"{len(nights)} saved" + (f" · {went_count} attended" if went_count else "")
             if nights else "")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Your nights — The Programme</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bodoni+Moda:ital,opsz,wght@0,6..96,400..700;1,6..96,400..600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/night.css?v={e(css_v)}">
</head>
<body>
<header class="masthead">
  <a class="masthead__home" href="/">The Programme</a>
  <nav class="masthead__nav">{nav_for(user)}</nav>
</header>

<section class="saved">
  <div class="saved__head">
    <h2 class="saved__title">Your nights</h2>
    <span class="saved__count">{e(count)}</span>
  </div>
  {body}
</section>
</body>
</html>"""
