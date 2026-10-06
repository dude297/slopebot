"""Print live sensor snapshots without steering.

Set REACT=0 to inspect straight-mode perception, or leave it at the default
(REACT=1) to inspect the full obstacle-aware sensor output.
"""
from playwright.sync_api import sync_playwright
import os
from bot import GAME, INIT, SENSE

REACT = os.environ.get("REACT", "1") != "0"

with sync_playwright() as p:
    b = p.chromium.launch(headless=False)
    pg = b.new_page(viewport={"width": 960, "height": 540})
    pg.add_init_script(INIT)
    pg.goto(GAME, referer="https://yoplay.io/")
    pg.wait_for_function("window.unityInstance", timeout=90000)
    for i in range(10):
        pg.wait_for_timeout(1000)
        print(i, pg.evaluate(SENSE, REACT))
    b.close()
