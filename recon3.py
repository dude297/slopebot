from playwright.sync_api import sync_playwright
import os, time

INIT = """
const orig = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function(t, a) {
  if (t && t.startsWith('webgl')) a = Object.assign({}, a, {preserveDrawingBuffer: true});
  return orig.call(this, t, a);
};
"""
os.makedirs("frames", exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(headless=False)
    pg = b.new_page(viewport={"width": 960, "height": 540})
    pg.add_init_script(INIT)
    pg.goto("https://slopeio.org/game/slope-gm/", referer="https://yoplay.io/")
    pg.wait_for_function("window.unityInstance", timeout=90000)
    pg.wait_for_timeout(6000)
    pg.mouse.click(480, 310, delay=100)  # PLAY
    t0 = time.time()
    i = 0
    while time.time() - t0 < 14:
        pg.screenshot(path=f"frames/f{i:03d}.jpg", type="jpeg", quality=60)
        i += 1
        pg.wait_for_timeout(200)
    print("frames", i)
    b.close()
