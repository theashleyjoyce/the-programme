"""Build slides.html — reveal.js from a CDN, ten slides, self-contained.

Same approach as the report: figures come from the live ledger, dataset and
guardrail suite at build time, and screenshots are base64'd in so the file
works when emailed.

Slide order follows the outline in the assignment:
  title · problem · what is new · agent diagram · demo · cost · safety ·
  impact · next

    python scripts/build_slides.py
"""

from __future__ import annotations

import base64
import html
import mimetypes
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "report"))
sys.path.insert(0, str(ROOT / "scripts"))

import content                                   # noqa: E402
from build_report import (dataset_facts, guardrail_facts,  # noqa: E402
                          ledger_facts, money)

OUT = ROOT / "slides.html"
SHOTS = ROOT / "report" / "screenshots"


def e(x) -> str:
    return html.escape(str(x))


def img(name: str) -> str:
    p = SHOTS / name
    if not p.is_file():
        return ""
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


def logo_img(height: str = "56vh") -> str:
    """The mark, base64'd rather than inlined.

    The SVG carries its own <style> block, and an inlined <svg> leaks those
    rules into the deck, where a class as generic as .fill will find something
    it was never meant to touch. As an image it is sealed, and the deck stays
    a single file.
    """
    path = ROOT / "frontend" / "static" / "img" / "programme.svg"
    if not path.is_file():
        return ""
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return (f'<img src="data:image/svg+xml;base64,{data}" alt="" '
            f'style="height:{height};width:auto;display:block">')


def shot(name: str, alt: str = "") -> str:
    src = img(name)
    return (f'<img class="shot" src="{src}" alt="{e(alt)}">' if src
            else f'<div class="missing">screenshot: {e(name)}</div>')


