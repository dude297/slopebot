# Current State

Last reviewed against the prototype on the `master` branch after the phased score-1/reactive-control update.

## What works now

### Browser and game control

- Playwright launches Chromium at 960x540.
- The game is opened directly at the Unity page.
- `preserveDrawingBuffer` is forced during WebGL context creation.
- Keyboard input is issued through Playwright.
- The bot can release held keys on death/menu transitions.
- GAMEOVER is detected and the next run is started automatically.

### Perception

The sensor currently runs inside the browser page and reads the Unity canvas directly.

It includes:

- red-pixel classification for obstacles/walls
- green-pixel classification for road/grid/UI geometry
- long-run crossbar detection
- least-squares fitting of left/right road boundaries
- short-lived reuse of the last detected track
- tunnel detection from red geometry on both sides
- obstacle padding
- row-by-row safe-gap selection
- weighted target generation
- a debug overlay for track, padded obstacles, and path

### Control

The current behavior has two phases:

1. roll straight during the predictable opening section
2. activate reactive steering after the score-1 visual is detected

The controller combines path error with a derivative-like term from near-path motion and maps the sign to ArrowLeft/ArrowRight.

### Diagnostics

- `DEBUG=1` draws perception overlays and captures frames
- `NOSTEER=1` provides a baseline mode
- death screenshots are saved
- `probe.py` and `explore.py` can inspect the current sensor contract

## Known brittle areas

### Camera roll

The code contains rotated-coordinate infrastructure, but the active tilt is currently fixed:

```javascript
const th = 0
```

This means the bot does not actually compensate for camera roll yet.

### Resolution assumptions

Many coordinates and thresholds assume exactly 960x540, including:

- ball anchor
- score-region probes
- GAMEOVER text probes
- road-run widths
- viewport geometry

This is acceptable for the current experiment harness but must be made explicit and eventually parameterized.

### Score detection

The current score logic is not a general score reader. It detects the visual geometry associated with the digit 1 and uses that as a phase transition.

This should eventually become a general game-state/score subsystem.

### Track confidence

Track validity is currently inferred mostly from the existence and age of fitted crossbars. The planner needs an explicit confidence value so it can distinguish:

- strong road fit
- weak road fit
- stale road fit
- tunnel geometry
- unknown geometry

### Scene false positives

Green scenery can resemble road geometry. Earlier tilt-search attempts reportedly locked onto diagonal scenery/building lines. Future roll estimation must be constrained by road-consistent geometry rather than simply maximizing green-run length.

### Tuning

`KD`, `DEAD`, lookahead, margins, obstacle padding, and persistence are still heuristic constants. There is not yet enough telemetry to know whether failures are dominated by perception, planning, or controller dynamics.

## Most important unanswered questions

1. What percentage of deaths are perception failures versus control failures?
2. At what game speed does the current reactive controller become unstable?
3. How often is the fitted road boundary wrong before a death?
4. Is the lookahead horizon too short, or is the road estimate itself wrong?
5. How much lateral momentum remains after key release?
6. How effective is counter-steering as a brake?
7. Which scene types dominate failures: curves, tunnels, open edges, or obstacles?
8. Does track confidence fall before deaths in a way that can be used as a safety signal?

The telemetry milestone exists to answer these before major architectural changes.
