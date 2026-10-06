"""Slope bot: reads the Unity WebGL canvas in-page, steers with arrow keys.
Run: python bot.py [seconds]
"""
import sys, time, os
from playwright.sync_api import sync_playwright

GAME = "https://slopeio.org/game/slope-gm/"  # real game, unwrapped from slopeio.org -> yoplay.io iframes
W, H = 160, 90          # analysis resolution
BALL_X, BALL_Y = 80, 55  # ball is camera-pinned here (scaled from ~480,330 @960x540)

INIT = """
const orig = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function(t, a) {
  if (t && t.startsWith('webgl')) a = Object.assign({}, a, {preserveDrawingBuffer: true});
  return orig.call(this, t, a);
};
"""

# Returns {black, steer, redC, gx}. steer: -1 left, 0 none, 1 right.
SENSE = f"""() => {{
  const W={W}, H={H}, BX={BALL_X}, BY={BALL_Y};
  const src = document.querySelector('#unity-canvas');
  const c = window._sc || (window._sc = Object.assign(document.createElement('canvas'), {{width: W, height: H}}));
  const ctx = c.getContext('2d', {{willReadFrequently: true}});
  ctx.drawImage(src, 0, 0, W, H);
  const d = ctx.getImageData(0, 0, W, H).data;
  const red = (x, y) => {{ const i = (y*W+x)*4; return d[i] > 150 && d[i+1] < 100; }};
  let black = 0;
  for (let i = 0; i < d.length; i += 4) if (d[i] + d[i+1] + d[i+2] < 40) black++;
  black /= W*H;

  // Corridor following: red = walls/obstacles. Walk rows from the ball forward,
  // tracking the free interval between nearest reds; when red blocks the path, jump to the wider gap.
  // ponytail: red-only boundaries; non-red drop-off edges need a floor detector if runs die by falling.
  let cx = BX, ts = 0, tw = 0, block = -1;
  const rows = [];
  for (let y = BY; y > BY - 28; y -= 2) {{
    if (red(cx, y)) {{
      if (block < 0) block = BY - y;
      let l = cx; while (l > 0 && red(l, y)) l--;
      let r = cx; while (r < W-1 && red(r, y)) r++;
      let ll = l; while (ll > 0 && !red(ll, y)) ll--;
      let rr = r; while (rr < W-1 && !red(rr, y)) rr++;
      cx = (l - ll) > (rr - r) ? (ll + l) >> 1 : (r + rr) >> 1;
    }} else {{
      let l = cx; while (l > 0 && !red(l, y)) l--;
      let r = cx; while (r < W-1 && !red(r, y)) r++;
      cx = (l + r) >> 1;
    }}
    const w = 1 + (y - (BY - 28)) / 7;  // near rows matter more
    ts += cx * w; tw += w; rows.push(cx);
  }}
  const target = ts / tw;
  // near-row error only (corridor at the ball), plus the look-ahead target
  const near = (rows[0] + rows[1] + rows[2]) / 3 - BX;
  let redNear = 0;
  for (let y = BY - 14; y <= BY; y++) for (let x = BX - 40; x <= BX + 40; x++) if (red(x, y)) redNear++;

  // Floor: open sections have drop-off edges, no red. Road grid lines are thick (13-35px @960w)
  // vs building lines (1-6px), so road extent = outermost thick green runs in rows below the ball.
  const F = window._fc || (window._fc = Object.assign(document.createElement('canvas'), {{width: 960, height: 540}}));
  const fx = F.getContext('2d', {{willReadFrequently: true}});
  fx.drawImage(src, 0, 0, 960, 540);
  const mids = [], edges = [];
  for (let y = 360; y <= 520; y += 20) {{
    const r = fx.getImageData(0, y, 960, 1).data, minRun = Math.max(8, 0.08 * (y - 250));
    let lo = -1, hi = -1;
    for (let x = 0; x < 960; ) {{
      if (r[x*4+1] > 150 && r[x*4] < 100) {{
        const s = x; while (x < 960 && r[x*4+1] > 150 && r[x*4] < 100) x++;
        if (x - s >= minRun) {{ if (lo < 0) lo = s; hi = x; }}
      }} else x++;
    }}
    if (lo >= 0 && hi - lo > 60) {{ mids.push((lo + hi) / 2); edges.push([y, lo, hi]); }}
  }}
  const floorErr = mids.length ? (mids.reduce((a, b) => a + b) / mids.length - 480) / (960 / W) : 0;

  const useRed = block >= 0 || redNear > 6;
  return {{black, err: useRed ? target - BX : floorErr, near: useRed ? near : floorErr, block, rows, useRed, floorErr, nf: mids.length, edges}};
}}"""


