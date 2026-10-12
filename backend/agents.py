"""The agent pipeline: free text in, a typed Night out.

    user text ──> CONCIERGE ──> Brief
                                  │
                      (deterministic retrieval, no model)
                                  ▼
                           candidate rooms
                                  │
                   sanitise: wrap as untrusted data
                                  ▼
                              EDITOR ──> Night ──> renderer

Two model calls, not a swarm. The retrieval step in the middle is ordinary
Python, which matters for cost: filtering 52 rooms is free, and asking a model
to do it would be the single most expensive thing in the app.

CONCIERGE  reads "it's my birthday, eight of us, Bushwick" and fills a Brief.
           Cheap, strictly structured, no tools.
EDITOR     writes the night: picks stops, sequences them, times the travel, and
           writes the one-sentence summary. Has web_search for the places the
           cached dataset does not cover (restaurants, galleries).
"""

from __future__ import annotations

import logging

from datetime import date as Date
from datetime import datetime
from typing import Any

from brief import Brief
from budget import BudgetExceeded, RunBudget, check_before_call, record, status as budget_status
from config import fallback_config, model_config, read_prompt
from critic import Critique, Verdict, plan_as_text
from refine import Amendment
from models import Night, NightDraft, Setting, StopKind, VenueSize
from planner import build_night, catalogue
from openai import AuthenticationError, OpenAI
from pydantic import ValidationError
from models import Source  # noqa: E402
from linkcheck import verify
from sanitize import filter_booking_urls, wrap_untrusted
from sources import dataset_status, find_rooms, lookup_venue, search_events
from tokens import Usage


# Set once the preferred provider has been proven dead, so later calls in the
# same process skip straight to the one that works.
_degraded: dict[str, Any] = {"provider": None, "reason": None}


def _build(cfg) -> OpenAI:
    return (OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
            if cfg.base_url else OpenAI(api_key=cfg.api_key))


def _client() -> tuple[OpenAI, str]:
    cfg = model_config()
    if _degraded["provider"] == cfg.provider:
        if (alt := fallback_config(cfg)):
            return _build(alt), alt.model
    return _build(cfg), cfg.model


def _call(make_request, label: str = "model call", run: RunBudget | None = None):
    """Run a request, falling back once if the preferred key will not auth.

    A course key that is expired or misconfigured is a setup problem, not a
    reason the app should return a 401 page to someone trying to plan a night.
    The swap is recorded so the UI and the audit trail can say it happened,
    rather than silently billing a different account.
    """
    # Gate before spending, not after. A refused call costs nothing; a
    # recorded one that already ran costs whatever it cost.
    check_before_call()
    if run is not None:
        run.check()

    cfg = model_config()
    client, model = _client()
    try:
        response = make_request(client, model)
        if run is not None:
            run.spend()
        record(Usage.from_response(response), label, model)
        return response
    except AuthenticationError as exc:
        alt = fallback_config(cfg)
        if alt is None or _degraded["provider"] == cfg.provider:
            raise
        _degraded.update(provider=cfg.provider, reason=str(exc)[:200])
        response = make_request(_build(alt), alt.model)
        if run is not None:
            run.spend()
        record(Usage.from_response(response), f"{label} (after {cfg.provider} auth failure)", alt.model)
        return response


def degraded_note() -> str | None:
    """Human-readable note when a provider was swapped out mid-session."""
    if not _degraded["provider"]:
        return None
    return (f"{_degraded['provider']} credentials were rejected; "
            f"fell back to the other configured key.")


# --- concierge -------------------------------------------------------------


def _brief_from_form(text: str, prefilled: dict[str, Any]) -> Brief | None:
    """Build a Brief without a model call when the form already has what matters.

    The Concierge exists to read intent out of free text. If the user ticked
    the date, the area and what they are up for, there is nothing left to
    infer, and spending a round trip to re-read their own form is pure latency.
    """
    if not (prefilled.get("date") and (prefilled.get("borough") or prefilled.get("neighborhood"))):
        return None
    if not (prefilled.get("wants") or prefilled.get("venue_sizes") or prefilled.get("settings")):
        return None
    return Brief(vibe=text, **{k: v for k, v in prefilled.items() if v not in (None, "", [], {})})


