"""Slope bot: reads the Unity WebGL canvas in-page, steers with arrow keys.
Run: python bot.py [seconds]
"""
import sys, time, os, json, base64, subprocess
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
// human key state for HUMAN=1 demonstrations: window._hk = -1 left, 0, 1 right
window._hk = 0;
const HK = {ArrowLeft: -1, KeyA: -1, ArrowRight: 1, KeyD: 1}, hkDown = new Set();
const hkUpd = () => { let v = 0; for (const c of hkDown) v += HK[c]; window._hk = Math.sign(v); };
addEventListener('keydown', e => { if (HK[e.code]) { hkDown.add(e.code); hkUpd(); } }, true);
addEventListener('keyup', e => { if (HK[e.code]) { hkDown.delete(e.code); hkUpd(); } }, true);
"""

# Two boundaries, sampled in a frame rotated about the ball (camera rolls on slopes/curves):
#  u = lateral offset from ball (+ right), v = offset along screen-up axis (- ahead, + toward camera).
#  1. TRACK: road crossbars = long green runs passing under the ball. Tilt = angle whose scanlines make
#     them longest. Fit lo(v)/hi(v) through crossbar endpoints, extrapolate ahead.
#     In the tunnel (red on both sides) the red walls are the track, crossbar fit is skipped.
#  2. OBSTACLES: red runs within LOOK px ahead, padded by ~ball radius.
# Safe zone per row = track minus padded red; walk forward picking the gap nearest the path.
SENSE = f"""(REACT) => {{
  const T0 = performance.now();
  const BX={BALL_X}, BY={BALL_Y}, U={UNIT}, LOOK=100, STRAIGHT=!REACT;
  const src = document.querySelector('#unity-canvas');
  const C = window._fc || (window._fc = Object.assign(document.createElement('canvas'), {{width: 960, height: 540}}));
  const g2 = C.getContext('2d', {{willReadFrequently: true}});
  g2.drawImage(src, 0, 0, 960, 540);
  const d = g2.getImageData(0, 0, 960, 540).data;
  // on death the game freezes the last frame for >2.5 s before GAMEOVER (with slight blur jitter):
  // frozen = <1% of sampled pixels changed by >40 since the previous tick
  const NS = d.length >> 6, prev = window._prev, cur = new Uint8Array(NS);
  let black = 0, n = 0, chg = 0;
  for (let i = 0, k = 0; i < d.length; i += 64, k++) {{
    n++; if (d[i] + d[i+1] + d[i+2] < 40) black++;
    cur[k] = d[i+1]; if (prev && Math.abs(cur[k] - prev[k]) > 40) chg++;
  }}
  black /= n;
  const frozen = !!prev && chg < 0.01 * n; window._prev = cur;
  const isR = i => d[i] > 150 && d[i+1] < 100, isG = i => d[i+1] > 150 && d[i] < 100;
  const gw = (y, a, b) => {{ let k = 0; for (let x = a; x < b; x++) if (isG((y*960 + x) * 4)) k++; return k; }};
  // score digit top-centre: row 25 is above the tutorial text. "1" = ~9px bar, "0"/"2".. = ~30px box
  // "1" = bar at x 472-488 with empty columns either side, on rows above (22,26) and below (62,66) the text
  const one = [22, 26, 62, 66].every(y => gw(y, 472, 489) >= 7 && gw(y, 440, 470) === 0 && gw(y, 491, 520) === 0);
  // GAMEOVER title text: ~120px green on rows 70/75 in x 320-640 (menu: 0, gameplay: <=32)
  // ...and nothing beside the title (tunnel ceiling arcs also hit rows 70/75 but fill x<300 / x>660)
  let side = 0; for (let y = 60; y <= 110; y += 5) side += gw(y, 0, 300) + gw(y, 660, 960);
  const over = black > 0.78 && gw(70, 320, 640) >= 90 && gw(75, 320, 640) >= 90 && side < 20;

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
  return {{black, over, frozen, score1: one, err: target / U, near: nearU / U, block, track: !!track, tunnel, nt: pts.length,
          th: Math.round(th * 57.3), road: pts.length > 0 || anyRed,
          track_age: window._trk ? window._trk.age : null, sense_ms: performance.now() - T0, ov: {{path, reds, tr}}}};
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


RUNS = int(os.environ.get("RUNS", 0))   # stop after N finished runs (0 = run for `seconds`)
# HUMAN=1: you play in the browser window, the bot only records (your keys -> cmd, phase "human")
HUMAN = os.environ.get("HUMAN") == "1"
# pre-death buffer: 150 frames every 2nd tick (~6.5 s: death animations - fall/freeze - last 2-3 s);
# human demos keep every 3rd frame of the whole run
RING_N, RING_EVERY = (100000, 3) if HUMAN else (150, 2)

# SENSE + rolling pre-death frame buffer (480x270 jpeg, in page) in one round trip
TICK = "(a) => { const s = (" + SENSE + """)(a.react);
  if (a.ring && !s.frozen) { const src = document.querySelector('#unity-canvas');
    const c = window._rc || (window._rc = Object.assign(document.createElement('canvas'), {width: 480, height: 270}));
    c.getContext('2d').drawImage(src, 0, 0, 480, 270);
    const r = window._ring || (window._ring = []); r.push([a.i, a.t, c.toDataURL('image/jpeg', 0.6)]);
    if (r.length > %d) r.shift(); }
  s.hk = window._hk || 0; return s; }""" % RING_N
TAKE_RING = "() => { const r = window._ring || []; window._ring = []; return r; }"


class Telemetry:
    """telemetry/<session>/: session.json, run_NNN.jsonl (per tick), run_NNN_pre/ (pre-death frames),
    run_NNN_death.png, summary.jsonl. Schema documented in docs/TELEMETRY.md."""

    def __init__(self):
        self.sid = time.strftime("%Y%m%d-%H%M%S")
        self.dir = os.path.join("telemetry", self.sid)
        os.makedirs(self.dir, exist_ok=True)
        try: commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        except OSError: commit = ""
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "bot.py"], capture_output=True, text=True).stdout.strip())
        with open(os.path.join(self.dir, "session.json"), "w") as f:
            json.dump({"session_id": self.sid, "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "commit": commit + ("-dirty" if dirty else ""),
                       "params": {"KD": KD, "DEAD": DEAD, "NOSTEER": NOSTEER, "DEBUG": DEBUG, "HUMAN": HUMAN}, "viewport": [960, 540]}, f, indent=1)
        self.f = None

    def start(self, run):
        self.run, self.rows, self.last_cmd, self.reversals = run, 0, 0, 0
        self.loop_sum = 0.0
        self.f = open(os.path.join(self.dir, f"run_{run:03d}.jsonl"), "w")

    def tick(self, rec):
        self.f.write(json.dumps(rec, separators=(",", ":")) + "\n")
        self.rows += 1; self.loop_sum += rec["loop_ms"]
        if rec["cmd"] and self.last_cmd and rec["cmd"] != self.last_cmd: self.reversals += 1
        if rec["cmd"]: self.last_cmd = rec["cmd"]

    def end(self, pg, duration, react_at, how, death_t=None):
        self.f.close(); self.f = None
        pre = os.path.join(self.dir, f"run_{self.run:03d}_pre"); os.makedirs(pre, exist_ok=True)
        idx = []
        for k, (i, t, url) in enumerate(pg.evaluate(TAKE_RING)):
            with open(os.path.join(pre, f"frame_{k:03d}.jpg"), "wb") as f: f.write(base64.b64decode(url.split(",", 1)[1]))
            idx.append({"i": i, "t": t})
        with open(os.path.join(pre, "index.json"), "w") as f: json.dump(idx, f)
        if how == "gameover": pg.screenshot(path=os.path.join(self.dir, f"run_{self.run:03d}_death.png"))
        with open(os.path.join(self.dir, "summary.jsonl"), "a") as f:
            f.write(json.dumps({"run": self.run, "duration": round(duration, 3), "react_at": react_at, "ticks": self.rows, "end": how, "death_t": death_t,
                                "mean_loop_ms": round(self.loop_sum / max(self.rows, 1), 2), "reversals": self.reversals}) + "\n")


