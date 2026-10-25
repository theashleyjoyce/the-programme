"""The words of the report. Numbers come from the live app, not from here.

Kept separate from build_report.py so Ashley can edit prose without touching
the machinery, and so a figure can never be stale: anything in {braces} is
filled from the ledger, the dataset and the guardrail suite at build time.

Section order follows the assignment exactly:
  1 Title + links   2 Motivation   3 What is new   4 The agents
  5 Tokenomics      6 Safety       7 Impact        8 Limits + next steps
"""

TITLE = "The Programme"
TAGLINE = "New York, Your Way"
AUTHOR = "Ashley Wheeler"
COURSE = "MGT 409 — AI Foundations for Managers"
ONE_LINER = (
    "Describe the night you want and it plans it: somewhere to eat, somewhere "
    "to go after, close enough together that the evening does not become a "
    "commute."
)

# TO FILL IN before submitting.
REPO_URL = "https://github.com/theashleyjoyce/the-programme"
APP_URL = ""           # leave empty if it is not hosted

MOTIVATION = [
    ("Going out in New York is a research project.",
     """Eater for the restaurant. The Infatuation to check it. Resident Advisor
     for who is playing. A listings site for the gallery opening. A ticket page
     to see if anything is left. Then a map, to find out whether any of it is
     near any of the rest. Nine tabs, four opinions that disagree, and a
     decision still to make."""),

    ("The cost is not the time. It is the night that does not happen.",
     """The research is tiring enough that the easy answer wins: the same bar as
     last time, chosen at eleven o'clock because it was the only option still
     in your head. That is not a preference. It is what decision fatigue looks
     like from the inside, and the city you moved here for goes unvisited
     while it happens."""),

    ("It is worse the more specific you are.",
     """A table for eight needs somewhere that will take eight. A second date
     needs somewhere you can hear each other. A birthday needs a room that
     feels like one. None of the listings sites let you ask for any of that,
     so the people with the most particular needs do the most work."""),

    ("And nothing puts the pieces together.",
     """Each of those nine tabs answers one question. Where to eat. What is on.
     Whether there are tickets left. None of them answers the actual question,
     which is what the whole evening looks like: where to start, what comes
     after, whether the two are anywhere near each other, and whether it adds
     up to a night rather than a list of places."""),

    ("Who this is for.",
     """Anyone going out in New York, but sharply: groups who need a room that
     fits them, people new to a neighbourhood, anyone who has noticed they
     keep going to the same three places and would like to stop."""),
]

WHATS_NEW_INTRO = """
There is no shortage of products here, and several are close. Being honest
about that is the point of this section."""

COMPETITORS = [
    ("Tyra", "usetyra.com",
     "An AI concierge for going out in NYC. Chat interface, plain-English "
     "requests, returns plans with reservation links.",
     "Closest competitor, and the only one also attempting a plan. It returns "
     "suggestions in a chat window; we return a sequenced evening with times, "
     "walking distances and the room size, laid out as a page."),
    ("Sift", "NYC events app",
     "Swipe through curated events across art, music, food, nightlife.",
     "A discovery feed, not a planner. It will not sequence a night or tell "
     "you whether two stops are walkable."),
    ("Nightlife AI", "iOS",
     "Recommends bars and clubs by location, age and vibe, with a chat.",
     "Nightlife only. No dinner, no galleries, no sequencing."),
    ("The Scene", "TechCrunch-covered, 2024",
     "Matches New Yorkers with restaurants, bars and clubs.",
     "Matching, not planning. The AI features described in coverage do not "
     "appear to have shipped."),
    ("Fever", "feverup.com",
     "Large events and ticketing platform with personalised recommendations.",
     "A marketplace. It sells you one event and stops. No dinner before, "
     "nothing after, no sense of an evening."),
    ("ChatGPT", "general assistant",
     "Will happily suggest a night out in New York if asked.",
     "No verified room sizes, no check that a link opens the right venue, no "
     "travel time between stops, and it will invent a closed restaurant "
     "without hesitation."),
]

WHATS_NEW_CLAIMS = [
    ("We plan a night, not a venue.",
     """This is the difference that matters most, and it is the one every
     product above shares. They return options: a list, a feed, a ranked set of
     bars. The deciding, the ordering and the working out of whether any of it
     fits together is still left to you, which is precisely the work that was
     exhausting in the first place.

     The Programme returns a complete evening. A gallery opening at six, dinner
     at half seven, a small room with a DJ at eleven, somewhere for a sweet
     treat after. Different kinds of activity, in a sensible order, timed so
     one finishes before the next begins, close enough together to walk, and
     chosen to match a single stated vibe rather than assembled from separate
     searches.

     Nobody else crosses categories. A nightlife app will not book your dinner.
     A restaurant guide does not know what is on at the venue round the corner.
     A ticketing platform sells you one event and stops. Stitching those
     together is the job people are actually doing by hand across nine tabs,
     and it is the job we took."""),

    ("We model the room, not the listing.",
     """Every product above filters on genre, date, neighbourhood and price.
     None of them know how big the room is. But a night in a space that holds
     eighty is not a night in one that holds three thousand, and a yard in
     July is not the same place in January. We hold the capacity of each room,
     whether it is indoors or out, which of a venue's several spaces you would
     be standing in, and whether it will seat a party of twelve. Nowadays is
     not one venue to us: it is a 269-capacity indoor room and an 800-capacity
     yard, and they are different nights."""),

    ("We sequence, and we respect travel.",
     """A plan is stops in order, with real walking times between them, and a
     bias toward keeping the night tight. Less time on the train means more of
     the evening spent somewhere. Anyone who wants to range across the city
     can say so and the radius opens up."""),

    ("We are biased against the obvious.",
     """A recommendation you could have made yourself is not worth making. The
     planner shuffles among the strongest matches rather than returning the
     same famous answer every time, and the corpus is built from local and
     niche coverage as well as the national titles."""),

    ("We do not pretend to certainties we do not have.",
     """A room whose capacity nobody has checked is never offered to a group. A
     venue that only opens for ticketed events says so rather than implying you
     can walk in. A booking link is shown only once we have fetched the page
     and confirmed it names that venue."""),
]

