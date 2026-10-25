"""Record the demo video: one real run through the app, captioned.

    python app.py                  # in one terminal
    python scripts/record_demo.py  # in another

Nothing here is staged. It types a vibe into the real form, waits for the real
planner, scrolls the real plan, asks the real Refiner to change something, and
saves it to a real account. The captions say what is happening because the
video has no sound.

Playwright drives the Chrome already on the machine and writes WebM. Chrome is
what most people will open it in, and Canvas accepts it.

Playwright is only needed to record this. It is not an app dependency and is
deliberately not in requirements.txt:

    pip install playwright
"""

from __future__ import annotations

import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = "http://127.0.0.1:8010"
OUT = ROOT / "output" / "demo.webm"

W, H = 1280, 800

# A caption bar, drawn over whatever page is loaded. add_init_script runs on
# every navigation, so it survives the redirects the app does on its own.
OVERLAY = """
window.__cap = function (text) {
  let bar = document.getElementById('__cap');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = '__cap';
    bar.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:2147483647;'
      + 'background:#14110F;color:#FBF9F6;font:500 17px/1.5 Inter,Helvetica,sans-serif;'
      + 'padding:16px 28px;letter-spacing:.01em;transition:opacity .25s;'
      + 'box-shadow:0 -2px 18px rgba(0,0,0,.18)';
    document.body.appendChild(bar);
  }
  bar.textContent = text;
  bar.style.opacity = text ? '1' : '0';
};
"""


def say(page, text: str, hold: int) -> None:
    page.evaluate("t => window.__cap && window.__cap(t)", text)
    page.wait_for_timeout(hold)


def glide(page, to: int, ms: int = 1400) -> None:
    """Scroll smoothly. A jump cut reads as a bug in a screen recording."""
    page.evaluate(
        """([target, dur]) => new Promise(done => {
            const start = window.scrollY, delta = target - start, t0 = performance.now();
            (function step(now) {
                const k = Math.min(1, (now - t0) / dur);
                const e = k < .5 ? 2*k*k : -1 + (4 - 2*k) * k;      // ease in out
                window.scrollTo(0, start + delta * e);
                if (k < 1) requestAnimationFrame(step); else done();
            })(t0);
        })""", [to, ms])


