"""Drive PrintVault and Headfit through a click path and record it.

Two webm clips into promo/, which tools/promo-build.sh then cuts into the reel.
Recording and composing are separate on purpose: the capture is the slow,
flaky half, and re-cutting titles should not mean re-driving two apps.

Needs both local servers up, which is what .claude/launch.json starts:
    printvault-app  on 9123   the app itself, opened with ?demo
    printvault-site on 9124   serves site/headfit.html

?demo matters. It fills the library with an invented one, so nothing anybody's
real folder contains ends up in a video, and the banner saying so stays on
screen rather than being cropped out.

    py tools/promo-record.py            both
    py tools/promo-record.py headfit    just that one, when a click path changed
"""
from pathlib import Path
from playwright.sync_api import sync_playwright
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "promo"
APP = "http://localhost:9123/index.html?demo"
HEADFIT = "http://localhost:9124/headfit.html"
# Portrait, because the reel is portrait. Filming at 1280x800 and scaling it
# into a 1080x1920 canvas left the clip filling barely a third of the height
# with dead space above and below. Both apps hold up at 1000x1400: PrintVault
# keeps its sidebar and a three wide grid, Headfit keeps a large viewport.
SIZE = {"width": 1000, "height": 1400}


def beat(page, seconds):
    """A pause long enough to read what just happened."""
    page.wait_for_timeout(int(seconds * 1000))


def record(pw, url, name, steps):
    # channel="chrome" uses the Chrome already installed on this machine.
    # Playwright pins its own chromium build and the one it wants is usually not
    # the one on disk, which turns "make a video" into a 150 MB download for no
    # gain: the thing being filmed is a web app in Chrome either way.
    browser = pw.chromium.launch(channel="chrome")
    ctx = browser.new_context(viewport=SIZE, record_video_dir=str(OUT / "raw"),
                              record_video_size=SIZE, device_scale_factor=1)
    page = ctx.new_page()
    page.goto(url, wait_until="load")
    try:
        steps(page)
    finally:
        video = page.video
        ctx.close()
        browser.close()
        src = Path(video.path())
        dest = OUT / f"{name}.webm"
        dest.unlink(missing_ok=True)
        shutil.move(str(src), str(dest))
        print(f"  {dest.name}  {dest.stat().st_size // 1024} KB")


def printvault(page):
    beat(page, 2.0)                      # the library draws itself
    for _ in range(6):                   # a slow look down the grid
        page.mouse.wheel(0, 160)
        beat(page, 0.22)
    beat(page, 0.8)
    page.mouse.wheel(0, -1200)
    beat(page, 0.6)

    # A model tile is div.pv-card with an onclick of PV.Library.click(event, id).
    # Not PV.Detail.open, which is what the detail view calls internally and what
    # a first guess at this selector matched: nothing.
    card = page.locator("div.pv-card").first
    if card.count():
        card.click()
        beat(page, 3.0)                  # one model, its files and its settings
        page.keyboard.press("Escape")
        beat(page, 0.6)
    else:
        print("  (no model card found, skipped the detail view)", file=sys.stderr)

    for tab, hold in (("Duplicates", 2.8), ("Prints", 2.6)):
        t = page.get_by_text(tab, exact=True).first
        if t.count():
            t.click()
            beat(page, hold)


def headfit(page):
    beat(page, 3.0)                      # three.js, and the head gets built

    def press(label, hold):
        b = page.get_by_role("button", name=label, exact=True).first
        if b.count():
            b.click()
            beat(page, hold)
        else:
            print(f"  (no button called {label}, skipped)", file=sys.stderr)

    press("Large", 1.8)                  # the head changes shape on screen

    # The side panel is <details> sections and only Head and Helmet start open,
    # so the button that does the actual work is not on screen until Fit check
    # is expanded. Worth opening on camera: it is how you would find it too.
    fit = page.locator("details.grp summary", has_text="Fit check").first
    if fit.count():
        fit.click()
        beat(page, 1.0)

    press("Analyse fit", 3.4)            # clearance painted onto the head
    # Side then back to iso. Top is left out on purpose: straight down, a head
    # with no face in frame is an egg, and it undoes the work the previous eight
    # seconds did to make it read as a head.
    press("Side", 2.2)
    press("Iso", 2.4)


if __name__ == "__main__":
    (OUT / "raw").mkdir(parents=True, exist_ok=True)
    want = sys.argv[1:] or ["printvault", "headfit"]
    jobs = {"printvault": (APP, printvault), "headfit": (HEADFIT, headfit)}
    for name in want:
        if name not in jobs:
            sys.exit(f"no click path called {name}; try {' or '.join(jobs)}")
    t0 = time.time()
    with sync_playwright() as pw:
        for name in want:
            url, steps = jobs[name]
            print(f"recording {name}")
            record(pw, url, name, steps)
    shutil.rmtree(OUT / "raw", ignore_errors=True)
    print(f"done in {time.time() - t0:.0f}s")
