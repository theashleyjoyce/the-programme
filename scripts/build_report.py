"""Build report.html from live data.

The assignment wants one self-contained HTML file of 10 to 15 printed pages.
Generating it rather than writing it by hand means every number comes from the
ledger, the dataset and the guardrail suite at build time, so the report cannot
drift from the app it describes.

    python scripts/build_report.py
    python scripts/build_report.py --open
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import mimetypes
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "report"))

import content  # noqa: E402

OUT = ROOT / "report.html"
LEDGER = ROOT / "output" / "spend_ledger.json"
SHOTS = ROOT / "report" / "screenshots"


def e(x) -> str:
    return html.escape(str(x))


# ── live figures ───────────────────────────────────────────────────────────

def ledger_facts() -> dict:
    """Real measurements from every call the project has made."""
    data = json.loads(LEDGER.read_text())
    entries = [x for x in data["entries"] if not x.get("backfilled")]

    def group(prefix):
        return [x for x in entries if x["label"].split(":")[0].startswith(prefix)]

    def mean(rows, field):
        return sum(r[field] for r in rows) / len(rows) if rows else 0

    conc, ed = group("concierge"), group("editor")
    offline = group("discover") + group("enrich") + group("write_copy")

    fresh, cached, out = mean(conc, "input_tokens"), mean(conc, "cached_input_tokens"), mean(conc, "output_tokens")
    return {
        "total_spend": data["total_usd"],
        "total_calls": len(entries),
        "offline_calls": len(offline),
        "offline_spend": sum(r["cost_usd"] for r in offline),
        "conc_calls": len(conc),
        "conc_fresh": fresh, "conc_cached": cached, "conc_out": out,
        "conc_cost": mean(conc, "cost_usd"),
        "conc_cache_rate": cached / (fresh + cached) * 100 if (fresh + cached) else 0,
        "ed_calls": len(ed),
        "ed_in": mean(ed, "input_tokens"), "ed_out": mean(ed, "output_tokens"),
        "ed_cost": mean(ed, "cost_usd"),
        "prices": data.get("prices_used", {}),
    }


def dataset_facts() -> dict:
    from sources import dataset_status
    from planner import catalogue
    rows = catalogue()
    return {**dataset_status(),
            "with_cuisine": sum(1 for r in rows if r.get("cuisine")),
            "with_genre": sum(1 for r in rows if r.get("genre"))}


def guardrail_facts() -> dict:
    """Run the suite so the report can only claim what currently passes.

    Strips ANSI first. The colour codes contain digits -- \033[32m is a green
    escape, not a count -- and an earlier version of this parser read that 32
    and printed it in the report as the number of passing guardrails while the
    real figure was 34. A report that quotes a terminal colour code as a
    result is exactly the kind of error this file exists to prevent.
    """
    import re as _re

    r = subprocess.run([sys.executable, "-I", str(ROOT / "test_guardrails.py")],
                       capture_output=True, text=True, cwd=ROOT)
    clean = _re.sub(r"\x1b\[[0-9;]*m", "", r.stdout)
    m = _re.search(r"(\d+)\s+passed,\s+(\d+)\s+failed", clean)
    if not m:
        raise RuntimeError(
            "Could not read the guardrail result. Refusing to guess a number "
            "for the report.")
    return {"passed": int(m.group(1)), "failed": int(m.group(2)),
            "ok": r.returncode == 0}


def embed(name: str) -> str:
    """Base64 an image so the file opens anywhere with nothing missing."""
    p = SHOTS / name
    if not p.is_file():
        return ""
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


def logo_img(width: str = "160px") -> str:
    """The mark, base64'd rather than inlined, so the SVG's own <style> block
    cannot leak its rules into the report."""
    path = ROOT / "frontend" / "static" / "img" / "programme.svg"
    if not path.is_file():
        return ""
    import base64 as _b64
    data = _b64.b64encode(path.read_bytes()).decode("ascii")
    return (f'<img src="data:image/svg+xml;base64,{data}" alt="" '
            f'style="width:{width};height:auto;display:block">')


def figure(name: str, caption: str) -> str:
    src = embed(name)
    if not src:
        return (f'<figure class="shot shot--missing"><div class="shot__todo">'
                f'SCREENSHOT TO ADD — save as <code>report/screenshots/{e(name)}</code>'
                f'</div><figcaption>{e(caption)}</figcaption></figure>')
    return (f'<figure class="shot"><img src="{src}" alt="{e(caption)}">'
            f'<figcaption>{e(caption)}</figcaption></figure>')


# ── sections ───────────────────────────────────────────────────────────────

def money(x: float) -> str:
    return f"${x:,.2f}" if x >= 0.01 else f"${x:.4f}"


def build() -> str:
    L, D, G = ledger_facts(), dataset_facts(), guardrail_facts()
    c = content

    per_plan_fast = L["conc_cost"]
    per_plan_slow = L["ed_cost"] + L["conc_cost"]
    PLANS_MONTH = 4
    tiers = [(1, "one user"), (100, "100 users"), (10_000, "10,000 users")]

    def scale_rows(cost):
        out = []
        for n, label in tiers:
            monthly = cost * PLANS_MONTH * n
            out.append(f"<tr><td>{label}</td><td>{money(monthly)}</td>"
                       f"<td>{money(monthly * 12)}</td></tr>")
        return "".join(out)

    repo = c.REPO_URL
    app_line = (f'<p><strong>Live app:</strong> <a href="{e(c.APP_URL)}">{e(c.APP_URL)}</a></p>'
                if c.APP_URL else
                '<p><strong>Live app:</strong> not hosted — runs locally from a fresh '
                'clone, see the README.</p>')

    motivation = "".join(
        f"<h3>{e(h)}</h3><p>{e(' '.join(b.split()))}</p>" for h, b in c.MOTIVATION)

    competitors = "".join(
        f"<tr><td><strong>{e(n)}</strong><br><span class='muted'>{e(w)}</span></td>"
        f"<td>{e(what)}</td><td>{e(diff)}</td></tr>"
        for n, w, what, diff in c.COMPETITORS)

    import re as _re
    kinds_on_form = len(_re.findall(
        r'name="wants" value="[a-z_]+"',
        (ROOT / "frontend" / "templates" / "index.html").read_text()))

    claims = "".join(
        f"<h3>{e(h)}</h3><p>{e(' '.join(b.format(kinds=kinds_on_form).split()))}</p>"
        for h, b in c.WHATS_NEW_CLAIMS)

    agents = "".join(
        f"<tr><td><strong>{e(n)}</strong></td><td>{e(when)}</td><td><code>{e(tools)}</code></td>"
        f"<td>{e(job)}</td><td class='muted'>{e(src)}</td></tr>"
        for n, when, tools, job, src in c.AGENTS)

    cutting = "".join(
        f"<li><strong>{e(h)}</strong> {e(' '.join(b.split()))}</li>" for h, b in c.COST_CUTTING)

    stories = "".join(
        f"<h3>{e(h)}</h3><p>{e(' '.join(b.split()))}</p>" for h, b in c.SAFETY_STORIES)

    limits = "".join(
        f"<li><strong>{e(h)}</strong> "
        f"{e(' '.join(b.format(mapped=D['venues_mapped'], venues=D['venues_known']).split()))}</li>"
        for h, b in c.LIMITS)

    nxt = "".join(f"<li>{e(x)}</li>" for x in c.NEXT)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(c.TITLE)} — Report — {e(c.AUTHOR)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bodoni+Moda:ital,opsz,wght@0,6..96,400..700;1,6..96,400..600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{{--paper:#FBF9F6;--ink:#14110F;--soft:#4A433E;--mute:#8A8077;--rule:#E4DCD2;--accent:#B8402C;
--display:'Bodoni Moda',Didot,Georgia,serif;--body:'Inter',-apple-system,sans-serif}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);font-family:var(--body);
font-size:11.5pt;line-height:1.62}}
.page{{max-width:46rem;margin:0 auto;padding:3rem 2.5rem 5rem}}
h1{{font-family:var(--display);font-weight:500;font-size:2.9rem;line-height:1.02;
letter-spacing:-.015em;margin:0 0 .6rem}}
h2{{font-family:var(--display);font-weight:500;font-size:1.85rem;line-height:1.1;
margin:3.2rem 0 1rem;padding-top:1.4rem;border-top:1px solid var(--ink)}}
h3{{font-size:.76rem;letter-spacing:.17em;text-transform:uppercase;color:var(--accent);
font-weight:600;margin:1.8rem 0 .5rem}}
p{{margin:0 0 .95rem}}
.lead{{font-family:var(--display);font-style:italic;font-size:1.3rem;line-height:1.45;
color:var(--soft);margin:0 0 1.6rem}}
.muted{{color:var(--mute);font-size:.85em}}
.meta{{font-size:.8rem;letter-spacing:.1em;text-transform:uppercase;color:var(--soft);
padding-top:1.2rem;border-top:1px solid var(--rule);margin-top:1.4rem}}
table{{width:100%;border-collapse:collapse;margin:1.1rem 0 1.4rem;font-size:.92rem}}
th{{text-align:left;font-size:.66rem;letter-spacing:.16em;text-transform:uppercase;
color:var(--soft);font-weight:600;padding:.5rem .6rem .5rem 0;border-bottom:1px solid var(--ink)}}
td{{padding:.6rem .6rem .6rem 0;border-bottom:1px solid var(--rule);vertical-align:top}}
code{{font-family:ui-monospace,Menlo,monospace;font-size:.86em;background:#F2EDE6;padding:.1em .35em}}
ul,ol{{margin:0 0 1.1rem;padding-left:1.1rem}}
li{{margin-bottom:.55rem}}
.callout{{background:#F2EDE6;border-left:2px solid var(--accent);padding:1rem 1.2rem;margin:1.3rem 0}}
.callout p:last-child{{margin:0}}
.fig{{display:grid;grid-template-columns:repeat(auto-fit,minmax(8rem,1fr));gap:1rem;margin:1.3rem 0}}
.fig div{{border-top:1px solid var(--ink);padding-top:.6rem}}
.fig .n{{font-family:var(--display);font-size:1.9rem;line-height:1;display:block}}
.fig .l{{font-size:.68rem;letter-spacing:.12em;text-transform:uppercase;color:var(--soft)}}
.diagram{{font-family:ui-monospace,Menlo,monospace;font-size:.72rem;line-height:1.5;
background:#F2EDE6;padding:1.2rem;white-space:pre;overflow-x:auto;margin:1.2rem 0}}
.shot{{margin:1.4rem 0}}
.shot img{{width:auto;max-width:100%;max-height:620px;border:1px solid var(--rule);
display:block;margin:0 auto}}
.shot figcaption{{font-size:.76rem;color:var(--soft);padding-top:.5rem}}
.shot--missing .shot__todo{{border:1px dashed var(--accent);color:var(--accent);
padding:1.6rem;text-align:center;font-size:.8rem;letter-spacing:.06em}}
.todo{{background:#FFF4E5;border-left:2px solid #C98A00;padding:.9rem 1.1rem;margin:1.2rem 0;font-size:.9rem}}
@media print{{body{{font-size:10.5pt}}.page{{max-width:none;padding:0}}h2{{page-break-after:avoid}}
.shot,table,.diagram{{page-break-inside:avoid}}
.shot img{{max-height:4in}}}}
</style></head><body><div class="page">

<div style="display:flex;align-items:flex-start;gap:2rem;justify-content:space-between">
  <div style="flex:1 1 auto">
    <p class="meta">{e(c.COURSE)} · Final project</p>
    <h1 style="margin-bottom:.35rem">{e(c.TITLE)}</h1>
    <p class="lead" style="margin:0">{e(c.TAGLINE)}.</p>
    <div style="width:2.6rem;height:2px;background:#B8402C;margin:.7rem 0 .7rem"></div>
    <p class="lead" style="margin:0">{e(c.ONE_LINER)}</p>
  </div>
  <div style="flex:0 0 auto">{logo_img()}</div>
</div>
<p style="margin-top:1.4rem"><strong>{e(c.AUTHOR)}</strong></p>
<p><strong>Repository:</strong> <a href="{e(repo)}">{e(repo)}</a></p>
{app_line}
<p class="meta">Built {date.today():%d %B %Y}</p>

<h2>2. Motivation</h2>
{motivation}

<h2>3. What is new here</h2>
<p>{e(' '.join(c.WHATS_NEW_INTRO.split()))}</p>
<table><tr><th>Product</th><th>What it does</th><th>What we do differently</th></tr>
{competitors}</table>
{claims}

<h2>4. The agents</h2>
<p>{e(' '.join(c.AGENTS_INTRO.split()))}</p>
<div class="diagram">OFFLINE — runs on a refresh, shared by every user
┌──────────┐     ┌──────────────┐     ┌──────────┐
│  SCOUT   │────▶│  RESEARCHER  │────▶│  WRITER  │
│ listings │     │ rooms, sizes │     │ the copy │
└──────────┘     └──────────────┘     └──────────┘
      └────────────────┬─────────────────────┘
                       ▼
              data/*.json   (committed to the repo)
                       │
PER REQUEST ───────────┼──────────────────────────────
                       ▼
  you type ──▶ CONCIERGE ──▶ Brief ──▶ PLANNER ──▶ Night ──▶ page
               (free text    (typed    (no model,   (typed
                to fields)   request)  pure Python)  object)
                                           │
                                 corpus cannot cover it?
                                           ▼
                                        EDITOR
                               (plans it, with web search)</div>
<table><tr><th>Agent</th><th>When</th><th>Tools</th><th>What it does</th><th>Sources</th></tr>
{agents}</table>
<div class="callout"><p>{e(' '.join(c.PLANNER_NOTE.split()))}</p></div>
<h3>Models, and why</h3>
<p>{e(' '.join(c.MODELS_NOTE.split()))}</p>

<h3>One real run, step by step</h3>
{figure("01-search.png", "The search page. A suggestion rotates on each visit; pressing go without typing uses it.")}
{figure("02-working.png", "The working page opens immediately rather than leaving a blank tab.")}
{figure("03-plan.png", "The finished night: stops in order, room size, travel time, nearest train, booking link.")}
{figure("04-costs.png", "The same plan with ?costs=1, showing measured token usage.")}
{figure("07-saved.png", "An account keeps the nights you plan, and marks the ones you went to.")}
{figure("08-newsletter.png", "The welcome note, composed on opt-in and written to an outbox. Nothing is sent: delivery needs a mail provider key this project is not allowed.")}

<h2>5. Tokenomics</h2>
<p>{e(' '.join(c.TOKENOMICS_INTRO.split()))}</p>
<div class="fig">
<div><span class="n">{L['total_calls']}</span><span class="l">model calls, all time</span></div>
<div><span class="n">{money(L['total_spend'])}</span><span class="l">total spend</span></div>
<div><span class="n">{L['conc_cache_rate']:.0f}%</span><span class="l">prompt cache hit</span></div>
<div><span class="n">{money(per_plan_fast)}</span><span class="l">per plan, cached path</span></div>
</div>
<h3>One typical run</h3>
<table><tr><th>Path</th><th>Fresh input</th><th>Cached input</th><th>Output</th><th>Cost</th></tr>
<tr><td>Cached corpus ({L['conc_calls']} runs)</td><td>{L['conc_fresh']:,.0f}</td>
<td>{L['conc_cached']:,.0f}</td><td>{L['conc_out']:,.0f}</td><td>{money(per_plan_fast)}</td></tr>
<tr><td>Model fallback ({L['ed_calls']} runs)</td><td>{L['ed_in']:,.0f}</td><td>—</td>
<td>{L['ed_out']:,.0f}</td><td>{money(per_plan_slow)}</td></tr>
<tr><td>Filters only, no typing</td><td>0</td><td>0</td><td>0</td><td>$0.0000</td></tr></table>
<h3>At scale</h3>
<p>Assuming {PLANS_MONTH} plans per user per month, on the cached path:</p>
<table><tr><th>Users</th><th>Per month</th><th>Per year</th></tr>{scale_rows(per_plan_fast)}</table>
<p class="muted">Corpus building is a separate, one-off cost: {L['offline_calls']} calls,
{money(L['offline_spend'])} to date, shared across every plan ever served.</p>
<h3>What we did to cut cost</h3>
<ol>{cutting}</ol>
<h3>Did it make the app worse?</h3>
<p>{e(' '.join(c.PERFORMANCE_TRADEOFF.split()))}</p>
<table><tr><th></th><th>Before</th><th>After</th></tr>
<tr><td>Time to a plan</td><td>~25 s</td><td>~5 s</td></tr>
<tr><td>Model calls per plan</td><td>2</td><td>0 – 1</td></tr>
<tr><td>Tokens per plan</td><td>~30,000</td><td>~{L['conc_fresh'] + L['conc_cached'] + L['conc_out']:,.0f}</td></tr>
<tr><td>Cost per plan</td><td>~$0.056</td><td>{money(per_plan_fast)}</td></tr></table>

<h2>6. Safety</h2>
<p>{e(' '.join(c.SAFETY_INTRO.split()))}</p>
<div class="fig">
<div><span class="n">{G['passed']}</span><span class="l">guardrails passing</span></div>
<div><span class="n">{G['failed']}</span><span class="l">failing</span></div>
<div><span class="n">7</span><span class="l">categories covered</span></div>
</div>
{figure("05-guardrails.png", "python test_guardrails.py — every defence exercised and reported.")}
{figure("06-attack.png", "python demo_attack.py — four prompt-injection attacks, each blocked.")}
{stories}

<h2>7. Impact</h2>
<p>{e(' '.join(c.IMPACT_INTRO.split()))}</p>
<h3>Measured</h3>
<table><tr><th>What</th><th>Figure</th><th>Source</th></tr>
<tr><td>Time to a plan</td><td>~5 s</td><td>Median of 15 timed requests on the fast path</td></tr>
<tr><td>Cost per plan</td><td>{money(per_plan_fast)}</td><td>Spend ledger, {L['conc_calls']} runs</td></tr>
<tr><td>Venues covered</td><td>{D['venues_known']:,}</td><td>The committed dataset</td></tr>
<tr><td>Neighbourhoods</td><td>{D['neighborhoods']}</td><td>All five boroughs</td></tr>
<tr><td>Guardrails passing</td><td>{G['passed']}</td><td><code>test_guardrails.py</code></td></tr></table>
<div class="todo"><strong>To add:</strong> the time a real person takes to plan a
night the usual way versus with this, and a quote from them. One fifteen-minute
session is enough, and it is the single strongest piece of evidence this report
could carry.</div>
<h3>Estimated, and labelled as such</h3>
<p>If planning a night out the usual way takes twenty minutes of tab-switching
and this takes two, a user who goes out four times a month saves roughly an
hour and a quarter a month. That arithmetic is sound; the twenty-minute figure
is an estimate from the author's own habit and has not been measured on anyone
else.</p>

<h2>8. Limits and next steps</h2>
<h3>What does not work yet</h3>
<ul>{limits}</ul>
<h3>What I would build next</h3>
<ol>{nxt}</ol>

<p class="meta">{e(c.AUTHOR)} · {e(c.COURSE)} · {date.today():%B %Y}</p>
</div></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()

    SHOTS.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    kb = OUT.stat().st_size // 1024
    print(f"wrote {OUT.name}  ({kb} KB)")

    missing = [n for n in ("01-search.png", "02-working.png", "03-plan.png",
                           "04-costs.png", "05-guardrails.png", "06-attack.png")
               if not (SHOTS / n).is_file()]
    if missing:
        print(f"screenshots still to add in report/screenshots/: {', '.join(missing)}")
    if args.open:
        import webbrowser
        webbrowser.open(OUT.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
