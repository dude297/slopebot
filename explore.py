"""Controlled experiment: scripted key holds, dump frames + sensor values to exp/."""
from playwright.sync_api import sync_playwright
import os, time, json
from bot import GAME, INIT, SENSE

PLAN = [(None, 2.0), ("ArrowRight", 1.5), (None, 1.0), ("ArrowLeft", 1.5), (None, 4.0)]
REACT = os.environ.get("REACT", "1") != "0"

os.makedirs("exp", exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(headless=False)
    pg = b.new_page(viewport={"width": 960, "height": 540})
    pg.add_init_script(INIT)
    pg.goto(GAME, referer="https://yoplay.io/")
    pg.wait_for_function("window.unityInstance", timeout=90000)
    pg.wait_for_timeout(6000)
    pg.mouse.click(480, 310, delay=100)
    pg.wait_for_timeout(500)
    i, log = 0, []
    for key, dur in PLAN:
        if key:
            pg.keyboard.down(key)
        end = time.time() + dur
        while time.time() < end:
            s = pg.evaluate(SENSE, REACT)
            s.update(i=i, key=key, react=REACT)
            log.append(s)
            pg.screenshot(path=f"exp/e{i:03d}.jpg", type="jpeg", quality=60)
            i += 1
        if key:
            pg.keyboard.up(key)
    for s in log:
        print(json.dumps(s))
    b.close()
