# The Programme

**New York, Your Way.** Describe your vibe and it plans your night: somewhere
to eat, somewhere to go after, close enough together that the evening does not
turn into a commute.

Built for MGT 409, AI Foundations for Managers.

---

## Run it

You need Python 3.11 or newer. From a fresh clone:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open **http://127.0.0.1:8000**.

That is the whole setup. No database server, no node, no build step.

### The API key

The app looks for a `.env` in two places, in this order:

1. this repo's own folder
2. **the folder one level above it**

Both are read, and the repo's own file wins where they overlap. So the standard
grading layout works with no changes:

```
submissions/
├── .env                 <-- your keys here
└── the-programme/       <-- this repo
```

It needs **one** of these two keys, and uses whichever it finds:

| Key | Model | Notes |
|---|---|---|
| `OPENAI_API_KEY` | `gpt-5.6-luna` | Preferred. Used by default. |
| `PORTKEY_API_KEY` | `gpt-6-luna` | Course key. Used if it is the only one present. |

If the first choice is rejected it falls back to the other automatically rather
than failing. Set `MODEL_PROVIDER=portkey` to force the course key.

See `.env.example` for every supported setting.

### Check it worked

```bash
curl http://127.0.0.1:8000/health
```

Reports which credential it found, how much data is loaded, and the spend so far.

---

## What to try

| | |
|---|---|
| Type a vibe | *"loud and a little sweaty, somewhere we can actually dance"* |
| Use only the filters | Tick **Late night** and **Sweet treat**, leave the text box empty |
| A group | Set **How many** to 8 and **Occasion** to *A birthday* |
| The room, not the genre | Tick **Intimate** against **Massive** and compare |
| Indoors or out | Tick **Outdoor** and plan a night in January |

Most plans return in about a second. A request the local data cannot cover
falls back to a live model call and takes longer.

---

## The data

Everything the app reads is committed, so it runs with no scraping and no
second API key:

| File | What it holds |
|---|---|
| `data/nyc_venues.json` | Venues with rooms, capacities, settings, coordinates |
| `data/candidate_venues.json` | Venues found across the city's editorial listings |
| `data/subway_stations.json` | 493 MTA stations, for nearest-train and walk times |
| `data/venue_copy.json` | The written entry for each venue |
| `data/venue_photos.json` | Venue photographs, where an appropriate one exists |

Refreshing it is offline work and is **not** needed to run the app:

```bash
python scripts/discover_venues.py --core     # find venues, by neighborhood
python scripts/enrich_capacity.py --venue X  # research one venue's rooms
python scripts/write_venue_copy.py --limit 40
python scripts/geocode_venues.py --limit 50  # free, OpenStreetMap
python scripts/fetch_transit.py              # free, MTA open data
```

---

## Spending

A hard cap lives in `backend/budget.py` and is enforced before every model
call, against a ledger at `output/spend_ledger.json` that survives restarts.

```bash
BUDGET_USD=10.00        # in .env
```

At the limit the app refuses the call and says so. One request may also make at
most `MAX_CALLS_PER_RUN` model calls, so a retry loop cannot drain the budget.

---

## Safety

```bash
python demo_attack.py
```

Runs four attacks against the app and shows what stops each one: an injected
instruction in a venue listing, the same thing hidden in zero-width characters,
a hallucinated venue with no source, and a fake booking link on a lookalike
domain.

The app never completes a booking. Every button opens the venue's own page, and
links on unrecognised domains are stripped rather than shown.

---

## Accounts

Optional. An account saves the nights you plan and lets you opt in to the
newsletter.

Passwords are hashed with PBKDF2-HMAC-SHA256, 600,000 rounds, with a unique
salt, and are never stored or logged as text. Sessions are random server-side
tokens in an HttpOnly cookie. The database is `data/accounts.db` and is
gitignored, so no user data is ever committed.

Not implemented, and deliberately so for a course project: email verification,
password reset, and rate limiting beyond the per-run cap.

---

## Layout

```
app.py                  routes
backend/
  planner.py            builds a night from local data, no model call
  agents.py             Concierge and Editor, and the model fallback
  models.py             every typed object
  budget.py             the spending cap and ledger
  sanitize.py           prompt-injection defences, booking-link allowlist
  accounts.py           users, sessions, saved nights
  sources.py            search over venues and rooms
  transit.py            nearest subway station
  render.py             a Night as an editorial page
  pages.py              about, signup, login, saved
  prompts/              each agent's instructions, as markdown
frontend/               one stylesheet, three templates, images
data/                   everything above, committed
scripts/                offline data building
output/                 plans, the spend ledger, logs
```

---

Built by Ashley Wheeler. New York, 2026.
