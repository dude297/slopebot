from playwright.sync_api import sync_playwright
import time
from bot import GAME, INIT, SENSE

with sync_playwright() as p:
    b = p.chromium.launch(headless=False)
    pg = b.new_page(viewport={"width": 960, "height": 540})
    pg.add_init_script(INIT)
    pg.goto(GAME, referer="https://yoplay.io/")
    pg.wait_for_function("window.unityInstance", timeout=90000)
    for i in range(10):
        pg.wait_for_timeout(1000)
        print(i, pg.evaluate(SENSE))
    b.close()