AGENTS_INTRO = """
Seven agents across two tiers. The split is the main design decision in the
project and the one worth defending: the expensive work runs once, offline,
and is shared by every user, rather than being repeated for each visitor.

What remains at request time is the work a database genuinely cannot do:
reading what someone meant, judging whether the result is any good, and
understanding an amendment to a plan already on screen."""

AGENTS = [
    ("Scout", "offline", "web_search",
     "Reads the city's editorial listings one neighbourhood at a time and "
     "returns candidate venues with category, price band, group policy, "
     "website, coordinates and which publications recommended them.",
     "Eater, The Infatuation, Grub Street, Vogue, Condé Nast Traveler, Time "
     "Out, Resident Advisor, Brooklyn Vegan, Artforum, Hyperallergic, local "
     "neighbourhood press."),
    ("Researcher", "offline", "web_search",
     "Takes one venue and finds its rooms, capacities, settings and policies, "
     "each with a citation. Reports conflicting published figures rather than "
     "choosing one.",
     "Venue's own site, Wikipedia, promoter listings, press coverage."),
    ("Writer", "offline", "none",
     "Turns a researched venue into the one or two sentences that appear on "
     "its card, plus the specific thing to order or the room to stand in.",
     "Works only from what the other two found."),
    ("Concierge", "per request", "none",
     "Turns what someone typed into a structured brief: what kind of evening, "
     "how many people, which area, what budget, what style. Skipped entirely "
     "when the filters already say it.",
     "No tools. Reading, not searching."),
    ("Editor", "per request, fallback only", "web_search",
     "Plans the whole evening itself when the corpus cannot cover the "
     "request, and writes the line that ties it together.",
     "Live web search, with everything it returns treated as untrusted."),
    ("Critic", "per request", "none",
     "Reads the assembled plan before anyone sees it and judges it the way a "
     "person would: does it answer what they asked, does the timing work, is "
     "it one evening or two unrelated halves. Names a single stop to drop, "
     "and the planner rebuilds without it.",
     "The plan and the brief. Nothing else; it judges, it never writes."),
    ("Refiner", "per request, on a change", "none",
     "Turns 'cheaper' or 'swap the second one' into a structured amendment "
     "the planner can apply, protecting whatever the person did not complain "
     "about.",
     "The plan on screen and one message."),
]

PLANNER_NOTE = """
The Planner is deliberately **not** an agent, and that is the decision this
section exists to argue. It is also why the Critic exists: a deterministic
planner is fast and predictable and structurally unable to notice that its own
output does not work as an evening. Judgment is the one thing it cannot do, so
that is exactly the job given to a model. Choosing venues that match a request is filtering.
Sequencing them is arithmetic. The prose about a venue does not change between
visitors, so it is written once and cached. None of that needs a language
model, so none of it uses one. What remains for a model at request time is
reading the sentence someone typed, and often not even that."""

MODELS_NOTE = """
`gpt-5.6-luna` throughout, through a direct OpenAI client. The assignment names
`gpt-6-luna` on the course Portkey key; that key was rejected by the gateway on
every authentication method tried, and the instructor has already approved the
substitution for coursework. The app still supports both and falls back
automatically, so a grader with a working course key is covered either way.
Every agent returns a schema-validated object rather than free text."""

TOKENOMICS_INTRO = """
Every figure below comes from `output/spend_ledger.json`, which records each
model call the project has ever made, including the ones made while building
the dataset. Nothing here is estimated except where it says so."""

COST_CUTTING = [
    ("Move the expensive agents offline.",
     """The Scout, Researcher and Writer run on a refresh, not per visitor.
     Their cost is paid once and amortised across every plan ever served."""),
    ("Do not use a model for work that is not language work.",
     """Filtering and sequencing became ordinary Python. This removed roughly
     2,000 output tokens from every single request."""),
    ("Skip the Concierge when the form already says it.",
     """A complete set of filters is an unambiguous request. Re-reading it with
     a model is a round trip that buys nothing."""),
    ("Keep the one remaining prompt stable so it caches.",
     """The Concierge instructions do not change between requests, so they are
     served from the provider's prompt cache."""),
    ("Reach for web search only when the corpus cannot answer.",
     """Search is the single most expensive thing the app can do, in both money
     and latency. It is a fallback, not a default."""),
]