def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        raise SystemExit("pip install playwright")

    try:
        urllib.request.urlopen(APP + "/health", timeout=5).read()
    except OSError:
        raise SystemExit("Start the app first:  python app.py")

    tmp = ROOT / "output" / "_video"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(
            viewport={"width": W, "height": H},
            record_video_dir=str(tmp),
            record_video_size={"width": W, "height": H},
        )
        ctx.add_init_script(OVERLAY)
        page = ctx.new_page()

        # 1 ── the ask ------------------------------------------------------
        page.goto(APP + "/", wait_until="load")
        page.wait_for_timeout(1200)
        say(page, "The Programme. Describe the night you want, in your own words.", 3200)
        glide(page, 260)
        say(page, "A suggestion rotates on each visit, so nobody faces a blank box.", 3000)
        glide(page, 0, 900)

        box = page.query_selector("textarea[name='vibe'], input[name='vibe']")
        if box:
            box.scroll_into_view_if_needed()
            box.click()
            box.type("a gallery opening then dinner in the east village", delay=42)
        say(page, "One sentence. No forms to fill in, no filters required.", 2600)

        # 2 ── the wait -----------------------------------------------------
        say(page, "", 300)
        # The form opens the working page in a new tab, which is right for the
        # app and wrong for a recording: Playwright writes one video per page,
        # so a new tab splits the film in half. Same journey, one window.
        page.evaluate("""() => {
            const f = document.getElementById('planner');
            if (f) f.removeAttribute('target');
        }""")
        submit = page.query_selector("#vibego") or page.query_selector("button[type='submit']")
        if submit:
            submit.click()
        page.wait_for_timeout(900)
        say(page, "It opens a working page immediately, and tells you what it is doing.", 4200)

        page.wait_for_url("**/night/**", timeout=120_000)
        page.wait_for_timeout(2600)

        # 3 ── the plan -----------------------------------------------------
        say(page, "A complete evening in about five seconds. Not a list of options.", 5200)
        glide(page, 420)
        say(page, "Each stop has its own time, and the gap between them is real walking time.", 4200)
        glide(page, 760)
        say(page, "A map for every stop, and the nearest station from MTA open data.", 4200)
        glide(page, 1180)
        say(page, "Booking links are only shown once the page has been read and confirmed.", 5600)
        glide(page, 1650)
        say(page, "Everything is sourced. The second stop is a short walk from the first.", 4000)

        # 4 ── changing it --------------------------------------------------
        chat = page.query_selector("form textarea[name='message'], textarea[name='message']")
        if chat:
            chat.scroll_into_view_if_needed()
            page.wait_for_timeout(700)
            say(page, "You can talk to the plan instead of starting again.", 3000)
            chat.click()
            chat.type("somewhere cheaper for dinner", delay=46)
            say(page, "", 500)
            send = page.query_selector("form button[type='submit']")
            if send:
                send.click()
            page.wait_for_timeout(1500)
            say(page, "A Critic agent reviews every plan, and a Refiner handles amendments.", 6000)
            page.wait_for_timeout(5000)
            say(page, "It keeps what you liked and changes only what you asked about.", 4200)

        # 5 ── keeping it ---------------------------------------------------
        # The plan on screen is the one that gets saved, so hold on to its URL
        # before walking off to the account pages.
        plan_url = page.url

        page.goto(APP + "/signup", wait_until="load")
        page.wait_for_timeout(900)
        say(page, "An account keeps the nights you plan.", 2600)
        page.fill("input[name='username']", "demo_viewer")
        page.fill("input[name='email']", "demo_viewer@example.test")
        page.fill("input[name='password']", "a-long-enough-passphrase")
        page.wait_for_timeout(700)
        say(page, "Passwords are hashed, never stored as text. The newsletter is opt in.", 3800)
        page.click("button[type='submit']")
        page.wait_for_timeout(1800)

        page.wait_for_timeout(800)
        if "/saved" in page.url:
            say(page, "Nothing saved yet. Let us go and keep that night.", 3400)

        # On a re-run the account is already there, so sign in instead.
        if "/saved" not in page.url:
            page.goto(APP + "/login", wait_until="load")
            page.fill("input[name='identifier']", "demo_viewer")
            page.fill("input[name='password']", "a-long-enough-passphrase")
            page.wait_for_timeout(600)
            page.click("button[type='submit']")
            page.wait_for_timeout(1600)

        # back to the night, and actually save it
        page.goto(plan_url, wait_until="load")
        page.wait_for_timeout(1600)
        say(page, "Back on the same night, now signed in.", 3000)
        save = page.query_selector("form.save-form button")
        if save:
            save.scroll_into_view_if_needed()
            page.wait_for_timeout(900)
            say(page, "One button to keep it.", 2600)
            save.click()
            page.wait_for_timeout(1800)
            saved_flag = page.query_selector("a[href='/saved']")
            if saved_flag:
                saved_flag.scroll_into_view_if_needed()
            say(page, "Saved. The button knows it, and says so.", 3600)

        page.goto(APP + "/saved", wait_until="load")
        page.wait_for_timeout(1500)
        say(page, "Your nights, with a picture for each and the ones you went to marked.", 5400)
        went = page.query_selector("form[action$='/went'] button")
        if went:
            went.scroll_into_view_if_needed()
            page.wait_for_timeout(600)
            went.click()
            page.wait_for_timeout(1500)
            say(page, "Marking one as went is how taste gets learned over time.", 4000)

        # 6 ── what it costs ------------------------------------------------
        pid = plan_url.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
        if pid:
            page.goto(f"{APP}/night/{pid}?costs=1", wait_until="load")
            page.wait_for_timeout(1500)
            glide(page, 99_000, 1800)
            say(page, "Every run reports its real token usage and what it cost.", 4600)
            say(page, "Roughly two hundredths of a cent a plan, because the corpus is built offline.", 6000)

        # 7 ── who made it, and what it refuses to do -----------------------
        # Scrolled rather than flashed: the page says where every fact comes
        # from and what the app will not claim, which is the argument for
        # trusting a recommendation at all.
        page.goto(APP + "/about", wait_until="load")
        page.wait_for_timeout(1400)
        say(page, "The Programme. New York, your way.", 4000)
        glide(page, 760)
        say(page, "Who we are, in plain language.", 3600)
        glide(page, 1180)
        say(page, "What it does, and where every fact on the page came from.", 4600)
        glide(page, 1800)
        say(page, "And what it will not do. It never books for you.", 4400)
        glide(page, 2050)
        say(page, "It never invents a venue, and it says so when it does not know.", 4600)
        glide(page, 2320)
        say(page, "What an account stores, and what it does not.", 4200)
        glide(page, 0, 1700)
        say(page, "An evening for any vibe, in all five boroughs.", 4400)
        say(page, "", 1000)

        ctx.close()
        browser.close()

    clips = sorted(tmp.glob("*.webm"))
    if not clips:
        raise SystemExit("Playwright wrote no video")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    shutil.move(str(clips[-1]), OUT)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"wrote {OUT.relative_to(ROOT)}  ({OUT.stat().st_size // 1024} KB)")

    # Playwright only writes WebM, and macOS has no VP9 decoder, so a marker
    # double-clicking the file would get nothing. imageio-ffmpeg ships a build
    # with libx264; without it the WebM is still perfectly good in a browser.
    try:
        import imageio_ffmpeg
        import subprocess
        mp4 = OUT.with_suffix(".mp4")
        subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
             "-i", str(OUT), "-c:v", "libx264", "-preset", "slow", "-crf", "23",
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4), "-y"],
            check=True)
        print(f"wrote {mp4.relative_to(ROOT)}  ({mp4.stat().st_size // 1024} KB)")
    except Exception as exc:                                   # noqa: BLE001
        print(f"no mp4 ({exc}); the webm plays in any browser")


if __name__ == "__main__":
    main()
