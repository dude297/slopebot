#!/usr/bin/env python3
"""Analyze slopebot telemetry. Usage: analyze.py <session> [<session_b>] | --latest"""
import glob, json, os, re, statistics, sys

# --- death-classification thresholds (checked in this order) ---
WINDOW_S = 2.0          # look at last N seconds of ticks
FELL_S = 0.3            # fell_off: trailing road=false span >= this
BLOCK_FRAC = 0.30       # obstacle_ahead: share of react ticks with block>=0
LOST_FRAC = 0.50        # track_lost: share of react ticks with track=false & tunnel=false
OSC_REVERSALS = 3       # oscillation: cmd reversals in window
OVERSHOOT_ERR = 15      # overshoot: |err| >= this ...
OVERSHOOT_FRAC = 0.50   # ... with cmd==0 or cmd opposite err, in this share of react ticks


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def read_jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass  # truncated last line etc.
    except OSError:
        pass
    return out


def reversals(ticks):
    n, last = 0, 0
    for k in ticks:
        c = k.get("cmd", 0)
        if c:
            if last and c != last:
                n += 1
            last = c
    return n


def classify(ticks):
    """-> (category, evidence) from the last WINDOW_S seconds of ticks."""
    if not ticks:
        return "unknown", "no ticks"
    if ticks[-1].get("phase") == "straight":
        return "died_straight", "still in straight phase"
    # fell_off: trailing run of road=false
    j = len(ticks)
    while j > 0 and not ticks[j - 1].get("road", True):
        j -= 1
    gap = ticks[-1]["t"] - ticks[j]["t"] if j < len(ticks) else 0.0
    if gap >= FELL_S:
        return "fell_off", f"road=false for last {gap:.2f}s"
    w = [k for k in ticks if k["t"] >= ticks[-1]["t"] - WINDOW_S]
    r = [k for k in w if k.get("phase") == "react"] or w
    f = lambda pred: sum(1 for k in r if pred(k)) / len(r)
    b = f(lambda k: k.get("block", -1) >= 0)
    if b >= BLOCK_FRAC:
        return "obstacle_ahead", f"block>=0 in {b:.0%} of react ticks"
    lost = f(lambda k: not k.get("track", True) and not k.get("tunnel", False))
    if lost >= LOST_FRAC:
        return "track_lost", f"track=false/no tunnel in {lost:.0%}"
    rev = reversals(w)
    if rev >= OSC_REVERSALS:
        return "oscillation", f"{rev} reversals in {WINDOW_S:g}s"
    bad = f(lambda k: abs(k.get("err", 0)) >= OVERSHOOT_ERR and
            (k.get("cmd", 0) == 0 or k["cmd"] * k["err"] < 0))
    if bad >= OVERSHOOT_FRAC:
        return "overshoot", f"|err|>={OVERSHOOT_ERR} w/o correcting cmd in {bad:.0%}"
    return "unknown", f"block {b:.0%} lost {lost:.0%} rev {rev} bad {bad:.0%}"


def load(d):
    sess = {}
    try:
        with open(os.path.join(d, "session.json"), encoding="utf-8") as f:
            sess = json.load(f)
    except (OSError, ValueError):
        pass
    summ = {s.get("run"): s for s in read_jsonl(os.path.join(d, "summary.jsonl"))}
    runs = []
    for p in sorted(glob.glob(os.path.join(d, "run_*.jsonl"))):
        m = re.search(r"run_(\d+)\.jsonl$", p)
        if not m:
            continue
        n = int(m.group(1))
        ticks = read_jsonl(p)
        s = summ.get(n, {})
        react = [k for k in ticks if k.get("phase") == "react"]
        dur = s.get("duration", ticks[-1]["t"] if ticks else 0.0)
        ra = s["react_at"] if "react_at" in s else (react[0]["t"] if react else None)
        end = s.get("end", "gameover")
        cat, ev = ("survived", "timeout") if end == "timeout" else classify(ticks)
        runs.append(dict(run=n, ticks=ticks, react=react, dur=dur, react_at=ra, end=end,
                         cat=cat, ev=ev, rev=s.get("reversals", reversals(ticks)),
                         phase=ticks[-1].get("phase", "?") if ticks else "?"))
    return sess, runs