PERFORMANCE_TRADEOFF = """
Yes, and it is worth stating plainly. Venue copy is now written once per venue
rather than per request, so a card's description does not know that this
particular visitor said "birthday, eight of us". The connective sentence is
still written per request and the structural facts still respond to the brief,
but the prose is general.

This is the same tradeoff a city guide makes. The Infatuation writes one review
per restaurant, not one per reader. We judged a one-second plan with general
prose to be worth more than a twenty-five-second plan with bespoke prose, and
the measured difference is below.

The second cost is coverage. The fast path can only recommend what is in the
corpus, so a request the dataset does not cover falls through to the model and
takes roughly thirty seconds instead of three."""

SAFETY_INTRO = """
The app reads third-party editorial pages, venue listings and live search
results, and it shows people links they are expected to click. That makes
prompt injection the central risk rather than a bolted-on one, and a wrong
booking link the most expensive failure.

Every defence below is exercised by `test_guardrails.py`, which runs them all
and reports pass or fail."""

SAFETY_STORIES = [
    ("A defence that was wrong, found by a real run",
     """The first version of the booking-link allowlist blocked
     `calendar.houseofyes.org` — House of Yes's own booking page. Over-blocking
     is not safety; it removes the useful half of the product and trains people
     to go and find the link somewhere less careful. The check now asks a
     different question: not "is this on my list" but "is this pretending to be
     on my list". A venue's own domain passes. `resy.com.secure-booking.io`
     does not."""),

    ("A link that resolved, and was still wrong",
     """A plan came back with a Book a table button pointing at
     `opentable.com/restaurant/profile/1394212`. It returned HTTP 200, so
     nothing downstream complained. Nothing confirmed it was the right
     restaurant either, and it was not: the Editor had produced it from memory.
     A link that resolves but opens the wrong venue is worse than no link,
     because nobody finds out until they arrive. Booking links are now shown
     only when the page has been fetched and confirmed to name that venue."""),

    ("A critic that catches what the filters cannot",
     """The planner matched categories, respected every filter and kept the
     stops close together, and still produced an evening with a three-hour hole
     in it between dinner and an eleven o'clock dance floor. No filter can
     express that objection. The Critic reads the finished plan and says so in
     the terms a person would, and the planner rebuilds without the stop it
     named."""),

    ("Failing without losing the plan",
     """An invented venue used to fail schema validation and take the whole
     evening down with it, returning a 500. The model's answer now lands in a
     lenient draft; a repair step fills what it can from our own data and drops
     only what it cannot attribute. One missing fact costs one stop, not the
     night."""),
]

IMPACT_INTRO = """
Two kinds of number here, kept apart on purpose: what has been measured, and
what has been estimated. The rubric asks for sources, and an honest estimate
labelled as one is worth more than a confident figure with nothing behind it."""

LIMITS = [
    ("Opening hours are not checked.",
     """The planner assigns times from a table of typical hours. It does not
     know that a restaurant closes on Mondays. OpenStreetMap returns an
     `opening_hours` field free alongside the geocoding we already do, and
     collecting it is the single most valuable next piece of work."""),
    ("No event calendar.",
     """The app knows venues, not what is on at them tonight. For a ticketed
     room it can only say "check what is on", which is honest but thin. A
     Ticketmaster Discovery feed would close most of this."""),
    ("Coverage is uneven.",
     """{mapped} of {venues} venues have coordinates, so the rest show no map
     and no walking time. OpenStreetMap's coverage of small businesses is
     patchy, and worst in the outer boroughs."""),
    ("Some kinds of night are thinly covered.",
     """Comedy, karaoke, games, markets and parks were added late, so the
     corpus holds far fewer of them than it does restaurants and bars. The
     planner refuses to offer a venue that does not say it is that kind of
     place, so these simply return fewer options rather than wrong ones."""),
    ("Genre tagging is thin.",
     """Cuisine resolves for most restaurants, but genre only for some venues,
     and no venue is tagged `techno` because the source descriptions rarely
     name subgenres. A request for techno currently ranks electronic rooms
     above cabaret bars, which is better than nothing but not what was
     asked."""),
    ("Nothing re-checks whether a venue still exists.",
     """A venue that closed or changed name stays in the corpus. One entry,
     The Brooklyn Monarch, appears to have rebranded; nothing in the system
     would catch that."""),
    ("No real user has tried it yet.",
     """The strongest evidence this project could have is someone other than
     its author using it to plan a night and reporting back. That has not
     happened."""),
]

NEXT = [
    "Collect opening hours and refuse to place a stop at a closed venue.",
    "Add an events feed so a ticketed room can say what is actually on.",
    "Finish geocoding, and re-check venues on a schedule so closures surface.",
    "Richer genre tagging, so a request for techno finds a techno room.",
    "Put it in front of five people and watch where they get stuck.",
    "Let people add their own photographs to a saved night, in place of the "
    "stand-in the page shows now.",
]