def run_concierge(text: str, prefilled: dict[str, Any] | None = None,
                  run: RunBudget | None = None) -> tuple[Brief, Usage]:
    """Free text -> Brief, with anything the form already supplied kept as-is.

    Form values win over the model's reading. If the user ticked "outdoor",
    that is a fact, not something to re-infer from their prose.
    """
    prefilled = prefilled or {}
    if (quick := _brief_from_form(text, prefilled)) is not None:
        return quick, Usage()

    today = Date.today().isoformat()

    response = _call(lambda client, model: client.responses.parse(
        model=model,
        store=False,
        instructions=read_prompt("concierge").replace("{{TODAY}}", today),
        input=f"Plan request: {text}",
        text_format=Brief,
    ), label="concierge", run=run)
    brief = response.output_parsed
    usage = Usage.from_response(response)

    for key, value in prefilled.items():
        if value in (None, "", [], {}):
            continue
        setattr(brief, key, value)
    # Their words, always. The model trims "it's my birthday, there are eight
    # of us" down to the actionable half, which is right for the fields and
    # wrong for the one string the page quotes back at them.
    brief.vibe = text

    return brief, usage


# --- retrieval (no model) --------------------------------------------------


def retrieve(brief: Brief, limit: int = 18) -> dict[str, Any]:
    """Pull candidate rooms and events from the cached dataset.

    Deliberately generous: the Editor needs room to choose and to avoid the
    obvious. Narrowing hard here is what makes a recommender repeat itself.
    """
    sizes = brief.venue_sizes or None
    settings = brief.settings or None
    party = brief.party_size if brief.is_group else None

    rooms = find_rooms(sizes=sizes, settings=settings, party_size=party,
                       neighborhood=brief.neighborhood, borough=brief.borough, limit=limit)
    if not rooms:
        # Relax rather than return nothing: a plan with a caveat beats a blank
        # page. The Editor is told which constraint was loosened.
        rooms = find_rooms(sizes=sizes, settings=settings, borough=brief.borough, limit=limit)

    events = search_events(on_date=brief.date, neighborhood=brief.neighborhood,
                           borough=brief.borough, sizes=sizes, settings=settings,
                           party_size=party, limit=limit)

    return {"rooms": rooms, "events": events, "dataset": dataset_status()}


# --- editor ----------------------------------------------------------------


def needs_web(brief: Brief, candidates: dict[str, Any]) -> bool:
    """Decide whether the Editor gets a search tool.

    web_search is by far the slowest thing in a run: it adds round trips and
    pushes input past 28k tokens, and it is the difference between a six second
    plan and a twenty-five second one. So it is used when the cached dataset
    genuinely cannot answer, not as a default.

    Needed when the request wants a kind of place the dataset does not hold
    (restaurants, galleries, dessert), or when retrieval came back thin.
    """
    cached_kinds = {StopKind.SHOW, StopKind.LATE}
    wanted = set(brief.wants)
    if wanted and not wanted.issubset(cached_kinds):
        return True
    if len(candidates.get("rooms", [])) < 4:
        return True
    if not candidates.get("events") and not wanted:
        return True
    return False


def run_editor(brief: Brief, candidates: dict[str, Any], allow_web: bool = True,
               run: RunBudget | None = None) -> tuple[Night, Usage, list[dict]]:
    """Candidates -> a sequenced, written Night.

    The candidate payload is wrapped as untrusted data even though it comes
    from our own files, because the venue notes inside it originated on
    third-party pages during enrichment.
    """
    payload, scan = wrap_untrusted(
        _format_candidates(candidates),
        source_name="cached NYC dataset (enriched from third-party pages)",
    )

    ask = f"""{payload}

THE REQUEST
Their words: "{brief.vibe}"
Constraints: {brief.constraints_summary() or "none given"}
Date: {brief.date or "not specified — assume the next Friday"}
Party size: {brief.party_size or "not specified — assume 2"}
Occasion: {brief.occasion.value if brief.occasion else "none stated"}
Budget per person: {brief.budget.label if brief.budget else "not specified"}
Wants: {", ".join(w.value for w in brief.wants) or "open to anything"}
Avoid: {", ".join(brief.avoid) or "nothing stated"}
"""

    kwargs: dict[str, Any] = {
        "store": False,
        "instructions": read_prompt("editor"),
        "input": ask,
        "text_format": NightDraft,
    }
    if allow_web:
        # Restaurants, galleries and openings are not in the cached dataset.
        # Only the Editor gets a tool, and only this one.
        kwargs["tools"] = [{"type": "web_search"}]

    response = _call(lambda client, model: client.responses.parse(model=model, **kwargs),
                     label="editor", run=run)
    usage = Usage.from_response(response)

    try:
        night, repairs = repair_draft(response.output_parsed)
    except (ValueError, ValidationError) as first_error:
        # One retry, with the failure quoted back. A plan is worth a second
        # call; a 500 page is worth nothing.
        retry_kwargs = dict(kwargs)
        retry_kwargs["input"] = (
            f"{ask}\n\nYour previous answer could not be used: {first_error}\n"
            f"Every stop must cite a source you actually used, and a SHOW must "
            f"state venue_size. Return a shorter night if that is what it takes."
        )
        response = _call(
            lambda client, model: client.responses.parse(model=model, **retry_kwargs),
            label="editor:retry", run=run)
        usage = usage + Usage.from_response(response)
        night, repairs = repair_draft(response.output_parsed)
        repairs.append(f"first attempt rejected: {first_error}")

    # Layer 4: strip any booking link that is not on a known booking domain.
    blocked = filter_booking_urls(night.stops)

    issues = blocked + ([scan.as_dict()] if scan.is_suspicious else [])
    if repairs:
        issues.append({"repairs": repairs})
    return night, usage, issues


