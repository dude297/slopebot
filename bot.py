"""Slope bot: reads the Unity WebGL canvas in-page, steers with arrow keys.
Run: python bot.py [seconds]
"""
import sys, time, os
from playwright.sync_api import sync_playwright

GAME = "https://slopeio.org/game/slope-gm/"  # real game, unwrapped from slopeio.org -> yoplay.io iframes
BALL_X, BALL_Y = 480, 330  # ball is camera-pinned here @960x540
NOSTEER = os.environ.get("NOSTEER") == "1"         # baseline: never press a key
UNIT = 6                  # err reported in 1/6 px so KD/DEAD tuning stays as before

INIT = """
const orig = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function(t, a) {
  if (t && t.startsWith('webgl')) a = Object.assign({}, a, {preserveDrawingBuffer: true});
  return orig.call(this, t, a);
};
"""

# Two boundaries, sampled in a frame rotated about the ball (camera rolls on slopes/curves):
#  u = lateral offset from ball (+ right), v = offset along screen-up axis (- ahead, + toward camera).
#  1. TRACK: road crossbars = long green runs passing under the ball. Tilt = angle whose scanlines make
#     them longest. Fit lo(v)/hi(v) through crossbar endpoints, extrapolate ahead.
#     In the tunnel (red on both sides) the red walls are the track, crossbar fit is skipped.
#  2. OBSTACLES: red runs within LOOK px ahead, padded by ~ball radius.
# Safe zone per row = track minus padded red; walk forward picking the gap nearest the path.
SENSE = f"""(REACT) => {{
  const BX={BALL_X}, BY={BALL_Y}, U={UNIT}, LOOK=100, STRAIGHT=!REACT;
  const src = document.querySelector('#unity-canvas');
  const C = window._fc || (window._fc = Object.assign(document.createElement('canvas'), {{width: 960, height: 540}}));
  const g2 = C.getContext('2d', {{willReadFrequently: true}});
  g2.drawImage(src, 0, 0, 960, 540);
  const d = g2.getImageData(0, 0, 960, 540).data;
  let black = 0, n = 0;
  for (let i = 0; i < d.length; i += 64) {{ n++; if (d[i] + d[i+1] + d[i+2] < 40) black++; }}
  black /= n;
  const isR = i => d[i] > 150 && d[i+1] < 100, isG = i => d[i+1] > 150 && d[i] < 100;
  const gw = (y, a, b) => {{ let k = 0; for (let x = a; x < b; x++) if (isG((y*960 + x) * 4)) k++; return k; }};
  // score digit top-centre: row 25 is above the tutorial text. "1" = ~9px bar, "0"/"2".. = ~30px box
  // "1" = bar at x 472-488 with empty columns either side, on rows above (22,26) and below (62,66) the text
  const one = [22, 26, 62, 66].every(y => gw(y, 472, 489) >= 7 && gw(y, 440, 470) === 0 && gw(y, 491, 520) === 0);
  // GAMEOVER title text: ~120px green on rows 70/75 in x 320-640 (menu: 0, gameplay: <=32)
  const over = black > 0.78 && gw(70, 320, 640) >= 90 && gw(75, 320, 640) >= 90;

  const px = (u, v, th) => {{ const c = Math.cos(th), s = Math.sin(th); return [BX + u*c - v*s, BY + u*s + v*c]; }};
  // runs along the rotated scanline at offset v, in u coords
  const runs = (v, f, th) => {{
    const c = Math.cos(th), s = Math.sin(th), out = []; let st = null;
    for (let u = -480; u <= 480; u++) {{
      const x = Math.round(BX + u*c - v*s), y = Math.round(BY + u*s + v*c);
      const on = x >= 0 && x < 960 && y >= 0 && y < 540 && f((y*960 + x) * 4);
      if (on && st === null) st = u; else if (!on && st !== null) {{ out.push([st, u]); st = null; }}
    }}
    if (st !== null) out.push([st, 481]);
    return out;
  }};

  // 1. track boundary: crossbars under the ball, best tilt
  const bars = th => {{
    const pts = [];
    for (let v = 5; v <= 205; v += 4) {{
      const min = Math.max(80, 0.8 * (v + 80));
      const ok = runs(v, isG, th).filter(([a, b]) => b - a >= min && a <= 40 && b >= -40);
      if (ok.length) {{ const [a, b] = ok.reduce((p, q) => q[1] - q[0] > p[1] - p[0] ? q : p); pts.push([v, a, b]); }}
    }}
    return pts;
  }};
  // ponytail: tilt fixed at 0; "longest run" tilt search locked onto diagonal building/rail lines.
  // Rotated sampling kept so a real tilt estimate (e.g. from crossbar edge slope) can plug in here.
  const th = 0, pts = bars(th);

  // tunnel: red walls on both sides just ahead of the ball -> they define the track
  let rl = 0, rrt = 0;
  for (let v = -60; v <= 0; v += 10) for (const [a, b] of runs(v, isR, th)) {{ if (b < 0) rl++; if (a > 0) rrt++; }}
  const tunnel = rl > 0 && rrt > 0;

  // single crossbar -> no slope; assume edges converge 80px above the ball
  if (pts.length && pts[pts.length-1][0] - pts[0][0] < 30) {{
    const [v, a, b] = pts[0], k = 60 / (v + 80);
    pts.push([v - 60, a * (1 - k), b * (1 - k)]);
  }}
  const fit = k => {{  // least squares u = a + b*v
    const m = pts.length, sy = pts.reduce((s, p) => s + p[0], 0), sx = pts.reduce((s, p) => s + p[k], 0);
    const syy = pts.reduce((s, p) => s + p[0]*p[0], 0), sxy = pts.reduce((s, p) => s + p[0]*p[k], 0);
    const b = (m*sxy - sy*sx) / (m*syy - sy*sy || 1), a = (sx - b*sy) / m; return v => a + b*v;
  }};
  // ponytail: last-seen track reused for 10 frames when no crossbar is visible
  if (pts.length >= 2) window._trk = {{t: [fit(1), fit(2)], age: 0}};
  else if (window._trk) window._trk.age++;
  const track = !tunnel && window._trk && window._trk.age < 10 ? window._trk.t : null;

  // 2. obstacle boundary + safe-gap walk
  let cu = 0, ts = 0, tw = 0, block = -1, anyRed = false;
  const path = [], reds = [];
  for (let v = 0; v >= -LOOK; v -= 5) {{
    let lo = -480, hi = 480;
    if (track) {{ lo = track[0](v); hi = track[1](v); const m = 0.12 * (hi - lo); lo += m; hi -= m; }}
    const pad = 6 + 0.22 * (v + LOOK);
    // STRAIGHT mode (milestone 1): lane-keeping only, red counts just as tunnel walls
    const rr = STRAIGHT && !tunnel ? [] : runs(v, isR, th).map(([a, b]) => [a - pad, b + pad]);
    if (rr.length) anyRed = true;
    rr.forEach(([a, b]) => reds.push([...px(a, v, th), ...px(b, v, th)]));
    let gaps = [[lo, hi]];
    for (const [a, b] of rr) gaps = gaps.flatMap(([l, h]) => b <= l || a >= h ? [[l, h]] : [[l, a], [b, h]].filter(([p, q]) => q - p > 4));
    if (!gaps.length) {{ path.push(px(cu, v, th)); continue; }}
    if (block < 0 && !gaps.some(([l, h]) => l <= cu && cu <= h)) block = -v;
    let bg = null, bs = -1e9;
    for (const [l, h] of gaps) {{
      const dist = cu < l ? l - cu : cu > h ? cu - h : 0, sc = (h - l) - 2 * dist;
      if (sc > bs) {{ bs = sc; bg = [l, h]; }}
    }}
    cu = (bg[0] + bg[1]) / 2;
    const w = 1 + (v + LOOK) / 25;  // near rows matter more
    ts += cu * w; tw += w; path.push(px(cu, v, th));
  }}
  const target = tw ? ts / tw : 0;
  const tr = track ? [[...px(track[0](-LOOK), -LOOK, th), ...px(track[0](210), 210, th)],
                      [...px(track[1](-LOOK), -LOOK, th), ...px(track[1](210), 210, th)]] : null;
  const nearU = path.length ? (path[0][0] - BX) : 0;
  return {{black, over, score1: one, err: target / U, near: nearU / U, block, track: !!track, tunnel, nt: pts.length,
          th: Math.round(th * 57.3), road: pts.length > 0 || anyRed, ov: {{path, reds, tr}}}};
}}"""


