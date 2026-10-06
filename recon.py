from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=False)
    pg = b.new_page(viewport={"width": 1280, "height": 800})
    pg.on("request", lambda r: r.resource_type in ("script", "document", "xhr", "fetch") and print("REQ", r.resource_type, r.url[:150]))
    pg.goto("https://slopeio.org/", wait_until="domcontentloaded")
    pg.wait_for_timeout(8000)
    pg.screenshot(path="shot.png")
    for f in pg.frames:
        print("FRAME", f.url[:150])
        try:
            print(f.evaluate("""() => JSON.stringify({
                title: document.title,
                canvases: [...document.querySelectorAll('canvas')].map(c => [c.id, c.width, c.height]),
                iframes: [...document.querySelectorAll('iframe')].map(i => [i.id, i.src]),
                globals: Object.keys(window).filter(k => /unity|game|slope|c3|gml|construct|phaser|ball|score/i.test(k)).slice(0, 50),
            })"""))
        except Exception as e:
            print("  err", e)
    b.close()
