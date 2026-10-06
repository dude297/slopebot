"""Slope bot: reads the Unity WebGL canvas in-page, steers with arrow keys.
Run: python bot.py [seconds]
"""
import sys, time, os
from playwright.sync_api import sync_playwright

GAME = "https://slopeio.org/game/slope-gm/"  # real game, unwrapped from slopeio.org -> yoplay.io iframes
BALL_X, BALL_Y = 480, 330  # ball is camera-pinned here @960x540
UNIT = 6                   # err reported in 1/6 px so KD/DEAD tuning stays as before

INIT = """
const orig = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function(t, a) {
  if (t && t.startsWith('webgl')) a = Object.assign({}, a, {preserveDrawingBuffer: true});
  return orig.call(this, t, a);
};
"""

# Two boundaries:
#  1. TRACK: road edges. Road grid lines are thick (13-35px) vs building lines (1-6px); take the outermost
#     thick green runs in rows below the ball, fit lo(y)/hi(y) as straight lines, extrapolate ahead.
#  2. OBSTACLES: red runs, padded by ~ball radius (pad grows toward the camera).
# Safe zone per row = track minus padded red. Walk rows from the ball forward, pick the safe gap
# nearest the current path (wide gaps preferred), target = weighted mean of gap mids.
SENSE = f"""() => {{
  const BX={BALL_X}, BY={BALL_Y}, U={UNIT};
  const src = document.querySelector('#unity-canvas');
  const C = window._fc || (window._fc = Object.assign(document.createElement('canvas'), {{width: 960, height: 540}}));
  const cx2 = C.getContext('2d', {{willReadFrequently: true}});
  cx2.drawImage(src, 0, 0, 960, 540);
  const d = cx2.getImageData(0, 0, 960, 540).data;
  const R = (x, y) => {{ const i = (y*960+x)*4; return d[i] > 150 && d[i+1] < 100; }};
  const G = (x, y) => {{ const i = (y*960+x)*4; return d[i+1] > 150 && d[i] < 100; }};
  const runs = (y, f) => {{ const out = []; for (let x = 0; x < 960; ) {{ if (f(x, y)) {{ const s = x; while (x < 960 && f(x, y)) x++; out.push([s, x]); }} else x++; }} return out; }};

  let black = 0, n = 0;
  for (let i = 0; i < d.length; i += 64) {{ n++; if (d[i] + d[i+1] + d[i+2] < 40) black++; }}
  black /= n;

  // 1. track boundary
  // crossbars: the road grid's horizontal lines are single long green runs spanning edge to edge
  const pts = [];
  for (let y = 335; y <= 535; y += 3) {{
    const long = runs(y, G).filter(([a, b]) => b - a >= Math.max(80, 0.8 * (y - 250)));
    if (long.length) {{ const [a, b] = long.reduce((p, q) => q[1] - q[0] > p[1] - p[0] ? q : p); pts.push([y, a, b]); }}
  }}
  // one crossbar only -> no slope info; add a point assuming edges converge to the vanishing point (480,250)
  if (pts.length && pts[pts.length-1][0] - pts[0][0] < 30) {{
    const [y, a, b] = pts[0], k = 60 / (y - 250);
    pts.push([y - 60, a + (480 - a) * k, b + (480 - b) * k]);
  }}
  const fit = k => {{  // least squares x = a + b*y
    const m = pts.length, sy = pts.reduce((s, p) => s + p[0], 0), sx = pts.reduce((s, p) => s + p[k], 0);
    const syy = pts.reduce((s, p) => s + p[0]*p[0], 0), sxy = pts.reduce((s, p) => s + p[0]*p[k], 0);
    const b = (m*sxy - sy*sx) / (m*syy - sy*sy || 1), a = (sx - b*sy) / m; return y => a + b*y;
  }};
  // ponytail: last-seen track reused for 10 frames when no crossbar is visible
  if (pts.length >= 2) window._trk = {{t: [fit(1), fit(2)], age: 0}};
  else if (window._trk) window._trk.age++;
  const track = window._trk && window._trk.age < 10 ? window._trk.t : null;

  // 2. obstacle boundary + safe-gap walk
  let cx = BX, ts = 0, tw = 0, block = -1;
  const path = [], reds = [];
  for (let y = BY; y >= 240; y -= 6) {{
    let lo = 0, hi = 959;
    if (track) {{ lo = Math.max(0, track[0](y)); hi = Math.min(959, track[1](y)); const m = 0.12 * (hi - lo); lo += m; hi -= m; }}
    const pad = 8 + 0.3 * (y - 240);
    const rr = runs(y, R).map(([a, b]) => [a - pad, b + pad]);
    rr.forEach(r => reds.push([y, r[0], r[1]]));
    let gaps = [[lo, hi]];
    for (const [a, b] of rr) gaps = gaps.flatMap(([l, h]) => b <= l || a >= h ? [[l, h]] : [[l, a], [b, h]].filter(([p, q]) => q - p > 4));
    if (!gaps.length) {{ path.push([y, cx]); continue; }}
    if (block < 0 && !gaps.some(([l, h]) => l <= cx && cx <= h)) block = BY - y;
    let best = null, bs = -1e9;
    for (const [l, h] of gaps) {{
      const dist = cx < l ? l - cx : cx > h ? cx - h : 0, sc = (h - l) - 2 * dist;
      if (sc > bs) {{ bs = sc; best = [l, h]; }}
    }}
    cx = (best[0] + best[1]) / 2;
    const w = 1 + (y - 240) / 30;  // near rows matter more
    ts += cx * w; tw += w; path.push([y, cx]);
  }}
  const target = tw ? ts / tw : BX;
  const tr = track ? [[240, track[0](240), track[1](240)], [540, track[0](540), track[1](540)]] : null;
  return {{black, err: (target - BX) / U, near: (path[0][1] - BX) / U, block, track: !!track, nt: pts.length, ov: {{path, reds, tr}}}};
}}"""