def metrics(runs):
    durs = [r["dur"] for r in runs]
    ticks = [k for r in runs for k in r["ticks"]]
    react = [k for r in runs for k in r["react"]]
    total_t = sum(durs)
    ras = [r["react_at"] for r in runs if r["react_at"] is not None]
    cats = {}
    for r in runs:
        cats[r["cat"]] = cats.get(r["cat"], 0) + 1
    P = lambda n, d: 100 * n / d if d else None
    loops = [k["loop_ms"] for k in ticks if "loop_ms" in k]
    return {
        "runs": len(runs), "median_s": pct(durs, 50), "p25_s": pct(durs, 25), "p75_s": pct(durs, 75),
        "min_s": min(durs, default=None), "max_s": max(durs, default=None),
        "react_pct": P(len(ras), len(runs)), "median_react_at_s": pct(ras, 50),
        "median_react_time_s": pct([r["dur"] - r["react_at"] for r in runs if r["react_at"] is not None], 50),
        "reversals_per_s": sum(r["rev"] for r in runs) / total_t if total_t else None,
        "cmd_active_pct": P(sum(1 for k in ticks if k.get("cmd")), len(ticks)),
        "loop_ms_mean": mean(loops), "loop_ms_p95": pct(loops, 95),
        "sense_ms_mean": mean([k["sense_ms"] for k in ticks if "sense_ms" in k]),
        "react_track_false_pct": P(sum(1 for k in react if not k.get("track", True)), len(react)),
        "tunnel_pct": P(sum(1 for k in ticks if k.get("tunnel")), len(ticks)),
        "road_false_pct": P(sum(1 for k in ticks if not k.get("road", True)), len(ticks)),
        "cats": cats,
    }


def fmt(v):
    return "-" if v is None else f"{v:.2f}" if isinstance(v, float) else str(v)


def report(d):
    sess, runs = load(d)
    m = metrics(runs)
    print(f"== {d}\nsession {sess.get('session_id', '?')} commit {sess.get('commit', '?')} "
          f"started {sess.get('started', '?')}\nparams {sess.get('params', {})}  runs {m['runs']}")
    for title, keys in [("survival", ["median_s", "p25_s", "p75_s", "min_s", "max_s", "react_pct",
                                      "median_react_at_s", "median_react_time_s"]),
                        ("control", ["reversals_per_s", "cmd_active_pct", "loop_ms_mean", "loop_ms_p95", "sense_ms_mean"]),
                        ("perception", ["react_track_false_pct", "tunnel_pct", "road_false_pct"])]:
        print(f"\n[{title}]")
        for k in keys:
            print(f"  {k:24s} {fmt(m[k])}")
    print("\n[deaths]\n  run  dur    phase     category        evidence")
    for r in runs:
        print(f"  {r['run']:3d}  {r['dur']:5.1f}  {r['phase']:8s}  {r['cat']:14s}  {r['ev']}")
    print("\n[categories]")
    for c, n in sorted(m["cats"].items(), key=lambda x: -x[1]):
        print(f"  {c:16s} {n}")


def compare(a, b):
    ma, mb = metrics(load(a)[1]), metrics(load(b)[1])
    print(f"A = {a}\nB = {b}\n\n  {'metric':22s} {'A':>9s} {'B':>9s} {'delta':>9s}")
    for k in ["runs", "median_s", "p25_s", "react_pct", "reversals_per_s"]:
        d = None if ma[k] is None or mb[k] is None else mb[k] - ma[k]
        print(f"  {k:22s} {fmt(ma[k]):>9s} {fmt(mb[k]):>9s} {fmt(d):>9s}")
    print("\n  categories")
    for c in sorted(set(ma["cats"]) | set(mb["cats"])):
        x, y = ma["cats"].get(c, 0), mb["cats"].get(c, 0)
        print(f"  {c:22s} {x:9d} {y:9d} {y - x:+9d}")


def main(argv):
    if argv and argv[0] == "--latest":
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telemetry")
        ds = [p for p in glob.glob(os.path.join(base, "*")) if os.path.isdir(p)]
        if not ds:
            sys.exit("no sessions under " + base)
        argv = [max(ds, key=os.path.getmtime)]
    if len(argv) == 1:
        report(argv[0])
    elif len(argv) == 2:
        compare(*argv)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
