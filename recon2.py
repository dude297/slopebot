from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=False)
    pg = b.new_page(viewport={"width": 960, "height": 540})
    pg.on("console", lambda m: print("CONSOLE", m.text[:200]))
    pg.goto("https://slopeio.org/game/slope-gm/", referer="https://yoplay.io/")
    pg.wait_for_function("window.unityInstance", timeout=90000)
    pg.wait_for_timeout(4000)
    pg.screenshot(path="s0_menu.png")
    print("unity keys:", pg.evaluate("Object.keys(window.unityInstance)"))
    pg.mouse.click(480, 270)
    pg.wait_for_timeout(1500)
    pg.screenshot(path="s1_after_click.png")
    pg.keyboard.press("Space")
    for i in range(2, 6):
        pg.wait_for_timeout(1500)
        pg.screenshot(path=f"s{i}.png")
    b.close()
