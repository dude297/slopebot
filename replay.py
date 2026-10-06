"""Offline perception replay: run bot.SENSE on recorded frames, no game needed.
  python replay.py frames/ [more files/dirs] [--react 0|1] [--fresh] [--json out.jsonl] [--overlay DIR]
  python replay.py --check fixtures/fixtures.json
"""
import argparse, base64, glob, json, mimetypes, os, sys
from playwright.sync_api import sync_playwright
from bot import SENSE, OVERLAY

PAGE = ('<body style="margin:0"><canvas id="unity-canvas" width="960" height="540" '
        'style="position:absolute;left:0;top:0"></canvas></body>')
LOAD = """async (url) => {
  const im = new Image(); im.src = url; await im.decode();
  const c = document.querySelector('#unity-canvas').getContext('2d');
  c.drawImage(im, 0, 0, 960, 540);
}"""


def collect(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            out += sorted(f for e in ("jpg", "jpeg", "png") for f in glob.glob(os.path.join(p, "*." + e)))
        else:
            out.append(p)
    return out


class Replayer:
    def __init__(self, pw):
        self.b = pw.chromium.launch()
        self.pg = self.b.new_page(viewport={"width": 960, "height": 540})
        self.pg.set_content(PAGE)

    def run(self, path, react=1, fresh=False):
        mime = mimetypes.guess_type(path)[0] or "image/png"
        with open(path, "rb") as f:
            url = f"data:{mime};base64," + base64.b64encode(f.read()).decode()
        if fresh:
            self.pg.evaluate("delete window._trk")
        self.pg.evaluate(LOAD, url)
        return self.pg.evaluate(SENSE, react)

    def overlay(self, ov, out):
        self.pg.evaluate(OVERLAY, ov)
        self.pg.screenshot(path=out)


def match(got, want):
    if isinstance(want, list):
        return isinstance(got, (int, float)) and want[0] <= got <= want[1]
    return got == want


def check(rp, fx_path):
    base = os.path.dirname(os.path.abspath(fx_path))
    bad = 0
    for fx in json.load(open(fx_path)):
        r = rp.run(os.path.join(base, fx["image"]), fx.get("react", 1), fresh=True)
        fails = [f"{k}={r.get(k)!r} want {v}" for k, v in fx["expect"].items() if not match(r.get(k), v)]
        bad += bool(fails)
        print(("FAIL " if fails else "PASS ") + fx["image"], "; ".join(fails))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="*")
    ap.add_argument("--react", type=int, default=1)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--overlay")
    ap.add_argument("--check")
    a = ap.parse_args()
    with sync_playwright() as pw:
        rp = Replayer(pw)
        if a.check:
            return check(rp, a.check)
        files = collect(a.inputs)
        if a.overlay:
            os.makedirs(a.overlay, exist_ok=True)
        jf = open(a.json, "w") if a.json else None
        if not jf:
            print(f"{'frame':14}{'over':>6}{'sc1':>6}{'err':>8}{'near':>8}{'trk':>5}{'tun':>5}{'blk':>6}{'road':>6}")
        for f in files:
            r = rp.run(f, a.react, a.fresh)
            ov = r.pop("ov", None)
            name = os.path.basename(f)
            if jf:
                jf.write(json.dumps({"frame": name, **r}) + "\n")
            else:
                print(f"{name:14}{int(r['over']):>6}{int(r['score1']):>6}{r['err']:>8.1f}{r['near']:>8.1f}"
                      f"{int(r['track']):>5}{int(r['tunnel']):>5}{r['block']:>6}{int(r['road']):>6}")
            if a.overlay and ov:
                rp.overlay(ov, os.path.join(a.overlay, os.path.splitext(name)[0] + ".png"))
        if jf:
            jf.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