DEBUG = os.environ.get("DEBUG") == "1"
KD = float(os.environ.get("KD", 0.15))   # seconds of look-ahead on lateral drift; tune per run
DEAD = float(os.environ.get("DEAD", 3))  # deadband in analysis px
# draws the sensed path (white dots) over the game so screenshots show what the bot "sees"
OVERLAY = f"""([rows, edges]) => {{
  let o = document.querySelector('#dbg');
  if (!o) {{ o = Object.assign(document.createElement('canvas'), {{id: 'dbg', width: 960, height: 540}});
    o.style.cssText = 'position:fixed;left:0;top:0;pointer-events:none;z-index:9'; document.body.append(o); }}
  const c = o.getContext('2d'), k = 960 / {W};
  c.clearRect(0, 0, 960, 540); c.fillStyle = '#fff';
  rows.forEach((x, j) => c.fillRect(x*k - 4, ({BALL_Y} - 2*j)*k - 4, 8, 8));
  c.fillStyle = '#0ff'; c.fillRect({BALL_X}*k - 2, 0, 4, 540);
  c.fillStyle = '#f0f'; edges.forEach(([y, lo, hi]) => {{ c.fillRect(lo - 5, y - 5, 10, 10); c.fillRect(hi - 5, y - 5, 10, 10); c.fillRect((lo+hi)/2 - 2, y - 2, 4, 4); }});
}}"""


def main(seconds=120):
    os.makedirs("deaths", exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(headless=False)
        pg = b.new_page(viewport={"width": 960, "height": 540})
        pg.add_init_script(INIT)
        pg.goto(GAME, referer="https://yoplay.io/")
        pg.wait_for_function("window.unityInstance", timeout=90000)
        pg.wait_for_timeout(6000)

        held, runs, run_start, last_click = None, 0, None, 0
        t0 = time.time()
        while time.time() - t0 < seconds:
            s = pg.evaluate(SENSE)
            if s["black"] > 0.78:  # menu / game over (menu measures ~0.845)
                if held: pg.keyboard.up(held); held = None
                if run_start and time.time() - run_start < 0.5:
                    run_start = None  # dark transition frame, not a real run
                if run_start:
                    runs += 1
                    print(f"run {runs}: {time.time() - run_start:.1f}s")
                    pg.screenshot(path=f"deaths/run{runs:03d}.png")
                    run_start = None
                if time.time() - last_click > 1.5:
                    pg.mouse.click(480, 310, delay=100)
                    last_click = time.time()
                continue
            now = time.time()
            if run_start is None: run_start = now; ticks = 0; prev = (now, s["near"])
            ticks += 1
            # PD: ball keeps lateral momentum, so counter-steer on how fast the corridor drifts past us
            dt = max(now - prev[0], 1e-3)
            vel = (s["near"] - prev[1]) / dt
            prev = (now, s["near"])
            u = s["err"] + KD * vel
            steer = 0 if abs(u) < DEAD else (1 if u > 0 else -1)
            if DEBUG and runs < 6:
                pg.evaluate(OVERLAY, [s["rows"], s["edges"]])
                pg.screenshot(path=f"exp/r{runs}_{ticks:03d}.jpg", type="jpeg", quality=60)
            if ticks % 15 == 0: print(f"  t={time.time() - run_start:4.1f} err={s['err']:+.0f} red={s['useRed']} floor={s['floorErr']:+.0f}/{s['nf']} block={s['block']}")
            want = {-1: "ArrowLeft", 1: "ArrowRight", 0: None}[steer]
            if want != held:
                if held: pg.keyboard.up(held)
                if want: pg.keyboard.down(want)
                held = want
        b.close()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 120)