def build() -> str:
    L, D, G = ledger_facts(), dataset_facts(), guardrail_facts()
    per_plan = L["conc_cost"]
    c = content

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{e(c.TITLE)} — {e(c.AUTHOR)}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/reveal.css">
<link href="https://fonts.googleapis.com/css2?family=Bodoni+Moda:ital,opsz,wght@0,6..96,400..700;1,6..96,400..600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{{--paper:#FBF9F6;--ink:#14110F;--soft:#4A433E;--mute:#8A8077;--rule:#E4DCD2;--accent:#B8402C}}
.reveal{{font-family:'Inter',sans-serif;color:var(--ink);font-size:30px}}
.reveal-viewport{{background:var(--paper)}}
.reveal .slides{{text-align:left}}
.reveal h1,.reveal h2{{font-family:'Bodoni Moda',Didot,serif;font-weight:500;
text-transform:none;letter-spacing:-.015em;line-height:1.02;margin:0 0 .4em;color:var(--ink)}}
.reveal h1{{font-size:2.5em}} .reveal h2{{font-size:1.5em}}
.reveal .kicker{{font-size:.44em;letter-spacing:.26em;text-transform:uppercase;
color:var(--accent);font-weight:600;margin-bottom:1.2em}}
.reveal .lead{{font-family:'Bodoni Moda',serif;font-style:italic;font-size:.82em;
color:var(--soft);line-height:1.4}}
.reveal p{{line-height:1.5}}
.reveal ul{{margin-left:0}} .reveal li{{margin-bottom:.45em;line-height:1.4}}
.reveal strong{{font-weight:600}}
.reveal .big{{font-family:'Bodoni Moda',serif;font-size:2.1em;line-height:1;display:block}}
.reveal .lbl{{font-size:.4em;letter-spacing:.14em;text-transform:uppercase;color:var(--soft)}}
.reveal .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(3.4em,1fr));
gap:.9em;margin-top:.7em}}
.reveal .grid>div{{border-top:1px solid var(--ink);padding-top:.35em}}
.reveal .two{{display:grid;grid-template-columns:1fr 1fr;gap:1.1em;align-items:start}}
.reveal table{{font-size:.52em;border-collapse:collapse;width:100%}}
.reveal th{{text-align:left;font-size:.78em;letter-spacing:.12em;text-transform:uppercase;
color:var(--soft);border-bottom:1px solid var(--ink);padding:.4em .5em .4em 0}}
.reveal td{{padding:.45em .5em .45em 0;border-bottom:1px solid var(--rule);vertical-align:top}}
.reveal .shot{{width:100%;border:1px solid var(--rule);box-shadow:0 10px 30px rgba(0,0,0,.09)}}
.reveal .missing{{border:1px dashed var(--accent);color:var(--accent);padding:1.4em;
text-align:center;font-size:.5em}}
.reveal pre.diagram{{font-family:ui-monospace,Menlo,monospace;font-size:.34em;line-height:1.45;
background:#F2EDE6;padding:1em;box-shadow:none;width:100%}}
.reveal .accent{{color:var(--accent)}}
.reveal .foot{{position:absolute;bottom:-1.4em;left:0;font-size:.4em;color:var(--mute);
letter-spacing:.12em;text-transform:uppercase}}
.reveal .progress{{color:var(--accent)}}
</style></head><body><div class="reveal"><div class="slides">

<section>
  <div style="display:flex;align-items:center;gap:2.6em;text-align:left">
    <div style="flex:1 1 60%">
      <p class="kicker">{e(c.COURSE)}</p>
      <h1 style="margin-bottom:.3em">{e(c.TITLE)}</h1>
      <p class="lead" style="margin:0">{e(c.TAGLINE)}.</p>
      <div style="width:3.2em;height:2px;background:var(--accent);
                  margin:.85em 0 .8em"></div>
      <p class="lead" style="margin:0">{e(c.ONE_LINER)}</p>
      <p style="margin-top:1.5em"><strong>{e(c.AUTHOR)}</strong></p>
      <p class="foot">{date.today():%B %Y}</p>
    </div>
    <div style="flex:0 0 auto">{logo_img()}</div>
  </div>
</section>

<section>
  <p class="kicker">The problem</p>
  <h2>Going out here is a research project</h2>
  <div class="two">
    <div>
      <p>Eater for the restaurant. The Infatuation to check it. Resident Advisor
      for who is playing. A ticket page. Then a map, to find out whether any of
      it is near any of the rest.</p>
      <p><strong>Nine tabs, four opinions that disagree, and a decision still to
      make.</strong></p>
    </div>
    <div>
      <p class="lead">So the easy answer wins: the same bar as last time, chosen
      at eleven o'clock because it was the only one still in your head.</p>
      <p style="font-size:.62em;color:var(--soft)">That is not a preference.
      That is what decision fatigue looks like from the inside.</p>
    </div>
  </div>
</section>

<section>
  <p class="kicker">What is new</p>
  <h2>Everyone returns options.<br>We return a night.</h2>
  <div class="two">
    <div>
      <p style="font-size:.74em">A gallery at six. Dinner at half seven. A small
      room with a DJ at eleven. Somewhere sweet after.</p>
      <p style="font-size:.74em">Different kinds of evening, in order, timed so
      one finishes before the next begins, close enough to walk.</p>
    </div>
    <div>
      <p style="font-size:.74em"><strong>And we model the room.</strong> How big
      it is, indoors or out, which of a venue's several spaces you would be in,
      whether it seats twelve.</p>
      <p style="font-size:.74em;color:var(--soft)">Nowadays is not one venue to
      us. It is a 269-capacity room and an 800-capacity yard. Different
      nights.</p>
    </div>
  </div>
  <p style="font-size:.56em;color:var(--mute);margin-top:.8em">Compared against
  Tyra, Sift, Nightlife AI, The Scene, Fever and ChatGPT. None sequence an
  evening. None know the size of the room.</p>
</section>

<section>
  <p class="kicker">How it works</p>
  <h2>Seven agents, two tiers</h2>
  <pre class="diagram">OFFLINE — runs on a refresh, shared by every user
  SCOUT ──▶ RESEARCHER ──▶ WRITER        reads listings · finds rooms · writes the copy
    └──────────┬──────────────┘
               ▼
        data/*.json  (committed)
               │
PER REQUEST ───┼──────────────────────────────────────────────────────
               ▼
 you type ─▶ CONCIERGE ─▶ Brief ─▶ PLANNER ─▶ Night ─▶ page
             (free text)          (no model,
                                   pure Python)
                                      │
                        CRITIC ◀─────┤  judges the plan; one objection sends it back
                                      │
                       REFINER ◀──────┤  "cheaper" · "swap the second one"
                                      │
                                      ▼  corpus cannot cover it?
                                   EDITOR  (plans it, with web search)</pre>
  <p style="font-size:.56em;color:var(--soft)">The expensive agents run once and
  are amortised across every plan. The Planner is deliberately not an agent:
  choosing is filtering, sequencing is arithmetic.</p>
</section>

<section>
  <p class="kicker">The app</p>
  <h2>Describe your vibe</h2>
  {shot("01-search.png", "The search page")}
</section>

<section>
  <p class="kicker">The app</p>
  <h2>Get a night, in order</h2>
  {shot("03-plan.png", "A finished plan")}
</section>

<section>
  <p class="kicker">The app</p>
  <h2>Keep the ones worth keeping</h2>
  {shot("07-saved.png", "Saved nights, with the ones you went to marked")}
</section>

<section>
  <p class="kicker">Cost to run</p>
  <h2>{money(per_plan)} a plan</h2>
  <div class="grid">
    <div><span class="big">{L['conc_cache_rate']:.0f}%</span><span class="lbl">prompt cache hit</span></div>
    <div><span class="big">0–1</span><span class="lbl">model calls per plan</span></div>
    <div><span class="big">{money(per_plan * 4 * 10_000)}</span><span class="lbl">10,000 users / month</span></div>
    <div><span class="big">{money(L['total_spend'])}</span><span class="lbl">whole project to date</span></div>
  </div>
  <table style="margin-top:1em">
    <tr><th></th><th>Before</th><th>After</th></tr>
    <tr><td>Time to a plan</td><td>~25 s</td><td class="accent"><strong>~5 s</strong></td></tr>
    <tr><td>Tokens per plan</td><td>~30,000</td><td class="accent"><strong>~1,450</strong></td></tr>
    <tr><td>Cost per plan</td><td>~$0.0090</td><td class="accent"><strong>{money(per_plan)}</strong></td></tr>
  </table>
  <p style="font-size:.5em;color:var(--soft);margin-top:.5em">Achieved by moving
  the expensive agents offline and doing the non-language work in Python. The
  tradeoff: venue copy is written once per venue, not per request.</p>
</section>

<section>
  <p class="kicker">Safety</p>
  <h2>{G['passed']} guardrails, all passing</h2>
  <div class="two">
    <div>{shot("06-attack.png", "Four injection attacks, all blocked")}</div>
    <div>
      <p style="font-size:.66em"><strong>Three defences that were wrong,
      and how we found out:</strong></p>
      <ul style="font-size:.6em">
        <li>The allowlist blocked House of Yes's own booking page. Over-blocking
        is not safety.</li>
        <li>A Book button resolved with HTTP 200 and opened the
        <em>wrong restaurant</em>. Links are now fetched and confirmed.</li>
        <li>One invented venue used to take down the whole plan with a 500. Now
        it costs one stop.</li>
      </ul>
    </div>
  </div>
</section>

<section>
  <p class="kicker">Impact</p>
  <h2>The numbers</h2>
  <div class="grid">
    <div><span class="big">~5s</span><span class="lbl">to plan a night</span></div>
    <div><span class="big">{D['venues_known']:,}</span><span class="lbl">venues</span></div>
    <div><span class="big">{D['neighborhoods']}</span><span class="lbl">neighbourhoods</span></div>
    <div><span class="big">5</span><span class="lbl">boroughs</span></div>
  </div>
  <p style="margin-top:1em;font-size:.68em">An evening for any vibe. Every room
  size researched and cited; every booking link fetched and confirmed to open
  that venue.</p>
  <p style="font-size:.56em;color:var(--accent)">TO ADD: measured comparison
  against planning a night the usual way, with a real user.</p>
</section>

<section>
  <p class="kicker">What is next</p>
  <h2>What does not work yet</h2>
  <div class="two">
    <div>
      <ul style="font-size:.64em">
        <li><strong>Opening hours.</strong> It can place you somewhere closed.</li>
        <li><strong>No event calendar.</strong> It knows venues, not what is on.</li>
        <li><strong>{D['venues_mapped']} of {D['venues_known']:,} mapped.</strong>
        The rest show no walking time.</li>
      </ul>
    </div>
    <div>
      <ul style="font-size:.64em">
        <li>Collect hours and refuse to place a closed stop.</li>
        <li>Add an events feed.</li>
        <li>Re-check venues on a schedule so closures surface.</li>
        <li>Put it in front of five people and watch where they get stuck.</li>
      </ul>
    </div>
  </div>
  <p class="foot">{e(c.AUTHOR)} · {e(c.TITLE)} · {date.today():%B %Y}</p>
</section>

</div></div>
<script src="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/reveal.js"></script>
<script>Reveal.initialize({{hash:true,slideNumber:'c/t',transition:'fade',
controlsTutorial:false,margin:0.08}});</script>
</body></html>"""


def main() -> int:
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT.name} ({OUT.stat().st_size//1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