def _host(url: str | None) -> str:
    from urllib.parse import urlparse
    try:
        host = urlparse(str(url)).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _same_site(a: str | None, b: str | None) -> bool:
    """Same registrable domain. Used to decide whether a booking link is one
    we can account for, rather than one the model remembered."""
    ha, hb = _host(a), _host(b)
    return bool(ha) and ha == hb


def repair_draft(draft: NightDraft) -> tuple[Night, list[str]]:
    """Fix what we can from our own data, drop what we cannot, then validate.

    Returns the strict Night and a list of repairs made, which goes into the
    audit trail. The point is that one missing field costs a stop at worst,
    never the whole plan.
    """
    notes: list[str] = []
    kept = []

    for stop in draft.stops:
        venue = lookup_venue(stop.name)

        # Coordinates: ours are geocoded and checked, the model's are guesses.
        if stop.lat is None and venue and venue.lat is not None:
            stop.lat, stop.lon = venue.lat, venue.lon

        # Room size for a show: look it up rather than lose the stop.
        if stop.kind is StopKind.SHOW and stop.venue_size is None:
            if venue and venue.size is not None:
                stop.venue_size = venue.size
                stop.capacity = stop.capacity or venue.main_space.capacity
                notes.append(f"filled venue_size for {stop.name} from the dataset")
            else:
                # Unknown room: report it as a late stop rather than claim a
                # size we do not have. The size filter is the product's whole
                # promise, so an invented one would be worse than reclassifying.
                stop.kind = StopKind.LATE
                notes.append(f"{stop.name}: no known room size, listed as late rather than a show")

        # A booking link the model produced from memory is not a link, it is
        # a guess. It resolves, which is why nothing downstream complained,
        # but nothing confirms it opens the right venue -- and the user does
        # not find out until they arrive somewhere else.
        #
        # So a link survives only if we can account for where it came from:
        #   1. our own dataset's verified site for that venue, or
        #   2. a page the model actually cited as a source for this stop.
        # Anything else is dropped and the card shows no button.
        if stop.booking_url:
            trusted = None
            if venue is not None and getattr(venue, "source_url", None):
                trusted = venue.source_url
            cited = {str(src.url) for src in stop.sources if src.url}
            if trusted and _same_site(stop.booking_url, trusted):
                stop.booking_url = trusted
            elif any(_same_site(stop.booking_url, c) for c in cited):
                # Cited, but a citation is not proof the page opens this venue.
                if not verify(stop.booking_url, stop.name, allow_fetch=False):
                    notes.append(f"{stop.name}: booking link not yet verified, hidden")
                    stop.booking_url = stop.booking_label = None
            else:
                notes.append(
                    f"{stop.name}: dropped a booking link the model supplied "
                    f"but did not cite ({_host(stop.booking_url)})")
                stop.booking_url = None
                stop.booking_label = None

        # Sourcing is a security property, not a formatting one. A stop we
        # cannot attribute is dropped.
        if not stop.sources:
            if venue is not None:
                stop.sources = [Source(name="Cached NYC venue dataset",
                                       url=venue.source_url or None)]
                notes.append(f"attributed {stop.name} to the cached dataset")
            else:
                notes.append(f"dropped {stop.name}: no source, and not in the dataset")
                continue

        kept.append(stop)

    if not kept:
        raise ValueError("every stop was unsourced")

    night = Night(
        summary=draft.summary, headline=draft.headline, dek=draft.dek,
        date=draft.date, neighborhood=draft.neighborhood, vibe=draft.vibe,
        stops=kept, est_total_cost_usd=draft.est_total_cost_usd, notes=draft.notes,
    )
    return night, notes