def main(seconds=120):
    tel = Telemetry()
    print(f"telemetry -> {tel.dir}")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=False)
        pg = b.new_page(viewport={"width": 960, "height": 540})
        pg.add_init_script(INIT)
        pg.goto(GAME, referer="https://yoplay.io/")
        pg.wait_for_function("window.unityInstance", timeout=90000)
        pg.wait_for_timeout(6000)

        held, runs, run_start, last_click, react, ticks, over_n = None, 0, None, 0, False, 0, 0
        t0 = last_tick = time.time()
        while time.time() - t0 < seconds and not (RUNS and runs >= RUNS):
            tick_start = time.time()
            rt = tick_start - run_start if run_start else 0.0
            s = pg.evaluate(TICK, {"react": react, "ring": run_start is not None and ticks % RING_EVERY == 0, "i": ticks, "t": round(rt, 3)})
            over_n = over_n + 1 if s["over"] else 0  # GAMEOVER is static: require 3 ticks in a row
            if over_n >= 3 or (run_start is None and s["black"] > 0.78):  # GAMEOVER, or menu before a run
                if held: pg.keyboard.up(held); held = None
                if run_start and over_n >= 3:
                    runs += 1
                    sw = f"bot from {react_at - run_start:.1f}s" if react else "never reached score 1"
                    print(f"run {runs}: {time.time() - run_start:.1f}s ({sw})")
                    tel.end(pg, time.time() - run_start, round(react_at - run_start, 3) if react else None, "gameover", round(dead_at - run_start, 3) if dead_at else None)
                    run_start = None
                if time.time() - last_click > 1.5:
                    pg.mouse.click(480, 310, delay=100)
                    last_click = time.time()
                continue
            now = time.time()
            if run_start is None:
                freeze_at = dead_at = None
                run_start = now; ticks = 0; prev = (now, s["near"]); react = HUMAN  # human: full sensing from t=0
                if HUMAN: react_at = now
                pg.evaluate("() => { window._ring = []; window._trk = null; }")
                tel.start(runs + 1)
            ticks += 1
            freeze_at = (freeze_at or now) if s["frozen"] else None
            if freeze_at and now - freeze_at >= 0.5: dead_at = freeze_at  # frozen >= 0.5 s = ball died at freeze onset
            # phase 1: roll straight (predictable) until score shows 1; phase 2: reactive bot
            if not react and s["score1"]: react, react_at = True, now; print(f"  score 1 at {now - run_start:.1f}s -> reactive bot on")
            # PD: ball keeps lateral momentum, so counter-steer on how fast the corridor drifts past us
            dt = max(now - prev[0], 1e-3)
            vel = (s["near"] - prev[1]) / dt
            prev = (now, s["near"])
            u = s["err"] + KD * vel
            bot_cmd = 0 if abs(u) < DEAD else (1 if u > 0 else -1)  # what the controller wants
            steer = 0 if HUMAN or NOSTEER or not react else bot_cmd
            if DEBUG and runs < 6:
                pg.evaluate(OVERLAY, s["ov"])
                pg.screenshot(path=f"exp/r{runs}_{ticks:03d}.jpg", type="jpeg", quality=60)
            if ticks % 15 == 0: print(f"  t={time.time() - run_start:4.1f} err={s['err']:+.0f} track={s['track']}/{s['nt']} tunnel={s['tunnel']} tilt={s['th']} block={s['block']}")
            want = {-1: "ArrowLeft", 1: "ArrowRight", 0: None}[steer]
            if want != held:
                if held: pg.keyboard.up(held)
                if want: pg.keyboard.down(want)
                held = want
            tel.tick({"i": ticks, "t": round(now - run_start, 3), "phase": "human" if HUMAN else "react" if react else "straight",
                      "err": round(s["err"], 2), "near": round(s["near"], 2), "vel": round(vel, 2), "u": round(u, 2),
                      "cmd": s["hk"] if HUMAN else steer, "bot_cmd": bot_cmd,
                      "track": s["track"], "track_age": s["track_age"], "nt": s["nt"], "tunnel": s["tunnel"], "block": s["block"],
                      "road": s["road"], "frozen": s["frozen"], "black": round(s["black"], 3), "sense_ms": round(s["sense_ms"], 2),
                      "loop_ms": round((time.time() - last_tick) * 1000, 1)})
            last_tick = time.time()
        if run_start:  # session ended mid-run
            if held: pg.keyboard.up(held)
            tel.end(pg, time.time() - run_start, round(react_at - run_start, 3) if react else None, "timeout")
        b.close()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 120)