DEBUG = os.environ.get("DEBUG") == "1"
KD = float(os.environ.get("KD", 0.15))   # seconds of look-ahead on lateral drift; tune per run
DEAD = float(os.environ.get("DEAD", 3))  # deadband in err units
# draws both boundaries over the game: magenta = track edges, red bars = padded obstacles, white = path
OVERLAY = """({path, reds, tr}) => {
  let o = document.querySelector('#dbg');
  if (!o) { o = Object.assign(document.createElement('canvas'), {id: 'dbg', width: 960, height: 540});
    o.style.cssText = 'position:fixed;left:0;top:0;pointer-events:none;z-index:9'; document.body.append(o); }
  const c = o.getContext('2d');
  c.clearRect(0, 0, 960, 540);
  if (tr) { c.strokeStyle = '#f0f'; c.lineWidth = 4; c.beginPath();
    c.moveTo(tr[0][1], tr[0][0]); c.lineTo(tr[1][1], tr[1][0]); c.moveTo(tr[0][2], tr[0][0]); c.lineTo(tr[1][2], tr[1][0]); c.stroke(); }
  c.fillStyle = 'rgba(255,128,0,0.6)'; reds.forEach(([y, a, b]) => c.fillRect(a, y - 2, b - a, 4));
  c.fillStyle = '#fff'; path.forEach(([y, x]) => c.fillRect(x - 4, y - 4, 8, 8));
  c.fillStyle = '#0ff'; c.fillRect(478, 0, 4, 540);
}"""


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
                pg.evaluate(OVERLAY, s["ov"])
                pg.screenshot(path=f"exp/r{runs}_{ticks:03d}.jpg", type="jpeg", quality=60)
            if ticks % 15 == 0: print(f"  t={time.time() - run_start:4.1f} err={s['err']:+.0f} track={s['track']}/{s['nt']} block={s['block']}")
            want = {-1: "ArrowLeft", 1: "ArrowRight", 0: None}[steer]
            if want != held:
                if held: pg.keyboard.up(held)
                if want: pg.keyboard.down(want)
                held = want
        b.close()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 120)