def _format_candidates(candidates: dict[str, Any]) -> str:
    """Compact text for the model. Compact on purpose -- this block is the
    bulk of the input tokens on every run, so it is the first place to look
    when cutting cost."""
    lines: list[str] = ["ROOMS IN THE CACHED DATASET (capacity researched and cited):"]
    for r in candidates["rooms"]:
        cap = f"{r['capacity']:,}" if r.get("capacity") else "capacity unknown"
        lines.append(
            f"- {r['venue']} — {r['room']} | {cap} | {r['setting']} | "
            f"{r.get('venue_size') or '?'} | {r['neighborhood']}, {r['borough']}"
        )
    if candidates["events"]:
        lines.append("\nEVENTS ON THAT DATE:")
        for ev in candidates["events"]:
            lines.append(f"- {ev.get('name')} at {ev.get('venue')} ({ev.get('room') or 'main'}) "
                         f"{ev.get('start_time','')} {ev.get('genre','')}")
    else:
        lines.append("\nEVENTS ON THAT DATE: none in the cached dataset. "
                     "Use web_search for anything on, and for restaurants, "
                     "galleries and late-night spots, which this dataset does not cover.")
    return "\n".join(lines)


# --- the whole run ---------------------------------------------------------


def run_critic(night, brief, run: RunBudget | None = None) -> tuple[Critique, Usage]:
    """Read a finished plan and judge it as a person would.

    Cheap: the plan is a few hundred tokens and the verdict is shorter. Worth
    it because the deterministic planner is structurally unable to notice that
    its own output does not work as an evening.
    """
    response = _call(lambda client, model: client.responses.parse(
        model=model, store=False,
        instructions=read_prompt("critic"),
        input=plan_as_text(night, brief),
        text_format=Critique,
    ), label="critic", run=run)
    return response.output_parsed, Usage.from_response(response)


def run_refiner(night, brief, message: str,
                run: RunBudget | None = None) -> tuple[Amendment, Usage]:
    """Turn 'cheaper' or 'swap the second one' into a structured edit.

    The model reads the message against the plan the person is actually
    looking at. It never picks venues; it decides what they meant, and the
    deterministic planner applies it.
    """
    ask = (f"{plan_as_text(night, brief)}\n\n"
           f"THEIR MESSAGE: \"{message.strip()}\"")
    response = _call(lambda client, model: client.responses.parse(
        model=model, store=False,
        instructions=read_prompt("refine"),
        input=ask,
        text_format=Amendment,
    ), label="refine", run=run)
    return response.output_parsed, Usage.from_response(response)


def apply_amendment(brief: Brief, amendment: Amendment) -> Brief:
    """A new Brief with the amendment folded in. The original is untouched."""
    from brief import Budget
    from models import Setting, StopKind, VenueSize

    data = brief.model_dump()
    c = amendment.brief_changes

    def enum_list(values, cls):
        out = []
        for v in values:
            try:
                out.append(cls(v))
            except ValueError:
                continue
        return out

    if c.budget:
        try:
            data["budget"] = Budget(c.budget)
        except ValueError:
            pass
    for field in ("start_time", "party_size", "neighborhood", "borough"):
        if (v := getattr(c, field)) is not None:
            data[field] = v
    if c.roam is not None:
        data["roam"] = c.roam
    if sizes := enum_list(c.venue_sizes, VenueSize):
        data["venue_sizes"] = sizes
    if settings := enum_list(c.settings, Setting):
        data["settings"] = settings
    if c.style:
        data["style"] = list(dict.fromkeys(list(brief.style) + c.style))

    wants = list(brief.wants)
    for w in enum_list(c.remove_wants, StopKind):
        wants = [x for x in wants if x is not w]
    for w in enum_list(c.add_wants, StopKind):
        if w not in wants:
            wants.append(w)
    data["wants"] = wants

    return Brief(**data)


def refine_night(night, brief, message: str, seed: int | None = None) -> dict[str, Any]:
    """One turn of conversation about a plan already on screen."""
    started = datetime.now()
    run = RunBudget()

    amendment, usage = run_refiner(night, brief, message, run=run)
    if amendment.is_noop:
        return {"night": night, "brief": brief, "amendment": amendment,
                "changed": False, "usage": usage,
                "seconds": round((datetime.now() - started).total_seconds(), 2)}

    new_brief = apply_amendment(brief, amendment)
    keep = {s.name for s in night.stops} & set(amendment.keep)
    pin = {s.kind.value: s.name for s in night.stops if s.name in keep}

    rebuilt = build_night(new_brief, seed=seed, exclude=set(amendment.drop), pin=pin)
    if rebuilt is None:
        # The edit asked for something the corpus cannot cover. Keep what they
        # already have rather than replacing it with nothing.
        return {"night": night, "brief": brief, "amendment": amendment,
                "changed": False, "usage": usage, "no_coverage": True,
                "seconds": round((datetime.now() - started).total_seconds(), 2)}

    filter_booking_urls(rebuilt.stops)
    return {"night": rebuilt, "brief": new_brief, "amendment": amendment,
            "changed": True, "usage": usage,
            "seconds": round((datetime.now() - started).total_seconds(), 2)}


