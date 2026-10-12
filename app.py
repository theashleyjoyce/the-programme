"""The Programme — FastAPI app.

    GET  /        the search page: "what's your vibe?" plus optional filters
    POST /plan    runs the agents, renders the night
    GET  /health  dataset + credential status, for the README dry run

One uvicorn command, no build step, no node_modules — which is what keeps a
fresh clone inside the assignment's ten-minute rule.
"""

from __future__ import annotations

import html
import json
import logging
import sys
import uuid
from collections import defaultdict
from datetime import date as Date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

from fastapi import FastAPI, Request                            # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles                     # noqa: E402

import accounts                                                  # noqa: E402
import pages                                                     # noqa: E402
from agents import plan_night                                   # noqa: E402
from brief import Budget, Occasion                              # noqa: E402
from budget import BudgetExceeded, TooManyCalls, status as budget_status  # noqa: E402
from collage import (collage_credit_line, collage_html,           # noqa: E402
                     suggested_seeds, suggested_vibe)
from config import MissingCredentials, model_config             # noqa: E402
from models import Setting, StopKind, VenueSize                 # noqa: E402
from render import css_version, render_night                    # noqa: E402
from sources import dataset_status, venues                      # noqa: E402

TEMPLATES = ROOT / "frontend" / "templates"
STATIC = ROOT / "frontend" / "static"
PLANS_DIR = ROOT / "output" / "plans"

# A plan costs a model call, so it is rendered once and kept. The search page
# posts here, this redirects to /night/<id>, and that URL is stable: a refresh
# re-reads the saved HTML instead of re-running the agents, the back button
# works, and the page can be sent to whoever you are going out with.
PLANS_DIR.mkdir(parents=True, exist_ok=True)
accounts.init_db()

SESSION_COOKIE = "programme_session"


def current_user(request: Request) -> dict | None:
    return accounts.user_for_session(request.cookies.get(SESSION_COOKIE))


def _set_session(response, token: str) -> None:
    """HttpOnly so page scripts cannot read it, SameSite=Lax so another site
    cannot ride the session with a cross-site POST. `secure` is left off only
    because the teaching staff will run this over plain http on localhost.
    """
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, samesite="lax",
        max_age=accounts.SESSION_DAYS * 24 * 3600, path="/",
    )