DEBUG = os.environ.get("DEBUG") == "1"
KD = float(os.environ.get("KD", 0.15))   # seconds of look-ahead on lateral drift; tune per run
DEAD = float(os.environ.get("DEAD", 3))  # deadband in err units
# draws both boundaries over the game: magenta = track edges, orange = padded obstacles, white = path
OVERLAY = """({path, reds, tr}) => {
  let o = document.querySelector('#dbg');
  if (!o) { o = Object.assign(document.createElement('canvas'), {id: 'dbg', width: 960, height: 540});
    o.style.cssText = 'position:fixed;left:0;top:0;pointer-events:none;z-index:9'; document.body.append(o); }
  const c = o.getContext('2d');
  c.clearRect(0, 0, 960, 540);
  const seg = ([a, b, x, y]) => { c.beginPath(); c.moveTo(a, b); c.lineTo(x, y); c.stroke(); };
  if (tr) { c.strokeStyle = '#f0f'; c.lineWidth = 4; tr.forEach(seg); }
  c.strokeStyle = 'rgba(255,128,0,0.7)'; c.lineWidth = 3; reds.forEach(seg);
  c.fillStyle = '#fff'; path.forEach(([x, y]) => c.fillRect(x - 4, y - 4, 8, 8));
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

        held, runs, run_start, last_click, react = None, 0, None, 0, False
        t0 = time.time()
        while time.time() - t0 < seconds:
            s = pg.evaluate(SENSE, react)
            if s["over"] or (run_start is None and s["black"] > 0.78):  # GAMEOVER, or menu before a run
                if held: pg.keyboard.up(held); held = None
                if run_start and s["over"]:
                    runs += 1
                    sw = f"bot from {react_at - run_start:.1f}s" if react else "never reached score 1"
                    print(f"run {runs}: {time.time() - run_start:.1f}s ({sw})")
                    pg.screenshot(path=f"deaths/run{runs:03d}.png")
                    run_start = None
                if time.time() - last_click > 1.5:
                    pg.mouse.click(480, 310, delay=100)
                    last_click = time.time()
                continue
            now = time.time()
            if run_start is None: run_start = now; ticks = 0; prev = (now, s["near"]); react = False
            ticks += 1
            # phase 1: roll straight (predictable) until score shows 1; phase 2: reactive bot
            if not react and s["score1"]: react, react_at = True, now; print(f"  score 1 at {now - run_start:.1f}s -> reactive bot on")
            # PD: ball keeps lateral momentum, so counter-steer on how fast the corridor drifts past us
            dt = max(now - prev[0], 1e-3)
            vel = (s["near"] - prev[1]) / dt
            prev = (now, s["near"])
            u = s["err"] + KD * vel
            steer = 0 if NOSTEER or not react or abs(u) < DEAD else (1 if u > 0 else -1)
            if DEBUG and runs < 6:
                pg.evaluate(OVERLAY, s["ov"])
                pg.screenshot(path=f"exp/r{runs}_{ticks:03d}.jpg", type="jpeg", quality=60)
            if ticks % 15 == 0: print(f"  t={time.time() - run_start:4.1f} err={s['err']:+.0f} track={s['track']}/{s['nt']} tunnel={s['tunnel']} tilt={s['th']} block={s['block']}")
            want = {-1: "ArrowLeft", 1: "ArrowRight", 0: None}[steer]
            if want != held:
                if held: pg.keyboard.up(held)
                if want: pg.keyboard.down(want)
                held = want
        b.close()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 120)
