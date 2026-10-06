# CLAUDE.md

This repository contains an experimental browser-game autoplayer. Treat the current `bot.py` as a working prototype that must be measured before it is rewritten.

## Primary objective

Improve survival and consistency while preserving a deterministic, debuggable control loop.

The goal is not merely to produce a visually impressive bot. The goal is to build a system where failures can be explained from telemetry and regression-tested.

## Rules for future work

1. **Do not tune blindly.** Before changing thresholds, gains, lookahead, padding, or geometry rules, collect baseline runs and record the result.
2. **Do not replace the current direct-canvas approach without evidence.** Reading the Unity canvas in page JavaScript avoids Python screenshot-transfer latency and is currently an architectural advantage.
3. **Keep a no-steer baseline.** `NOSTEER=1` is useful for measuring the natural opening section and detecting regressions in game-state logic.
4. **Keep helper tools working.** Any change to the sensor contract must update `probe.py`, `explore.py`, tests, and docs in the same PR.
5. **Prefer small, measurable PRs.** Perception, planning, control, telemetry, and tooling should not all be rewritten in one change.
6. **Preserve debug visibility.** Every important perception output should be visualizable on the overlay or serialized to telemetry.
7. **Do not hard-code a new heuristic without documenting its failure mode and confidence signal.**
8. **Do not optimize for one lucky run.** Compare distributions across multiple runs.
9. **Use recorded frames for regression tests.** Once representative frames exist, major perception bugs should become reproducible offline.
10. **Update CURRENT_STATE.md after material behavior changes.**

## Immediate priority order

### P0 — Instrumentation and reproducibility

- add structured per-tick telemetry
- log run ID, timestamp, score/state, error, near error, lateral velocity, steering command, track confidence, tunnel state, obstacle geometry, and controller parameters
- keep a rolling pre-death buffer so the final seconds of every run can be inspected
- write one JSONL file per run or one session-level file with run IDs
- record the reason a run terminated when inferable
- add a session summary with survival time and score

### P1 — Offline replay and regression

Build an offline sensor harness that can feed recorded frames through the perception logic without launching the game. This is required before making major perception changes.

Create a small curated fixture set containing at minimum:

- opening straight
- ordinary turn
- narrow section
- tunnel entry
- tunnel interior
- red obstacle left
- red obstacle center
- red obstacle right
- road-edge/drop-off case
- camera-roll/tilted case
- game-over screen
- score/UI screen

Tests should assert geometry ranges or classifications rather than exact pixels when exactness is brittle.

### P2 — Perception quality

Current weaknesses to address:

- `th = 0` means camera-roll compensation is described but not implemented
- road fitting can lock onto scenery or stale crossbars
- track reuse is time-based rather than confidence-based
- score detection only recognizes the specific score-1 transition
- many constants assume exactly 960x540
- color thresholds are global and not confidence-scored

Add explicit confidence values for track, obstacle, tunnel, and game-state detection. The planner should respond differently to low-confidence perception than to high-confidence perception.

### P3 — Dynamics and prediction

Before adding more aggressive steering, estimate the ball's lateral dynamics from controlled experiments.

Measure:

- response latency after key-down
- lateral acceleration under left/right hold
- momentum after key release
- effective braking from counter-steer
- how the relationship changes with game speed

Use this to predict future lateral position over a short horizon instead of reacting only to current error.

### P4 — Controller

The current controller is approximately:

```
u = err + KD * lateral_velocity
```

Long term, make control explicit and testable:

- target lateral position
- predicted ball state
- predicted safe corridor
- steering policy
- deadband/hysteresis
- command duration

Avoid rapid key chatter. Consider pulse-width control or hysteresis if continuous hold/release oscillates.

### P5 — Parameter optimization

Only after telemetry and replay exist:

- define objective metrics
- run repeated seeded/comparable sessions when possible
- search `KD`, deadband, lookahead, safety padding, confidence thresholds, and steering pulse policy
- optimize median and lower-percentile performance, not best-ever score

### P6 — Long-term modularization

Do not refactor just for aesthetics. Split `bot.py` once interfaces are stable.

Target modules are documented in `docs/ARCHITECTURE.md`.

## Definition of a meaningful improvement

A change should normally satisfy at least one of these:

- increases median survival across repeated runs
- improves lower-percentile survival
- fixes a reproducible perception failure on recorded fixtures
- reduces false steering events
- makes a previously opaque failure diagnosable
- removes brittle coupling without behavior regression

"Looked better in one run" is not sufficient evidence.

## Commit/PR expectations

For non-trivial changes, include:

- hypothesis
- implementation summary
- before/after run counts
- before/after metrics
- representative failure screenshots or telemetry notes
- known regressions or untested cases
- next recommended experiment
