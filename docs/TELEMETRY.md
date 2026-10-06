# Telemetry

Every `bot.py` session writes to `telemetry/<YYYYmmdd-HHMMSS>/` (gitignored):

```
session.json        {session_id, started, commit ("<sha>[-dirty]"), params:{KD, DEAD, NOSTEER, DEBUG, HUMAN}, viewport}
run_NNN.jsonl       one object per control tick (schema below)
run_NNN_pre/        frame_KKK.jpg (480x270) + index.json [{i, t}]
                    bot: last ~40 frames before death (every 2nd tick, ~2.5 s)
                    HUMAN=1: every 3rd tick of the whole run
run_NNN_death.png   GAMEOVER screenshot (absent when end = timeout)
summary.jsonl       per run: {run, duration, react_at, ticks, end: gameover|timeout, mean_loop_ms, reversals}
```

## Per-tick fields

| field | meaning |
|---|---|
| `i`, `t` | tick index, seconds since run start |
| `phase` | `straight` (no steering until score 1), `react` (bot steering), `human` (HUMAN=1) |
| `err` | weighted look-ahead target, lateral, units of 6 px (+ = target right of ball) |
| `near` | safe-gap centre at the ball row, same units |
| `vel` | d(near)/dt, units/s |
| `u` | controller output `err + KD*vel` |
| `cmd` | key actually held: -1 left, 0 none, 1 right (human's key in HUMAN mode) |
| `bot_cmd` | what the controller wanted (sign of `u` outside deadband) — compare to `cmd` in human demos |
| `track`, `track_age`, `nt` | road-edge fit in use, frames since last fresh fit, crossbar points this frame |
| `tunnel` | red on both sides just ahead (known false positive: single red box straddling the ball) |
| `block` | px ahead where red blocks the current path, -1 none |
| `road` | any crossbar or red seen this tick (false streak ~ ball fell off) |
| `black` | fraction of near-black pixels |
| `sense_ms`, `loop_ms` | in-page sensor time, wall time since previous tick |

## Tools

- `python analyze.py --latest` / `analyze.py <session>` / `analyze.py <a> <b>` — survival stats, control/perception health, heuristic death categories, A/B comparison.
- `python replay.py <frames dir> [--overlay DIR] [--json out.jsonl]` — run the live `SENSE` on saved frames offline (pre-death frames included; they are upscaled to 960x540).
- `python replay.py --check fixtures/fixtures.json` — perception regression fixtures.
