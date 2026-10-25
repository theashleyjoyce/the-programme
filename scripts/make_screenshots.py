"""Regenerate every screenshot the report and slides embed.

The figures were captured by hand once, which meant they drifted the moment
the app changed and nobody could tell which version they showed. This script
takes all seven from the running app and the current test output, so the
images in the report are always of the code in the repo.

    python app.py                      # in one terminal
    python scripts/make_screenshots.py # in another

Playwright drives the Chrome already on the machine, so there is no browser
to download. It replaced a plain `chrome --screenshot`, which shot the page
before OpenStreetMap had drawn its tiles and produced a figure with an empty
grey box where the map belongs. The map is a feature; a screenshot that does
not show it is not a screenshot of this app.

Playwright is only needed to make these figures. It is not an app dependency
and is deliberately not in requirements.txt:

    pip install playwright
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "report" / "screenshots"
WORK = ROOT / "output"
APP = "http://127.0.0.1:8010"

WIDTH = 800

# Long enough for OpenStreetMap to fetch and paint its tiles. Short of this
# the map is a grey rectangle and the figure quietly lies about the product.
MAP_WAIT = 9000
PAGE_WAIT = 2500

# A throwaway account so the saved-nights figure has something in it. Reused
# between runs, and it only ever exists in the local database.
SHOT_USER = "programme_demo"
SHOT_MAIL = "programme_demo@example.test"
SHOT_PASS = "figures-only-local-account"

ANSI = {
    "32": "#5FD38A", "31": "#E86A5A", "33": "#E2B341",
    "90": "#8A8077", "36": "#6FB7D4", "35": "#C08CD6",
}


def ansi_to_html(text: str) -> str:
    """ANSI escape codes to spans, closing what it opens.

    An earlier version of the report printed a raw colour code as a result
    because something read this output without decoding it.
    """
    out: list[str] = []
    depth = 0
    i = 0
    for m in re.finditer(r"\x1b\[([0-9;]*)m", text):
        out.append(html.escape(text[i:m.start()]))
        i = m.end()
        codes = [c for c in m.group(1).split(";") if c]
        if not codes or "0" in codes:
            out.append("</span>" * depth)
            depth = 0
            continue
        for code in codes:
            if code in ANSI:
                out.append(f'<span style="color:{ANSI[code]}">')
                depth += 1
    out.append(html.escape(text[i:]))
    out.append("</span>" * depth)
    return "".join(out)


TERM_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html,body{{background:#14110F;margin:0}}
body{{padding:2rem 2.4rem;font-family:ui-monospace,Menlo,monospace;
font-size:13px;line-height:1.55;color:#EDE7DF;width:800px;box-sizing:border-box}}
.bar{{color:#8A8077;font-size:13px;letter-spacing:.16em;text-transform:uppercase;
border-bottom:1px solid #322D28;padding-bottom:.8rem;margin-bottom:1.2rem}}
pre{{margin:0;white-space:pre-wrap;word-break:break-word}}
</style></head><body><div class="bar">$ {cmd}</div><pre>{body}</pre></body></html>"""


def run_terminal(script: str) -> str:
    proc = subprocess.run([sys.executable, "-I", str(ROOT / script)],
                          capture_output=True, text=True, cwd=ROOT)
    if proc.returncode != 0 and not proc.stdout:
        raise SystemExit(f"{script} produced nothing:\n{proc.stderr[:800]}")
    return proc.stdout


def plan_id(vibe: str) -> str:
    body = urllib.parse.urlencode({"vibe": vibe, "date": "2026-10-26"}).encode()
    req = urllib.request.Request(
        APP + "/plan", data=body, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.load(r)["redirect"].rsplit("/", 1)[1]


def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        raise SystemExit("pip install playwright")

    SHOTS.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlopen(APP + "/health", timeout=5).read()
    except OSError:
        raise SystemExit("Start the app first:  python app.py")

    print("planning nights for the figures...")
    gallery = plan_id("a gallery opening then dinner in the east village")
    second = plan_id("cocktails then live music in williamsburg")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": WIDTH, "height": 1000})

        def shoot(name: str, wait: int = PAGE_WAIT) -> None:
            page.wait_for_timeout(wait)
            page.screenshot(path=str(SHOTS / name), full_page=True)
            print(f"  {name}")

        page.goto(APP + "/", wait_until="load")
        shoot("01-search.png")

        # The working page replaces itself the moment the plan lands, so a
        # plain visit screenshots the finished plan instead. Stubbing fetch
        # before the page's own script runs holds it mid-flight: same markup,
        # same CSS, same staged ticks, just paused where the work happens.
        page.add_init_script("window.fetch = function () "
                             "{ return new Promise(function () {}); };")
        vibe = urllib.parse.quote("a gallery opening then dinner in the east village")
        page.goto(f"{APP}/working?vibe={vibe}&date=2026-10-26", wait_until="load")
        shoot("02-working.png", 2200)

        # Undo the stub for everything that follows.
        page = browser.new_page(viewport={"width": WIDTH, "height": 1000})

        def shoot2(name: str, wait: int = PAGE_WAIT) -> None:
            page.wait_for_timeout(wait)
            page.screenshot(path=str(SHOTS / name), full_page=True)
            print(f"  {name}")

        page.goto(f"{APP}/night/{gallery}", wait_until="load")
        shoot2("03-plan.png", MAP_WAIT)

        page.goto(f"{APP}/night/{gallery}?costs=1", wait_until="load")
        shoot2("04-costs.png", MAP_WAIT)

        # Saved nights, which needs an account and something saved in it.
        page.goto(APP + "/signup", wait_until="load")
        page.fill('input[name="username"]', SHOT_USER)
        page.fill('input[name="email"]', SHOT_MAIL)
        page.fill('input[name="password"]', SHOT_PASS)
        page.click('button[type="submit"]')
        page.wait_for_timeout(600)
        if "/saved" not in page.url:                     # already registered
            page.goto(APP + "/login", wait_until="load")
            page.fill('input[name="identifier"]', SHOT_USER)
            page.fill('input[name="password"]', SHOT_PASS)
            page.click('button[type="submit"]')
            page.wait_for_timeout(600)

        for pid in (gallery, second):
            page.goto(f"{APP}/night/{pid}", wait_until="load")
            button = page.query_selector('form.save-form button')
            if button:
                button.click()
                page.wait_for_timeout(700)

        page.goto(APP + "/saved", wait_until="load")
        shoot2("07-saved.png")

        page.goto(APP + "/newsletter/preview", wait_until="load")
        shoot2("08-newsletter.png", 1200)

        for name, script, cmd in [
            ("05-guardrails.png", "test_guardrails.py", "python test_guardrails.py"),
            ("06-attack.png", "demo_attack.py", "python demo_attack.py"),
        ]:
            print(f"  running {script}...")
            body = ansi_to_html(run_terminal(script))
            tmp = WORK / name.replace(".png", ".html")
            tmp.write_text(TERM_PAGE.format(cmd=cmd, body=body), encoding="utf-8")
            page.goto(tmp.as_uri(), wait_until="load")
            shoot2(name, 400)

        browser.close()

    print("\nwritten to report/screenshots/")
    print("now rerun:  python scripts/build_report.py && python scripts/build_slides.py")


if __name__ == "__main__":
    main()