def plan_night(text: str, prefilled: dict[str, Any] | None = None,
               allow_web: bool = True, seed: int | None = None,
               exclude: set[str] | None = None,
               pin: dict[str, str] | None = None) -> dict[str, Any]:
    """One full request.

    Two paths. The fast one assembles a night from the cached dataset with no
    model call at all, in under a millisecond. The slow one asks the model, and
    is used only when the dataset cannot cover what was asked for.

    Choosing venues is filtering, sequencing is arithmetic, and the prose about
    a venue is the same every time, so it is written once offline. What is left
    for a model at request time is nothing, most of the time.
    """
    started = datetime.now()
    run = RunBudget()
    timings: dict[str, float] = {}

    t0 = datetime.now()
    brief, u1 = run_concierge(text, prefilled, run=run)
    timings["concierge"] = round((datetime.now() - t0).total_seconds(), 2)

    # --- fast path: no model, no network -----------------------------------
    t0 = datetime.now()
    instant = build_night(brief, seed=seed, exclude=exclude, pin=pin)
    timings["assemble"] = round((datetime.now() - t0).total_seconds(), 3)

    # Good enough when it covered what was actually asked for. One stop out of
    # three requested means the dataset is thin here, so fall through.
    wanted_count = len(brief.wants) or 2
    if instant is not None and len(instant.stops) >= min(wanted_count, 2):

        # The Critic reads the assembled plan and judges it the way a person
        # would. On a reshuffle the planner rebuilds without the stop it
        # named; we do this at most once, because a critic you argue with
        # forever is a loop, not a review.
        t0 = datetime.now()
        critique = None
        u_crit = Usage()
        try:
            critique, u_crit = run_critic(instant, brief, run=run)
            if critique.verdict is Verdict.RESHUFFLE and critique.worst_stop:
                second = build_night(brief, seed=(seed or 0) + 101,
                                     exclude=(exclude or set()) | {critique.worst_stop},
                                     pin=pin)
                if second is not None and len(second.stops) >= min(wanted_count, 2):
                    instant = second
        except (BudgetExceeded, TooManyCalls):
            pass          # a plan without a review beats no plan
        except Exception:                                      # noqa: BLE001
            logging.exception("critic failed; shipping the plan unreviewed")
        timings["critic"] = round((datetime.now() - t0).total_seconds(), 2)

        total = u1 + u_crit
        blocked = filter_booking_urls(instant.stops)
        return {
            "brief": brief, "night": instant, "usage": total,
            "critique": critique,
            "usage_breakdown": {"concierge": u1.as_dict(), "critic": u_crit.as_dict()},
            "blocked": blocked, "dataset": dataset_status(),
            "candidates_considered": len(catalogue()),
            "seconds": round((datetime.now() - started).total_seconds(), 2),
            "timings": timings, "used_web_search": False, "path": "instant",
            "budget": budget_status(), "degraded": degraded_note(),
        }

    t0 = datetime.now()
    candidates = retrieve(brief)
    timings["retrieval"] = round((datetime.now() - t0).total_seconds(), 2)

    use_web = allow_web and needs_web(brief, candidates)
    t0 = datetime.now()
    night, u2, blocked = run_editor(brief, candidates, allow_web=use_web, run=run)
    timings["editor"] = round((datetime.now() - t0).total_seconds(), 2)

    total = u1 + u2
    return {
        "brief": brief,
        "night": night,
        "usage": total,
        "usage_breakdown": {"concierge": u1.as_dict(), "editor": u2.as_dict()},
        "blocked": blocked,
        "dataset": candidates["dataset"],
        "candidates_considered": len(candidates["rooms"]) + len(candidates["events"]),
        "seconds": round((datetime.now() - started).total_seconds(), 1),
        "timings": timings,
        "used_web_search": use_web,
        "path": "model",
        "budget": budget_status(),
        "degraded": degraded_note(),
    }