app = FastAPI(title="The Programme", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def neighborhoods_by_borough() -> dict[str, list[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for venue in venues().values():
        if venue.borough and venue.neighborhood:
            grouped[venue.borough].add(venue.neighborhood)
    return {b: sorted(n) for b, n in sorted(grouped.items())}


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (
        (TEMPLATES / "index.html").read_text(encoding="utf-8")
        .replace("{{HOODS_JSON}}", json.dumps(neighborhoods_by_borough()))
        .replace("{{CSS_V}}", css_version())
        .replace("{{VIBE_PLACEHOLDER}}", html.escape(suggested_vibe()))
        .replace("{{SEEDS}}", "".join(
            f'<button type="button" class="seed" data-vibe="{html.escape(full)}">'
            f'{html.escape(label)}</button>'
            for label, full in suggested_seeds()))
        .replace("{{COLLAGE}}", collage_html())
        .replace("{{COLLAGE_CREDIT}}", collage_credit_line())
    )


@app.get("/health")
def health() -> dict:
    """Everything a grader needs to see that setup worked."""
    try:
        cfg = model_config()
        creds = {"ok": True, "using": cfg.describe()}
    except MissingCredentials as exc:
        creds = {"ok": False, "error": str(exc)}
    return {"credentials": creds, "dataset": dataset_status(), "budget": budget_status()}


# Plain-English names for the filter values, so a generated vibe reads like a
# sentence rather than like a query string.
_WANT_WORDS = {
    "dinner": "dinner", "drinks": "drinks", "show": "live music",
    "club": "a dance floor", "hotel_bar": "a hotel bar", "tea": "tea",
    "shopping": "somewhere to shop",
    "gallery": "a gallery", "museum": "a museum", "theatre": "theatre",
    "screening": "a film", "late": "somewhere late", "dessert": "a sweet treat",
    "coffee": "coffee", "activity": "something to do",
}
_SIZE_WORDS = {
    "intimate": "somewhere small", "midsize": "a midsize room",
    "large": "a big room", "massive": "somewhere I can get lost in the crowd",
}
_SETTING_WORDS = {
    "indoor": "indoors", "outdoor": "outdoors",
    "rooftop": "on a roof", "convertible": "indoors or out",
}


def _vibe_from_filters(prefilled: dict) -> str:
    """Turn ticked filters into a sentence the Editor can work from."""
    parts: list[str] = []

    wants = [_WANT_WORDS.get(w.value, w.value) for w in prefilled.get("wants", [])]
    if wants:
        parts.append(wants[0] if len(wants) == 1
                     else ", ".join(wants[:-1]) + " and " + wants[-1])

    if sizes := [_SIZE_WORDS.get(v.value, v.value) for v in prefilled.get("venue_sizes", [])]:
        parts.append(sizes[0])
    if settings := [_SETTING_WORDS.get(v.value, v.value) for v in prefilled.get("settings", [])]:
        parts.append(settings[0])

    if prefilled.get("roam"):
        parts.append("happy to range across the city")

    occasion_words = {
        "date": "it is a date", "birthday": "it is a birthday",
        "celebration": "we are celebrating", "friends_visiting": "friends are in town",
        "solo": "I am on my own", "work": "it is work people",
    }
    occasion = prefilled.get("occasion")
    if occasion and (phrase := occasion_words.get(occasion.value)):
        parts.append(phrase)

    if party := prefilled.get("party_size"):
        if party > 2:
            parts.append(f"there are {party} of us")

    return ", ".join(parts)


def _error_page(title: str, detail: str) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>{title} — The Programme</title>
<link rel="stylesheet" href="/static/night.css"></head><body>
<header class="masthead"><h1 class="masthead__title">The Programme</h1>
<span class="masthead__meta"><a href="/" style="color:inherit">Start again</a></span></header>
<div class="error"><strong>{title}</strong>{detail}</div></body></html>"""


FORM_FIELDS = ("vibe", "date", "borough", "neighborhood", "party_size",
               "budget", "occasion", "roam", "suggested")
FORM_LISTS = ("venue_sizes", "settings", "wants")


@app.get("/working", response_class=HTMLResponse)
def working(request: Request) -> str:
    """Opens instantly, then fetches the plan and replaces itself.

    The form targets this rather than POSTing straight to /plan, so a new tab
    shows something immediately instead of sitting blank while two model calls
    run. The work is identical; what changes is that the user can see it
    happening.
    """
    q = request.query_params
    payload: dict = {k: q.get(k, "") for k in FORM_FIELDS}
    for k in FORM_LISTS:
        payload[k] = q.getlist(k)

    vibe = (payload.get("vibe") or "").strip()
    # Show the suggestion on the working page too, so the night they are
    # waiting for is the one they saw.
    shown = vibe or (payload.get("suggested") or "").strip() or "whatever you picked"

    return (
        (TEMPLATES / "working.html").read_text(encoding="utf-8")
        .replace("{{CSS_V}}", css_version())
        .replace("{{VIBE_PLACEHOLDER}}", html.escape(suggested_vibe()))
        .replace("{{SEEDS}}", "".join(
            f'<button type="button" class="seed" data-vibe="{html.escape(full)}">'
            f'{html.escape(label)}</button>'
            for label, full in suggested_seeds()))
        .replace("{{VIBE}}", html.escape(shown))
        .replace("{{PAYLOAD}}", json.dumps(payload))
    )


@app.get("/night/{plan_id}", response_class=HTMLResponse)
def saved_night(plan_id: str) -> str:
    """A previously planned night. Stable URL, no model call."""
    if not plan_id.isalnum() or len(plan_id) > 40:
        return _error_page("No such plan", "That link does not look right.")
    path = PLANS_DIR / f"{plan_id}.html"
    if not path.is_file():
        return _error_page(
            "That night has expired",
            'Plans are kept on disk next to the app. '
            '<a href="/">Plan a new one</a>.',
        )
    return path.read_text(encoding="utf-8")


@app.post("/plan")
async def plan(request: Request):
    form = await request.form()

    wants_json = "application/json" in (request.headers.get("accept") or "")

    def fail(title: str, detail: str, status: int = 400):
        if wants_json:
            return JSONResponse({"detail": f"{title}. {detail}"}, status_code=status)
        return HTMLResponse(_error_page(title, detail))

    vibe = (form.get("vibe") or "").strip()

    def enum_list(field: str, cls):
        out = []
        for raw in form.getlist(field):
            try:
                out.append(cls(raw))
            except ValueError:
                continue          # ignore anything not in the enum
        return out

    prefilled: dict = {
        "neighborhood": (form.get("neighborhood") or "").strip() or None,
        "borough": (form.get("borough") or "").strip() or None,
        "venue_sizes": enum_list("venue_sizes", VenueSize),
        "settings": enum_list("settings", Setting),
        "wants": enum_list("wants", StopKind),
    }

    if raw_date := (form.get("date") or "").strip():
        try:
            prefilled["date"] = Date.fromisoformat(raw_date)
        except ValueError:
            pass
    if raw_party := (form.get("party_size") or "").strip():
        if raw_party.isdigit() and 1 <= int(raw_party) <= 60:
            prefilled["party_size"] = int(raw_party)
    if raw_budget := (form.get("budget") or "").strip():
        try:
            prefilled["budget"] = Budget(raw_budget)
        except ValueError:
            pass
    if (form.get("roam") or "").strip():
        prefilled["roam"] = True

    if raw_occasion := (form.get("occasion") or "").strip():
        try:
            prefilled["occasion"] = Occasion(raw_occasion)
        except ValueError:
            pass

    # Three ways to ask, in order of how specific they are.
    #
    #   1. what they typed
    #   2. the filters they ticked, which are a complete request on their own
    #   3. the suggestion that was on screen when they pressed go
    #
    # The third matters most for someone with no idea what they want. Pressing
    # the button under "a museum that stays open late, then noodles" is a
    # choice, and refusing it with "tell me something to go on" would turn the
    # one moment of inspiration the page offers into an error message.
    if not vibe:
        vibe = _vibe_from_filters(prefilled)
    if not vibe:
        vibe = (form.get("suggested") or "").strip().rstrip("…").strip()
    if not vibe:
        return fail("Tell me something to go on",
                    "Either describe the night, or pick a few filters below.")

    try:
        result = plan_night(vibe, prefilled=prefilled)
    except BudgetExceeded as exc:
        return fail("Budget reached",
                    f"{exc} This is a deliberate stop, not a failure: a hard cap "
                    f"refuses the call rather than spending past the limit.")
    except TooManyCalls as exc:
        return fail("Stopped a runaway request", str(exc))
    except MissingCredentials as exc:
        return fail("No API key found", str(exc))
    except Exception as exc:                                   # noqa: BLE001
        # Log the traceback server-side. An error the user sees but nobody can
        # diagnose is the worst of both worlds.
        logging.exception("plan failed for vibe=%r", vibe[:120])
        return fail(
            "That didn't work",
            "Something went wrong putting that night together. "
            "Trying a slightly different vibe usually sorts it.",
            status=500,
        )

    page = render_night(
        result["night"],
        brief=result["brief"],
        usage=result["usage"].as_dict(),
        dataset=result["dataset"],
        budget=result["budget"],
    )

    plan_id = uuid.uuid4().hex[:12]
    (PLANS_DIR / f"{plan_id}.html").write_text(page, encoding="utf-8")

    if wants_json:
        return JSONResponse({
            "redirect": f"/night/{plan_id}",
            "seconds": result["seconds"],
            "timings": result["timings"],
            "used_web_search": result["used_web_search"],
        })

    # 303 so the browser follows with GET: refreshing the result never re-posts
    # the form, and therefore never spends another model call.
    return RedirectResponse(url=f"/night/{plan_id}", status_code=303)


# ---------------------------------------------------------------- accounts

@app.get("/about", response_class=HTMLResponse)
def about(request: Request) -> str:
    from collections import Counter

    from planner import catalogue

    rows = catalogue()
    kinds = Counter(r["category"] for r in rows)
    hoods = {r["neighborhood"] for r in rows if r.get("neighborhood")}
    rooms = sum(1 for r in rows if r.get("capacity"))

    # One sentence, counted from the same list every time, so the numbers
    # cannot disagree with each other the way two separate counters did.
    line = (f"{len(rows):,} places across {len(kinds)} kinds of evening "
            f"and {len(hoods)} neighborhoods, in all five boroughs"
            + (f", {rooms} of them with the room size on file." if rooms else "."))

    return pages.about_page(css_version(), current_user(request), {"line": line})


@app.get("/signup", response_class=HTMLResponse)
def signup_form(request: Request) -> str:
    if current_user(request):
        return RedirectResponse("/saved", status_code=303)
    return pages.signup_page(css_version(), user=None)


@app.post("/signup")
async def signup(request: Request):
    form = await request.form()
    values = {"username": (form.get("username") or "").strip(),
              "email": (form.get("email") or "").strip()}
    try:
        user_id = accounts.create_user(
            email=values["email"],
            username=values["username"],
            password=form.get("password") or "",
            newsletter=bool(form.get("newsletter")),
        )
    except accounts.AccountError as exc:
        return HTMLResponse(pages.signup_page(css_version(), error=str(exc), values=values),
                            status_code=400)

    response = RedirectResponse("/saved", status_code=303)
    _set_session(response, accounts.start_session(user_id))
    return response


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> str:
    if current_user(request):
        return RedirectResponse("/saved", status_code=303)
    return pages.login_page(css_version(), user=None)


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    identifier = (form.get("identifier") or "").strip()
    user_id = accounts.verify_login(identifier, form.get("password") or "")
    if user_id is None:
        # One message for both wrong-password and no-such-user: saying which
        # tells a stranger whether an account exists.
        return HTMLResponse(
            pages.login_page(css_version(), error="That username or password is not right.",
                             values={"identifier": identifier}),
            status_code=401)

    response = RedirectResponse("/saved", status_code=303)
    _set_session(response, accounts.start_session(user_id))
    return response


@app.get("/logout")
def logout(request: Request):
    accounts.end_session(request.cookies.get(SESSION_COOKIE))
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@app.get("/saved", response_class=HTMLResponse)
def saved(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(pages.saved_page(css_version(), user, accounts.saved_for(user["id"])))


@app.post("/night/{plan_id}/save")
async def save_night(plan_id: str, request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not plan_id.isalnum() or len(plan_id) > 40:
        return RedirectResponse("/", status_code=303)

    form = await request.form()
    accounts.save_night(
        user["id"], plan_id,
        summary=(form.get("summary") or "A night out")[:300],
        headline=(form.get("headline") or "")[:120],
        night_date=(form.get("night_date") or "")[:20],
        neighborhood=(form.get("neighborhood") or "")[:80],
    )
    return RedirectResponse(f"/night/{plan_id}", status_code=303)


@app.post("/saved/{plan_id}/went")
def saved_went(plan_id: str, request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    already = any(n["plan_id"] == plan_id and n["went"] for n in accounts.saved_for(user["id"]))
    accounts.mark_went(user["id"], plan_id, went=not already)
    return RedirectResponse("/saved", status_code=303)


@app.post("/saved/{plan_id}/remove")
def saved_remove(plan_id: str, request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    accounts.unsave_night(user["id"], plan_id)
    return RedirectResponse("/saved", status_code=303)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)