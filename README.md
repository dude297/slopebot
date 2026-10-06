# slopebot

Experimental Slope autoplayer driven by direct Unity WebGL canvas perception and browser keyboard control.

The current prototype is intentionally simple: it runs the game in Playwright, reads pixels directly from the Unity canvas in page JavaScript, estimates a safe lateral corridor, and steers with left/right keyboard input.

## Current status

The bot already has a viable end-to-end loop:

- launches the Slope Unity WebGL game in Chromium
- forces `preserveDrawingBuffer` so the rendered canvas can be sampled
- reads the 960x540 canvas directly in JavaScript
- detects green road/crossbar geometry
- detects red obstacles and tunnel walls
- estimates track boundaries and a safe corridor
- switches from straight rolling to reactive control after score 1
- uses a PD-style lateral controller
- detects GAMEOVER and automatically restarts
- saves death screenshots
- provides a debug overlay and no-steer baseline mode

This is still an experimental prototype. The current perception stack is heuristic-heavy and assumes the 960x540 layout.

## Quick start

Requirements:

- Python 3.11+
- Playwright
- Chromium installed through Playwright

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
python bot.py 120
```

Useful modes:

```bash
DEBUG=1 python bot.py 120
NOSTEER=1 python bot.py 120
KD=0.15 DEAD=3 python bot.py 120
REACT=0 python probe.py
REACT=1 python explore.py
```

## Files

- `bot.py` — current perception, planning, control, restart loop
- `probe.py` — prints live sensor snapshots without steering
- `explore.py` — controlled scripted-key experiment and frame capture
- `recon*.py` — early game/canvas reconnaissance scripts
- `CLAUDE.md` — implementation guidance and engineering constraints
- `docs/CURRENT_STATE.md` — what works, what is brittle, known failure modes
- `docs/ARCHITECTURE.md` — target long-term system design
- `docs/ROADMAP.md` — staged roadmap with exit criteria
- `docs/EXPERIMENT_PROTOCOL.md` — how to evaluate changes instead of tuning by feel

## Engineering direction

Do not jump directly to reinforcement learning or a large rewrite.

The preferred development order is:

1. make experiments reproducible
2. add telemetry and death classification
3. build offline replay/regression tests
4. improve perception confidence and camera-roll handling
5. model ball dynamics and add trajectory prediction
6. tune the controller from data
7. only then consider more advanced learning-based components

The key principle is that a better controller cannot compensate for incorrect perception. Every major change should be evaluated against recorded runs and a baseline.

See `docs/ROADMAP.md` for the long-term plan.
